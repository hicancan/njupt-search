import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, Code, Download } from 'lucide-react';
import { UptimeDisplay } from '@/components/UptimeDisplay';
import { APP_CONFIG } from '@/constants';
import { useExamData } from '@/hooks/useExamData';
import { useClassSearch } from '@/hooks/useClassSearch';
import { useSelectedExamIds } from '@/hooks/useSelectedExamIds';
import { useDataUpdateNotifier } from '@/hooks/useDataUpdateNotifier';
import { useSearchIndex } from '@/hooks/useSearchIndex';
import { SearchCategory } from '@/types';
import { buildExamDocuments, getLearningResources, rankSearchDocuments } from '@/utils/searchIndex';

import { Header } from '@/components/Header';
import { LoadingScreen } from '@/components/LoadingScreen';
import { HomeView } from '@/views/HomeView';
import { ResultsView } from '@/views/ResultsView';

type CategoryFilter = SearchCategory | '全部';

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

    useEffect(() => {
        const handlePopState = () => {
            const urlParams = new URLSearchParams(window.location.search);
            const classParam = urlParams.get('class')?.toUpperCase();
            const qParam = urlParams.get('q');
            
            setInputValue(classParam || qParam || '');
            setSearchQuery(classParam || qParam || '');
            setManualSelection(classParam || null);
            setSelectedCategory(classParam ? '考试' : '全部');
            setIsHomeState(!classParam && !qParam);
        };

        window.addEventListener('popstate', handlePopState);
        return () => window.removeEventListener('popstate', handlePopState);
    }, []);

    const handleInputChange = (value: string) => {
        setInputValue(value);
    };

    const handleSearchSubmit = (value: string) => {
        const trimmed = value.trim();
        const nextUrl = trimmed.length >= 2 ? `${window.location.pathname}?${new URLSearchParams({ q: trimmed }).toString()}` : window.location.pathname;
        if (window.location.search !== new URLSearchParams(nextUrl.split('?')[1] || '').toString()) {
            window.history.pushState(null, '', nextUrl);
        }
        setSearchQuery(value);
        setIsHomeState(false);
        if (manualSelection && value.toUpperCase() !== manualSelection) {
            setManualSelection(null);
        }
    };

    const handleQuickSearch = (nextQuery: string, category: CategoryFilter) => {
        const nextUrl = `${window.location.pathname}?${new URLSearchParams({ q: nextQuery }).toString()}`;
        window.history.pushState(null, '', nextUrl);
        setInputValue(nextQuery);
        setSearchQuery(nextQuery);
        setSelectedCategory(category);
        setManualSelection(null);
        setIsHomeState(false);
    };

    const handleOpenClass = (className: string) => {
        if (!className) return;
        const nextUrl = `${window.location.pathname}?${new URLSearchParams({ class: className.toUpperCase() }).toString()}`;
        window.history.pushState(null, '', nextUrl);
        setInputValue(className.toUpperCase());
        setSearchQuery(className.toUpperCase());
        setSelectedCategory('考试');
        setManualSelection(className.toUpperCase());
        setIsHomeState(false);
    };

    const handleGoHome = () => {
        window.history.pushState(null, '', window.location.pathname);
        setInputValue('');
        setSearchQuery('');
        setSelectedCategory('全部');
        setIsHomeState(true);
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
                        <a href="https://github.com/hicancan/njupt-search/releases/latest/download/njupt-search-latest.apk" className="inline-flex items-center gap-1.5 hover:underline text-[#5f6368] dark:text-[#9aa0a6] hover:text-[#202124] dark:hover:text-[#e8eaed] transition-colors">
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
