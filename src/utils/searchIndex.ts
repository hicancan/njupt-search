import {
    RankedSearchDocument,
    SearchDocument,
    SearchDomain,
    SearchIntent,
    SearchLifecycle,
    SearchManifest,
    SearchSourceType,
    SearchDocumentSchema,
    SearchManifestSchema
} from '@/types';
import { z } from 'zod';
import { routeQuery } from './queryRouter';

class SearchContractError extends Error {
    constructor(message: string) {
        super(message);
        this.name = 'SearchContractError';
    }
}

const valueAtPath = (payload: unknown, path: PropertyKey[]): unknown => {
    let current = payload;
    for (const part of path) {
        if (current === null || current === undefined) return undefined;
        current = (current as Record<PropertyKey, unknown>)[part];
    }
    return current;
};

const formatZodIssues = (payload: unknown, error: z.ZodError): string => {
    return error.issues.map(issue => {
        const fieldPath = issue.path.join('.') || '<root>';
        const invalidValue = valueAtPath(payload, issue.path);
        return `${fieldPath}: ${issue.message}; value=${JSON.stringify(invalidValue)}`;
    }).join('; ');
};

const DOMAIN_LABELS: Record<SearchDomain, string> = {
    academic: '学业事务',
    exam: '考试',
    course: '课程选课',
    degree: '学位培养',
    scholarship: '资助评优',
    employment: '就业实习',
    competition: '竞赛活动',
    project: '项目机会',
    innovation_project: '大创项目',
    international: '国际交流',
    life: '校园生活',
    library: '图书馆',
    security: '安全保卫',
    logistics: '后勤服务',
    campus_network: '校园网络',
    subsidy: '资助补助',
    medical_insurance: '医保体检',
    archive: '档案服务',
    lecture: '讲座活动',
    research: '科研事务',
    resource: '学习资料',
    news: '校园新闻',
    policy: '政策制度'
};

const INTENT_LABELS: Record<SearchIntent, string> = {
    apply: '申请',
    register: '报名',
    submit: '提交',
    attend: '参加',
    check_result: '查结果',
    publicity: '公示',
    download: '下载',
    read: '阅读',
    schedule: '安排',
    alert: '提醒',
    pay: '缴费',
    contact: '联系',
    export: '导出'
};

const SOURCE_TYPE_LABELS: Record<SearchSourceType, string> = {
    central_admin: '校级部门',
    central_notice: '校级通知',
    central_news: '校园新闻',
    college: '学院站',
    service_unit: '服务单位',
    job_platform: '就业平台',
    github_resource: '资料仓库',
    research_admin: '科研管理',
    policy: '信息公开',
    exam_vertical: '考试频道'
};

const LIFECYCLE_LABELS: Record<SearchLifecycle, string> = {
    active: '进行中',
    upcoming: '即将开始',
    expired: '已过期',
    evergreen: '长期有效',
    unknown: '时效未知'
};

const normalize = (value: string): string => {
    return value.toLowerCase().replace(/\s+/g, '');
};

const tokenize = (query: string): string[] => {
    const normalized = query.trim();
    if (!normalized) return [];

    const parts = normalized
        .split(/[\s,，、/|]+/)
        .map(part => part.trim())
        .filter(Boolean);

    return parts.length > 0 ? parts : [normalized];
};

const asRecord = (value: unknown): Record<string, unknown> => {
    return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
};

const collectStrings = (value: unknown, limit = 120): string[] => {
    const result: string[] = [];
    const visit = (item: unknown) => {
        if (result.length >= limit || item === null || item === undefined) return;
        if (typeof item === 'string' || typeof item === 'number' || typeof item === 'boolean') {
            const text = String(item).trim();
            if (text) result.push(text);
            return;
        }
        if (Array.isArray(item)) {
            for (const child of item) visit(child);
            return;
        }
        if (typeof item === 'object') {
            for (const child of Object.values(item as Record<string, unknown>)) visit(child);
        }
    };
    visit(value);
    return result;
};

const daysFromNow = (dateLike: string | null | undefined): number | null => {
    if (!dateLike) return null;
    const date = new Date(dateLike);
    if (Number.isNaN(date.getTime())) return null;
    return (Date.now() - date.getTime()) / 86_400_000;
};

const dateSortValue = (dateLike: string | null | undefined): number => {
    if (!dateLike) return 0;
    const date = new Date(dateLike);
    return Number.isNaN(date.getTime()) ? 0 : date.getTime();
};

type QueryAliasPayload = {
    aliases?: unknown[];
    domains?: unknown[];
    intents?: unknown[];
};

const aliasPayloadsForQuery = (query: string, queryAliases: Record<string, unknown>): QueryAliasPayload[] => {
    const normalizedQuery = normalize(query);
    const payloads: QueryAliasPayload[] = [];
    for (const [key, rawPayload] of Object.entries(queryAliases)) {
        const payload = rawPayload as QueryAliasPayload;
        const aliases = Array.isArray(payload.aliases) ? payload.aliases.map(String) : [];
        const candidates = [key, ...aliases];
        if (candidates.some(candidate => normalize(candidate) && normalizedQuery.includes(normalize(candidate)))) {
            payloads.push(payload);
        }
    }
    return payloads;
};

const aliasTermsFromPayloads = (payloads: QueryAliasPayload[]): string[] => {
    const terms: string[] = [];
    for (const payload of payloads) {
        if (Array.isArray(payload.aliases)) {
            terms.push(...payload.aliases.map(String));
        }
    }
    return Array.from(new Set(terms.filter(Boolean)));
};

const queryTerms = (query: string, queryAliases: Record<string, unknown>): string[] => {
    return Array.from(new Set([
        ...tokenize(query),
        ...aliasTermsFromPayloads(aliasPayloadsForQuery(query, queryAliases))
    ].map(term => term.trim()).filter(Boolean)));
};

const taskFrameText = (document: SearchDocument): string => {
    return document.task_frames.map(frame => [
        frame.what,
        frame.action.summary,
        frame.action.verb,
        frame.action.object,
        frame.time.deadline,
        ...frame.materials.map(material => material.name),
        frame.location.place,
        frame.location.online,
        frame.location.contact,
        ...frame.evidence.map(item => item.text)
    ].filter(Boolean).join(' ')).join(' ');
};

const documentRecallText = (document: SearchDocument): string => {
    const payload = document as SearchDocument & Record<string, unknown>;
    const llm = asRecord(payload.llm);
    const typedSearchTerms = collectStrings(payload.typed_search_terms);
    const synonyms = collectStrings(payload.synonyms);
    const noticeCard = collectStrings(payload.notice_card);
    const semanticTerms = collectStrings([
        llm.semantic_queries,
        llm.query_phrases,
        llm.search_profile
    ]);

    return [
        document.title,
        document.summary,
        document.content,
        document.source,
        document.source_id,
        document.channel,
        document.channel_id,
        document.source_domain,
        DOMAIN_LABELS[document.domain] || document.domain,
        INTENT_LABELS[document.intent] || document.intent,
        SOURCE_TYPE_LABELS[document.source_type] || document.source_type,
        document.class_name,
        ...document.tags,
        ...document.evidence,
        ...document.required_materials,
        ...document.attachments.flatMap(attachment => [attachment.name, attachment.role, attachment.description]),
        taskFrameText(document),
        ...typedSearchTerms,
        ...synonyms,
        ...noticeCard,
        ...semanticTerms
    ].filter(Boolean).join(' ');
};

const containsAny = (text: string, terms: string[]): boolean => {
    return terms.some(term => {
        const normalizedTerm = normalize(term);
        return normalizedTerm.length > 0 && text.includes(normalizedTerm);
    });
};

type RecallRoute = ReturnType<typeof routeQuery>;

const routeRejectsDocument = (document: SearchDocument, route: RecallRoute, normalizedText: string): boolean => {
    const blockedDomains = new Set(route.blocked_domains_for_top5);
    const blockedSources = new Set(route.blocked_sources_for_top5.map(normalize));
    const source = normalize(document.source);
    const sourceId = normalize(document.source_id);

    if (blockedDomains.has(document.domain)) return true;
    if (blockedSources.has(source) || blockedSources.has(sourceId)) return true;
    if (!route.allow_resource_top5 && document.source_type === 'github_resource') return true;
    if (containsAny(normalizedText, route.bad_result_terms)) return true;
    if (route.must_include_terms_for_top_results.length > 0 && !containsAny(normalizedText, route.must_include_terms_for_top_results)) {
        return true;
    }
    return false;
};

const recallReasons = (
    document: SearchDocument,
    query: string,
    terms: string[],
    route: RecallRoute
): string[] => {
    const normalizedText = normalize(documentRecallText(document));
    if (routeRejectsDocument(document, route, normalizedText)) return [];

    const normalizedQuery = normalize(query);
    const reasons: string[] = [];
    const title = normalize(document.title);
    if (normalizedQuery && title.includes(normalizedQuery)) reasons.push('标题命中');

    const matchedTerms = terms
        .filter(term => {
            const normalizedTerm = normalize(term);
            return normalizedTerm.length > 0 && normalizedText.includes(normalizedTerm);
        })
        .slice(0, 6);
    if (matchedTerms.length > 0) reasons.push(`关键词/同义词: ${matchedTerms.join('、')}`);

    if (route.target_domains.includes(document.domain)) reasons.push(`领域: ${getDomainLabel(document.domain)}`);
    if (route.target_intents.includes(document.intent)) reasons.push(`动作: ${getIntentLabel(document.intent)}`);

    const hasGroundedTextHit = matchedTerms.length > 0 || (normalizedQuery.length > 0 && title.includes(normalizedQuery));
    return reasons.length > 0 && hasGroundedTextHit ? reasons : [];
};

const recallReasonText = (document: SearchDocument, reasons: string[]): string => {
    const lead = reasons.length > 0 ? reasons.join('；') : '候选召回';
    const source = `${document.source} · ${document.channel}`;
    return `${lead}；${source}；按发布时间倒序`;
};

const compareByPublishedAtDesc = (a: SearchDocument, b: SearchDocument): number => {
    const dateDelta = dateSortValue(b.published_at) - dateSortValue(a.published_at);
    if (dateDelta !== 0) return dateDelta;
    return a.id.localeCompare(b.id);
};

export const parseSearchDocuments = (payload: unknown, source = 'search documents'): SearchDocument[] => {
    try {
        const docs = z.array(SearchDocumentSchema).parse(payload);
        const ids = new Set<string>();
        for (const item of docs) {
            if (ids.has(item.id)) {
                throw new SearchContractError(`${source} contains duplicate id: ${item.id}`);
            }
            ids.add(item.id);
        }
        return docs as unknown as SearchDocument[];
    } catch (e) {
        if (e instanceof z.ZodError) {
            throw new SearchContractError(`Validation failed for ${source}: ${formatZodIssues(payload, e)}`);
        }
        throw new SearchContractError(`Validation failed for ${source}: ${e instanceof Error ? e.message : String(e)}`);
    }
};

export const parseSearchManifest = (payload: unknown, source = 'search manifest'): SearchManifest => {
    try {
        return SearchManifestSchema.parse(payload) as unknown as SearchManifest;
    } catch (e) {
        if (e instanceof z.ZodError) {
            throw new SearchContractError(`Validation failed for ${source}: ${formatZodIssues(payload, e)}`);
        }
        throw new SearchContractError(`Validation failed for ${source}: ${e instanceof Error ? e.message : String(e)}`);
    }
};

export const recallSearchDocuments = (
    documents: SearchDocument[],
    query: string,
    queryAliases: Record<string, unknown> = {},
    limit = 30
): RankedSearchDocument[] => {
    const trimmed = query.trim();
    if (trimmed.length < 2) return [];

    const route = routeQuery(trimmed);
    const terms = queryTerms(trimmed, queryAliases);
    const recalled: RankedSearchDocument[] = [];

    for (const document of documents) {
        const reasons = recallReasons(document, trimmed, terms, route);
        if (reasons.length === 0) continue;
        recalled.push({
            ...document,
            score: 1,
            score_reason: recallReasonText(document, reasons)
        });
    }

    return recalled
        .sort(compareByPublishedAtDesc)
        .slice(0, limit);
};

export const getDomainLabel = (domain: SearchDomain): string => DOMAIN_LABELS[domain] || domain;

export const getIntentLabel = (intent: SearchIntent): string => INTENT_LABELS[intent] || intent;

export const getSourceTypeLabel = (sourceType: SearchSourceType): string => SOURCE_TYPE_LABELS[sourceType] || sourceType;

export const getLifecycleLabel = (lifecycle: SearchLifecycle): string => LIFECYCLE_LABELS[lifecycle] || lifecycle;

export const getRecentDocuments = (documents: SearchDocument[], limit: number): SearchDocument[] => {
    return [...documents]
        .sort(compareByPublishedAtDesc)
        .slice(0, limit);
};

export const getUpdateStats = (documents: SearchDocument[]) => {
    const noticeDocuments = documents.filter(document => document.kind !== 'exam');
    const today = noticeDocuments.filter(document => {
        const days = daysFromNow(document.published_at);
        return days !== null && days >= 0 && days <= 1;
    }).length;
    const sevenDays = noticeDocuments.filter(document => {
        const days = daysFromNow(document.published_at);
        return days !== null && days >= 0 && days <= 7;
    }).length;

    return { today, sevenDays };
};

export const formatSearchDate = (dateLike: string | null | undefined): string => {
    if (!dateLike) return '日期待确认';
    const date = new Date(dateLike);
    if (Number.isNaN(date.getTime())) return dateLike;

    return date.toLocaleDateString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    });
};
