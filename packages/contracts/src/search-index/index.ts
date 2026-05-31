import { z } from 'zod';
import {
    SitegraphArtifactSchema,
    SitegraphFullShardSchema
} from './schema-parts';
import type {
    SitegraphFacet,
    SitegraphDocMeta,
    SitegraphFullDocument
} from './schema-parts';

export {
    SitegraphArtifactSchema,
    SitegraphFullShardSchema
} from './schema-parts';

export type {
    SitegraphArtifact,
    SitegraphFullShard
} from './schema-parts';

export const SitegraphImpactTermSchema = z.record(z.string(), z.array(z.number()));
export const SitegraphImpactIndexSchema = z.object({
    version: z.string().min(1),
    tokenizer: z.string().min(1),
    field_codes: z.record(z.string(), z.string()),
    field_impacts: z.record(z.string(), z.number()),
    block_size: z.number(),
    scoring_model: z.literal('impact-ordered-block-max-bm25f-lite-v2'),
    terms: z.record(z.string(), SitegraphImpactTermSchema)
}).passthrough();
export type SitegraphImpactIndex = z.infer<typeof SitegraphImpactIndexSchema>;

export const SitegraphLocalIndexScopeSchema = z.object({
    index_id: z.string().min(1),
    source_id: z.string().min(1),
    facet: z.string().min(1),
    year: z.string().min(1),
    shard_ids: z.array(z.string())
}).passthrough();
export type SitegraphLocalIndexScope = z.infer<typeof SitegraphLocalIndexScopeSchema>;

export const SitegraphLocalLightIndexSchema = SitegraphImpactIndexSchema.extend({
    scope: SitegraphLocalIndexScopeSchema,
    documents: z.array(z.custom<SitegraphDocMeta>())
}).passthrough();
export type SitegraphLocalLightIndex = z.infer<typeof SitegraphLocalLightIndexSchema>;

export const SitegraphLocalBodyIndexSchema = SitegraphImpactIndexSchema.extend({
    scope: SitegraphLocalIndexScopeSchema
}).passthrough();
export type SitegraphLocalBodyIndex = z.infer<typeof SitegraphLocalBodyIndexSchema>;

export const SitegraphLocalIndexRefSchema = z.object({
    index_id: z.string().min(1),
    scope: SitegraphLocalIndexScopeSchema,
    doc_count: z.number(),
    light_index: SitegraphArtifactSchema,
    body_index: SitegraphArtifactSchema
}).passthrough();
export type SitegraphLocalIndexRef = z.infer<typeof SitegraphLocalIndexRefSchema>;

export const SitegraphSourceManifestSchema = z.object({
    version: z.string().min(1),
    source_id: z.string().min(1),
    display_name: z.string().min(1),
    domain: z.string().min(1).optional(),
    doc_count: z.number(),
    attachment_count: z.number(),
    facet_counts: z.record(z.string(), z.number()),
    record_counts: z.record(z.string(), z.number()),
    year_counts: z.record(z.string(), z.number()),
    local_indexes: z.array(SitegraphLocalIndexRefSchema),
    full_shards: z.array(SitegraphFullShardSchema),
    artifacts: z.record(z.string(), SitegraphArtifactSchema)
}).passthrough();
export type SitegraphSourceManifest = z.infer<typeof SitegraphSourceManifestSchema>;

export const SourceRegistryEntrySchema = z.object({
    source_id: z.string().min(1),
    display_name: z.string().min(1),
    owner_unit: z.string().min(1),
    domain: z.string().min(1).optional(),
    source_kind: z.literal('sitegraph'),
    authority_domains: z.array(z.string()),
    priority_by_intent: z.record(z.string(), z.string()),
    freshness_policy: z.string().min(1),
    artifact_manifest: SitegraphArtifactSchema,
    doc_count: z.number(),
    attachment_count: z.number(),
    updated_at: z.string().nullable().optional(),
    quality_status: z.string().min(1),
    coverage_status: z.string().min(1),
    facet_counts: z.record(z.string(), z.number()),
    record_counts: z.record(z.string(), z.number()),
    truth_counts: z.record(z.string(), z.number())
}).passthrough();
export type SourceRegistryEntry = z.infer<typeof SourceRegistryEntrySchema>;

export const SitegraphFilterOptionSchema = z.object({
    id: z.string(),
    label: z.string(),
    count: z.number()
});

export const SitegraphFilterOptionsSchema = z.object({
    sources: z.array(SitegraphFilterOptionSchema),
    facets: z.array(SitegraphFilterOptionSchema)
});

export const SitegraphSourceRegistrySchema = z.object({
    version: z.string().min(1),
    collection_id: z.literal('njupt-public'),
    sources: z.array(SourceRegistryEntrySchema).min(1),
    filter_options: SitegraphFilterOptionsSchema
}).passthrough();
export type SitegraphSourceRegistry = z.infer<typeof SitegraphSourceRegistrySchema>;

export const QueryDirectoryRouteSchema = z.object({
    term: z.string().nullable().optional(),
    likely_sources: z.array(z.string()),
    likely_facets: z.array(z.string()),
    likely_years: z.array(z.string()),
    likely_task_kinds: z.array(z.string()),
    expected_result_types: z.array(z.string()),
    local_index_ids: z.array(z.string()),
    sample_shard_ids: z.array(z.string()).optional(),
    candidate_shard_group_count: z.number().optional(),
    authority_priors: z.record(z.string(), z.number()),
    freshness_policy: z.string().min(1),
    matched_document_count: z.number(),
    expected_cost_bytes: z.number(),
    expected_utility_per_kb: z.number(),
    planner_features: z.record(z.string(), z.number())
}).passthrough();
export type QueryDirectoryRoute = z.infer<typeof QueryDirectoryRouteSchema>;

export const SitegraphGlobalQueryDirectorySchema = z.object({
    version: z.string().min(1),
    tokenizer: z.string().min(1),
    entry_count: z.number(),
    entries: z.record(z.string(), QueryDirectoryRouteSchema),
    intents: z.record(z.string(), QueryDirectoryRouteSchema),
    fallback: z.record(z.string(), z.unknown())
}).passthrough();
export type SitegraphGlobalQueryDirectory = z.infer<typeof SitegraphGlobalQueryDirectorySchema>;

export const CollectionSourceSchema = z.object({
    source_id: z.string().min(1),
    source_kind: z.literal('sitegraph'),
    artifact_root: z.string().min(1).optional(),
    upstream_generated_at: z.string().min(1).nullable().optional(),
    display_name: z.string().min(1).optional()
}).passthrough();
export type CollectionSource = z.infer<typeof CollectionSourceSchema>;

export const SitegraphSearchManifestSchema = z.object({
    generated_at: z.string().min(1),
    strategy: z.literal('routed-verifiable-static-search'),
    producer_repo: z.string().min(1),
    producer_ref: z.string().min(1),
    site_id: z.string().min(1),
    collection_id: z.literal('njupt-public'),
    artifact_path: z.string().min(1),
    upstream_generated_at: z.string().min(1),
    truth_counts: z.record(z.string(), z.number()),
    total_documents: z.number(),
    record_counts: z.record(z.string(), z.number()),
    facet_counts: z.record(z.string(), z.number()),
    exam_vertical_preserved: z.literal(true),
    core_search: z.object({
        algorithm: z.string().min(1),
        execution_model: z.literal('pure_frontend_worker'),
        readiness: z.literal('routed_bootstrap'),
        legacy_global_first_screen: z.literal(false),
        first_screen_artifacts: z.tuple([
            z.literal('source_registry'),
            z.literal('global_query_directory'),
            z.literal('query_aliases')
        ]),
        local_index_loading: z.literal('query_planned_on_demand'),
        body_index_loading: z.literal('query_planned_on_demand'),
        full_text_loading: z.literal('lazy_candidate_hydration_then_verified_scope_scan'),
        search_worker: z.literal(true)
    }).passthrough(),
    progressive_search: z.object({
        total_shards: z.number(),
        total_documents: z.number(),
        full_scan_supported: z.literal(true),
        progressive_events: z.literal(true),
        artifact_roles: z.array(z.string())
    }).passthrough(),
    coverage_contract: z.object({
        states: z.array(z.string()),
        coverage_fields: z.array(z.string()),
        proof: z.object({
            indexed_fields: z.array(z.string()),
            full_scan_fields: z.array(z.string()),
            complete_requires: z.array(z.string())
        }).passthrough(),
        total_shards: z.number(),
        total_documents: z.number()
    }).passthrough(),
    verification_contract: z.object({
        shard_filter_supported: z.literal(true),
        proved_skip_supported: z.literal(true),
        scan_fallback_supported: z.literal(true),
        filter_artifact_family: z.literal('shard_filters'),
        proof_catalog_artifact_family: z.literal('proof_catalogs'),
        completion_requires_ledger: z.literal(true)
    }).passthrough(),
    routing_contract: z.object({
        planner: z.string().min(1),
        directory_contains_doc_postings: z.literal(false),
        startup_loads_local_indexes: z.literal(false),
        startup_loads_full_shards: z.literal(false),
        startup_loads_global_document_metadata: z.literal(false)
    }).passthrough(),
    artifacts: z.object({
        source_registry: SitegraphArtifactSchema,
        global_query_directory: SitegraphArtifactSchema,
        query_aliases: SitegraphArtifactSchema,
        outcomes: SitegraphArtifactSchema,
        quality_report: SitegraphArtifactSchema,
        query_eval_report: SitegraphArtifactSchema,
        size_report: SitegraphArtifactSchema
    }).passthrough(),
    sitegraph: z.object({
        truth_counts: z.record(z.string(), z.number()),
        quality: z.record(z.string(), z.unknown()),
        upstream_generated_at: z.string().nullable().optional(),
        detail_page_records: z.number(),
        attachment_metadata_records: z.number(),
        direct_attachment_records: z.number(),
        external_link_records: z.number(),
        external_document_records: z.number(),
        utility_link_records: z.number(),
        attachment_policy: z.literal('metadata_only'),
        external_link_policy: z.literal('record_only'),
        source_manifests: z.record(z.string(), SitegraphArtifactSchema),
        source_manifest_summaries: z.record(z.string(), z.record(z.string(), z.number())),
        shard_strategy: z.object({
            version: z.string().min(1),
            dimensions: z.array(z.string()),
            hash_bucket_count: z.number(),
            sequential_fixed_size_shards: z.literal(false)
        }).passthrough(),
        indexes: z.record(z.string(), SitegraphArtifactSchema)
    }).passthrough()
}).passthrough();
export type SitegraphSearchManifest = z.infer<typeof SitegraphSearchManifestSchema>;

export interface SitegraphRoutedSession {
    manifest: SitegraphSearchManifest;
    sourceRegistry: SitegraphSourceRegistry;
    globalQueryDirectory: SitegraphGlobalQueryDirectory;
    queryAliases: Record<string, unknown>;
}

export type SitegraphSearchPhase =
    | 'plan_started'
    | 'local_index_started'
    | 'first_trusted_results'
    | 'body_index_started'
    | 'top_results_hydrated'
    | 'verification_started'
    | 'partial_verified'
    | 'scoped_exhaustive_complete'
    | 'global_exhaustive_complete'
    | 'cancelled'
    | 'error';

export type SitegraphProofLedgerState =
    | 'pending'
    | 'scanned'
    | 'proved_no_match'
    | 'excluded_by_filter'
    | 'excluded_by_declared_scope'
    | 'failed';

export interface SitegraphProofLedgerEntry {
    shard_id: string;
    source_id: string;
    state: SitegraphProofLedgerState;
    document_count: number;
    byte_size: number;
    path: string;
    reason: string;
    covered_fields: string[];
}

export interface SitegraphProofLedgerSummary {
    total_shards: number;
    pending_shards: number;
    scanned_shards: number;
    proved_no_match_shards: number;
    excluded_by_filter_shards: number;
    excluded_by_declared_scope_shards: number;
    failed_shards: number;
    complete: boolean;
}

export interface SitegraphSearchCoverage {
    phase: SitegraphSearchPhase;
    coverage_state: SitegraphSearchPhase;
    scope: 'global' | 'scoped';
    searched_fields: string[];
    proved_no_match_shards: number;
    scanned_shards: number;
    excluded_by_filter_shards: number;
    excluded_by_declared_scope_shards: number;
    pending_shards: number;
    failed_shards: number;
    total_shards: number;
    searched_documents: number;
    total_documents: number;
    loaded_bytes: number;
    first_screen_bytes: number;
    local_index_bytes: number;
    hydrated_shard_bytes: number;
    used_body_index: boolean;
    exhaustive_complete: boolean;
    proof_ledger: SitegraphProofLedgerSummary;
}

export interface SitegraphFallbackStats {
    localMetaFallbackDocuments: number;
    snippetFallbackResults: number;
    verifiedFullScanMatches: number;
}

export interface SitegraphQueryPlan {
    normalized_query: string;
    aliases: string[];
    intent: string;
    authority_sources: string[];
    expected_result_types: string[];
    source_ids: string[];
    local_index_ids: string[];
    verification_source_ids: string[];
    declared_completion_scope: 'global' | 'scoped';
    estimated_cost_bytes: number;
    estimated_utility_per_kb: number;
    route_decisions: Array<{
        term: string;
        local_index_count: number;
        expected_cost_bytes: number;
        expected_utility_per_kb: number;
        likely_sources: string[];
        likely_facets: string[];
    }>;
    selected_local_indexes?: Array<{
        index_id: string;
        expected_bytes: number;
        utility_score: number;
        source_id: string;
        facet: string;
        year: string;
    }>;
}

export interface SitegraphQueryStats {
    phase: SitegraphSearchPhase;
    coverage: SitegraphSearchCoverage;
    plan: SitegraphQueryPlan;
    usedBodyIndex: boolean;
    loadedLocalIndexCount: number;
    loadedLocalIndexIds: string[];
    loadedShardCount: number;
    loadedShardPaths: string[];
    candidateCount: number;
    exhaustiveComplete: boolean;
    resultCount: number;
    localIndexBytes: number;
    hydratedShardBytes: number;
    fallbacks: SitegraphFallbackStats;
    retrieval: {
        dynamicPruning: boolean;
        impactBlocksVisited: number;
        impactBlocksPruned: number;
        postingsVisited: number;
        postingsPruned: number;
        competitiveThreshold: number;
    };
}

export type SitegraphSortMode = 'relevance' | 'date_desc';

export type SitegraphDateFilter = 'all' | 'past_year' | 'past_3_years' | 'past_5_years' | 'undated';

export interface SitegraphSearchFilters {
    sourceId?: string;
    facet?: SitegraphFacet | 'all';
    dateRange?: SitegraphDateFilter;
}

export interface SitegraphFilterOption {
    id: string;
    label: string;
    count: number;
}

export interface SitegraphFilterOptions {
    sources: SitegraphFilterOption[];
    facets: Array<SitegraphFilterOption & { id: SitegraphFacet }>;
}

export interface SitegraphMatchHighlight {
    start: number;
    end: number;
    term: string;
}

export interface SitegraphMatchSnippet {
    text: string;
    field: 'title' | 'summary' | 'content' | 'attachments' | 'nav_path' | 'url';
    matched_terms: string[];
    highlights: SitegraphMatchHighlight[];
    primary_term?: string;
    fallback?: boolean;
}

export interface RankedSitegraphDocument extends SitegraphFullDocument {
    score: number;
    score_reason: string;
    match_snippet?: SitegraphMatchSnippet;
    query_stats?: SitegraphQueryStats;
}

export interface SitegraphSearchEvent {
    type: SitegraphSearchPhase;
    query: string;
    coverage: SitegraphSearchCoverage;
    results?: RankedSitegraphDocument[];
    stats?: SitegraphQueryStats;
    message?: string;
}

export interface SearchWorkerHandle {
    worker: Worker;
}
