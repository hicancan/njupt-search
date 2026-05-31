import type { SitegraphSearchCoverage } from '@/shared/lib/contracts';

export interface SearchCoverageProgress {
    completedShards: number;
    totalShards: number;
    percent: number;
    label: string;
    complete: boolean;
    showBar: boolean;
}

export function getSearchCoverageProgress(coverage: SitegraphSearchCoverage): SearchCoverageProgress {
    const totalShards = Math.max(0, coverage.total_shards);
    const completedShards = Math.min(
        totalShards,
        Math.max(0, coverage.scanned_shards) + Math.max(0, coverage.proved_no_match_shards)
            + Math.max(0, coverage.excluded_by_filter_shards)
            + Math.max(0, coverage.excluded_by_declared_scope_shards)
    );
    const percent = totalShards > 0
        ? Math.min(100, Math.max(0, Math.round(completedShards / totalShards * 100)))
        : 0;

    const failed = Math.max(0, coverage.failed_shards);
    const pending = Math.max(0, coverage.pending_shards);
    const completeLabel = coverage.scope === 'scoped' ? '筛选范围账本已闭合' : '全站账本已闭合';
    const activeLabel = failed > 0
        ? `账本异常 ${failed} 个分片`
        : pending > 0
            ? `证明账本 ${percent}%`
            : `证明账本 ${percent}%`;

    return {
        completedShards,
        totalShards,
        percent: coverage.exhaustive_complete ? 100 : percent,
        label: coverage.exhaustive_complete ? completeLabel : activeLabel,
        complete: coverage.exhaustive_complete,
        showBar: !coverage.exhaustive_complete,
    };
}
