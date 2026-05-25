import { useMemo } from 'react';
import { SearchDocument } from '@/types';
import { recallSearchDocuments } from '@/utils/searchIndex';

export function useSearchEngine(
    noticeDocuments: SearchDocument[],
    searchQuery: string,
    queryAliases: Record<string, unknown>
) {
    const recalledResults = useMemo(
        () => {
            const trimmed = searchQuery.trim();
            if (trimmed.length < 2) return [];
            return recallSearchDocuments(noticeDocuments, searchQuery, queryAliases);
        },
        [noticeDocuments, searchQuery, queryAliases]
    );

    return {
        recalledResults,
        learningResources: [] as SearchDocument[]
    };
}
