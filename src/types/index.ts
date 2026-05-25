import { z } from 'zod';

export interface Exam {
    id: string; // Generated unique id (filename-row)
    class_name: string; // e.g., "B250403"
    course_name: string; // e.g., "大学物理"
    location: string; // e.g., "教2-201"

    // Parsed time fields (from Python script)
    // NOTE: Timestamps might be null if parsing failed, but the record is still preserved.
    start_timestamp: string | null; // ISO string or null
    end_timestamp: string | null; // ISO string or null
    duration_minutes: number; // Exam duration in minutes

    // Optional fields
    teacher?: string;
    notes?: string;
    campus?: string;
    course_code?: string;
    count?: number; // Number of students
    raw_time?: string; // Original time string from Excel

    // Additional fields from Excel (optional, may not be in all files)
    school?: string; // 开课学院
    student_school?: string; // 学生所在学院
    major?: string; // 专业名称
    grade?: string; // 年级
    date?: string; // Parsed date string (YYYY-MM-DD)
    parse_error?: string | null; // Time parsing error message (if any)
}

export interface Manifest {
    generated_at: string; // ISO string
    files_processed: string[]; // List of processed Excel files
    total_records: number; // From Python script
    source_url?: string; // Original URL of the exam schedule
    source_title?: string; // Title of the news article
}

export const SearchDocumentKindSchema = z.enum(['notice', 'exam', 'resource']);
export type SearchDocumentKind = z.infer<typeof SearchDocumentKindSchema>;

export const SearchCategorySchema = z.enum([
    '考试', '选课', '竞赛', '奖助', '就业', '讲座', '生活', '学院', '研究生', '项目', '资料', '公告'
]);
export type SearchCategory = z.infer<typeof SearchCategorySchema>;

export const SearchDomainSchema = z.enum([
    'academic', 'exam', 'course', 'degree', 'scholarship', 'employment', 'competition',
    'project', 'innovation_project', 'international', 'life', 'library', 'security', 'logistics',
    'campus_network', 'subsidy', 'medical_insurance', 'archive', 'lecture',
    'research', 'resource', 'news', 'policy'
]);
export type SearchDomain = z.infer<typeof SearchDomainSchema>;

export const SearchIntentSchema = z.enum([
    'apply', 'register', 'submit', 'attend', 'check_result', 'publicity', 'download',
    'read', 'schedule', 'alert', 'pay', 'contact', 'export'
]);
export type SearchIntent = z.infer<typeof SearchIntentSchema>;

export const SearchSourceTypeSchema = z.enum([
    'central_admin', 'central_notice', 'central_news', 'college', 'service_unit',
    'job_platform', 'github_resource', 'research_admin', 'policy', 'exam_vertical'
]);
export type SearchSourceType = z.infer<typeof SearchSourceTypeSchema>;

export const SearchLifecycleSchema = z.enum(['active', 'upcoming', 'expired', 'evergreen', 'unknown']);
export type SearchLifecycle = z.infer<typeof SearchLifecycleSchema>;

export const SearchSemanticModeSchema = z.enum(['llm', 'heuristic', 'heuristic_degraded', 'guarded_metadata', 'structured_exam', 'unprocessed']);
export type SearchSemanticMode = z.infer<typeof SearchSemanticModeSchema>;

export const TaskFrameSourceModeSchema = z.enum([
    'llm_raw_task_frame',
    'generated_from_llm_fields',
    'heuristic_rule_frame',
    'exam_structured_data',
    'guarded_metadata_empty',
    'unprocessed',
    'unknown'
]);
export type TaskFrameSourceMode = z.infer<typeof TaskFrameSourceModeSchema>;

export const TaskFrameTaskTypeSchema = z.enum(['application', 'schedule', 'result_check', 'download', 'opportunity', 'read']);
export type TaskFrameTaskType = z.infer<typeof TaskFrameTaskTypeSchema>;

export const SearchAttachmentSchema = z.object({
    name: z.string(),
    url: z.string(),
    type: z.string().optional(),
    role: z.string().nullable().optional(),
    description: z.string().nullable().optional(),
    sensitive: z.boolean().optional().default(false)
});
export type SearchAttachment = z.infer<typeof SearchAttachmentSchema>;

export const SearchDocumentLLMSchema = z.object({
    used: z.boolean().optional(),
    provider: z.string().nullable().optional(),
    model: z.string().nullable().optional(),
    prompt_version: z.string().optional(),
    confidence: z.number().nullable().optional(),
    review_required: z.boolean().optional()
}).passthrough();
export type SearchDocumentLLMMetadata = z.infer<typeof SearchDocumentLLMSchema>;

export const TaskFrameSchema = z.object({
    task_id: z.string(),
    doc_id: z.string(),
    source_mode: TaskFrameSourceModeSchema,
    field_sources: z.record(z.string(), z.string()).optional(),
    task_type: TaskFrameTaskTypeSchema,
    who: z.object({
        audience: z.array(z.string()).default([]),
        college: z.array(z.string()).default([]),
        grade: z.array(z.string()).default([]),
        major: z.array(z.string()).default([]),
        class_name: z.array(z.string()).default([])
    }).default({ audience: [], college: [], grade: [], major: [], class_name: [] }),
    what: z.string(),
    action: z.object({
        required: z.boolean().default(false),
        verb: z.string().nullable().optional(),
        object: z.string().nullable().optional(),
        summary: z.string().nullable().optional()
    }).default({ required: false }),
    time: z.object({
        published_at: z.string().nullable().optional(),
        deadline: z.string().nullable().optional(),
        lifecycle: SearchLifecycleSchema,
        urgency_days: z.number().nullable().optional()
    }),
    materials: z.array(z.object({
        name: z.string(),
        role: z.string().nullable().optional(),
        required: z.boolean().default(false),
        sensitive: z.boolean().default(false)
    })).default([]),
    location: z.object({
        place: z.string().nullable().optional(),
        online: z.string().nullable().optional(),
        contact: z.string().nullable().optional()
    }).default({}),
    source: z.object({
        source_id: z.string(),
        channel_id: z.string(),
        authority: z.number().default(0.7),
        official: z.boolean().default(true)
    }).default({ source_id: '', channel_id: '', authority: 0.7, official: true }),
    evidence: z.array(z.object({
        field: z.string(),
        text: z.string()
    })).default([]),
    risk: z.object({
        sensitive: z.boolean().default(false),
        restricted: z.boolean().default(false),
        low_evidence: z.boolean().default(false),
        review_required: z.boolean().default(false)
    }).default({ sensitive: false, restricted: false, low_evidence: false, review_required: false }),
    confidence: z.number().optional()
}).passthrough();
export type TaskFrame = z.infer<typeof TaskFrameSchema>;

export const SearchDocumentSchema = z.object({
    id: z.string().min(1),
    kind: SearchDocumentKindSchema,
    status: z.string().optional(),
    source_id: z.string().min(1),
    channel_id: z.string().min(1),
    channel: z.string().min(1),
    title: z.string().min(1),
    url: z.string().min(1),
    source: z.string().min(1),
    source_domain: z.string().min(1),
    source_type: SearchSourceTypeSchema,
    category: SearchCategorySchema,
    domain: SearchDomainSchema,
    intent: SearchIntentSchema,
    lifecycle: SearchLifecycleSchema,
    evidence: z.array(z.string()).optional().default([]),
    confidence: z.number().nullable().optional(),
    sub_category: z.string().nullable().optional(),
    deadline: z.string().nullable().optional(),
    action_required: z.boolean().optional().default(false),
    action_type: z.string().nullable().optional(),
    action_summary: z.string().nullable().optional(),
    required_materials: z.array(z.string()).optional().default([]),
    sensitive: z.boolean().optional().default(false),
    sensitive_types: z.array(z.string()).optional().default([]),
    review_required: z.boolean().optional().default(false),
    risk_flags: z.array(z.string()).optional().default([]),
    audience: z.array(z.string()),
    published_at: z.string().nullable().optional(),
    content: z.string().min(1),
    summary: z.string().optional(),
    attachments: z.array(SearchAttachmentSchema).default([]),
    tags: z.array(z.string()),
    hash: z.string().min(1),
    cache_key: z.string().optional(),
    llm_schema_version: z.string().optional(),
    llm: SearchDocumentLLMSchema.optional(),
    canonical: z.record(z.string(), z.unknown()).optional(),
    notice_card: z.record(z.string(), z.unknown()).optional(),
    typed_search_terms: z.array(z.record(z.string(), z.unknown())).optional(),
    synonyms: z.array(z.string()).optional(),
    rule_guard: z.record(z.string(), z.unknown()).optional(),
    semantic_mode: SearchSemanticModeSchema.optional(),
    field_sources: z.record(z.string(), z.string()).optional(),
    task_frames: z.array(TaskFrameSchema).default([]),
    class_name: z.string().optional(),
    exam_id: z.string().optional()
}).passthrough();
export type SearchDocument = z.infer<typeof SearchDocumentSchema>;

export interface RankedSearchDocument extends SearchDocument {
    score: number;
    score_reason: string;
}

export const SearchManifestSourceSchema = z.object({
    id: z.string().min(1),
    name: z.string().min(1),
    domain: z.string().min(1),
    source_type: z.enum([
        'central_admin', 'central_notice', 'central_news', 'college', 'service_unit',
        'job_platform', 'github_resource', 'research_admin', 'policy', 'exam_vertical'
    ]).optional(),
    priority: z.number().optional(),
    candidates: z.number().optional(),
    filtered_out: z.number().optional(),
    status: z.enum(['ok', 'error']),
    documents: z.number(),
    last_fetch_at: z.string().nullable().optional(),
    error: z.string().optional()
}).passthrough();
export type SearchManifestSource = z.infer<typeof SearchManifestSourceSchema>;

export const SearchManifestSchema = z.object({
    generated_at: z.string().min(1),
    total_documents: z.number(),
    strategy: z.string().min(1),
    llm_schema_version: z.string().optional(),
    llm_enabled: z.boolean().optional(),
    llm_provider: z.string().optional(),
    llm_model: z.string().nullable().optional(),
    llm_batch_size: z.number().optional(),
    llm_batch_max_chars: z.number().optional(),
    llm_batch_max_output_tokens: z.number().optional(),
    semantic_pipeline_version: z.string().optional(),
    semantic_mode_counts: z.record(z.string(), z.number()).optional(),
    field_source_counts: z.record(z.string(), z.any()).optional(),
    task_frame_source_mode_counts: z.record(z.string(), z.number()).optional(),
    llm_missing_field_counts: z.record(z.string(), z.number()).optional(),
    training_eligible_count: z.number().optional(),
    heuristic_degraded_count: z.number().optional(),
    llm_purity_rate: z.number().optional(),
    sources: z.array(SearchManifestSourceSchema)
}).passthrough();
export type SearchManifest = z.infer<typeof SearchManifestSchema>;

export type SearchMode = 'EMPTY' | 'NOT_FOUND' | 'LIST' | 'DETAIL';

export interface SearchResult {
    mode: SearchMode;
    classes: string[];
    exams: Exam[];
}
