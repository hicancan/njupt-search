import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
    SitegraphDocMetaSchema,
    SitegraphGlobalQueryDirectorySchema,
    SitegraphLocalLightIndexSchema,
    SitegraphSearchManifestSchema,
    SitegraphSourceManifestSchema,
    SitegraphSourceRegistrySchema
} from '../src';

const loadPublicJson = (relativePath: string): unknown => {
    return JSON.parse(readFileSync(new URL(relativePath, import.meta.url), 'utf-8'));
};

const required = <T>(value: T | undefined, message: string): T => {
    if (value === undefined) throw new Error(message);
    return value;
};

describe('search index contracts package', () => {
    it('accepts the committed public search manifest', () => {
        const manifest = SitegraphSearchManifestSchema.parse(
            loadPublicJson('../../../apps/web/public/generated/collections/njupt-public/manifest.json')
        );

        expect(manifest.strategy).toBe('routed-verifiable-static-search');
        expect(manifest.exam_vertical_preserved).toBe(true);
        expect(manifest.core_search.first_screen_artifacts).toEqual(['source_registry', 'global_query_directory', 'query_aliases']);
        expect(manifest.progressive_search.full_scan_supported).toBe(true);
        expect(manifest.verification_contract.shard_filter_supported).toBe(true);
        expect(manifest.verification_contract.proof_catalog_artifact_family).toBe('proof_catalogs');
        expect(manifest.verification_contract.completion_requires_ledger).toBe(true);
        expect('full_shards' in manifest.sitegraph).toBe(false);
        expect(Object.keys(manifest.sitegraph.source_manifests).length).toBeGreaterThan(0);
        expect('doc_meta_light' in manifest.artifacts).toBe(false);
        expect('light_inverted_index' in manifest.artifacts).toBe(false);
    });

    it('accepts routed bootstrap artifacts and source manifests', () => {
        const manifest = SitegraphSearchManifestSchema.parse(
            loadPublicJson('../../../apps/web/public/generated/collections/njupt-public/manifest.json')
        );
        const sourceRegistry = SitegraphSourceRegistrySchema.parse(
            loadPublicJson(`../../../apps/web/public/${manifest.artifacts.source_registry.path}`)
        );
        const queryDirectory = SitegraphGlobalQueryDirectorySchema.parse(
            loadPublicJson(`../../../apps/web/public/${manifest.artifacts.global_query_directory.path}`)
        );
        const sourceManifest = SitegraphSourceManifestSchema.parse(
            loadPublicJson(`../../../apps/web/public/${manifest.sitegraph.source_manifests.jwc.path}`)
        );

        expect(sourceRegistry.sources.map(source => source.source_id).sort()).toEqual(['cxcy', 'jwc', 'xsc']);
        expect(queryDirectory.entry_count).toBe(Object.keys(queryDirectory.entries).length);
        expect(queryDirectory.entries['大创']?.local_index_ids.length).toBeGreaterThan(0);
        expect(sourceManifest.local_indexes.length).toBeGreaterThan(0);
        expect(sourceManifest.full_shards.length).toBeGreaterThan(0);
        expect(sourceManifest.artifacts.proof_catalog?.role).toBe('proof_catalog');
    });

    it('keeps local light index metadata free of full-document fields', () => {
        const manifest = SitegraphSearchManifestSchema.parse(
            loadPublicJson('../../../apps/web/public/generated/collections/njupt-public/manifest.json')
        );
        const sourceManifest = SitegraphSourceManifestSchema.parse(
            loadPublicJson(`../../../apps/web/public/${manifest.sitegraph.source_manifests.jwc.path}`)
        );
        const firstLocalIndex = required(sourceManifest.local_indexes[0], 'expected a local light index fixture');
        const localLightIndex = SitegraphLocalLightIndexSchema.parse(
            loadPublicJson(`../../../apps/web/public/${firstLocalIndex.light_index.path}`)
        );
        const firstDoc = required(localLightIndex.documents[0], 'expected local metadata');

        expect(firstDoc.source_id).toBe('jwc');
        expect('content' in firstDoc).toBe(false);
        expect('summary' in firstDoc).toBe(false);
        expect('attachments' in firstDoc).toBe(false);
        expect('provenance' in firstDoc).toBe(false);
        expect('tokens' in localLightIndex).toBe(false);
        expect(localLightIndex.scoring_model).toBe('impact-ordered-block-max-bm25f-lite-v2');
        expect(Object.keys(localLightIndex.terms).length).toBeGreaterThan(0);

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
