import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
    SitegraphDocMetaSchema,
    SitegraphSearchManifestSchema
} from '../src';

const loadPublicJson = (relativePath: string): unknown => {
    return JSON.parse(readFileSync(new URL(relativePath, import.meta.url), 'utf-8'));
};

describe('search index contracts package', () => {
    it('accepts the committed public search manifest', () => {
        const manifest = SitegraphSearchManifestSchema.parse(
            loadPublicJson('../../../public/index/manifest.json')
        );

        expect(manifest.strategy).toBe('progressive-verifiable-static-search');
        expect(manifest.exam_vertical_preserved).toBe(true);
        expect(manifest.progressive_search.full_scan_supported).toBe(true);
        expect(manifest.verification_contract.shard_filter_supported).toBe(true);
        expect(manifest.sitegraph.full_shards.length).toBeGreaterThan(0);
    });

    it('keeps doc_meta_light free of full-document fields', () => {
        const docMeta = {
            doc_index: 0,
            id: 'jwc-detail-1',
            record_type: 'detail',
            facet: 'policy',
            title: '南京邮电大学本科生转专业管理办法',
            url: 'https://jwc.njupt.edu.cn/1/page.htm',
            source: '本科生院 / 教务处',
            section: '规章制度',
            nav_path: ['规章制度'],
            nav_path_text: '规章制度',
            attachment_count: 1,
            shard: { shard_id: 'policy__detail__2026__rules__b0', path: 'fixture.json' }
        };

        expect(SitegraphDocMetaSchema.parse(docMeta).id).toBe('jwc-detail-1');
        expect(SitegraphDocMetaSchema.safeParse({ ...docMeta, title: '' }).success).toBe(false);
    });
});

