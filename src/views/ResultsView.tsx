import { GraduationCap } from 'lucide-react';
import { ExamList } from '@/components/ExamList';
import { ExamDetail } from '@/components/ExamDetail';
import { SearchCategory, RankedSearchDocument, SearchDocument, SearchResult } from '@/types';
import { getCategoryOrder, formatSearchDate } from '@/utils/searchIndex';

type CategoryFilter = SearchCategory | '全部';

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
        <Wrapper {...wrapperProps} className="block w-full text-left py-4 group">
            <div className="flex items-center gap-2 text-[14px] text-[#202124] dark:text-[#bdc1c6] mb-1">
                <span className="font-medium">{document.source}</span>
                <span className="text-[#70757a] dark:text-[#9aa0a6]">›</span>
                <span className="text-[#70757a] dark:text-[#9aa0a6] truncate">{document.category}</span>
                {isExam ? (
                    <span className="ml-2 inline-flex items-center justify-center h-5 px-2 rounded text-[11px] bg-[#e8f0fe] text-[#1967d2] dark:bg-[#263850] dark:text-[#8ab4f8] shrink-0">
                        考试频道
                    </span>
                ) : null}
            </div>
            <h3 className="text-[20px] leading-snug font-medium text-[#1a0dab] dark:text-[#8ab4f8] group-hover:underline break-words">
                {document.title}
            </h3>
            <div className="mt-1 text-[14px] text-[#4d5156] dark:text-[#bdc1c6]">
                <span className="text-[#70757a] dark:text-[#9aa0a6] font-medium mr-2">{formatSearchDate(document.published_at)}</span>
                <span className="line-clamp-2 inline">
                    {document.summary || document.content}
                </span>
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
    const visibleResults = results.slice(0, 30);

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

                <section className="mt-8">
                    <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-2 mb-4">
                        <div>
                            <h2 className="text-xl font-semibold text-[#202124] dark:text-[#e8eaed]">搜索结果</h2>
                            <p className="mt-1 text-sm text-[#70757a] dark:text-[#9aa0a6]">
                                {trimmedQuery.length >= 2
                                    ? `“${trimmedQuery}” 找到 ${results.length} 条结果，按相关度和时间排序。`
                                    : '未输入关键词时展示当前频道的最新高价值内容。'}
                            </p>
                        </div>
                    </div>

                    {visibleResults.length > 0 ? (
                        <div className="space-y-3">
                            {visibleResults.map(document => (
                                <SearchResultCard key={document.id} document={document} onOpenClass={onOpenClass} />
                            ))}
                        </div>
                    ) : (
                        <div className="border border-[#dadce0] dark:border-[#3c4043] rounded-md bg-white dark:bg-[#202124] p-6 text-[#4d5156] dark:text-[#bdc1c6] max-w-[692px]">
                            <p>没有找到匹配结果。</p>
                            <p className="mt-2 text-sm">可以尝试“考试安排”“奖学金 公示”“停水 停电”“B250403”这类更具体的关键词。</p>
                        </div>
                    )}
                </section>
            </div>
        </main>
    );
}
