import { useMemo, useState } from 'react';
import { Download, ExternalLink, FileText, Filter } from 'lucide-react';
import {
    RankedSitegraphDocument,
    SitegraphFacet,
    SitegraphFullDocument,
    SitegraphQueryStats,
    SitegraphSearchCoverage,
    SitegraphSearchPhase,
} from '@/shared/lib/contracts';
import { formatSearchDate } from '@/features/collection-search/lib/searchIndex';

type FacetFilter = SitegraphFacet | 'all';

const FACET_LABELS: Record<FacetFilter, string> = {
    all: '全部',
    notice_article: '通知文章',
    policy: '政策制度',
    workflow: '办事流程',
    download: '下载资源',
    system: '系统入口',
    exam: '考试相关',
    news: '教务快讯',
    external: '外部链接',
};

const isExternalUrl = (url: string): boolean => /^https?:\/\//.test(url);

interface SearchResultCardProps {
    document: RankedSitegraphDocument | SitegraphFullDocument;
}

function methodLabel(method: string): string {
    if (method === 'search_record') return '官网页面收录';
    if (method === 'attachment_metadata_only') return '附件元数据收录';
    if (method === 'external_record_only') return '外部入口收录';
    return '站点图收录';
}

function phaseLabel(phase: SitegraphSearchPhase | null, searching: boolean): string {
    if (phase === 'exhaustive_complete') return '已完成 JWC 全量公开索引核查';
    if (phase === 'cancelled') return '已取消本次核查';
    if (!searching) return '等待搜索';
    if (phase === 'quick_started') return '正在启动快速搜索';
    if (phase === 'quick_results') return '快速结果已返回，正在继续核查全量公开索引';
    if (phase === 'body_started' || phase === 'body_results') return '正在继续核查正文索引';
    if (phase === 'hydrate_started' || phase === 'hydrate_results') return '正在补全文档记录并重排结果';
    if (phase === 'verify_started' || phase === 'verify_progress' || phase === 'verify_results') return '正在核查 JWC 全量公开索引';
    return '正在搜索';
}

function fieldLabel(fields: string[]): string {
    if (fields.length === 0) return '尚未开始';
    const labels: Record<string, string> = {
        title: '标题',
        section: '栏目',
        nav_path: '导航路径',
        tags: '标签',
        attachments: '附件',
        external: '外部入口',
        system: '系统入口',
        summary: '摘要',
        content: '正文',
        url: 'URL',
    };
    return fields.map(field => labels[field] || field).join('、');
}

function formatBytes(bytes: number): string {
    if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
    return `${bytes} B`;
}

function SearchResultCard({ document }: SearchResultCardProps) {
    const recallReason = (document as Partial<RankedSitegraphDocument>).score_reason || '';
    const wrapperProps = {
        href: document.url,
        target: isExternalUrl(document.url) ? '_blank' : undefined,
        rel: isExternalUrl(document.url) ? 'noopener noreferrer' : undefined,
    };

    return (
        <a {...wrapperProps} className="block w-full text-left py-4 group border-b border-[#e8eaed] dark:border-[#3c4043] last:border-b-0">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-[#70757a] dark:text-[#9aa0a6]">
                <span className="font-medium text-[#3c4043] dark:text-[#bdc1c6]">{FACET_LABELS[document.facet]}</span>
                <span>{document.source}</span>
                <span>›</span>
                <span>{document.nav_path_text || document.section}</span>
                {document.published_at ? (
                    <>
                        <span>›</span>
                        <span>{formatSearchDate(document.published_at)}</span>
                    </>
                ) : null}
            </div>

            <h3 className="mt-1 text-[20px] leading-snug font-medium text-[#1a0dab] dark:text-[#8ab4f8] group-hover:underline break-words">
                {document.title}
            </h3>

            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-[#0b8043] dark:text-[#81c995]">
                <span className="truncate max-w-full">{document.url}</span>
                {document.record_type === 'external' ? (
                    <span className="inline-flex items-center gap-1 text-[#5f6368] dark:text-[#9aa0a6]">
                        <ExternalLink size={13} />
                        只记录入口
                    </span>
                ) : null}
                {document.record_type === 'attachment' ? (
                    <span className="inline-flex items-center gap-1 text-[#5f6368] dark:text-[#9aa0a6]">
                        <Download size={13} />
                        元数据附件
                    </span>
                ) : null}
            </div>

            <p className="mt-2 text-[14px] text-[#4d5156] dark:text-[#bdc1c6] line-clamp-2 break-words">
                {document.summary || document.content}
            </p>

            <div className="mt-2 flex flex-wrap gap-2 text-[12px] text-[#5f6368] dark:text-[#9aa0a6]">
                <span className="inline-flex items-center gap-1 rounded bg-[#f1f3f4] dark:bg-[#303134] px-2 py-1">
                    <Filter size={12} />
                    {document.section}
                </span>
                {document.attachment_count > 0 ? (
                    <span className="inline-flex items-center gap-1 rounded bg-[#e8f0fe] dark:bg-[#263850] px-2 py-1 text-[#1967d2] dark:text-[#8ab4f8]">
                        <FileText size={12} />
                        附件 {document.attachment_count}
                    </span>
                ) : null}
                <span className="rounded bg-[#f1f3f4] dark:bg-[#303134] px-2 py-1">
                    {methodLabel(document.collection_method)}
                </span>
            </div>

            {document.attachments.length > 0 ? (
                <div className="mt-2 flex flex-wrap gap-1.5">
                    {document.attachments.slice(0, 4).map(attachment => (
                        <span
                            key={`${attachment.attachment_id}-${attachment.url}`}
                            className="inline-flex items-center gap-1 max-w-full h-6 px-2 rounded bg-[#f8fafd] dark:bg-[#2d2f33] text-[12px] text-[#3c4043] dark:text-[#d2d5da]"
                        >
                            <FileText size={12} className="shrink-0" />
                            <span className="truncate">{attachment.name}</span>
                            {attachment.extension ? <span className="uppercase text-[#70757a] dark:text-[#9aa0a6]">{attachment.extension}</span> : null}
                        </span>
                    ))}
                </div>
            ) : null}

            {recallReason ? (
                <div className="mt-1 text-[12px] text-[#70757a] dark:text-[#9aa0a6]">
                    召回依据：{recallReason}
                </div>
            ) : null}
        </a>
    );
}

interface CollectionSearchSectionProps {
    query: string;
    results: RankedSitegraphDocument[];
    queryStats: SitegraphQueryStats | null;
    queryCoverage: SitegraphSearchCoverage | null;
    searchPhase: SitegraphSearchPhase | null;
    searching: boolean;
}

export function CollectionSearchSection({
    query,
    results,
    queryStats,
    queryCoverage,
    searchPhase,
    searching,
}: CollectionSearchSectionProps) {
    const trimmedQuery = query.trim();
    const [activeFacet, setActiveFacet] = useState<FacetFilter>('all');
    const [visibleState, setVisibleState] = useState({ key: '', count: 20 });
    const availableFacets = useMemo(() => {
        const facets = Array.from(new Set(results.map(document => document.facet)));
        const preferred: SitegraphFacet[] = ['notice_article', 'policy', 'workflow', 'download', 'system', 'exam', 'news', 'external'];
        return preferred.filter(facet => facets.includes(facet));
    }, [results]);
    const filteredResults = useMemo(() => {
        return results.filter(document => activeFacet === 'all' || document.facet === activeFacet);
    }, [activeFacet, results]);
    const visibleKey = `${trimmedQuery}\u0000${activeFacet}`;
    const visibleCount = visibleState.key === visibleKey ? visibleState.count : 20;
    const visibleResults = filteredResults.slice(0, visibleCount);
    const coverage = queryCoverage || queryStats?.coverage || null;

    return (
        <section className="mt-8">
            <div className="mb-4">
                <h2 className="text-xl font-semibold text-[#202124] dark:text-[#e8eaed]">JWC sitegraph 搜索结果</h2>
                <div className="flex gap-4 mt-2 mb-1 border-b border-[#dadce0] dark:border-[#3c4043] overflow-x-auto whitespace-nowrap">
                    <button onClick={() => setActiveFacet('all')} className={`shrink-0 pb-2 text-sm font-medium ${activeFacet === 'all' ? 'text-[#1a73e8] border-b-2 border-[#1a73e8]' : 'text-[#5f6368] hover:text-[#202124] dark:text-[#9aa0a6] dark:hover:text-[#e8eaed]'}`}>全部</button>
                    {availableFacets.map(facet => (
                        <button
                            key={facet}
                            onClick={() => setActiveFacet(facet)}
                            className={`shrink-0 pb-2 text-sm font-medium ${activeFacet === facet ? 'text-[#1a73e8] border-b-2 border-[#1a73e8]' : 'text-[#5f6368] hover:text-[#202124] dark:text-[#9aa0a6] dark:hover:text-[#e8eaed]'}`}
                        >
                            {FACET_LABELS[facet]}
                        </button>
                    ))}
                </div>
                <p className="mt-1 text-sm text-[#70757a] dark:text-[#9aa0a6]">
                    {trimmedQuery.length >= 2
                        ? `找到 ${filteredResults.length} 条结果。${phaseLabel(searchPhase, searching)}。`
                        : '输入至少两个字符搜索本科生院 / 教务处站点图。'}
                </p>
                {coverage ? (
                    <div className="mt-3 rounded-md border border-[#dadce0] dark:border-[#3c4043] bg-[#f8fafc] dark:bg-[#2d2e30] px-3 py-2 text-sm text-[#4d5156] dark:text-[#bdc1c6]">
                        <div className="flex flex-wrap gap-x-4 gap-y-1">
                            <span>已证明跳过 {coverage.proved_no_match_shards}</span>
                            <span>已扫描 {coverage.scanned_shards}/{coverage.total_shards}</span>
                            <span>文档 {coverage.searched_documents}/{coverage.total_documents}</span>
                            <span>已加载 {formatBytes(coverage.loaded_bytes)}</span>
                            <span>阶段：{coverage.phase}</span>
                            <span>字段：{fieldLabel(coverage.searched_fields)}</span>
                        </div>
                        <div className="mt-1 text-[#70757a] dark:text-[#9aa0a6]">
                            {coverage.exhaustive_complete
                                ? '已完成 JWC 全量公开索引核查；核查范围扩大已结束，加载更多结果只会展示更多已召回结果。'
                                : '核查范围扩大中；加载更多结果只会展示更多已召回结果。'}
                        </div>
                    </div>
                ) : null}
            </div>

            {visibleResults.length > 0 ? (
                <div>
                    {visibleResults.map(document => (
                        <SearchResultCard key={document.id} document={document} />
                    ))}
                    {visibleCount < filteredResults.length && (
                        <div className="pt-4 pb-2 text-center">
                            <button
                                onClick={() => setVisibleState({ key: visibleKey, count: visibleCount + 20 })}
                                className="px-6 py-2 rounded-full border border-[#dadce0] dark:border-[#3c4043] bg-white dark:bg-[#202124] text-sm font-medium text-[#1a73e8] hover:bg-[#f8f9fa] dark:hover:bg-[#303134] transition-colors"
                            >
                                加载更多结果
                            </button>
                        </div>
                    )}
                </div>
            ) : (
                <div className="border border-[#dadce0] dark:border-[#3c4043] rounded-md bg-white dark:bg-[#202124] p-6 text-[#4d5156] dark:text-[#bdc1c6] max-w-[692px]">
                    <p>没有找到匹配的 JWC sitegraph 记录。</p>
                    <p className="mt-2 text-sm">可以尝试“校历”“期末考试”“学生相关文件及表格”“教务管理系统”这类官网栏目或标题关键词。</p>
                </div>
            )}
        </section>
    );
}
