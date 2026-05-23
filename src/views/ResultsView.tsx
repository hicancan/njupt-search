import { useMemo, useState, useEffect } from 'react';
import { AlertTriangle, CalendarDays, Clock, FileText, GraduationCap, LockKeyhole } from 'lucide-react';
import { ExamList } from '@/components/ExamList';
import { ExamDetail } from '@/components/ExamDetail';
import { SearchCategory, RankedSearchDocument, SearchDocument, SearchDomain, SearchIntent, SearchResult } from '@/types';
import {
    getCategoryOrder,
    formatSearchDate,
    getDomainLabel,
    getIntentLabel,
    getLifecycleLabel,
    getSourceTypeLabel
} from '@/utils/searchIndex';

type CategoryFilter = SearchCategory | '全部';
type DomainFilter = SearchDomain | '全部';
type IntentFilter = SearchIntent | '全部';

const isExternalUrl = (url: string): boolean => /^https?:\/\//.test(url);

interface CategoryTabsProps {
    active: CategoryFilter;
    onChange: (category: CategoryFilter) => void;
}

function CategoryTabs({ active, onChange }: CategoryTabsProps) {
    const categories = getCategoryOrder();

    return (
        <div className="flex gap-6 overflow-x-auto pb-0 border-b border-[#dadce0] dark:border-[#3c4043] mb-4">
            <button
                type="button"
                onClick={() => onChange('全部')}
                className={`pb-3 text-sm font-medium whitespace-nowrap border-b-[3px] transition-colors ${
                    active === '全部'
                        ? 'border-[#1a73e8] text-[#1a73e8] dark:border-[#8ab4f8] dark:text-[#8ab4f8]'
                        : 'border-transparent text-[#5f6368] dark:text-[#9aa0a6] hover:text-[#202124] dark:hover:text-[#e8eaed]'
                }`}
            >
                全部
            </button>
            {categories.map(category => (
                <button
                    key={category}
                    type="button"
                    onClick={() => onChange(category)}
                    className={`pb-3 text-sm font-medium whitespace-nowrap border-b-[3px] transition-colors ${
                        active === category
                            ? 'border-[#1a73e8] text-[#1a73e8] dark:border-[#8ab4f8] dark:text-[#8ab4f8]'
                            : 'border-transparent text-[#5f6368] dark:text-[#9aa0a6] hover:text-[#202124] dark:hover:text-[#e8eaed]'
                    }`}
                >
                    {category}
                </button>
            ))}
        </div>
    );
}

interface SearchResultCardProps {
    document: RankedSearchDocument | SearchDocument;
    onOpenClass: (className: string) => void;
}

function SearchResultCard({ document, onOpenClass }: SearchResultCardProps) {
    const isExam = document.kind === 'exam' && document.class_name;
    const isRestricted = document.status === 'restricted';
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
                <span className="text-[#70757a] dark:text-[#9aa0a6] truncate">{document.category}{document.sub_category ? ` / ${document.sub_category}` : ''}</span>
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
            </div>
            <h3 className="text-[20px] leading-snug font-medium text-[#1a0dab] dark:text-[#8ab4f8] group-hover:underline break-words">
                {document.title}
            </h3>

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
        </Wrapper>
    );
}

interface ResultsViewProps {
    query: string;
    selectedCategory: CategoryFilter;
    results: RankedSearchDocument[];
    resources: SearchDocument[];
    classMode: SearchResult;
    selectedIds: Set<string>;
    reminders: number[];
    onCategoryChange: (category: CategoryFilter) => void;
    onOpenClass: (className: string) => void;
    onToggleSelection: (id: string) => void;
    onRemindersChange: (reminders: number[]) => void;
    sourceUrl: string | null;
    sourceTitle: string | null;
    generatedAt: string | null;
    totalRecords: number | null;
}

export function ResultsView({
    query,
    selectedCategory,
    results,
    resources,
    classMode,
    selectedIds,
    reminders,
    onCategoryChange,
    onOpenClass,
    onToggleSelection,
    onRemindersChange,
    sourceUrl,
    sourceTitle,
    generatedAt,
    totalRecords
}: ResultsViewProps) {
    const trimmedQuery = query.trim();
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
            if (domainFilter !== '全部' && document.domain !== domainFilter) return false;
            if (intentFilter !== '全部' && document.intent !== intentFilter) return false;
            return true;
        });
    }, [domainFilter, intentFilter, results]);
    const [visibleCount, setVisibleCount] = useState(20);
    useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setVisibleCount(20);
    }, [query, selectedCategory, domainFilter, intentFilter]);

    const visibleResults = filteredResults.slice(0, visibleCount);

    return (
        <main className="max-w-6xl w-full mx-auto px-4 py-6">
            <div className="w-full">
                <CategoryTabs active={selectedCategory} onChange={onCategoryChange} />

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

                {(trimmedQuery === '考试安排' && classMode.mode === 'NOT_FOUND') || (selectedCategory === '考试' && classMode.mode === 'NOT_FOUND' && trimmedQuery === '') ? (
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
                ) : (
                    <section className="mt-8">
                        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-2 mb-4">
                            <div>
                                <h2 className="text-xl font-semibold text-[#202124] dark:text-[#e8eaed]">搜索结果</h2>
                                <p className="mt-1 text-sm text-[#70757a] dark:text-[#9aa0a6]">
                                    {trimmedQuery.length >= 2
                                        ? `“${trimmedQuery}” 找到 ${filteredResults.length} 条结果，按相关度、任务动作和时效排序。`
                                        : '未输入关键词时展示当前频道的最新高价值内容。'}
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
                                <p>没有找到匹配结果。</p>
                                <p className="mt-2 text-sm">可以尝试“考试安排”“奖学金 公示”“停水 停电”“B250403”这类更具体的关键词。</p>
                            </div>
                        )}
                    </section>
                )}
            </div>
        </main>
    );
}
