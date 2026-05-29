from __future__ import annotations

import os
import shutil
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .sitegraph_artifact_io import artifact_entry, write_hashed_json, write_json
from .sitegraph_documents import section_label, site_display_name
from .sitegraph_index_postings import (
    build_body_inverted_index,
    build_light_inverted_index,
    measure_representative_full_scan_ms,
    query_alias_payload,
)
from .sitegraph_package_summary import (
    aggregate_counts,
    aggregate_quality,
    latest_upstream_generated_at,
    source_entries,
    source_truth_counts,
)
from .sitegraph_shards import build_locality_shards
from .sitegraph_source import package_source_id
from .sitegraph_text import clean_text


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


def write_public_index(packages: list[dict[str, Any]], built: dict[str, Any], *, shard_size: int) -> dict[str, Any]:
    # Preserved for CLI compatibility; locality shards no longer use fixed-size splitting.
    _ = shard_size

    # Removing the directories prevents stale fixed-name or obsolete indexes from being deployed.
    for directory in (PUBLIC_INDEX_DIR, OBSOLETE_INDEX_DIR):
        if directory.exists():
            shutil.rmtree(directory)
    PUBLIC_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_SHARD_DIR.mkdir(parents=True, exist_ok=True)

    documents = built["documents"]
    full_shards, _, shard_filter = build_locality_shards(
        documents,
        public_root=PUBLIC_ROOT,
        shard_dir=PUBLIC_SHARD_DIR,
    )

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
        "sources": source_entries(packages, collection_id=COLLECTION_ID),
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
