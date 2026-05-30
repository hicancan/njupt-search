import { describe, expect, it } from 'vitest';
import {
    buildSitegraphMatchSnippet,
    formatResolvedSearchDate,
    parseSitegraphDocMeta,
    parseSitegraphManifest,
    recallSitegraphDocuments,
    searchSitegraphProgressively,
    tokenizeSitegraphQuery
} from '../src';
import type { SitegraphIndexBundle, SitegraphSearchEvent, SitegraphSearchManifest } from '@njupt-search/contracts';

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
    collection_id: 'njupt-public',
    sources: [{
        source_id: 'jwc',
        source_kind: 'sitegraph',
        artifact_root: 'generated/collections/njupt-public/sitegraph/jwc',
        upstream_generated_at: '2026-05-26T00:00:00Z',
        display_name: '本科生院 / 教务处'
    }],
    artifact_path: 'generated/collections/njupt-public',
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
        source_id: fullDocument.source_id,
        source: fullDocument.source,
        section_id: fullDocument.section_id,
        section: fullDocument.section,
        nav_path: fullDocument.nav_path,
        nav_path_text: fullDocument.nav_path_text,
        published_at: fullDocument.published_at,
        version_date: fullDocument.version_date,
        date_kind: fullDocument.date_kind,
        task_kind: fullDocument.task_kind,
        attachment_count: fullDocument.attachment_count,
        collection_method: fullDocument.collection_method,
        shard: fullDocument.shard
    };
};

describe('sitegraph search contract', () => {
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
            ...fullDocument,
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
            ...fullDocument,
            content: '这是一段可显示的正文，但它不包含当前查询词。'
        }, '不存在的词', ['不存在的词']);

        expect(snippet?.fallback).toBe(true);
        expect(snippet?.highlights).toEqual([]);
        expect(snippet?.matched_terms).toEqual([]);
    });

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
            expect(results[0]?.match_snippet?.field).toBe('attachments');
            expect(results[0]?.match_snippet?.text).toContain('转专业申请表.doc');
            expect(results[0]?.match_snippet?.matched_terms).toContain('转专业申请表');
            expect(results[0]?.match_snippet?.highlights.length).toBeGreaterThan(0);
            expect(stats.loadedShardCount).toBe(1);
            expect(stats.loadedShardPaths).toEqual([fullShard.path]);
            expect(stats.coverage.exhaustive_complete).toBe(true);
        } finally {
            globalThis.fetch = originalFetch;
        }
    });

    it('reports fallback and verification telemetry in query stats', async () => {
        const docMeta = docMetaLightFixture();
        const bundle: SitegraphIndexBundle = {
            manifest,
            docMeta: [docMeta],
            lightInvertedIndex: {
                version: 'sitegraph-light-inverted-progressive',
                tokenizer: 'test',
                field_codes: { title: 't' },
                tokens: {}
            },
            queryAliases: {}
        };
        const originalFetch = globalThis.fetch;
        globalThis.fetch = (async (input: RequestInfo | URL) => {
            const url = String(input);
            if (url.includes('body_inverted_index')) {
                return new Response(JSON.stringify({
                    version: 'sitegraph-body-inverted-progressive',
                    tokenizer: 'test',
                    field_codes: { summary: 'm', content: 'c' },
                    tokens: {}
                }));
            }
            if (url.includes('shard_filter')) {
                return new Response(JSON.stringify({
                    [fullShard.shard_id]: {
                        bitset_base64: '/w==',
                        bit_count: 8,
                        hash_count: 1,
                        token_count: 1,
                        sha256: '0123456789abcdef0123456789abcdef',
                        hash_algorithm: 'bloom-fnv1a32-utf8'
                    }
                }));
            }
            return new Response(JSON.stringify([fullDocument]));
        }) as typeof fetch;
        try {
            const { results, stats } = await recallSitegraphDocuments(bundle, fullDocument.title, new AbortController().signal);
            expect(results[0]?.id).toBe('jwc-detail-1');
            expect(stats.fallbacks.lightMetaFallbackDocuments).toBe(1);
            expect(stats.fallbacks.exhaustiveFullScanMatches).toBe(1);
            expect(stats.fallbacks.snippetFallbackResults).toBe(0);
            expect(results[0]?.query_stats?.fallbacks.lightMetaFallbackDocuments).toBe(1);
        } finally {
            globalThis.fetch = originalFetch;
        }
    });

    it('uses version and recorded dates for display and date sorting', async () => {
        const oldNotice = {
            ...fullDocument,
            doc_index: 0,
            id: 'old-notice',
            facet: 'notice_article' as const,
            title: '2024年推免工作方案',
            canonical_title: '2024年推免工作方案',
            published_at: '2024-09-07',
            version_date: null,
            date_kind: 'published',
            summary: '推免工作方案',
            content: '2024年推免工作方案。'
        };
        const versionedDownload = {
            ...fullDocument,
            doc_index: 1,
            id: 'versioned-download',
            facet: 'download' as const,
            title: '南京邮电大学学生一般事务申请表 2026-04-16',
            canonical_title: '南京邮电大学学生一般事务申请表 2026-04-16',
            published_at: null,
            version_date: '2026-04-16',
            date_kind: 'version',
            date_confidence: 'title_or_attachment',
            summary: '附件元数据：南京邮电大学学生一般事务申请表 2026-04-16。来源栏目：推免生。',
            content: '附件元数据命中推免生栏目。',
            collection_method: 'attachment_metadata_only'
        };
        const otherSource = {
            ...versionedDownload,
            doc_index: 2,
            id: 'other-source',
            source_id: 'graduate',
            source: '研究生院',
            source_domain: 'graduate.njupt.edu.cn',
            facet: 'download' as const,
            version_date: '2026-05-01',
            title: '研究生院推免下载入口',
            canonical_title: '研究生院推免下载入口',
            summary: '研究生院推免下载入口。',
            content: '研究生院推免下载入口。'
        };
        const docs = [oldNotice, versionedDownload, otherSource];
        const searchShard = {
            ...fullShard,
            path: 'fixture-date-filter-shard.0123456789abcdef.json',
            count: docs.length,
            facet_range: ['notice_article', 'download']
        };
        const searchManifest: SitegraphSearchManifest = {
            ...manifest,
            total_documents: docs.length,
            sitegraph: {
                ...manifest.sitegraph,
                full_shards: [searchShard]
            },
            progressive_search: {
                ...manifest.progressive_search,
                total_documents: docs.length
            }
        };
        const bundle: SitegraphIndexBundle = {
            manifest: searchManifest,
            docMeta: docs.map(document => ({
                doc_index: document.doc_index,
                id: document.id,
                record_type: document.record_type,
                facet: document.facet,
                title: document.title,
                url: document.url,
                source_id: document.source_id,
                source: document.source,
                section_id: document.section_id,
                section: document.section,
                nav_path: document.nav_path,
                nav_path_text: document.nav_path_text,
                published_at: document.published_at,
                version_date: document.version_date,
                recorded_at: document.recorded_at,
                date_kind: document.date_kind,
                date_confidence: document.date_confidence,
                task_kind: document.task_kind,
                attachment_count: document.attachment_count,
                collection_method: document.collection_method,
                shard: { shard_id: searchShard.shard_id, path: searchShard.path }
            })),
            lightInvertedIndex: {
                version: 'sitegraph-light-inverted-progressive',
                tokenizer: 'test',
                field_codes: { title: 't' },
                tokens: {
                    推免: { t: [0, 1, 2] }
                }
            },
            queryAliases: {}
        };
        const originalFetch = globalThis.fetch;
        globalThis.fetch = (async (input: RequestInfo | URL) => {
            const url = String(input);
            if (url.includes('body_inverted_index')) {
                return new Response(JSON.stringify({
                    version: 'sitegraph-body-inverted-progressive',
                    tokenizer: 'test',
                    field_codes: { content: 'c' },
                    tokens: {
                        推免: { c: [0, 1, 2] }
                    }
                }));
            }
            if (url.includes('shard_filter')) {
                return new Response(JSON.stringify({
                    [searchShard.shard_id]: {
                        bitset_base64: '/w==',
                        bit_count: 8,
                        hash_count: 1,
                        token_count: 3,
                        sha256: '0123456789abcdef0123456789abcdef',
                        hash_algorithm: 'bloom-fnv1a32-utf8'
                    }
                }));
            }
            return new Response(JSON.stringify(docs.map(document => ({
                ...document,
                shard: { shard_id: searchShard.shard_id, path: searchShard.path }
            }))));
        }) as typeof fetch;
        try {
            const events: SitegraphSearchEvent[] = [];
            await searchSitegraphProgressively(bundle, '推免', new AbortController().signal, event => events.push(event), {
                limit: 10,
                sortMode: 'date_desc',
                filters: { sourceId: 'jwc', facet: 'download', dateRange: 'past_year' },
                now: new Date('2026-05-29T00:00:00+08:00').getTime()
            });
            const complete = events.at(-1);
            expect(complete?.type).toBe('exhaustive_complete');
            expect(complete?.results?.map(result => result.id)).toEqual(['versioned-download']);
            expect(formatResolvedSearchDate(versionedDownload)).toBe('版本日期 2026/04/16');
            expect(formatResolvedSearchDate({
                ...versionedDownload,
                published_at: null,
                version_date: null,
                recorded_at: '2026-05-01'
            })).toBe('收录日期 2026/05/01');
        } finally {
            globalThis.fetch = originalFetch;
        }
    });

    it('uses alias n-grams for candidate recall without counting weak phrase misses as results', async () => {
        const aliasShard = {
            ...fullShard,
            shard_id: 'notice__detail__2026__calendar__b0',
            path: 'fixture-alias-shard.0123456789abcdef.json',
            count: 2,
            facet_range: ['notice_article'],
            section_range: ['jwc_notice_root']
        };
        const calendarDocument = {
            ...fullDocument,
            doc_index: 0,
            id: 'calendar',
            facet: 'notice_article' as const,
            title: '2025-2026学年校历',
            canonical_title: '2025-2026学年校历',
            section: '通知公告',
            nav_path: ['通知公告'],
            nav_path_text: '通知公告',
            summary: '2025-2026学年校历',
            content: '学校发布2025-2026学年校历。',
            task_kind: 'academic_calendar',
            shard: { shard_id: aliasShard.shard_id, path: aliasShard.path },
            attachments: []
        };
        const weakAliasDocument = {
            ...calendarDocument,
            doc_index: 1,
            id: 'weak-alias',
            title: '2025-2026学年第二学期学生选课通知',
            canonical_title: '2025-2026学年第二学期学生选课通知',
            summary: '2025-2026学年第二学期选课安排。',
            content: '学生选课通知，不包含目标完整短语。',
            task_kind: 'course_grade_credit'
        };
        const bundle: SitegraphIndexBundle = {
            manifest: {
                ...manifest,
                total_documents: 2,
                sitegraph: {
                    ...manifest.sitegraph,
                    full_shards: [aliasShard]
                },
                progressive_search: {
                    ...manifest.progressive_search,
                    total_documents: 2
                }
            },
            docMeta: [calendarDocument, weakAliasDocument].map(document => ({
                doc_index: document.doc_index,
                id: document.id,
                record_type: document.record_type,
                facet: document.facet,
                title: document.title,
                url: document.url,
                source_id: document.source_id,
                source: document.source,
                section_id: document.section_id,
                section: document.section,
                nav_path: document.nav_path,
                nav_path_text: document.nav_path_text,
                published_at: document.published_at,
                version_date: document.version_date,
                date_kind: document.date_kind,
                task_kind: document.task_kind,
                attachment_count: document.attachment_count,
                collection_method: document.collection_method,
                shard: document.shard
            })),
            lightInvertedIndex: {
                version: 'sitegraph-light-inverted-progressive',
                tokenizer: 'test',
                field_codes: { title: 't' },
                tokens: {
                    校历: { t: [0] },
                    '2025-2026': { t: [0, 1] },
                    学年: { t: [0, 1] }
                }
            },
            queryAliases: { 校历: { aliases: ['2025-2026学年校历'] } }
        };
        const originalFetch = globalThis.fetch;
        globalThis.fetch = (async (input: RequestInfo | URL) => {
            const url = String(input);
            if (url.includes('body_inverted_index')) {
                return new Response(JSON.stringify({
                    version: 'sitegraph-body-inverted-progressive',
                    tokenizer: 'test',
                    field_codes: { content: 'c' },
                    tokens: {
                        校历: { c: [0] },
                        '2025-2026': { c: [0, 1] },
                        学年: { c: [0, 1] }
                    }
                }));
            }
            if (url.includes('shard_filter')) {
                return new Response(JSON.stringify({
                    [aliasShard.shard_id]: {
                        bitset_base64: '/w==',
                        bit_count: 8,
                        hash_count: 1,
                        token_count: 3,
                        sha256: '0123456789abcdef0123456789abcdef',
                        hash_algorithm: 'bloom-fnv1a32-utf8'
                    }
                }));
            }
            return new Response(JSON.stringify([calendarDocument, weakAliasDocument]));
        }) as typeof fetch;
        try {
            const { results, stats } = await recallSitegraphDocuments(bundle, '校历', new AbortController().signal, 10);
            expect(results.map(result => result.id)).toEqual(['calendar']);
            expect(stats.resultCount).toBe(1);
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

    it('does not share pending shard fetches across abort signals', async () => {
        const shardPath = 'fixture-shard-abort-race.0123456789abcdef.json';
        const raceShard = { ...fullShard, shard_id: 'policy__detail__2026__rules__race', path: shardPath };
        const raceDocument = {
            ...fullDocument,
            shard: { shard_id: raceShard.shard_id, path: shardPath }
        };
        const raceManifest: SitegraphSearchManifest = {
            ...manifest,
            sitegraph: {
                ...manifest.sitegraph,
                full_shards: [raceShard]
            }
        };
        const docMeta = {
            ...docMetaLightFixture(),
            shard: { shard_id: raceShard.shard_id, path: shardPath }
        };
        const bundle = (): SitegraphIndexBundle => ({
            manifest: raceManifest,
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
        });
        const originalFetch = globalThis.fetch;
        let shardFetches = 0;
        let firstShardRequested: (() => void) | null = null;
        const firstShardStarted = new Promise<void>(resolve => {
            firstShardRequested = resolve;
        });
        globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
            const url = String(input);
            if (url.includes('body_inverted_index')) {
                return new Response(JSON.stringify({
                    version: 'sitegraph-body-inverted-progressive',
                    tokenizer: 'test',
                    field_codes: { summary: 'm', content: 'c' },
                    tokens: {}
                }));
            }
            if (url.includes('shard_filter')) {
                return new Response(JSON.stringify({
                    [raceShard.shard_id]: {
                        bitset_base64: '/w==',
                        bit_count: 8,
                        hash_count: 1,
                        token_count: 3,
                        sha256: '0123456789abcdef0123456789abcdef',
                        hash_algorithm: 'bloom-fnv1a32-utf8'
                    }
                }));
            }
            if (url.includes(shardPath)) {
                shardFetches += 1;
                if (shardFetches === 1) {
                    firstShardRequested?.();
                    return new Promise<Response>((_resolve, reject) => {
                        const signal = init?.signal;
                        if (signal?.aborted) {
                            reject(new DOMException('Search cancelled', 'AbortError'));
                            return;
                        }
                        signal?.addEventListener('abort', () => reject(new DOMException('Search cancelled', 'AbortError')), { once: true });
                    });
                }
                return new Response(JSON.stringify([raceDocument]));
            }
            return new Response(JSON.stringify([raceDocument]));
        }) as typeof fetch;

        const controller1 = new AbortController();
        const controller2 = new AbortController();
        try {
            const firstSearch = searchSitegraphProgressively(bundle(), '转专业', controller1.signal, () => undefined, { limit: 5 });
            await firstShardStarted;
            const secondEvents: SitegraphSearchEvent[] = [];
            const secondSearch = searchSitegraphProgressively(bundle(), '转专业', controller2.signal, event => secondEvents.push(event), { limit: 5 });
            await new Promise(resolve => setTimeout(resolve, 0));
            controller1.abort();
            await expect(firstSearch).rejects.toThrow(/cancel/i);
            await expect(secondSearch).resolves.toBeUndefined();
            expect(shardFetches).toBe(2);
            expect(secondEvents.at(-1)?.type).toBe('exhaustive_complete');
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
