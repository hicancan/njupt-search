import type { SitegraphImpactIndex, SitegraphLocalBodyIndex } from '@njupt-search/contracts';

const MAGIC = 'SGIXB001';
const decoder = new TextDecoder();

class BinaryCursor {
    private offset = 0;

    constructor(private readonly data: Uint8Array, private readonly source: string) {}

    readMagic(): void {
        const actual = decoder.decode(this.readBytes(MAGIC.length));
        if (actual !== MAGIC) {
            throw new Error(`Validation failed for ${this.source}: invalid packed impact index header`);
        }
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
}

export const decodePackedImpactIndex = <TIndex extends SitegraphImpactIndex = SitegraphImpactIndex>(
    buffer: ArrayBuffer,
    source = 'packed impact index'
): TIndex => {
    const cursor = new BinaryCursor(new Uint8Array(buffer), source);
    cursor.readMagic();
    const metadataLength = cursor.readUint32();
    const metadata = JSON.parse(decoder.decode(cursor.readBytes(metadataLength))) as Omit<TIndex, 'terms'>;
    const termCount = cursor.readVarint();
    const terms: SitegraphImpactIndex['terms'] = {};
    for (let termIndex = 0; termIndex < termCount; termIndex += 1) {
        const term = decoder.decode(cursor.readBytes(cursor.readVarint()));
        const fieldCount = cursor.readVarint();
        const fields: Record<string, number[]> = {};
        for (let fieldIndex = 0; fieldIndex < fieldCount; fieldIndex += 1) {
            const field = String.fromCharCode(cursor.readByte());
            const docCount = cursor.readVarint();
            const docIds: number[] = [];
            let previous = 0;
            for (let docOffset = 0; docOffset < docCount; docOffset += 1) {
                const delta = cursor.readVarint();
                const docId = docOffset === 0 ? delta : previous + delta;
                docIds.push(docId);
                previous = docId;
            }
            fields[field] = docIds;
        }
        terms[term] = fields;
    }
    if (!cursor.done()) {
        throw new Error(`Validation failed for ${source}: trailing bytes in packed impact index`);
    }
    return {
        ...metadata,
        terms,
    } as TIndex;
};

export const decodePackedLocalBodyIndex = (buffer: ArrayBuffer, source = 'packed local body index'): SitegraphLocalBodyIndex => {
    return decodePackedImpactIndex<SitegraphLocalBodyIndex>(buffer, source);
};
