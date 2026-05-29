from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from .sitegraph_artifact_io import artifact_entry, write_hashed_json, write_json
from .sitegraph_documents import build_documents, section_label, site_display_name
from .sitegraph_source import (
    COUNT_FIELDS,
    load_collection_source_packages,
    package_source_id,
    validate_sitegraph_package,
)
from .sitegraph_text import (
    clean_text,
    normalize_text,
    sha256_text,
    sitegraph_tokens,
    stable_slug,
)


BASE_DIR = Path(__file__).resolve().parents[4]
PUBLIC_ROOT = BASE_DIR / "apps" / "web" / "public"
COLLECTION_ID = "njupt-public"
PUBLIC_INDEX_DIR = PUBLIC_ROOT / "generated" / "collections" / COLLECTION_ID
PUBLIC_SITEGRAPH_DIR = PUBLIC_INDEX_DIR / "sitegraph"
PUBLIC_ARTIFACT_DIR = PUBLIC_SITEGRAPH_DIR / "artifacts"
PUBLIC_SHARD_DIR = PUBLIC_SITEGRAPH_DIR / "shards"
OBSOLETE_INDEX_DIR = PUBLIC_ROOT / "index"


def configure_collection_output(collection_id: str = COLLECTION_ID, output_dir: Path | None = None) -> None:
    global COLLECTION_ID, PUBLIC_INDEX_DIR, PUBLIC_SITEGRAPH_DIR, PUBLIC_ARTIFACT_DIR, PUBLIC_SHARD_DIR

    if collection_id != "njupt-public":
        raise ValueError("Only collection-id njupt-public is currently supported")
    target = (output_dir.resolve() if output_dir is not None else PUBLIC_ROOT / "generated" / "collections" / collection_id)
    try:
        target.relative_to(PUBLIC_ROOT)
    except ValueError as exc:
        raise ValueError(f"collection output must be under {PUBLIC_ROOT}") from exc

    COLLECTION_ID = collection_id
    PUBLIC_INDEX_DIR = target
    PUBLIC_SITEGRAPH_DIR = PUBLIC_INDEX_DIR / "sitegraph"
    PUBLIC_ARTIFACT_DIR = PUBLIC_SITEGRAPH_DIR / "artifacts"
    PUBLIC_SHARD_DIR = PUBLIC_SITEGRAPH_DIR / "shards"

QUERY_SYNONYMS: dict[str, list[str]] = {
    "校历": ["教学日历", "教学周历", "2025-2026学年校历"],
    "慕课考试": ["慕课", "MOOC", "SPOC", "在线开放课程", "线下考试"],
    "期末考试": ["期末", "考试安排", "考场安排", "考试周"],
    "转专业": ["专业变更", "转入转出", "转专业管理办法"],
    "规章制度": ["规章", "制度", "管理办法", "政策文件"],
    "办事流程": ["流程", "办理指南", "办事指南", "申请流程"],
    "学生相关文件及表格": ["学生表格", "常用下载", "表格下载", "学生相关文件"],
    "教务管理系统": ["正方教务", "教务系统", "jwxt"],
    "信息门户": ["综合信息服务", "智慧校园", "统一身份认证"],
    "大创": ["大学生创新创业", "创新创业", "创新训练", "创业训练"],
    "推免": ["免试攻读研究生", "推荐免试", "推免生"],
    "成绩": ["成绩查询", "成绩单", "绩点", "成绩复核"],
    "附件1": ["附件 1", "附件一", "附件"],
    "xlsx": ["xls", "Excel", "表格"],
    "学工": ["学生工作", "学生工作部", "学工要闻"],
    "奖学金": ["助学金", "资助", "评奖评优"],
    "困难认定": ["家庭经济困难学生认定", "家庭经济困难", "困难学生认定", "资助认定"],
    "助学金": ["资助", "奖助学金", "家庭经济困难"],
    "辅导员": ["辅导员队伍建设", "辅导员宣讲团"],
    "心理健康": ["心理咨询", "心理中心"],
    "双创": ["双创信息管理系统", "双创基地"],
    "互联网+": [],
    "竞赛报名": ["创新创业竞赛报名", "学科竞赛报名", "大赛报名"],
}

FIELD_CODES = {
    "title": "t",
    "section": "s",
    "nav_path": "n",
    "attachment": "a",
    "external": "e",
    "system": "y",
    "tag": "g",
    "summary": "m",
    "content": "c",
}

LIGHT_FIELD_CODES = {key: FIELD_CODES[key] for key in ("title", "section", "nav_path", "attachment", "external", "system", "tag")}
BODY_FIELD_CODES = {key: FIELD_CODES[key] for key in ("summary", "content")}

FACET_ORDER = ("notice_article", "policy", "workflow", "download", "system", "exam", "news", "external")


def filter_token_hash(text: str) -> str:
    value = 2166136261
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * 16777619) & 0xFFFFFFFF
    return f"{value:08x}"


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


def producer_ref() -> str:
    for env_name in ("GITHUB_SHA", "GITHUB_REF_NAME"):
        value = os.environ.get(env_name)
        if value:
            return value
    try:
        return subprocess.check_output(["git", "rev-parse", "--short=12", "HEAD"], cwd=BASE_DIR, text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "local-unversioned"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def query_alias_payload() -> dict[str, dict[str, list[str]]]:
    return {
        key: {"aliases": aliases}
        for key, aliases in sorted(QUERY_SYNONYMS.items())
    }


def add_postings(index: dict[str, dict[str, set[int]]], doc_index: int, field_code: str, tokens: set[str]) -> None:
    for token in tokens:
        if not token:
            continue
        index[token][field_code].add(doc_index)


def compact_postings(raw_index: dict[str, dict[str, set[int]]]) -> dict[str, dict[str, list[int]]]:
    tokens: dict[str, dict[str, list[int]]] = {}
    for token, fields in raw_index.items():
        compact_fields: dict[str, list[int]] = {}
        for field, ids in fields.items():
            compact_fields[field] = sorted(ids)
        tokens[token] = compact_fields
    return tokens


def build_light_inverted_index(documents: list[dict[str, Any]]) -> dict[str, Any]:
    raw_index: dict[str, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    for document in documents:
        doc_index = int(document["doc_index"])
        add_postings(raw_index, doc_index, FIELD_CODES["title"], sitegraph_tokens(document.get("title"), cjk_max_n=4, cap=120))
        add_postings(raw_index, doc_index, FIELD_CODES["section"], sitegraph_tokens([document.get("section"), document.get("nav_path_text")], cjk_max_n=4, cap=80))
        add_postings(raw_index, doc_index, FIELD_CODES["nav_path"], sitegraph_tokens(" ".join(document.get("nav_path") or []), cjk_max_n=4, cap=80))
        add_postings(raw_index, doc_index, FIELD_CODES["tag"], sitegraph_tokens(" ".join(document.get("tags") or []), cjk_max_n=4))
        attachment_text = " ".join(
            " ".join(clean_text(attachment.get(field)) for field in ("name", "extension", "section"))
            for attachment in document.get("attachments") or []
        )
        add_postings(raw_index, doc_index, FIELD_CODES["attachment"], sitegraph_tokens(attachment_text, cjk_max_n=4, cap=80))
        if document.get("record_type") == "external":
            add_postings(raw_index, doc_index, FIELD_CODES["external"], sitegraph_tokens([document.get("title"), document.get("url")], cjk_max_n=5))
        if document.get("record_type") == "utility" or document.get("facet") == "system":
            add_postings(raw_index, doc_index, FIELD_CODES["system"], sitegraph_tokens([document.get("title"), document.get("url"), document.get("section")], cjk_max_n=5))

    return {
        "version": "sitegraph-light-inverted-progressive",
        "tokenizer": "nfkc-lower-cjk-ngram-code",
        "field_codes": LIGHT_FIELD_CODES,
        "entry_fields": ["title", "section", "nav_path", "tag", "attachment", "external", "system"],
        "tokens": compact_postings(raw_index),
    }


def build_body_inverted_index(documents: list[dict[str, Any]]) -> dict[str, Any]:
    raw_index: dict[str, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    for document in documents:
        doc_index = int(document["doc_index"])
        add_postings(raw_index, doc_index, FIELD_CODES["summary"], sitegraph_tokens(document.get("summary"), cjk_max_n=4, cap=80))
        add_postings(raw_index, doc_index, FIELD_CODES["content"], sitegraph_tokens(document.get("content"), cjk_max_n=3, cap=180))
    return {
        "version": "sitegraph-body-inverted-progressive",
        "tokenizer": "nfkc-lower-cjk-ngram-code",
        "field_codes": BODY_FIELD_CODES,
        "entry_fields": ["summary", "content"],
        "tokens": compact_postings(raw_index),
    }


def exhaustive_scan_blob(document: dict[str, Any]) -> str:
    attachment_text = " ".join(
        " ".join(clean_text(attachment.get(field)) for field in ("name", "extension", "url", "section", "parent_url"))
        for attachment in document.get("attachments") or []
    )
    return normalize_text(
        " ".join(
            [
                clean_text(document.get("title")),
                clean_text(document.get("section")),
                " ".join(clean_text(item) for item in document.get("nav_path") or []),
                clean_text(document.get("nav_path_text")),
                clean_text(document.get("summary")),
                clean_text(document.get("content")),
                clean_text(document.get("url")),
                attachment_text,
            ]
        )
    )


def measure_representative_full_scan_ms(documents: list[dict[str, Any]], query: str = "校历") -> float:
    normalized_query = normalize_text(query)
    terms = sitegraph_tokens(query, cjk_max_n=5)
    started = perf_counter()
    matches = 0
    for document in documents:
        blob = exhaustive_scan_blob(document)
        if (normalized_query and normalized_query in blob) or any(term in blob for term in terms):
            matches += 1
    elapsed_ms = (perf_counter() - started) * 1000
    # Touch the match count so the measurement cannot be optimized away by future rewrites.
    return round(elapsed_ms + (matches * 0), 3)


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


def build_locality_shards(documents: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
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
        artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_SHARD_DIR, f"full.{shard_id}", payload_docs, compact=True)
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


def aggregate_counts(packages: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for package in packages:
        counts.update({field: int(package["actual_counts"].get(field, 0) or 0) for field in COUNT_FIELDS})
    return {field: int(counts.get(field, 0)) for field in COUNT_FIELDS}


def source_truth_counts(packages: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    return {package_source_id(package): dict(package["actual_counts"]) for package in packages}


def aggregate_quality(packages: list[dict[str, Any]]) -> dict[str, Any]:
    qualities = [
        package.get("manifest", {}).get("quality")
        for package in packages
        if isinstance(package.get("manifest", {}).get("quality"), dict)
    ]
    return {
        "all_discovered_urls_have_outcomes": all(item.get("all_discovered_urls_have_outcomes") is True for item in qualities),
        "errors": sum(int(item.get("errors", 0) or 0) for item in qualities),
        "attachment_policy": "metadata_only" if all(item.get("attachment_policy") == "metadata_only" for item in qualities) else "mixed",
        "external_link_policy": "record_only" if all(item.get("external_link_policy") == "record_only" for item in qualities) else "mixed",
        "sources": {
            package_source_id(package): package.get("manifest", {}).get("quality")
            for package in packages
        },
    }


def latest_upstream_generated_at(packages: list[dict[str, Any]]) -> str | None:
    values = [
        clean_text(package.get("manifest", {}).get("generated_at"))
        for package in packages
        if clean_text(package.get("manifest", {}).get("generated_at"))
    ]
    return max(values) if values else None


def source_entries(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for package in packages:
        source_id = package_source_id(package)
        entries.append(
            {
                "source_id": source_id,
                "source_kind": "sitegraph",
                "artifact_root": f"generated/collections/{COLLECTION_ID}/sitegraph",
                "upstream_generated_at": clean_text(package["manifest"].get("generated_at")) or None,
                "display_name": site_display_name(package["site"]),
                "truth_counts": dict(package["actual_counts"]),
                "quality": package["manifest"].get("quality"),
            }
        )
    return entries


def merge_built_packages(built_packages: list[dict[str, Any]]) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    attachment_index: list[dict[str, Any]] = []
    external_index: list[dict[str, Any]] = []
    outcomes: dict[str, list[dict[str, Any]]] = {
        "detail_page_records": [],
        "attachment_metadata_records": [],
        "direct_attachment_records": [],
        "external_link_records": [],
        "utility_link_records": [],
    }
    for built in built_packages:
        for document in built["documents"]:
            document["doc_index"] = len(documents)
            documents.append(document)
        attachment_index.extend(built["attachment_index"])
        external_index.extend(built["external_index"])
        for key in outcomes:
            outcomes[key].extend(built["outcomes"].get(key) or [])
    return {
        "documents": documents,
        "attachment_index": attachment_index,
        "external_index": external_index,
        "outcomes": outcomes,
    }


def write_public_index(packages: list[dict[str, Any]], built: dict[str, Any], *, shard_size: int) -> dict[str, Any]:
    # Removing the directories prevents stale fixed-name or obsolete indexes from being deployed.
    for directory in (PUBLIC_INDEX_DIR, OBSOLETE_INDEX_DIR):
        if directory.exists():
            shutil.rmtree(directory)
    PUBLIC_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_SHARD_DIR.mkdir(parents=True, exist_ok=True)

    documents = built["documents"]
    full_shards, _, shard_filter = build_locality_shards(documents)

    doc_meta_light_fields = {
        "doc_index",
        "id",
        "record_type",
        "facet",
        "title",
        "source_id",
        "section",
        "nav_path_text",
        "published_at",
        "version_date",
        "date_kind",
        "task_kind",
        "shard",
    }
    doc_meta_light = [
        {key: document.get(key) for key in doc_meta_light_fields if key in document}
        for document in documents
    ]
    light_inverted_index = build_light_inverted_index(documents)
    body_inverted_index = build_body_inverted_index(documents)

    section_counts = Counter(clean_text(document.get("section_id")) or "unknown" for document in documents)
    section_index = []
    for package in packages:
        source_id = package_source_id(package)
        source = site_display_name(package["site"])
        for section in package["sections"]:
            section_id = clean_text(section.get("section_id"))
            section_name, nav_path, tags = section_label(section)
            section_index.append(
                {
                    "source_id": source_id,
                    "source": source,
                    "section_id": section_id,
                    "name": section_name,
                    "url": clean_text(section.get("url")),
                    "section_type": clean_text(section.get("section_type")),
                    "nav_path": nav_path,
                    "business_tags": tags,
                    "document_count": section_counts.get(section_id, 0),
                }
            )

    query_aliases = query_alias_payload()
    artifacts: dict[str, dict[str, Any]] = {}
    doc_meta_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_ARTIFACT_DIR, "doc_meta_light", doc_meta_light, compact=True)
    light_index_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_ARTIFACT_DIR, "light_inverted_index", light_inverted_index, compact=True)
    body_index_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_ARTIFACT_DIR, "body_inverted_index", body_inverted_index, compact=True)
    section_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_ARTIFACT_DIR, "section_index", section_index, compact=True)
    attachment_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_ARTIFACT_DIR, "attachment_index", built["attachment_index"], compact=True)
    external_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_ARTIFACT_DIR, "external_index", built["external_index"], compact=True)
    aliases_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_ARTIFACT_DIR, "query_aliases", query_aliases, compact=False)
    shard_catalog_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_ARTIFACT_DIR, "shard_catalog", full_shards, compact=True)
    shard_filter_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_ARTIFACT_DIR, "shard_filter", shard_filter, compact=True)
    outcomes_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_ARTIFACT_DIR, "outcomes", built["outcomes"], compact=True)

    artifacts["doc_meta_light"] = artifact_entry(doc_meta_artifact, role="doc_meta_light", count=len(doc_meta_light), load="initial")
    artifacts["light_inverted_index"] = artifact_entry(light_index_artifact, role="light_inverted_index", load="initial")
    artifacts["query_aliases"] = artifact_entry(aliases_artifact, role="query_aliases", count=len(query_aliases), load="initial")
    artifacts["body_inverted_index"] = artifact_entry(body_index_artifact, role="body_inverted_index", load="deep_search")
    artifacts["section_index"] = artifact_entry(section_artifact, role="section_index", count=len(section_index), load="on_demand")
    artifacts["attachment_index"] = artifact_entry(attachment_artifact, role="attachment_index", count=len(built["attachment_index"]), load="on_demand")
    artifacts["external_index"] = artifact_entry(external_artifact, role="external_index", count=len(built["external_index"]), load="on_demand")
    artifacts["shard_catalog"] = artifact_entry(shard_catalog_artifact, role="shard_catalog", count=len(full_shards), load="verify")
    artifacts["shard_filter"] = artifact_entry(shard_filter_artifact, role="shard_filter", count=len(shard_filter), load="verify")
    artifacts["outcomes"] = artifact_entry(outcomes_artifact, role="outcomes", load="audit")

    upstream_counts = aggregate_counts(packages)
    per_source_truth_counts = source_truth_counts(packages)
    upstream_quality = aggregate_quality(packages)
    record_counts = Counter(document["record_type"] for document in documents)
    facet_counts = Counter(document["facet"] for document in documents)
    first_screen_artifacts = ["doc_meta_light", "light_inverted_index", "query_aliases"]
    total_full_scan_bytes = sum(int(item["bytes"]) for item in full_shards)
    max_full_shard_bytes = max((int(item["bytes"]) for item in full_shards), default=0)
    avg_full_shard_bytes = round(total_full_scan_bytes / max(1, len(full_shards)), 2)
    first_screen_bytes = sum(int(artifacts[name]["bytes"]) for name in first_screen_artifacts)
    representative_full_scan_ms = measure_representative_full_scan_ms(documents, "校历")
    size_report = {
        "generated_at": now_iso(),
        "first_screen_files": [
            {"name": name, "path": artifacts[name]["path"], "bytes": artifacts[name]["bytes"]}
            for name in first_screen_artifacts
        ],
        "first_screen_bytes": first_screen_bytes,
        "first_screen_total_bytes": first_screen_bytes,
        "body_index_bytes": artifacts["body_inverted_index"]["bytes"],
        "full_scan_total_bytes": total_full_scan_bytes,
        "shard_count": len(full_shards),
        "max_shard_bytes": max_full_shard_bytes,
        "avg_shard_bytes": avg_full_shard_bytes,
        "full_shard_count": len(full_shards),
        "max_full_shard_bytes": max_full_shard_bytes,
        "avg_full_shard_bytes": avg_full_shard_bytes,
        "max_full_shard_documents": max((int(item["count"]) for item in full_shards), default=0),
        "avg_full_shard_documents": round(sum(int(item["count"]) for item in full_shards) / max(1, len(full_shards)), 2),
        "representative_query_phase_timings": {
            "query": "校历",
            "quick_ms": 0,
            "body_ms": 0,
            "hydrate_ms": 0,
            "verify_scan_ms": representative_full_scan_ms,
        },
        "exhaustive_scan": {
            "shard_count": len(full_shards),
            "max_shard_bytes": max_full_shard_bytes,
            "avg_shard_bytes": avg_full_shard_bytes,
            "estimated_full_scan_bytes": total_full_scan_bytes,
            "representative_query": "校历",
            "representative_query_full_scan_time_ms": representative_full_scan_ms,
        },
    }
    size_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_ARTIFACT_DIR, "size_report", size_report, compact=False)
    artifacts["size_report"] = artifact_entry(size_artifact, role="size_report", load="audit")

    generated_at = now_iso()
    upstream_generated_at = latest_upstream_generated_at(packages) or generated_at
    manifest = {
        "generated_at": generated_at,
        "strategy": "progressive-verifiable-static-search",
        "producer_repo": os.environ.get("GITHUB_REPOSITORY") or "hicancan/njupt-search",
        "producer_ref": producer_ref(),
        "site_id": COLLECTION_ID,
        "collection_id": COLLECTION_ID,
        "sources": source_entries(packages),
        "artifact_path": f"generated/collections/{COLLECTION_ID}",
        "upstream_generated_at": upstream_generated_at,
        "truth_counts": upstream_counts,
        "total_documents": len(documents),
        "record_counts": dict(record_counts),
        "facet_counts": dict(facet_counts),
        "exam_vertical_preserved": True,
        "core_search": {
            "algorithm": "progressive exhaustive static search: light inverted recall, body inverted recall, candidate shard hydration, then complete full shard scan",
            "execution_model": "pure_frontend_worker",
            "light_first_screen": True,
            "first_screen_artifacts": first_screen_artifacts,
            "body_index_loading": "on_deep_search",
            "full_text_loading": "progressive_candidate_hydration_then_exhaustive_full_scan",
            "search_worker": True,
        },
        "progressive_search": {
            "total_shards": len(full_shards),
            "total_documents": len(documents),
            "full_scan_supported": True,
            "progressive_events": True,
            "artifact_roles": [
                "manifest",
                "doc_meta_light",
                "light_inverted_index",
                "query_aliases",
                "body_inverted_index",
                "shard_catalog",
                "shard_filter",
                "full_shards",
                "size_report",
                "outcomes",
            ],
        },
        "coverage_contract": {
            "coverage_fields": ["title", "section", "nav_path", "summary", "content", "attachments", "url"],
            "proof": {
                "indexed_fields": ["title", "section", "nav_path", "tags", "attachments", "external", "system", "summary", "content"],
                "full_scan_fields": ["title", "section", "nav_path", "summary", "content", "attachments", "url"],
            },
            "total_shards": len(full_shards),
            "total_documents": len(documents),
        },
        "verification_contract": {
            "shard_filter_supported": True,
            "proved_skip_supported": True,
            "scan_fallback_supported": True,
            "filter_artifact": "shard_filter",
            "catalog_artifact": "shard_catalog",
        },
        "artifacts": artifacts,
        "sitegraph": {
            "truth_counts": upstream_counts,
            "source_truth_counts": per_source_truth_counts,
            "quality": upstream_quality,
            "upstream_generated_at": upstream_generated_at,
            "detail_page_records": record_counts.get("detail", 0),
            "attachment_metadata_records": len(built["attachment_index"]),
            "direct_attachment_records": record_counts.get("attachment", 0),
            "external_link_records": len(built["external_index"]),
            "external_document_records": record_counts.get("external", 0),
            "utility_link_records": record_counts.get("utility", 0),
            "attachment_policy": "metadata_only",
            "external_link_policy": "record_only",
            "full_shards": full_shards,
            "shard_strategy": {
                "version": "locality-facet-record-year-section-hash-progressive",
                "dimensions": ["facet", "record_type", "year", "top_nav_section", "hash_bucket"],
                "hash_bucket_count": 4,
                "sequential_fixed_size_shards": False,
            },
            "indexes": artifacts,
        },
    }
    write_json(PUBLIC_INDEX_DIR / "manifest.json", manifest)
    return manifest


def build_sitegraph_indexes(index_dirs: list[Path] | tuple[Path, ...], *, shard_size: int = 1000) -> dict[str, Any]:
    packages = [validate_sitegraph_package(index_dir) for index_dir in index_dirs]
    built = merge_built_packages([build_documents(package) for package in packages])
    manifest = write_public_index(packages, built, shard_size=shard_size)
    return {
        "sitegraph_indexes": [str(index_dir) for index_dir in index_dirs],
        "source_ids": [package_source_id(package) for package in packages],
        "generated_documents": manifest["total_documents"],
        "detail_page_records": manifest["sitegraph"]["detail_page_records"],
        "attachment_metadata_records": manifest["sitegraph"]["attachment_metadata_records"],
        "direct_attachment_records": manifest["sitegraph"]["direct_attachment_records"],
        "external_link_records": manifest["sitegraph"]["external_link_records"],
        "utility_link_records": manifest["sitegraph"]["utility_link_records"],
        "truth_counts": manifest["sitegraph"]["truth_counts"],
        "full_shards": manifest["sitegraph"]["full_shards"],
        "public_index": str(PUBLIC_INDEX_DIR),
    }


def build_sitegraph_index(index_dir: Path, *, shard_size: int = 1000) -> dict[str, Any]:
    return build_sitegraph_indexes([index_dir], shard_size=shard_size)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build generated collection search artifacts for njupt-search.")
    parser.add_argument(
        "--source-package",
        dest="source_packages",
        action="append",
        type=Path,
        default=None,
        help="Path to an audited njupt-site-graph source package index. Repeat for multiple source packages.",
    )
    parser.add_argument("--collection-id", default=COLLECTION_ID)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--shard-size", type=int, default=1000, help="Number of full documents per shard")
    args = parser.parse_args()
    configure_collection_output(args.collection_id, args.out)
    source_packages = args.source_packages or load_collection_source_packages()
    summary = build_sitegraph_indexes([path.resolve() for path in source_packages], shard_size=args.shard_size)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
