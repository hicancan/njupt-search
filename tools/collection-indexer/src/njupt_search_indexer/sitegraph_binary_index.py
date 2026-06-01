from __future__ import annotations

import json
from typing import Any


PACKED_IMPACT_MAGIC = b"SGIXB001"


def encode_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("varint value must be non-negative")
    chunks = bytearray()
    current = value
    while current >= 0x80:
        chunks.append((current & 0x7F) | 0x80)
        current >>= 7
    chunks.append(current)
    return bytes(chunks)


def decode_varint(data: bytes, offset: int) -> tuple[int, int]:
    shift = 0
    value = 0
    current_offset = offset
    while current_offset < len(data):
        byte = data[current_offset]
        current_offset += 1
        value |= (byte & 0x7F) << shift
        if (byte & 0x80) == 0:
            return value, current_offset
        shift += 7
        if shift > 63:
            raise ValueError("varint is too large")
    raise ValueError("truncated varint")


def impact_index_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key != "terms"
    }


def pack_impact_index(payload: dict[str, Any]) -> bytes:
    metadata = json.dumps(impact_index_metadata(payload), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    terms = payload.get("terms")
    if not isinstance(terms, dict):
        raise ValueError("impact index payload missing terms")

    out = bytearray(PACKED_IMPACT_MAGIC)
    out.extend(len(metadata).to_bytes(4, "little"))
    out.extend(metadata)
    out.extend(encode_varint(len(terms)))
    for term, fields in sorted(terms.items()):
        term_bytes = str(term).encode("utf-8")
        out.extend(encode_varint(len(term_bytes)))
        out.extend(term_bytes)
        if not isinstance(fields, dict):
            raise ValueError(f"impact term fields must be an object: {term}")
        out.extend(encode_varint(len(fields)))
        for field, doc_ids in sorted(fields.items()):
            field_code = str(field)
            if len(field_code.encode("ascii")) != 1:
                raise ValueError(f"field code must be one ASCII byte: {field_code}")
            sorted_ids = sorted(int(item) for item in doc_ids)
            out.extend(field_code.encode("ascii"))
            out.extend(encode_varint(len(sorted_ids)))
            previous = 0
            for index, doc_id in enumerate(sorted_ids):
                delta = doc_id if index == 0 else doc_id - previous
                if delta < 0:
                    raise ValueError("doc ids must be sorted")
                out.extend(encode_varint(delta))
                previous = doc_id
    return bytes(out)


def unpack_impact_index(data: bytes) -> dict[str, Any]:
    if not data.startswith(PACKED_IMPACT_MAGIC):
        raise ValueError("packed impact index has invalid magic header")
    offset = len(PACKED_IMPACT_MAGIC)
    if offset + 4 > len(data):
        raise ValueError("packed impact index is missing metadata length")
    metadata_length = int.from_bytes(data[offset: offset + 4], "little")
    offset += 4
    metadata_end = offset + metadata_length
    if metadata_end > len(data):
        raise ValueError("packed impact index metadata is truncated")
    payload = json.loads(data[offset:metadata_end])
    offset = metadata_end
    term_count, offset = decode_varint(data, offset)
    terms: dict[str, dict[str, list[int]]] = {}
    for _ in range(term_count):
        term_length, offset = decode_varint(data, offset)
        term_end = offset + term_length
        if term_end > len(data):
            raise ValueError("packed impact term is truncated")
        term = data[offset:term_end].decode("utf-8")
        offset = term_end
        field_count, offset = decode_varint(data, offset)
        fields: dict[str, list[int]] = {}
        for _ in range(field_count):
            if offset >= len(data):
                raise ValueError("packed impact field code is truncated")
            field = chr(data[offset])
            offset += 1
            doc_count, offset = decode_varint(data, offset)
            doc_ids: list[int] = []
            previous = 0
            for index in range(doc_count):
                delta, offset = decode_varint(data, offset)
                doc_id = delta if index == 0 else previous + delta
                doc_ids.append(doc_id)
                previous = doc_id
            fields[field] = doc_ids
        terms[term] = fields
    if offset != len(data):
        raise ValueError("packed impact index has trailing bytes")
    payload["terms"] = terms
    return payload
