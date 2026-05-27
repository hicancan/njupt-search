import { CalendarDays } from 'lucide-react';
import { CollectionSearchSection } from '@/features/collection-search/ui/CollectionSearchSection';
import { ExamDetail } from '@/features/exam-search/ui/ExamDetail';
import { ExamList } from '@/features/exam-search/ui/ExamList';
import { ResultsSkeleton } from '@/widgets/app-shell/ResultsSkeleton';
import {
    RankedSitegraphDocument,
    SearchResult,
    SitegraphQueryStats,
    SitegraphSearchCoverage,
    SitegraphSearchPhase,
} from '@/shared/lib/contracts';

interface ResultsPageProps {
    isLoading?: boolean;
    query: string;
    results: RankedSitegraphDocument[];
    queryStats: SitegraphQueryStats | null;
    queryCoverage: SitegraphSearchCoverage | null;
    searchPhase: SitegraphSearchPhase | null;
    searching: boolean;
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

export function ResultsPage({
    isLoading,
    query,
    results,
    queryStats,
    queryCoverage,
    searchPhase,
    searching,
    classMode,
    selectedIds,
    reminders,
    onOpenClass,
    onToggleSelection,
    onRemindersChange,
    sourceUrl,
    sourceTitle,
    generatedAt,
    totalRecords,
}: ResultsPageProps) {
    const trimmedQuery = query.trim();
    const hasClassDetail = classMode.mode === 'DETAIL' && classMode.exams.length > 0;
    const showSearchResultsSection = !(hasClassDetail && results.length === 0);

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

                    {trimmedQuery === '考试安排' && classMode.mode === 'NOT_FOUND' ? (
                        <section className="mt-8">
                            <div className="border border-[#dadce0] dark:border-[#3c4043] rounded-xl bg-[#f8fafc] dark:bg-[#2d2e30] p-8 text-center max-w-[692px] mx-auto shadow-sm">
                                <div className="mx-auto w-16 h-16 bg-[#e8f0fe] dark:bg-[#3b4043] rounded-full flex items-center justify-center mb-4">
                                    <CalendarDays className="w-8 h-8 text-[#1a73e8] dark:text-[#8ab4f8]" aria-hidden="true" />
                                </div>
                                <h2 className="text-2xl font-semibold text-[#202124] dark:text-[#e8eaed] mb-2">考试日程助手已就绪</h2>
                                <p className="text-[15px] text-[#4d5156] dark:text-[#bdc1c6] mb-6">
                                    请在顶部搜索框输入完整班级号，例如 <span className="font-mono bg-[#e8eaed] dark:bg-[#3c4043] px-1.5 py-0.5 rounded text-[#202124] dark:text-[#e8eaed]">B250403</span>。
                                </p>
                            </div>
                        </section>
                    ) : showSearchResultsSection ? (
                        <CollectionSearchSection
                            query={query}
                            results={results}
                            queryStats={queryStats}
                            queryCoverage={queryCoverage}
                            searchPhase={searchPhase}
                            searching={searching}
                        />
                    ) : null}
                </div>
            )}
        </main>
    );
}
