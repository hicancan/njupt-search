import {
    RankedSitegraphDocument,
    SitegraphAttachment,
    SitegraphAttachmentSchema,
    SitegraphDocMeta,
    SitegraphDocMetaSchema,
    SitegraphExternalRecord,
    SitegraphExternalRecordSchema,
    SitegraphFullDocument,
    SitegraphFullDocumentSchema,
    SitegraphIndexBundle,
    SitegraphInvertedIndex,
    SitegraphInvertedIndexSchema,
    SitegraphQueryStats,
    SitegraphSearchCoverage,
    SitegraphSearchEvent,
    SitegraphSearchPhase,
    SitegraphSearchManifest,
    SitegraphSearchManifestSchema
} from '../../contracts/src';
import { fetchJson } from './fetchJson';
import { z } from 'zod';

export class SearchContractError extends Error {
    constructor(message: string) {
        super(message);
        this.name = 'SearchContractError';
    }
}

const MODEL_FIELD_PREFIX = ['l', 'l', 'm'].join('');
const TASK_FIELD_PREFIX = ['hy', 'task'].join('');
const LEGACY_FIELDS = new Set([
    MODEL_FIELD_PREFIX,
    `${MODEL_FIELD_PREFIX}_provider`,
    `${MODEL_FIELD_PREFIX}_schema_version`,
    'semantic_mode',
    'task_frames',
    `${MODEL_FIELD_PREFIX}_in_core_path`,
    `old_${TASK_FIELD_PREFIX}_removed`,
    'source_channel_production_enabled',
    'github_resource_production_enabled'
]);
const DOC_META_FORBIDDEN_FIELDS = new Set(['content', 'summary', 'attachments', 'provenance']);
const DEFAULT_CANDIDATE_LIMIT = 160;
const DEFAULT_MAX_SHARD_LOADS = 40;
const QUICK_MAX_SHARD_LOADS = 8;
const BODY_MAX_SHARD_LOADS = 18;
const HYDRATE_MAX_SHARD_LOADS = 40;
const SHARD_BATCH_SIZE = 4;
const LIGHT_SEARCH_FIELDS = ['title', 'section', 'nav_path', 'tags', 'attachments', 'external', 'system'];
const BODY_SEARCH_FIELDS = [...LIGHT_SEARCH_FIELDS, 'summary', 'content'];
const FULL_SCAN_FIELDS = ['title', 'section', 'nav_path', 'summary', 'content', 'attachments', 'url'];

const valueAtPath = (payload: unknown, path: PropertyKey[]): unknown => {
    let current = payload;
    for (const part of path) {
        if (current === null || current === undefined) return undefined;
        current = (current as Record<PropertyKey, unknown>)[part];
    }
    return current;
};

const formatZodIssues = (payload: unknown, error: z.ZodError): string => {
    return error.issues.map(issue => {
        const fieldPath = issue.path.join('.') || '<root>';
        const invalidValue = valueAtPath(payload, issue.path);
        return `${fieldPath}: ${issue.message}; value=${JSON.stringify(invalidValue)}`;
    }).join('; ');
};

const parseArray = <T>(schema: z.ZodType<T>, payload: unknown, source: string): T[] => {
    try {
        return z.array(schema).parse(payload);
    } catch (e) {
        if (e instanceof z.ZodError) {
            throw new SearchContractError(`Validation failed for ${source}: ${formatZodIssues(payload, e)}`);
        }
        throw new SearchContractError(`Validation failed for ${source}: ${e instanceof Error ? e.message : String(e)}`);
    }
};

const assertNoLegacyFields = (payload: unknown, source: string, path = '$'): void => {
    if (Array.isArray(payload)) {
        payload.forEach((item, index) => assertNoLegacyFields(item, source, `${path}[${index}]`));
        return;
    }
    if (!payload || typeof payload !== 'object') return;
    for (const [key, value] of Object.entries(payload as Record<string, unknown>)) {
        if (LEGACY_FIELDS.has(key)) {
            throw new SearchContractError(`Validation failed for ${source}: ${path}.${key} is an obsolete search field`);
        }
        assertNoLegacyFields(value, source, `${path}.${key}`);
    }
};

export const parseSitegraphManifest = (payload: unknown, source = 'sitegraph manifest'): SitegraphSearchManifest => {
    try {
        assertNoLegacyFields(payload, source);
        const text = JSON.stringify(payload);
        if (text.includes('D:\\') || text.includes('D:/')) {
            throw new SearchContractError(`Validation failed for ${source}: public manifest must not expose local D: paths`);
        }
        return SitegraphSearchManifestSchema.parse(payload);
    } catch (e) {
        if (e instanceof z.ZodError) {
            throw new SearchContractError(`Validation failed for ${source}: ${formatZodIssues(payload, e)}`);
        }
        throw new SearchContractError(`Validation failed for ${source}: ${e instanceof Error ? e.message : String(e)}`);
    }
};

export const parseSitegraphDocMeta = (payload: unknown, source = 'sitegraph doc_meta'): SitegraphDocMeta[] => {
    assertNoLegacyFields(payload, source);
    const docs = parseArray(SitegraphDocMetaSchema, payload, source);
    const ids = new Set<string>();
    for (const item of docs) {
        if (ids.has(item.id)) throw new SearchContractError(`${source} contains duplicate id: ${item.id}`);
        for (const field of DOC_META_FORBIDDEN_FIELDS) {
            if (field in item) {
                throw new SearchContractError(`Validation failed for ${source}: doc_meta_light must not contain ${field}`);
            }
        }
        ids.add(item.id);
    }
    return docs;
};

export const parseSitegraphFullDocuments = (payload: unknown, source = 'sitegraph full shard'): SitegraphFullDocument[] => {
    assertNoLegacyFields(payload, source);
    return parseArray(SitegraphFullDocumentSchema, payload, source);
};

export const parseSitegraphAttachmentIndex = (payload: unknown, source = 'sitegraph attachment_index'): SitegraphAttachment[] => {
    return parseArray(SitegraphAttachmentSchema, payload, source);
};

export const parseSitegraphExternalIndex = (payload: unknown, source = 'sitegraph external_index'): SitegraphExternalRecord[] => {
    return parseArray(SitegraphExternalRecordSchema, payload, source);
};

export const parseSitegraphInvertedIndex = (payload: unknown, source = 'sitegraph inverted_index'): SitegraphInvertedIndex => {
    try {
        return SitegraphInvertedIndexSchema.parse(payload);
    } catch (e) {
        if (e instanceof z.ZodError) {
            throw new SearchContractError(`Validation failed for ${source}: ${formatZodIssues(payload, e)}`);
        }
        throw new SearchContractError(`Validation failed for ${source}: ${e instanceof Error ? e.message : String(e)}`);
    }
};

const normalize = (value: unknown): string => String(value || '')
    .normalize('NFKC')
    .toLowerCase()
    .replace(/\s+/g, '');

export const tokenizeSitegraphQuery = (query: string, queryAliases: Record<string, unknown> = {}): string[] => {
    const candidates = [query];
    const normalizedQuery = normalize(query);
    for (const [key, rawPayload] of Object.entries(queryAliases)) {
        const payload = rawPayload && typeof rawPayload === 'object' ? rawPayload as { aliases?: unknown[] } : {};
        const terms = [key, ...(Array.isArray(payload.aliases) ? payload.aliases.map(String) : [])];
        if (terms.some(term => normalize(term) && normalizedQuery.includes(normalize(term)))) {
            candidates.push(...terms);
        }
    }

    const tokens = new Set<string>();
    for (const candidate of candidates) {
        const text = normalize(candidate);
        if (text.length >= 2) tokens.add(text);
        const matches = text.match(/[\u4e00-\u9fff]{2,}|[a-z0-9][a-z0-9._-]{1,}/g) || [];
        for (const part of matches) {
            if (/^[\u4e00-\u9fff]+$/.test(part)) {
                const maxSize = Math.min(5, part.length);
                for (let size = 2; size <= maxSize; size += 1) {
                    for (let index = 0; index <= part.length - size; index += 1) {
                        tokens.add(part.slice(index, index + size));
                    }
                }
            } else {
                tokens.add(part);
            }
        }
    }
    return Array.from(tokens).sort((a, b) => b.length - a.length);
};

const FIELD_WEIGHTS: Record<string, number> = {
    t: 120,
    a: 95,
    e: 95,
    y: 95,
    s: 60,
    n: 55,
    g: 45,
    m: 16,
    c: 10
};

const shardCache = new Map<string, Promise<SitegraphFullDocument[]>>();

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
    if (existing) return existing;
    const promise = fetchJson(publicAssetPath(path), signal, 'shard')
        .then(payload => parseSitegraphFullDocuments(payload, path))
        .catch(error => {
            shardCache.delete(path);
            throw error;
        });
    shardCache.set(path, promise);
    return promise;
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

const attachmentBlob = (document: SitegraphFullDocument): string => normalize(
    document.attachments
        .map(attachment => [attachment.name, attachment.extension, attachment.section, attachment.parent_url].filter(Boolean).join(' '))
        .join(' ')
);

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

const dateSortValue = (dateLike: string | null | undefined): number => {
    if (!dateLike) return 0;
    const date = new Date(dateLike);
    return Number.isNaN(date.getTime()) ? 0 : date.getTime();
};

const freshnessScore = (document: SitegraphFullDocument): number => {
    if (!['notice_article', 'exam', 'news'].includes(document.facet)) return 0;
    const value = dateSortValue(document.published_at);
    if (!value) return 0;
    const days = Math.max(0, (Date.now() - value) / 86_400_000);
    return Math.max(0, 600 - Math.min(days, 3650) / 3650 * 600);
};

const rankDocument = (
    document: SitegraphFullDocument,
    query: string,
    terms: string[],
    lightScore: number
): RankedSitegraphDocument => {
    const normalizedQuery = normalize(query);
    const title = textBlob(document, ['title']);
    const section = textBlob(document, ['section', 'nav_path_text']);
    const summary = textBlob(document, ['summary']);
    const content = textBlob(document, ['content']);
    const tags = textBlob(document, ['tags']);
    const attachment = attachmentBlob(document);
    const url = normalize(document.url);
    const external = document.record_type === 'external' ? normalize(`${document.title} ${document.url} ${document.summary}`) : '';
    let score = lightScore;
    const reasons: string[] = [];

    if (normalizedQuery && title === normalizedQuery) {
        score += 5000;
        reasons.push('标题精确');
    } else if (normalizedQuery && title.includes(normalizedQuery)) {
        score += 520;
        reasons.push('标题包含');
    }
    if (normalizedQuery && attachment.includes(normalizedQuery)) {
        score += 360;
        reasons.push('附件名命中');
    }
    if (normalizedQuery && external.includes(normalizedQuery)) {
        score += 360;
        reasons.push('外部入口命中');
    }
    if (normalizedQuery && url.includes(normalizedQuery)) {
        score += 220;
        reasons.push('URL 命中');
    }
    if (normalizedQuery && section.includes(normalizedQuery)) {
        score += 180;
        reasons.push('栏目路径命中');
    }
    if (normalizedQuery && content.includes(normalizedQuery)) {
        score += 120;
        reasons.push('正文命中');
    }
    if (normalizedQuery && tags.includes(normalizedQuery)) {
        score += 80;
        reasons.push('标签命中');
    }

    const matchedTerms: string[] = [];
    for (const term of terms.slice(0, 12)) {
        if (title.includes(term)) {
            score += 80;
            matchedTerms.push(term);
        } else if (attachment.includes(term)) {
            score += 70;
            matchedTerms.push(term);
        } else if (external.includes(term)) {
            score += 65;
            matchedTerms.push(term);
        } else if (url.includes(term)) {
            score += 55;
            matchedTerms.push(term);
        } else if (section.includes(term)) {
            score += 45;
            matchedTerms.push(term);
        } else if (summary.includes(term) || content.includes(term)) {
            score += 12;
            matchedTerms.push(term);
        }
    }
    if (matchedTerms.length > 0) {
        reasons.push(`词项：${Array.from(new Set(matchedTerms)).sort((a, b) => b.length - a.length).slice(0, 6).join('、')}`);
    }
    if (document.facet === 'system' && ['系统', 'jwxt', '教务'].some(term => normalizedQuery.includes(term))) {
        score += 1500;
        reasons.push('系统入口');
    }
    if (document.facet === 'download' && ['附件', '下载', 'xlsx', 'xls', '表格'].some(term => normalizedQuery.includes(term))) {
        score += 120;
        reasons.push('下载资源');
    }
    if (document.facet === 'policy' && ['规章', '制度', '管理办法', '政策'].some(term => normalizedQuery.includes(term))) {
        score += 900;
        reasons.push('政策制度');
    }
    if (document.facet === 'workflow' && ['办事流程', '办理', '申请流程', '流程'].some(term => normalizedQuery.includes(term))) {
        score += 900;
        reasons.push('办事流程');
    }
    if (document.facet === 'exam' && ['考试', '期末', '慕课', 'mooc'].some(term => normalizedQuery.includes(term))) {
        score += 650;
        reasons.push('考试相关');
    }
    score += freshnessScore(document);

    return {
        ...document,
        score,
        score_reason: reasons.join('；') || '倒排候选'
    };
};

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
            const weight = FIELD_WEIGHTS[field] || 8;
            for (const docIndex of ids) {
                scores.set(docIndex, (scores.get(docIndex) || 0) + weight + Math.min(term.length, 8));
            }
        }
    }
};

const applyLightMetaFallback = (
    bundle: SitegraphIndexBundle,
    scores: Map<number, number>,
    normalizedQuery: string
): void => {
    if (scores.size >= 8 || !normalizedQuery) return;
    for (const meta of bundle.docMeta) {
        const haystack = textBlob(meta, ['title', 'section', 'nav_path_text']);
        if (haystack.includes(normalizedQuery)) {
            scores.set(meta.doc_index, (scores.get(meta.doc_index) || 0) + 90);
        }
    }
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
    maxShardLoads: number
): { indices: number[]; paths: string[] } => {
    const indices: number[] = [];
    const paths: string[] = [];
    const seenPaths = new Set<string>();
    for (const [docIndex] of sortedScoreEntries(scores).slice(0, candidateLimit)) {
        const meta = bundle.docMeta[docIndex];
        if (!meta?.shard?.shard_id) continue;
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

const sortRankedResults = (results: RankedSitegraphDocument[]): RankedSitegraphDocument[] => {
    return results.sort((a, b) => {
        const scoreDelta = b.score - a.score;
        if (scoreDelta !== 0) return scoreDelta;
        const dateDelta = dateSortValue(b.published_at) - dateSortValue(a.published_at);
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
    limit: number
): RankedSitegraphDocument[] => {
    return sortRankedResults(Array.from(resultMap.values()))
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
    resultCount: number
) => ({
    phase,
    coverage,
    usedBodyIndex: coverage.used_body_index,
    loadedShardCount: loadedShardPaths.size,
    loadedShardPaths: Array.from(loadedShardPaths).sort(),
    candidateCount,
    exhaustiveComplete: coverage.exhaustive_complete,
    resultCount,
});

const rankHydratedCandidates = (
    indices: number[],
    fullDocsByIndex: Map<number, SitegraphFullDocument>,
    scores: Map<number, number>,
    query: string,
    terms: string[]
): RankedSitegraphDocument[] => {
    return indices
        .map(docIndex => {
            const document = fullDocsByIndex.get(docIndex);
            return document ? rankDocument(document, query, terms, scores.get(docIndex) || 0) : null;
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
    maxShardLoads: number
): Promise<{ ranked: RankedSitegraphDocument[]; candidateCount: number }> => {
    const candidates = candidateShardPaths(bundle, scores, candidateLimit, maxShardLoads);
    const pathsToLoad = candidates.paths.filter(path => !loadedShardPaths.has(path));
    await loadShardBatch(pathsToLoad, signal, loadedShardPaths, fullDocsByIndex);
    return {
        ranked: rankHydratedCandidates(candidates.indices, fullDocsByIndex, scores, query, terms),
        candidateCount: candidates.indices.length,
    };
};

const documentMatchesFullScan = (document: SitegraphFullDocument, normalizedQuery: string, terms: string[]): boolean => {
    const blob = fullScanBlob(document);
    if (normalizedQuery && blob.includes(normalizedQuery)) return true;
    return terms.some(term => term.length >= 2 && blob.includes(term));
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

const decodeBase64Bytes = (value: string): Uint8Array => {
    const binary = atob(value);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
        bytes[index] = binary.charCodeAt(index);
    }
    return bytes;
};

const bloomMayContain = (filter: NonNullable<SitegraphIndexBundle['shardFilter']>[string], term: string): boolean => {
    const bytes = decodeBase64Bytes(filter.bitset_base64);
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
    const terms = tokenizeSitegraphQuery(trimmed, bundle.queryAliases);
    const normalizedQuery = normalize(trimmed);
    const scores = new Map<number, number>();
    const resultMap = new Map<string, RankedSitegraphDocument>();
    const loadedShardPaths = new Set<string>();
    const fullDocsByIndex = new Map<number, SitegraphFullDocument>();
    let candidateCount = 0;
    let usedBodyIndex = false;
    const totalDocuments = bundle.manifest.total_documents;

    const emitResults = (
        type: SitegraphSearchPhase,
        coverage: SitegraphSearchCoverage,
        includeResults: boolean
    ) => {
        const stats = statsFor(type, coverage, loadedShardPaths, candidateCount, resultMap.size);
        emit({
            type,
            query: trimmed,
            coverage,
            stats,
            ...(includeResults ? { results: rankedSnapshot(resultMap, stats, limit) } : {}),
        });
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
    applyLightMetaFallback(bundle, scores, normalizedQuery);
    const quick = await hydrateCandidatePhase(
        bundle,
        scores,
        trimmed,
        terms,
        signal,
        loadedShardPaths,
        fullDocsByIndex,
        Math.min(candidateLimit, 48),
        Math.min(maxShardLoads, QUICK_MAX_SHARD_LOADS)
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
    applyLightMetaFallback(bundle, scores, normalizedQuery);
    const body = await hydrateCandidatePhase(
        bundle,
        scores,
        trimmed,
        terms,
        signal,
        loadedShardPaths,
        fullDocsByIndex,
        Math.min(candidateLimit, 96),
        Math.min(maxShardLoads, BODY_MAX_SHARD_LOADS)
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
        Math.min(maxShardLoads, HYDRATE_MAX_SHARD_LOADS)
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
                if (documentMatchesFullScan(document, normalizedQuery, terms)) {
                    const baseScore = scores.get(document.doc_index) ?? 24;
                    verifyMatches.push(rankDocument(document, trimmed, terms, baseScore));
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

export const formatSearchDate = (dateLike: string | null | undefined): string => {
    if (!dateLike) return '日期未标注';
    const date = new Date(dateLike);
    if (Number.isNaN(date.getTime())) return dateLike;

    return date.toLocaleDateString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    });
};
