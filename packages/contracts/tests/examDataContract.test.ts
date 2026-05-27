import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
    ExamSchema,
    ManifestSchema
} from '../src/exam';
import { z } from 'zod';

const loadPublicJson = (relativePath: string): unknown => {
    return JSON.parse(readFileSync(new URL(relativePath, import.meta.url), 'utf-8'));
};

describe('exam data contract package', () => {
    it('accepts the committed public data file shapes', () => {
        const exams = z.array(ExamSchema).parse(loadPublicJson('../../../apps/web/public/generated/exam/all_exams.json'));
        const manifest = ManifestSchema.parse(loadPublicJson('../../../apps/web/public/generated/exam/data_summary.json'));

        expect(exams.length).toBeGreaterThan(0);
        expect(manifest.files_processed.length).toBeGreaterThan(0);
    });

    it('rejects invalid exam field shapes', () => {
        const exam = {
            id: 'invalid-time',
            class_name: 'B240402',
            course_name: '算法分析与设计',
            duration_minutes: 0,
            start_timestamp: '2026-07-01T08:00:00+08:00',
            end_timestamp: '2026-07-01T09:50:00+08:00'
        };

        expect(ExamSchema.safeParse(exam).success).toBe(false);
        expect(ExamSchema.safeParse({
            ...exam,
            duration_minutes: 110,
            start_timestamp: 'not-a-date'
        }).success).toBe(false);
    });
});
