import { useMemo, useState, useEffect } from 'react';
import { AlertTriangle, CalendarDays, Clock, FileText, GraduationCap, LockKeyhole } from 'lucide-react';
import { ExamList } from '@/components/ExamList';
import { ExamDetail } from '@/components/ExamDetail';
import { ResultsSkeleton } from '@/components/ResultsSkeleton';
import { routeQuery } from '@/utils/queryRouter';
import { RankedSearchDocument, SearchDocument, SearchDomain, SearchIntent, SearchResult } from '@/types';
import {
    formatSearchDate,
    getDomainLabel,
    getIntentLabel,
    getLifecycleLabel,
    getSourceTypeLabel
} from '@/utils/searchIndex';

type DomainFilter = SearchDomain | '全部';
type IntentFilter = SearchIntent | '全部';

const isExternalUrl = (url: string): boolean => /^https?:\/\//.test(url);

const getRouteName = (route: string) => {
    const names: Record<string, string> = {
        exam_notice_search: '考试相关',
        class_exam_lookup: '考表查询',
        degree_defense_search: '论文答辩',
        service_search: '办事服务',
        innovation_project_search: '竞赛大创',
        scholarship_search: '奖助学金',
        campus_alert_search: '重要通知',
        resource_search: '学习资料',
        general_search: '综合查询'
    };
    return names[route] || '综合查询';
};

const getNoResultsCopy = (route: string, query: string) => {
    const fallback = {
        title: '没有找到匹配结果。',
        detail: '可以尝试“考试安排”“奖学金 公示”“停水 停电”“B250403”这类更具体的关键词。'
    };

    if (query.length < 2) return fallback;

    const routeCopies: Record<string, { title: string; detail: string }> = {
        degree_defense_search: {
            title: `我们理解你在查“${query}”。`,
            detail: '但当前索引中“研究生院-学位与答辩 / 毕业与论文”栏目暂无可用公开文档。'
        },
        cet_notice_search: {
            title: `我们理解你在查“${query}”。`,
            detail: '但当前教务处考试栏目没有可用于检索的 CET / 四六级专项公开通知。'
        },
        competition_search: {
            title: `我们理解你在查“${query}”。`,
            detail: '但当前创新创业学院竞赛栏目没有该赛事的可用公开文档。'
        }
    };

    return routeCopies[route] || fallback;
};

interface SearchResultCardProps {
    document: RankedSearchDocument | SearchDocument;
    onOpenClass: (className: string) => void;
}

function SearchResultCard({ document, onOpenClass }: SearchResultCardProps) {
    const isExam = document.kind === 'exam' && document.class_name;
    const isRestricted = document.status === 'restricted';
    const primaryTask = document.task_frames[0];
    const recallReason = (document as Partial<RankedSearchDocument>).score_reason || '';
    const attachmentChips = document.attachments
        .filter(attachment => attachment.role || attachment.sensitive)
        .slice(0, 3);
    const Wrapper = isExam ? 'button' : 'a';
    const wrapperProps = isExam
        ? {
            type: 'button' as const,
            onClick: () => onOpenClass(document.class_name || ''),
        }
        : {
            href: document.url,
            target: isExternalUrl(document.url) ? '_blank' : undefined,
            rel: isExternalUrl(document.url) ? 'noopener noreferrer' : undefined,
        };

    return (
        <Wrapper {...wrapperProps} className={`block w-full text-left py-4 group ${document.action_required ? 'border-l-[3px] border-[#f29900] pl-4 bg-[#fef7e0]/30 dark:bg-[#f29900]/10 rounded-r-md mb-2' : ''}`}>
            <div className="flex items-center gap-2 text-[14px] text-[#202124] dark:text-[#bdc1c6] mb-1">
                <span className="font-medium">{document.source}</span>
                <span className="text-[#70757a] dark:text-[#9aa0a6]">›</span>
                <span className="text-[#70757a] dark:text-[#9aa0a6] truncate">{document.channel}</span>
                <span className="text-[#70757a] dark:text-[#9aa0a6]">›</span>
                <span className="text-[#70757a] dark:text-[#9aa0a6] truncate">
                    {getDomainLabel(document.domain)} · {getIntentLabel(document.intent)}{document.sub_category ? ` · ${document.sub_category}` : ''}
                </span>
                <span className="hidden sm:inline-flex items-center h-5 px-2 rounded bg-[#f1f3f4] text-[#5f6368] dark:bg-[#303134] dark:text-[#bdc1c6] text-[11px] shrink-0">
                    {getSourceTypeLabel(document.source_type)}
                </span>
                {isExam ? (
                    <span className="ml-2 inline-flex items-center justify-center h-5 px-2 rounded text-[11px] bg-[#e8f0fe] text-[#1967d2] dark:bg-[#263850] dark:text-[#8ab4f8] shrink-0">
                        考试频道
                    </span>
                ) : null}
                {document.sensitive && (
                    <span className="ml-auto inline-flex items-center justify-center h-5 px-2 rounded text-[11px] bg-[#fce8e6] text-[#c5221f] dark:bg-[#5c1e19] dark:text-[#f28b82] shrink-0">
                        含敏感信息
                    </span>
                )}
                {isRestricted && (
                    <span className="ml-auto inline-flex items-center gap-1 h-5 px-2 rounded text-[11px] bg-[#fce8e6] text-[#c5221f] dark:bg-[#5c1e19] dark:text-[#f28b82] shrink-0">
                        <LockKeyhole size={12} />
                        校内访问
                    </span>
                )}
                {document.review_required && !isRestricted ? (
                    <span className="inline-flex items-center justify-center h-5 px-2 rounded text-[11px] bg-[#fff4e5] text-[#8c4d00] dark:bg-[#42341c] dark:text-[#fde293] shrink-0">
                        需复核
                    </span>
                ) : null}
            </div>
            <h3 className="text-[20px] leading-snug font-medium text-[#1a0dab] dark:text-[#8ab4f8] group-hover:underline break-words">
                {document.title}
            </h3>

            {primaryTask ? (
                <div className="mt-3 border border-[#dadce0] dark:border-[#3c4043] rounded-md p-3 bg-white dark:bg-[#202124]">
                    <div className="grid gap-2 text-[13px] text-[#3c4043] dark:text-[#d2d5da]">
                        <div className="flex flex-wrap gap-x-4 gap-y-1">
                            <span><span className="text-[#70757a] dark:text-[#9aa0a6]">对象：</span>{primaryTask.who.audience.join('、') || '对象待确认'}</span>
                            <span><span className="text-[#70757a] dark:text-[#9aa0a6]">任务：</span>{primaryTask.what}</span>
                        </div>
                        <div className="flex flex-wrap gap-x-4 gap-y-1">
                            <span><span className="text-[#70757a] dark:text-[#9aa0a6]">动作：</span>{primaryTask.action.summary || primaryTask.action.verb || (primaryTask.action.required ? '需要处理' : '查看信息')}</span>
                            <span><span className="text-[#70757a] dark:text-[#9aa0a6]">状态：</span>{primaryTask.time.lifecycle || document.lifecycle}</span>
                            {primaryTask.time.deadline ? (
                                <span className="text-[#c5221f] dark:text-[#f28b82]"><span className="text-[#70757a] dark:text-[#9aa0a6]">截止：</span>{primaryTask.time.deadline.substring(0, 16).replace('T', ' ')}</span>
                            ) : null}
                        </div>
                        {primaryTask.materials.length > 0 ? (
                            <div><span className="text-[#70757a] dark:text-[#9aa0a6]">材料：</span>{primaryTask.materials.slice(0, 3).map(item => item.name).join('、')}</div>
                        ) : null}
                        {primaryTask.evidence.length > 0 ? (
                            <div className="line-clamp-2"><span className="text-[#70757a] dark:text-[#9aa0a6]">证据：</span>{primaryTask.evidence[0]?.text || ''}</div>
                        ) : null}
                        <div className="flex flex-wrap gap-x-4 gap-y-1">
                            <span><span className="text-[#70757a] dark:text-[#9aa0a6]">来源：</span>{document.source} · {document.channel}</span>
                            <span><span className="text-[#70757a] dark:text-[#9aa0a6]">原文：</span>{isExternalUrl(document.url) ? '打开官网原文' : '打开详情'}</span>
                            <span><span className="text-[#70757a] dark:text-[#9aa0a6]">风险：</span>{isRestricted ? '访问受限' : document.sensitive ? '敏感信息' : document.review_required ? '需复核' : '未标记'}</span>
                        </div>
                    </div>
                </div>
            ) : null}

            <div className="mt-2 flex flex-wrap gap-1.5 text-[12px]">
                <span className="inline-flex items-center h-6 px-2 rounded bg-[#e8f0fe] text-[#1967d2] dark:bg-[#263850] dark:text-[#8ab4f8]">
                    {getDomainLabel(document.domain)}
                </span>
                <span className="inline-flex items-center h-6 px-2 rounded bg-[#e6f4ea] text-[#137333] dark:bg-[#1f3b28] dark:text-[#81c995]">
                    {getIntentLabel(document.intent)}
                </span>
                <span className="inline-flex items-center h-6 px-2 rounded bg-[#f1f3f4] text-[#5f6368] dark:bg-[#303134] dark:text-[#bdc1c6]">
                    {getLifecycleLabel(document.lifecycle)}
                </span>
            </div>

            {document.action_required && (
                <div className="mt-2.5 mb-1.5 p-3 bg-[#fef7e0] dark:bg-[#42341c] rounded border border-[#fad270]/40 dark:border-[#f29900]/20">
                    <div className="flex items-center gap-2 text-[#b06000] dark:text-[#fde293] font-medium mb-1 text-[14px]">
                        <AlertTriangle size={15} className="shrink-0" />
                        <span className="flex-shrink-0">{document.action_type || '需采取行动'}</span>
                        {document.deadline && (
                            <span className="ml-auto inline-flex items-center gap-1 text-[13px] bg-[#fce8e6] dark:bg-[#5c1e19] px-2 py-0.5 rounded text-[#c5221f] dark:text-[#f28b82]">
                                <Clock size={12} />
                                截止: {document.deadline.substring(0, 16).replace('T', ' ')}
                            </span>
                        )}
                    </div>
                    {document.action_summary && (
                        <div className="text-[13px] text-[#8c4d00] dark:text-[#f6c65b]">
                            {document.action_summary}
                        </div>
                    )}
                </div>
            )}

            {attachmentChips.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                    {attachmentChips.map(attachment => (
                        <span
                            key={`${attachment.url}-${attachment.role || attachment.name}`}
                            className={`inline-flex items-center gap-1 max-w-full h-6 px-2 rounded text-[12px] ${
                                attachment.sensitive
                                    ? 'bg-[#fce8e6] text-[#c5221f] dark:bg-[#5c1e19] dark:text-[#f28b82]'
                                    : 'bg-[#e8f0fe] text-[#1967d2] dark:bg-[#263850] dark:text-[#8ab4f8]'
                            }`}
                        >
                            <FileText size={12} className="shrink-0" />
                            <span className="truncate">{attachment.role || '附件'}</span>
                        </span>
                    ))}
                </div>
            )}

            <div className="mt-1 text-[14px] text-[#4d5156] dark:text-[#bdc1c6] line-clamp-2 break-words">
                <span className="text-[#70757a] dark:text-[#9aa0a6] font-medium mr-2">{formatSearchDate(document.published_at)}</span>
                {document.summary || document.content}
            </div>
            {recallReason || document.semantic_mode ? (
                <details className="mt-1 text-[12px] text-[#70757a] dark:text-[#9aa0a6]">
                    <summary className="cursor-pointer select-none inline-flex hover:text-[#202124] dark:hover:text-[#e8eaed]">调试信息</summary>
                    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
                    {recallReason && <span>召回依据：{recallReason}</span>}
                    {document.semantic_mode && (
                        <span>
                            语义模式：
                            <span className={`font-medium ${
                                document.semantic_mode === 'llm' ? 'text-[#188038] dark:text-[#81c995]' :
                                document.semantic_mode === 'heuristic_degraded' || document.semantic_mode === 'unprocessed' ? 'text-[#c5221f] dark:text-[#f28b82]' : 
                                'text-[#b06000] dark:text-[#fde293]'
                            }`} title={document.field_sources ? JSON.stringify(document.field_sources, null, 2) : undefined}>
                                {document.semantic_mode}
                            </span>
                        </span>
                    )}
                    </div>
                </details>
            ) : null}
        </Wrapper>
    );
}

interface ResultsViewProps {
    isLoading?: boolean;
    query: string;
    results: RankedSearchDocument[];
    resources: SearchDocument[];
    classMode: SearchResult;
    selectedIds: Set<string>;
    reminders: number[];
    onOpenClass: (className: string) => void;
    onToggleSelection: (id: string) => void;
    onRemindersChange: (reminders: number[]) => void;
    sourceUrl: string | null;
    sourceTitle: string | null;
    generatedAt: string | null;
    totalRecords: number | null;
}

export function ResultsView({
    isLoading,
    query,
    results,
    resources,
    classMode,
    selectedIds,
    reminders,
    onOpenClass,
    onToggleSelection,
    onRemindersChange,
    sourceUrl,
    sourceTitle,
    generatedAt,
    totalRecords
}: ResultsViewProps) {
    const trimmedQuery = query.trim();
    const routeInfo = useMemo(() => routeQuery(trimmedQuery), [trimmedQuery]);
    const [activeTab, setActiveTab] = useState<'all' | 'official_notice' | 'task_deadline' | 'exam' | 'resource' | 'service'>('all');
    const [domainFilter, setDomainFilter] = useState<DomainFilter>('全部');
    const [intentFilter, setIntentFilter] = useState<IntentFilter>('全部');
    const domainOptions = useMemo(() => {
        return Array.from(new Set(results.map(document => document.domain))).sort((a, b) => getDomainLabel(a).localeCompare(getDomainLabel(b), 'zh-CN'));
    }, [results]);
    const intentOptions = useMemo(() => {
        return Array.from(new Set(results.map(document => document.intent))).sort((a, b) => getIntentLabel(a).localeCompare(getIntentLabel(b), 'zh-CN'));
    }, [results]);
    const filteredResults = useMemo(() => {
        return results.filter(document => {
            if (activeTab === 'exam' && document.domain !== 'exam' && document.kind !== 'exam') return false;
            if (activeTab === 'resource' && document.kind !== 'resource' && document.domain !== 'resource' && document.source_type !== 'github_resource') return false;
            if (activeTab === 'official_notice' && document.kind !== 'notice' && document.source_type !== 'central_notice' && document.source_type !== 'central_admin' && document.domain !== 'policy' && document.domain !== 'news') return false;
            if (activeTab === 'task_deadline' && !['apply', 'register', 'submit', 'pay', 'attend'].includes(document.intent)) return false;
            if (activeTab === 'service' && !['logistics', 'campus_network', 'medical_insurance', 'archive', 'library', 'security', 'life'].includes(document.domain)) return false;
            if (domainFilter !== '全部' && document.domain !== domainFilter) return false;
            if (intentFilter !== '全部' && document.intent !== intentFilter) return false;

            // Deduplicate exams that are already visible in the calendar at the top
            if (classMode.mode === 'DETAIL' && classMode.classes.length > 0) {
                const currentClass = classMode.classes[0];
                if (document.kind === 'exam' && document.class_name === currentClass) {
                    return false;
                }
            }

            return true;
        });
    }, [activeTab, domainFilter, intentFilter, results, classMode]);
    const [visibleCount, setVisibleCount] = useState(20);
    useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setVisibleCount(20);
    }, [query, activeTab, domainFilter, intentFilter]);

    const visibleResults = filteredResults.slice(0, visibleCount);
    const hasClassDetail = classMode.mode === 'DETAIL' && classMode.exams.length > 0;
    const showSearchResultsSection = !(hasClassDetail && filteredResults.length === 0);
    const noResultsCopy = getNoResultsCopy(routeInfo.query_type, trimmedQuery);

    return (
        <main className="max-w-6xl w-full mx-auto px-4 py-6">
            {isLoading ? (
                <ResultsSkeleton />
            ) : (
            <div className="w-full">
                {classMode.mode === 'LIST' ? (
                    <section className="mt-6">
                        <ExamList classes={classMode.classes} onClassClick={onOpenClass} />
                    </section>
                ) : null}

                {classMode.mode === 'DETAIL' ? (
                    <section className="mt-6 border-b border-[#dadce0] dark:border-[#3c4043] pb-8">
                        <ExamDetail
                            className={classMode.classes[0] || ''}
                            exams={classMode.exams}
                            selectedIds={selectedIds}
                            onToggleSelection={onToggleSelection}
                            reminders={reminders}
                            onRemindersChange={onRemindersChange}
                            sourceUrl={sourceUrl}
                            sourceTitle={sourceTitle}
                            generatedAt={generatedAt}
                            totalRecords={totalRecords}
                        />
                    </section>
                ) : null}

                {resources.length > 0 ? (
                    <section className="mt-8">
                        <div className="flex items-center gap-2 mb-3">
                            <GraduationCap className="w-5 h-5 text-[#1a73e8]" aria-hidden="true" />
                            <h2 className="text-lg font-semibold text-[#202124] dark:text-[#e8eaed]">相关学习资源</h2>
                        </div>
                        <div className="grid md:grid-cols-2 gap-3">
                            {resources.map(resource => (
                                <SearchResultCard key={resource.id} document={resource} onOpenClass={onOpenClass} />
                            ))}
                        </div>
                    </section>
                ) : null}

                {trimmedQuery === '考试安排' && classMode.mode === 'NOT_FOUND' ? (
                    <section className="mt-8">
                        <div className="border border-[#dadce0] dark:border-[#3c4043] rounded-xl bg-[#f8fafc] dark:bg-[#2d2e30] p-8 text-center max-w-[692px] mx-auto shadow-sm">
                            <div className="mx-auto w-16 h-16 bg-[#e8f0fe] dark:bg-[#3b4043] rounded-full flex items-center justify-center mb-4">
                                <CalendarDays className="w-8 h-8 text-[#1a73e8] dark:text-[#8ab4f8]" aria-hidden="true" />
                            </div>
                            <h2 className="text-2xl font-semibold text-[#202124] dark:text-[#e8eaed] mb-2">🎓 考试日程助手已就绪</h2>
                            <p className="text-[15px] text-[#4d5156] dark:text-[#bdc1c6] mb-6">
                                请在顶部搜索框输入您的完整班级号（例如：<span className="font-mono bg-[#e8eaed] dark:bg-[#3c4043] px-1.5 py-0.5 rounded text-[#202124] dark:text-[#e8eaed]">B250403</span>）来获取您的专属考试日程表。
                            </p>
                            <p className="text-[13px] text-[#70757a] dark:text-[#9aa0a6]">
                                💡 提示：查询后我们将为您记住该班级，下次点击将一键直达。
                            </p>
                        </div>
                    </section>
                ) : showSearchResultsSection ? (
                    <section className="mt-8">
                        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-2 mb-4">
                            <div>
                                <h2 className="text-xl font-semibold text-[#202124] dark:text-[#e8eaed]">搜索结果</h2>
                                <div className="flex gap-4 mt-2 mb-1 border-b border-[#dadce0] dark:border-[#3c4043] overflow-x-auto whitespace-nowrap">
                                    <button onClick={() => setActiveTab('all')} className={`shrink-0 pb-2 text-sm font-medium ${activeTab === 'all' ? 'text-[#1a73e8] border-b-2 border-[#1a73e8]' : 'text-[#5f6368] hover:text-[#202124] dark:text-[#9aa0a6] dark:hover:text-[#e8eaed]'}`}>全部</button>
                                    <button onClick={() => setActiveTab('official_notice')} className={`shrink-0 pb-2 text-sm font-medium ${activeTab === 'official_notice' ? 'text-[#1a73e8] border-b-2 border-[#1a73e8]' : 'text-[#5f6368] hover:text-[#202124] dark:text-[#9aa0a6] dark:hover:text-[#e8eaed]'}`}>官方通知</button>
                                    <button onClick={() => setActiveTab('task_deadline')} className={`shrink-0 pb-2 text-sm font-medium ${activeTab === 'task_deadline' ? 'text-[#1a73e8] border-b-2 border-[#1a73e8]' : 'text-[#5f6368] hover:text-[#202124] dark:text-[#9aa0a6] dark:hover:text-[#e8eaed]'}`}>任务/截止</button>
                                    <button onClick={() => setActiveTab('exam')} className={`shrink-0 pb-2 text-sm font-medium ${activeTab === 'exam' ? 'text-[#1a73e8] border-b-2 border-[#1a73e8]' : 'text-[#5f6368] hover:text-[#202124] dark:text-[#9aa0a6] dark:hover:text-[#e8eaed]'}`}>考试</button>
                                    <button onClick={() => setActiveTab('resource')} className={`shrink-0 pb-2 text-sm font-medium ${activeTab === 'resource' ? 'text-[#1a73e8] border-b-2 border-[#1a73e8]' : 'text-[#5f6368] hover:text-[#202124] dark:text-[#9aa0a6] dark:hover:text-[#e8eaed]'}`}>资料</button>
                                    <button onClick={() => setActiveTab('service')} className={`shrink-0 pb-2 text-sm font-medium ${activeTab === 'service' ? 'text-[#1a73e8] border-b-2 border-[#1a73e8]' : 'text-[#5f6368] hover:text-[#202124] dark:text-[#9aa0a6] dark:hover:text-[#e8eaed]'}`}>服务</button>
                                </div>
                                <p className="mt-1 text-sm text-[#70757a] dark:text-[#9aa0a6]">
                                    {trimmedQuery.length >= 2
                                        ? `当前理解：${getRouteName(routeInfo.query_type)} | 找到 ${filteredResults.length} 条结果`
                                        : '未输入关键词时展示近期高价值校园信息。'}
                                </p>
                            </div>
                            <div className="flex flex-wrap gap-2">
                                <select
                                    value={domainFilter}
                                    onChange={event => setDomainFilter(event.target.value as DomainFilter)}
                                    className="h-9 rounded border border-[#dadce0] dark:border-[#3c4043] bg-white dark:bg-[#202124] px-3 text-sm text-[#202124] dark:text-[#e8eaed]"
                                    aria-label="按事务领域筛选"
                                >
                                    <option value="全部">全部领域</option>
                                    {domainOptions.map(domain => (
                                        <option key={domain} value={domain}>{getDomainLabel(domain)}</option>
                                    ))}
                                </select>
                                <select
                                    value={intentFilter}
                                    onChange={event => setIntentFilter(event.target.value as IntentFilter)}
                                    className="h-9 rounded border border-[#dadce0] dark:border-[#3c4043] bg-white dark:bg-[#202124] px-3 text-sm text-[#202124] dark:text-[#e8eaed]"
                                    aria-label="按动作类型筛选"
                                >
                                    <option value="全部">全部动作</option>
                                    {intentOptions.map(intent => (
                                        <option key={intent} value={intent}>{getIntentLabel(intent)}</option>
                                    ))}
                                </select>
                            </div>
                        </div>

                        {visibleResults.length > 0 ? (
                            <div className="space-y-3">
                                {visibleResults.map(document => (
                                    <SearchResultCard key={document.id} document={document} onOpenClass={onOpenClass} />
                                ))}
                                {visibleCount < filteredResults.length && (
                                    <div className="pt-4 pb-2 text-center">
                                        <button 
                                            onClick={() => setVisibleCount(v => v + 20)}
                                            className="px-6 py-2 rounded-full border border-[#dadce0] dark:border-[#3c4043] bg-white dark:bg-[#202124] text-sm font-medium text-[#1a73e8] hover:bg-[#f8f9fa] dark:hover:bg-[#303134] transition-colors"
                                        >
                                            加载更多
                                        </button>
                                    </div>
                                )}
                            </div>
                        ) : (
                            <div className="border border-[#dadce0] dark:border-[#3c4043] rounded-md bg-white dark:bg-[#202124] p-6 text-[#4d5156] dark:text-[#bdc1c6] max-w-[692px]">
                                <p>{noResultsCopy.title}</p>
                                <p className="mt-2 text-sm">{noResultsCopy.detail}</p>
                            </div>
                        )}
                    </section>
                ) : null}
            </div>
            )}
        </main>
    );
}
