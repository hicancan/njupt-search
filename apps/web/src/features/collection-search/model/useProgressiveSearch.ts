import { useEffect, useState } from 'react';
import {
    RankedSitegraphDocument,
    SitegraphQueryStats,
    SitegraphSearchCoverage,
    SitegraphSearchFilters,
    SitegraphSearchPhase,
    SitegraphSortMode
} from '@/shared/lib/contracts';
import { APP_CONFIG } from '@/app/config/constants';

type SearchState = {
    key: string;
    results: RankedSitegraphDocument[];
    stats: SitegraphQueryStats | null;
    coverage: SitegraphSearchCoverage | null;
    phase: SitegraphSearchPhase | null;
    error: string | null;
    settled: boolean;
};

interface ProgressiveSearchControls {
    sortMode?: SitegraphSortMode;
    filters?: SitegraphSearchFilters;
}

export function useProgressiveSearch(
    worker: Worker | null,
    searchQuery: string,
    enabled = true,
    controls: ProgressiveSearchControls = {}
) {
    const sortMode = controls.sortMode ?? 'relevance';
    const sourceId = controls.filters?.sourceId ?? 'all';
    const facet = controls.filters?.facet ?? 'all';
    const dateRange = controls.filters?.dateRange ?? 'all';
    const searchKey = `${searchQuery.trim()}\u0000${sortMode}\u0000${sourceId}\u0000${facet}\u0000${dateRange}`;
    const [searchState, setSearchState] = useState<SearchState>({
        key: '',
        results: [],
        stats: null,
        coverage: null,
        phase: null,
        error: null,
        settled: true
    });
    const trimmed = searchQuery.trim();
    const canSearch = Boolean(enabled && worker && trimmed.length >= 2);

    useEffect(() => {
        if (!enabled || !worker || trimmed.length < 2) {
            return;
        }

        const requestId = Date.now() + Math.floor(Math.random() * 100000);
        const requestQuery = trimmed;
        const requestKey = `${requestQuery}\u0000${sortMode}\u0000${sourceId}\u0000${facet}\u0000${dateRange}`;
        let active = true;

        const handleMessage = (event: MessageEvent) => {
            const message = event.data as {
                type?: string;
                requestId?: number;
                results?: RankedSitegraphDocument[];
                stats?: SitegraphQueryStats;
                coverage?: SitegraphSearchCoverage;
                message?: string;
            };
            if (!active || message.requestId !== requestId) return;
            const phase = message.type as SitegraphSearchPhase | undefined;
            if (phase && [
                'quick_started',
                'quick_results',
                'body_started',
                'body_results',
                'hydrate_started',
                'hydrate_results',
                'verify_started',
                'verify_progress',
                'verify_results',
                'exhaustive_complete',
                'cancelled'
            ].includes(phase)) {
                setSearchState(previous => ({
                    key: requestKey,
                    results: message.results || previous.results,
                    stats: message.stats || previous.stats,
                    coverage: message.coverage || previous.coverage,
                    phase,
                    error: null,
                    settled: phase === 'exhaustive_complete' || phase === 'cancelled'
                }));
            } else if (message.type === 'error') {
                setSearchState({
                    key: requestKey,
                    results: [],
                    stats: null,
                    coverage: message.coverage || null,
                    phase: 'error',
                    error: message.message || '搜索南邮官网信息失败',
                    settled: true
                });
            }
        };

        worker.addEventListener('message', handleMessage);
        worker.postMessage({
            type: 'query',
            requestId,
            query: requestQuery,
            limit: APP_CONFIG.COLLECTION_SEARCH_RESULT_LIMIT,
            sortMode,
            filters: {
                sourceId,
                facet,
                dateRange,
            },
        });

        return () => {
            active = false;
            worker.removeEventListener('message', handleMessage);
            worker.postMessage({ type: 'cancel', requestId });
        };
    }, [enabled, worker, trimmed, sortMode, sourceId, facet, dateRange]);

    const isCurrentResult = canSearch && searchState.key === searchKey;

    return {
        recalledResults: isCurrentResult ? searchState.results : [],
        queryStats: isCurrentResult ? searchState.stats : null,
        queryCoverage: isCurrentResult ? searchState.coverage : null,
        searchPhase: isCurrentResult ? searchState.phase : null,
        searching: canSearch ? !(isCurrentResult && searchState.settled) : false,
        searchError: isCurrentResult ? searchState.error : null
    };
}
