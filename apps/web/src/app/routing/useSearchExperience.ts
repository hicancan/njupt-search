import { useEffect, useState } from 'react';
import { useProgressiveSearch } from '@/features/collection-search/model/useProgressiveSearch';
import { useSearchIndexWorker } from '@/features/collection-search/model/useSearchIndexWorker';
import { useClassSearch } from '@/features/exam-search/model/useClassSearch';
import { useExamData } from '@/features/exam-search/model/useExamData';
import { useSelectedExamIds } from '@/features/exam-search/model/useSelectedExamIds';
import {
    isClassLookupQuery,
    isCompleteClassQuery,
    isExamHelperQuery,
    normalizeClassQuery,
} from '@/features/query-router/model/examQuery';
import { useUrlState } from '@/features/query-router/model/useUrlState';
import { useDataUpdateNotifier } from '@/widgets/update-notifier/model/useDataUpdateNotifier';

export function useSearchExperience() {
    const { classParam, qParam, navigate } = useUrlState();

    const initialQuery = classParam || qParam || '';
    const isHome = !classParam && !qParam;
    const isExamRoute = Boolean(classParam) || isExamHelperQuery(qParam || '') || isClassLookupQuery(qParam || '');
    const needsExamData = Boolean(classParam) || isClassLookupQuery(qParam || '');
    const shouldSearchSitegraph = Boolean(qParam && !isExamRoute && qParam.trim().length >= 2);
    const searchQuery = shouldSearchSitegraph ? qParam || '' : '';
    const manualSelection = classParam;

    const { exams: allExams, loading: examLoading, error: examError, sourceUrl, sourceTitle, generatedAt, totalRecords } = useExamData(needsExamData);
    const { newDataAvailable, reloadToUpdate } = useDataUpdateNotifier();
    const [inputValue, setInputValue] = useState<string>(initialQuery);
    const [reminders, setReminders] = useState<number[]>([30, 60]);
    const { worker: searchWorker, loading: searchLoading, error: searchIndexError } = useSearchIndexWorker(shouldSearchSitegraph);

    const {
        recalledResults,
        queryStats,
        queryCoverage,
        searchPhase,
        searching,
        searchError: sitegraphSearchError,
    } = useProgressiveSearch(searchWorker, searchQuery, shouldSearchSitegraph);
    const classSearchResult = useClassSearch(allExams, initialQuery, manualSelection);
    const currentClass = classSearchResult.mode === 'DETAIL' ? classSearchResult.classes[0] || null : null;
    const { selectedIds, toggleExamSelection } = useSelectedExamIds(currentClass, classSearchResult.exams);

    useEffect(() => {
        // URL navigation is the external source of truth here; keep the controlled search box in sync.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setInputValue(classParam || qParam || '');
    }, [classParam, qParam]);

    useEffect(() => {
        if (classSearchResult.mode === 'DETAIL' && currentClass && classSearchResult.exams.length > 0) {
            localStorage.setItem('SAVED_CLASS', currentClass);
            if (classParam !== currentClass) {
                navigate({ class: currentClass, q: null }, true);
            }
        }
    }, [classSearchResult.exams.length, classSearchResult.mode, currentClass, navigate, classParam]);

    const handleInputChange = (value: string) => {
        setInputValue(value);
    };

    const handleOpenClass = (className: string) => {
        if (!className) return;
        localStorage.setItem('SAVED_CLASS', className.toUpperCase());
        navigate({ class: className.toUpperCase(), q: null });
    };

    const handleSearchSubmit = (value: string) => {
        const trimmed = value.trim();
        if (trimmed.length >= 2) {
            if (isCompleteClassQuery(trimmed)) {
                navigate({ class: normalizeClassQuery(trimmed), q: null });
                return;
            }
            navigate({ q: trimmed, class: null });
        } else {
            navigate({ q: null, class: null });
        }
    };

    const handleQuickSearch = (nextQuery: string) => {
        if (nextQuery === '考试安排') {
            const savedClass = localStorage.getItem('SAVED_CLASS');
            if (savedClass) {
                handleOpenClass(savedClass);
                return;
            }
        }
        navigate({ q: nextQuery, class: null });
    };

    const handleGoHome = () => {
        navigate({ class: null, q: null });
    };

    const searchError = searchIndexError || sitegraphSearchError;
    const activeExamError = needsExamData ? examError : null;
    const activeSearchError = shouldSearchSitegraph ? searchError : null;
    const displayedError = activeSearchError || activeExamError;
    const isLoading = needsExamData
        ? examLoading
        : shouldSearchSitegraph && (searchLoading || (searching && recalledResults.length === 0));
    const blockingError = activeExamError && activeSearchError
        ? { examError: activeExamError, searchError: activeSearchError }
        : null;

    return {
        isHome,
        blockingError,
        displayedError,
        header: {
            inputValue,
            onInputChange: handleInputChange,
            onSubmit: handleSearchSubmit,
            onGoHome: handleGoHome,
        },
        home: {
            inputValue,
            onQuickSearch: handleQuickSearch,
            onInputChange: handleInputChange,
            onSubmit: handleSearchSubmit,
        },
        results: {
            isLoading,
            query: initialQuery,
            results: recalledResults,
            queryStats,
            queryCoverage,
            searchPhase,
            searching,
            classMode: classSearchResult,
            selectedIds,
            reminders,
            onOpenClass: handleOpenClass,
            onToggleSelection: toggleExamSelection,
            onRemindersChange: setReminders,
            sourceUrl,
            sourceTitle,
            generatedAt,
            totalRecords,
        },
        updateToast: {
            visible: newDataAvailable,
            onRefresh: reloadToUpdate,
        },
    };
}
