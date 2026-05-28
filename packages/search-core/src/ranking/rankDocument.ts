import type { RankedSitegraphDocument, SitegraphFullDocument } from '@njupt-search/contracts';
import { detectQueryIntent, SEARCH_INTENT_CONFIG, sourceIdForDocument } from '../intent/queryIntent';
import { normalizeSearchText as normalize } from '../tokenizer';

export const SITEGRAPH_FIELD_WEIGHTS: Record<string, number> = SEARCH_INTENT_CONFIG.field_weights;

const textBlob = (document: SitegraphFullDocument, fields: Array<keyof SitegraphFullDocument>): string => {
    const values: string[] = [];
    for (const field of fields) {
        const value = document[field];
        if (Array.isArray(value)) values.push(...value.map(String));
        else if (value !== null && value !== undefined) values.push(String(value));
    }
    return normalize(values.join(' '));
};

const attachmentBlob = (document: SitegraphFullDocument): string => normalize(
    document.attachments
        .map(attachment => [attachment.name, attachment.extension, attachment.section, attachment.parent_url].filter(Boolean).join(' '))
        .join(' ')
);

export const dateSortValue = (dateLike: string | null | undefined): number => {
    if (!dateLike) return 0;
    const date = new Date(dateLike);
    return Number.isNaN(date.getTime()) ? 0 : date.getTime();
};

export const rankingDateSortValue = (document: SitegraphFullDocument): number => {
    return dateSortValue(document.published_at) || dateSortValue(document.version_date);
};

const ageDays = (timestamp: number): number => Math.max(0, (Date.now() - timestamp) / 86_400_000);

const decayedFreshness = (timestamp: number, maxScore: number, horizonDays: number): number => {
    if (!timestamp) return 0;
    return Math.max(0, maxScore - Math.min(ageDays(timestamp), horizonDays) / horizonDays * maxScore);
};

const freshnessScore = (document: SitegraphFullDocument, freshnessMode: ReturnType<typeof detectQueryIntent>['freshnessMode']): number => {
    const config = SEARCH_INTENT_CONFIG.ranking.freshness[freshnessMode];
    if (!config) return 0;
    if (freshnessMode === 'official_entry') {
        return document.facet === 'system' ? Number(config.system_facet_score || 0) : 0;
    }
    const timestamp = freshnessMode === 'form_version'
        ? dateSortValue(document.version_date) || dateSortValue(document.published_at)
        : dateSortValue(document.published_at) || dateSortValue(document.version_date);
    return decayedFreshness(
        timestamp,
        Number(config.max_score || 0),
        Number(config.horizon_days || 3650)
    );
};

const stalePenalty = (document: SitegraphFullDocument, freshnessMode: ReturnType<typeof detectQueryIntent>['freshnessMode']): number => {
    const penaltyConfig = SEARCH_INTENT_CONFIG.ranking.stale_penalty;
    if (!penaltyConfig.modes.includes(freshnessMode)) return 0;
    const value = dateSortValue(document.published_at) || dateSortValue(document.version_date);
    if (!value) return 0;
    const days = ageDays(value);
    for (const threshold of penaltyConfig.thresholds) {
        if (days > threshold.older_than_days) return threshold.score;
    }
    return 0;
};

const isShortLandingPage = (document: SitegraphFullDocument, normalizedQuery: string, title: string): boolean => {
    return title === normalizedQuery
        && ['workflow', 'news', 'notice_article'].includes(document.facet)
        && !dateSortValue(document.published_at)
        && normalize(document.content).length < 220;
};

export const rankSitegraphDocument = (
    document: SitegraphFullDocument,
    query: string,
    terms: string[],
    lightScore: number
): RankedSitegraphDocument => {
    const profile = detectQueryIntent(query);
    const normalizedQuery = normalize(query);
    const title = textBlob(document, ['title']);
    const canonicalTitle = textBlob(document, ['canonical_title']);
    const section = textBlob(document, ['section', 'nav_path_text']);
    const summary = textBlob(document, ['summary']);
    const content = textBlob(document, ['content']);
    const tags = textBlob(document, ['tags']);
    const attachment = attachmentBlob(document);
    const url = normalize(document.url);
    const external = document.record_type === 'external' ? normalize(`${document.title} ${document.url} ${document.summary}`) : '';
    const sourceId = sourceIdForDocument(document);
    const taskKind = normalize(document.task_kind || '');
    const textWeights = SEARCH_INTENT_CONFIG.ranking.text_match;
    const termWeights = SEARCH_INTENT_CONFIG.ranking.term_match;
    const authorityWeights = SEARCH_INTENT_CONFIG.ranking.authority;
    let score = lightScore;
    const reasons: string[] = [];

    if (normalizedQuery && (title === normalizedQuery || canonicalTitle === normalizedQuery)) {
        score += document.facet === 'system'
            ? textWeights.system_title_exact
            : textWeights.title_exact;
        reasons.push('标题精确');
    } else if (normalizedQuery && (title.includes(normalizedQuery) || canonicalTitle.includes(normalizedQuery))) {
        score += textWeights.title_contains;
        reasons.push('标题包含');
        if (normalizedQuery.length >= textWeights.long_query_min_length) {
            score += textWeights.long_query_title_contains_extra;
            reasons.push('标题短语命中');
        }
    }
    if (normalizedQuery && attachment.includes(normalizedQuery)) {
        score += textWeights.attachment_contains;
        reasons.push('附件名命中');
    }
    if (normalizedQuery && external.includes(normalizedQuery)) {
        score += textWeights.external_contains;
        reasons.push('外部入口命中');
    }
    if (normalizedQuery && url.includes(normalizedQuery)) {
        score += textWeights.url_contains;
        reasons.push('URL 命中');
    }
    if (normalizedQuery && section.includes(normalizedQuery)) {
        score += textWeights.section_contains;
        reasons.push('栏目路径命中');
    }
    if (normalizedQuery && content.includes(normalizedQuery)) {
        score += textWeights.content_contains;
        reasons.push('正文命中');
    }
    if (normalizedQuery && tags.includes(normalizedQuery)) {
        score += textWeights.tags_contains;
        reasons.push('标签命中');
    }

    const matchedTerms: string[] = [];
    for (const term of terms.slice(0, 12)) {
        if (title.includes(term) || canonicalTitle.includes(term)) {
            score += termWeights.title;
            matchedTerms.push(term);
        } else if (attachment.includes(term)) {
            score += termWeights.attachment;
            matchedTerms.push(term);
        } else if (external.includes(term)) {
            score += termWeights.external;
            matchedTerms.push(term);
        } else if (url.includes(term)) {
            score += termWeights.url;
            matchedTerms.push(term);
        } else if (section.includes(term)) {
            score += termWeights.section;
            matchedTerms.push(term);
        } else if (summary.includes(term) || content.includes(term)) {
            score += termWeights.summary_or_content;
            matchedTerms.push(term);
        }
    }
    if (matchedTerms.length > 0) {
        reasons.push(`词项：${Array.from(new Set(matchedTerms)).sort((a, b) => b.length - a.length).slice(0, 6).join('、')}`);
    }

    if (profile.authoritySources.includes(sourceId)) {
        score += profile.intent === 'broad_exploratory'
            ? authorityWeights.broad_source_boost
            : authorityWeights.focused_source_boost;
        reasons.push('权威来源');
    } else if (profile.authoritySources.length === 1 && profile.intent !== 'broad_exploratory') {
        score -= authorityWeights.single_source_miss_penalty;
    }
    for (const boost of SEARCH_INTENT_CONFIG.ranking.facet_boosts) {
        if (document.facet === boost.facet && boost.intents.includes(profile.intent)) {
            score += boost.score;
            reasons.push(boost.reason);
        }
    }
    if (taskKind === normalize(profile.intent)) {
        score += SEARCH_INTENT_CONFIG.ranking.task_kind_match;
        reasons.push('任务匹配');
    }

    const freshness = freshnessScore(document, profile.freshnessMode);
    if (freshness > 0) {
        score += freshness;
        const freshnessConfig = SEARCH_INTENT_CONFIG.ranking.freshness[profile.freshnessMode];
        reasons.push(String(freshnessConfig?.reason || '时间较新'));
    }
    const penalty = stalePenalty(document, profile.freshnessMode);
    if (penalty > 0) {
        score -= penalty;
        reasons.push('历史内容降权');
    }
    if (profile.intent === 'academic_policy' && isShortLandingPage(document, normalizedQuery, title)) {
        score -= SEARCH_INTENT_CONFIG.ranking.short_landing_page_penalty;
        reasons.push('短入口降权');
    }
    if (profile.intent === 'scholarship_aid' && title.includes(normalize('学业困难')) && !title.includes(normalize('家庭经济困难'))) {
        score -= SEARCH_INTENT_CONFIG.ranking.scholarship_non_financial_hardship_penalty;
        reasons.push('非资助困难降权');
    }

    return {
        ...document,
        score,
        score_reason: reasons.join('；') || '倒排候选'
    };
};
