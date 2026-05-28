import type { SitegraphSearchCoverage } from '@/shared/lib/contracts';

export interface SearchCoverageProgress {
    completedShards: number;
    totalShards: number;
    percent: number;
    label: string;
}

export function getSearchCoverageProgress(coverage: SitegraphSearchCoverage): SearchCoverageProgress {
    const totalShards = Math.max(0, coverage.total_shards);
    const completedShards = Math.min(
        totalShards,
        Math.max(0, coverage.scanned_shards) + Math.max(0, coverage.proved_no_match_shards)
    );
    const percent = totalShards > 0
        ? Math.min(100, Math.max(0, Math.round(completedShards / totalShards * 100)))
        : 0;

    return {
        completedShards,
        totalShards,
        percent: coverage.exhaustive_complete ? 100 : percent,
        label: coverage.exhaustive_complete ? '已全量核查' : `已核查 ${percent}%`,
    };
}
