import { useMemo, useState } from 'react';
import { ArrowDownWideNarrow, CalendarDays, ChevronDown, ChevronUp, Download, ExternalLink, FileText, Filter, ListFilter, RotateCcw, ShieldCheck } from 'lucide-react';
import {
    SitegraphFilterOption,
    SitegraphFilterOptions,
    SitegraphMatchHighlight,
    RankedSitegraphDocument,
    SitegraphFacet,
    SitegraphFullDocument,
    SitegraphQueryStats,
    SitegraphSearchFilters,
    SitegraphSearchCoverage,
    SitegraphSearchPhase,
    SitegraphSortMode,
} from '@/shared/lib/contracts';
import { formatResolvedSearchDate } from '@njupt-search/search-core';
import { getSearchCoverageProgress } from './searchCoverageProgress';

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

const DATE_FILTER_LABELS: Record<NonNullable<SitegraphSearchFilters['dateRange']>, string> = {
    all: '全部时间',
    past_year: '近一年',
    past_3_years: '近三年',
    past_5_years: '近五年',
    undated: '未标日期',
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

function evidenceLevelLabel(level: string | undefined): string | null {
    if (level === 'filename_only') return '附件文件名';
    if (level === 'metadata_only' || level === 'source_metadata') return '来源元数据';
    if (level === 'text_extracted') return '附件文本';
    if (level === 'snippet') return '摘要片段';
    if (level === 'full_content') return '正文全文';
    return null;
}

function phaseLabel(phase: SitegraphSearchPhase | null, searching: boolean): string {
    if (phase === 'scoped_exhaustive_complete' || phase === 'global_exhaustive_complete') return '';
    if (phase === 'cancelled') return '已取消本次核查';
    if (!searching) return '等待搜索';
    if (phase === 'plan_started') return '正在规划权威来源';
    if (phase === 'local_index_started') return '正在加载相关局部索引';
    if (phase === 'first_trusted_results') return '可信首批结果已返回，正在继续补全';
    if (phase === 'body_index_started') return '正在加载相关正文索引';
    if (phase === 'top_results_hydrated') return '高相关结果已补全，正在做覆盖证明';
    if (phase === 'verification_started' || phase === 'partial_verified') return '正在验证范围内官网分片';
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

function highlightRangesFromTerms(text: string, terms: string[]): SitegraphMatchHighlight[] {
    const uniqueTerms = Array.from(new Set(terms.filter(term => term.length >= 2)))
        .sort((a, b) => b.length - a.length);
    if (uniqueTerms.length === 0) return [];

    const lowerText = text.toLocaleLowerCase('zh-CN');
    const ranges: SitegraphMatchHighlight[] = [];
    for (const term of uniqueTerms) {
        const lowerTerm = term.toLocaleLowerCase('zh-CN');
        let index = lowerText.indexOf(lowerTerm);
        while (index >= 0) {
            const end = index + term.length;
            const overlaps = ranges.some(range => index < range.end && end > range.start);
            if (!overlaps) {
                ranges.push({ start: index, end, term });
            }
            index = lowerText.indexOf(lowerTerm, index + 1);
        }
    }
    return ranges.sort((a, b) => a.start - b.start);
}

function highlightedSegments(
    text: string,
    highlights: SitegraphMatchHighlight[] | undefined,
    terms: string[]
): Array<{ text: string; highlighted: boolean }> {
    const ranges = (highlights && highlights.length > 0 ? highlights : highlightRangesFromTerms(text, terms))
        .filter(range => Number.isInteger(range.start)
            && Number.isInteger(range.end)
            && range.start >= 0
            && range.end > range.start
            && range.end <= text.length)
        .sort((a, b) => a.start - b.start);
    if (ranges.length === 0) return [{ text, highlighted: false }];

    const segments: Array<{ text: string; highlighted: boolean }> = [];
    let cursor = 0;
    for (const range of ranges) {
        if (range.start < cursor) continue;
        if (range.start > cursor) {
            segments.push({ text: text.slice(cursor, range.start), highlighted: false });
        }
        segments.push({ text: text.slice(range.start, range.end), highlighted: true });
        cursor = range.end;
    }
    if (cursor < text.length) {
        segments.push({ text: text.slice(cursor), highlighted: false });
    }
    return segments.filter(segment => segment.text.length > 0);
}

function HighlightedText({ text, terms, highlights }: { text: string; terms: string[]; highlights?: SitegraphMatchHighlight[] }) {
    return (
        <>
            {highlightedSegments(text, highlights, terms).map((segment, index) => segment.highlighted ? (
                <mark
                    key={`${segment.text}-${index}`}
                    data-testid="collection-result-highlight"
                    className="rounded bg-[#fff3bf] px-0.5 text-inherit dark:bg-[#5f4b18]"
                >
                    {segment.text}
                </mark>
            ) : (
                <span key={`${segment.text}-${index}`}>{segment.text}</span>
            ))}
        </>
    );
}

function hasActiveFilters(filters: SitegraphSearchFilters): boolean {
    return (filters.sourceId || 'all') !== 'all'
        || (filters.facet || 'all') !== 'all'
        || (filters.dateRange || 'all') !== 'all';
}

function resultSummary(
    filters: SitegraphSearchFilters,
    returnedCount: number,
    totalCount: number,
    exhaustiveComplete: boolean,
    sortMode: SitegraphSortMode
): string {
    const phaseVerb = exhaustiveComplete ? '匹配' : '已召回';
    const isCapped = totalCount > returnedCount;
    const scope = hasActiveFilters(filters) ? '筛选后' : '';
    const sortLabel = sortMode === 'date_desc' ? '时间较新的' : '相关性最高的';
    if (isCapped) {
        return `${scope}${phaseVerb} ${totalCount} 条，展示${sortLabel}前 ${returnedCount} 条。`;
    }
    return `${scope}${phaseVerb} ${totalCount} 条。`;
}

function SearchResultCard({ document }: SearchResultCardProps) {
    const recallReason = (document as Partial<RankedSitegraphDocument>).score_reason || '';
    const snippet = (document as Partial<RankedSitegraphDocument>).match_snippet;
    const snippetEvidenceLabel = evidenceLevelLabel(snippet?.evidence_level);
    const snippetText = snippet?.text || document.summary || document.content;
    const wrapperProps = {
        href: document.url,
        target: isExternalUrl(document.url) ? '_blank' : undefined,
        rel: isExternalUrl(document.url) ? 'noopener noreferrer' : undefined,
    };

    return (
        <a {...wrapperProps} className="block w-full text-left py-3 group border-b border-[#e8eaed] dark:border-[#3c4043] last:border-b-0">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-[#70757a] dark:text-[#9aa0a6]">
                <span className="font-medium text-[#3c4043] dark:text-[#bdc1c6]">{FACET_LABELS[document.facet]}</span>
                <span>{document.source}</span>
                <span>›</span>
                <span>{document.nav_path_text || document.section}</span>
                <span>›</span>
                <span>{formatResolvedSearchDate(document)}</span>
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

            <p
                data-testid="collection-result-snippet"
                className="mt-2 text-[14px] text-[#4d5156] dark:text-[#bdc1c6] line-clamp-3 sm:line-clamp-2 break-words"
            >
                <HighlightedText
                    text={snippetText}
                    terms={snippet?.matched_terms || []}
                    highlights={snippet?.highlights}
                />
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
                {snippetEvidenceLabel ? (
                    <span className="inline-flex items-center gap-1 rounded bg-[#f1f3f4] dark:bg-[#303134] px-2 py-1">
                        <ShieldCheck size={12} />
                        {snippetEvidenceLabel}
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
    sortMode: SitegraphSortMode;
    filters: SitegraphSearchFilters;
    filterOptions: SitegraphFilterOptions | null;
    onSortModeChange: (sortMode: SitegraphSortMode) => void;
    onFiltersChange: (patch: SitegraphSearchFilters) => void;
}

export function CollectionSearchSection({
    query,
    results,
    queryStats,
    queryCoverage,
    searchPhase,
    searching,
    sortMode,
    filters,
    filterOptions,
    onSortModeChange,
    onFiltersChange,
}: CollectionSearchSectionProps) {
    const trimmedQuery = query.trim();
    const [showDiagnostics, setShowDiagnostics] = useState(false);
    const [visibleState, setVisibleState] = useState({ key: '', count: 20 });
    const facetOptions = useMemo(() => {
        const facets = Array.from(new Set((filterOptions?.facets || []).map(facet => facet.id)));
        const preferred: SitegraphFacet[] = ['notice_article', 'policy', 'workflow', 'download', 'system', 'exam', 'news', 'external'];
        const facetById = new Map((filterOptions?.facets || []).map(facet => [facet.id, facet]));
        return preferred
            .filter(facet => facets.includes(facet))
            .map(facet => facetById.get(facet))
            .filter((facet): facet is SitegraphFilterOption & { id: SitegraphFacet } => Boolean(facet));
    }, [filterOptions]);
    const sourceOptions = filterOptions?.sources || [];
    const visibleKey = `${trimmedQuery}\u0000${sortMode}\u0000${filters.sourceId || 'all'}\u0000${filters.facet || 'all'}\u0000${filters.dateRange || 'all'}`;
    const visibleCount = visibleState.key === visibleKey ? visibleState.count : 20;
    const visibleResults = results.slice(0, visibleCount);
    const coverage = queryCoverage || queryStats?.coverage || null;
    const totalResultCount = queryStats?.resultCount ?? results.length;
    const coverageProgress = coverage ? getSearchCoverageProgress(coverage) : null;
    const phaseText = phaseLabel(searchPhase, searching);
    const summary = resultSummary(
        filters,
        results.length,
        totalResultCount,
        Boolean(coverage?.exhaustive_complete),
        sortMode
    );
    const statusText = trimmedQuery.length < 2
        ? '输入至少两个字符搜索南邮官网信息。'
        : phaseText
            ? `${summary}${phaseText}。`
            : summary;
    const activeFilters = hasActiveFilters(filters);

    return (
        <section>
            <div className="mb-2">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                    <div className="inline-flex h-9 items-center rounded-md border border-[#dadce0] dark:border-[#3c4043] bg-white dark:bg-[#202124] p-0.5" aria-label="排序方式">
                        <button
                            type="button"
                            aria-pressed={sortMode === 'relevance'}
                            onClick={() => onSortModeChange('relevance')}
                            className={`inline-flex h-7 items-center gap-1 rounded px-2.5 text-sm ${sortMode === 'relevance' ? 'bg-[#e8f0fe] text-[#1967d2] dark:bg-[#263850] dark:text-[#8ab4f8]' : 'text-[#5f6368] hover:bg-[#f1f3f4] dark:text-[#9aa0a6] dark:hover:bg-[#303134]'}`}
                        >
                            <ArrowDownWideNarrow size={14} aria-hidden="true" />
                            相关性
                        </button>
                        <button
                            type="button"
                            aria-pressed={sortMode === 'date_desc'}
                            onClick={() => onSortModeChange('date_desc')}
                            className={`inline-flex h-7 items-center gap-1 rounded px-2.5 text-sm ${sortMode === 'date_desc' ? 'bg-[#e8f0fe] text-[#1967d2] dark:bg-[#263850] dark:text-[#8ab4f8]' : 'text-[#5f6368] hover:bg-[#f1f3f4] dark:text-[#9aa0a6] dark:hover:bg-[#303134]'}`}
                        >
                            <CalendarDays size={14} aria-hidden="true" />
                            时间
                        </button>
                    </div>
                    <label className="inline-flex h-9 items-center gap-1.5 rounded-md border border-[#dadce0] dark:border-[#3c4043] bg-white dark:bg-[#202124] px-2 text-sm text-[#4d5156] dark:text-[#bdc1c6]">
                        <Filter size={14} aria-hidden="true" />
                        <span className="sr-only">来源筛选</span>
                        <select
                            value={filters.sourceId || 'all'}
                            onChange={event => onFiltersChange({ sourceId: event.target.value })}
                            className="max-w-[210px] bg-transparent text-sm outline-none"
                            aria-label="来源筛选"
                        >
                            <option value="all">全部来源</option>
                            {sourceOptions.map(source => (
                                <option key={source.id} value={source.id}>{source.label} ({source.count})</option>
                            ))}
                        </select>
                    </label>
                    <label className="inline-flex h-9 items-center gap-1.5 rounded-md border border-[#dadce0] dark:border-[#3c4043] bg-white dark:bg-[#202124] px-2 text-sm text-[#4d5156] dark:text-[#bdc1c6]">
                        <ListFilter size={14} aria-hidden="true" />
                        <span className="sr-only">类型筛选</span>
                        <select
                            value={filters.facet || 'all'}
                            onChange={event => onFiltersChange({ facet: event.target.value as FacetFilter })}
                            className="bg-transparent text-sm outline-none"
                            aria-label="类型筛选"
                        >
                            <option value="all">全部类型</option>
                            {facetOptions.map(facet => (
                                <option key={facet.id} value={facet.id}>{FACET_LABELS[facet.id]} ({facet.count})</option>
                            ))}
                        </select>
                    </label>
                    <label className="inline-flex h-9 items-center gap-1.5 rounded-md border border-[#dadce0] dark:border-[#3c4043] bg-white dark:bg-[#202124] px-2 text-sm text-[#4d5156] dark:text-[#bdc1c6]">
                        <CalendarDays size={14} aria-hidden="true" />
                        <span className="sr-only">时间筛选</span>
                        <select
                            value={filters.dateRange || 'all'}
                            onChange={event => onFiltersChange({ dateRange: event.target.value as NonNullable<SitegraphSearchFilters['dateRange']> })}
                            className="bg-transparent text-sm outline-none"
                            aria-label="时间筛选"
                        >
                            {Object.entries(DATE_FILTER_LABELS).map(([value, label]) => (
                                <option key={value} value={value}>{label}</option>
                            ))}
                        </select>
                    </label>
                    {activeFilters ? (
                        <button
                            type="button"
                            onClick={() => onFiltersChange({ sourceId: 'all', facet: 'all', dateRange: 'all' })}
                            className="inline-flex h-9 items-center gap-1.5 rounded-md px-2 text-sm text-[#1a73e8] hover:bg-[#f1f3f4] dark:text-[#8ab4f8] dark:hover:bg-[#303134]"
                        >
                            <RotateCcw size={14} aria-hidden="true" />
                            清除筛选
                        </button>
                    ) : null}
                </div>
                <div className="mt-1 flex max-w-[880px] flex-col gap-2 text-sm text-[#70757a] dark:text-[#9aa0a6] sm:flex-row sm:items-center sm:justify-between">
                    <p>
                        {statusText}
                    </p>
                    {coverageProgress ? (
                        <div className="flex shrink-0 flex-wrap items-center gap-2 text-[12px] text-[#5f6368] dark:text-[#9aa0a6]">
                            <span className="inline-flex items-center gap-1">
                                <ShieldCheck size={14} className="text-[#188038] dark:text-[#81c995]" aria-hidden="true" />
                                {coverageProgress.label}
                            </span>
                            {coverageProgress.showBar ? (
                                <div
                                    className="h-1.5 w-28 overflow-hidden rounded-full bg-[#e8eaed] dark:bg-[#3c4043]"
                                    aria-label={`官网信息核查进度 ${coverageProgress.percent}%`}
                                    role="progressbar"
                                    aria-valuemin={0}
                                    aria-valuemax={100}
                                    aria-valuenow={coverageProgress.percent}
                                >
                                    <div
                                        className="h-full rounded-full bg-[#1a73e8] transition-[width] duration-300 ease-out dark:bg-[#8ab4f8]"
                                        style={{ width: `${coverageProgress.percent}%` }}
                                    />
                                </div>
                            ) : null}
                            <button
                                type="button"
                                onClick={() => setShowDiagnostics(value => !value)}
                                className="inline-flex items-center gap-1 text-[#1a73e8] dark:text-[#8ab4f8] hover:underline"
                            >
                                {showDiagnostics ? <ChevronUp size={14} aria-hidden="true" /> : <ChevronDown size={14} aria-hidden="true" />}
                                技术细节
                            </button>
                        </div>
                    ) : null}
                </div>
                {coverage && showDiagnostics ? (
                    <div className="mt-2 max-w-[880px] rounded-md border border-[#dadce0] dark:border-[#3c4043] bg-[#f8fafc] dark:bg-[#2d2e30] px-3 py-2 text-[13px] text-[#4d5156] dark:text-[#bdc1c6]">
                        <div className="flex flex-wrap gap-x-4 gap-y-1">
                            <span>已证明跳过 {coverage.proved_no_match_shards}</span>
                            <span>筛选排除 {coverage.excluded_by_filter_shards}</span>
                            <span>待证明 {coverage.pending_shards}</span>
                            <span>失败 {coverage.failed_shards}</span>
                            <span>已扫描 {coverage.scanned_shards}/{coverage.total_shards}</span>
                            <span>文档 {coverage.searched_documents}/{coverage.total_documents}</span>
                            <span>已加载 {formatBytes(coverage.loaded_bytes)}</span>
                            <span>新读 {formatBytes(coverage.uncached_loaded_bytes)}</span>
                            <span>缓存命中 {formatBytes(coverage.cached_artifact_bytes)} / {coverage.cache.artifact_hits}</span>
                            <span>阶段：{coverage.phase}</span>
                            <span>字段：{fieldLabel(coverage.searched_fields)}</span>
                            {queryStats ? (
                                <>
                                    <span>局部元数据兜底 {queryStats.fallbacks.localMetaFallbackDocuments}</span>
                                    <span>摘要兜底 {queryStats.fallbacks.snippetFallbackResults}</span>
                                    <span>验证命中 {queryStats.fallbacks.verifiedFullScanMatches}</span>
                                    <span>局部索引 {queryStats.loadedLocalIndexCount}</span>
                                    <span>剪枝块 {queryStats.retrieval.impactBlocksPruned}</span>
                                    <span>跳过 postings {queryStats.retrieval.postingsPruned}</span>
                                </>
                            ) : null}
                        </div>
                    </div>
                ) : null}
            </div>

            {visibleResults.length > 0 ? (
                <div>
                    {visibleResults.map(document => (
                        <SearchResultCard key={document.id} document={document} />
                    ))}
                    {visibleCount < results.length && (
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
                    <p>没有找到匹配的南邮官网信息。</p>
                    <p className="mt-2 text-sm">可以尝试“期末考试”“四六级”“计算机等级”“口语考试”“奖学金”“大创”“竞赛报名”这类学生任务关键词。</p>
                </div>
            )}
        </section>
    );
}
