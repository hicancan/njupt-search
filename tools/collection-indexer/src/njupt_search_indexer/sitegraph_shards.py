from __future__ import annotations

import base64
import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .sitegraph_artifact_io import write_hashed_json
from .sitegraph_index_postings import exhaustive_scan_blob
from .sitegraph_text import clean_text, sha256_text, sitegraph_tokens, stable_slug


def filter_token_hash_int(text: str, seed: int) -> int:
    value = (2166136261 ^ seed) & 0xFFFFFFFF
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * 16777619) & 0xFFFFFFFF
    return value


def build_filter_bitset(tokens: list[str], *, bit_count: int = 16384, hash_count: int = 3) -> dict[str, Any]:
    data = bytearray(bit_count // 8)
    for token in tokens:
        for seed in range(hash_count):
            bit = filter_token_hash_int(token, seed) % bit_count
            data[bit // 8] |= 1 << (bit % 8)
    return {
        "bitset_base64": base64.b64encode(bytes(data)).decode("ascii"),
        "bit_count": bit_count,
        "hash_count": hash_count,
    }


def shard_year(document: dict[str, Any]) -> str:
    date_text = clean_text(document.get("published_at")) or clean_text(document.get("version_date"))
    match = re.search(r"(20\d{2}|19\d{2})", date_text)
    return match.group(1) if match else "undated"


def shard_section(document: dict[str, Any]) -> str:
    nav_path = document.get("nav_path") if isinstance(document.get("nav_path"), list) else []
    section = nav_path[0] if nav_path else document.get("section_id") or document.get("section")
    return stable_slug(section, fallback="root", max_length=32)


def shard_bucket(document: dict[str, Any], bucket_count: int = 4) -> str:
    digest = hashlib.sha1(str(document.get("id") or "").encode("utf-8")).hexdigest()
    return f"b{int(digest[:2], 16) % bucket_count}"


def shard_id_for_document(document: dict[str, Any]) -> str:
    return "__".join(
        [
            stable_slug(document.get("facet"), fallback="facet"),
            stable_slug(document.get("record_type"), fallback="record"),
            shard_year(document),
            shard_section(document),
            shard_bucket(document),
        ]
    )


def build_locality_shards(
    documents: list[dict[str, Any]],
    *,
    public_root: Path,
    shard_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for document in documents:
        groups[shard_id_for_document(document)].append(document)

    shard_refs: list[dict[str, Any]] = []
    shard_by_id: dict[str, dict[str, Any]] = {}
    shard_filter: dict[str, dict[str, Any]] = {}
    for shard_id in sorted(groups):
        shard_docs = sorted(groups[shard_id], key=lambda item: int(item["doc_index"]))
        facets = sorted({str(item.get("facet")) for item in shard_docs})
        record_types = sorted({str(item.get("record_type")) for item in shard_docs})
        sections = sorted({str(item.get("section_id") or "unknown") for item in shard_docs})
        years = sorted({shard_year(item) for item in shard_docs})
        payload_docs = [
            {key: value for key, value in document.items() if key != "shard"}
            for document in shard_docs
        ]
        filter_tokens = sorted({
            token
            for document in payload_docs
            for token in sitegraph_tokens(exhaustive_scan_blob(document), cjk_max_n=5)
        })
        filter_bitset = build_filter_bitset(filter_tokens)
        filter_hash = sha256_text(filter_bitset["bitset_base64"], length=32)
        artifact = write_hashed_json(public_root, shard_dir, f"full.{shard_id}", payload_docs, compact=True)
        shard_ref = {
            "shard_id": shard_id,
            "path": artifact["path"],
            "sha256": artifact["sha256"],
            "bytes": artifact["bytes"],
            "count": len(shard_docs),
            "contains": "full_documents",
            "facet_range": facets,
            "record_type_range": record_types,
            "section_range": sections[:24],
            "year_range": years,
            "hash_bucket": shard_id.rsplit("__", 1)[-1],
            "filter_token_count": len(filter_tokens),
            "filter_sha256": filter_hash,
        }
        shard_filter[shard_id] = {
            **filter_bitset,
            "token_count": len(filter_tokens),
            "sha256": filter_hash,
            "hash_algorithm": "bloom-fnv1a32-utf8",
            "coverage_fields": ["title", "section", "nav_path", "summary", "content", "attachments", "url"],
        }
        shard_refs.append(shard_ref)
        shard_by_id[shard_id] = shard_ref
        for document in shard_docs:
            document["shard"] = {
                "shard_id": shard_id,
            }
    return shard_refs, shard_by_id, shard_filter
