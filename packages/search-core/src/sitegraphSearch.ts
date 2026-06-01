import {
    QueryDirectoryRoute,
    RankedSitegraphDocument,
    SitegraphArtifact,
    SitegraphArtifactCacheStats,
    SitegraphDocMeta,
    SitegraphFullDocument,
    SitegraphFullShard,
    SitegraphImpactIndex,
    SitegraphLocalBodyIndex,
    SitegraphLocalIndexRef,
    SitegraphLocalShardRef,
    SitegraphLocalLightIndex,
    SitegraphProofCatalog,
    SitegraphProofCatalogShard,
    SitegraphProofLedgerEntry,
    SitegraphProofLedgerState,
    SitegraphProofLedgerSummary,
    SitegraphQueryPlan,
    SitegraphQueryStats,
    SitegraphRoutedSession,
    SitegraphSearchCoverage,
    SitegraphSearchEvent,
    SitegraphSearchFilters,
    SitegraphSearchPhase,
    SitegraphSortMode,
    SitegraphSourceManifest,
    SourceRegistryEntry
} from '@njupt-search/contracts';
import {
    ArtifactContentCache,
    ArtifactCacheScope,
    fetchArrayBufferArtifact,
    fetchJsonArtifact
} from './fetchJson';
import {
    parseSitegraphFullDocuments,
    parseSitegraphLocalBodyIndex,
    parseSitegraphLocalLightIndex,
    parseSitegraphProofCatalog,
    parseSitegraphSourceManifest,
    SearchContractError
} from './sitegraphContract';
import { decodePackedImpactIndexTerms, decodePackedLocalBodyIndexTerms } from './sitegraphBinaryIndex';
import { sitegraphDocumentMatchesFilters } from './sitegraphFilters';
import { rankingDateSortValue, rankSitegraphDocument, SITEGRAPH_FIELD_WEIGHTS } from './ranking/rankDocument';
import { detectQueryIntent } from './intent/queryIntent';
import { expandSitegraphQueryPhrases, normalizeSearchText as normalize, tokenizeSitegraphQuery } from './tokenizer';

const DEFAULT_CANDIDATE_LIMIT = 160;
const DEFAULT_MAX_SHARD_LOADS = 40;
const QUICK_MAX_SHARD_LOADS = 8;
const BODY_MAX_SHARD_LOADS = 18;
const HYDRATE_MAX_SHARD_LOADS = 18;
const SHARD_BATCH_SIZE = 4;
const ONE_MIB = 1024 * 1024;
const FIRST_TRUSTED_MAX_UNCACHED_BYTES = 5 * ONE_MIB;
const FIRST_TRUSTED_HYDRATION_RESERVE_BYTES = Math.floor(1.5 * ONE_MIB);
const TOP_RESULTS_MAX_UNCACHED_BYTES = 10 * ONE_MIB;
const TOP_RESULTS_HYDRATION_RESERVE_BYTES = Math.floor(2.25 * ONE_MIB);
const MIN_FIRST_TRUSTED_LOCAL_INDEXES = 6;
const MIN_TOP_RESULTS_LOCAL_INDEXES = 12;
const LIGHT_SEARCH_FIELDS = ['title', 'section', 'nav_path', 'tags', 'attachments', 'external', 'system'];
const BODY_SEARCH_FIELDS = [...LIGHT_SEARCH_FIELDS, 'summary', 'content'];
const FULL_SCAN_FIELDS = ['title', 'section', 'nav_path', 'summary', 'content', 'attachments', 'url'];

type RoutedSessionWithArtifactCache = SitegraphRoutedSession & {
    artifactCache?: ArtifactContentCache;
    packedImpactRetriever?: PackedImpactRetriever;
};

export interface PackedImpactRetrievalInput {
    bytes: ArrayBuffer;
    terms: string[];
    targetCandidates: number;
    source: string;
}

export interface PackedImpactRetrievalResult {
    scoreEntries: Array<readonly [number, number]>;
    matchedTermCount: number;
    blockCount: number;
    candidateCount: number;
    impactBlocksVisited: number;
    impactBlocksPruned: number;
    postingsVisited: number;
    postingsPruned: number;
    competitiveThreshold: number;
}

export type PackedImpactRetrievalMetrics = Omit<PackedImpactRetrievalResult, 'scoreEntries'>;

export interface PackedImpactRetrievalSession {
    applyPackedImpactScores(input: PackedImpactRetrievalInput): Promise<PackedImpactRetrievalMetrics>;
    readScoreEntries(): Promise<Array<readonly [number, number]>>;
}

export interface PackedImpactRetriever {
    engine: 'rust_wasm_packed_impact' | string;
    createSession?(targetCandidates: number): Promise<PackedImpactRetrievalSession>;
    retrievePackedImpactScores(input: PackedImpactRetrievalInput): Promise<PackedImpactRetrievalResult>;
}

type ShardFilterMap = Record<string, {
    bitset_base64: string;
    bit_count: number;
    hash_count: number;
    token_count: number;
    sha256: string;
    hash_algorithm: string;
}>;

interface LoadedPlanningScope {
    sourceManifests: SitegraphSourceManifest[];
    localRefs: SitegraphLocalIndexRef[];
    sourceManifestBytes: number;
    shardPathById: Map<string, string>;
    shardBytesByPath: Map<string, number>;
    selectedLocalIndexes: NonNullable<SitegraphQueryPlan['selected_local_indexes']>;
}

interface VerificationShard {
    shard_id: string;
    source_id: string;
    path: string;
    sha256: string;
    bytes: number;
    count: number;
    facet_range: string[];
    record_type_range: string[];
    section_range: string[];
    year_range: string[];
    hash_bucket: string;
    filter_token_count?: number;
    filter_sha256?: string;
}

interface SearchTelemetry {
    localMetaFallbackDocIndices: Set<number>;
    fullScanMatchDocIndices: Set<number>;
    retrieval: {
        dynamicPruning: boolean;
        engine: 'typescript_impact_index' | 'rust_wasm_packed_impact' | 'mixed';
        impactBlocksVisited: number;
        impactBlocksPruned: number;
        postingsVisited: number;
        postingsPruned: number;
        competitiveThreshold: number;
        wasmCalls: number;
        typescriptCalls: number;
        scoreEntriesReturned: number;
    };
}

interface LoadedLocalLightRuntimeIndex {
    documents: SitegraphDocMeta[];
    index?: SitegraphLocalLightIndex;
    packedBytes?: ArrayBuffer;
    packedPath?: string;
}

interface LoadedLocalBodyRuntimeIndex {
    index?: SitegraphLocalBodyIndex;
    packedBytes?: ArrayBuffer;
    packedPath?: string;
}

const sourceManifestCache = new Map<string, SitegraphSourceManifest>();
const localLightIndexCache = new Map<string, SitegraphLocalLightIndex>();
const localLightMetaCache = new Map<string, Omit<SitegraphLocalLightIndex, 'terms'>>();
const localLightPackedBytesCache = new Map<string, ArrayBuffer>();
const localBodyIndexCache = new Map<string, SitegraphLocalBodyIndex>();
const localBodyPackedBytesCache = new Map<string, ArrayBuffer>();
const proofCatalogCache = new Map<string, SitegraphProofCatalog>();
const shardFilterCache = new Map<string, ShardFilterMap>();
const shardCache = new Map<string, SitegraphFullDocument[]>();

export const clearSitegraphRuntimeCaches = (): void => {
    sourceManifestCache.clear();
    localLightIndexCache.clear();
    localLightMetaCache.clear();
    localLightPackedBytesCache.clear();
    localBodyIndexCache.clear();
    localBodyPackedBytesCache.clear();
    proofCatalogCache.clear();
    shardFilterCache.clear();
    shardCache.clear();
};

const createCacheStats = (scope: ArtifactCacheScope = 'memory_content_hash'): SitegraphArtifactCacheStats => ({
    scope,
    artifact_hits: 0,
    artifact_misses: 0,
    cached_bytes: 0,
    uncached_bytes: 0,
    cacheable_bytes: 0,
    memory_hits: 0,
    persistent_hits: 0,
    network_misses: 0,
});

const snapshotCacheStats = (stats: SitegraphArtifactCacheStats): SitegraphArtifactCacheStats => ({ ...stats });

const recordArtifactCache = (
    stats: SitegraphArtifactCacheStats | undefined,
    cached: boolean,
    bytes: number,
    layer: 'memory' | 'persistent' | 'network' = cached ? 'memory' : 'network'
): void => {
    if (!stats) return;
    const safeBytes = Math.max(0, Number(bytes) || 0);
    stats.cacheable_bytes += safeBytes;
    if (cached) {
        stats.artifact_hits += 1;
        stats.cached_bytes += safeBytes;
        if (layer === 'persistent') stats.persistent_hits += 1;
        else stats.memory_hits += 1;
    } else {
        stats.artifact_misses += 1;
        stats.uncached_bytes += safeBytes;
        stats.network_misses += 1;
    }
};

const publicAssetPath = (path: string): string => {
    if (/^https?:\/\//.test(path) || path.startsWith('/')) return path;
    return `/${path}`;
};

const artifactPersistentCached = async (
    cache: ArtifactContentCache | undefined,
    path: string
): Promise<boolean> => {
    if (!cache) return false;
    try {
        return await cache.has(publicAssetPath(path));
    } catch {
        return false;
    }
};

const fetchJsonArtifactPayload = async <T = unknown>(
    path: string,
    signal: AbortSignal,
    resourceType: 'index' | 'shard',
    cacheStats: SitegraphArtifactCacheStats | undefined,
    artifactBytes: number,
    artifactCache?: ArtifactContentCache
): Promise<T> => {
    const result = await fetchJsonArtifact<T>(publicAssetPath(path), signal, resourceType, artifactCache);
    recordArtifactCache(
        cacheStats,
        result.cacheHit,
        artifactBytes,
        result.cacheHit ? 'persistent' : 'network'
    );
    return result.value;
};

const fetchArrayBufferArtifactPayload = async (
    path: string,
    signal: AbortSignal,
    cacheStats: SitegraphArtifactCacheStats | undefined,
    artifactBytes: number,
    artifactCache?: ArtifactContentCache
): Promise<ArrayBuffer> => {
    const result = await fetchArrayBufferArtifact(publicAssetPath(path), signal, 'index', artifactCache);
    recordArtifactCache(
        cacheStats,
        result.cacheHit,
        artifactBytes,
        result.cacheHit ? 'persistent' : 'network'
    );
    return result.value;
};

const throwIfAborted = (signal: AbortSignal): void => {
    if (signal.aborted) {
        throw new DOMException('Search cancelled', 'AbortError');
    }
};

const isAbortError = (error: unknown): boolean => error instanceof DOMException && error.name === 'AbortError';

const yieldToWorker = async (): Promise<void> => {
    await new Promise(resolve => setTimeout(resolve, 0));
};

const firstScreenBytes = (session: SitegraphRoutedSession): number => {
    const artifacts = session.manifest.artifacts;
    return artifacts.source_registry.bytes + artifacts.global_query_directory.bytes + artifacts.query_aliases.bytes;
};

const activeFilters = (filters: SitegraphSearchFilters): boolean => {
    return (filters.sourceId || 'all') !== 'all'
        || (filters.facet || 'all') !== 'all'
        || (filters.dateRange || 'all') !== 'all';
};

const dateRangeFloorYear = (dateRange: SitegraphSearchFilters['dateRange'], now: number): number => {
    if (!dateRange || dateRange === 'all' || dateRange === 'undated') return 0;
    const years = dateRange === 'past_year' ? 1 : dateRange === 'past_3_years' ? 3 : 5;
    return new Date(now - years * 365 * 86_400_000).getFullYear();
};

const scopeMatchesFilters = (
    scope: SitegraphLocalIndexRef['scope'],
    filters: SitegraphSearchFilters,
    now: number
): boolean => {
    const sourceId = filters.sourceId || 'all';
    if (sourceId !== 'all' && scope.source_id !== sourceId) return false;
    const facet = filters.facet || 'all';
    if (facet !== 'all' && scope.facet !== facet) return false;
    const dateRange = filters.dateRange || 'all';
    if (dateRange === 'undated') return scope.year === 'undated';
    const floor = dateRangeFloorYear(dateRange, now);
    if (floor > 0) {
        const year = Number(scope.year);
        if (!Number.isFinite(year) || year < floor) return false;
    }
    return true;
};

const shardMatchesFilters = (
    shard: VerificationShard,
    filters: SitegraphSearchFilters,
    now: number
): boolean => {
    const shardSourceId = String(shard.source_id || '');
    const sourceId = filters.sourceId || 'all';
    if (sourceId !== 'all' && shardSourceId !== sourceId) return false;
    const facet = filters.facet || 'all';
    if (facet !== 'all' && !shard.facet_range.includes(facet)) return false;
    const dateRange = filters.dateRange || 'all';
    if (dateRange === 'undated') return shard.year_range.includes('undated');
    const floor = dateRangeFloorYear(dateRange, now);
    if (floor > 0) {
        return shard.year_range.some(year => Number.isFinite(Number(year)) && Number(year) >= floor);
    }
    return true;
};

const sourceEntriesById = (session: SitegraphRoutedSession): Map<string, SourceRegistryEntry> => {
    return new Map(session.sourceRegistry.sources.map(source => [source.source_id, source]));
};

const routeForTerms = (
    session: RoutedSessionWithArtifactCache,
    terms: string[],
    intent: string
): QueryDirectoryRoute[] => {
    const routes: QueryDirectoryRoute[] = [];
    const seen = new Set<QueryDirectoryRoute>();
    for (const term of terms) {
        const route = session.globalQueryDirectory.entries[normalize(term)];
        if (route && !seen.has(route)) {
            seen.add(route);
            routes.push(route);
        }
    }
    const intentRoute = session.globalQueryDirectory.intents[intent];
    if (intentRoute && !seen.has(intentRoute)) routes.push(intentRoute);
    return routes;
};

const uniqueOrdered = (values: string[]): string[] => {
    const seen = new Set<string>();
    const result: string[] = [];
    for (const value of values) {
        if (!value || seen.has(value)) continue;
        seen.add(value);
        result.push(value);
    }
    return result;
};

const buildQueryPlan = (
    session: SitegraphRoutedSession,
    query: string,
    terms: string[],
    filters: SitegraphSearchFilters
): SitegraphQueryPlan => {
    const profile = detectQueryIntent(query);
    const routes = routeForTerms(session, terms, profile.intent);
    const routeSources = routes.flatMap(route => route.likely_sources);
    const routeLocalIndexes = routes.flatMap(route => route.local_index_ids);
    const routeResultTypes = routes.flatMap(route => route.expected_result_types);
    const routeDecisions = routes.map(route => ({
        term: route.term || profile.intent,
        local_index_count: route.local_index_ids.length,
        expected_cost_bytes: route.expected_cost_bytes,
        expected_utility_per_kb: route.expected_utility_per_kb,
        likely_sources: route.likely_sources,
        likely_facets: route.likely_facets,
    }));
    const estimatedCostBytes = routeDecisions.reduce((sum, route) => sum + route.expected_cost_bytes, 0);
    const estimatedUtility = routeDecisions.reduce((sum, route) => sum + route.expected_utility_per_kb, 0);
    const allSources = session.sourceRegistry.sources.map(source => source.source_id);
    const filteredSource = filters.sourceId && filters.sourceId !== 'all' ? [filters.sourceId] : [];
    const sourceIds = uniqueOrdered([
        ...filteredSource,
        ...profile.authoritySources,
        ...routeSources,
        ...allSources,
    ]).filter(sourceId => allSources.includes(sourceId));
    const verificationSourceIds = filteredSource.length > 0 ? filteredSource : allSources;
    return {
        normalized_query: normalize(query),
        aliases: expandSitegraphQueryPhrases(query, session.queryAliases),
        intent: profile.intent,
        authority_sources: profile.authoritySources,
        expected_result_types: uniqueOrdered(routeResultTypes),
        source_ids: sourceIds,
        local_index_ids: uniqueOrdered(routeLocalIndexes),
        verification_source_ids: verificationSourceIds,
        declared_completion_scope: activeFilters(filters) ? 'scoped' : 'global',
        estimated_cost_bytes: estimatedCostBytes,
        estimated_utility_per_kb: Number(estimatedUtility.toFixed(6)),
        route_decisions: routeDecisions,
    };
};

const loadSourceManifest = async (
    entry: SourceRegistryEntry,
    signal: AbortSignal,
    cacheStats?: SitegraphArtifactCacheStats,
    artifactCache?: ArtifactContentCache
): Promise<SitegraphSourceManifest> => {
    const path = entry.artifact_manifest.path;
    const existing = sourceManifestCache.get(path);
    if (existing) {
        recordArtifactCache(cacheStats, true, entry.artifact_manifest.bytes, 'memory');
        return existing;
    }
    const payload = await fetchJsonArtifactPayload(
        path,
        signal,
        'index',
        cacheStats,
        entry.artifact_manifest.bytes,
        artifactCache
    );
    const parsed = parseSitegraphSourceManifest(payload, path);
    sourceManifestCache.set(path, parsed);
    return parsed;
};

const loadProofCatalog = async (
    sourceManifest: SitegraphSourceManifest,
    signal: AbortSignal,
    cacheStats?: SitegraphArtifactCacheStats,
    artifactCache?: ArtifactContentCache
): Promise<SitegraphProofCatalog> => {
    const artifact = sourceManifest.artifacts.proof_catalog;
    if (!artifact) {
        throw new SearchContractError(`Source manifest ${sourceManifest.source_id} is missing proof_catalog`);
    }
    const path = artifact.path;
    const existing = proofCatalogCache.get(path);
    if (existing) {
        recordArtifactCache(cacheStats, true, artifact.bytes, 'memory');
        return existing;
    }
    const payload = await fetchJsonArtifactPayload(path, signal, 'index', cacheStats, artifact.bytes, artifactCache);
    const parsed = parseSitegraphProofCatalog(payload, path);
    if (parsed.source_id !== sourceManifest.source_id) {
        throw new SearchContractError(`Validation failed for ${path}: proof catalog source_id does not match ${sourceManifest.source_id}`);
    }
    proofCatalogCache.set(path, parsed);
    return parsed;
};

const localShardRefsFor = (ref: SitegraphLocalIndexRef): SitegraphLocalShardRef[] => {
    const shards = ref.shards ?? [];
    if (shards.length > 0) return shards;
    return ref.scope.shard_ids.map(shardId => ({
        shard_id: shardId,
        path: '',
        bytes: 0,
        count: 0,
    }));
};

const lightIndexArtifactKey = (ref: SitegraphLocalIndexRef): string => {
    if (ref.light_index_meta && ref.light_index_packed) {
        return `${ref.light_index_meta.path}|${ref.light_index_packed.path}`;
    }
    if (!ref.light_index) {
        throw new SearchContractError(`Local index ${ref.index_id} is missing split light artifacts`);
    }
    return ref.light_index.path;
};

const queryTermCacheKey = (terms: string[]): string => Array.from(new Set(terms)).sort().join('\u0000');

const lightIndexRuntimeBytes = (ref: SitegraphLocalIndexRef): number => {
    if (ref.light_index_meta && ref.light_index_packed) {
        return ref.light_index_meta.bytes + ref.light_index_packed.bytes;
    }
    if (!ref.light_index) {
        throw new SearchContractError(`Local index ${ref.index_id} is missing split light artifacts`);
    }
    return ref.light_index.bytes;
};

const lightIndexCachedBytes = (ref: SitegraphLocalIndexRef): number => {
    if (ref.light_index_meta && ref.light_index_packed) {
        const metaBytes = localLightMetaCache.has(ref.light_index_meta.path) ? ref.light_index_meta.bytes : 0;
        const packedBytes = localLightPackedBytesCache.has(ref.light_index_packed.path) ? ref.light_index_packed.bytes : 0;
        return metaBytes + packedBytes;
    }
    if (ref.light_index && localLightIndexCache.has(ref.light_index.path)) return ref.light_index.bytes;
    return 0;
};

const verificationShardFromFullShard = (shard: SitegraphFullShard): VerificationShard => ({
    shard_id: shard.shard_id,
    source_id: String(shard.source_id || ''),
    path: shard.path,
    sha256: shard.sha256,
    bytes: shard.bytes,
    count: shard.count,
    facet_range: shard.facet_range,
    record_type_range: shard.record_type_range,
    section_range: shard.section_range,
    year_range: shard.year_range,
    hash_bucket: shard.hash_bucket,
    filter_token_count: Number(shard.filter_token_count || 0),
    filter_sha256: String(shard.filter_sha256 || ''),
});

const verificationShardFromProofCatalog = (shard: SitegraphProofCatalogShard): VerificationShard => ({
    shard_id: shard.shard_id,
    source_id: shard.source_id,
    path: shard.path,
    sha256: shard.sha256,
    bytes: shard.bytes,
    count: shard.document_count,
    facet_range: shard.scope.facets,
    record_type_range: shard.scope.record_types,
    section_range: shard.scope.sections,
    year_range: shard.scope.years,
    hash_bucket: shard.scope.hash_bucket,
    filter_token_count: shard.filter_contract.filter_token_count,
    filter_sha256: shard.filter_contract.filter_sha256,
});

const loadPlanningScope = async (
    session: RoutedSessionWithArtifactCache,
    plan: SitegraphQueryPlan,
    filters: SitegraphSearchFilters,
    now: number,
    signal: AbortSignal,
    cacheStats: SitegraphArtifactCacheStats
): Promise<LoadedPlanningScope> => {
    const entries = sourceEntriesById(session);
    const artifactCache = session.artifactCache;
    const sourceManifests: SitegraphSourceManifest[] = [];
    let sourceManifestBytes = 0;
    for (const sourceId of plan.source_ids) {
        const entry = entries.get(sourceId);
        if (!entry) continue;
        const manifest = await loadSourceManifest(entry, signal, cacheStats, artifactCache);
        sourceManifests.push(manifest);
        sourceManifestBytes += entry.artifact_manifest.bytes;
    }

    const plannedIndexIds = new Set(plan.local_index_ids);
    const plannedIndexOrder = new Map(plan.local_index_ids.map((indexId, index) => [indexId, index]));
    const routeFacetPriors = new Set(plan.route_decisions.flatMap(route => route.likely_facets));
    const routeSourcePriors = new Set(plan.route_decisions.flatMap(route => route.likely_sources));
    const yearScore = (year: string): number => {
        const numeric = Number(year);
        if (!Number.isFinite(numeric)) return 0.2;
        return Math.max(0.2, Math.min(1.2, (numeric - 2015) / 10));
    };
    const persistedLightBytes = new Map<string, number>();
    const persistedBodyBytes = new Map<string, number>();
    const cachedLightBytesForRef = (ref: SitegraphLocalIndexRef): number => {
        return Math.max(lightIndexCachedBytes(ref), persistedLightBytes.get(ref.index_id) ?? 0);
    };
    const cachedBodyBytesForRef = (ref: SitegraphLocalIndexRef): number => {
        return Math.max(bodyIndexCachedBytes(ref), persistedBodyBytes.get(ref.index_id) ?? 0);
    };
    const cacheStateForRef = (ref: SitegraphLocalIndexRef): 'cold' | 'partial' | 'warm' => {
        const lightCached = cachedLightBytesForRef(ref) === lightIndexRuntimeBytes(ref);
        const bodyCached = cachedBodyBytesForRef(ref) === bodyIndexArtifact(ref).bytes;
        if (lightCached && bodyCached) return 'warm';
        if (lightCached || bodyCached) return 'partial';
        return 'cold';
    };
    const expectedUncachedBytesForRef = (ref: SitegraphLocalIndexRef): number => {
        const lightBytes = Math.max(0, lightIndexRuntimeBytes(ref) - cachedLightBytesForRef(ref));
        const bodyArtifact = bodyIndexArtifact(ref);
        const bodyBytes = Math.max(0, bodyArtifact.bytes - cachedBodyBytesForRef(ref));
        return lightBytes + bodyBytes;
    };
    const utilityForRef = (ref: SitegraphLocalIndexRef): number => {
        const routed = plannedIndexIds.has(ref.index_id) ? 4 : 1;
        const sourcePrior = routeSourcePriors.has(ref.scope.source_id) || plan.authority_sources.includes(ref.scope.source_id) ? 2 : 1;
        const facetPrior = routeFacetPriors.has(ref.scope.facet) ? 1.5 : 1;
        const costKb = Math.max(1, expectedUncachedBytesForRef(ref) / 1024);
        return Number((routed * sourcePrior * facetPrior * yearScore(ref.scope.year) * Math.log2(ref.doc_count + 2) / costKb).toFixed(6));
    };
    let localRefs = sourceManifests
        .flatMap(sourceManifest => sourceManifest.local_indexes)
        .filter(ref => scopeMatchesFilters(ref.scope, filters, now));
    await Promise.all(localRefs.map(async ref => {
        if (ref.light_index_meta && ref.light_index_packed) {
            const [metaCached, packedCached] = await Promise.all([
                artifactPersistentCached(artifactCache, ref.light_index_meta.path),
                artifactPersistentCached(artifactCache, ref.light_index_packed.path),
            ]);
            persistedLightBytes.set(
                ref.index_id,
                (metaCached ? ref.light_index_meta.bytes : 0) + (packedCached ? ref.light_index_packed.bytes : 0)
            );
        } else if (ref.light_index && await artifactPersistentCached(artifactCache, ref.light_index.path)) {
            persistedLightBytes.set(ref.index_id, ref.light_index.bytes);
        }
        const bodyArtifact = bodyIndexArtifact(ref);
        if (await artifactPersistentCached(artifactCache, bodyArtifact.path)) {
            persistedBodyBytes.set(ref.index_id, bodyArtifact.bytes);
        }
    }));
    if (plannedIndexIds.size > 0) {
        const routedRefs = localRefs.filter(ref => plannedIndexIds.has(ref.index_id));
        if (routedRefs.length > 0) {
            localRefs = routedRefs
                .sort((a, b) => {
                    const utilityDelta = utilityForRef(b) - utilityForRef(a);
                    if (utilityDelta !== 0) return utilityDelta;
                    const orderDelta = (plannedIndexOrder.get(a.index_id) ?? Number.MAX_SAFE_INTEGER)
                        - (plannedIndexOrder.get(b.index_id) ?? Number.MAX_SAFE_INTEGER);
                    if (orderDelta !== 0) return orderDelta;
                    return b.doc_count - a.doc_count || a.index_id.localeCompare(b.index_id);
                })
                .slice(0, 48);
        }
    }
    if (plannedIndexIds.size === 0 || localRefs.every(ref => !plannedIndexIds.has(ref.index_id))) {
        localRefs = localRefs
            .sort((a, b) => {
                const utilityDelta = utilityForRef(b) - utilityForRef(a);
                if (utilityDelta !== 0) return utilityDelta;
                const yearDelta = Number(b.scope.year) - Number(a.scope.year);
                if (Number.isFinite(yearDelta) && yearDelta !== 0) return yearDelta;
                return b.doc_count - a.doc_count || a.index_id.localeCompare(b.index_id);
            })
            .slice(0, 48);
    }

    const shardPathById = new Map<string, string>();
    const shardBytesByPath = new Map<string, number>();
    for (const ref of localRefs) {
        for (const shard of localShardRefsFor(ref)) {
            if (shard.path) {
                shardPathById.set(shard.shard_id, shard.path);
                shardBytesByPath.set(shard.path, shard.bytes);
            }
        }
    }
    for (const sourceManifest of sourceManifests) {
        for (const shard of sourceManifest.full_shards) {
            shardPathById.set(shard.shard_id, shard.path);
            shardBytesByPath.set(shard.path, shard.bytes);
        }
    }

    return {
        sourceManifests,
        localRefs,
        sourceManifestBytes,
        shardPathById,
        shardBytesByPath,
        selectedLocalIndexes: localRefs.map(ref => ({
            index_id: ref.index_id,
            expected_bytes: lightIndexRuntimeBytes(ref) + bodyIndexArtifact(ref).bytes,
            expected_uncached_bytes: expectedUncachedBytesForRef(ref),
            cache_state: cacheStateForRef(ref),
            utility_score: utilityForRef(ref),
            source_id: ref.scope.source_id,
            facet: ref.scope.facet,
            year: ref.scope.year,
        })),
    };
};

const loadLocalLightIndex = async (
    ref: SitegraphLocalIndexRef,
    terms: string[],
    signal: AbortSignal,
    cacheStats?: SitegraphArtifactCacheStats,
    artifactCache?: ArtifactContentCache,
    packedImpactRetriever?: PackedImpactRetriever
): Promise<LoadedLocalLightRuntimeIndex> => {
    const path = lightIndexArtifactKey(ref);
    const usePackedRetriever = Boolean(packedImpactRetriever && ref.light_index_meta && ref.light_index_packed);
    const cacheKey = usePackedRetriever
        ? `${path}\u0000rust_wasm_packed_impact`
        : ref.light_index_meta && ref.light_index_packed
            ? `${path}\u0000${queryTermCacheKey(terms)}`
            : path;
    const bytes = lightIndexRuntimeBytes(ref);
    const existing = !usePackedRetriever ? localLightIndexCache.get(cacheKey) : undefined;
    if (existing) {
        recordArtifactCache(cacheStats, true, bytes, 'memory');
        return { documents: existing.documents, index: existing };
    }
    let payload: unknown;
    if (ref.light_index_meta && ref.light_index_packed) {
        let metadata = localLightMetaCache.get(ref.light_index_meta.path);
        if (metadata) {
            recordArtifactCache(cacheStats, true, ref.light_index_meta.bytes, 'memory');
        } else {
            metadata = await fetchJsonArtifactPayload<Omit<SitegraphLocalLightIndex, 'terms'>>(
                ref.light_index_meta.path,
                signal,
                'index',
                cacheStats,
                ref.light_index_meta.bytes,
                artifactCache
            );
            localLightMetaCache.set(ref.light_index_meta.path, metadata);
        }
        let packedBytes = localLightPackedBytesCache.get(ref.light_index_packed.path);
        if (packedBytes) {
            recordArtifactCache(cacheStats, true, ref.light_index_packed.bytes, 'memory');
        } else {
            packedBytes = await fetchArrayBufferArtifactPayload(
                ref.light_index_packed.path,
                signal,
                cacheStats,
                ref.light_index_packed.bytes,
                artifactCache
            );
            localLightPackedBytesCache.set(ref.light_index_packed.path, packedBytes);
        }
        payload = usePackedRetriever
            ? { ...metadata, terms: {} }
            : {
                ...metadata,
                terms: decodePackedImpactIndexTerms<SitegraphImpactIndex>(
                    packedBytes,
                    terms,
                    ref.light_index_packed.path
                ).terms,
            };
        const parsed = parseSitegraphLocalLightIndex(payload, path);
        localLightIndexCache.set(cacheKey, parsed);
        return {
            documents: parsed.documents,
            index: usePackedRetriever ? undefined : parsed,
            packedBytes: usePackedRetriever ? packedBytes : undefined,
            packedPath: usePackedRetriever ? ref.light_index_packed.path : undefined,
        };
    } else {
        if (!ref.light_index) {
            throw new SearchContractError(`Local index ${ref.index_id} is missing split light artifacts`);
        }
        payload = await fetchJsonArtifactPayload(ref.light_index.path, signal, 'index', cacheStats, bytes, artifactCache);
    }
    const parsed = parseSitegraphLocalLightIndex(payload, path);
    localLightIndexCache.set(cacheKey, parsed);
    return { documents: parsed.documents, index: parsed };
};

const loadLocalBodyIndex = async (
    ref: SitegraphLocalIndexRef,
    terms: string[],
    signal: AbortSignal,
    cacheStats?: SitegraphArtifactCacheStats,
    artifactCache?: ArtifactContentCache,
    packedImpactRetriever?: PackedImpactRetriever
): Promise<LoadedLocalBodyRuntimeIndex> => {
    const artifact = bodyIndexArtifact(ref);
    const path = artifact.path;
    const packed = path.endsWith('.bin');
    const usePackedRetriever = Boolean(packedImpactRetriever && packed);
    const cacheKey = usePackedRetriever
        ? `${path}\u0000rust_wasm_packed_impact`
        : packed ? `${path}\u0000${Array.from(new Set(terms)).sort().join('\u0000')}` : path;
    const existing = !usePackedRetriever ? localBodyIndexCache.get(cacheKey) : undefined;
    if (existing) {
        recordArtifactCache(cacheStats, true, artifact.bytes, 'memory');
        return { index: existing };
    }
    let payload: unknown;
    if (packed) {
        let buffer = localBodyPackedBytesCache.get(path);
        if (buffer) {
            recordArtifactCache(cacheStats, true, artifact.bytes, 'memory');
        } else {
            buffer = await fetchArrayBufferArtifactPayload(path, signal, cacheStats, artifact.bytes, artifactCache);
            localBodyPackedBytesCache.set(path, buffer);
        }
        if (usePackedRetriever) {
            return { packedBytes: buffer, packedPath: path };
        }
        payload = decodePackedLocalBodyIndexTerms(buffer, terms, path);
    } else {
        payload = await fetchJsonArtifactPayload(path, signal, 'index', cacheStats, artifact.bytes, artifactCache);
    }
    const parsed = parseSitegraphLocalBodyIndex(payload, path);
    localBodyIndexCache.set(cacheKey, parsed);
    return { index: parsed };
};

const bodyIndexArtifact = (ref: SitegraphLocalIndexRef): SitegraphArtifact => {
    const artifact = ref.body_index_packed ?? ref.body_index;
    if (!artifact) {
        throw new SearchContractError(`Local index ${ref.index_id} is missing body index artifacts`);
    }
    return artifact;
};

const bodyIndexCachedBytes = (ref: SitegraphLocalIndexRef): number => {
    const artifact = bodyIndexArtifact(ref);
    if (artifact.path.endsWith('.bin')) {
        return localBodyPackedBytesCache.has(artifact.path) ? artifact.bytes : 0;
    }
    return localBodyIndexCache.has(artifact.path) ? artifact.bytes : 0;
};

const selectLocalRefsWithinBudget = (
    refs: SitegraphLocalIndexRef[],
    byteBudget: number,
    byteSize: (ref: SitegraphLocalIndexRef) => number,
    minimumRefs: number
): SitegraphLocalIndexRef[] => {
    const selected: SitegraphLocalIndexRef[] = [];
    let selectedBytes = 0;
    for (const ref of refs) {
        const bytes = byteSize(ref);
        const needMinimumCoverage = selected.length < minimumRefs;
        if (!needMinimumCoverage && selected.length > 0 && selectedBytes + bytes > byteBudget) {
            continue;
        }
        selected.push(ref);
        selectedBytes += bytes;
    }
    return selected.length > 0 ? selected : refs.slice(0, 1);
};

const uniqueLocalRefs = (refs: SitegraphLocalIndexRef[]): SitegraphLocalIndexRef[] => {
    const seen = new Set<string>();
    const selected: SitegraphLocalIndexRef[] = [];
    for (const ref of refs) {
        if (seen.has(ref.index_id)) continue;
        seen.add(ref.index_id);
        selected.push(ref);
    }
    return selected;
};

const loadShardFilter = async (
    sourceManifest: SitegraphSourceManifest,
    signal: AbortSignal,
    cacheStats?: SitegraphArtifactCacheStats,
    artifactCache?: ArtifactContentCache
): Promise<ShardFilterMap> => {
    const artifact = sourceManifest.artifacts.shard_filter;
    if (!artifact) {
        throw new SearchContractError(`Source manifest ${sourceManifest.source_id} is missing shard_filter`);
    }
    const path = artifact.path;
    const existing = shardFilterCache.get(path);
    if (existing) {
        recordArtifactCache(cacheStats, true, artifact.bytes, 'memory');
        return existing;
    }
    const payload = await fetchJsonArtifactPayload(path, signal, 'index', cacheStats, artifact.bytes, artifactCache);
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
        throw new SearchContractError(`Validation failed for ${path}: shard_filter must be an object`);
    }
    shardFilterCache.set(path, payload as ShardFilterMap);
    return payload as ShardFilterMap;
};

const loadShard = (
    path: string,
    signal: AbortSignal,
    cacheStats?: SitegraphArtifactCacheStats,
    bytes = 0,
    artifactCache?: ArtifactContentCache
): Promise<SitegraphFullDocument[]> => {
    const existing = shardCache.get(path);
    if (existing) {
        recordArtifactCache(cacheStats, true, bytes, 'memory');
        return Promise.resolve(existing);
    }
    return fetchJsonArtifactPayload(path, signal, 'shard', cacheStats, bytes, artifactCache)
        .then(payload => {
            const documents = parseSitegraphFullDocuments(payload, path);
            shardCache.set(path, documents);
            return documents;
        });
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

interface ImpactBlock {
    key: string;
    impact: number;
    ids: number[];
}

const competitiveThreshold = (scores: Map<number, number>, target: number): number => {
    if (scores.size < target) return Number.NEGATIVE_INFINITY;
    return sortedScoreEntries(scores)[Math.max(0, target - 1)]?.[1] ?? Number.NEGATIVE_INFINITY;
};

const impactBlocksForTerms = (
    index: SitegraphLocalLightIndex | SitegraphLocalBodyIndex,
    terms: string[]
): ImpactBlock[] => {
    const blocks: ImpactBlock[] = [];
    const blockSize = Math.max(8, index.block_size || 32);
    for (const term of terms) {
        const termPayload = index.terms[term];
        if (!termPayload) continue;
        for (const [field, ids] of Object.entries(termPayload)) {
            const impact = (index.field_impacts[field] || SITEGRAPH_FIELD_WEIGHTS[field] || 8) + Math.min(term.length, 8);
            for (let offset = 0; offset < ids.length; offset += blockSize) {
                blocks.push({
                    key: `${term}\u0000${field}`,
                    impact,
                    ids: ids.slice(offset, offset + blockSize),
                });
            }
        }
    }
    return blocks.sort((a, b) => b.impact - a.impact || a.key.localeCompare(b.key));
};

const suffixUniqueImpact = (blocks: ImpactBlock[]): number[] => {
    const suffix = new Array<number>(blocks.length + 1).fill(0);
    const seen = new Set<string>();
    let sum = 0;
    for (let index = blocks.length - 1; index >= 0; index -= 1) {
        const block = blocks[index];
        if (block && !seen.has(block.key)) {
            seen.add(block.key);
            sum += block.impact;
        }
        suffix[index] = sum;
    }
    return suffix;
};

const applyImpactIndex = (
    scores: Map<number, number>,
    index: SitegraphLocalLightIndex | SitegraphLocalBodyIndex,
    terms: string[],
    targetCandidates: number,
    telemetry: SearchTelemetry
): void => {
    const blocks = impactBlocksForTerms(index, terms);
    const suffix = suffixUniqueImpact(blocks);
    telemetry.retrieval.dynamicPruning = true;
    for (let index = 0; index < blocks.length; index += 1) {
        const block = blocks[index];
        if (!block) continue;
        const threshold = competitiveThreshold(scores, targetCandidates);
        telemetry.retrieval.competitiveThreshold = Number.isFinite(threshold) ? threshold : telemetry.retrieval.competitiveThreshold;
        const maxPossibleForUnseenDoc = block.impact + (suffix[index + 1] ?? 0);
        const hasKnownCandidate = block.ids.some(docIndex => scores.has(docIndex));
        if (!hasKnownCandidate && scores.size >= targetCandidates && maxPossibleForUnseenDoc <= threshold) {
            telemetry.retrieval.impactBlocksPruned += 1;
            telemetry.retrieval.postingsPruned += block.ids.length;
            continue;
        }
        telemetry.retrieval.impactBlocksVisited += 1;
        for (const docIndex of block.ids) {
            telemetry.retrieval.postingsVisited += 1;
            scores.set(docIndex, (scores.get(docIndex) || 0) + block.impact);
        }
    }
};

const markRetrievalEngine = (
    telemetry: SearchTelemetry,
    engine: SearchTelemetry['retrieval']['engine']
): void => {
    if (engine === 'mixed') {
        telemetry.retrieval.engine = 'mixed';
        return;
    }
    if (telemetry.retrieval.engine !== engine) {
        telemetry.retrieval.engine = telemetry.retrieval.typescriptCalls + telemetry.retrieval.wasmCalls > 0 ? 'mixed' : engine;
    }
};

const recordPackedImpactRetrieval = (
    result: PackedImpactRetrievalMetrics,
    telemetry: SearchTelemetry
): void => {
    telemetry.retrieval.dynamicPruning = true;
    markRetrievalEngine(telemetry, 'rust_wasm_packed_impact');
    telemetry.retrieval.wasmCalls += 1;
    telemetry.retrieval.impactBlocksVisited += result.impactBlocksVisited;
    telemetry.retrieval.impactBlocksPruned += result.impactBlocksPruned;
    telemetry.retrieval.postingsVisited += result.postingsVisited;
    telemetry.retrieval.postingsPruned += result.postingsPruned;
    telemetry.retrieval.competitiveThreshold = Number.isFinite(result.competitiveThreshold)
        ? result.competitiveThreshold
        : telemetry.retrieval.competitiveThreshold;
};

const addPackedImpactScoreEntries = (
    scores: Map<number, number>,
    entries: Array<readonly [number, number]>,
    telemetry: SearchTelemetry
): void => {
    telemetry.retrieval.scoreEntriesReturned += entries.length;
    for (const [docIndex, score] of entries) {
        scores.set(docIndex, (scores.get(docIndex) || 0) + score);
    }
};

const setPackedImpactScoreEntries = (
    scores: Map<number, number>,
    entries: Array<readonly [number, number]>,
    telemetry: SearchTelemetry
): void => {
    telemetry.retrieval.scoreEntriesReturned += entries.length;
    for (const [docIndex, score] of entries) {
        scores.set(docIndex, score);
    }
};

const applyPackedImpactRetrieval = (
    scores: Map<number, number>,
    result: PackedImpactRetrievalResult,
    telemetry: SearchTelemetry
): void => {
    recordPackedImpactRetrieval(result, telemetry);
    addPackedImpactScoreEntries(scores, result.scoreEntries, telemetry);
};

const syncPackedImpactSessionScores = async (
    scores: Map<number, number>,
    retrievalSession: PackedImpactRetrievalSession | undefined,
    telemetry: SearchTelemetry
): Promise<void> => {
    if (!retrievalSession) return;
    const entries = await retrievalSession.readScoreEntries();
    setPackedImpactScoreEntries(scores, entries, telemetry);
};

const applyImpactIndexRuntime = async (
    scores: Map<number, number>,
    runtimeIndex: LoadedLocalLightRuntimeIndex | LoadedLocalBodyRuntimeIndex,
    terms: string[],
    targetCandidates: number,
    telemetry: SearchTelemetry,
    packedImpactRetriever?: PackedImpactRetriever,
    retrievalSession?: PackedImpactRetrievalSession
): Promise<boolean> => {
    if (runtimeIndex.packedBytes && runtimeIndex.packedPath && retrievalSession) {
        const result = await retrievalSession.applyPackedImpactScores({
            bytes: runtimeIndex.packedBytes,
            terms,
            targetCandidates,
            source: runtimeIndex.packedPath,
        });
        recordPackedImpactRetrieval(result, telemetry);
        return true;
    }
    if (runtimeIndex.packedBytes && runtimeIndex.packedPath && packedImpactRetriever) {
        const result = await packedImpactRetriever.retrievePackedImpactScores({
            bytes: runtimeIndex.packedBytes,
            terms,
            targetCandidates,
            source: runtimeIndex.packedPath,
        });
        applyPackedImpactRetrieval(scores, result, telemetry);
        return false;
    }
    if (!runtimeIndex.index) {
        throw new SearchContractError('Packed impact index runtime is missing a TypeScript index and WASM retriever');
    }
    markRetrievalEngine(telemetry, 'typescript_impact_index');
    telemetry.retrieval.typescriptCalls += 1;
    applyImpactIndex(scores, runtimeIndex.index, terms, targetCandidates, telemetry);
    return false;
};

const applyLocalMetaFallback = (
    docsByIndex: Map<number, SitegraphDocMeta>,
    scores: Map<number, number>,
    normalizedQuery: string,
    filters: SitegraphSearchFilters,
    now: number
): number[] => {
    if (!normalizedQuery) return [];
    let filteredScoreCount = 0;
    for (const docIndex of scores.keys()) {
        const meta = docsByIndex.get(docIndex);
        if (meta && sitegraphDocumentMatchesFilters(meta, filters, now)) filteredScoreCount += 1;
        if (filteredScoreCount >= 8) return [];
    }
    const matchedIndices: number[] = [];
    for (const meta of docsByIndex.values()) {
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
    docsByIndex: Map<number, SitegraphDocMeta>,
    scores: Map<number, number>,
    shardPathById: Map<string, string>,
    candidateLimit: number,
    maxShardLoads: number,
    filters: SitegraphSearchFilters,
    now: number
): { indices: number[]; paths: string[] } => {
    const indices: number[] = [];
    const paths: string[] = [];
    const seenPaths = new Set<string>();
    for (const [docIndex] of sortedScoreEntries(scores).slice(0, candidateLimit)) {
        const meta = docsByIndex.get(docIndex);
        if (!meta?.shard?.shard_id) continue;
        if (!sitegraphDocumentMatchesFilters(meta, filters, now)) continue;
        const shardPath = meta.shard.path || shardPathById.get(meta.shard.shard_id);
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
    fullDocsByIndex: Map<number, SitegraphFullDocument>,
    shardBytesByPath: Map<string, number>,
    cacheStats: SitegraphArtifactCacheStats,
    artifactCache?: ArtifactContentCache
): Promise<void> => {
    for (let index = 0; index < paths.length; index += SHARD_BATCH_SIZE) {
        throwIfAborted(signal);
        const batch = paths.slice(index, index + SHARD_BATCH_SIZE);
        const shardResults = await Promise.all(batch.map(path => loadShard(
            path,
            signal,
            cacheStats,
            shardBytesByPath.get(path) || 0,
            artifactCache
        )));
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

const loadedBytesFor = (
    session: SitegraphRoutedSession,
    localIndexBytes: number,
    hydratedShardBytes: number,
    filterBytes: number
): number => firstScreenBytes(session) + localIndexBytes + hydratedShardBytes + filterBytes;

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
    session: SitegraphRoutedSession,
    phase: SitegraphSearchPhase,
    searchedFields: string[],
    provedNoMatchShards: number,
    scannedShards: number,
    searchedDocuments: number,
    totalShards: number,
    totalDocuments: number,
    localIndexBytes: number,
    hydratedShardBytes: number,
    filterBytes: number,
    usedBodyIndex: boolean,
    exhaustiveComplete: boolean,
    scoped: boolean,
    ledgerEntries: SitegraphProofLedgerEntry[] | null = null,
    cacheStats: SitegraphArtifactCacheStats = createCacheStats()
): SitegraphSearchCoverage => {
    const ledger = proofLedgerSummary(ledgerEntries, {
        totalShards,
        scannedShards,
        provedNoMatchShards,
        exhaustiveComplete,
    });
    const cache = snapshotCacheStats(cacheStats);
    return {
        phase,
        coverage_state: phase,
        scope: scoped ? 'scoped' : 'global',
        searched_fields: searchedFields,
        proved_no_match_shards: ledger.proved_no_match_shards,
        scanned_shards: ledger.scanned_shards,
        excluded_by_filter_shards: ledger.excluded_by_filter_shards,
        excluded_by_declared_scope_shards: ledger.excluded_by_declared_scope_shards,
        pending_shards: ledger.pending_shards,
        failed_shards: ledger.failed_shards,
        total_shards: ledger.total_shards,
        searched_documents: searchedDocuments,
        total_documents: totalDocuments,
        loaded_bytes: loadedBytesFor(session, localIndexBytes, hydratedShardBytes, filterBytes),
        uncached_loaded_bytes: cache.uncached_bytes,
        cached_artifact_bytes: cache.cached_bytes,
        first_screen_bytes: firstScreenBytes(session),
        local_index_bytes: localIndexBytes,
        hydrated_shard_bytes: hydratedShardBytes,
        used_body_index: usedBodyIndex,
        exhaustive_complete: exhaustiveComplete && ledger.complete,
        proof_ledger: ledger,
        cache,
    };
};

const statsFor = (
    phase: SitegraphSearchPhase,
    coverage: SitegraphSearchCoverage,
    plan: SitegraphQueryPlan,
    loadedLocalIndexIds: Set<string>,
    loadedShardPaths: Set<string>,
    candidateCount: number,
    resultMap: Map<string, RankedSitegraphDocument>,
    telemetry: SearchTelemetry
): SitegraphQueryStats => ({
    phase,
    coverage,
    plan,
    usedBodyIndex: coverage.used_body_index,
    loadedLocalIndexCount: loadedLocalIndexIds.size,
    loadedLocalIndexIds: Array.from(loadedLocalIndexIds).sort(),
    loadedShardCount: loadedShardPaths.size,
    loadedShardPaths: Array.from(loadedShardPaths).sort(),
    candidateCount,
    exhaustiveComplete: coverage.exhaustive_complete,
    resultCount: resultMap.size,
    localIndexBytes: coverage.local_index_bytes,
    hydratedShardBytes: coverage.hydrated_shard_bytes,
    uncachedLoadedBytes: coverage.uncached_loaded_bytes,
    cachedArtifactBytes: coverage.cached_artifact_bytes,
    cache: coverage.cache,
    fallbacks: {
        localMetaFallbackDocuments: telemetry.localMetaFallbackDocIndices.size,
        snippetFallbackResults: Array.from(resultMap.values()).filter(result => result.match_snippet?.fallback === true).length,
        verifiedFullScanMatches: telemetry.fullScanMatchDocIndices.size,
    },
    retrieval: {
        ...telemetry.retrieval,
    },
});

const documentMatchesFullScan = (document: SitegraphFullDocument, matchPhrases: string[]): boolean => {
    const blob = fullScanBlob(document);
    return matchPhrases.some(term => blob.includes(term));
};

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
    docsByIndex: Map<number, SitegraphDocMeta>,
    shardPathById: Map<string, string>,
    scores: Map<number, number>,
    query: string,
    terms: string[],
    signal: AbortSignal,
    loadedShardPaths: Set<string>,
    fullDocsByIndex: Map<number, SitegraphFullDocument>,
    shardBytesByPath: Map<string, number>,
    cacheStats: SitegraphArtifactCacheStats,
    candidateLimit: number,
    maxShardLoads: number,
    matchPhrases: string[],
    filters: SitegraphSearchFilters,
    now: number,
    artifactCache?: ArtifactContentCache
): Promise<{ ranked: RankedSitegraphDocument[]; candidateCount: number }> => {
    const candidates = candidateShardPaths(docsByIndex, scores, shardPathById, candidateLimit, maxShardLoads, filters, now);
    const pathsToLoad = candidates.paths.filter(path => !loadedShardPaths.has(path));
    await loadShardBatch(pathsToLoad, signal, loadedShardPaths, fullDocsByIndex, shardBytesByPath, cacheStats, artifactCache);
    return {
        ranked: rankHydratedCandidates(candidates.indices, fullDocsByIndex, scores, query, terms, matchPhrases, filters, now),
        candidateCount: candidates.indices.length,
    };
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

const decodedFilterBytes = (filter: ShardFilterMap[string]): Uint8Array => {
    const cached = decodedFilterCache.get(filter);
    if (cached) return cached;
    const decoded = decodeBase64Bytes(filter.bitset_base64);
    decodedFilterCache.set(filter, decoded);
    return decoded;
};

const bloomMayContain = (filter: ShardFilterMap[string], term: string): boolean => {
    const bytes = decodedFilterBytes(filter);
    for (let seed = 0; seed < filter.hash_count; seed += 1) {
        const bit = filterTokenHashInt(term, seed) % filter.bit_count;
        if (((bytes[Math.floor(bit / 8)] ?? 0) & (1 << (bit % 8))) === 0) {
            return false;
        }
    }
    return true;
};

const shardFilterPhraseTokens = (phrase: string): string[] => {
    const text = normalize(phrase);
    if (!text) return [];
    const tokens = new Set<string>();
    const matches = text.match(/[\u4e00-\u9fff]{2,}|[a-z0-9][a-z0-9._-]{1,}/g) || [];
    if (matches.length === 0 && text.length >= 2) {
        tokens.add(text);
    }
    for (const part of matches) {
        if (/^[\u4e00-\u9fff]+$/.test(part)) {
            if (part.length <= 16) tokens.add(part);
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
    return Array.from(tokens).sort((a, b) => b.length - a.length);
};

const shardFilterProvesNoMatch = (
    shardId: string,
    shardFilter: ShardFilterMap,
    matchPhrases: string[]
): boolean => {
    const filter = shardFilter[shardId];
    if (!filter || filter.hash_algorithm !== 'bloom-fnv1a32-utf8') return false;
    const phrases = matchPhrases.map(shardFilterPhraseTokens).filter(tokens => tokens.length > 0);
    if (phrases.length === 0) return false;
    return phrases.every(tokens => tokens.some(token => !bloomMayContain(filter, token)));
};

const proofLedgerSummary = (
    entries: SitegraphProofLedgerEntry[] | null,
    fallback: {
        totalShards: number;
        scannedShards: number;
        provedNoMatchShards: number;
        exhaustiveComplete: boolean;
    }
): SitegraphProofLedgerSummary => {
    if (!entries) {
        return {
            total_shards: fallback.totalShards,
            pending_shards: fallback.exhaustiveComplete ? 0 : Math.max(0, fallback.totalShards - fallback.scannedShards - fallback.provedNoMatchShards),
            scanned_shards: fallback.scannedShards,
            proved_no_match_shards: fallback.provedNoMatchShards,
            excluded_by_filter_shards: 0,
            excluded_by_declared_scope_shards: 0,
            failed_shards: 0,
            complete: fallback.exhaustiveComplete,
        };
    }
    const count = (state: SitegraphProofLedgerState): number => entries.filter(entry => entry.state === state).length;
    const pending = count('pending');
    const failed = count('failed');
    return {
        total_shards: entries.length,
        pending_shards: pending,
        scanned_shards: count('scanned'),
        proved_no_match_shards: count('proved_no_match'),
        excluded_by_filter_shards: count('excluded_by_filter'),
        excluded_by_declared_scope_shards: count('excluded_by_declared_scope'),
        failed_shards: failed,
        complete: pending === 0 && failed === 0,
    };
};

const buildProofLedger = (
    shards: VerificationShard[],
    filters: SitegraphSearchFilters,
    now: number
): SitegraphProofLedgerEntry[] => shards.map(shard => {
    const matches = shardMatchesFilters(shard, filters, now);
    return {
        shard_id: shard.shard_id,
        source_id: String(shard.source_id || ''),
        state: matches ? 'pending' : 'excluded_by_filter',
        document_count: shard.count,
        byte_size: shard.bytes,
        path: shard.path,
        reason: matches ? 'awaiting shard filter proof or scan' : 'excluded by active source/facet/date filter',
        covered_fields: FULL_SCAN_FIELDS,
    };
});

const setLedgerState = (
    entries: SitegraphProofLedgerEntry[],
    shardId: string,
    state: SitegraphProofLedgerState,
    reason: string
): void => {
    const entry = entries.find(item => item.shard_id === shardId);
    if (entry) {
        entry.state = state;
        entry.reason = reason;
    }
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
    session: SitegraphRoutedSession,
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
    const terms = tokenizeSitegraphQuery(trimmed, session.queryAliases);
    const artifactCache = (session as RoutedSessionWithArtifactCache).artifactCache;
    const packedImpactRetriever = (session as RoutedSessionWithArtifactCache).packedImpactRetriever;
    const normalizedQuery = normalize(trimmed);
    const matchPhrases = expandSitegraphQueryPhrases(trimmed, session.queryAliases);
    const plan = buildQueryPlan(session, trimmed, terms, filters);
    const scores = new Map<number, number>();
    const resultMap = new Map<string, RankedSitegraphDocument>();
    const loadedShardPaths = new Set<string>();
    const loadedLocalIndexIds = new Set<string>();
    const docsByIndex = new Map<number, SitegraphDocMeta>();
    const fullDocsByIndex = new Map<number, SitegraphFullDocument>();
    const cacheStats = createCacheStats(artifactCache?.scope ?? 'memory_content_hash');
    const telemetry: SearchTelemetry = {
        localMetaFallbackDocIndices: new Set<number>(),
        fullScanMatchDocIndices: new Set<number>(),
        retrieval: {
            dynamicPruning: false,
            engine: 'typescript_impact_index',
            impactBlocksVisited: 0,
            impactBlocksPruned: 0,
            postingsVisited: 0,
            postingsPruned: 0,
            competitiveThreshold: 0,
            wasmCalls: 0,
            typescriptCalls: 0,
            scoreEntriesReturned: 0,
        },
    };
    let candidateCount = 0;
    let usedBodyIndex = false;
    let localIndexBytes = 0;
    let hydratedShardBytes = 0;
    let filterBytes = 0;
    let totalScopeShards = session.manifest.progressive_search.total_shards;
    let totalScopeDocuments = session.manifest.progressive_search.total_documents;
    const scoped = activeFilters(filters);
    let proofLedgerEntries: SitegraphProofLedgerEntry[] | null = null;

    const emitResults = (
        type: SitegraphSearchPhase,
        coverage: SitegraphSearchCoverage,
        includeResults: boolean
    ) => {
        const stats = statsFor(type, coverage, plan, loadedLocalIndexIds, loadedShardPaths, candidateCount, resultMap, telemetry);
        emit({
            type,
            query: trimmed,
            coverage,
            stats,
            ...(includeResults ? { results: rankedSnapshot(resultMap, stats, limit, sortMode) } : {}),
        });
    };

    const startedCoverage = coverageFor(
        session,
        'plan_started',
        [],
        0,
        0,
        0,
        totalScopeShards,
        totalScopeDocuments,
        0,
        0,
        0,
        false,
        false,
        scoped,
        null,
        cacheStats
    );
    emitResults('plan_started', startedCoverage, false);
    throwIfAborted(signal);

    if (trimmed.length < 2) {
        const completePhase = scoped ? 'scoped_exhaustive_complete' : 'global_exhaustive_complete';
        const completeCoverage = coverageFor(session, completePhase, FULL_SCAN_FIELDS, 0, 0, 0, totalScopeShards, totalScopeDocuments, 0, 0, 0, false, true, scoped, null, cacheStats);
        emitResults(completePhase, completeCoverage, true);
        return;
    }

    const planningScope = await loadPlanningScope(session, plan, filters, now, signal, cacheStats);
    plan.selected_local_indexes = planningScope.selectedLocalIndexes;
    plan.estimated_cost_bytes = planningScope.selectedLocalIndexes.reduce((sum, item) => sum + item.expected_uncached_bytes, plan.estimated_cost_bytes);
    const firstTrustedLocalBudget = Math.max(
        0,
        FIRST_TRUSTED_MAX_UNCACHED_BYTES
        - firstScreenBytes(session)
        - planningScope.sourceManifestBytes
        - FIRST_TRUSTED_HYDRATION_RESERVE_BYTES
    );
    const firstTrustedRefs = selectLocalRefsWithinBudget(
        planningScope.localRefs,
        firstTrustedLocalBudget,
        lightIndexRuntimeBytes,
        MIN_FIRST_TRUSTED_LOCAL_INDEXES
    );
    const topResultsLocalBudget = Math.max(
        0,
        TOP_RESULTS_MAX_UNCACHED_BYTES
        - firstScreenBytes(session)
        - planningScope.sourceManifestBytes
        - TOP_RESULTS_HYDRATION_RESERVE_BYTES
    );
    const topResultsRefs = uniqueLocalRefs([
        ...firstTrustedRefs,
        ...selectLocalRefsWithinBudget(
            planningScope.localRefs,
            topResultsLocalBudget,
            ref => lightIndexRuntimeBytes(ref) + bodyIndexArtifact(ref).bytes,
            MIN_TOP_RESULTS_LOCAL_INDEXES
        ),
    ]);
    plan.phase_local_index_ids = {
        first_trusted_results: firstTrustedRefs.map(ref => ref.index_id),
        top_results_hydrated: topResultsRefs.map(ref => ref.index_id),
        proof_complete: planningScope.localRefs.map(ref => ref.index_id),
    };
    localIndexBytes += planningScope.sourceManifestBytes;
    const localIndexStartedCoverage = coverageFor(
        session,
        'local_index_started',
        [],
        0,
        0,
        0,
        totalScopeShards,
        totalScopeDocuments,
        localIndexBytes,
        hydratedShardBytes,
        filterBytes,
        false,
        false,
        scoped,
        null,
        cacheStats
    );
    emitResults('local_index_started', localIndexStartedCoverage, false);

    const packedImpactSessionPromise = packedImpactRetriever?.createSession?.(candidateLimit);
    const localLightIndexes = await Promise.all(firstTrustedRefs.map(ref => loadLocalLightIndex(
        ref,
        terms,
        signal,
        cacheStats,
        artifactCache,
        packedImpactRetriever
    )));
    const packedImpactSession = await packedImpactSessionPromise;
    let packedImpactSessionDirty = false;
    firstTrustedRefs.forEach(ref => {
        loadedLocalIndexIds.add(ref.index_id);
        localIndexBytes += lightIndexRuntimeBytes(ref);
    });
    for (const localIndex of localLightIndexes) {
        for (const document of localIndex.documents) {
            docsByIndex.set(document.doc_index, document);
        }
        packedImpactSessionDirty = await applyImpactIndexRuntime(
            scores,
            localIndex,
            terms,
            candidateLimit,
            telemetry,
            packedImpactRetriever,
            packedImpactSession
        ) || packedImpactSessionDirty;
    }
    if (packedImpactSessionDirty) {
        await syncPackedImpactSessionScores(scores, packedImpactSession, telemetry);
        packedImpactSessionDirty = false;
    }
    for (const docIndex of applyLocalMetaFallback(docsByIndex, scores, normalizedQuery, filters, now)) {
        telemetry.localMetaFallbackDocIndices.add(docIndex);
    }

    const quick = await hydrateCandidatePhase(
        docsByIndex,
        planningScope.shardPathById,
        scores,
        trimmed,
        terms,
        signal,
        loadedShardPaths,
        fullDocsByIndex,
        planningScope.shardBytesByPath,
        cacheStats,
        Math.min(candidateLimit, 48),
        Math.min(maxShardLoads, QUICK_MAX_SHARD_LOADS),
        matchPhrases,
        filters,
        now,
        artifactCache
    );
    candidateCount = quick.candidateCount;
    for (const path of loadedShardPaths) {
        hydratedShardBytes += planningScope.shardBytesByPath.get(path) || 0;
    }
    mergeRankedResults(resultMap, quick.ranked);
    const firstTrustedCoverage = coverageFor(
        session,
        'first_trusted_results',
        LIGHT_SEARCH_FIELDS,
        0,
        loadedShardPaths.size,
        fullDocsByIndex.size,
        totalScopeShards,
        totalScopeDocuments,
        localIndexBytes,
        hydratedShardBytes,
        filterBytes,
        false,
        false,
        scoped,
        null,
        cacheStats
    );
    emitResults('first_trusted_results', firstTrustedCoverage, true);

    const bodyStartedCoverage = coverageFor(
        session,
        'body_index_started',
        LIGHT_SEARCH_FIELDS,
        0,
        loadedShardPaths.size,
        fullDocsByIndex.size,
        totalScopeShards,
        totalScopeDocuments,
        localIndexBytes,
        hydratedShardBytes,
        filterBytes,
        false,
        false,
        scoped,
        null,
        cacheStats
    );
    emitResults('body_index_started', bodyStartedCoverage, false);
    throwIfAborted(signal);
    const additionalTopLightRefs = topResultsRefs.filter(ref => !loadedLocalIndexIds.has(ref.index_id));
    const additionalTopLightIndexes = await Promise.all(additionalTopLightRefs.map(ref => loadLocalLightIndex(
        ref,
        terms,
        signal,
        cacheStats,
        artifactCache,
        packedImpactRetriever
    )));
    additionalTopLightRefs.forEach(ref => {
        loadedLocalIndexIds.add(ref.index_id);
        localIndexBytes += lightIndexRuntimeBytes(ref);
    });
    for (const localIndex of additionalTopLightIndexes) {
        for (const document of localIndex.documents) {
            docsByIndex.set(document.doc_index, document);
        }
        packedImpactSessionDirty = await applyImpactIndexRuntime(
            scores,
            localIndex,
            terms,
            candidateLimit,
            telemetry,
            packedImpactRetriever,
            packedImpactSession
        ) || packedImpactSessionDirty;
    }
    if (packedImpactSessionDirty) {
        await syncPackedImpactSessionScores(scores, packedImpactSession, telemetry);
        packedImpactSessionDirty = false;
    }
    const bodyIndexes = await Promise.all(topResultsRefs.map(ref => loadLocalBodyIndex(
        ref,
        terms,
        signal,
        cacheStats,
        artifactCache,
        packedImpactRetriever
    )));
    topResultsRefs.forEach(ref => {
        localIndexBytes += bodyIndexArtifact(ref).bytes;
    });
    usedBodyIndex = true;
    for (const bodyIndex of bodyIndexes) {
        packedImpactSessionDirty = await applyImpactIndexRuntime(
            scores,
            bodyIndex,
            terms,
            candidateLimit,
            telemetry,
            packedImpactRetriever,
            packedImpactSession
        ) || packedImpactSessionDirty;
    }
    if (packedImpactSessionDirty) {
        await syncPackedImpactSessionScores(scores, packedImpactSession, telemetry);
        packedImpactSessionDirty = false;
    }
    for (const docIndex of applyLocalMetaFallback(docsByIndex, scores, normalizedQuery, filters, now)) {
        telemetry.localMetaFallbackDocIndices.add(docIndex);
    }
    const beforeBodyShardPaths = new Set(loadedShardPaths);
    const body = await hydrateCandidatePhase(
        docsByIndex,
        planningScope.shardPathById,
        scores,
        trimmed,
        terms,
        signal,
        loadedShardPaths,
        fullDocsByIndex,
        planningScope.shardBytesByPath,
        cacheStats,
        Math.min(candidateLimit, 96),
        Math.min(maxShardLoads, BODY_MAX_SHARD_LOADS),
        matchPhrases,
        filters,
        now,
        artifactCache
    );
    candidateCount = body.candidateCount;
    for (const path of loadedShardPaths) {
        if (beforeBodyShardPaths.has(path)) continue;
        hydratedShardBytes += planningScope.shardBytesByPath.get(path) || 0;
    }
    mergeRankedResults(resultMap, body.ranked);

    const beforeHydrateShardPaths = new Set(loadedShardPaths);
    const hydrate = await hydrateCandidatePhase(
        docsByIndex,
        planningScope.shardPathById,
        scores,
        trimmed,
        terms,
        signal,
        loadedShardPaths,
        fullDocsByIndex,
        planningScope.shardBytesByPath,
        cacheStats,
        candidateLimit,
        Math.min(maxShardLoads, HYDRATE_MAX_SHARD_LOADS),
        matchPhrases,
        filters,
        now,
        artifactCache
    );
    candidateCount = hydrate.candidateCount;
    for (const path of loadedShardPaths) {
        if (beforeHydrateShardPaths.has(path)) continue;
        hydratedShardBytes += planningScope.shardBytesByPath.get(path) || 0;
    }
    mergeRankedResults(resultMap, hydrate.ranked);
    const hydratedCoverage = coverageFor(
        session,
        'top_results_hydrated',
        BODY_SEARCH_FIELDS,
        0,
        loadedShardPaths.size,
        fullDocsByIndex.size,
        totalScopeShards,
        totalScopeDocuments,
        localIndexBytes,
        hydratedShardBytes,
        filterBytes,
        usedBodyIndex,
        false,
        scoped,
        null,
        cacheStats
    );
    emitResults('top_results_hydrated', hydratedCoverage, true);

    const verificationEntries = sourceEntriesById(session);
    const verificationManifests: SitegraphSourceManifest[] = [];
    const allVerificationShards: VerificationShard[] = [];
    for (const sourceId of plan.verification_source_ids) {
        const entry = verificationEntries.get(sourceId);
        if (!entry) continue;
        const sourceManifest = await loadSourceManifest(entry, signal, cacheStats, artifactCache);
        verificationManifests.push(sourceManifest);
        if (!planningScope.sourceManifests.some(item => item.source_id === sourceManifest.source_id)) {
            localIndexBytes += entry.artifact_manifest.bytes;
        }
        const proofCatalog = await loadProofCatalog(sourceManifest, signal, cacheStats, artifactCache);
        filterBytes += sourceManifest.artifacts.proof_catalog?.bytes || 0;
        allVerificationShards.push(...proofCatalog.shards.map(verificationShardFromProofCatalog));
    }
    if (allVerificationShards.length === 0) {
        allVerificationShards.push(...verificationManifests.flatMap(sourceManifest => sourceManifest.full_shards.map(verificationShardFromFullShard)));
    }
    proofLedgerEntries = buildProofLedger(allVerificationShards, filters, now);
    const inScopeShards = allVerificationShards
        .filter(shard => proofLedgerEntries?.find(entry => entry.shard_id === shard.shard_id)?.state === 'pending');
    totalScopeShards = proofLedgerEntries.length;
    totalScopeDocuments = inScopeShards.reduce((sum, shard) => sum + shard.count, 0);
    const verificationStartedCoverage = coverageFor(
        session,
        'verification_started',
        FULL_SCAN_FIELDS,
        0,
        0,
        0,
        totalScopeShards,
        totalScopeDocuments,
        localIndexBytes,
        hydratedShardBytes,
        filterBytes,
        usedBodyIndex,
        false,
        scoped,
        proofLedgerEntries,
        cacheStats
    );
    emitResults('verification_started', verificationStartedCoverage, false);

    const shardFiltersBySource = new Map<string, ShardFilterMap>();
    for (const sourceManifest of verificationManifests) {
        const filter = await loadShardFilter(sourceManifest, signal, cacheStats, artifactCache);
        shardFiltersBySource.set(sourceManifest.source_id, filter);
        filterBytes += sourceManifest.artifacts.shard_filter?.bytes || 0;
    }

    let provedNoMatchShards = 0;
    let scannedShards = 0;
    let searchedDocuments = 0;
    const shardBytesByPath = new Map(inScopeShards.map(shard => [shard.path, shard.bytes]));
    for (let shardIndex = 0; shardIndex < inScopeShards.length; shardIndex += SHARD_BATCH_SIZE) {
        throwIfAborted(signal);
        const shardBatch = inScopeShards.slice(shardIndex, shardIndex + SHARD_BATCH_SIZE);
        const scanBatch = shardBatch.filter(shard => {
            const canSkip = shardFilterProvesNoMatch(shard.shard_id, shardFiltersBySource.get(String(shard.source_id || '')) || {}, matchPhrases);
            if (canSkip) {
                provedNoMatchShards += 1;
                if (proofLedgerEntries) setLedgerState(proofLedgerEntries, shard.shard_id, 'proved_no_match', 'no-false-negative shard filter proved every full-scan phrase absent');
            }
            return !canSkip;
        });
        const shardResults = await Promise.allSettled(scanBatch.map(shard => loadShard(
            shard.path,
            signal,
            cacheStats,
            shard.bytes,
            artifactCache
        )));
        const verifyMatches: RankedSitegraphDocument[] = [];
        let firstShardError: unknown = null;
        shardResults.forEach((result, batchIndex) => {
            const shard = scanBatch[batchIndex];
            if (!shard) return;
            if (result.status === 'rejected') {
                if (isAbortError(result.reason)) {
                    firstShardError = result.reason;
                    return;
                }
                firstShardError ??= result.reason;
                if (proofLedgerEntries) setLedgerState(proofLedgerEntries, shard.shard_id, 'failed', result.reason instanceof Error ? result.reason.message : 'failed to load full shard for completion proof');
                return;
            }
            const documents = result.value;
            const firstLoad = !loadedShardPaths.has(shard.path);
            loadedShardPaths.add(shard.path);
            if (firstLoad) hydratedShardBytes += shardBytesByPath.get(shard.path) || 0;
            scannedShards += 1;
            if (proofLedgerEntries) setLedgerState(proofLedgerEntries, shard.shard_id, 'scanned', 'full shard scanned for completion proof');
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

        if (firstShardError) {
            if (isAbortError(firstShardError)) throw firstShardError;
            const failedCoverage = coverageFor(
                session,
                'error',
                FULL_SCAN_FIELDS,
                provedNoMatchShards,
                scannedShards,
                searchedDocuments,
                totalScopeShards,
                totalScopeDocuments,
                localIndexBytes,
                hydratedShardBytes,
                filterBytes,
                usedBodyIndex,
                false,
                scoped,
                proofLedgerEntries,
                cacheStats
            );
            emitResults('error', failedCoverage, true);
            throw firstShardError;
        }

        const progressCoverage = coverageFor(
            session,
            'partial_verified',
            FULL_SCAN_FIELDS,
            provedNoMatchShards,
            scannedShards,
            searchedDocuments,
            totalScopeShards,
            totalScopeDocuments,
            localIndexBytes,
            hydratedShardBytes,
            filterBytes,
            usedBodyIndex,
            false,
            scoped,
            proofLedgerEntries,
            cacheStats
        );
        if (mergeRankedResults(resultMap, verifyMatches) > 0) {
            emitResults('partial_verified', progressCoverage, true);
        } else {
            emitResults('partial_verified', progressCoverage, false);
        }
        await yieldToWorker();
    }

    const ledgerComplete = proofLedgerSummary(proofLedgerEntries, {
        totalShards: totalScopeShards,
        scannedShards,
        provedNoMatchShards,
        exhaustiveComplete: true,
    }).complete;
    const completePhase = scoped ? 'scoped_exhaustive_complete' : 'global_exhaustive_complete';
    const completeCoverage = coverageFor(
        session,
        completePhase,
        FULL_SCAN_FIELDS,
        provedNoMatchShards,
        scannedShards,
        searchedDocuments,
        totalScopeShards,
        totalScopeDocuments,
        localIndexBytes,
        hydratedShardBytes,
        filterBytes,
        usedBodyIndex,
        ledgerComplete,
        scoped,
        proofLedgerEntries,
        cacheStats
    );
    emitResults(completePhase, completeCoverage, true);
};

export const recallSitegraphDocuments = async (
    session: SitegraphRoutedSession,
    query: string,
    signal: AbortSignal,
    limit = 30
): Promise<{ results: RankedSitegraphDocument[]; stats: SitegraphQueryStats }> => {
    const resultEvents: SitegraphSearchEvent[] = [];
    await searchSitegraphProgressively(session, query, signal, event => {
        if (event.results) resultEvents.push(event);
    }, { limit });
    const finalEvent = resultEvents[resultEvents.length - 1];
    if (!finalEvent?.stats) {
        throw new SearchContractError('Progressive routed search completed without a result event');
    }
    return {
        results: finalEvent.results || [],
        stats: finalEvent.stats,
    };
};
