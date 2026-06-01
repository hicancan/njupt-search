import { APP_CONFIG } from '@/app/config/constants';
import {
    SitegraphRoutedSession,
    SitegraphSearchFilters,
    SitegraphSearchCoverage,
    SitegraphSearchManifest,
    SitegraphSortMode,
} from '@/shared/lib/contracts';
import { fetchJson } from '@/shared/lib/fetch';
import {
    createBrowserContentHashArtifactCache,
    fetchJsonArtifact,
    parseSitegraphGlobalQueryDirectory,
    parseSitegraphManifest,
    parseSitegraphSourceRegistry,
    searchSitegraphProgressively,
} from '@njupt-search/search-core';
import type {
    ArtifactContentCache,
    PackedImpactRetrievalMetrics,
    PackedImpactRetrievalResult,
    PackedImpactRetriever,
} from '@njupt-search/search-core';
import initPackedImpactDecoder, {
    PackedImpactRetrievalSession as WasmPackedImpactRetrievalSession,
    retrieve_packed_impact_topk_scores,
} from '../wasm/packed_impact_decoder.js';
import packedImpactDecoderUrl from '../wasm/packed_impact_decoder_bg.wasm?url';

type InitMessage = { type: 'init'; requestId: number };
type QueryMessage = {
    type: 'query';
    requestId: number;
    query: string;
    limit?: number;
    sortMode?: SitegraphSortMode;
    filters?: SitegraphSearchFilters;
};
type CancelMessage = { type: 'cancel'; requestId: number };
type IncomingMessage = InitMessage | QueryMessage | CancelMessage;

let manifest: SitegraphSearchManifest | null = null;
type CachedRoutedSession = SitegraphRoutedSession & {
    artifactCache?: ArtifactContentCache;
    packedImpactRetriever?: PackedImpactRetriever;
};

let session: CachedRoutedSession | null = null;
let activeController: AbortController | null = null;
let activeRequestId: number | null = null;
let lastCoverage: SitegraphSearchCoverage | null = null;
const artifactCache = createBrowserContentHashArtifactCache('njupt-public');
let packedImpactDecoderReady: Promise<unknown> | null = null;

const post = (payload: Record<string, unknown>) => {
    self.postMessage(payload);
};

const publicPath = (path: string): string => {
    if (/^https?:\/\//.test(path) || path.startsWith('/')) return path;
    return `/${path}`;
};

const ensurePackedImpactDecoder = (): Promise<unknown> => {
    packedImpactDecoderReady ??= initPackedImpactDecoder(packedImpactDecoderUrl);
    return packedImpactDecoderReady;
};

const numeric = (value: unknown): number => typeof value === 'number' && Number.isFinite(value) ? value : 0;

const parseScoreEntries = (value: unknown): Array<readonly [number, number]> => {
    if (!Array.isArray(value)) return [];
    const entries: Array<readonly [number, number]> = [];
    for (const item of value) {
        if (!Array.isArray(item)) continue;
        const docIndex = numeric(item[0]);
        const score = numeric(item[1]);
        if (Number.isInteger(docIndex) && score > 0) entries.push([docIndex, score]);
    }
    return entries;
};

const parsePackedImpactMetrics = (payload: unknown): PackedImpactRetrievalMetrics => {
    const record = payload && typeof payload === 'object' ? payload as Record<string, unknown> : {};
    return {
        matchedTermCount: numeric(record.matched_term_count),
        blockCount: numeric(record.block_count),
        candidateCount: numeric(record.candidate_count),
        impactBlocksVisited: numeric(record.impact_blocks_visited),
        impactBlocksPruned: numeric(record.impact_blocks_pruned),
        postingsVisited: numeric(record.postings_visited),
        postingsPruned: numeric(record.postings_pruned),
        competitiveThreshold: numeric(record.competitive_threshold),
    };
};

const parsePackedImpactRetrieval = (payload: unknown): PackedImpactRetrievalResult => {
    const record = payload && typeof payload === 'object' ? payload as Record<string, unknown> : {};
    return {
        ...parsePackedImpactMetrics(record),
        scoreEntries: parseScoreEntries(record.score_entries),
    };
};

const packedImpactRetriever: PackedImpactRetriever = {
    engine: 'rust_wasm_packed_impact',
    async createSession(targetCandidates) {
        await ensurePackedImpactDecoder();
        const wasmSession = new WasmPackedImpactRetrievalSession(targetCandidates);
        return {
            async applyPackedImpactScores(input) {
                const payload = wasmSession.apply(
                    new Uint8Array(input.bytes),
                    JSON.stringify(input.terms),
                );
                return parsePackedImpactMetrics(JSON.parse(payload) as unknown);
            },
            async readScoreEntries() {
                const payload = JSON.parse(wasmSession.scores_json()) as unknown;
                const record = payload && typeof payload === 'object' ? payload as Record<string, unknown> : {};
                return parseScoreEntries(record.score_entries);
            },
        };
    },
    async retrievePackedImpactScores(input) {
        await ensurePackedImpactDecoder();
        const payload = retrieve_packed_impact_topk_scores(
            new Uint8Array(input.bytes),
            JSON.stringify(input.terms),
            input.targetCandidates,
        );
        return parsePackedImpactRetrieval(JSON.parse(payload) as unknown);
    },
};

const init = async (requestId: number) => {
    activeController?.abort();
    const controller = new AbortController();
    activeController = controller;
    activeRequestId = requestId;
    const manifestPath = publicPath(APP_CONFIG.DATA_URLS.SEARCH_MANIFEST);
    const manifestPayload = await fetchJson(manifestPath, controller.signal, 'manifest');
    manifest = parseSitegraphManifest(manifestPayload, manifestPath);
    const artifacts = manifest.artifacts;
    const [sourceRegistryPayload, queryDirectoryPayload, aliasesPayload] = await Promise.all([
        fetchJsonArtifact(publicPath(artifacts.source_registry.path), controller.signal, 'index', artifactCache),
        fetchJsonArtifact(publicPath(artifacts.global_query_directory.path), controller.signal, 'index', artifactCache),
        fetchJsonArtifact(publicPath(artifacts.query_aliases.path), controller.signal, 'index', artifactCache),
    ]);
    const sourceRegistry = parseSitegraphSourceRegistry(sourceRegistryPayload.value, artifacts.source_registry.path);
    session = {
        manifest,
        sourceRegistry,
        globalQueryDirectory: parseSitegraphGlobalQueryDirectory(queryDirectoryPayload.value, artifacts.global_query_directory.path),
        queryAliases: aliasesPayload.value as Record<string, unknown>,
        artifactCache,
        packedImpactRetriever,
    };
    post({
        type: 'ready',
        requestId,
        manifest,
        filterOptions: sourceRegistry.filter_options,
        firstScreenBytes: artifacts.source_registry.bytes + artifacts.global_query_directory.bytes + artifacts.query_aliases.bytes,
        bootstrapCache: {
            scope: artifactCache.scope,
            artifact_hits: [sourceRegistryPayload, queryDirectoryPayload, aliasesPayload].filter(item => item.cacheHit).length,
            artifact_misses: [sourceRegistryPayload, queryDirectoryPayload, aliasesPayload].filter(item => !item.cacheHit).length,
            cached_bytes: [sourceRegistryPayload, queryDirectoryPayload, aliasesPayload]
                .filter(item => item.cacheHit)
                .reduce((sum, item) => sum + item.byteLength, 0),
            uncached_bytes: [sourceRegistryPayload, queryDirectoryPayload, aliasesPayload]
                .filter(item => !item.cacheHit)
                .reduce((sum, item) => sum + item.byteLength, 0),
        },
    });
};

const query = async (
    requestId: number,
    queryText: string,
    limit = 30,
    sortMode: SitegraphSortMode = 'relevance',
    filters: SitegraphSearchFilters = {}
) => {
    if (!session) {
        throw new Error('Search worker is not initialized');
    }
    activeController?.abort();
    const controller = new AbortController();
    activeController = controller;
    activeRequestId = requestId;
    await searchSitegraphProgressively(session, queryText, controller.signal, event => {
        lastCoverage = event.coverage;
        post({ ...event, requestId });
    }, { limit, sortMode, filters });
};

self.onmessage = (event: MessageEvent<IncomingMessage>) => {
    const message = event.data;
    if (message.type === 'cancel') {
        if (message.requestId === activeRequestId) {
            activeController?.abort();
            activeController = null;
            activeRequestId = null;
        }
        post({
            type: 'cancelled',
            requestId: message.requestId,
            coverage: lastCoverage ? { ...lastCoverage, phase: 'cancelled', coverage_state: 'cancelled', exhaustive_complete: false } : null,
        });
        return;
    }

    const run = message.type === 'init'
        ? init(message.requestId)
        : query(message.requestId, message.query, message.limit, message.sortMode, message.filters);

    run.catch(error => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        post({
            type: 'error',
            requestId: message.requestId,
            message: error instanceof Error ? error.message : String(error),
            coverage: lastCoverage ? { ...lastCoverage, phase: 'error', coverage_state: 'error', exhaustive_complete: false } : null,
        });
    });
};
