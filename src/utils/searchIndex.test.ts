import { describe, expect, it } from 'vitest';
import { SearchDocument } from '@/types';
import { parseSearchDocuments, recallSearchDocuments } from './searchIndex';

const baseNotice: SearchDocument = {
    id: 'notice-1',
    kind: 'notice',
    source_id: 'xsc',
    channel_id: 'xsc_notice',
    channel: '学生工作通知',
    title: '关于2026年春季学期奖学金评选工作的通知',
    url: 'https://xsc.njupt.edu.cn/notice',
    source: '学生工作处',
    source_domain: 'xsc.njupt.edu.cn',
    source_type: 'central_admin',
    category: '奖助',
    domain: 'scholarship',
    intent: 'publicity',
    lifecycle: 'active',
    evidence: ['奖学金评选工作的通知'],
    confidence: 0.9,
    sub_category: null,
    deadline: null,
    action_required: false,
    action_type: null,
    action_summary: null,
    required_materials: [],
    sensitive: false,
    sensitive_types: [],
    review_required: false,
    risk_flags: [],
    audience: ['本科生'],
    published_at: '2026-05-20',
    content: '奖学金 评优 公示 学生资助',
    summary: '奖学金评选通知',
    attachments: [],
    tags: ['奖学金', '评优', '公示'],
    hash: 'notice-1',
    canonical: {
        doc_id: 'notice-1',
        canonical_url: 'https://xsc.njupt.edu.cn/notice',
        content_hash: 'notice-1',
        dedupe_key: 'notice-1',
    },
    rule_guard: {
        restricted: false,
        sensitive: false,
        low_evidence: false,
        duplicate: false,
        expired: false,
        evergreen: false,
        risk_flags: [],
        allow_llm: true,
        allow_full_text_display: true,
        review_required: false,
    },
    task_frames: [{
        task_id: 'task-notice-1',
        doc_id: 'notice-1',
        source_mode: 'generated_from_llm_fields',
        task_type: 'application',
        who: { audience: ['本科生'], college: [], grade: [], major: [], class_name: [] },
        what: '奖学金评选',
        action: { required: false, verb: '查看', object: '评选通知', summary: '查看奖学金评选通知。' },
        time: { published_at: '2026-05-20', deadline: null, lifecycle: 'active', urgency_days: null },
        materials: [],
        location: { place: null, online: null, contact: null },
        source: { source_id: 'xsc', channel_id: 'xsc_notice', authority: 0.96, official: true },
        evidence: [{ field: 'action', text: '奖学金评选工作的通知' }],
        risk: { sensitive: false, restricted: false, low_evidence: false, review_required: false },
        confidence: 0.9,
    }],
};

describe('recallSearchDocuments', () => {
    it('recalls relevant notices and displays them strictly by publish time', () => {
        const newerNotice: SearchDocument = {
            ...baseNotice,
            id: 'notice-2',
            title: '关于奖学金补充材料提交的通知',
            content: '奖学金 补充材料 提交',
            published_at: '2026-05-22',
            tags: ['奖学金', '材料'],
            hash: 'notice-2',
        };

        const results = recallSearchDocuments([baseNotice, newerNotice], '奖学金');

        expect(results.map(item => item.id)).toEqual(['notice-2', 'notice-1']);
        expect(results.every(item => item.score === 1)).toBe(true);
    });

    it('does not use category filtering for result inclusion', () => {
        const document: SearchDocument = {
            ...baseNotice,
            id: 'notice-misaligned-category',
            category: '公告',
            domain: 'scholarship',
            intent: 'publicity',
            title: '2026年奖学金名单公示',
            content: '奖学金 公示 名单',
            tags: ['奖学金', '公示'],
            hash: 'notice-misaligned-category',
        };

        expect(recallSearchDocuments([document], '奖学金 公示')[0]?.id).toBe('notice-misaligned-category');
    });

    it('rejects invalid production enum values instead of masking them', () => {
        const invalidDocument = {
            ...baseNotice,
            id: 'notice-invalid-domain',
            domain: 'campus_life',
        };

        expect(() => parseSearchDocuments([invalidDocument], 'fixture')).toThrow(/campus_life/);
    });
});
