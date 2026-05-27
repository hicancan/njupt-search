import { z } from 'zod';
import {
    ExamSchema,
    ManifestSchema
} from '../../../contracts/src/exam';
import type {
    Exam,
    Manifest
} from '../../../contracts/src/exam';

export type {
    Exam,
    Manifest
} from '../../../contracts/src/exam';

export class DataContractError extends Error {
    constructor(message: string) {
        super(message);
        this.name = 'DataContractError';
    }
}

export const parseExamData = (payload: unknown, source = 'exam data'): Exam[] => {
    try {
        const exams = z.array(ExamSchema).parse(payload);
        const ids = new Set<string>();
        for (const item of exams) {
            if (ids.has(item.id)) {
                throw new DataContractError(`${source} contains duplicate id: ${item.id}`);
            }
            ids.add(item.id);
        }
        return exams as unknown as Exam[];
    } catch (e) {
        throw new DataContractError(`Validation failed for ${source}: ${e instanceof Error ? e.message : String(e)}`);
    }
};

export const parseManifest = (payload: unknown, source = 'data summary'): Manifest => {
    try {
        return ManifestSchema.parse(payload) as unknown as Manifest;
    } catch (e) {
        throw new DataContractError(`Validation failed for ${source}: ${e instanceof Error ? e.message : String(e)}`);
    }
};

export const assertManifestMatchesExams = (manifest: Manifest, exams: Exam[]) => {
    if (manifest.total_records !== exams.length) {
        throw new DataContractError(
            `data_summary.total_records=${manifest.total_records} does not match all_exams.length=${exams.length}`
        );
    }
};
