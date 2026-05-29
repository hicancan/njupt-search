import type {
    SitegraphDocMeta,
    SitegraphFacet,
    SitegraphFilterOption,
    SitegraphFilterOptions,
    SitegraphFullDocument,
    SitegraphSearchFilters,
} from '@njupt-search/contracts';
import { searchDateSortValue } from './sitegraphDate';

const DAY_MS = 86_400_000;
const ALL_FILTER = 'all';

type FilterableDocument = SitegraphDocMeta | SitegraphFullDocument;

const normalizeFilterValue = (value: string | null | undefined): string => (value || ALL_FILTER).trim() || ALL_FILTER;

const dateRangeFloor = (dateRange: SitegraphSearchFilters['dateRange'], now: number): number => {
    if (dateRange === 'past_year') return now - 365 * DAY_MS;
    if (dateRange === 'past_3_years') return now - 3 * 365 * DAY_MS;
    if (dateRange === 'past_5_years') return now - 5 * 365 * DAY_MS;
    return 0;
};

export const sitegraphDocumentMatchesFilters = (
    document: FilterableDocument,
    filters: SitegraphSearchFilters = {},
    now = Date.now()
): boolean => {
    const sourceId = normalizeFilterValue(filters.sourceId);
    if (sourceId !== ALL_FILTER && document.source_id !== sourceId) return false;

    const facet = normalizeFilterValue(filters.facet);
    if (facet !== ALL_FILTER && document.facet !== facet) return false;

    const dateRange = filters.dateRange || ALL_FILTER;
    const sortValue = searchDateSortValue(document);
    if (dateRange === 'undated') return sortValue === 0;
    const floor = dateRangeFloor(dateRange, now);
    if (floor > 0 && sortValue < floor) return false;

    return true;
};

const countedOptions = <TId extends string>(
    counts: Map<TId, { label: string; count: number }>
): Array<SitegraphFilterOption & { id: TId }> => {
    return Array.from(counts.entries())
        .map(([id, payload]) => ({ id, label: payload.label, count: payload.count }))
        .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, 'zh-CN'));
};

export const buildSitegraphFilterOptions = (
    documents: SitegraphDocMeta[],
    sourceLabels: Record<string, string> = {}
): SitegraphFilterOptions => {
    const sources = new Map<string, { label: string; count: number }>();
    const facets = new Map<SitegraphFacet, { label: string; count: number }>();

    for (const document of documents) {
        const sourceId = document.source_id || document.source_domain || document.source || '';
        if (sourceId) {
            const existing = sources.get(sourceId);
            sources.set(sourceId, {
                label: sourceLabels[sourceId] || document.source || document.source_domain || sourceId,
                count: (existing?.count || 0) + 1,
            });
        }

        const existingFacet = facets.get(document.facet);
        facets.set(document.facet, {
            label: document.facet,
            count: (existingFacet?.count || 0) + 1,
        });
    }

    return {
        sources: countedOptions(sources),
        facets: countedOptions(facets),
    };
};
