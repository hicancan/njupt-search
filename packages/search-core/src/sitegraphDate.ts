import type { SitegraphDocMeta, SitegraphFullDocument } from '@njupt-search/contracts';

type SitegraphDatedRecord = Pick<
    SitegraphDocMeta | SitegraphFullDocument,
    'published_at' | 'version_date' | 'recorded_at' | 'date_kind' | 'date_confidence'
>;

export type SitegraphResolvedDateKind = 'published' | 'version' | 'recorded' | 'undated';

export interface SitegraphResolvedDate {
    value: string | null;
    kind: SitegraphResolvedDateKind;
    label: string;
    confidence: string | null;
}

export const dateSortValue = (dateLike: string | null | undefined): number => {
    if (!dateLike) return 0;
    const date = new Date(dateLike);
    return Number.isNaN(date.getTime()) ? 0 : date.getTime();
};

export const resolveSearchDate = (document: SitegraphDatedRecord): SitegraphResolvedDate => {
    if (document.published_at) {
        return {
            value: document.published_at,
            kind: 'published',
            label: '发布日期',
            confidence: document.date_confidence || null,
        };
    }
    if (document.version_date) {
        return {
            value: document.version_date,
            kind: 'version',
            label: '版本日期',
            confidence: document.date_confidence || null,
        };
    }
    if (document.recorded_at) {
        return {
            value: document.recorded_at,
            kind: 'recorded',
            label: '收录日期',
            confidence: document.date_confidence || null,
        };
    }
    return {
        value: null,
        kind: 'undated',
        label: '日期未标注',
        confidence: document.date_confidence || document.date_kind || null,
    };
};

export const searchDateSortValue = (document: SitegraphDatedRecord): number => {
    const resolved = resolveSearchDate(document);
    return dateSortValue(resolved.value);
};

export const formatSearchDate = (dateLike: string | null | undefined): string => {
    if (!dateLike) return '日期未标注';
    const dateOnly = /^(\d{4})-(\d{2})-(\d{2})/.exec(dateLike);
    if (dateOnly) return `${dateOnly[1]}/${dateOnly[2]}/${dateOnly[3]}`;

    const date = new Date(dateLike);
    if (Number.isNaN(date.getTime())) return dateLike;

    return date.toLocaleDateString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    });
};

export const formatResolvedSearchDate = (document: SitegraphDatedRecord): string => {
    const resolved = resolveSearchDate(document);
    if (!resolved.value) return resolved.label;
    return `${resolved.label} ${formatSearchDate(resolved.value)}`;
};
