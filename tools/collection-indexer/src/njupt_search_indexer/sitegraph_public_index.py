from __future__ import annotations

import os
import shutil
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .sitegraph_artifact_io import artifact_entry, json_bytes, write_hashed_bytes, write_hashed_json, write_json
from .sitegraph_binary_index import pack_impact_index
from .sitegraph_documents import section_label, site_display_name
from .sitegraph_index_postings import (
    QUERY_SYNONYMS,
    build_body_inverted_index,
    build_light_inverted_index,
    measure_representative_full_scan_ms,
    query_alias_payload,
)
from .sitegraph_package_summary import (
    aggregate_counts,
    aggregate_quality,
    latest_upstream_generated_at,
    source_truth_counts,
)
from .sitegraph_shards import build_locality_shards, shard_year
from .sitegraph_source import package_source_id
from .sitegraph_text import clean_text, normalize_text, sitegraph_tokens, stable_slug


BASE_DIR = Path(__file__).resolve().parents[4]
PUBLIC_ROOT = BASE_DIR / "apps" / "web" / "public"
COLLECTION_ID = "njupt-public"
PUBLIC_INDEX_DIR = PUBLIC_ROOT / "generated" / "collections" / COLLECTION_ID
PUBLIC_SITEGRAPH_DIR = PUBLIC_INDEX_DIR / "sitegraph"
PUBLIC_ARTIFACT_DIR = PUBLIC_SITEGRAPH_DIR / "artifacts"
PUBLIC_SOURCE_MANIFEST_DIR = PUBLIC_SITEGRAPH_DIR / "source_manifests"
PUBLIC_LOCAL_LIGHT_META_DIR = PUBLIC_SITEGRAPH_DIR / "local_impact_light_meta_indexes"
PUBLIC_LOCAL_LIGHT_PACKED_DIR = PUBLIC_SITEGRAPH_DIR / "local_impact_light_packed_indexes"
PUBLIC_LOCAL_BODY_DIR = PUBLIC_SITEGRAPH_DIR / "local_impact_body_indexes"
PUBLIC_LOCAL_BODY_PACKED_DIR = PUBLIC_SITEGRAPH_DIR / "local_impact_body_packed_indexes"
PUBLIC_PROOF_CATALOG_DIR = PUBLIC_SITEGRAPH_DIR / "proof_catalogs"
PUBLIC_SHARD_FILTER_DIR = PUBLIC_SITEGRAPH_DIR / "shard_filters"
PUBLIC_FULL_SHARD_DIR = PUBLIC_SITEGRAPH_DIR / "full_shards"
PUBLIC_ATTACHMENT_META_DIR = PUBLIC_SITEGRAPH_DIR / "attachment_meta_indexes"
PUBLIC_ATTACHMENT_FILENAME_DIR = PUBLIC_SITEGRAPH_DIR / "attachment_filename_indexes"
PUBLIC_ATTACHMENT_TEXT_DIR = PUBLIC_SITEGRAPH_DIR / "attachment_text_shards"
PUBLIC_SECTION_DIR = PUBLIC_SITEGRAPH_DIR / "section_indexes"
PUBLIC_EXTERNAL_DIR = PUBLIC_SITEGRAPH_DIR / "external_indexes"
PUBLIC_SHARD_DIR = PUBLIC_FULL_SHARD_DIR
OBSOLETE_INDEX_DIR = PUBLIC_ROOT / "index"

LOCAL_DOC_META_FIELDS = {
    "doc_index",
    "id",
    "record_type",
    "facet",
    "title",
    "url",
    "canonical_title",
    "source_id",
    "source",
    "source_domain",
    "section_id",
    "section",
    "nav_path",
    "nav_path_text",
    "published_at",
    "updated_at",
    "recorded_at",
    "version_date",
    "date_kind",
    "date_confidence",
    "academic_year",
    "term",
    "task_kind",
    "authority_profile",
    "dedupe_key",
    "attachment_count",
    "collection_method",
    "shard",
}

SOURCE_AUTHORITY: dict[str, dict[str, Any]] = {
    "jwc": {
        "owner_unit": "本科生院 / 教务处",
        "authority_domains": ["academic", "exam", "course", "calendar", "forms"],
        "priority_by_intent": {
            "exam_schedule": "high",
            "academic_calendar": "high",
            "academic_policy": "high",
            "course_grade_credit": "high",
            "form_download": "high",
            "system_entry": "high",
        },
        "freshness_policy": "current_term_or_latest_notice",
    },
    "xsc": {
        "owner_unit": "学生工作处",
        "authority_domains": ["student_affairs", "scholarship_aid", "counselor", "forms"],
        "priority_by_intent": {
            "scholarship_aid": "high",
            "student_affairs": "high",
            "form_download": "medium",
        },
        "freshness_policy": "latest_notice_with_policy_backstop",
    },
    "cxcy": {
        "owner_unit": "创新创业教育学院",
        "authority_domains": ["innovation_entrepreneurship", "competition", "dual_creation"],
        "priority_by_intent": {
            "innovation_entrepreneurship": "high",
            "form_download": "medium",
            "system_entry": "high",
        },
        "freshness_policy": "latest_notice_with_project_history",
    },
}

ATTACHMENT_EVIDENCE_LEVELS = ("metadata_only", "filename_only", "text_extracted", "snippet", "full_content")


def attachment_evidence_coverage(attachments: list[dict[str, Any]]) -> dict[str, int]:
    coverage = {level: 0 for level in ATTACHMENT_EVIDENCE_LEVELS}
    for attachment in attachments:
        available = attachment.get("available_evidence")
        if isinstance(available, list) and available:
            for level in available:
                if level in coverage:
                    coverage[level] += 1
        else:
            if attachment.get("metadata_only") is True:
                coverage["metadata_only"] += 1
            level = str(attachment.get("evidence_level") or "metadata_only")
            coverage[level if level in coverage else "metadata_only"] += 1
    return {"total": len(attachments), **coverage}


def configure_collection_output(collection_id: str = COLLECTION_ID, output_dir: Path | None = None) -> None:
    global COLLECTION_ID, PUBLIC_INDEX_DIR, PUBLIC_SITEGRAPH_DIR, PUBLIC_ARTIFACT_DIR
    global PUBLIC_SOURCE_MANIFEST_DIR, PUBLIC_LOCAL_LIGHT_META_DIR, PUBLIC_LOCAL_LIGHT_PACKED_DIR
    global PUBLIC_LOCAL_BODY_DIR, PUBLIC_LOCAL_BODY_PACKED_DIR
    global PUBLIC_PROOF_CATALOG_DIR, PUBLIC_SHARD_FILTER_DIR, PUBLIC_FULL_SHARD_DIR, PUBLIC_SHARD_DIR
    global PUBLIC_ATTACHMENT_META_DIR, PUBLIC_ATTACHMENT_FILENAME_DIR, PUBLIC_ATTACHMENT_TEXT_DIR
    global PUBLIC_SECTION_DIR, PUBLIC_EXTERNAL_DIR

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
    PUBLIC_SOURCE_MANIFEST_DIR = PUBLIC_SITEGRAPH_DIR / "source_manifests"
    PUBLIC_LOCAL_LIGHT_META_DIR = PUBLIC_SITEGRAPH_DIR / "local_impact_light_meta_indexes"
    PUBLIC_LOCAL_LIGHT_PACKED_DIR = PUBLIC_SITEGRAPH_DIR / "local_impact_light_packed_indexes"
    PUBLIC_LOCAL_BODY_DIR = PUBLIC_SITEGRAPH_DIR / "local_impact_body_indexes"
    PUBLIC_LOCAL_BODY_PACKED_DIR = PUBLIC_SITEGRAPH_DIR / "local_impact_body_packed_indexes"
    PUBLIC_PROOF_CATALOG_DIR = PUBLIC_SITEGRAPH_DIR / "proof_catalogs"
    PUBLIC_SHARD_FILTER_DIR = PUBLIC_SITEGRAPH_DIR / "shard_filters"
    PUBLIC_FULL_SHARD_DIR = PUBLIC_SITEGRAPH_DIR / "full_shards"
    PUBLIC_SHARD_DIR = PUBLIC_FULL_SHARD_DIR
    PUBLIC_ATTACHMENT_META_DIR = PUBLIC_SITEGRAPH_DIR / "attachment_meta_indexes"
    PUBLIC_ATTACHMENT_FILENAME_DIR = PUBLIC_SITEGRAPH_DIR / "attachment_filename_indexes"
    PUBLIC_ATTACHMENT_TEXT_DIR = PUBLIC_SITEGRAPH_DIR / "attachment_text_shards"
    PUBLIC_SECTION_DIR = PUBLIC_SITEGRAPH_DIR / "section_indexes"
    PUBLIC_EXTERNAL_DIR = PUBLIC_SITEGRAPH_DIR / "external_indexes"


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


def source_id_for_document(document: dict[str, Any]) -> str:
    return clean_text(document.get("source_id")) or "unknown"


def index_scope_for_document(document: dict[str, Any]) -> tuple[str, str, str]:
    return (
        source_id_for_document(document),
        clean_text(document.get("facet")) or "unknown",
        shard_year(document),
    )


def index_id_for_scope(source_id: str, facet: str, year: str) -> str:
    return "__".join(
        [
            stable_slug(source_id, fallback="source"),
            stable_slug(facet, fallback="facet"),
            stable_slug(year, fallback="year"),
        ]
    )


def local_doc_meta(document: dict[str, Any], shard_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    payload = {key: document.get(key) for key in LOCAL_DOC_META_FIELDS if key in document}
    shard = payload.get("shard") if isinstance(payload.get("shard"), dict) else {}
    shard_id = str(shard.get("shard_id") or "")
    if shard_id and shard_id in shard_by_id:
        payload["shard"] = {
            "shard_id": shard_id,
            "path": shard_by_id[shard_id]["path"],
        }
    return payload


def local_shard_refs(shard_ids: list[str], shard_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for shard_id in shard_ids:
        shard = shard_by_id.get(shard_id)
        if not shard:
            continue
        refs.append(
            {
                "shard_id": shard_id,
                "path": shard["path"],
                "bytes": shard["bytes"],
                "count": shard["count"],
            }
        )
    return refs


def source_counts(documents: list[dict[str, Any]], source_id: str, field: str) -> dict[str, int]:
    counts = Counter(str(document.get(field) or "unknown") for document in documents if source_id_for_document(document) == source_id)
    return dict(sorted(counts.items()))


def source_domain(package: dict[str, Any]) -> str:
    return clean_text(package.get("site", {}).get("domain")) or clean_text(package.get("site", {}).get("base_url"))


def build_section_index(packages: list[dict[str, Any]], documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    section_counts = Counter(clean_text(document.get("section_id")) or "unknown" for document in documents)
    section_index: list[dict[str, Any]] = []
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
    return section_index


def attachment_filename_index(attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "attachment_id": item.get("attachment_id"),
            "source_id": item.get("source_id"),
            "name": item.get("name"),
            "extension": item.get("extension"),
            "parent_doc_id": item.get("parent_doc_id"),
            "parent_url": item.get("parent_url"),
            "url": item.get("url"),
            "section": item.get("section"),
            "nav_path": item.get("nav_path") or [],
            "metadata_only": item.get("metadata_only") is True,
            "evidence_level": item.get("evidence_level") or "filename_only",
            "text_extracted": item.get("text_extracted") is True,
            "snippet_available": item.get("snippet_available") is True,
            "full_content_available": item.get("full_content_available") is True,
        }
        for item in attachments
    ]


def route_blob(document: dict[str, Any]) -> str:
    attachment_text = " ".join(
        " ".join(clean_text(attachment.get(field)) for field in ("name", "extension", "section", "parent_url"))
        for attachment in document.get("attachments") or []
    )
    return normalize_text(
        " ".join(
            [
                clean_text(document.get("title")),
                clean_text(document.get("canonical_title")),
                clean_text(document.get("section")),
                clean_text(document.get("nav_path_text")),
                " ".join(clean_text(item) for item in document.get("nav_path") or []),
                clean_text(document.get("summary")),
                clean_text(document.get("content")),
                clean_text(document.get("url")),
                clean_text(document.get("facet")),
                clean_text(document.get("task_kind")),
                clean_text(document.get("source_id")),
                attachment_text,
            ]
        )
    )


def route_summary(
    docs: list[dict[str, Any]],
    *,
    term: str | None = None,
    local_index_costs: dict[str, int] | None = None,
    max_local_indexes: int = 24,
    max_shards: int = 12,
) -> dict[str, Any]:
    sources = Counter(source_id_for_document(document) for document in docs)
    facets = Counter(str(document.get("facet") or "unknown") for document in docs)
    years = Counter(shard_year(document) for document in docs)
    task_kinds = Counter(str(document.get("task_kind") or "broad_exploratory") for document in docs)
    result_types = Counter(str(document.get("record_type") or "detail") for document in docs)
    local_indexes = Counter(index_id_for_scope(*index_scope_for_document(document)) for document in docs)
    shard_ids = Counter(str((document.get("shard") or {}).get("shard_id") or "") for document in docs)
    selected_local_indexes = [key for key, _ in local_indexes.most_common(max_local_indexes)]
    expected_cost_bytes = sum((local_index_costs or {}).get(index_id, 0) for index_id in selected_local_indexes)
    expected_utility = round(
        (len(docs) + sum(sources.values()) * 0.4 + sum(facets.values()) * 0.2)
        / max(1, expected_cost_bytes / 1024),
        6,
    )
    summary = {
        "term": term,
        "likely_sources": [key for key, _ in sources.most_common()],
        "likely_facets": [key for key, _ in facets.most_common()],
        "likely_years": [key for key, _ in years.most_common()],
        "likely_task_kinds": [key for key, _ in task_kinds.most_common(8)],
        "expected_result_types": [key for key, _ in result_types.most_common()],
        "local_index_ids": selected_local_indexes,
        "sample_shard_ids": [key for key, _ in shard_ids.most_common(max_shards) if key],
        "candidate_shard_group_count": len(shard_ids),
        "authority_priors": {
            source_id: round(count / max(1, len(docs)), 4)
            for source_id, count in sources.most_common()
        },
        "freshness_policy": "prefer_recent_for_current_notice_intents",
        "matched_document_count": len(docs),
        "expected_cost_bytes": expected_cost_bytes,
        "expected_utility_per_kb": expected_utility,
        "planner_features": {
            "source_entropy": len(sources),
            "facet_entropy": len(facets),
            "year_entropy": len(years),
            "local_index_count": len(selected_local_indexes),
        },
    }
    return summary


def build_global_query_directory(
    documents: list[dict[str, Any]],
    query_aliases: dict[str, Any],
    local_index_costs: dict[str, int],
) -> dict[str, Any]:
    normalized_blobs = [(document, route_blob(document)) for document in documents]
    known_terms: set[str] = set()
    for key, payload in query_aliases.items():
        known_terms.add(str(key))
        if isinstance(payload, dict):
            known_terms.update(str(item) for item in payload.get("aliases") or [])
    for document in documents:
        known_terms.update(str(document.get(field) or "") for field in ("facet", "task_kind", "source_id"))

    entries: dict[str, Any] = {}
    for raw_term in sorted(known_terms):
        normalized = normalize_text(raw_term)
        if len(normalized) < 2:
            continue
        matched_docs = [document for document, blob in normalized_blobs if normalized in blob]
        if not matched_docs:
            continue
        entries[normalized] = route_summary(matched_docs, term=normalized, local_index_costs=local_index_costs)

    intents: dict[str, Any] = {}
    for intent in sorted({str(document.get("task_kind") or "broad_exploratory") for document in documents}):
        intent_docs = [document for document in documents if str(document.get("task_kind") or "broad_exploratory") == intent]
        intents[intent] = route_summary(intent_docs, term=intent, local_index_costs=local_index_costs, max_local_indexes=36, max_shards=16)

    return {
        "version": "sitegraph-global-query-directory-cost-v2",
        "description": "Routing evidence only. This directory maps query evidence to sources, facets, years, local indexes, and shard groups; it never stores corpus-wide document postings.",
        "tokenizer": "nfkc-lower-cjk-ngram-code",
        "planner": "cost_authority_proof_ledger_v2",
        "entry_count": len(entries),
        "entries": entries,
        "intents": intents,
        "fallback": {
            "mode": "cost_sort_authority_manifests_then_proof_ledger_verify",
            "false_negative_policy": "directory misses route broadly and cannot justify exhaustive completion without shard scan or safe filter proof",
        },
    }


def build_local_indexes(
    documents: list[dict[str, Any]],
    shard_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for document in documents:
        groups[index_scope_for_document(document)].append(document)

    local_refs: list[dict[str, Any]] = []
    refs_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (source_id, facet, year), group_docs in sorted(groups.items()):
        index_id = index_id_for_scope(source_id, facet, year)
        sorted_docs = sorted(group_docs, key=lambda item: int(item["doc_index"]))
        shard_ids = sorted({str((document.get("shard") or {}).get("shard_id") or "") for document in sorted_docs if (document.get("shard") or {}).get("shard_id")})
        scope = {
            "index_id": index_id,
            "source_id": source_id,
            "facet": facet,
            "year": year,
            "shard_ids": shard_ids,
        }
        light_payload = {
            **build_light_inverted_index(sorted_docs),
            "version": "sitegraph-local-light-impact-v2",
            "scope": scope,
            "documents": [local_doc_meta(document, shard_by_id) for document in sorted_docs],
        }
        body_payload = {
            **build_body_inverted_index(sorted_docs),
            "version": "sitegraph-local-body-impact-v2",
            "scope": scope,
        }
        light_meta_payload = {key: value for key, value in light_payload.items() if key != "terms"}
        light_terms_payload = {key: value for key, value in light_payload.items() if key != "documents"}
        light_meta_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_LOCAL_LIGHT_META_DIR, f"local_impact_light_meta.{index_id}", light_meta_payload, compact=True)
        light_packed_artifact = write_hashed_bytes(
            PUBLIC_ROOT,
            PUBLIC_LOCAL_LIGHT_PACKED_DIR,
            f"local_impact_light.{index_id}",
            pack_impact_index(light_terms_payload),
            extension="bin",
        )
        body_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_LOCAL_BODY_DIR, f"local_impact_body.{index_id}", body_payload, compact=True)
        body_packed_artifact = write_hashed_bytes(
            PUBLIC_ROOT,
            PUBLIC_LOCAL_BODY_PACKED_DIR,
            f"local_impact_body.{index_id}",
            pack_impact_index(body_payload),
            extension="bin",
        )
        ref = {
            "index_id": index_id,
            "scope": scope,
            "doc_count": len(sorted_docs),
            "shards": local_shard_refs(shard_ids, shard_by_id),
            "light_index_meta": artifact_entry(light_meta_artifact, role="local_impact_light_index_meta", count=len(sorted_docs), load="query_planned"),
            "light_index_packed": artifact_entry(light_packed_artifact, role="local_impact_light_index_packed", load="query_planned"),
            "body_index": artifact_entry(body_artifact, role="local_impact_body_index", load="query_deepening"),
            "body_index_packed": artifact_entry(body_packed_artifact, role="local_impact_body_index_packed", load="query_deepening"),
        }
        local_refs.append(ref)
        refs_by_source[source_id].append(ref)
    return local_refs, refs_by_source


def build_source_manifests(
    packages: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    built: dict[str, Any],
    full_shards: list[dict[str, Any]],
    shard_filter: dict[str, dict[str, Any]],
    local_refs_by_source: dict[str, list[dict[str, Any]]],
    section_index: list[dict[str, Any]],
    external_index: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    source_manifest_artifacts: dict[str, dict[str, Any]] = {}
    source_manifest_payloads: dict[str, dict[str, Any]] = {}
    attachments_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in built["attachment_index"]:
        attachments_by_source[str(item.get("source_id") or "unknown")].append(item)
    sections_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in section_index:
        sections_by_source[str(item.get("source_id") or "unknown")].append(item)
    external_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in external_index:
        source_id = str(item.get("document_id") or "").split("-", 1)[0] or "unknown"
        external_by_source[source_id].append(item)

    for package in packages:
        source_id = package_source_id(package)
        source_docs = [document for document in documents if source_id_for_document(document) == source_id]
        source_shards = [shard for shard in full_shards if shard.get("source_id") == source_id]
        source_shard_ids = {str(shard["shard_id"]) for shard in source_shards}
        source_filter = {
            shard_id: payload
            for shard_id, payload in shard_filter.items()
            if shard_id in source_shard_ids
        }
        attachment_meta = attachments_by_source.get(source_id, [])
        attachment_coverage = attachment_evidence_coverage(attachment_meta)
        proof_catalog = {
            "version": "sitegraph-proof-ledger-catalog-v2",
            "source_id": source_id,
            "state_model": [
                "pending",
                "scanned",
                "proved_no_match",
                "excluded_by_filter",
                "excluded_by_declared_scope",
                "failed",
            ],
            "complete_requires_no_states": ["pending", "failed"],
            "covered_fields": ["title", "section", "nav_path", "summary", "content", "attachments", "url"],
            "shards": [
                {
                    "shard_id": shard["shard_id"],
                    "source_id": shard["source_id"],
                    "path": shard["path"],
                    "sha256": shard["sha256"],
                    "bytes": shard["bytes"],
                    "document_count": shard["count"],
                    "scope": {
                        "facets": shard["facet_range"],
                        "record_types": shard["record_type_range"],
                        "sections": shard["section_range"],
                        "years": shard["year_range"],
                        "hash_bucket": shard["hash_bucket"],
                    },
                    "filter_contract": {
                        "artifact_family": "shard_filters",
                        "hash_algorithm": "bloom-fnv1a32-utf8",
                        "false_negative": False,
                        "filter_sha256": shard["filter_sha256"],
                        "filter_token_count": shard["filter_token_count"],
                    },
                }
                for shard in source_shards
            ],
        }
        proof_catalog_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_PROOF_CATALOG_DIR, f"proof_catalog.{source_id}", proof_catalog, compact=True)
        shard_filter_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_SHARD_FILTER_DIR, f"shard_filter.{source_id}", source_filter, compact=True)
        attachment_meta_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_ATTACHMENT_META_DIR, f"attachment_meta.{source_id}", attachment_meta, compact=True)
        attachment_filename_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_ATTACHMENT_FILENAME_DIR, f"attachment_filename.{source_id}", attachment_filename_index(attachment_meta), compact=True)
        attachment_text_artifact = write_hashed_json(
            PUBLIC_ROOT,
            PUBLIC_ATTACHMENT_TEXT_DIR,
            f"attachment_text_manifest.{source_id}",
            {"version": "attachment-text-shards-v1", "source_id": source_id, "shards": [], "ocr_default": False},
            compact=True,
        )
        section_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_SECTION_DIR, f"section_index.{source_id}", sections_by_source.get(source_id, []), compact=True)
        external_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_EXTERNAL_DIR, f"external_index.{source_id}", external_by_source.get(source_id, []), compact=True)
        payload = {
            "version": "sitegraph-source-manifest-proof-ledger-v3",
            "source_id": source_id,
            "display_name": site_display_name(package["site"]),
            "domain": source_domain(package),
            "doc_count": len(source_docs),
            "attachment_count": len(attachment_meta),
            "attachment_evidence_coverage": attachment_coverage,
            "facet_counts": source_counts(documents, source_id, "facet"),
            "record_counts": source_counts(documents, source_id, "record_type"),
            "year_counts": Counter(shard_year(document) for document in source_docs),
            "local_indexes": local_refs_by_source.get(source_id, []),
            "artifacts": {
                "proof_catalog": artifact_entry(proof_catalog_artifact, role="proof_catalog", count=len(source_shards), load="verify"),
                "shard_filter": artifact_entry(shard_filter_artifact, role="shard_filter", count=len(source_filter), load="verify"),
                "attachment_meta_index": artifact_entry(attachment_meta_artifact, role="attachment_meta_index", count=len(attachment_meta), load="on_demand"),
                "attachment_filename_index": artifact_entry(attachment_filename_artifact, role="attachment_filename_index", count=len(attachment_meta), load="query_planned"),
                "attachment_text_shards": artifact_entry(attachment_text_artifact, role="attachment_text_shards", count=0, load="future_lazy"),
                "section_index": artifact_entry(section_artifact, role="section_index", count=len(sections_by_source.get(source_id, [])), load="on_demand"),
                "external_index": artifact_entry(external_artifact, role="external_index", count=len(external_by_source.get(source_id, [])), load="on_demand"),
            },
        }
        payload["year_counts"] = dict(sorted(payload["year_counts"].items()))
        artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_SOURCE_MANIFEST_DIR, f"source_manifest.{source_id}", payload, compact=False)
        source_manifest_artifacts[source_id] = artifact_entry(artifact, role="source_manifest", count=len(source_docs), load="query_planned")
        source_manifest_payloads[source_id] = payload
    return source_manifest_artifacts, source_manifest_payloads


def build_source_registry(
    packages: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    built: dict[str, Any],
    source_manifest_artifacts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    facet_counts = Counter(str(document.get("facet") or "unknown") for document in documents)
    sources = []
    for package in packages:
        source_id = package_source_id(package)
        authority = SOURCE_AUTHORITY.get(source_id, {})
        source_docs = [document for document in documents if source_id_for_document(document) == source_id]
        source_attachments = [item for item in built["attachment_index"] if str(item.get("source_id") or "") == source_id]
        attachment_coverage = attachment_evidence_coverage(source_attachments)
        quality = package.get("manifest", {}).get("quality") if isinstance(package.get("manifest"), dict) else {}
        sources.append(
            {
                "source_id": source_id,
                "display_name": site_display_name(package["site"]),
                "owner_unit": authority.get("owner_unit") or site_display_name(package["site"]),
                "domain": source_domain(package),
                "source_kind": "sitegraph",
                "authority_domains": authority.get("authority_domains") or [],
                "priority_by_intent": authority.get("priority_by_intent") or {},
                "freshness_policy": authority.get("freshness_policy") or "balanced",
                "artifact_manifest": source_manifest_artifacts[source_id],
                "doc_count": len(source_docs),
                "attachment_count": len(source_attachments),
                "attachment_evidence_coverage": attachment_coverage,
                "updated_at": clean_text(package.get("manifest", {}).get("generated_at")) or None,
                "quality_status": "ok" if isinstance(quality, dict) and quality.get("errors", 0) == 0 else "degraded",
                "coverage_status": "audited" if isinstance(quality, dict) and quality.get("all_discovered_urls_have_outcomes") is True else "partial",
                "facet_counts": source_counts(documents, source_id, "facet"),
                "record_counts": source_counts(documents, source_id, "record_type"),
                "truth_counts": dict(package["actual_counts"]),
            }
        )
    return {
        "version": "sitegraph-source-registry-routed-v1",
        "collection_id": COLLECTION_ID,
        "sources": sources,
        "filter_options": {
            "sources": [
                {"id": item["source_id"], "label": item["display_name"], "count": item["doc_count"]}
                for item in sources
            ],
            "facets": [
                {"id": facet, "label": facet, "count": count}
                for facet, count in sorted(facet_counts.items())
            ],
        },
    }


def public_artifact_dirs() -> tuple[Path, ...]:
    return (
        PUBLIC_ARTIFACT_DIR,
        PUBLIC_SOURCE_MANIFEST_DIR,
        PUBLIC_LOCAL_LIGHT_META_DIR,
        PUBLIC_LOCAL_LIGHT_PACKED_DIR,
        PUBLIC_LOCAL_BODY_DIR,
        PUBLIC_LOCAL_BODY_PACKED_DIR,
        PUBLIC_PROOF_CATALOG_DIR,
        PUBLIC_SHARD_FILTER_DIR,
        PUBLIC_FULL_SHARD_DIR,
        PUBLIC_ATTACHMENT_META_DIR,
        PUBLIC_ATTACHMENT_FILENAME_DIR,
        PUBLIC_ATTACHMENT_TEXT_DIR,
        PUBLIC_SECTION_DIR,
        PUBLIC_EXTERNAL_DIR,
    )


def local_light_runtime_bytes(ref: dict[str, Any]) -> int:
    meta = ref.get("light_index_meta") if isinstance(ref.get("light_index_meta"), dict) else None
    packed = ref.get("light_index_packed") if isinstance(ref.get("light_index_packed"), dict) else None
    if meta is not None and packed is not None:
        return int(meta.get("bytes") or 0) + int(packed.get("bytes") or 0)
    fallback = ref.get("light_index") if isinstance(ref.get("light_index"), dict) else None
    if fallback is not None:
        return int(fallback.get("bytes") or 0)
    raise ValueError(f"local index missing light artifacts: {ref.get('index_id')}")


def local_body_runtime_bytes(ref: dict[str, Any]) -> int:
    packed = ref.get("body_index_packed") if isinstance(ref.get("body_index_packed"), dict) else None
    if packed is not None:
        return int(packed.get("bytes") or 0)
    return int(ref["body_index"]["bytes"])


def write_public_index(packages: list[dict[str, Any]], built: dict[str, Any], *, shard_size: int) -> dict[str, Any]:
    # Preserved for CLI compatibility; routed locality shards no longer use fixed-size splitting.
    _ = shard_size

    for directory in (PUBLIC_INDEX_DIR, OBSOLETE_INDEX_DIR):
        if directory.exists():
            shutil.rmtree(directory)
    for directory in public_artifact_dirs():
        directory.mkdir(parents=True, exist_ok=True)

    documents = built["documents"]
    full_shards, shard_by_id, shard_filter = build_locality_shards(
        documents,
        public_root=PUBLIC_ROOT,
        shard_dir=PUBLIC_FULL_SHARD_DIR,
    )
    local_refs, local_refs_by_source = build_local_indexes(documents, shard_by_id)
    section_index = build_section_index(packages, documents)
    query_aliases = query_alias_payload()
    source_manifest_artifacts, source_manifest_payloads = build_source_manifests(
        packages,
        documents,
        built,
        full_shards,
        shard_filter,
        local_refs_by_source,
        section_index,
        built["external_index"],
    )
    source_registry = build_source_registry(packages, documents, built, source_manifest_artifacts)
    local_index_costs = {
        ref["index_id"]: local_light_runtime_bytes(ref) + local_body_runtime_bytes(ref)
        for ref in local_refs
    }
    global_query_directory = build_global_query_directory(documents, query_aliases, local_index_costs)

    artifacts: dict[str, dict[str, Any]] = {}
    source_registry_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_ARTIFACT_DIR, "source_registry", source_registry, compact=True)
    query_directory_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_ARTIFACT_DIR, "global_query_directory", global_query_directory, compact=True)
    aliases_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_ARTIFACT_DIR, "query_aliases", query_aliases, compact=False)
    outcomes_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_ARTIFACT_DIR, "outcomes", built["outcomes"], compact=True)

    upstream_counts = aggregate_counts(packages)
    per_source_truth_counts = source_truth_counts(packages)
    upstream_quality = aggregate_quality(packages)
    record_counts = Counter(document["record_type"] for document in documents)
    facet_counts = Counter(document["facet"] for document in documents)
    total_full_scan_bytes = sum(int(item["bytes"]) for item in full_shards)
    max_full_shard_bytes = max((int(item["bytes"]) for item in full_shards), default=0)
    avg_full_shard_bytes = round(total_full_scan_bytes / max(1, len(full_shards)), 2)
    representative_full_scan_ms = measure_representative_full_scan_ms(documents, "校历")

    quality_report = {
        "generated_at": now_iso(),
        "truth_counts": upstream_counts,
        "source_truth_counts": per_source_truth_counts,
        "quality": upstream_quality,
        "all_discovered_urls_have_outcomes": upstream_quality.get("all_discovered_urls_have_outcomes") is True,
        "attachment_policy": upstream_quality.get("attachment_policy"),
        "external_link_policy": upstream_quality.get("external_link_policy"),
    }
    quality_report_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_ARTIFACT_DIR, "quality_report", quality_report, compact=False)
    query_eval_report = {
        "generated_at": now_iso(),
        "representative_queries": sorted(QUERY_SYNONYMS),
        "metrics": {
            "local_index_bytes_per_query": "reported_by_search_eval",
            "hydrated_shard_bytes_per_query": "reported_by_search_eval",
            "coverage_truthfulness": "verified_by_smoke_and_task_queries",
        },
    }
    query_eval_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_ARTIFACT_DIR, "query_eval_report", query_eval_report, compact=False)

    artifacts["source_registry"] = artifact_entry(source_registry_artifact, role="source_registry", count=len(source_registry["sources"]), load="bootstrap")
    artifacts["global_query_directory"] = artifact_entry(query_directory_artifact, role="global_query_directory", count=global_query_directory["entry_count"], load="bootstrap")
    artifacts["query_aliases"] = artifact_entry(aliases_artifact, role="query_aliases", count=len(query_aliases), load="bootstrap")
    artifacts["outcomes"] = artifact_entry(outcomes_artifact, role="outcomes", load="audit")
    artifacts["quality_report"] = artifact_entry(quality_report_artifact, role="quality_report", load="audit")
    artifacts["query_eval_report"] = artifact_entry(query_eval_artifact, role="query_eval_report", load="audit")

    generated_at = now_iso()
    upstream_generated_at = latest_upstream_generated_at(packages) or generated_at
    first_screen_artifacts = ["source_registry", "global_query_directory", "query_aliases"]
    global_attachment_coverage = attachment_evidence_coverage(built["attachment_index"])

    def make_manifest() -> dict[str, Any]:
        return {
            "generated_at": generated_at,
            "strategy": "routed-verifiable-static-search",
            "producer_repo": os.environ.get("GITHUB_REPOSITORY") or "hicancan/njupt-search",
            "producer_ref": producer_ref(),
            "site_id": COLLECTION_ID,
            "collection_id": COLLECTION_ID,
            "artifact_path": f"generated/collections/{COLLECTION_ID}",
            "upstream_generated_at": upstream_generated_at,
            "truth_counts": upstream_counts,
            "total_documents": len(documents),
            "record_counts": dict(record_counts),
            "facet_counts": dict(facet_counts),
            "exam_vertical_preserved": True,
            "core_search": {
                "algorithm": "cost-authority planned impact-block retrieval with lazy evidence hydration and per-shard proof ledger completion",
                "execution_model": "pure_frontend_worker",
                "readiness": "routed_bootstrap",
                "legacy_global_first_screen": False,
                "first_screen_artifacts": first_screen_artifacts,
                "local_index_loading": "query_planned_on_demand",
                "body_index_loading": "query_planned_on_demand",
                "full_text_loading": "lazy_candidate_hydration_then_verified_scope_scan",
                "search_worker": True,
            },
            "progressive_search": {
                "total_shards": len(full_shards),
                "total_documents": len(documents),
                "full_scan_supported": True,
                "progressive_events": True,
                "artifact_roles": [
                    "bootstrap_manifest",
                    "source_registry",
                    "global_query_directory",
                    "query_aliases",
                    "source_manifest",
                    "local_impact_light_index_meta",
                    "local_impact_light_index_packed",
                    "local_impact_body_index",
                    "local_impact_body_index_packed",
                    "proof_catalog",
                    "shard_filter",
                    "full_shards",
                    "attachment_meta_index",
                    "attachment_filename_index",
                    "attachment_text_shards",
                    "quality_report",
                    "size_report",
                    "query_eval_report",
                    "outcomes",
                ],
            },
            "coverage_contract": {
                "states": [
                    "first_trusted_results",
                    "top_results_hydrated",
                    "partial_verified",
                    "scoped_exhaustive_complete",
                    "global_exhaustive_complete",
                    "cancelled",
                    "error",
                ],
                "coverage_fields": ["title", "section", "nav_path", "summary", "content", "attachments", "url"],
                "attachment_evidence_levels": list(ATTACHMENT_EVIDENCE_LEVELS),
                "proof": {
                    "indexed_fields": ["title", "section", "nav_path", "tags", "attachments", "external", "system", "summary", "content"],
                    "full_scan_fields": ["title", "section", "nav_path", "summary", "content", "attachments", "url"],
                    "complete_requires": ["scanned_shard", "explicit_filter_exclusion", "metadata_scope_exclusion", "no_false_negative_filter_exclusion"],
                    "ledger_states": ["pending", "scanned", "proved_no_match", "excluded_by_filter", "excluded_by_declared_scope", "failed"],
                },
                "total_shards": len(full_shards),
                "total_documents": len(documents),
            },
            "verification_contract": {
                "shard_filter_supported": True,
                "proved_skip_supported": True,
                "scan_fallback_supported": True,
                "filter_artifact_family": "shard_filters",
                "proof_catalog_artifact_family": "proof_catalogs",
                "completion_requires_ledger": True,
            },
            "routing_contract": {
                "planner": "cost_authority_proof_ledger_planner_v2",
                "directory_contains_doc_postings": False,
                "startup_loads_local_indexes": False,
                "startup_loads_full_shards": False,
                "startup_loads_global_document_metadata": False,
            },
            "artifacts": artifacts,
            "sitegraph": {
                "truth_counts": upstream_counts,
                "source_truth_counts": per_source_truth_counts,
                "quality": upstream_quality,
                "upstream_generated_at": upstream_generated_at,
                "detail_page_records": record_counts.get("detail", 0),
                "attachment_metadata_records": len(built["attachment_index"]),
                "attachment_evidence_policy": "metadata_and_filename_only_no_extracted_attachment_content",
                "attachment_evidence_coverage": global_attachment_coverage,
                "direct_attachment_records": record_counts.get("attachment", 0),
                "external_link_records": len(built["external_index"]),
                "external_document_records": record_counts.get("external", 0),
                "utility_link_records": record_counts.get("utility", 0),
                "attachment_policy": "metadata_only",
                "external_link_policy": "record_only",
                "source_manifests": source_manifest_artifacts,
                "source_manifest_summaries": {
                    source_id: {
                        "doc_count": payload["doc_count"],
                        "attachment_count": payload["attachment_count"],
                        "attachment_filename_only": payload["attachment_evidence_coverage"]["filename_only"],
                        "attachment_text_extracted": payload["attachment_evidence_coverage"]["text_extracted"],
                        "attachment_full_content": payload["attachment_evidence_coverage"]["full_content"],
                        "shard_count": int(payload["artifacts"]["proof_catalog"]["count"]),
                        "local_index_count": len(payload["local_indexes"]),
                    }
                    for source_id, payload in source_manifest_payloads.items()
                },
                "shard_strategy": {
                    "version": "locality-source-facet-record-year-section-hash-routed",
                    "dimensions": ["source_id", "facet", "record_type", "year", "top_nav_section", "hash_bucket"],
                    "hash_bucket_count": 4,
                    "sequential_fixed_size_shards": False,
                },
                "indexes": artifacts,
            },
        }

    size_report = {
        "generated_at": now_iso(),
        "first_screen_files": [],
        "first_screen_bytes": 0,
        "routed_first_screen_files": [
            {"name": name, "path": artifacts[name]["path"], "bytes": artifacts[name]["bytes"]}
            for name in first_screen_artifacts
        ],
        "routed_first_screen_bytes": sum(int(artifacts[name]["bytes"]) for name in first_screen_artifacts),
        "routed_first_screen_total_bytes": sum(int(artifacts[name]["bytes"]) for name in first_screen_artifacts),
        "global_query_directory_bytes": artifacts["global_query_directory"]["bytes"],
        "source_registry_bytes": artifacts["source_registry"]["bytes"],
        "query_aliases_bytes": artifacts["query_aliases"]["bytes"],
        "local_impact_light_index_total_bytes": sum(int((ref.get("light_index") or {}).get("bytes") or 0) for ref in local_refs),
        "local_impact_light_index_meta_total_bytes": sum(int(ref["light_index_meta"]["bytes"]) for ref in local_refs),
        "local_impact_light_index_packed_total_bytes": sum(int(ref["light_index_packed"]["bytes"]) for ref in local_refs),
        "local_impact_body_index_total_bytes": sum(int(ref["body_index"]["bytes"]) for ref in local_refs),
        "local_impact_body_index_packed_total_bytes": sum(int(ref["body_index_packed"]["bytes"]) for ref in local_refs),
        "local_index_count": len(local_refs),
        "light_index_runtime_bytes": sum(local_light_runtime_bytes(ref) for ref in local_refs),
        "body_index_bytes": sum(int(ref["body_index"]["bytes"]) for ref in local_refs),
        "body_index_runtime_bytes": sum(local_body_runtime_bytes(ref) for ref in local_refs),
        "local_index_runtime_bytes": sum(local_light_runtime_bytes(ref) + local_body_runtime_bytes(ref) for ref in local_refs),
        "full_scan_total_bytes": total_full_scan_bytes,
        "shard_count": len(full_shards),
        "max_shard_bytes": max_full_shard_bytes,
        "avg_shard_bytes": avg_full_shard_bytes,
        "full_shard_count": len(full_shards),
        "max_full_shard_bytes": max_full_shard_bytes,
        "avg_full_shard_bytes": avg_full_shard_bytes,
        "max_full_shard_documents": max((int(item["count"]) for item in full_shards), default=0),
        "avg_full_shard_documents": round(sum(int(item["count"]) for item in full_shards) / max(1, len(full_shards)), 2),
        "artifact_count": sum(1 for _ in PUBLIC_SITEGRAPH_DIR.rglob("*.json")),
        "artifact_total_bytes": sum(path.stat().st_size for path in PUBLIC_SITEGRAPH_DIR.rglob("*.json")),
        "binary_artifact_count": sum(1 for _ in PUBLIC_SITEGRAPH_DIR.rglob("*.bin")),
        "binary_artifact_total_bytes": sum(path.stat().st_size for path in PUBLIC_SITEGRAPH_DIR.rglob("*.bin")),
        "runtime_artifact_total_bytes": sum(path.stat().st_size for path in PUBLIC_SITEGRAPH_DIR.rglob("*") if path.is_file()),
        "representative_query_phase_timings": {
            "query": "校历",
            "planning_ms": 0,
            "local_index_ms": 0,
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

    manifest = make_manifest()
    write_json(PUBLIC_INDEX_DIR / "manifest.json", manifest)

    bootstrap_bytes = (PUBLIC_INDEX_DIR / "manifest.json").stat().st_size
    size_report["bootstrap_manifest_bytes"] = bootstrap_bytes
    size_report["routed_first_screen_files"] = [
        {"name": "bootstrap_manifest", "path": f"generated/collections/{COLLECTION_ID}/manifest.json", "bytes": bootstrap_bytes},
        *[
            {"name": name, "path": artifacts[name]["path"], "bytes": artifacts[name]["bytes"]}
            for name in first_screen_artifacts
        ],
    ]
    size_report["routed_first_screen_bytes"] = bootstrap_bytes + sum(int(artifacts[name]["bytes"]) for name in first_screen_artifacts)
    size_report["routed_first_screen_total_bytes"] = size_report["routed_first_screen_bytes"]
    size_report["artifact_count"] = sum(1 for _ in PUBLIC_SITEGRAPH_DIR.rglob("*.json"))
    size_report["artifact_total_bytes"] = sum(path.stat().st_size for path in PUBLIC_SITEGRAPH_DIR.rglob("*.json"))
    size_report["binary_artifact_count"] = sum(1 for _ in PUBLIC_SITEGRAPH_DIR.rglob("*.bin"))
    size_report["binary_artifact_total_bytes"] = sum(path.stat().st_size for path in PUBLIC_SITEGRAPH_DIR.rglob("*.bin"))
    size_report["runtime_artifact_total_bytes"] = sum(path.stat().st_size for path in PUBLIC_SITEGRAPH_DIR.rglob("*") if path.is_file())
    size_artifact = write_hashed_json(PUBLIC_ROOT, PUBLIC_ARTIFACT_DIR, "size_report", size_report, compact=False)
    artifacts["size_report"] = artifact_entry(size_artifact, role="size_report", load="audit")
    manifest = make_manifest()
    write_json(PUBLIC_INDEX_DIR / "manifest.json", manifest)
    return manifest
