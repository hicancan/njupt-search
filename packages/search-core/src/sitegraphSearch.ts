import {
    RankedSitegraphDocument,
    SitegraphDocMeta,
    SitegraphFullDocument,
    SitegraphIndexBundle,
    SitegraphInvertedIndex,
    SitegraphQueryStats,
    SitegraphSearchCoverage,
    SitegraphSearchEvent,
    SitegraphSearchFilters,
    SitegraphSearchPhase,
    SitegraphSortMode
} from '@njupt-search/contracts';
import { fetchJson } from './fetchJson';
import {
    parseSitegraphFullDocuments,
    parseSitegraphInvertedIndex,
    SearchContractError
} from './sitegraphContract';
import { sitegraphDocumentMatchesFilters } from './sitegraphFilters';
import { rankingDateSortValue, rankSitegraphDocument, SITEGRAPH_FIELD_WEIGHTS } from './ranking/rankDocument';
import { expandSitegraphQueryPhrases, normalizeSearchText as normalize, tokenizeSitegraphQuery } from './tokenizer';
const DEFAULT_CANDIDATE_LIMIT = 160;
const DEFAULT_MAX_SHARD_LOADS = 40;
const QUICK_MAX_SHARD_LOADS = 8;
const BODY_MAX_SHARD_LOADS = 18;
const HYDRATE_MAX_SHARD_LOADS = 40;
const SHARD_BATCH_SIZE = 4;
const LIGHT_SEARCH_FIELDS = ['title', 'section', 'nav_path', 'tags', 'attachments', 'external', 'system'];
const BODY_SEARCH_FIELDS = [...LIGHT_SEARCH_FIELDS, 'summary', 'content'];
const FULL_SCAN_FIELDS = ['title', 'section', 'nav_path', 'summary', 'content', 'attachments', 'url'];

const shardCache = new Map<string, SitegraphFullDocument[]>();

interface SearchTelemetry {
    lightMetaFallbackDocIndices: Set<number>;
    fullScanMatchDocIndices: Set<number>;
}

const publicAssetPath = (path: string): string => {
    if (/^https?:\/\//.test(path) || path.startsWith('/')) return path;
    return `/${path}`;
};

const shardPathForMeta = (bundle: SitegraphIndexBundle, meta: SitegraphDocMeta): string | null => {
    if (meta.shard.path) return meta.shard.path;
    return bundle.manifest.sitegraph.full_shards.find(shard => shard.shard_id === meta.shard.shard_id)?.path || null;
};

const loadShard = (path: string, signal: AbortSignal): Promise<SitegraphFullDocument[]> => {
    const existing = shardCache.get(path);
    if (existing) return Promise.resolve(existing);
    return fetchJson(publicAssetPath(path), signal, 'shard')
        .then(payload => {
            const documents = parseSitegraphFullDocuments(payload, path);
            shardCache.set(path, documents);
            return documents;
        });
};

const ensureBodyIndex = async (bundle: SitegraphIndexBundle, signal: AbortSignal): Promise<SitegraphInvertedIndex> => {
    if (bundle.bodyInvertedIndex) return bundle.bodyInvertedIndex;
    const bodyPath = bundle.manifest.artifacts.body_inverted_index.path;
    const payload = await fetchJson(publicAssetPath(bodyPath), signal, 'index');
    bundle.bodyInvertedIndex = parseSitegraphInvertedIndex(payload, bodyPath);
    return bundle.bodyInvertedIndex;
};

const ensureShardFilter = async (
    bundle: SitegraphIndexBundle,
    signal: AbortSignal
): Promise<NonNullable<SitegraphIndexBundle['shardFilter']>> => {
    if (bundle.shardFilter) return bundle.shardFilter;
    const filterPath = bundle.manifest.artifacts.shard_filter.path;
    const payload = await fetchJson(publicAssetPath(filterPath), signal, 'index');
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
        throw new SearchContractError(`Validation failed for ${filterPath}: shard_filter must be an object`);
    }
    bundle.shardFilter = payload as NonNullable<SitegraphIndexBundle['shardFilter']>;
    return bundle.shardFilter;
};

const textBlob = (document: SitegraphFullDocument | SitegraphDocMeta, fields: Array<keyof SitegraphFullDocument | keyof SitegraphDocMeta>): string => {
    const values: string[] = [];
    for (const field of fields) {
        const value = document[field as keyof typeof document];
        if (Array.isArray(value)) values.push(...value.map(String));
        else if (value !== null && value !== undefined) values.push(String(value));
    }
    return normalize(values.join(' '));
};

const fullScanBlob = (document: SitegraphFullDocument): string => normalize([
    document.title,
    document.section,
    document.nav_path_text,
    document.nav_path.join(' '),
    document.summary,
    document.content,
    document.url,
    document.attachments
        .map(attachment => [attachment.name, attachment.extension, attachment.url, attachment.section, attachment.parent_url].filter(Boolean).join(' '))
        .join(' ')
].join(' '));

const throwIfAborted = (signal: AbortSignal): void => {
    if (signal.aborted) {
        throw new DOMException('Search cancelled', 'AbortError');
    }
};

const yieldToWorker = async (): Promise<void> => {
    await new Promise(resolve => setTimeout(resolve, 0));
};

const applyPostings = (
    scores: Map<number, number>,
    tokens: SitegraphInvertedIndex['tokens'],
    terms: string[]
): void => {
    for (const term of terms) {
        const postings = tokens[term];
        if (!postings) continue;
        for (const [field, ids] of Object.entries(postings)) {
            const weight = SITEGRAPH_FIELD_WEIGHTS[field] || 8;
            for (const docIndex of ids) {
                scores.set(docIndex, (scores.get(docIndex) || 0) + weight + Math.min(term.length, 8));
            }
        }
    }
};

const applyLightMetaFallback = (
    bundle: SitegraphIndexBundle,
    scores: Map<number, number>,
    normalizedQuery: string,
    filters: SitegraphSearchFilters,
    now: number
): number[] => {
    if (!normalizedQuery) return [];
    let filteredScoreCount = 0;
    for (const docIndex of scores.keys()) {
        const meta = bundle.docMeta[docIndex];
        if (meta && sitegraphDocumentMatchesFilters(meta, filters, now)) filteredScoreCount += 1;
        if (filteredScoreCount >= 8) return [];
    }
    const matchedIndices: number[] = [];
    for (const meta of bundle.docMeta) {
        if (!sitegraphDocumentMatchesFilters(meta, filters, now)) continue;
        const haystack = textBlob(meta, ['title', 'section', 'nav_path_text']);
        if (haystack.includes(normalizedQuery)) {
            scores.set(meta.doc_index, (scores.get(meta.doc_index) || 0) + 90);
            matchedIndices.push(meta.doc_index);
        }
    }
    return matchedIndices;
};

const sortedScoreEntries = (scores: Map<number, number>): Array<[number, number]> => {
    return Array.from(scores.entries()).sort((a, b) => {
        const scoreDelta = b[1] - a[1];
        if (scoreDelta !== 0) return scoreDelta;
        return a[0] - b[0];
    });
};

const candidateShardPaths = (
    bundle: SitegraphIndexBundle,
    scores: Map<number, number>,
    candidateLimit: number,
    maxShardLoads: number,
    filters: SitegraphSearchFilters,
    now: number
): { indices: number[]; paths: string[] } => {
    const indices: number[] = [];
    const paths: string[] = [];
    const seenPaths = new Set<string>();
    for (const [docIndex] of sortedScoreEntries(scores).slice(0, candidateLimit)) {
        const meta = bundle.docMeta[docIndex];
        if (!meta?.shard?.shard_id) continue;
        if (!sitegraphDocumentMatchesFilters(meta, filters, now)) continue;
        const shardPath = shardPathForMeta(bundle, meta);
        if (!shardPath) continue;
        const isNewShard = !seenPaths.has(shardPath);
        if (isNewShard && seenPaths.size >= maxShardLoads) continue;
        indices.push(docIndex);
        if (isNewShard) {
            seenPaths.add(shardPath);
            paths.push(shardPath);
        }
    }
    return { indices, paths };
};

const loadShardBatch = async (
    paths: string[],
    signal: AbortSignal,
    loadedShardPaths: Set<string>,
    fullDocsByIndex: Map<number, SitegraphFullDocument>
): Promise<void> => {
    for (let index = 0; index < paths.length; index += SHARD_BATCH_SIZE) {
        throwIfAborted(signal);
        const batch = paths.slice(index, index + SHARD_BATCH_SIZE);
        const shardResults = await Promise.all(batch.map(path => loadShard(path, signal)));
        shardResults.forEach((documents, batchIndex) => {
            const path = batch[batchIndex];
            if (path) loadedShardPaths.add(path);
            for (const document of documents) {
                fullDocsByIndex.set(document.doc_index, document);
            }
        });
        await yieldToWorker();
    }
};

const sortRankedResults = (
    results: RankedSitegraphDocument[],
    sortMode: SitegraphSortMode = 'relevance'
): RankedSitegraphDocument[] => {
    return results.sort((a, b) => {
        const dateDelta = rankingDateSortValue(b) - rankingDateSortValue(a);
        if (sortMode === 'date_desc' && dateDelta !== 0) return dateDelta;
        const scoreDelta = b.score - a.score;
        if (scoreDelta !== 0) return scoreDelta;
        if (dateDelta !== 0) return dateDelta;
        return a.id.localeCompare(b.id);
    });
};

const mergeRankedResults = (
    resultMap: Map<string, RankedSitegraphDocument>,
    incoming: RankedSitegraphDocument[]
): number => {
    let addedOrImproved = 0;
    for (const result of incoming) {
        const existing = resultMap.get(result.id);
        if (!existing || result.score > existing.score) {
            resultMap.set(result.id, result);
            addedOrImproved += 1;
        }
    }
    return addedOrImproved;
};

const loadedBytesFor = (bundle: SitegraphIndexBundle, loadedShardPaths: Set<string>, usedBodyIndex: boolean): number => {
    const artifacts = bundle.manifest.artifacts;
    const initialBytes = artifacts.doc_meta_light.bytes + artifacts.light_inverted_index.bytes + artifacts.query_aliases.bytes;
    const bodyBytes = usedBodyIndex ? artifacts.body_inverted_index.bytes : 0;
    const filterBytes = bundle.shardFilter ? artifacts.shard_filter.bytes : 0;
    const shardBytesByPath = new Map(bundle.manifest.sitegraph.full_shards.map(shard => [shard.path, shard.bytes]));
    let shardBytes = 0;
    for (const path of loadedShardPaths) {
        shardBytes += shardBytesByPath.get(path) || 0;
    }
    return initialBytes + bodyBytes + filterBytes + shardBytes;
};

const rankedSnapshot = (
    resultMap: Map<string, RankedSitegraphDocument>,
    stats: SitegraphQueryStats,
    limit: number,
    sortMode: SitegraphSortMode
): RankedSitegraphDocument[] => {
    return sortRankedResults(Array.from(resultMap.values()), sortMode)
        .slice(0, limit)
        .map(result => ({ ...result, query_stats: stats }));
};

const coverageFor = (
    bundle: SitegraphIndexBundle,
    phase: SitegraphSearchPhase,
    searchedFields: string[],
    provedNoMatchShards: number,
    scannedShards: number,
    searchedDocuments: number,
    loadedShardPaths: Set<string>,
    usedBodyIndex: boolean,
    exhaustiveComplete: boolean
): SitegraphSearchCoverage => ({
    phase,
    searched_fields: searchedFields,
    proved_no_match_shards: provedNoMatchShards,
    scanned_shards: scannedShards,
    total_shards: bundle.manifest.progressive_search?.total_shards ?? bundle.manifest.sitegraph.full_shards.length,
    searched_documents: searchedDocuments,
    total_documents: bundle.manifest.progressive_search?.total_documents ?? bundle.manifest.total_documents,
    loaded_bytes: loadedBytesFor(bundle, loadedShardPaths, usedBodyIndex),
    used_body_index: usedBodyIndex,
    exhaustive_complete: exhaustiveComplete,
});

const statsFor = (
    phase: SitegraphSearchPhase,
    coverage: SitegraphSearchCoverage,
    loadedShardPaths: Set<string>,
    candidateCount: number,
    resultMap: Map<string, RankedSitegraphDocument>,
    telemetry: SearchTelemetry
): SitegraphQueryStats => ({
    phase,
    coverage,
    usedBodyIndex: coverage.used_body_index,
    loadedShardCount: loadedShardPaths.size,
    loadedShardPaths: Array.from(loadedShardPaths).sort(),
    candidateCount,
    exhaustiveComplete: coverage.exhaustive_complete,
    resultCount: resultMap.size,
    fallbacks: {
        lightMetaFallbackDocuments: telemetry.lightMetaFallbackDocIndices.size,
        snippetFallbackResults: Array.from(resultMap.values()).filter(result => result.match_snippet?.fallback === true).length,
        exhaustiveFullScanMatches: telemetry.fullScanMatchDocIndices.size,
    },
});

const rankHydratedCandidates = (
    indices: number[],
    fullDocsByIndex: Map<number, SitegraphFullDocument>,
    scores: Map<number, number>,
    query: string,
    terms: string[],
    matchPhrases: string[],
    filters: SitegraphSearchFilters,
    now: number
): RankedSitegraphDocument[] => {
    return indices
        .map(docIndex => {
            const document = fullDocsByIndex.get(docIndex);
            return document
                && sitegraphDocumentMatchesFilters(document, filters, now)
                && documentMatchesFullScan(document, matchPhrases)
                ? rankSitegraphDocument(document, query, terms, scores.get(docIndex) || 0)
                : null;
        })
        .filter((item): item is RankedSitegraphDocument => Boolean(item));
};

const hydrateCandidatePhase = async (
    bundle: SitegraphIndexBundle,
    scores: Map<number, number>,
    query: string,
    terms: string[],
    signal: AbortSignal,
    loadedShardPaths: Set<string>,
    fullDocsByIndex: Map<number, SitegraphFullDocument>,
    candidateLimit: number,
    maxShardLoads: number,
    matchPhrases: string[],
    filters: SitegraphSearchFilters,
    now: number
): Promise<{ ranked: RankedSitegraphDocument[]; candidateCount: number }> => {
    const candidates = candidateShardPaths(bundle, scores, candidateLimit, maxShardLoads, filters, now);
    const pathsToLoad = candidates.paths.filter(path => !loadedShardPaths.has(path));
    await loadShardBatch(pathsToLoad, signal, loadedShardPaths, fullDocsByIndex);
    return {
        ranked: rankHydratedCandidates(candidates.indices, fullDocsByIndex, scores, query, terms, matchPhrases, filters, now),
        candidateCount: candidates.indices.length,
    };
};

const documentMatchesFullScan = (document: SitegraphFullDocument, matchPhrases: string[]): boolean => {
    const blob = fullScanBlob(document);
    return matchPhrases.some(term => blob.includes(term));
};

const filterTokenHashInt = (text: string, seed: number): number => {
    let value = (2166136261 ^ seed) >>> 0;
    const bytes = new TextEncoder().encode(text);
    for (const byte of bytes) {
        value ^= byte;
        value = Math.imul(value, 16777619) >>> 0;
    }
    return value;
};

const decodedFilterCache = new WeakMap<object, Uint8Array>();

const decodeBase64Bytes = (value: string): Uint8Array => {
    const binary = atob(value);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
        bytes[index] = binary.charCodeAt(index);
    }
    return bytes;
};

const decodedFilterBytes = (filter: NonNullable<SitegraphIndexBundle['shardFilter']>[string]): Uint8Array => {
    const cached = decodedFilterCache.get(filter);
    if (cached) return cached;
    const decoded = decodeBase64Bytes(filter.bitset_base64);
    decodedFilterCache.set(filter, decoded);
    return decoded;
};

const bloomMayContain = (filter: NonNullable<SitegraphIndexBundle['shardFilter']>[string], term: string): boolean => {
    const bytes = decodedFilterBytes(filter);
    for (let seed = 0; seed < filter.hash_count; seed += 1) {
        const bit = filterTokenHashInt(term, seed) % filter.bit_count;
        if (((bytes[Math.floor(bit / 8)] ?? 0) & (1 << (bit % 8))) === 0) {
            return false;
        }
    }
    return true;
};

const shardFilterProvesNoMatch = (
    shardId: string,
    shardFilter: NonNullable<SitegraphIndexBundle['shardFilter']>,
    terms: string[]
): boolean => {
    const filter = shardFilter[shardId];
    if (!filter || filter.hash_algorithm !== 'bloom-fnv1a32-utf8') return false;
    return terms.every(term => !bloomMayContain(filter, term));
};

export interface ProgressiveSearchOptions {
    limit?: number;
    candidateLimit?: number;
    maxShardLoads?: number;
    sortMode?: SitegraphSortMode;
    filters?: SitegraphSearchFilters;
    now?: number;
}

export const searchSitegraphProgressively = async (
    bundle: SitegraphIndexBundle,
    query: string,
    signal: AbortSignal,
    emit: (event: SitegraphSearchEvent) => void,
    options: ProgressiveSearchOptions = {}
): Promise<void> => {
    const trimmed = query.trim();
    const limit = options.limit ?? 60;
    const candidateLimit = options.candidateLimit ?? DEFAULT_CANDIDATE_LIMIT;
    const maxShardLoads = options.maxShardLoads ?? DEFAULT_MAX_SHARD_LOADS;
    const sortMode = options.sortMode ?? 'relevance';
    const filters = options.filters ?? {};
    const now = options.now ?? Date.now();
    const terms = tokenizeSitegraphQuery(trimmed, bundle.queryAliases);
    const normalizedQuery = normalize(trimmed);
    const matchPhrases = expandSitegraphQueryPhrases(trimmed, bundle.queryAliases);
    const scores = new Map<number, number>();
    const resultMap = new Map<string, RankedSitegraphDocument>();
    const loadedShardPaths = new Set<string>();
    const fullDocsByIndex = new Map<number, SitegraphFullDocument>();
    const telemetry: SearchTelemetry = {
        lightMetaFallbackDocIndices: new Set<number>(),
        fullScanMatchDocIndices: new Set<number>(),
    };
    let candidateCount = 0;
    let usedBodyIndex = false;
    const totalDocuments = bundle.manifest.total_documents;

    const emitResults = (
        type: SitegraphSearchPhase,
        coverage: SitegraphSearchCoverage,
        includeResults: boolean
    ) => {
        const stats = statsFor(type, coverage, loadedShardPaths, candidateCount, resultMap, telemetry);
        emit({
            type,
            query: trimmed,
            coverage,
            stats,
            ...(includeResults ? { results: rankedSnapshot(resultMap, stats, limit, sortMode) } : {}),
        });
    };

    const recordLightMetaFallback = () => {
        for (const docIndex of applyLightMetaFallback(bundle, scores, normalizedQuery, filters, now)) {
            telemetry.lightMetaFallbackDocIndices.add(docIndex);
        }
    };

    const startedCoverage = coverageFor(bundle, 'quick_started', [], 0, 0, 0, loadedShardPaths, false, false);
    emitResults('quick_started', startedCoverage, false);
    throwIfAborted(signal);

    if (trimmed.length < 2) {
        const completeCoverage = coverageFor(bundle, 'exhaustive_complete', FULL_SCAN_FIELDS, 0, 0, 0, loadedShardPaths, false, true);
        emitResults('exhaustive_complete', completeCoverage, true);
        return;
    }

    applyPostings(scores, bundle.lightInvertedIndex.tokens, terms);
    recordLightMetaFallback();
    const quick = await hydrateCandidatePhase(
        bundle,
        scores,
        trimmed,
        terms,
        signal,
        loadedShardPaths,
        fullDocsByIndex,
        Math.min(candidateLimit, 48),
        Math.min(maxShardLoads, QUICK_MAX_SHARD_LOADS),
        matchPhrases,
        filters,
        now
    );
    candidateCount = quick.candidateCount;
    mergeRankedResults(resultMap, quick.ranked);
    const quickCoverage = coverageFor(bundle, 'quick_results', LIGHT_SEARCH_FIELDS, 0, loadedShardPaths.size, totalDocuments, loadedShardPaths, false, false);
    emitResults('quick_results', quickCoverage, true);

    const bodyStartedCoverage = coverageFor(bundle, 'body_started', LIGHT_SEARCH_FIELDS, 0, loadedShardPaths.size, totalDocuments, loadedShardPaths, false, false);
    emitResults('body_started', bodyStartedCoverage, false);
    throwIfAborted(signal);
    const bodyIndex = await ensureBodyIndex(bundle, signal);
    throwIfAborted(signal);
    usedBodyIndex = true;
    applyPostings(scores, bodyIndex.tokens, terms);
    recordLightMetaFallback();
    const body = await hydrateCandidatePhase(
        bundle,
        scores,
        trimmed,
        terms,
        signal,
        loadedShardPaths,
        fullDocsByIndex,
        Math.min(candidateLimit, 96),
        Math.min(maxShardLoads, BODY_MAX_SHARD_LOADS),
        matchPhrases,
        filters,
        now
    );
    candidateCount = body.candidateCount;
    mergeRankedResults(resultMap, body.ranked);
    const bodyCoverage = coverageFor(bundle, 'body_results', BODY_SEARCH_FIELDS, 0, loadedShardPaths.size, totalDocuments, loadedShardPaths, usedBodyIndex, false);
    emitResults('body_results', bodyCoverage, true);

    const hydrateStartedCoverage = coverageFor(bundle, 'hydrate_started', BODY_SEARCH_FIELDS, 0, loadedShardPaths.size, fullDocsByIndex.size, loadedShardPaths, usedBodyIndex, false);
    emitResults('hydrate_started', hydrateStartedCoverage, false);
    const hydrate = await hydrateCandidatePhase(
        bundle,
        scores,
        trimmed,
        terms,
        signal,
        loadedShardPaths,
        fullDocsByIndex,
        candidateLimit,
        Math.min(maxShardLoads, HYDRATE_MAX_SHARD_LOADS),
        matchPhrases,
        filters,
        now
    );
    candidateCount = hydrate.candidateCount;
    mergeRankedResults(resultMap, hydrate.ranked);
    const hydrateCoverage = coverageFor(bundle, 'hydrate_results', FULL_SCAN_FIELDS, 0, loadedShardPaths.size, fullDocsByIndex.size, loadedShardPaths, usedBodyIndex, false);
    emitResults('hydrate_results', hydrateCoverage, true);

    const shardFilter = await ensureShardFilter(bundle, signal);
    let provedNoMatchShards = 0;
    let scannedShards = 0;
    let searchedDocuments = 0;
    const verifyStartedCoverage = coverageFor(bundle, 'verify_started', FULL_SCAN_FIELDS, 0, 0, 0, loadedShardPaths, usedBodyIndex, false);
    emitResults('verify_started', verifyStartedCoverage, false);

    for (let shardIndex = 0; shardIndex < bundle.manifest.sitegraph.full_shards.length; shardIndex += SHARD_BATCH_SIZE) {
        throwIfAborted(signal);
        const shardBatch = bundle.manifest.sitegraph.full_shards.slice(shardIndex, shardIndex + SHARD_BATCH_SIZE);
        const scanBatch = shardBatch.filter(shard => {
            const canSkip = shardFilterProvesNoMatch(shard.shard_id, shardFilter, terms);
            if (canSkip) provedNoMatchShards += 1;
            return !canSkip;
        });
        const shardResults = await Promise.all(scanBatch.map(shard => loadShard(shard.path, signal)));
        const verifyMatches: RankedSitegraphDocument[] = [];
        shardResults.forEach((documents, batchIndex) => {
            const shard = scanBatch[batchIndex];
            if (!shard) return;
            loadedShardPaths.add(shard.path);
            scannedShards += 1;
            for (const document of documents) {
                fullDocsByIndex.set(document.doc_index, document);
                searchedDocuments += 1;
                if (sitegraphDocumentMatchesFilters(document, filters, now) && documentMatchesFullScan(document, matchPhrases)) {
                    telemetry.fullScanMatchDocIndices.add(document.doc_index);
                    const baseScore = scores.get(document.doc_index) ?? 24;
                    verifyMatches.push(rankSitegraphDocument(document, trimmed, terms, baseScore));
                }
            }
        });

        const progressCoverage = coverageFor(bundle, 'verify_progress', FULL_SCAN_FIELDS, provedNoMatchShards, scannedShards, searchedDocuments, loadedShardPaths, usedBodyIndex, false);
        if (mergeRankedResults(resultMap, verifyMatches) > 0) {
            const resultsCoverage = coverageFor(bundle, 'verify_results', FULL_SCAN_FIELDS, provedNoMatchShards, scannedShards, searchedDocuments, loadedShardPaths, usedBodyIndex, false);
            emitResults('verify_results', resultsCoverage, true);
        }
        emitResults('verify_progress', progressCoverage, false);
        await yieldToWorker();
    }

    const completeCoverage = coverageFor(bundle, 'exhaustive_complete', FULL_SCAN_FIELDS, provedNoMatchShards, scannedShards, searchedDocuments, loadedShardPaths, usedBodyIndex, true);
    emitResults('exhaustive_complete', completeCoverage, true);
};

export const recallSitegraphDocuments = async (
    bundle: SitegraphIndexBundle,
    query: string,
    signal: AbortSignal,
    limit = 30
): Promise<{ results: RankedSitegraphDocument[]; stats: SitegraphQueryStats }> => {
    const resultEvents: SitegraphSearchEvent[] = [];
    await searchSitegraphProgressively(bundle, query, signal, event => {
        if (event.results) resultEvents.push(event);
    }, { limit });
    const finalEvent = resultEvents[resultEvents.length - 1];
    if (!finalEvent?.stats) {
        throw new SearchContractError('Progressive search completed without a result event');
    }
    return {
        results: finalEvent.results || [],
        stats: finalEvent.stats,
    };
};
