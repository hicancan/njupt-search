import type { SitegraphFullDocument } from '@njupt-search/contracts';
import { normalizeSearchText as normalize } from '../tokenizer';
import searchIntentConfig from './queryIntentProfiles.json';

export type CampusSearchIntent =
    | 'exam_schedule'
    | 'academic_calendar'
    | 'system_entry'
    | 'form_download'
    | 'academic_policy'
    | 'course_grade_credit'
    | 'scholarship_aid'
    | 'student_affairs'
    | 'innovation_entrepreneurship'
    | 'broad_exploratory';

export type FreshnessMode = 'current_notice' | 'current_term' | 'official_entry' | 'form_version' | 'current_policy' | 'balanced';

export interface QueryIntentProfile {
    intent: CampusSearchIntent;
    authoritySources: string[];
    freshnessMode: FreshnessMode;
}

type AuthoritySourcesConfig = string[] | 'dynamic_system';

interface QueryIntentRuleConfig {
    intent: CampusSearchIntent;
    authority_sources: AuthoritySourcesConfig;
    freshness_mode: FreshnessMode;
    match_any: string[];
}

interface TextMatchWeights {
    title_exact: number;
    system_title_exact: number;
    title_contains: number;
    long_query_min_length: number;
    long_query_title_contains_extra: number;
    attachment_contains: number;
    external_contains: number;
    url_contains: number;
    section_contains: number;
    content_contains: number;
    tags_contains: number;
}

interface TermMatchWeights {
    title: number;
    attachment: number;
    external: number;
    url: number;
    section: number;
    summary_or_content: number;
}

interface AuthorityWeights {
    focused_source_boost: number;
    broad_source_boost: number;
    single_source_miss_penalty: number;
}

interface FreshnessWeightConfig {
    system_facet_score?: number;
    max_score?: number;
    horizon_days?: number;
    reason: string;
}

interface SearchIntentConfig {
    field_weights: Record<string, number>;
    intent_detection: {
        default_authority_sources: string[];
        system_authority_rules: Array<{
            source_id: string;
            match_any: string[];
        }>;
        system_default_authority_sources: string[];
        profiles: QueryIntentRuleConfig[];
        fallback_profile: {
            intent: CampusSearchIntent;
            authority_sources: string[];
            freshness_mode: FreshnessMode;
        };
    };
    ranking: {
        text_match: TextMatchWeights;
        term_match: TermMatchWeights;
        authority: AuthorityWeights;
        facet_boosts: Array<{
            facet: string;
            intents: CampusSearchIntent[];
            score: number;
            reason: string;
        }>;
        task_kind_match: number;
        freshness: Record<FreshnessMode, FreshnessWeightConfig>;
        stale_penalty: {
            modes: FreshnessMode[];
            thresholds: Array<{
                older_than_days: number;
                score: number;
            }>;
        };
        short_landing_page_penalty: number;
        scholarship_non_financial_hardship_penalty: number;
    };
}

export const SEARCH_INTENT_CONFIG = searchIntentConfig as SearchIntentConfig;

const includesAny = (text: string, terms: string[]): boolean => terms.some(term => text.includes(normalize(term)));

const dynamicSystemAuthoritySources = (text: string): string[] => {
    for (const rule of SEARCH_INTENT_CONFIG.intent_detection.system_authority_rules) {
        if (includesAny(text, rule.match_any)) {
            return [rule.source_id];
        }
    }
    return [...SEARCH_INTENT_CONFIG.intent_detection.system_default_authority_sources];
};

export const detectQueryIntent = (query: string): QueryIntentProfile => {
    const text = normalize(query);

    for (const rule of SEARCH_INTENT_CONFIG.intent_detection.profiles) {
        if (!includesAny(text, rule.match_any)) continue;
        const authoritySources = rule.authority_sources === 'dynamic_system'
            ? dynamicSystemAuthoritySources(text)
            : [...rule.authority_sources];
        return {
            intent: rule.intent,
            authoritySources,
            freshnessMode: rule.freshness_mode,
        };
    }

    const fallback = SEARCH_INTENT_CONFIG.intent_detection.fallback_profile;
    return {
        intent: fallback.intent,
        authoritySources: [...fallback.authority_sources],
        freshnessMode: fallback.freshness_mode,
    };
};

export const sourceIdForDocument = (document: SitegraphFullDocument): string => {
    return document.source_id || document.provenance.site_id || document.id.split('-', 1)[0] || '';
};
