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

export type SearchDocumentKind = 'notice' | 'exam' | 'resource';

export type SearchCategory =
    | '考试'
    | '选课'
    | '竞赛'
    | '奖助'
    | '就业'
    | '讲座'
    | '生活'
    | '学院'
    | '研究生'
    | '项目'
    | '资料'
    | '公告';

export interface SearchAttachment {
    name: string;
    url: string;
    type?: string;
}

export interface SearchDocument {
    id: string;
    kind: SearchDocumentKind;
    title: string;
    url: string;
    source: string;
    source_domain: string;
    category: SearchCategory;
    audience: string[];
    published_at: string | null;
    content: string;
    summary?: string;
    attachments: SearchAttachment[];
    student_score: number;
    freshness_score: number;
    importance_score: number;
    source_weight?: number;
    tags: string[];
    hash: string;
    class_name?: string;
    exam_id?: string;
}

export interface RankedSearchDocument extends SearchDocument {
    score: number;
    score_reason: string;
}

export interface SearchManifestSource {
    id: string;
    name: string;
    domain: string;
    status: 'ok' | 'error';
    documents: number;
    last_fetch_at: string | null;
    error?: string;
}

export interface SearchManifest {
    generated_at: string;
    total_documents: number;
    sources: SearchManifestSource[];
    strategy: string;
}

export type SearchMode = 'EMPTY' | 'NOT_FOUND' | 'LIST' | 'DETAIL';

export interface SearchResult {
    mode: SearchMode;
    classes: string[];
    exams: Exam[];
}
