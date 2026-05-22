import { useEffect, useMemo, useState } from 'react';
import {
    AlertCircle,
    Bell,
    BookOpen,
    CalendarDays,
    Code,
    Download,
    GraduationCap,
    Search,
    Sparkles,
    Trophy,
    Users
} from 'lucide-react';
import { ThemeToggle } from './components/ThemeToggle';
import { UptimeDisplay } from '@/components/UptimeDisplay';
import { SearchInput } from './components/SearchInput';
import { ExamList } from './components/ExamList';
import { ExamDetail } from './components/ExamDetail';
import { APP_CONFIG } from '@/constants';
import { useExamData } from '@/hooks/useExamData';
import { useClassSearch } from '@/hooks/useClassSearch';
import { useSelectedExamIds } from '@/hooks/useSelectedExamIds';
import { useDataUpdateNotifier } from '@/hooks/useDataUpdateNotifier';
import { useSearchIndex } from '@/hooks/useSearchIndex';
import { RankedSearchDocument, SearchCategory, SearchDocument } from '@/types';
import {
    buildExamDocuments,
    formatSearchDate,
    getCategoryOrder,
    getLearningResources,
    rankSearchDocuments
} from '@/utils/searchIndex';

type CategoryFilter = SearchCategory | '全部';

const QUICK_SEARCHES: { label: string; query: string; category: CategoryFilter; icon: typeof Search }[] = [
    { label: '考试安排', query: '考试安排', category: '考试', icon: CalendarDays },
    { label: '竞赛报名', query: '竞赛 报名', category: '竞赛', icon: Trophy },
    { label: '奖助公示', query: '奖学金 公示', category: '奖助', icon: Sparkles },
    { label: '招聘宣讲', query: '招聘 宣讲会', category: '就业', icon: Users },
    { label: '图书馆开放', query: '图书馆 开放', category: '生活', icon: BookOpen },
    { label: '停水停电', query: '停水 停电', category: '生活', icon: Bell },
];

const isExternalUrl = (url: string): boolean => {
    return /^https?:\/\//.test(url);
};

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
        <Wrapper
            {...wrapperProps}
            className="block w-full text-left py-4 group"
        >
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

interface HeaderProps {
    inputValue: string;
    onInputChange: (value: string) => void;
    onSubmit: (value: string) => void;
    onGoHome: () => void;
}

function Header({ inputValue, onInputChange, onSubmit, onGoHome }: HeaderProps) {
    return (
        <header className="sticky top-0 z-40 border-b border-[#dadce0] dark:border-[#3c4043] bg-white/95 dark:bg-[#202124]/95 backdrop-blur">
            <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-4">
                <button
                    type="button"
                    onClick={onGoHome}
                    className="flex items-center gap-2 shrink-0 text-left sm:w-[140px]"
                    aria-label="回到 njupt-search 首页"
                >
                    <img src="/assets/logo.png" alt="" className="w-8 h-8 rounded-md" />
                    <div className="hidden sm:block font-semibold leading-tight text-[#202124] dark:text-[#e8eaed]">
                        njupt-search
                    </div>
                </button>
                <div className="flex-1 min-w-0 max-w-[692px]">
                    <SearchInput value={inputValue} onChange={onInputChange} onSubmit={onSubmit} autoFocus={false} />
                </div>
                <ThemeToggle />
            </div>
        </header>
    );
}

function LoadingScreen() {
    return (
        <div className="min-h-screen bg-white dark:bg-[#202124] text-[#202124] dark:text-[#e8eaed]">
            <div className="max-w-6xl mx-auto px-4 py-10">
                <div className="h-10 w-52 rounded bg-white dark:bg-[#202124] border border-[#dadce0] dark:border-[#3c4043] relative overflow-hidden">
                    <div className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-[#edf2f7] dark:via-white/10 to-transparent animate-shimmer" />
                </div>
                <div className="mt-8 h-[52px] max-w-3xl rounded-full bg-white dark:bg-[#202124] border border-[#dadce0] dark:border-[#3c4043] relative overflow-hidden">
                    <div className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-[#edf2f7] dark:via-white/10 to-transparent animate-shimmer" />
                </div>
                <div className="mt-8 grid grid-cols-1 sm:grid-cols-4 gap-3">
                    {[0, 1, 2, 3].map(item => (
                        <div key={item} className="h-28 rounded-md bg-white dark:bg-[#202124] border border-[#dadce0] dark:border-[#3c4043] relative overflow-hidden">
                            <div className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-[#edf2f7] dark:via-white/10 to-transparent animate-shimmer" />
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

interface HomeViewProps {
    inputValue: string;
    onQuickSearch: (query: string, category: CategoryFilter) => void;
    onInputChange: (value: string) => void;
    onSubmit: (value: string) => void;
}

function HomeView({
    inputValue,
    onQuickSearch,
    onInputChange,
    onSubmit
}: HomeViewProps) {
    return (
        <main className="flex-1 px-4">
            <div className="max-w-6xl mx-auto pt-5 flex justify-end">
                <ThemeToggle />
            </div>
            <section className="max-w-[680px] mx-auto min-h-[calc(100vh-176px)] flex flex-col items-center justify-center pb-20">
                <img src="/assets/logo.png" alt="" className="w-16 h-16 rounded-2xl" />
                <h1 className="mt-5 text-5xl sm:text-6xl font-normal text-[#202124] dark:text-[#e8eaed] leading-tight">njupt-search</h1>

                <div className="mt-8 w-full">
                    <SearchInput value={inputValue} onChange={onInputChange} onSubmit={onSubmit} />
                </div>

                <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
                    {QUICK_SEARCHES.map(item => {
                        const Icon = item.icon;
                        return (
                            <button
                                key={item.label}
                                type="button"
                                onClick={() => onQuickSearch(item.query, item.category)}
                                className="inline-flex items-center gap-2 h-10 px-4 rounded-full border border-[#dadce0] dark:border-[#3c4043] bg-white dark:bg-[#202124] text-sm text-[#3c4043] dark:text-[#e8eaed] hover:border-[#8ab4f8] transition-colors"
                            >
                                <Icon className="w-4 h-4" aria-hidden="true" />
                                {item.label}
                            </button>
                        );
                    })}
                </div>
            </section>
        </main>
    );
}

interface ResultsViewProps {
    query: string;
    selectedCategory: CategoryFilter;
    results: RankedSearchDocument[];
    resources: SearchDocument[];
    classMode: ReturnType<typeof useClassSearch>;
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

function ResultsView({
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

function App() {
    const { exams: allExams, loading: examLoading, error: examError, sourceUrl, sourceTitle, generatedAt, totalRecords } = useExamData();
    const { documents: noticeDocuments, loading: searchLoading, error: searchError } = useSearchIndex();
    const { newDataAvailable, reloadToUpdate } = useDataUpdateNotifier();

    const [inputValue, setInputValue] = useState<string>(() => {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get('class')?.toUpperCase() || urlParams.get('q') || '';
    });
    const [isHomeState, setIsHomeState] = useState<boolean>(() => {
        const urlParams = new URLSearchParams(window.location.search);
        return !urlParams.has('class') && !urlParams.has('q');
    });
    const [searchQuery, setSearchQuery] = useState<string>(() => {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get('class')?.toUpperCase() || urlParams.get('q') || '';
    });
    const [manualSelection, setManualSelection] = useState<string | null>(() => {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get('class')?.toUpperCase() || null;
    });
    const [selectedCategory, setSelectedCategory] = useState<CategoryFilter>(() => {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.has('class') ? '考试' : '全部';
    });
    const [reminders, setReminders] = useState<number[]>([30, 60]);

    const examDocuments = useMemo(() => buildExamDocuments(allExams), [allExams]);
    const allDocuments = useMemo(() => [...noticeDocuments, ...examDocuments], [noticeDocuments, examDocuments]);
    const rankedResults = useMemo(
        () => rankSearchDocuments(allDocuments, searchQuery, selectedCategory),
        [allDocuments, searchQuery, selectedCategory]
    );
    const learningResources = useMemo(() => getLearningResources(searchQuery), [searchQuery]);
    const classSearchResult = useClassSearch(allExams, searchQuery, manualSelection);
    const currentClass = classSearchResult.mode === 'DETAIL' ? classSearchResult.classes[0] || null : null;
    const { selectedIds, toggleExamSelection } = useSelectedExamIds(currentClass, classSearchResult.exams);

    useEffect(() => {
        const trimmed = searchQuery.trim();
        if (classSearchResult.mode === 'DETAIL' && currentClass && classSearchResult.exams.length > 0) {
            const nextUrl = `${window.location.pathname}?${new URLSearchParams({ class: currentClass }).toString()}`;
            window.history.replaceState(null, '', nextUrl);
        } else if (trimmed.length >= 2) {
            const nextUrl = `${window.location.pathname}?${new URLSearchParams({ q: trimmed }).toString()}`;
            window.history.replaceState(null, '', nextUrl);
        } else {
            window.history.replaceState(null, '', window.location.pathname);
        }
    }, [classSearchResult.exams.length, classSearchResult.mode, currentClass, searchQuery]);

    const handleInputChange = (value: string) => {
        setInputValue(value);
    };

    const handleSearchSubmit = (value: string) => {
        setSearchQuery(value);
        setIsHomeState(false);
        if (manualSelection && value.toUpperCase() !== manualSelection) {
            setManualSelection(null);
        }
    };

    const handleQuickSearch = (nextQuery: string, category: CategoryFilter) => {
        setInputValue(nextQuery);
        setSearchQuery(nextQuery);
        setSelectedCategory(category);
        setManualSelection(null);
        setIsHomeState(false);
    };

    const handleOpenClass = (className: string) => {
        if (!className) return;
        setInputValue(className.toUpperCase());
        setSearchQuery(className.toUpperCase());
        setSelectedCategory('考试');
        setManualSelection(className.toUpperCase());
        setIsHomeState(false);
    };

    const handleGoHome = () => {
        setInputValue('');
        setSearchQuery('');
        setSelectedCategory('全部');
        setIsHomeState(true);
        window.history.replaceState(null, '', window.location.pathname);
    };

    const isLoading = examLoading || searchLoading;
    const isHome = isHomeState;

    if (isLoading) {
        return <LoadingScreen />;
    }

    if (examError && searchError) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-[#f8fafc] dark:bg-[#171717] text-[#202124] dark:text-[#e8eaed] px-4">
                <div className="max-w-md border border-[#dadce0] dark:border-[#3c4043] rounded-md bg-white dark:bg-[#202124] p-6">
                    <AlertCircle className="w-8 h-8 text-[#d93025]" aria-hidden="true" />
                    <h1 className="mt-3 text-xl font-semibold">数据加载失败</h1>
                    <p className="mt-2 text-sm text-[#4d5156] dark:text-[#bdc1c6]">{examError}</p>
                    <p className="mt-1 text-sm text-[#4d5156] dark:text-[#bdc1c6]">{searchError}</p>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen flex flex-col bg-white dark:bg-[#202124] text-[#202124] dark:text-[#e8eaed] transition-colors duration-200 font-sans">
            {!isHome ? <Header inputValue={inputValue} onInputChange={handleInputChange} onSubmit={handleSearchSubmit} onGoHome={handleGoHome} /> : null}

            {searchError || examError ? (
                <div className="max-w-6xl mx-auto w-full px-4 pt-4">
                    <div className="border border-[#f4c7c3] dark:border-[#5f2b26] bg-[#fce8e6] dark:bg-[#2b1715] text-[#b3261e] dark:text-[#f28b82] rounded-md p-3 text-sm flex gap-2">
                        <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
                        <span>{searchError || examError}</span>
                    </div>
                </div>
            ) : null}

            {isHome ? (
                <HomeView
                    inputValue={inputValue}
                    onQuickSearch={handleQuickSearch}
                    onInputChange={handleInputChange}
                    onSubmit={handleSearchSubmit}
                />
            ) : (
                <ResultsView
                    query={searchQuery}
                    selectedCategory={selectedCategory}
                    results={rankedResults}
                    resources={learningResources}
                    classMode={classSearchResult}
                    selectedIds={selectedIds}
                    reminders={reminders}
                    onCategoryChange={setSelectedCategory}
                    onOpenClass={handleOpenClass}
                    onToggleSelection={toggleExamSelection}
                    onRemindersChange={setReminders}
                    sourceUrl={sourceUrl}
                    sourceTitle={sourceTitle}
                    generatedAt={generatedAt}
                    totalRecords={totalRecords}
                />
            )}

            <footer className="mt-auto border-t border-[#dadce0] dark:border-[#3c4043] bg-white dark:bg-[#202124] text-sm text-[#70757a] dark:text-[#9aa0a6]">
                <div className="max-w-6xl mx-auto px-4 py-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                    <div className="flex flex-wrap items-center gap-6">
                        <a href={APP_CONFIG.GITHUB_REPO} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 hover:underline text-[#5f6368] dark:text-[#9aa0a6] hover:text-[#202124] dark:hover:text-[#e8eaed] transition-colors">
                            <Code className="w-4 h-4" aria-hidden="true" />
                            GitHub
                        </a>
                        <a href={APP_CONFIG.BILIBILI_PAGE} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 hover:underline text-[#5f6368] dark:text-[#9aa0a6] hover:text-[#202124] dark:hover:text-[#e8eaed] transition-colors">
                            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                                <path d="M17.813 4.653h.854c1.51.054 2.769.657 3.773 1.811 1.004 1.154 1.515 2.649 1.536 4.485v5.23c-.021 1.84-.533 3.337-1.536 4.492-1.004 1.154-2.263 1.758-3.773 1.811H5.333c-1.51-.053-2.769-.657-3.773-1.811C.557 19.518.046 18.021.025 16.18V10.95c.021-1.836.532-3.331 1.535-4.485 1.004-1.154 2.263-1.757 3.773-1.81h.854l-1.84-2.002a.81.81 0 01-.137-.735c.05-.24.238-.41.498-.445.195-.027.391.047.525.2l2.361 2.583c.125.136.216.31.263.504h8.286c.046-.194.137-.368.262-.504l2.361-2.583c.134-.153.33-.227.525-.2.26-.035.448.135.498.376.028.14-.012.285-.107.395l-1.871 2.002zm-12.48 2.083c-1.082.02-1.954.4-2.617 1.14-.662.74-1 1.706-1.013 2.898v5.229c.013 1.192.35 2.158 1.013 2.898.663.74 1.535 1.12 2.617 1.14h13.334c1.082-.02 1.954-.4 2.617-1.14.662-.74 1-1.706 1.013-2.898V10.774c-.013-1.192-.35-2.158-1.013-2.898-.663-.74-1.535-1.12-2.617-1.14H5.333zm2.593 3.65c0-.629.566-1.139 1.263-1.139.697 0 1.263.51 1.263 1.139v1.94c0 .63-.566 1.14-1.263 1.14-.697 0-1.263-.51-1.263-1.14v-1.94zm8.258 0c0-.629.566-1.139 1.263-1.139.697 0 1.263.51 1.263 1.139v1.94c0 .63-.566 1.14-1.263 1.14-.697 0-1.263-.51-1.263-1.14v-1.94z"/>
                            </svg>
                            Bilibili
                        </a>
                        <a href="https://github.com/hicancan/njupt-exam/releases/latest/download/njupt-search-latest.apk" className="inline-flex items-center gap-1.5 hover:underline text-[#5f6368] dark:text-[#9aa0a6] hover:text-[#202124] dark:hover:text-[#e8eaed] transition-colors">
                            <Download className="w-4 h-4" aria-hidden="true" />
                            Android APK
                        </a>
                    </div>
                    <div className="flex flex-wrap items-center gap-3 text-xs sm:text-sm">
                        <UptimeDisplay />
                    </div>
                </div>
            </footer>

            {newDataAvailable && (
                <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[100] fade-in">
                    <div className="bg-[#1a73e8] text-white px-5 py-3 rounded-full shadow-lg flex items-center gap-3 text-sm font-medium whitespace-nowrap border border-transparent dark:border-[#3c4043]">
                        <span>发现最新校园索引数据</span>
                        <button
                            type="button"
                            onClick={reloadToUpdate}
                            className="bg-white text-[#1a73e8] px-4 py-1.5 rounded-full hover:bg-gray-100 transition-colors cursor-pointer"
                        >
                            立刻刷新
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}

export default App;
