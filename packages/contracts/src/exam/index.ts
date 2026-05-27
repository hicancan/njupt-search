import { z } from 'zod';

export interface Exam {
    id: string;
    class_name: string;
    course_name: string;
    location: string;
    start_timestamp: string | null;
    end_timestamp: string | null;
    duration_minutes: number;
    teacher?: string;
    notes?: string;
    campus?: string;
    course_code?: string;
    count?: number;
    raw_time?: string;
    school?: string;
    student_school?: string;
    major?: string;
    grade?: string;
    date?: string;
    parse_error?: string | null;
}

export interface Manifest {
    generated_at: string;
    files_processed: string[];
    total_records: number;
    source_url?: string;
    source_title?: string;
}

export type SearchMode = 'EMPTY' | 'NOT_FOUND' | 'LIST' | 'DETAIL';

export interface SearchResult {
    mode: SearchMode;
    classes: string[];
    exams: Exam[];
}

export const ExamSchema = z.object({
    id: z.string().min(1),
    class_name: z.string().min(1),
    course_name: z.string().min(1),
    duration_minutes: z.number().positive(),
    start_timestamp: z.string().nullable().optional(),
    end_timestamp: z.string().nullable().optional(),
    parse_error: z.string().nullable().optional(),
}).passthrough().superRefine((val, ctx) => {
    const start = val.start_timestamp;
    const end = val.end_timestamp;

    if (start && start.trim() === '') {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'start_timestamp must not be empty when present' });
    }
    if (end && end.trim() === '') {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'end_timestamp must not be empty when present' });
    }

    if (start && Number.isNaN(new Date(start).getTime())) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'start_timestamp must be a parseable date-time string' });
    }
    if (end && Number.isNaN(new Date(end).getTime())) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'end_timestamp must be a parseable date-time string' });
    }

    if ((start && !end) || (!start && end)) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'has incomplete time range' });
    }
});

export const ManifestSchema = z.object({
    generated_at: z.string().min(1),
    total_records: z.number(),
    files_processed: z.array(z.string()),
    source_url: z.string().nullable().optional(),
    source_title: z.string().nullable().optional(),
}).passthrough();
