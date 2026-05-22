import { Exam, RankedSearchDocument, SearchCategory, SearchDocument, SearchManifest } from '@/types';

class SearchContractError extends Error {
    constructor(message: string) {
        super(message);
        this.name = 'SearchContractError';
    }
}

const CATEGORY_ORDER: SearchCategory[] = [
    '考试',
    '竞赛',
    '奖助',
    '就业',
    '讲座',
    '生活',
    '研究生',
    '选课',
    '学院',
    '项目',
    '资料',
    '公告'
];

const RESOURCE_INTENT_KEYWORDS = [
    '高数',
    '数学',
    '线代',
    '概率',
    '电路',
    '大物',
    '物理',
    'c语言',
    'C语言',
    '数据结构',
    '算法',
    '实验',
    '复习',
    '题',
    '考试',
    '项目',
    '竞赛'
];

const isRecord = (value: unknown): value is Record<string, unknown> => {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
};

const clamp01 = (value: number): number => {
    if (!Number.isFinite(value)) return 0;
    return Math.min(1, Math.max(0, value));
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

const readRequiredString = (record: Record<string, unknown>, key: string, label: string): string => {
    const value = record[key];
    if (typeof value !== 'string' || value.trim() === '') {
        throw new SearchContractError(`${label}.${key} must be a non-empty string`);
    }
    return value;
};

const readOptionalString = (record: Record<string, unknown>, key: string): string | null => {
    const value = record[key];
    return typeof value === 'string' && value.trim() ? value : null;
};

const readNumber = (record: Record<string, unknown>, key: string, label: string): number => {
    const value = record[key];
    if (typeof value !== 'number' || !Number.isFinite(value)) {
        throw new SearchContractError(`${label}.${key} must be a finite number`);
    }
    return value;
};

const readStringArray = (record: Record<string, unknown>, key: string, label: string): string[] => {
    const value = record[key];
    if (!Array.isArray(value) || value.some(item => typeof item !== 'string')) {
        throw new SearchContractError(`${label}.${key} must be a string array`);
    }
    return value;
};

const readCategory = (record: Record<string, unknown>, label: string): SearchCategory => {
    const category = readRequiredString(record, 'category', label);
    if (!CATEGORY_ORDER.includes(category as SearchCategory)) {
        return '公告';
    }
    return category as SearchCategory;
};

const daysFromNow = (dateLike: string | null): number | null => {
    if (!dateLike) return null;
    const date = new Date(dateLike);
    if (Number.isNaN(date.getTime())) return null;
    return (Date.now() - date.getTime()) / 86_400_000;
};

const calculateFreshness = (dateLike: string | null): number => {
    const days = daysFromNow(dateLike);
    if (days === null) return 0.45;
    if (days < -120) return 0.66;
    if (days < 0) return 0.95;
    if (days <= 3) return 1;
    if (days <= 7) return 0.92;
    if (days <= 30) return 0.78;
    if (days <= 180) return 0.58;
    return 0.42;
};

const dateSortValue = (dateLike: string | null): number => {
    if (!dateLike) return 0;
    const date = new Date(dateLike);
    return Number.isNaN(date.getTime()) ? 0 : date.getTime();
};

const scoreTextMatch = (document: SearchDocument, query: string): number => {
    const tokens = tokenize(query);
    if (tokens.length === 0) return 0;

    const title = normalize(document.title);
    const content = normalize(document.content);
    const source = normalize(document.source);
    const tags = normalize(document.tags.join(' '));
    const className = normalize(document.class_name || '');

    let score = 0;
    const normalizedQuery = normalize(query);

    if (title === normalizedQuery) score += 18;
    if (title.includes(normalizedQuery)) score += 12;
    if (className && className === normalizedQuery) score += 16;

    for (const token of tokens) {
        const normalizedToken = normalize(token);
        if (!normalizedToken) continue;
        if (title.includes(normalizedToken)) score += 8;
        if (tags.includes(normalizedToken)) score += 4;
        if (source.includes(normalizedToken)) score += 3;
        if (content.includes(normalizedToken)) score += 1.5;
        if (className.includes(normalizedToken)) score += 8;
    }

    return score;
};

const buildScoreReason = (document: SearchDocument): string => {
    const parts = [`${document.category}`];

    if (document.attachments.length > 0) {
        parts.push(`${document.attachments.length} 个附件`);
    }

    return parts.join(' · ');
};

export const parseSearchDocuments = (payload: unknown, source = 'search documents'): SearchDocument[] => {
    if (!Array.isArray(payload)) {
        throw new SearchContractError(`${source} must be an array`);
    }

    const ids = new Set<string>();
    return payload.map((item, index) => {
        const label = `${source}[${index}]`;
        if (!isRecord(item)) {
            throw new SearchContractError(`${label} must be an object`);
        }

        const id = readRequiredString(item, 'id', label);
        if (ids.has(id)) {
            throw new SearchContractError(`${source} contains duplicate id: ${id}`);
        }
        ids.add(id);

        return {
            id,
            kind: item.kind === 'exam' || item.kind === 'resource' ? item.kind : 'notice',
            title: readRequiredString(item, 'title', label),
            url: readRequiredString(item, 'url', label),
            source: readRequiredString(item, 'source', label),
            source_domain: readRequiredString(item, 'source_domain', label),
            category: readCategory(item, label),
            audience: readStringArray(item, 'audience', label),
            published_at: readOptionalString(item, 'published_at'),
            content: readRequiredString(item, 'content', label),
            summary: readOptionalString(item, 'summary') || undefined,
            attachments: Array.isArray(item.attachments) ? item.attachments as SearchDocument['attachments'] : [],
            student_score: clamp01(readNumber(item, 'student_score', label)),
            freshness_score: clamp01(readNumber(item, 'freshness_score', label)),
            importance_score: clamp01(readNumber(item, 'importance_score', label)),
            source_weight: typeof item.source_weight === 'number' ? clamp01(item.source_weight) : undefined,
            tags: readStringArray(item, 'tags', label),
            hash: readRequiredString(item, 'hash', label),
            class_name: readOptionalString(item, 'class_name') || undefined,
            exam_id: readOptionalString(item, 'exam_id') || undefined
        };
    });
};

export const parseSearchManifest = (payload: unknown, source = 'search manifest'): SearchManifest => {
    if (!isRecord(payload)) {
        throw new SearchContractError(`${source} must be an object`);
    }

    const sources = payload.sources;
    if (!Array.isArray(sources)) {
        throw new SearchContractError(`${source}.sources must be an array`);
    }

    return {
        generated_at: readRequiredString(payload, 'generated_at', source),
        total_documents: readNumber(payload, 'total_documents', source),
        strategy: readRequiredString(payload, 'strategy', source),
        sources: sources.map((item, index) => {
            const label = `${source}.sources[${index}]`;
            if (!isRecord(item)) {
                throw new SearchContractError(`${label} must be an object`);
            }

            return {
                id: readRequiredString(item, 'id', label),
                name: readRequiredString(item, 'name', label),
                domain: readRequiredString(item, 'domain', label),
                status: item.status === 'error' ? 'error' : 'ok',
                documents: readNumber(item, 'documents', label),
                last_fetch_at: readOptionalString(item, 'last_fetch_at'),
                error: readOptionalString(item, 'error') || undefined
            };
        })
    };
};

export const buildExamDocuments = (exams: Exam[]): SearchDocument[] => {
    return exams.map(exam => {
        const title = `${exam.class_name} ${exam.course_name} 考试安排`;
        const content = [
            exam.class_name,
            exam.course_name,
            exam.course_code,
            exam.teacher,
            exam.location,
            exam.raw_time,
            exam.campus,
            exam.school,
            exam.student_school,
            exam.major,
            exam.grade,
            exam.notes
        ].filter(Boolean).join(' ');

        return {
            id: `exam-${exam.id}`,
            kind: 'exam',
            title,
            url: `?class=${encodeURIComponent(exam.class_name)}`,
            source: '考试垂直频道',
            source_domain: 'jwc.njupt.edu.cn',
            category: '考试',
            audience: ['本科生'],
            published_at: exam.date || exam.start_timestamp,
            content: content || title,
            summary: `${exam.raw_time || '时间待确认'} · ${exam.location || '地点待确认'}`,
            attachments: [],
            student_score: 1,
            freshness_score: calculateFreshness(exam.date || exam.start_timestamp),
            importance_score: 0.94,
            source_weight: 1,
            tags: ['考试', '期末', exam.class_name, exam.course_name, exam.campus || '', exam.major || ''].filter(Boolean),
            hash: exam.id,
            class_name: exam.class_name,
            exam_id: exam.id
        };
    });
};

export const rankSearchDocuments = (
    documents: SearchDocument[],
    query: string,
    category: SearchCategory | '全部'
): RankedSearchDocument[] => {
    const trimmed = query.trim();
    const categoryFiltered = category === '全部'
        ? documents
        : documents.filter(document => document.category === category);

    if (trimmed.length < 2) {
        return [...categoryFiltered]
            .sort((a, b) => {
                const dateDelta = dateSortValue(b.published_at) - dateSortValue(a.published_at);
                if (dateDelta !== 0) return dateDelta;
                return b.importance_score - a.importance_score;
            })
            .slice(0, 30)
            .map(document => ({
                ...document,
                score: document.importance_score,
                score_reason: buildScoreReason(document)
            }));
    }

    return categoryFiltered
        .map(document => {
            const textScore = scoreTextMatch(document, trimmed);
            const sourceWeight = document.source_weight ?? 0.8;
            const weightedScore = textScore *
                (0.55 + document.student_score * 0.45) *
                (0.72 + document.freshness_score * 0.28) *
                (0.7 + document.importance_score * 0.3) *
                (0.78 + sourceWeight * 0.22);

            return {
                ...document,
                score: Number(weightedScore.toFixed(4)),
                score_reason: buildScoreReason(document)
            };
        })
        .filter(document => document.score > 0)
        .sort((a, b) => {
            if (b.score !== a.score) return b.score - a.score;
            return dateSortValue(b.published_at) - dateSortValue(a.published_at);
        })
        .slice(0, 80);
};

export const getCategoryOrder = (): SearchCategory[] => [...CATEGORY_ORDER];

export const getCategoryCounts = (documents: SearchDocument[]): Record<SearchCategory, number> => {
    return CATEGORY_ORDER.reduce((accumulator, category) => {
        accumulator[category] = documents.filter(document => document.category === category).length;
        return accumulator;
    }, {} as Record<SearchCategory, number>);
};

export const getRecentDocuments = (documents: SearchDocument[], limit: number): SearchDocument[] => {
    return [...documents]
        .sort((a, b) => dateSortValue(b.published_at) - dateSortValue(a.published_at))
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

export const formatSearchDate = (dateLike: string | null): string => {
    if (!dateLike) return '日期待确认';
    const date = new Date(dateLike);
    if (Number.isNaN(date.getTime())) return dateLike;

    return date.toLocaleDateString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    });
};

export const getLearningResources = (query: string): SearchDocument[] => {
    const normalizedQuery = normalize(query);
    if (normalizedQuery.length < 2) return [];
    const hasResourceIntent = RESOURCE_INTENT_KEYWORDS.some(keyword => normalizedQuery.includes(normalize(keyword)));
    if (!hasResourceIntent) return [];

    const resources: SearchDocument[] = [
        {
            id: 'resource-exam-review',
            kind: 'resource',
            title: '课程期末复习与习题讲解入口',
            url: 'https://space.bilibili.com/1144561698',
            source: 'hicancan 学习资源',
            source_domain: 'space.bilibili.com',
            category: '资料',
            audience: ['本科生'],
            published_at: null,
            content: '高数 C语言 数据结构 电路 物理 期末 复习 习题 讲解 视频',
            summary: '按课程名、考试名、实验和题型触发，作为搜索结果后的学习资源推荐。',
            attachments: [],
            student_score: 0.82,
            freshness_score: 0.7,
            importance_score: 0.74,
            source_weight: 0.68,
            tags: ['复习', '习题', '视频', '课程资料'],
            hash: 'resource-exam-review'
        },
        {
            id: 'resource-project-template',
            kind: 'resource',
            title: '课程项目与竞赛项目模板',
            url: 'https://github.com/hicancan',
            source: 'hicancan 项目库',
            source_domain: 'github.com',
            category: '项目',
            audience: ['本科生', '研究生'],
            published_at: null,
            content: '项目 文档 模板 课程设计 大创 竞赛 实验',
            summary: '当搜索项目、实验、竞赛、大创时，提供可复用项目文档入口。',
            attachments: [],
            student_score: 0.72,
            freshness_score: 0.66,
            importance_score: 0.68,
            source_weight: 0.62,
            tags: ['项目', '模板', '竞赛', '课程设计'],
            hash: 'resource-project-template'
        }
    ];

    return rankSearchDocuments(resources, query, '全部');
};
