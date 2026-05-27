import { z } from 'zod';

export const SitegraphRecordTypeSchema = z.enum(['detail', 'attachment', 'external', 'utility']);
export type SitegraphRecordType = z.infer<typeof SitegraphRecordTypeSchema>;

export const SitegraphFacetSchema = z.enum([
    'notice_article',
    'policy',
    'workflow',
    'download',
    'system',
    'exam',
    'news',
    'external'
]);
export type SitegraphFacet = z.infer<typeof SitegraphFacetSchema>;

export const SitegraphProvenanceSchema = z.object({
    site_id: z.string(),
    section_id: z.string().nullable().optional(),
    nav_path: z.array(z.string()).default([]),
    source_url: z.string().nullable().optional(),
    outcome: z.string(),
    external_category: z.string().nullable().optional()
}).passthrough();
export type SitegraphProvenance = z.infer<typeof SitegraphProvenanceSchema>;

export const SitegraphShardRefSchema = z.object({
    shard_id: z.string().min(1),
    path: z.string().optional(),
}).passthrough();
export type SitegraphShardRef = z.infer<typeof SitegraphShardRefSchema>;

export const SitegraphDocMetaSchema = z.object({
    doc_index: z.number(),
    id: z.string().min(1),
    record_type: SitegraphRecordTypeSchema,
    facet: SitegraphFacetSchema,
    title: z.string().min(1),
    url: z.string().min(1).optional(),
    source: z.string().min(1).optional(),
    section_id: z.string().nullable().optional(),
    section: z.string().min(1),
    nav_path: z.array(z.string()).default([]),
    nav_path_text: z.string().default(''),
    published_at: z.string().nullable().optional(),
    attachment_count: z.number().default(0).optional(),
    collection_method: z.string().min(1).optional(),
    shard: SitegraphShardRefSchema
}).passthrough();
export type SitegraphDocMeta = z.infer<typeof SitegraphDocMetaSchema>;

export const SitegraphAttachmentSchema = z.object({
    attachment_id: z.string().min(1),
    name: z.string().min(1),
    url: z.string().min(1),
    extension: z.string().nullable().optional(),
    parent_url: z.string().min(1),
    parent_doc_id: z.string().nullable().optional(),
    section_id: z.string().nullable().optional(),
    section: z.string().min(1),
    nav_path: z.array(z.string()).default([]),
    metadata_only: z.literal(true),
    position: z.number().nullable().optional()
}).passthrough();
export type SitegraphAttachment = z.infer<typeof SitegraphAttachmentSchema>;

export const SitegraphFullDocumentSchema = z.object({
    doc_index: z.number(),
    id: z.string().min(1),
    record_type: SitegraphRecordTypeSchema,
    page_type: z.string().min(1),
    facet: SitegraphFacetSchema,
    title: z.string().min(1),
    url: z.string().min(1),
    source: z.string().min(1),
    source_domain: z.string().min(1),
    section_id: z.string().nullable().optional(),
    section: z.string().min(1),
    nav_path: z.array(z.string()).default([]),
    nav_path_text: z.string().default(''),
    published_at: z.string().nullable().optional(),
    publisher: z.string().nullable().optional(),
    summary: z.string().default(''),
    attachment_count: z.number().default(0),
    hash: z.string().min(1),
    tags: z.array(z.string()).default([]),
    collection_method: z.string().min(1),
    provenance: SitegraphProvenanceSchema,
    content: z.string().min(1),
    attachments: z.array(SitegraphAttachmentSchema).default([])
}).passthrough();
export type SitegraphFullDocument = z.infer<typeof SitegraphFullDocumentSchema>;

export const SitegraphExternalRecordSchema = z.object({
    external_id: z.string().min(1),
    label: z.string().min(1),
    url: z.string().min(1),
    category: z.string().min(1),
    source_url: z.string().nullable().optional(),
    source_section_id: z.string().nullable().optional(),
    document_id: z.string().min(1),
    outcome: z.string().min(1)
}).passthrough();
export type SitegraphExternalRecord = z.infer<typeof SitegraphExternalRecordSchema>;
