import { z } from 'zod';
import type {
    SitegraphDocMeta,
    SitegraphFullDocument
} from '../source-sitegraph';

export type {
    SitegraphDocMeta,
    SitegraphFullDocument
};

export const SitegraphArtifactSchema = z.object({
    path: z.string().min(1),
    sha256: z.string().min(16),
    bytes: z.number(),
    role: z.string().min(1),
    load: z.string().min(1),
    count: z.number().optional()
}).passthrough();
export type SitegraphArtifact = z.infer<typeof SitegraphArtifactSchema>;

export const SitegraphFullShardSchema = z.object({
    shard_id: z.string().min(1),
    path: z.string().min(1),
    sha256: z.string().min(16),
    bytes: z.number(),
    count: z.number(),
    contains: z.literal('full_documents'),
    facet_range: z.array(z.string()),
    record_type_range: z.array(z.string()),
    section_range: z.array(z.string()),
    year_range: z.array(z.string()),
    hash_bucket: z.string().min(1)
}).passthrough();
export type SitegraphFullShard = z.infer<typeof SitegraphFullShardSchema>;

