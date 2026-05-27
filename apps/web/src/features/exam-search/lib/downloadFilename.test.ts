import { describe, expect, it } from 'vitest';
import { buildExamCalendarFilename } from './downloadFilename';

describe('buildExamCalendarFilename', () => {
    it('uses the project name and class name for exported calendars', () => {
        expect(buildExamCalendarFilename('B240402')).toBe('njupt-search-B240402.ics');
    });
});
