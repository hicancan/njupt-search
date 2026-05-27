import { describe, expect, it } from 'vitest';
import type { Exam } from '../../contracts/src/exam';
import { generateICSContent } from '../src/calendar';

const baseExam: Exam = {
    id: '2025-2026学年第二学期考试安排表.xlsx-497',
    campus: '仙林',
    class_name: 'B240402',
    course_name: '数字电路与逻辑设计B',
    course_code: 'DG1011X0S',
    teacher: '张晶',
    location: '教2－410',
    raw_time: '2026年07月01日(18:30-20:20)',
    count: 31,
    notes: '携带铅笔,橡皮;证件',
    start_timestamp: '2026-07-01T18:30:00+08:00',
    end_timestamp: '2026-07-01T20:20:00+08:00',
    duration_minutes: 110
};

const otherExam: Exam = {
    ...baseExam,
    id: '2025-2026学年第二学期考试安排表.xlsx-1723',
    course_name: '算法分析与设计',
    course_code: 'JS113400S',
    start_timestamp: '2026-07-02T08:00:00+08:00',
    end_timestamp: '2026-07-02T09:50:00+08:00'
};

const uidForCourse = (content: string, courseName: string): string => {
    const event = content
        .split('BEGIN:VEVENT')
        .find(chunk => chunk.includes(`SUMMARY:考试: ${courseName}`));

    const uid = event?.match(/UID:([^\r\n]+)/)?.[1];
    if (!uid) throw new Error(`UID not found for ${courseName}`);
    return uid;
};

describe('exam-core calendar export', () => {
    it('generates Shanghai-time calendar events with escaped values', () => {
        const content = generateICSContent([baseExam], 'B240402', [30]);

        expect(content).toContain('BEGIN:VTIMEZONE');
        expect(content).toContain('TZID:Asia/Shanghai');
        expect(content).toContain('DTSTART;TZID=Asia/Shanghai:20260701T183000');
        expect(content).toContain('DTEND;TZID=Asia/Shanghai:20260701T202000');
        expect(content).toContain('LOCATION:[仙林] 教2－410');
        expect(content).toContain('备注: 携带铅笔\\,橡皮\\;证件');
        expect(content).toContain('TRIGGER:-PT30M');
    });

    it('keeps event UIDs stable regardless of selected exam order', () => {
        const single = generateICSContent([baseExam], 'B240402', []);
        const reordered = generateICSContent([otherExam, baseExam], 'B240402', []);

        expect(uidForCourse(single, baseExam.course_name)).toBe(
            uidForCourse(reordered, baseExam.course_name)
        );
    });
});
