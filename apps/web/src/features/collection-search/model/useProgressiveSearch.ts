import { useEffect, useState } from 'react';
import {
    RankedSitegraphDocument,
    SitegraphQueryStats,
    SitegraphSearchCoverage,
    SitegraphSearchPhase
} from '@/shared/lib/contracts';

type SearchState = {
    query: string;
    results: RankedSitegraphDocument[];
    stats: SitegraphQueryStats | null;
    coverage: SitegraphSearchCoverage | null;
    phase: SitegraphSearchPhase | null;
    error: string | null;
    settled: boolean;
};

export function useProgressiveSearch(
    worker: Worker | null,
    searchQuery: string,
    enabled = true
) {
    const [searchState, setSearchState] = useState<SearchState>({
        query: '',
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
                    query: requestQuery,
                    results: message.results || previous.results,
                    stats: message.stats || previous.stats,
                    coverage: message.coverage || previous.coverage,
                    phase,
                    error: null,
                    settled: phase === 'exhaustive_complete' || phase === 'cancelled'
                }));
            } else if (message.type === 'error') {
                setSearchState({
                    query: requestQuery,
                    results: [],
                    stats: null,
                    coverage: message.coverage || null,
                    phase: 'error',
                    error: message.message || '搜索 JWC sitegraph 失败',
                    settled: true
                });
            }
        };

        worker.addEventListener('message', handleMessage);
        worker.postMessage({ type: 'query', requestId, query: requestQuery, limit: 30 });

        return () => {
            active = false;
            worker.removeEventListener('message', handleMessage);
            worker.postMessage({ type: 'cancel', requestId });
        };
    }, [enabled, worker, trimmed]);

    const isCurrentResult = canSearch && searchState.query === trimmed;

    return {
        recalledResults: isCurrentResult ? searchState.results : [],
        queryStats: isCurrentResult ? searchState.stats : null,
        queryCoverage: isCurrentResult ? searchState.coverage : null,
        searchPhase: isCurrentResult ? searchState.phase : null,
        searching: canSearch ? !(isCurrentResult && searchState.settled) : false,
        searchError: isCurrentResult ? searchState.error : null
    };
}
