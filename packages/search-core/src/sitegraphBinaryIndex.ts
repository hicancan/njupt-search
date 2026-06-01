import type { SitegraphImpactIndex, SitegraphLocalBodyIndex } from '@njupt-search/contracts';

const MAGIC_V1 = 'SGIXB001';
const MAGIC_V2 = 'SGIXB002';
const MAGIC_LENGTH = 8;
const decoder = new TextDecoder();

class BinaryCursor {
    private offset = 0;

    constructor(private readonly data: Uint8Array, private readonly source: string) {}

    readMagic(): string {
        const actual = decoder.decode(this.readBytes(MAGIC_LENGTH));
        if (actual !== MAGIC_V1 && actual !== MAGIC_V2) {
            throw new Error(`Validation failed for ${this.source}: invalid packed impact index header`);
        }
        return actual;
    }

    readUint32(): number {
        const b0 = this.data[this.offset];
        const b1 = this.data[this.offset + 1];
        const b2 = this.data[this.offset + 2];
        const b3 = this.data[this.offset + 3];
        if (b0 === undefined || b1 === undefined || b2 === undefined || b3 === undefined) {
            throw new Error(`Validation failed for ${this.source}: truncated uint32`);
        }
        this.offset += 4;
        const value = b0 | (b1 << 8) | (b2 << 16) | (b3 << 24);
        return value >>> 0;
    }

    readVarint(): number {
        let shift = 0;
        let value = 0;
        while (this.offset < this.data.length) {
            const byte = this.data[this.offset];
            if (byte === undefined) {
                throw new Error(`Validation failed for ${this.source}: truncated varint`);
            }
            this.offset += 1;
            value += (byte & 0x7f) * 2 ** shift;
            if ((byte & 0x80) === 0) return value;
            shift += 7;
            if (shift > 53) {
                throw new Error(`Validation failed for ${this.source}: varint exceeds safe integer range`);
            }
        }
        throw new Error(`Validation failed for ${this.source}: truncated varint`);
    }

    readByte(): number {
        const byte = this.data[this.offset];
        if (byte === undefined) {
            throw new Error(`Validation failed for ${this.source}: truncated byte`);
        }
        this.offset += 1;
        return byte;
    }

    readBytes(length: number): Uint8Array {
        if (this.offset + length > this.data.length) {
            throw new Error(`Validation failed for ${this.source}: truncated bytes`);
        }
        const value = this.data.subarray(this.offset, this.offset + length);
        this.offset += length;
        return value;
    }

    done(): boolean {
        return this.offset === this.data.length;
    }

    position(): number {
        return this.offset;
    }
}

const readTermFields = (
    cursor: BinaryCursor,
    collect: boolean
): Record<string, number[]> | null => {
    const fields: Record<string, number[]> = {};
    const fieldCount = cursor.readVarint();
    for (let fieldIndex = 0; fieldIndex < fieldCount; fieldIndex += 1) {
        const field = String.fromCharCode(cursor.readByte());
        const docCount = cursor.readVarint();
        const docIds: number[] = collect ? [] : [];
        let previous = 0;
        for (let docOffset = 0; docOffset < docCount; docOffset += 1) {
            const delta = cursor.readVarint();
            const docId = docOffset === 0 ? delta : previous + delta;
            if (collect) docIds.push(docId);
            previous = docId;
        }
        if (collect) fields[field] = docIds;
    }
    return collect ? fields : null;
};

const readV1Terms = (
    cursor: BinaryCursor,
    source: string,
    selectedTerms?: Set<string>
): SitegraphImpactIndex['terms'] => {
    const termCount = cursor.readVarint();
    const terms: SitegraphImpactIndex['terms'] = {};
    for (let termIndex = 0; termIndex < termCount; termIndex += 1) {
        const term = decoder.decode(cursor.readBytes(cursor.readVarint()));
        const collect = !selectedTerms || selectedTerms.has(term);
        const fields = readTermFields(cursor, collect);
        if (fields) terms[term] = fields;
    }
    if (!cursor.done()) {
        throw new Error(`Validation failed for ${source}: trailing bytes in packed impact index`);
    }
    return terms;
};

const readV2Terms = (
    data: Uint8Array,
    cursor: BinaryCursor,
    source: string,
    selectedTerms?: Set<string>
): SitegraphImpactIndex['terms'] => {
    const termCount = cursor.readVarint();
    const directory: Array<{ length: number; term: string }> = [];
    let payloadLengthTotal = 0;
    for (let termIndex = 0; termIndex < termCount; termIndex += 1) {
        const term = decoder.decode(cursor.readBytes(cursor.readVarint()));
        const length = cursor.readVarint();
        directory.push({ length, term });
        payloadLengthTotal += length;
    }
    const payloadStart = cursor.position();
    if (payloadStart + payloadLengthTotal !== data.length) {
        throw new Error(`Validation failed for ${source}: packed impact payload directory length mismatch`);
    }
    const terms: SitegraphImpactIndex['terms'] = {};
    let offset = payloadStart;
    for (const entry of directory) {
        const collect = !selectedTerms || selectedTerms.has(entry.term);
        if (collect) {
            const payloadCursor = new BinaryCursor(data.subarray(offset, offset + entry.length), `${source}:${entry.term}`);
            const fields = readTermFields(payloadCursor, true);
            if (fields) terms[entry.term] = fields;
        }
        offset += entry.length;
    }
    return terms;
};

const readPackedImpactIndex = <TIndex extends SitegraphImpactIndex = SitegraphImpactIndex>(
    buffer: ArrayBuffer,
    source: string,
    selectedTerms?: Set<string>
): TIndex => {
    const data = new Uint8Array(buffer);
    const cursor = new BinaryCursor(data, source);
    const magic = cursor.readMagic();
    const metadataLength = cursor.readUint32();
    const metadata = JSON.parse(decoder.decode(cursor.readBytes(metadataLength))) as Omit<TIndex, 'terms'>;
    const terms = magic === MAGIC_V2
        ? readV2Terms(data, cursor, source, selectedTerms)
        : readV1Terms(cursor, source, selectedTerms);
    return {
        ...metadata,
        terms,
    } as TIndex;
};

export const decodePackedImpactIndex = <TIndex extends SitegraphImpactIndex = SitegraphImpactIndex>(
    buffer: ArrayBuffer,
    source = 'packed impact index'
): TIndex => readPackedImpactIndex<TIndex>(buffer, source);

export const decodePackedImpactIndexTerms = <TIndex extends SitegraphImpactIndex = SitegraphImpactIndex>(
    buffer: ArrayBuffer,
    terms: string[],
    source = 'packed impact index'
): TIndex => readPackedImpactIndex<TIndex>(buffer, source, new Set(terms));

export const decodePackedLocalBodyIndex = (buffer: ArrayBuffer, source = 'packed local body index'): SitegraphLocalBodyIndex => {
    return decodePackedImpactIndex<SitegraphLocalBodyIndex>(buffer, source);
};

export const decodePackedLocalBodyIndexTerms = (
    buffer: ArrayBuffer,
    terms: string[],
    source = 'packed local body index'
): SitegraphLocalBodyIndex => {
    return decodePackedImpactIndexTerms<SitegraphLocalBodyIndex>(buffer, terms, source);
};
