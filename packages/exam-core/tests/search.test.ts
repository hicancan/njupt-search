import { describe, expect, it } from 'vitest';
import type { Exam } from '../../contracts/src/exam';
import {
    getClassSearchResult,
    isClassLookupQuery,
    isCompleteClassQuery,
    isExamHelperQuery,
    normalizeClassQuery
} from '../src/search';

const exam = (id: string, className: string, courseName = '算法分析与设计'): Exam => ({
    id,
    class_name: className,
    course_name: courseName,
    location: '教3-202',
    start_timestamp: null,
    end_timestamp: null,
    duration_minutes: 0
});

describe('exam-core query routing helpers', () => {
    it('normalizes class queries before routing', () => {
        expect(normalizeClassQuery(' b250218 ')).toBe('B250218');
    });

    it('recognizes class lookup prefixes without treating general queries as exams', () => {
        expect(isClassLookupQuery('B250218')).toBe(true);
        expect(isClassLookupQuery('b24040')).toBe(true);
        expect(isClassLookupQuery('Q230101(TG)')).toBe(true);
        expect(isClassLookupQuery('校历')).toBe(false);
        expect(isClassLookupQuery('AI')).toBe(false);
    });

    it('only promotes complete class names to class routes', () => {
        expect(isCompleteClassQuery('B250218')).toBe(true);
        expect(isCompleteClassQuery('q230101(tg)')).toBe(true);
        expect(isCompleteClassQuery('B24040')).toBe(false);
    });

    it('keeps the exam helper independent from sitegraph search', () => {
        expect(isExamHelperQuery('考试安排')).toBe(true);
        expect(isExamHelperQuery('  考试安排  ')).toBe(true);
        expect(isExamHelperQuery('期末考试')).toBe(false);
    });
});

describe('exam-core class search', () => {
    const exams = [
        exam('1', 'B240401'),
        exam('2', 'B240402'),
        exam('3', 'B240402', '离散数学')
    ];

    it('stays empty for short input', () => {
        expect(getClassSearchResult(exams, 'B', null)).toEqual({
            mode: 'EMPTY',
            classes: [],
            exams: []
        });
    });

    it('returns a class list for ambiguous input', () => {
        const result = getClassSearchResult(exams, 'B24040', null);
        expect(result.mode).toBe('LIST');
        expect(result.classes).toEqual(['B240401', 'B240402']);
    });

    it('returns detail for a unique class match', () => {
        const result = getClassSearchResult(exams, 'B240402', null);
        expect(result.mode).toBe('DETAIL');
        expect(result.classes).toEqual(['B240402']);
        expect(result.exams).toHaveLength(2);
    });

    it('fails sharply for an invalid shared URL class', () => {
        const result = getClassSearchResult(exams, 'B999999', 'B999999');
        expect(result).toEqual({
            mode: 'NOT_FOUND',
            classes: [],
            exams: []
        });
    });
});
