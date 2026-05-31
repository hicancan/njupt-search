import { describe, expect, it } from 'vitest';
import type { SitegraphSearchCoverage } from '@/shared/lib/contracts';
import { getSearchCoverageProgress } from './searchCoverageProgress';

const coverage = (partial: Partial<SitegraphSearchCoverage>): SitegraphSearchCoverage => ({
    phase: 'partial_verified',
    coverage_state: 'partial_verified',
    scope: 'global',
    searched_fields: [],
    proved_no_match_shards: 0,
    scanned_shards: 0,
    excluded_by_filter_shards: 0,
    excluded_by_declared_scope_shards: 0,
    pending_shards: 100,
    failed_shards: 0,
    total_shards: 100,
    searched_documents: 0,
    total_documents: 1000,
    loaded_bytes: 0,
    first_screen_bytes: 0,
    local_index_bytes: 0,
    hydrated_shard_bytes: 0,
    used_body_index: true,
    exhaustive_complete: false,
    proof_ledger: {
        total_shards: 100,
        pending_shards: 100,
        scanned_shards: 0,
        proved_no_match_shards: 0,
        excluded_by_filter_shards: 0,
        excluded_by_declared_scope_shards: 0,
        failed_shards: 0,
        complete: false,
    },
    ...partial,
});

describe('getSearchCoverageProgress', () => {
    it('counts skipped and scanned shards as verified coverage', () => {
        expect(getSearchCoverageProgress(coverage({
            proved_no_match_shards: 20,
            scanned_shards: 45,
            pending_shards: 35,
        }))).toEqual({
            completedShards: 65,
            totalShards: 100,
            percent: 65,
            label: '证明账本 65%',
            complete: false,
            showBar: true,
        });
    });

    it('uses a compact complete state without a redundant progress bar', () => {
        expect(getSearchCoverageProgress(coverage({
            proved_no_match_shards: 70,
            scanned_shards: 50,
            pending_shards: 0,
            exhaustive_complete: true,
        }))).toEqual({
            completedShards: 100,
            totalShards: 100,
            percent: 100,
            label: '全站账本已闭合',
            complete: true,
            showBar: false,
        });
    });

    it('counts filter exclusions as closed ledger entries', () => {
        expect(getSearchCoverageProgress(coverage({
            total_shards: 20,
            scanned_shards: 4,
            proved_no_match_shards: 6,
            excluded_by_filter_shards: 8,
            pending_shards: 2,
            proof_ledger: {
                total_shards: 20,
                pending_shards: 2,
                scanned_shards: 4,
                proved_no_match_shards: 6,
                excluded_by_filter_shards: 8,
                excluded_by_declared_scope_shards: 0,
                failed_shards: 0,
                complete: false,
            },
        })).percent).toBe(90);
    });
});
