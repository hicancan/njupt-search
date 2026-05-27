import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
    assertManifestMatchesExams,
    DataContractError,
    parseExamData,
    parseManifest
} from '../src/exam';

const loadPublicJson = (relativePath: string): unknown => {
    return JSON.parse(readFileSync(new URL(relativePath, import.meta.url), 'utf-8'));
};

describe('exam data contract package', () => {
    it('accepts the committed public data files', () => {
        const exams = parseExamData(
            loadPublicJson('../../../public/data/all_exams.json'),
            'public/data/all_exams.json'
        );
        const manifest = parseManifest(
            loadPublicJson('../../../public/data/data_summary.json'),
            'public/data/data_summary.json'
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
});

