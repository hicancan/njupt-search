import {
    SitegraphAttachment,
    SitegraphAttachmentSchema,
    SitegraphDocMetaSchema,
    SitegraphExternalRecord,
    SitegraphExternalRecordSchema,
    SitegraphFullDocument,
    SitegraphFullDocumentSchema,
    SitegraphGlobalQueryDirectory,
    SitegraphGlobalQueryDirectorySchema,
    SitegraphImpactIndex,
    SitegraphImpactIndexSchema,
    SitegraphLocalBodyIndex,
    SitegraphLocalBodyIndexSchema,
    SitegraphLocalLightIndex,
    SitegraphLocalLightIndexSchema,
    SitegraphProofCatalog,
    SitegraphProofCatalogSchema,
    SitegraphSearchManifest,
    SitegraphSearchManifestSchema,
    SitegraphSourceManifest,
    SitegraphSourceManifestSchema,
    SitegraphSourceRegistry,
    SitegraphSourceRegistrySchema
} from '@njupt-search/contracts';
import { z } from 'zod';

export class SearchContractError extends Error {
    constructor(message: string) {
        super(message);
        this.name = 'SearchContractError';
    }
}

const MODEL_FIELD_PREFIX = ['l', 'l', 'm'].join('');
const TASK_FIELD_PREFIX = ['hy', 'task'].join('');
const LEGACY_FIELDS = new Set([
    MODEL_FIELD_PREFIX,
    `${MODEL_FIELD_PREFIX}_provider`,
    `${MODEL_FIELD_PREFIX}_schema_version`,
    'semantic_mode',
    'task_frames',
    `${MODEL_FIELD_PREFIX}_in_core_path`,
    `old_${TASK_FIELD_PREFIX}_removed`,
    'source_channel_production_enabled',
    'github_resource_production_enabled'
]);
const LOCAL_META_FORBIDDEN_FIELDS = new Set(['content', 'summary', 'attachments', 'provenance']);
const LEGACY_ARTIFACT_NAMES = new Set(['doc_meta_light', 'light_inverted_index']);

const valueAtPath = (payload: unknown, path: PropertyKey[]): unknown => {
    let current = payload;
    for (const part of path) {
        if (current === null || current === undefined) return undefined;
        current = (current as Record<PropertyKey, unknown>)[part];
    }
    return current;
};

const formatZodIssues = (payload: unknown, error: z.ZodError): string => {
    return error.issues.map(issue => {
        const fieldPath = issue.path.join('.') || '<root>';
        const invalidValue = valueAtPath(payload, issue.path);
        return `${fieldPath}: ${issue.message}; value=${JSON.stringify(invalidValue)}`;
    }).join('; ');
};

const parseArray = <T>(schema: z.ZodType<T>, payload: unknown, source: string): T[] => {
    try {
        return z.array(schema).parse(payload);
    } catch (e) {
        if (e instanceof z.ZodError) {
            throw new SearchContractError(`Validation failed for ${source}: ${formatZodIssues(payload, e)}`);
        }
        throw new SearchContractError(`Validation failed for ${source}: ${e instanceof Error ? e.message : String(e)}`);
    }
};

const assertNoLegacyFields = (payload: unknown, source: string, path = '$'): void => {
    if (Array.isArray(payload)) {
        payload.forEach((item, index) => assertNoLegacyFields(item, source, `${path}[${index}]`));
        return;
    }
    if (!payload || typeof payload !== 'object') return;
    for (const [key, value] of Object.entries(payload as Record<string, unknown>)) {
        if (LEGACY_FIELDS.has(key)) {
            throw new SearchContractError(`Validation failed for ${source}: ${path}.${key} is an obsolete search field`);
        }
        assertNoLegacyFields(value, source, `${path}.${key}`);
    }
};

export const parseSitegraphManifest = (payload: unknown, source = 'sitegraph manifest'): SitegraphSearchManifest => {
    try {
        assertNoLegacyFields(payload, source);
        const text = JSON.stringify(payload);
        if (text.includes('D:\\') || text.includes('D:/')) {
            throw new SearchContractError(`Validation failed for ${source}: public manifest must not expose local D: paths`);
        }
        const manifest = SitegraphSearchManifestSchema.parse(payload);
        for (const legacyName of LEGACY_ARTIFACT_NAMES) {
            if (legacyName in manifest.artifacts || manifest.core_search.first_screen_artifacts.includes(legacyName as never)) {
                throw new SearchContractError(`Validation failed for ${source}: legacy global artifact ${legacyName} is not a routed startup artifact`);
            }
        }
        return manifest;
    } catch (e) {
        if (e instanceof z.ZodError) {
            throw new SearchContractError(`Validation failed for ${source}: ${formatZodIssues(payload, e)}`);
        }
        throw new SearchContractError(`Validation failed for ${source}: ${e instanceof Error ? e.message : String(e)}`);
    }
};

export const parseSitegraphSourceRegistry = (payload: unknown, source = 'sitegraph source_registry'): SitegraphSourceRegistry => {
    try {
        assertNoLegacyFields(payload, source);
        return SitegraphSourceRegistrySchema.parse(payload);
    } catch (e) {
        if (e instanceof z.ZodError) {
            throw new SearchContractError(`Validation failed for ${source}: ${formatZodIssues(payload, e)}`);
        }
        throw new SearchContractError(`Validation failed for ${source}: ${e instanceof Error ? e.message : String(e)}`);
    }
};

export const parseSitegraphGlobalQueryDirectory = (
    payload: unknown,
    source = 'sitegraph global_query_directory'
): SitegraphGlobalQueryDirectory => {
    try {
        assertNoLegacyFields(payload, source);
        return SitegraphGlobalQueryDirectorySchema.parse(payload);
    } catch (e) {
        if (e instanceof z.ZodError) {
            throw new SearchContractError(`Validation failed for ${source}: ${formatZodIssues(payload, e)}`);
        }
        throw new SearchContractError(`Validation failed for ${source}: ${e instanceof Error ? e.message : String(e)}`);
    }
};

export const parseSitegraphSourceManifest = (payload: unknown, source = 'sitegraph source manifest'): SitegraphSourceManifest => {
    try {
        assertNoLegacyFields(payload, source);
        return SitegraphSourceManifestSchema.parse(payload);
    } catch (e) {
        if (e instanceof z.ZodError) {
            throw new SearchContractError(`Validation failed for ${source}: ${formatZodIssues(payload, e)}`);
        }
        throw new SearchContractError(`Validation failed for ${source}: ${e instanceof Error ? e.message : String(e)}`);
    }
};

export const parseSitegraphProofCatalog = (payload: unknown, source = 'sitegraph proof catalog'): SitegraphProofCatalog => {
    try {
        assertNoLegacyFields(payload, source);
        const parsed = SitegraphProofCatalogSchema.parse(payload);
        if (!parsed.state_model.includes('pending') || !parsed.state_model.includes('failed')) {
            throw new SearchContractError(`Validation failed for ${source}: proof catalog state model must include pending and failed`);
        }
        if (!parsed.complete_requires_no_states.includes('pending') || !parsed.complete_requires_no_states.includes('failed')) {
            throw new SearchContractError(`Validation failed for ${source}: proof catalog must reject completion with pending or failed shards`);
        }
        return parsed;
    } catch (e) {
        if (e instanceof z.ZodError) {
            throw new SearchContractError(`Validation failed for ${source}: ${formatZodIssues(payload, e)}`);
        }
        throw new SearchContractError(`Validation failed for ${source}: ${e instanceof Error ? e.message : String(e)}`);
    }
};

const validateLocalDocuments = (documents: unknown, source: string): void => {
    const docs = parseArray(SitegraphDocMetaSchema, documents, source);
    const ids = new Set<string>();
    for (const item of docs) {
        if (ids.has(item.id)) throw new SearchContractError(`${source} contains duplicate id: ${item.id}`);
        for (const field of LOCAL_META_FORBIDDEN_FIELDS) {
            if (field in item) {
                throw new SearchContractError(`Validation failed for ${source}: local index metadata must not contain ${field}`);
            }
        }
        ids.add(item.id);
    }
};

export const parseSitegraphLocalLightIndex = (payload: unknown, source = 'sitegraph local light index'): SitegraphLocalLightIndex => {
    try {
        assertNoLegacyFields(payload, source);
        const parsed = SitegraphLocalLightIndexSchema.parse(payload);
        validateLocalDocuments(parsed.documents, source);
        return parsed;
    } catch (e) {
        if (e instanceof z.ZodError) {
            throw new SearchContractError(`Validation failed for ${source}: ${formatZodIssues(payload, e)}`);
        }
        throw new SearchContractError(`Validation failed for ${source}: ${e instanceof Error ? e.message : String(e)}`);
    }
};

export const parseSitegraphLocalBodyIndex = (payload: unknown, source = 'sitegraph local body index'): SitegraphLocalBodyIndex => {
    try {
        assertNoLegacyFields(payload, source);
        return SitegraphLocalBodyIndexSchema.parse(payload);
    } catch (e) {
        if (e instanceof z.ZodError) {
            throw new SearchContractError(`Validation failed for ${source}: ${formatZodIssues(payload, e)}`);
        }
        throw new SearchContractError(`Validation failed for ${source}: ${e instanceof Error ? e.message : String(e)}`);
    }
};

export const parseSitegraphFullDocuments = (payload: unknown, source = 'sitegraph full shard'): SitegraphFullDocument[] => {
    assertNoLegacyFields(payload, source);
    return parseArray(SitegraphFullDocumentSchema, payload, source);
};

export const parseSitegraphAttachmentIndex = (payload: unknown, source = 'sitegraph attachment_index'): SitegraphAttachment[] => {
    return parseArray(SitegraphAttachmentSchema, payload, source);
};

export const parseSitegraphExternalIndex = (payload: unknown, source = 'sitegraph external_index'): SitegraphExternalRecord[] => {
    return parseArray(SitegraphExternalRecordSchema, payload, source);
};

export const parseSitegraphImpactIndex = (payload: unknown, source = 'sitegraph impact_index'): SitegraphImpactIndex => {
    try {
        return SitegraphImpactIndexSchema.parse(payload);
    } catch (e) {
        if (e instanceof z.ZodError) {
            throw new SearchContractError(`Validation failed for ${source}: ${formatZodIssues(payload, e)}`);
        }
        throw new SearchContractError(`Validation failed for ${source}: ${e instanceof Error ? e.message : String(e)}`);
    }
};
