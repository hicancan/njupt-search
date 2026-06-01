from __future__ import annotations

import json
from typing import Any


PACKED_IMPACT_MAGIC_V1 = b"SGIXB001"
PACKED_IMPACT_MAGIC_V2 = b"SGIXB002"
PACKED_IMPACT_MAGIC = PACKED_IMPACT_MAGIC_V2


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


def _pack_term_fields(fields: dict[str, Any], term: str) -> bytes:
    out = bytearray()
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


def pack_impact_index(payload: dict[str, Any]) -> bytes:
    metadata = json.dumps(impact_index_metadata(payload), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    terms = payload.get("terms")
    if not isinstance(terms, dict):
        raise ValueError("impact index payload missing terms")

    out = bytearray(PACKED_IMPACT_MAGIC)
    out.extend(len(metadata).to_bytes(4, "little"))
    out.extend(metadata)
    packed_terms: list[tuple[str, bytes, bytes]] = []
    for term, fields in sorted(terms.items()):
        term_bytes = str(term).encode("utf-8")
        packed_terms.append((str(term), term_bytes, _pack_term_fields(fields, str(term))))

    out.extend(encode_varint(len(packed_terms)))
    for _term, term_bytes, payload_bytes in packed_terms:
        out.extend(encode_varint(len(term_bytes)))
        out.extend(term_bytes)
        out.extend(encode_varint(len(payload_bytes)))
    for _term, _term_bytes, payload_bytes in packed_terms:
        out.extend(payload_bytes)
    return bytes(out)


def _unpack_term_fields(data: bytes, offset: int, end: int, *, collect: bool = True) -> tuple[dict[str, list[int]], int]:
    field_count, offset = decode_varint(data, offset)
    fields: dict[str, list[int]] = {}
    for _ in range(field_count):
        if offset >= end:
            raise ValueError("packed impact field code is truncated")
        field = chr(data[offset])
        offset += 1
        doc_count, offset = decode_varint(data, offset)
        doc_ids: list[int] = []
        previous = 0
        for index in range(doc_count):
            delta, offset = decode_varint(data, offset)
            if offset > end:
                raise ValueError("packed impact doc ids are truncated")
            doc_id = delta if index == 0 else previous + delta
            if collect:
                doc_ids.append(doc_id)
            previous = doc_id
        if collect:
            fields[field] = doc_ids
    if offset != end:
        raise ValueError("packed impact term payload has trailing bytes")
    return fields, offset


def _selected_term_bytes(selected_terms: set[str] | None) -> set[bytes] | None:
    if selected_terms is None:
        return None
    return {term.encode("utf-8") for term in selected_terms}


def _unpack_v1_terms(data: bytes, offset: int, selected_terms: set[str] | None = None) -> tuple[dict[str, dict[str, list[int]]], int]:
    term_count, offset = decode_varint(data, offset)
    selected_bytes = _selected_term_bytes(selected_terms)
    terms: dict[str, dict[str, list[int]]] = {}
    for _ in range(term_count):
        term_length, offset = decode_varint(data, offset)
        term_end = offset + term_length
        if term_end > len(data):
            raise ValueError("packed impact term is truncated")
        term_bytes = data[offset:term_end]
        offset = term_end
        collect = selected_bytes is None or term_bytes in selected_bytes
        term = term_bytes.decode("utf-8") if collect else ""
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
                if collect:
                    doc_ids.append(doc_id)
                previous = doc_id
            if collect:
                fields[field] = doc_ids
        if collect:
            terms[term] = fields
    return terms, offset


def _unpack_v2_terms(data: bytes, offset: int, selected_terms: set[str] | None = None) -> tuple[dict[str, dict[str, list[int]]], int]:
    term_count, offset = decode_varint(data, offset)
    selected_bytes = _selected_term_bytes(selected_terms)
    directory: list[tuple[str, int, bool]] = []
    payload_length_total = 0
    for _ in range(term_count):
        term_length, offset = decode_varint(data, offset)
        term_end = offset + term_length
        if term_end > len(data):
            raise ValueError("packed impact term is truncated")
        term_bytes = data[offset:term_end]
        offset = term_end
        payload_length, offset = decode_varint(data, offset)
        collect = selected_bytes is None or term_bytes in selected_bytes
        term = term_bytes.decode("utf-8") if collect else ""
        directory.append((term, payload_length, collect))
        payload_length_total += payload_length
    payload_start = offset
    if payload_start + payload_length_total != len(data):
        raise ValueError("packed impact payload directory length mismatch")

    terms: dict[str, dict[str, list[int]]] = {}
    for term, payload_length, collect in directory:
        payload_end = offset + payload_length
        if payload_end > len(data):
            raise ValueError("packed impact term payload is truncated")
        if collect:
            fields, _ = _unpack_term_fields(data, offset, payload_end, collect=True)
            terms[term] = fields
        offset = payload_end
    return terms, offset


def _unpack_impact_index(data: bytes, selected_terms: set[str] | None = None) -> dict[str, Any]:
    if data.startswith(PACKED_IMPACT_MAGIC_V2):
        magic = PACKED_IMPACT_MAGIC_V2
    elif data.startswith(PACKED_IMPACT_MAGIC_V1):
        magic = PACKED_IMPACT_MAGIC_V1
    else:
        raise ValueError("packed impact index has invalid magic header")
    offset = len(magic)
    if offset + 4 > len(data):
        raise ValueError("packed impact index is missing metadata length")
    metadata_length = int.from_bytes(data[offset: offset + 4], "little")
    offset += 4
    metadata_end = offset + metadata_length
    if metadata_end > len(data):
        raise ValueError("packed impact index metadata is truncated")
    payload = json.loads(data[offset:metadata_end])
    offset = metadata_end
    terms, offset = _unpack_v2_terms(data, offset, selected_terms) if magic == PACKED_IMPACT_MAGIC_V2 else _unpack_v1_terms(data, offset, selected_terms)
    if offset != len(data):
        raise ValueError("packed impact index has trailing bytes")
    payload["terms"] = terms
    return payload


def unpack_impact_index(data: bytes) -> dict[str, Any]:
    return _unpack_impact_index(data)


def unpack_impact_terms(data: bytes, terms: list[str] | set[str]) -> dict[str, Any]:
    return _unpack_impact_index(data, set(terms))
