import { describe, expect, it } from 'vitest';
import {
    buildSitegraphMatchSnippet,
    decodePackedLocalBodyIndex,
    decodePackedLocalBodyIndexTerms,
    formatResolvedSearchDate,
    parseSitegraphLocalLightIndex,
    parseSitegraphManifest,
    recallSitegraphDocuments,
    searchSitegraphProgressively,
    tokenizeSitegraphQuery
} from '../src';
import type {
    QueryDirectoryRoute,
    SitegraphDocMeta,
    SitegraphFullDocument,
    SitegraphFullShard,
    SitegraphGlobalQueryDirectory,
    SitegraphImpactIndex,
    SitegraphLocalBodyIndex,
    SitegraphLocalIndexRef,
    SitegraphLocalLightIndex,
    SitegraphProofCatalog,
    SitegraphRoutedSession,
    SitegraphSearchEvent,
    SitegraphSearchManifest,
    SitegraphSourceManifest,
    SitegraphSourceRegistry
} from '@njupt-search/contracts';

const artifact = (path: string, role: string, load = 'on_demand', count?: number) => ({
    path,
    sha256: '0123456789abcdef0123456789abcdef',
    bytes: 128,
    role,
    load,
    ...(count === undefined ? {} : { count })
});

const required = <T>(value: T | undefined, message: string): T => {
    if (value === undefined) throw new Error(message);
    return value;
};

const encodeVarint = (value: number): number[] => {
    const bytes: number[] = [];
    let current = value;
    while (current >= 0x80) {
        bytes.push((current & 0x7f) | 0x80);
        current = Math.floor(current / 128);
    }
    bytes.push(current);
    return bytes;
};

const filterTokenHashInt = (text: string, seed: number): number => {
    let value = (2166136261 ^ seed) >>> 0;
    for (const byte of new TextEncoder().encode(text)) {
        value ^= byte;
        value = Math.imul(value, 16777619) >>> 0;
    }
    return value;
};

const shardFilterBase64For = (tokens: string[], bitCount = 2048, hashCount = 1): string => {
    const bytes = new Uint8Array(Math.ceil(bitCount / 8));
    for (const token of tokens) {
        for (let seed = 0; seed < hashCount; seed += 1) {
            const bit = filterTokenHashInt(token, seed) % bitCount;
            bytes[Math.floor(bit / 8)] |= 1 << (bit % 8);
        }
    }
    return btoa(String.fromCharCode(...bytes));
};

const packedImpactIndexFixture = (payload: SitegraphImpactIndex): ArrayBuffer => {
    const encoder = new TextEncoder();
    const metadata = encoder.encode(JSON.stringify(Object.fromEntries(
        Object.entries(payload).filter(([key]) => key !== 'terms')
    )));
    const bytes: number[] = [
        ...encoder.encode('SGIXB001'),
        metadata.length & 0xff,
        (metadata.length >> 8) & 0xff,
        (metadata.length >> 16) & 0xff,
        (metadata.length >> 24) & 0xff,
        ...metadata,
        ...encodeVarint(Object.keys(payload.terms).length),
    ];
    for (const term of Object.keys(payload.terms).sort()) {
        const termBytes = encoder.encode(term);
        bytes.push(...encodeVarint(termBytes.length), ...termBytes);
        const fields = payload.terms[term];
        bytes.push(...encodeVarint(Object.keys(fields).length));
        for (const field of Object.keys(fields).sort()) {
            bytes.push(field.charCodeAt(0), ...encodeVarint(fields[field].length));
            let previous = 0;
            fields[field].forEach((docId, index) => {
                bytes.push(...encodeVarint(index === 0 ? docId : docId - previous));
                previous = docId;
            });
        }
    }
    return new Uint8Array(bytes).buffer;
};

const packedImpactIndexFixtureV2 = (payload: SitegraphImpactIndex): ArrayBuffer => {
    const encoder = new TextEncoder();
    const metadata = encoder.encode(JSON.stringify(Object.fromEntries(
        Object.entries(payload).filter(([key]) => key !== 'terms')
    )));
    const termPayloads = Object.keys(payload.terms).sort().map(term => {
        const fields = payload.terms[term];
        const payloadBytes: number[] = [...encodeVarint(Object.keys(fields).length)];
        for (const field of Object.keys(fields).sort()) {
            payloadBytes.push(field.charCodeAt(0), ...encodeVarint(fields[field].length));
            let previous = 0;
            fields[field].forEach((docId, index) => {
                payloadBytes.push(...encodeVarint(index === 0 ? docId : docId - previous));
                previous = docId;
            });
        }
        return { term, termBytes: encoder.encode(term), payloadBytes };
    });
    const bytes: number[] = [
        ...encoder.encode('SGIXB002'),
        metadata.length & 0xff,
        (metadata.length >> 8) & 0xff,
        (metadata.length >> 16) & 0xff,
        (metadata.length >> 24) & 0xff,
        ...metadata,
        ...encodeVarint(termPayloads.length),
    ];
    for (const item of termPayloads) {
        bytes.push(...encodeVarint(item.termBytes.length), ...item.termBytes, ...encodeVarint(item.payloadBytes.length));
    }
    for (const item of termPayloads) {
        bytes.push(...item.payloadBytes);
    }
    return new Uint8Array(bytes).buffer;
};

const fullShard = (prefix: string, count: number, facet = 'policy'): SitegraphFullShard => ({
    shard_id: `jwc__${facet}__detail__2026__rules__b0__${prefix}`,
    path: `${prefix}/full-shard.json`,
    sha256: '0123456789abcdef0123456789abcdef',
    bytes: 256,
    count,
    contains: 'full_documents',
    source_id: 'jwc',
    facet_range: [facet],
    record_type_range: ['detail'],
    section_range: ['jwc_rules_root'],
    year_range: ['2026'],
    hash_bucket: 'b0',
    filter_token_count: 4,
    filter_sha256: '0123456789abcdef'
});

const makeDocument = (overrides: Partial<SitegraphFullDocument> = {}): SitegraphFullDocument => {
    const shard = overrides.shard ?? { shard_id: 'jwc__policy__detail__2026__rules__b0', path: 'fixture/full-shard.json' };
    return {
        doc_index: 0,
        id: 'jwc-detail-1',
        record_type: 'detail',
        page_type: 'detail_article_page',
        facet: 'policy',
        title: '南京邮电大学本科生转专业管理办法',
        url: 'https://jwc.njupt.edu.cn/1/page.htm',
        source_id: 'jwc',
        source: '本科生院 / 教务处',
        source_domain: 'jwc.njupt.edu.cn',
        section_id: 'jwc_rules_root',
        section: '规章制度',
        nav_path: ['规章制度'],
        nav_path_text: '规章制度',
        canonical_title: '南京邮电大学本科生转专业管理办法',
        published_at: '2026-05-20',
        updated_at: null,
        recorded_at: null,
        version_date: '2026-05-20',
        date_kind: 'published',
        date_confidence: 'source_published',
        academic_year: null,
        term: null,
        task_kind: 'academic_policy',
        authority_profile: 'jwc_academic',
        dedupe_key: 'jwc:detail:fixture',
        publisher: '综合科',
        summary: '转专业政策摘要',
        attachment_count: 1,
        hash: 'hash',
        tags: ['policy'],
        collection_method: 'search_record',
        provenance: { site_id: 'jwc', section_id: 'jwc_rules_root', nav_path: ['规章制度'], outcome: 'search_record' },
        shard,
        content: '学生申请转专业需要符合管理办法。',
        attachments: [{
            attachment_id: 'att-1',
            name: '转专业申请表.doc',
            url: 'https://jwc.njupt.edu.cn/a.doc',
            extension: 'doc',
            parent_url: 'https://jwc.njupt.edu.cn/1/page.htm',
            parent_doc_id: 'jwc-detail-1',
            section_id: 'jwc_rules_root',
            section: '规章制度',
            nav_path: ['规章制度'],
            metadata_only: true,
            evidence_level: 'filename_only',
            available_evidence: ['metadata_only', 'filename_only'],
            unavailable_evidence: ['text_extracted', 'snippet', 'full_content'],
            text_extracted: false,
            snippet_available: false,
            full_content_available: false,
            coverage_note: 'Only authoritative attachment metadata and filename are indexed; binary attachment content is not extracted.',
            position: 1
        }],
        ...overrides
    };
};

const docMetaFrom = (document: SitegraphFullDocument): SitegraphDocMeta => ({
    doc_index: document.doc_index,
    id: document.id,
    record_type: document.record_type,
    facet: document.facet,
    title: document.title,
    url: document.url,
    source_id: document.source_id,
    source: document.source,
    source_domain: document.source_domain,
    section_id: document.section_id,
    section: document.section,
    nav_path: document.nav_path,
    nav_path_text: document.nav_path_text,
    canonical_title: document.canonical_title,
    published_at: document.published_at,
    updated_at: document.updated_at,
    recorded_at: document.recorded_at,
    version_date: document.version_date,
    date_kind: document.date_kind,
    date_confidence: document.date_confidence,
    task_kind: document.task_kind,
    authority_profile: document.authority_profile,
    dedupe_key: document.dedupe_key,
    attachment_count: document.attachment_count,
    collection_method: document.collection_method,
    shard: document.shard
});

const route = (
    term: string,
    localIndexIds: string[],
    likelyFacets = ['policy'],
    expectedResultTypes = ['detail']
): QueryDirectoryRoute => ({
    term,
    likely_sources: ['jwc'],
    likely_facets: likelyFacets,
    likely_years: ['2026'],
    likely_task_kinds: ['academic_policy'],
    expected_result_types: expectedResultTypes,
    local_index_ids: localIndexIds,
    sample_shard_ids: [],
    candidate_shard_group_count: 1,
    authority_priors: { jwc: 1 },
    freshness_policy: 'prefer_recent_for_current_notice_intents',
    matched_document_count: 1,
    expected_cost_bytes: 256,
    expected_utility_per_kb: 4,
    planner_features: {
        source_entropy: 1,
        facet_entropy: 1,
        year_entropy: 1,
        local_index_count: localIndexIds.length
    }
});

const impactTerms = (postings: Record<string, Record<string, number[]>>): SitegraphImpactIndex['terms'] => {
    return postings;
};

interface RoutedFixture {
    session: SitegraphRoutedSession;
    sourceManifest: SitegraphSourceManifest;
    proofCatalog: SitegraphProofCatalog;
    localLightIndex: SitegraphLocalLightIndex;
    localBodyIndex: SitegraphLocalBodyIndex;
    shardFilter: Record<string, unknown>;
    documents: SitegraphFullDocument[];
}

const makeRoutedFixture = (
    prefix: string,
    documents: SitegraphFullDocument[],
    options: {
        queryTerms?: string[];
        lightTerms?: SitegraphImpactIndex['terms'];
        bodyTerms?: SitegraphImpactIndex['terms'];
        queryAliases?: Record<string, unknown>;
        routeEntries?: Record<string, QueryDirectoryRoute>;
        intentRoutes?: Record<string, QueryDirectoryRoute>;
        facet?: string;
        filterBase64?: string;
        filterBitCount?: number;
        filterHashCount?: number;
    } = {}
): RoutedFixture => {
    const shard = fullShard(prefix, documents.length, options.facet || documents[0]?.facet || 'policy');
    const localIndexId = `jwc__${options.facet || documents[0]?.facet || 'policy'}__2026__${prefix}`;
    const scope = {
        index_id: localIndexId,
        source_id: 'jwc',
        facet: options.facet || documents[0]?.facet || 'policy',
        year: '2026',
        shard_ids: [shard.shard_id]
    };
    const localRef: SitegraphLocalIndexRef = {
        index_id: localIndexId,
        scope,
        doc_count: documents.length,
        shards: [{
            shard_id: shard.shard_id,
            path: shard.path,
            bytes: shard.bytes,
            count: shard.count
        }],
        light_index_meta: artifact(`${prefix}/local-impact-light-meta.json`, 'local_impact_light_index_meta', 'query_planned', documents.length),
        light_index_packed: artifact(`${prefix}/local-impact-light.bin`, 'local_impact_light_index_packed', 'query_planned', documents.length),
        body_index_packed: artifact(`${prefix}/local-impact-body.bin`, 'local_impact_body_index_packed', 'query_planned', documents.length)
    };
    const manifest: SitegraphSearchManifest = {
        generated_at: '2026-05-30T00:00:00Z',
        strategy: 'routed-verifiable-static-search',
        producer_repo: 'hicancan/njupt-search',
        producer_ref: 'fixture',
        site_id: 'njupt-public',
        collection_id: 'njupt-public',
        artifact_path: 'generated/collections/njupt-public',
        upstream_generated_at: '2026-05-30T00:00:00Z',
        truth_counts: { detail_pages: documents.length, attachments: 1, external_links: 0, edges: 0 },
        total_documents: documents.length,
        record_counts: { detail: documents.length },
        facet_counts: { [scope.facet]: documents.length },
        exam_vertical_preserved: true,
        core_search: {
            algorithm: 'routed fixture',
            execution_model: 'pure_frontend_worker',
            readiness: 'routed_bootstrap',
            legacy_global_first_screen: false,
            first_screen_artifacts: ['source_registry', 'global_query_directory', 'query_aliases'],
            local_index_loading: 'query_planned_on_demand',
            body_index_loading: 'query_planned_on_demand',
            full_text_loading: 'lazy_candidate_hydration_then_verified_scope_scan',
            search_worker: true
        },
        progressive_search: {
            total_shards: 1,
            total_documents: documents.length,
            full_scan_supported: true,
            progressive_events: true,
            artifact_roles: ['source_registry', 'global_query_directory', 'local_impact_light_index_meta', 'local_impact_light_index_packed', 'local_impact_body_index_packed', 'proof_catalog', 'full_shards']
        },
        coverage_contract: {
            states: ['plan_started', 'local_index_started', 'first_trusted_results', 'body_index_started', 'top_results_hydrated', 'verification_started', 'partial_verified', 'global_exhaustive_complete'],
            coverage_fields: ['title', 'section', 'nav_path', 'summary', 'content', 'attachments', 'url'],
            attachment_evidence_levels: ['metadata_only', 'filename_only', 'text_extracted', 'snippet', 'full_content'],
            proof: {
                indexed_fields: ['title', 'section', 'nav_path', 'attachments'],
                full_scan_fields: ['title', 'section', 'nav_path', 'summary', 'content', 'attachments', 'url'],
                complete_requires: ['proof_ledger', 'shard_filter', 'full_shard_scan_or_proof'],
                ledger_states: ['pending', 'scanned', 'proved_no_match', 'excluded_by_filter', 'excluded_by_declared_scope', 'failed']
            },
            total_shards: 1,
            total_documents: documents.length
        },
        verification_contract: {
            shard_filter_supported: true,
            proved_skip_supported: true,
            scan_fallback_supported: true,
            filter_artifact_family: 'shard_filters',
            proof_catalog_artifact_family: 'proof_catalogs',
            completion_requires_ledger: true
        },
        routing_contract: {
            planner: 'cost_authority_proof_ledger_planner_v2',
            directory_contains_doc_postings: false,
            startup_loads_local_indexes: false,
            startup_loads_full_shards: false,
            startup_loads_global_document_metadata: false
        },
        artifacts: {
            source_registry: artifact(`${prefix}/source-registry.json`, 'source_registry', 'bootstrap', 1),
            global_query_directory: artifact(`${prefix}/global-query-directory.json`, 'global_query_directory', 'bootstrap', 1),
            query_aliases: artifact(`${prefix}/query-aliases.json`, 'query_aliases', 'bootstrap', 1),
            outcomes: artifact(`${prefix}/outcomes.json`, 'outcomes', 'audit'),
            quality_report: artifact(`${prefix}/quality-report.json`, 'quality_report', 'audit'),
            query_eval_report: artifact(`${prefix}/query-eval-report.json`, 'query_eval_report', 'audit'),
            size_report: artifact(`${prefix}/size-report.json`, 'size_report', 'audit')
        },
        sitegraph: {
            truth_counts: { detail_pages: documents.length, attachments: 1, external_links: 0, edges: 0 },
            quality: { errors: 0 },
            upstream_generated_at: '2026-05-30T00:00:00Z',
            detail_page_records: documents.length,
            attachment_metadata_records: 1,
            direct_attachment_records: 0,
            external_link_records: 0,
            external_document_records: 0,
            utility_link_records: 0,
            attachment_policy: 'metadata_only',
            attachment_evidence_policy: 'metadata_and_filename_only_no_extracted_attachment_content',
            attachment_evidence_coverage: {
                total: 1,
                metadata_only: 1,
                filename_only: 1,
                text_extracted: 0,
                snippet: 0,
                full_content: 0
            },
            external_link_policy: 'record_only',
            source_manifests: {
                jwc: artifact(`${prefix}/source-manifest.json`, 'source_manifest', 'query_planned', documents.length)
            },
            source_manifest_summaries: {
                jwc: { doc_count: documents.length, shard_count: 1, local_index_count: 1 }
            },
            shard_strategy: {
                version: 'source-facet-record-year-section-hash-routed',
                dimensions: ['source_id', 'facet', 'record_type', 'year', 'top_nav_section', 'hash_bucket'],
                hash_bucket_count: 4,
                sequential_fixed_size_shards: false
            },
            indexes: {}
        }
    };
    manifest.sitegraph.indexes = manifest.artifacts;

    const sourceRegistry: SitegraphSourceRegistry = {
        version: 'sitegraph-source-registry-v1',
        collection_id: 'njupt-public',
        sources: [{
            source_id: 'jwc',
            display_name: '本科生院 / 教务处',
            owner_unit: '本科生院 / 教务处',
            domain: 'jwc.njupt.edu.cn',
            source_kind: 'sitegraph',
            authority_domains: ['academic', 'forms'],
            priority_by_intent: { academic_policy: 'high', form_download: 'high', academic_calendar: 'high' },
            freshness_policy: 'current_term_or_latest_notice',
            artifact_manifest: required(manifest.sitegraph.source_manifests.jwc, 'expected jwc source manifest artifact'),
            doc_count: documents.length,
            attachment_count: 1,
            attachment_evidence_coverage: {
                total: 1,
                metadata_only: 1,
                filename_only: 1,
                text_extracted: 0,
                snippet: 0,
                full_content: 0
            },
            updated_at: '2026-05-30T00:00:00Z',
            quality_status: 'ok',
            coverage_status: 'audited',
            facet_counts: { [scope.facet]: documents.length },
            record_counts: { detail: documents.length },
            truth_counts: { detail_pages: documents.length, attachments: 1, external_links: 0, edges: 0 }
        }],
        filter_options: {
            sources: [{ id: 'jwc', label: '本科生院 / 教务处', count: documents.length }],
            facets: [{ id: scope.facet, label: scope.facet, count: documents.length }]
        }
    };
    const defaultRoute = route(options.queryTerms?.[0] || documents[0]?.title || '转专业', [localIndexId], [scope.facet]);
    const entries = options.routeEntries || Object.fromEntries((options.queryTerms || ['转专业']).map(term => [term, route(term, [localIndexId], [scope.facet])]));
    const globalQueryDirectory: SitegraphGlobalQueryDirectory = {
        version: 'sitegraph-global-query-directory-v1',
        tokenizer: 'sitegraph-tokenizer-v1',
        entry_count: Object.keys(entries).length,
        entries,
        intents: options.intentRoutes || { academic_policy: defaultRoute, form_download: defaultRoute, academic_calendar: defaultRoute },
        fallback: {
            mode: 'load_authority_source_manifests_then_verify_in_scope_shards',
            false_negative_policy: 'verify with shard scan or safe filter proof'
        }
    };
    const sourceManifest: SitegraphSourceManifest = {
        version: 'sitegraph-source-manifest-v1',
        source_id: 'jwc',
        display_name: '本科生院 / 教务处',
        domain: 'jwc.njupt.edu.cn',
        doc_count: documents.length,
            attachment_count: 1,
            attachment_evidence_coverage: {
                total: 1,
                metadata_only: 1,
                filename_only: 1,
                text_extracted: 0,
                snippet: 0,
                full_content: 0
            },
            facet_counts: { [scope.facet]: documents.length },
        record_counts: { detail: documents.length },
        year_counts: { '2026': documents.length },
        local_indexes: [localRef],
        full_shards: [shard],
        artifacts: {
            proof_catalog: artifact(`${prefix}/proof-catalog.json`, 'proof_catalog', 'verify', 1),
            shard_filter: artifact(`${prefix}/shard-filter.json`, 'shard_filter', 'verify', 1),
            attachment_meta_index: artifact(`${prefix}/attachment-meta.json`, 'attachment_meta_index', 'on_demand', 1),
            attachment_filename_index: artifact(`${prefix}/attachment-filename.json`, 'attachment_filename_index', 'on_demand', 1),
            attachment_text_shards: artifact(`${prefix}/attachment-text-manifest.json`, 'attachment_text_shards', 'future', 0),
            section_index: artifact(`${prefix}/section-index.json`, 'section_index', 'on_demand', 1),
            external_index: artifact(`${prefix}/external-index.json`, 'external_index', 'on_demand', 0)
        }
    };
    const proofCatalog: SitegraphProofCatalog = {
        version: 'sitegraph-proof-ledger-catalog-v2',
        source_id: 'jwc',
        state_model: ['pending', 'scanned', 'proved_no_match', 'excluded_by_filter', 'excluded_by_declared_scope', 'failed'],
        complete_requires_no_states: ['pending', 'failed'],
        covered_fields: ['title', 'section', 'nav_path', 'summary', 'content', 'attachments', 'url'],
        shards: [{
            shard_id: shard.shard_id,
            source_id: 'jwc',
            path: shard.path,
            sha256: shard.sha256,
            bytes: shard.bytes,
            document_count: shard.count,
            scope: {
                facets: shard.facet_range,
                record_types: shard.record_type_range,
                sections: shard.section_range,
                years: shard.year_range,
                hash_bucket: shard.hash_bucket
            },
            filter_contract: {
                artifact_family: 'shard_filters',
                hash_algorithm: 'bloom-fnv1a32-utf8',
                false_negative: false,
                filter_sha256: shard.filter_sha256,
                filter_token_count: shard.filter_token_count
            }
        }]
    };
    const localLightIndex: SitegraphLocalLightIndex = {
        version: 'sitegraph-local-light-impact-v2',
        tokenizer: 'test',
        field_codes: { title: 't', attachment: 'a', section: 's' },
        field_impacts: { t: 120, a: 95, s: 60 },
        block_size: 32,
        scoring_model: 'impact-ordered-block-max-bm25f-lite-v2',
        scope,
        documents: documents.map(document => docMetaFrom({ ...document, shard: { shard_id: shard.shard_id, path: shard.path } })),
        terms: options.lightTerms || impactTerms({ 转专业: { t: [0] }, 申请表: { a: [0] } })
    };
    const localBodyIndex: SitegraphLocalBodyIndex = {
        version: 'sitegraph-local-body-impact-v2',
        tokenizer: 'test',
        field_codes: { summary: 'm', content: 'c' },
        field_impacts: { m: 16, c: 10 },
        block_size: 32,
        scoring_model: 'impact-ordered-block-max-bm25f-lite-v2',
        scope,
        terms: options.bodyTerms || impactTerms({ 转专业: { c: [0] }, 申请表: { c: [0] } })
    };
    const shardFilter = {
        [shard.shard_id]: {
            bitset_base64: options.filterBase64 || '/w==',
            bit_count: options.filterBitCount || 8,
            hash_count: options.filterHashCount || 1,
            token_count: 4,
            sha256: '0123456789abcdef0123456789abcdef',
            hash_algorithm: 'bloom-fnv1a32-utf8'
        }
    };

    return {
        session: {
            manifest,
            sourceRegistry,
            globalQueryDirectory,
            queryAliases: options.queryAliases || {}
        },
        sourceManifest,
        proofCatalog,
        localLightIndex,
        localBodyIndex,
        shardFilter,
        documents: documents.map(document => ({ ...document, shard: { shard_id: shard.shard_id, path: shard.path } }))
    };
};

const withMockFetch = async (
    fixture: RoutedFixture,
    callback: () => Promise<void>,
    options: { failPaths?: string[] } = {}
): Promise<void> => {
    const originalFetch = globalThis.fetch;
    const manifestArtifact = required(fixture.session.sourceRegistry.sources[0], 'expected source registry entry').artifact_manifest;
    const localRef = required(fixture.sourceManifest.local_indexes[0], 'expected local index ref');
    const sourceManifest = fixture.sourceManifest;
    const shard = required(sourceManifest.full_shards[0], 'expected full shard');
    const shardFilterArtifact = required(sourceManifest.artifacts.shard_filter, 'expected shard filter artifact');
    const proofCatalogArtifact = required(sourceManifest.artifacts.proof_catalog, 'expected proof catalog artifact');
    const responses = new Map<string, unknown>([
        [manifestArtifact.path, sourceManifest],
        [proofCatalogArtifact.path, fixture.proofCatalog],
        [required(localRef.light_index_meta, 'expected light index metadata artifact').path, Object.fromEntries(Object.entries(fixture.localLightIndex).filter(([key]) => key !== 'terms'))],
        [required(localRef.light_index_packed, 'expected packed light index artifact').path, packedImpactIndexFixture(Object.fromEntries(Object.entries(fixture.localLightIndex).filter(([key]) => key !== 'documents')) as SitegraphImpactIndex)],
        [required(localRef.body_index_packed, 'expected packed body index artifact').path, packedImpactIndexFixtureV2(fixture.localBodyIndex)],
        [shardFilterArtifact.path, fixture.shardFilter],
        [shard.path, fixture.documents]
    ]);
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.signal?.aborted) {
            throw new DOMException('Search cancelled', 'AbortError');
        }
        const url = String(input).replace(/^\//, '');
        if ((options.failPaths || []).some(path => url.endsWith(path))) {
            return new Response('fixture failure', { status: 503 });
        }
        const match = Array.from(responses.entries()).find(([path]) => url.endsWith(path));
        if (!match) return new Response(JSON.stringify({}), { status: 404 });
        return match[1] instanceof ArrayBuffer
            ? new Response(match[1])
            : new Response(JSON.stringify(match[1]));
    }) as typeof fetch;
    try {
        await callback();
    } finally {
        globalThis.fetch = originalFetch;
    }
};

describe('sitegraph search contract', () => {
    it('decodes packed local body impact indexes', () => {
        const payload: SitegraphLocalBodyIndex = {
            version: 'sitegraph-local-body-impact-v2',
            tokenizer: 'nfkc-lower-cjk-ngram-code',
            field_codes: { summary: 'm', content: 'c' },
            field_impacts: { m: 16, c: 10 },
            block_size: 32,
            scoring_model: 'impact-ordered-block-max-bm25f-lite-v2',
            scope: {
                index_id: 'jwc__exam__2026',
                source_id: 'jwc',
                facet: 'exam',
                year: '2026',
                shard_ids: ['s1', 's2'],
            },
            terms: {
                校历: { m: [3, 9, 14], c: [4] },
                考试: { c: [1, 2, 99] },
            },
        };

        expect(decodePackedLocalBodyIndex(packedImpactIndexFixture(payload), 'fixture.bin')).toEqual(payload);
        expect(decodePackedLocalBodyIndex(packedImpactIndexFixtureV2(payload), 'fixture-v2.bin')).toEqual(payload);
        expect(decodePackedLocalBodyIndexTerms(packedImpactIndexFixtureV2(payload), ['考试'], 'fixture-v2.bin')).toEqual({
            ...payload,
            terms: {
                考试: { c: [1, 2, 99] },
            },
        });
    });

    it('tokenizes Chinese, ASCII, and aliases for recall', () => {
        const tokens = tokenizeSitegraphQuery('转专业 B250403.xlsx', {
            转专业: { aliases: ['专业变更'] }
        });

        expect(tokens).toEqual(expect.arrayContaining(['转专业', '专业变更', 'b250403.xlsx']));
        expect(tokens[0]?.length).toBeGreaterThanOrEqual(tokens[tokens.length - 1]?.length ?? 0);
    });

    it('keeps the primary body hit visible near the start of mobile-safe snippets', () => {
        const terms = tokenizeSitegraphQuery('四六级', {
            四六级: { aliases: ['四级', '六级'] }
        });
        const snippet = buildSitegraphMatchSnippet({
            ...makeDocument(),
            title: '关于英国伦敦大学学院2026年暑期访学项目报名的通知',
            summary: '暑期访学项目报名通知。',
            content: '自习等多种方式进行。项目时间：8月3日-8月21日 项目收获：官方证书、学习报告 申请要求：托福 76、雅思6、四级425、六级400；无以上语言成绩者可内测，测试通过替代语言成绩获得申请资格。',
            attachments: []
        }, '四六级', terms);

        expect(snippet?.text).toContain('六级400');
        expect(snippet?.matched_terms).toEqual(expect.arrayContaining(['四级', '六级']));
        expect(snippet?.fallback).toBeFalsy();
        const firstHighlight = snippet?.highlights[0];
        expect(firstHighlight?.term).toBe('四级');
        expect(firstHighlight?.start).toBeLessThanOrEqual(32);
        const visibleLead = snippet?.text.slice(0, firstHighlight?.end ?? 0);
        expect(visibleLead).toContain('四级');
    });

    it('marks snippets that could not place a query hit as fallback snippets', () => {
        const snippet = buildSitegraphMatchSnippet({
            ...makeDocument(),
            content: '这是一段可显示的正文，但它不包含当前查询词。'
        }, '不存在的词', ['不存在的词']);

        expect(snippet?.fallback).toBe(true);
        expect(snippet?.highlights).toEqual([]);
        expect(snippet?.matched_terms).toEqual([]);
    });

    it('rejects legacy startup artifacts and full fields in local metadata', () => {
        const fixture = makeRoutedFixture('legacy-reject', [makeDocument()], { queryTerms: ['转专业'] });
        expect(() => parseSitegraphManifest({
            ...fixture.session.manifest,
            artifacts: {
                ...fixture.session.manifest.artifacts,
                doc_meta_light: artifact('legacy/doc_meta_light.json', 'doc_meta_light', 'initial')
            }
        })).toThrow(/legacy global artifact/);

        expect(() => parseSitegraphLocalLightIndex({
            ...fixture.localLightIndex,
            documents: [{ ...fixture.localLightIndex.documents[0], content: 'must stay in full shards' }]
        }, 'fixture-local-light')).toThrow(/local index metadata must not contain content/);
    });

    it('ranks attachment matches after loading routed local indexes and candidate shards', async () => {
        const document = makeDocument();
        const fixture = makeRoutedFixture('rank-attachment', [document], {
            queryTerms: ['转专业申请表'],
            lightTerms: impactTerms({ 转专业: { t: [0] }, 申请表: { a: [0] }, 转专业申请表: { a: [0] } }),
            bodyTerms: impactTerms({ 转专业: { c: [0] }, 申请表: { c: [0] } }),
            queryAliases: { 转专业申请表: { aliases: ['专业变更申请表'] } }
        });

        await withMockFetch(fixture, async () => {
            const { results, stats } = await recallSitegraphDocuments(fixture.session, '转专业申请表', new AbortController().signal);
            expect(results[0]?.id).toBe('jwc-detail-1');
            expect(results[0]?.score_reason).toContain('附件名命中');
            expect(results[0]?.match_snippet?.field).toBe('attachments');
            expect(results[0]?.match_snippet?.evidence_level).toBe('filename_only');
            expect(results[0]?.match_snippet?.text).toContain('转专业申请表.doc');
            expect(stats.loadedLocalIndexIds).toEqual([required(fixture.sourceManifest.local_indexes[0], 'expected local index ref').index_id]);
            expect(stats.loadedShardPaths).toEqual([required(fixture.sourceManifest.full_shards[0], 'expected full shard').path]);
            expect(stats.coverage.coverage_state).toBe('global_exhaustive_complete');
            expect(stats.coverage.exhaustive_complete).toBe(true);
        });
    });

    it('reports fallback and verification telemetry in routed query stats', async () => {
        const fixture = makeRoutedFixture('fallback-telemetry', [makeDocument()], {
            queryTerms: ['南京邮电大学本科生转专业管理办法'],
            lightTerms: {},
            bodyTerms: {}
        });

        await withMockFetch(fixture, async () => {
            const { results, stats } = await recallSitegraphDocuments(
                fixture.session,
                '南京邮电大学本科生转专业管理办法',
                new AbortController().signal
            );
            expect(results[0]?.id).toBe('jwc-detail-1');
            expect(stats.fallbacks.localMetaFallbackDocuments).toBe(1);
            expect(stats.fallbacks.verifiedFullScanMatches).toBe(1);
            expect(results[0]?.query_stats?.fallbacks.localMetaFallbackDocuments).toBe(1);
        });
    });

    it('uses version and recorded dates for display and scoped date sorting', async () => {
        const oldNotice = makeDocument({
            doc_index: 0,
            id: 'old-notice',
            facet: 'notice_article',
            title: '2024年推免工作方案',
            canonical_title: '2024年推免工作方案',
            published_at: '2024-09-07',
            version_date: null,
            date_kind: 'published',
            summary: '推免工作方案',
            content: '2024年推免工作方案。',
            attachments: [],
            attachment_count: 0
        });
        const versionedDownload = makeDocument({
            doc_index: 1,
            id: 'versioned-download',
            facet: 'download',
            title: '南京邮电大学学生一般事务申请表 2026-04-16',
            canonical_title: '南京邮电大学学生一般事务申请表 2026-04-16',
            published_at: null,
            version_date: '2026-04-16',
            date_kind: 'version',
            date_confidence: 'title_or_attachment',
            summary: '附件元数据：南京邮电大学学生一般事务申请表 2026-04-16。来源栏目：推免生。',
            content: '附件元数据命中推免生栏目。',
            collection_method: 'attachment_metadata_only'
        });
        const docs = [oldNotice, versionedDownload];
        const fixture = makeRoutedFixture('date-filter', docs, {
            queryTerms: ['推免'],
            facet: 'download',
            lightTerms: impactTerms({ 推免: { t: [0, 1] } }),
            bodyTerms: impactTerms({ 推免: { c: [0, 1] } })
        });

        await withMockFetch(fixture, async () => {
            const events: SitegraphSearchEvent[] = [];
            await searchSitegraphProgressively(fixture.session, '推免', new AbortController().signal, event => events.push(event), {
                limit: 10,
                sortMode: 'date_desc',
                filters: { sourceId: 'jwc', facet: 'download', dateRange: 'past_year' },
                now: new Date('2026-05-29T00:00:00+08:00').getTime()
            });
            const complete = events.at(-1);
            expect(complete?.type).toBe('scoped_exhaustive_complete');
            expect(complete?.results?.map(result => result.id)).toEqual(['versioned-download']);
            expect(formatResolvedSearchDate(versionedDownload)).toBe('版本日期 2026/04/16');
            expect(formatResolvedSearchDate({
                ...versionedDownload,
                published_at: null,
                version_date: null,
                recorded_at: '2026-05-01'
            })).toBe('收录日期 2026/05/01');
        });
    });

    it('uses alias phrases for candidate recall without counting weak phrase misses as results', async () => {
        const calendarDocument = makeDocument({
            doc_index: 0,
            id: 'calendar',
            facet: 'notice_article',
            title: '2025-2026学年校历',
            canonical_title: '2025-2026学年校历',
            section: '通知公告',
            nav_path: ['通知公告'],
            nav_path_text: '通知公告',
            summary: '2025-2026学年校历',
            content: '学校发布2025-2026学年校历。',
            task_kind: 'academic_calendar',
            attachments: [],
            attachment_count: 0
        });
        const weakAliasDocument = makeDocument({
            doc_index: 1,
            id: 'weak-alias',
            facet: 'notice_article',
            title: '2025-2026学年第二学期学生选课通知',
            canonical_title: '2025-2026学年第二学期学生选课通知',
            section: '通知公告',
            nav_path: ['通知公告'],
            nav_path_text: '通知公告',
            summary: '2025-2026学年第二学期选课安排。',
            content: '学生选课通知，不包含目标完整短语。',
            task_kind: 'course_grade_credit',
            attachments: [],
            attachment_count: 0
        });
        const fixture = makeRoutedFixture('alias-recall', [calendarDocument, weakAliasDocument], {
            queryTerms: ['校历'],
            facet: 'notice_article',
            lightTerms: impactTerms({
                校历: { t: [0] },
                '2025-2026': { t: [0, 1] },
                学年: { t: [0, 1] }
            }),
            bodyTerms: impactTerms({
                校历: { c: [0] },
                '2025-2026': { c: [0, 1] },
                学年: { c: [0, 1] }
            }),
            queryAliases: { 校历: { aliases: ['2025-2026学年校历'] } }
        });

        await withMockFetch(fixture, async () => {
            const { results, stats } = await recallSitegraphDocuments(fixture.session, '校历', new AbortController().signal, 10);
            expect(results.map(result => result.id)).toEqual(['calendar']);
            expect(stats.resultCount).toBe(1);
        });
    });

    it('emits routed progressive phases with exhaustive coverage', async () => {
        const fixture = makeRoutedFixture('progressive-phases', [makeDocument()], {
            queryTerms: ['转专业申请'],
            lightTerms: impactTerms({ 转专业: { t: [0] } }),
            bodyTerms: impactTerms({ 申请: { c: [0] } })
        });

        await withMockFetch(fixture, async () => {
            const events: SitegraphSearchEvent[] = [];
            await searchSitegraphProgressively(fixture.session, '转专业申请', new AbortController().signal, event => events.push(event), { limit: 5 });
            expect(events.map(event => event.type)).toEqual(expect.arrayContaining([
                'plan_started',
                'local_index_started',
                'first_trusted_results',
                'body_index_started',
                'top_results_hydrated',
                'verification_started',
                'partial_verified',
                'global_exhaustive_complete'
            ]));
            const complete = events.at(-1);
            expect(complete?.type).toBe('global_exhaustive_complete');
            expect(complete?.coverage.exhaustive_complete).toBe(true);
            expect(complete?.coverage.scanned_shards).toBe(1);
            expect(complete?.coverage.proved_no_match_shards).toBe(0);
            expect(complete?.coverage.searched_documents).toBe(1);
            expect(complete?.results?.[0]?.id).toBe('jwc-detail-1');
        });
    });

    it('reports warm immutable artifact cache hits and cache-aware local index cost', async () => {
        const fixture = makeRoutedFixture('cache-warm', [makeDocument()], {
            queryTerms: ['转专业申请'],
            lightTerms: impactTerms({ 转专业: { t: [0] } }),
            bodyTerms: impactTerms({ 申请: { c: [0] } })
        });

        await withMockFetch(fixture, async () => {
            const first = await recallSitegraphDocuments(fixture.session, '转专业申请', new AbortController().signal, 5);
            expect(first.stats.cache.artifact_misses).toBeGreaterThan(0);
            expect(first.stats.cache.uncached_bytes).toBeGreaterThan(0);
            expect(first.stats.coverage.uncached_loaded_bytes).toBe(first.stats.cache.uncached_bytes);
            expect(first.stats.plan.selected_local_indexes?.[0]?.expected_uncached_bytes).toBeGreaterThan(0);

            const second = await recallSitegraphDocuments(fixture.session, '转专业申请', new AbortController().signal, 5);
            expect(second.stats.cache.artifact_hits).toBeGreaterThan(0);
            expect(second.stats.cache.artifact_misses).toBe(0);
            expect(second.stats.cache.uncached_bytes).toBe(0);
            expect(second.stats.cache.cached_bytes).toBeGreaterThan(0);
            expect(second.stats.coverage.uncached_loaded_bytes).toBe(0);
            expect(second.stats.plan.selected_local_indexes?.[0]?.cache_state).toBe('warm');
            expect(second.stats.plan.selected_local_indexes?.[0]?.expected_uncached_bytes).toBe(0);
        });
    });

    it('treats changed content-hash artifact paths as cache misses', async () => {
        const firstFixture = makeRoutedFixture('cache-invalidate-a', [makeDocument()], {
            queryTerms: ['转专业申请'],
            lightTerms: impactTerms({ 转专业: { t: [0] } }),
            bodyTerms: impactTerms({ 申请: { c: [0] } })
        });
        const changedFixture = makeRoutedFixture('cache-invalidate-b', [makeDocument()], {
            queryTerms: ['转专业申请'],
            lightTerms: impactTerms({ 转专业: { t: [0] } }),
            bodyTerms: impactTerms({ 申请: { c: [0] } })
        });

        await withMockFetch(firstFixture, async () => {
            const first = await recallSitegraphDocuments(firstFixture.session, '转专业申请', new AbortController().signal, 5);
            expect(first.stats.cache.artifact_misses).toBeGreaterThan(0);
        });
        await withMockFetch(changedFixture, async () => {
            const changed = await recallSitegraphDocuments(changedFixture.session, '转专业申请', new AbortController().signal, 5);
            expect(changed.stats.cache.artifact_misses).toBeGreaterThan(0);
            expect(changed.stats.cache.uncached_bytes).toBeGreaterThan(0);
            expect(changed.stats.plan.selected_local_indexes?.[0]?.cache_state).toBe('cold');
            expect(changed.stats.plan.selected_local_indexes?.[0]?.expected_uncached_bytes).toBeGreaterThan(0);
        });
    });

    it('uses shard filter proof to skip no-match shards', async () => {
        const fixture = makeRoutedFixture('filter-skip', [makeDocument()], {
            queryTerms: ['不存在的查询'],
            lightTerms: {},
            bodyTerms: {},
            filterBase64: 'AA=='
        });

        await withMockFetch(fixture, async () => {
            const events: SitegraphSearchEvent[] = [];
            await searchSitegraphProgressively(fixture.session, '不存在的查询', new AbortController().signal, event => events.push(event), { limit: 5 });
            const complete = events.at(-1);
            expect(complete?.type).toBe('global_exhaustive_complete');
            expect(complete?.coverage.proved_no_match_shards).toBe(1);
            expect(complete?.coverage.scanned_shards).toBe(0);
            expect(complete?.results).toEqual([]);
        });
    });

    it('refuses exhaustive completion when cancellation leaves proof ledger shards pending', async () => {
        const fixture = makeRoutedFixture('proof-cancelled', [makeDocument()], {
            queryTerms: ['不存在的查询'],
            lightTerms: {},
            bodyTerms: {},
            filterBase64: '/w=='
        });

        await withMockFetch(fixture, async () => {
            const controller = new AbortController();
            const events: SitegraphSearchEvent[] = [];
            await expect(searchSitegraphProgressively(
                fixture.session,
                '不存在的查询',
                controller.signal,
                event => {
                    events.push(event);
                    if (event.type === 'verification_started') {
                        controller.abort();
                    }
                },
                { limit: 5 }
            )).rejects.toMatchObject({ name: 'AbortError' });
            const verification = events.find(event => event.type === 'verification_started');
            expect(verification?.coverage.pending_shards).toBe(1);
            expect(verification?.coverage.failed_shards).toBe(0);
            expect(verification?.coverage.exhaustive_complete).toBe(false);
            expect(events.some(event => event.type === 'global_exhaustive_complete')).toBe(false);
        });
    });

    it('uses absent phrase tokens to prove a full-scan phrase cannot match', async () => {
        const fixture = makeRoutedFixture('filter-phrase-skip', [makeDocument()], {
            queryTerms: ['材料提交'],
            lightTerms: {},
            bodyTerms: {},
            filterBase64: shardFilterBase64For(['材料']),
            filterBitCount: 2048
        });

        await withMockFetch(fixture, async () => {
            const events: SitegraphSearchEvent[] = [];
            await searchSitegraphProgressively(fixture.session, '材料提交', new AbortController().signal, event => events.push(event), { limit: 5 });
            const complete = events.at(-1);
            expect(complete?.type).toBe('global_exhaustive_complete');
            expect(complete?.coverage.proved_no_match_shards).toBe(1);
            expect(complete?.coverage.scanned_shards).toBe(0);
            expect(complete?.coverage.hydrated_shard_bytes).toBe(0);
            expect(complete?.results).toEqual([]);
        });
    });

    it('marks failed proof ledger shards and refuses exhaustive completion when verification loading fails', async () => {
        const fixture = makeRoutedFixture('proof-failure', [makeDocument()], {
            queryTerms: ['不存在的查询'],
            lightTerms: {},
            bodyTerms: {},
            filterBase64: '/w=='
        });
        const shardPath = required(fixture.sourceManifest.full_shards[0], 'expected full shard').path;

        await withMockFetch(fixture, async () => {
            const events: SitegraphSearchEvent[] = [];
            await expect(searchSitegraphProgressively(
                fixture.session,
                '不存在的查询',
                new AbortController().signal,
                event => events.push(event),
                { limit: 5 }
            )).rejects.toThrow(/HTTP 503/);
            const error = events.at(-1);
            expect(error?.type).toBe('error');
            expect(error?.coverage.failed_shards).toBe(1);
            expect(error?.coverage.pending_shards).toBe(0);
            expect(error?.coverage.exhaustive_complete).toBe(false);
            expect(events.some(event => event.type === 'global_exhaustive_complete')).toBe(false);
        }, { failPaths: [shardPath] });
    });
});
