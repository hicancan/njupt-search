import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
    assertManifestMatchesExams,
    DataContractError,
    parseExamData,
    parseManifest
} from './examDataContract';

const loadPublicJson = (relativePath: string): unknown => {
    return JSON.parse(readFileSync(new URL(relativePath, import.meta.url), 'utf-8'));
};

describe('exam data contract', () => {
    it('accepts the committed public data files', () => {
        const exams = parseExamData(
            loadPublicJson('../../../../public/generated/exam/all_exams.json'),
            'apps/web/public/generated/exam/all_exams.json'
        );
        const manifest = parseManifest(
            loadPublicJson('../../../../public/generated/exam/data_summary.json'),
            'apps/web/public/generated/exam/data_summary.json'
        );

        assertManifestMatchesExams(manifest, exams);

        expect(exams.length).toBeGreaterThan(0);
        expect(manifest.files_processed.length).toBeGreaterThan(0);
        expect(new Set(exams.map(exam => exam.id)).size).toBe(exams.length);
    });

    it('fails fast when all_exams is not an array', () => {
        expect(() => parseExamData({ data: [] }, 'all_exams.json')).toThrow(DataContractError);
    });

    it('fails fast on duplicate exam ids', () => {
        const exam = {
            id: 'duplicate',
            class_name: 'B240402',
            course_name: '算法分析与设计',
            duration_minutes: 110,
            start_timestamp: null,
            end_timestamp: null
        };

        expect(() => parseExamData([exam, exam], 'all_exams.json')).toThrow(/duplicate id/);
    });

    it('rejects non-positive durations and invalid timestamps', () => {
        const exam = {
            id: 'invalid-time',
            class_name: 'B240402',
            course_name: '算法分析与设计',
            duration_minutes: 0,
            start_timestamp: '2026-07-01T08:00:00+08:00',
            end_timestamp: '2026-07-01T09:50:00+08:00'
        };

        expect(() => parseExamData([exam], 'all_exams.json')).toThrow(/duration_minutes/);
        expect(() => parseExamData([{
            ...exam,
            duration_minutes: 110,
            start_timestamp: 'not-a-date'
        }], 'all_exams.json')).toThrow(/start_timestamp/);
    });
});
