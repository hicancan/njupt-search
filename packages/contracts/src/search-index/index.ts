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

export const SitegraphInvertedPostingSchema = z.record(z.string(), z.array(z.number()));
export const SitegraphInvertedIndexSchema = z.object({
    version: z.string().min(1),
    tokenizer: z.string().min(1),
    field_codes: z.record(z.string(), z.string()),
    tokens: z.record(z.string(), SitegraphInvertedPostingSchema)
}).passthrough();
export type SitegraphInvertedIndex = z.infer<typeof SitegraphInvertedIndexSchema>;

export const CollectionSourceSchema = z.object({
    source_id: z.string().min(1),
    source_kind: z.literal('sitegraph'),
    artifact_root: z.string().min(1),
    upstream_generated_at: z.string().min(1).nullable().optional(),
    display_name: z.string().min(1).optional()
}).passthrough();
export type CollectionSource = z.infer<typeof CollectionSourceSchema>;

export const SitegraphSearchManifestSchema = z.object({
    generated_at: z.string().min(1),
    strategy: z.literal('progressive-verifiable-static-search'),
    producer_repo: z.string().min(1),
    producer_ref: z.string().min(1),
    site_id: z.string().min(1),
    collection_id: z.literal('njupt-public'),
    sources: z.array(CollectionSourceSchema).min(1),
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
        light_first_screen: z.literal(true),
        first_screen_artifacts: z.tuple([
            z.literal('doc_meta_light'),
            z.literal('light_inverted_index'),
            z.literal('query_aliases')
        ]),
        body_index_loading: z.literal('on_deep_search'),
        full_text_loading: z.literal('progressive_candidate_hydration_then_exhaustive_full_scan'),
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
        coverage_fields: z.array(z.string()),
        proof: z.object({
            indexed_fields: z.array(z.string()),
            full_scan_fields: z.array(z.string())
        }).passthrough(),
        total_shards: z.number(),
        total_documents: z.number()
    }).passthrough(),
    verification_contract: z.object({
        shard_filter_supported: z.literal(true),
        proved_skip_supported: z.literal(true),
        scan_fallback_supported: z.literal(true),
        filter_artifact: z.literal('shard_filter'),
        catalog_artifact: z.literal('shard_catalog')
    }).passthrough(),
    artifacts: z.object({
        doc_meta_light: SitegraphArtifactSchema,
        light_inverted_index: SitegraphArtifactSchema,
        body_inverted_index: SitegraphArtifactSchema,
        section_index: SitegraphArtifactSchema,
        attachment_index: SitegraphArtifactSchema,
        external_index: SitegraphArtifactSchema,
        query_aliases: SitegraphArtifactSchema,
        shard_catalog: SitegraphArtifactSchema,
        shard_filter: SitegraphArtifactSchema,
        outcomes: SitegraphArtifactSchema,
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
        full_shards: z.array(SitegraphFullShardSchema),
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

export interface SitegraphIndexBundle {
    manifest: SitegraphSearchManifest;
    docMeta: SitegraphDocMeta[];
    lightInvertedIndex: SitegraphInvertedIndex;
    bodyInvertedIndex?: SitegraphInvertedIndex;
    shardFilter?: Record<string, {
        bitset_base64: string;
        bit_count: number;
        hash_count: number;
        token_count: number;
        sha256: string;
        hash_algorithm: string;
    }>;
    queryAliases: Record<string, unknown>;
}

export type SitegraphSearchPhase =
    | 'quick_started'
    | 'quick_results'
    | 'body_started'
    | 'body_results'
    | 'hydrate_started'
    | 'hydrate_results'
    | 'verify_started'
    | 'verify_progress'
    | 'verify_results'
    | 'exhaustive_complete'
    | 'cancelled'
    | 'error';

export interface SitegraphSearchCoverage {
    phase: SitegraphSearchPhase;
    searched_fields: string[];
    proved_no_match_shards: number;
    scanned_shards: number;
    total_shards: number;
    searched_documents: number;
    total_documents: number;
    loaded_bytes: number;
    used_body_index: boolean;
    exhaustive_complete: boolean;
}

export interface SitegraphFallbackStats {
    lightMetaFallbackDocuments: number;
    snippetFallbackResults: number;
    exhaustiveFullScanMatches: number;
}

export interface SitegraphQueryStats {
    phase: SitegraphSearchPhase;
    coverage: SitegraphSearchCoverage;
    usedBodyIndex: boolean;
    loadedShardCount: number;
    loadedShardPaths: string[];
    candidateCount: number;
    exhaustiveComplete: boolean;
    resultCount: number;
    fallbacks: SitegraphFallbackStats;
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
