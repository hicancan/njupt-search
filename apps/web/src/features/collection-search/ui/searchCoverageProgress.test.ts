import { describe, expect, it } from 'vitest';
import type { SitegraphSearchCoverage } from '@/shared/lib/contracts';
import { getSearchCoverageProgress } from './searchCoverageProgress';

const coverage = (partial: Partial<SitegraphSearchCoverage>): SitegraphSearchCoverage => ({
    phase: 'verify_progress',
    searched_fields: [],
    proved_no_match_shards: 0,
    scanned_shards: 0,
    total_shards: 100,
    searched_documents: 0,
    total_documents: 1000,
    loaded_bytes: 0,
    used_body_index: true,
    exhaustive_complete: false,
    ...partial,
});

describe('getSearchCoverageProgress', () => {
    it('counts skipped and scanned shards as verified coverage', () => {
        expect(getSearchCoverageProgress(coverage({
            proved_no_match_shards: 20,
            scanned_shards: 45,
        }))).toEqual({
            completedShards: 65,
            totalShards: 100,
            percent: 65,
            label: '已核查 65%',
        });
    });

    it('caps complete coverage at 100 percent', () => {
        expect(getSearchCoverageProgress(coverage({
            proved_no_match_shards: 70,
            scanned_shards: 50,
            exhaustive_complete: true,
        })).percent).toBe(100);
    });
});
