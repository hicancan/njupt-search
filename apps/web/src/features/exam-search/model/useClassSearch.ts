import { useMemo } from 'react';
import { getClassSearchResult } from '@/features/query-router/model/examQuery';
import type { Exam, SearchResult } from '@/shared/lib/contracts';

export { getClassSearchResult };

export const useClassSearch = (
    exams: Exam[],
    inputValue: string,
    manualSelection: string | null
): SearchResult => {
    return useMemo(
        () => getClassSearchResult(exams, inputValue, manualSelection),
        [exams, inputValue, manualSelection]
    );
};
