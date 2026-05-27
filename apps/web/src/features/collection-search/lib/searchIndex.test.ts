import { describe, expect, it } from 'vitest';
import {
    parseSitegraphDocMeta,
    parseSitegraphManifest,
    recallSitegraphDocuments,
    searchSitegraphProgressively
} from './searchIndex';
import { SitegraphIndexBundle, SitegraphSearchEvent, SitegraphSearchManifest } from '@/shared/lib/contracts';

const artifact = (path: string, role: string, load = 'on_demand', count?: number) => ({
    path,
    sha256: '0123456789abcdef0123456789abcdef',
    bytes: 128,
    role,
    load,
    ...(count === undefined ? {} : { count })
});

const fullShard = {
    shard_id: 'policy__detail__2026__rules__b0',
    path: 'fixture-shard.0123456789abcdef.json',
    sha256: '0123456789abcdef0123456789abcdef',
    bytes: 256,
    count: 1,
    contains: 'full_documents' as const,
    facet_range: ['policy'],
    record_type_range: ['detail'],
    section_range: ['jwc_rules_root'],
    year_range: ['2026'],
    hash_bucket: 'b0'
};

const manifest: SitegraphSearchManifest = {
    generated_at: '2026-05-27T00:00:00Z',
    strategy: 'progressive-verifiable-static-search',
    producer_repo: 'hicancan/njupt-search',
    producer_ref: 'fixture',
    site_id: 'jwc',
    artifact_path: 'index',
    upstream_generated_at: '2026-05-26T00:00:00Z',
    truth_counts: { detail_pages: 1, attachments: 1, external_links: 0, edges: 0 },
    total_documents: 1,
    record_counts: { detail: 1 },
    facet_counts: { policy: 1 },
    exam_vertical_preserved: true,
    core_search: {
        algorithm: 'static inverted index plus on-demand full shard ranking',
        execution_model: 'pure_frontend_worker',
        light_first_screen: true,
        first_screen_artifacts: ['doc_meta_light', 'light_inverted_index', 'query_aliases'],
        body_index_loading: 'on_deep_search',
        full_text_loading: 'progressive_candidate_hydration_then_exhaustive_full_scan',
        search_worker: true
    },
    progressive_search: {
        total_shards: 1,
        total_documents: 1,
        full_scan_supported: true,
        progressive_events: true,
        artifact_roles: ['doc_meta_light', 'light_inverted_index', 'body_inverted_index', 'full_shards']
    },
    coverage_contract: {
        coverage_fields: ['title', 'section', 'nav_path', 'summary', 'content', 'attachments', 'url'],
        proof: {
            indexed_fields: ['title', 'section', 'nav_path', 'summary', 'content'],
            full_scan_fields: ['title', 'section', 'nav_path', 'summary', 'content', 'attachments', 'url']
        },
        total_shards: 1,
        total_documents: 1
    },
    verification_contract: {
        shard_filter_supported: true,
        proved_skip_supported: true,
        scan_fallback_supported: true,
        filter_artifact: 'shard_filter',
        catalog_artifact: 'shard_catalog'
    },
    artifacts: {
        doc_meta_light: artifact('index/sitegraph/jwc/artifacts/doc_meta_light.0123456789abcdef.json', 'doc_meta_light', 'initial', 1),
        light_inverted_index: artifact('index/sitegraph/jwc/artifacts/light_inverted_index.0123456789abcdef.json', 'light_inverted_index', 'initial'),
        body_inverted_index: artifact('index/sitegraph/jwc/artifacts/body_inverted_index.0123456789abcdef.json', 'body_inverted_index', 'deep_search'),
        section_index: artifact('index/sitegraph/jwc/artifacts/section_index.0123456789abcdef.json', 'section_index', 'on_demand'),
        attachment_index: artifact('index/sitegraph/jwc/artifacts/attachment_index.0123456789abcdef.json', 'attachment_index', 'on_demand', 1),
        external_index: artifact('index/sitegraph/jwc/artifacts/external_index.0123456789abcdef.json', 'external_index', 'on_demand', 0),
        query_aliases: artifact('index/sitegraph/jwc/artifacts/query_aliases.0123456789abcdef.json', 'query_aliases', 'initial', 1),
        shard_catalog: artifact('index/sitegraph/jwc/artifacts/shard_catalog.0123456789abcdef.json', 'shard_catalog', 'verify', 1),
        shard_filter: artifact('index/sitegraph/jwc/artifacts/shard_filter.0123456789abcdef.json', 'shard_filter', 'verify', 1),
        outcomes: artifact('index/sitegraph/jwc/artifacts/outcomes.0123456789abcdef.json', 'outcomes', 'audit'),
        size_report: artifact('index/sitegraph/jwc/artifacts/size_report.0123456789abcdef.json', 'size_report', 'audit')
    },
    sitegraph: {
        truth_counts: { detail_pages: 1, attachments: 1, external_links: 0, edges: 0 },
        quality: {
            errors: 0,
            all_discovered_urls_have_outcomes: true,
            attachment_policy: 'metadata_only',
            external_link_policy: 'record_only'
        },
        upstream_generated_at: '2026-05-26T00:00:00Z',
        detail_page_records: 1,
        attachment_metadata_records: 1,
        direct_attachment_records: 0,
        external_link_records: 0,
        external_document_records: 0,
        utility_link_records: 0,
        attachment_policy: 'metadata_only',
        external_link_policy: 'record_only',
        full_shards: [fullShard],
        shard_strategy: {
            version: 'locality-facet-record-year-section-hash-progressive',
            dimensions: ['facet', 'record_type', 'year', 'top_nav_section', 'hash_bucket'],
            hash_bucket_count: 4,
            sequential_fixed_size_shards: false
        },
        indexes: {
            doc_meta_light: artifact('index/sitegraph/jwc/artifacts/doc_meta_light.0123456789abcdef.json', 'doc_meta_light', 'initial', 1),
            light_inverted_index: artifact('index/sitegraph/jwc/artifacts/light_inverted_index.0123456789abcdef.json', 'light_inverted_index', 'initial'),
            body_inverted_index: artifact('index/sitegraph/jwc/artifacts/body_inverted_index.0123456789abcdef.json', 'body_inverted_index', 'deep_search'),
            section_index: artifact('index/sitegraph/jwc/artifacts/section_index.0123456789abcdef.json', 'section_index', 'on_demand'),
            attachment_index: artifact('index/sitegraph/jwc/artifacts/attachment_index.0123456789abcdef.json', 'attachment_index', 'on_demand', 1),
            external_index: artifact('index/sitegraph/jwc/artifacts/external_index.0123456789abcdef.json', 'external_index', 'on_demand', 0),
            query_aliases: artifact('index/sitegraph/jwc/artifacts/query_aliases.0123456789abcdef.json', 'query_aliases', 'initial', 1),
            shard_catalog: artifact('index/sitegraph/jwc/artifacts/shard_catalog.0123456789abcdef.json', 'shard_catalog', 'verify', 1),
            shard_filter: artifact('index/sitegraph/jwc/artifacts/shard_filter.0123456789abcdef.json', 'shard_filter', 'verify', 1),
            outcomes: artifact('index/sitegraph/jwc/artifacts/outcomes.0123456789abcdef.json', 'outcomes', 'audit'),
            size_report: artifact('index/sitegraph/jwc/artifacts/size_report.0123456789abcdef.json', 'size_report', 'audit')
        }
    }
};

const fullDocument = {
    doc_index: 0,
    id: 'jwc-detail-1',
    record_type: 'detail' as const,
    page_type: 'detail_article_page',
    facet: 'policy' as const,
    title: '南京邮电大学本科生转专业管理办法',
    url: 'https://jwc.njupt.edu.cn/1/page.htm',
    source: '本科生院 / 教务处',
    source_domain: 'jwc.njupt.edu.cn',
    section_id: 'jwc_rules_root',
    section: '规章制度',
    nav_path: ['规章制度'],
    nav_path_text: '规章制度',
    published_at: '2026-05-20',
    publisher: '综合科',
    summary: '转专业政策摘要',
    attachment_count: 1,
    hash: 'hash',
    tags: ['policy'],
    collection_method: 'search_record',
    provenance: { site_id: 'jwc', section_id: 'jwc_rules_root', nav_path: ['规章制度'], outcome: 'search_record' },
    shard: { shard_id: fullShard.shard_id, path: fullShard.path },
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
        metadata_only: true as const,
        position: 1
    }]
};

const docMetaLightFixture = () => {
    return {
        doc_index: fullDocument.doc_index,
        id: fullDocument.id,
        record_type: fullDocument.record_type,
        facet: fullDocument.facet,
        title: fullDocument.title,
        url: fullDocument.url,
        source: fullDocument.source,
        section_id: fullDocument.section_id,
        section: fullDocument.section,
        nav_path: fullDocument.nav_path,
        nav_path_text: fullDocument.nav_path_text,
        published_at: fullDocument.published_at,
        attachment_count: fullDocument.attachment_count,
        collection_method: fullDocument.collection_method,
        shard: fullDocument.shard
    };
};

describe('sitegraph search contract', () => {
    it('rejects obsolete provider fields instead of masking schema errors', () => {
        const obsoleteProviderField = `${['l', 'l', 'm'].join('')}_provider`;
        expect(() => parseSitegraphManifest({ ...manifest, [obsoleteProviderField]: null })).toThrow(/provider|Validation/);
    });

    it('rejects old semantic fields in doc meta', () => {
        const docMeta = docMetaLightFixture();
        expect(() => parseSitegraphDocMeta([{ ...docMeta, semantic_mode: 'sitegraph_rule' }], 'fixture')).toThrow();
        expect(() => parseSitegraphDocMeta([{ ...docMeta, content: 'must stay in body index' }], 'fixture')).toThrow(/doc_meta_light/);
    });

    it('ranks title and attachment matches after loading only candidate shard', async () => {
        const docMeta = docMetaLightFixture();
        const bundle: SitegraphIndexBundle = {
            manifest,
            docMeta: [docMeta],
            lightInvertedIndex: {
                version: 'sitegraph-light-inverted-progressive',
                tokenizer: 'test',
                field_codes: { title: 't', attachment: 'a' },
                tokens: {
                    转专业: { t: [0], a: [0] },
                    申请表: { a: [0] }
                }
            },
            queryAliases: { 转专业: { aliases: ['专业变更'] } }
        };
        const originalFetch = globalThis.fetch;
        globalThis.fetch = (async (input: RequestInfo | URL) => {
            const url = String(input);
            if (url.includes('body_inverted_index')) {
                return new Response(JSON.stringify({
                    version: 'sitegraph-body-inverted-progressive',
                    tokenizer: 'test',
                    field_codes: { summary: 'm', content: 'c' },
                    tokens: {
                        转专业: { c: [0] }
                    }
                }));
            }
            if (url.includes('shard_filter')) {
                return new Response(JSON.stringify({
                    [fullShard.shard_id]: {
                        bitset_base64: '/w==',
                        bit_count: 8,
                        hash_count: 1,
                        token_count: 4,
                        sha256: '0123456789abcdef0123456789abcdef',
                        hash_algorithm: 'bloom-fnv1a32-utf8'
                    }
                }));
            }
            return new Response(JSON.stringify([fullDocument]));
        }) as typeof fetch;
        try {
            const { results, stats } = await recallSitegraphDocuments(bundle, '转专业申请表', new AbortController().signal);
            expect(results[0]?.id).toBe('jwc-detail-1');
            expect(results[0]?.score_reason).toContain('附件名命中');
            expect(stats.loadedShardCount).toBe(1);
            expect(stats.loadedShardPaths).toEqual([fullShard.path]);
            expect(stats.coverage.exhaustive_complete).toBe(true);
        } finally {
            globalThis.fetch = originalFetch;
        }
    });

    it('emits progressive phases with exhaustive coverage', async () => {
        const docMeta = docMetaLightFixture();
        const bundle: SitegraphIndexBundle = {
            manifest,
            docMeta: [docMeta],
            lightInvertedIndex: {
                version: 'sitegraph-light-inverted-progressive',
                tokenizer: 'test',
                field_codes: { title: 't' },
                tokens: {
                    转专业: { t: [0] }
                }
            },
            queryAliases: { 转专业: { aliases: ['专业变更'] } }
        };
        const originalFetch = globalThis.fetch;
        globalThis.fetch = (async (input: RequestInfo | URL) => {
            const url = String(input);
            if (url.includes('body_inverted_index')) {
                return new Response(JSON.stringify({
                    version: 'sitegraph-body-inverted-progressive',
                    tokenizer: 'test',
                    field_codes: { summary: 'm', content: 'c' },
                    tokens: {
                        申请: { c: [0] }
                    }
                }));
            }
            if (url.includes('shard_filter')) {
                return new Response(JSON.stringify({
                    [fullShard.shard_id]: {
                        bitset_base64: '/w==',
                        bit_count: 8,
                        hash_count: 1,
                        token_count: 3,
                        sha256: '0123456789abcdef0123456789abcdef',
                        hash_algorithm: 'bloom-fnv1a32-utf8'
                    }
                }));
            }
            return new Response(JSON.stringify([fullDocument]));
        }) as typeof fetch;
        try {
            const events: SitegraphSearchEvent[] = [];
            await searchSitegraphProgressively(bundle, '转专业申请', new AbortController().signal, event => events.push(event), { limit: 5 });
            expect(events.map(event => event.type)).toEqual(expect.arrayContaining([
                'quick_started',
                'quick_results',
                'body_started',
                'body_results',
                'hydrate_started',
                'hydrate_results',
                'verify_started',
                'verify_progress',
                'exhaustive_complete'
            ]));
            const complete = events[events.length - 1];
            expect(complete?.type).toBe('exhaustive_complete');
            expect(complete?.coverage.exhaustive_complete).toBe(true);
            expect(complete?.coverage.scanned_shards).toBe(1);
            expect(complete?.coverage.proved_no_match_shards).toBe(0);
            expect(complete?.coverage.searched_documents).toBe(1);
            expect(complete?.results?.[0]?.id).toBe('jwc-detail-1');
        } finally {
            globalThis.fetch = originalFetch;
        }
    });

    it('supports cancellation before exhaustive completion', async () => {
        const docMeta = docMetaLightFixture();
        const bundle: SitegraphIndexBundle = {
            manifest,
            docMeta: [docMeta],
            lightInvertedIndex: {
                version: 'sitegraph-light-inverted-progressive',
                tokenizer: 'test',
                field_codes: { title: 't' },
                tokens: {
                    转专业: { t: [0] }
                }
            },
            queryAliases: {}
        };
        const controller = new AbortController();
        const originalFetch = globalThis.fetch;
        globalThis.fetch = (async (input: RequestInfo | URL) => {
            const url = String(input);
            if (url.includes('body_inverted_index')) {
                controller.abort();
                return new Response(JSON.stringify({
                    version: 'sitegraph-body-inverted-progressive',
                    tokenizer: 'test',
                    field_codes: { summary: 'm', content: 'c' },
                    tokens: {}
                }));
            }
            return new Response(JSON.stringify([fullDocument]));
        }) as typeof fetch;
        try {
            const events: SitegraphSearchEvent[] = [];
            await expect(searchSitegraphProgressively(bundle, '转专业', controller.signal, event => events.push(event))).rejects.toThrow(/cancel/i);
            expect(events.some(event => event.type === 'exhaustive_complete')).toBe(false);
        } finally {
            globalThis.fetch = originalFetch;
        }
    });

    it('uses shard filter proof to skip no-match shards', async () => {
        const docMeta = docMetaLightFixture();
        const bundle: SitegraphIndexBundle = {
            manifest,
            docMeta: [docMeta],
            lightInvertedIndex: {
                version: 'sitegraph-light-inverted-current',
                tokenizer: 'test',
                field_codes: { title: 't' },
                tokens: {}
            },
            queryAliases: {}
        };
        const originalFetch = globalThis.fetch;
        let shardLoads = 0;
        globalThis.fetch = (async (input: RequestInfo | URL) => {
            const url = String(input);
            if (url.includes('body_inverted_index')) {
                return new Response(JSON.stringify({
                    version: 'sitegraph-body-inverted-current',
                    tokenizer: 'test',
                    field_codes: { summary: 'm', content: 'c' },
                    tokens: {}
                }));
            }
            if (url.includes('shard_filter')) {
                return new Response(JSON.stringify({
                    [fullShard.shard_id]: {
                        bitset_base64: 'AA==',
                        bit_count: 8,
                        hash_count: 1,
                        token_count: 0,
                        sha256: '0123456789abcdef0123456789abcdef',
                        hash_algorithm: 'bloom-fnv1a32-utf8'
                    }
                }));
            }
            shardLoads += 1;
            return new Response(JSON.stringify([fullDocument]));
        }) as typeof fetch;
        try {
            const events: SitegraphSearchEvent[] = [];
            await searchSitegraphProgressively(bundle, '不存在的查询', new AbortController().signal, event => events.push(event), { limit: 5 });
            const complete = events[events.length - 1];
            expect(complete?.type).toBe('exhaustive_complete');
            expect(complete?.coverage.proved_no_match_shards).toBe(1);
            expect(complete?.coverage.scanned_shards).toBe(0);
            expect(shardLoads).toBe(0);
        } finally {
            globalThis.fetch = originalFetch;
        }
    });
});

