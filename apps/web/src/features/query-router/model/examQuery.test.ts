import { describe, expect, it } from 'vitest';
import { isClassLookupQuery, isCompleteClassQuery, isExamHelperQuery, normalizeClassQuery } from './examQuery';

describe('exam query helpers', () => {
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
