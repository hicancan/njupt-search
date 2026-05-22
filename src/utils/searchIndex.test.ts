import { describe, expect, it } from 'vitest';
import { Exam, SearchDocument } from '@/types';
import { buildExamDocuments, getLearningResources, rankSearchDocuments } from './searchIndex';

const baseNotice: SearchDocument = {
    id: 'notice-1',
    kind: 'notice',
    title: '关于2026年春季学期奖学金评选工作的通知',
    url: 'https://xsc.njupt.edu.cn/notice',
    source: '学生工作处',
    source_domain: 'xsc.njupt.edu.cn',
    category: '奖助',
    audience: ['本科生'],
    published_at: '2026-05-20',
    content: '奖学金 评优 公示 学生资助',
    summary: '奖学金评选通知',
    attachments: [],
    student_score: 0.95,
    freshness_score: 1,
    importance_score: 0.9,
    source_weight: 0.96,
    tags: ['奖学金', '评优', '公示'],
    hash: 'notice-1',
};

describe('rankSearchDocuments', () => {
    it('ranks student-facing notices by direct keyword match', () => {
        const lowPriority: SearchDocument = {
            ...baseNotice,
            id: 'notice-2',
            title: '党委理论学习中心组学习通知',
            category: '公告',
            content: '党委理论学习 会议',
            student_score: 0.2,
            tags: ['公告'],
            hash: 'notice-2',
        };

        const results = rankSearchDocuments([lowPriority, baseNotice], '奖学金 公示', '全部');

        expect(results[0]?.id).toBe('notice-1');
        expect(results[0]?.score).toBeGreaterThan(results[1]?.score || 0);
    });

    it('converts exam records into searchable exam documents', () => {
        const exam: Exam = {
            id: 'sheet-2',
            class_name: 'B250403',
            course_name: '数据结构',
            location: '教2-201',
            start_timestamp: '2026-06-29T08:00:00+08:00',
            end_timestamp: '2026-06-29T09:50:00+08:00',
            duration_minutes: 110,
            raw_time: '2026年06月29日(08:00-09:50)',
        };

        const [document] = buildExamDocuments([exam]);

        expect(document?.kind).toBe('exam');
        expect(document?.category).toBe('考试');
        expect(document?.class_name).toBe('B250403');
        expect(rankSearchDocuments([document as SearchDocument], 'B250403', '考试')[0]?.id).toBe('exam-sheet-2');
    });

    it('only shows learning resources for course or exam intent', () => {
        expect(getLearningResources('数据结构 复习').length).toBeGreaterThan(0);
        expect(getLearningResources('后勤 停电')).toHaveLength(0);
    });
});
