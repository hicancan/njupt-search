from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from . import sitegraph_public_index as public_index
from .sitegraph_public_index import aggregate_counts
from .sitegraph_source import load_collection_source_packages, package_source_id, validate_sitegraph_package


REQUIRED_QUERIES = (
    "校历",
    "慕课考试",
    "期末考试",
    "转专业",
    "规章制度",
    "办事流程",
    "学生相关文件及表格",
    "教务管理系统",
    "大创",
    "推免",
    "成绩",
    "附件1",
    "xlsx",
    "奖学金",
    "辅导员",
    "双创",
    "互联网+",
)

MODEL_FIELD_PREFIX = "".join(["l", "l", "m"])
TASK_FIELD_PREFIX = "".join(["hy", "task"])
OBSOLETE_FIELDS = {
    MODEL_FIELD_PREFIX,
    f"{MODEL_FIELD_PREFIX}_provider",
    "semantic_mode",
    "task_frames",
    f"{MODEL_FIELD_PREFIX}_schema_version",
    f"{MODEL_FIELD_PREFIX}_in_core_path",
    f"old_{TASK_FIELD_PREFIX}_removed",
    "source_channel_production_enabled",
    "github_resource_production_enabled",
}
LEGACY_RUNTIME_ARTIFACTS = {"doc_meta_light", "light_inverted_index"}


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def fail(message: str) -> None:
    print(f"[validate_sitegraph_index] {message}", file=sys.stderr)
    raise SystemExit(1)


def ensure_no_obsolete_fields(payload: Any, path: str = "$") -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in OBSOLETE_FIELDS:
                fail(f"{path}.{key} is an obsolete search field")
            ensure_no_obsolete_fields(value, f"{path}.{key}")
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            ensure_no_obsolete_fields(item, f"{path}[{index}]")


def ensure_public_hashed_path(path: str, label: str) -> Path:
    if "\\" in path or re.search(r"^[A-Za-z]:", path):
        fail(f"{label} must be public-relative: {path}")
    if not re.search(r"\.[0-9a-f]{16}\.json$", path):
        fail(f"{label} must use content hash filename: {path}")
    resolved = public_index.PUBLIC_ROOT / path
    if not resolved.exists():
        fail(f"{label} is missing: {resolved}")
    return resolved


def artifact_path(manifest: dict[str, Any], name: str) -> Path:
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}
    entry = artifacts.get(name)
    if not isinstance(entry, dict) or not entry.get("path"):
        fail(f"manifest.artifacts.{name}.path is missing")
    return ensure_public_hashed_path(str(entry["path"]), f"manifest.artifacts.{name}.path")


def load_source_manifests(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    source_manifests = ((manifest.get("sitegraph") or {}).get("source_manifests") or {})
    if not isinstance(source_manifests, dict) or not source_manifests:
        fail("manifest.sitegraph.source_manifests must declare routed source manifests")
    payloads: list[dict[str, Any]] = []
    for source_id, entry in source_manifests.items():
        if not isinstance(entry, dict) or not entry.get("path"):
            fail(f"source manifest entry missing path: {source_id}")
        payload = read_json(ensure_public_hashed_path(str(entry["path"]), f"source_manifest.{source_id}"))
        if payload.get("source_id") != source_id:
            fail(f"source manifest source_id mismatch: {source_id}")
        payloads.append(payload)
    return payloads


def load_full_documents(source_manifests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    seen_shards: set[str] = set()
    for source_manifest in source_manifests:
        shards = source_manifest.get("full_shards")
        if not isinstance(shards, list) or not shards:
            fail(f"source {source_manifest.get('source_id')} has no full_shards")
        for shard in shards:
            if not isinstance(shard, dict):
                fail("source manifest full_shards contains a non-object shard")
            shard_id = str(shard.get("shard_id") or "")
            if shard_id in seen_shards:
                fail(f"duplicate shard id across source manifests: {shard_id}")
            seen_shards.add(shard_id)
            for field in ("source_id", "shard_id", "facet_range", "section_range", "year_range", "hash_bucket", "sha256", "bytes", "filter_token_count", "filter_sha256"):
                if field not in shard:
                    fail(f"full shard missing {field}: {shard_id}")
            shard_path = ensure_public_hashed_path(str(shard.get("path") or ""), f"full_shard.{shard_id}.path")
            payload = read_json(shard_path)
            if not isinstance(payload, list):
                fail(f"full shard must be a list: {shard_path}")
            if int(shard.get("count", -1)) != len(payload):
                fail(f"full shard count mismatch for {shard_path}: manifest={shard.get('count')} actual={len(payload)}")
            for document in payload:
                if document.get("source_id") != shard.get("source_id"):
                    fail(f"full shard source_id mismatch: {document.get('id')}")
            documents.extend(payload)
    return documents


def validate_local_indexes(source_manifests: list[dict[str, Any]], expected_source_ids: set[str]) -> list[dict[str, Any]]:
    local_documents: list[dict[str, Any]] = []
    for source_manifest in source_manifests:
        source_id = str(source_manifest["source_id"])
        for name in ("proof_catalog", "shard_filter", "attachment_meta_index", "attachment_filename_index", "attachment_text_shards"):
            entry = source_manifest.get("artifacts", {}).get(name)
            if not isinstance(entry, dict) or not entry.get("path"):
                fail(f"source {source_id} missing artifact {name}")
            ensure_public_hashed_path(str(entry["path"]), f"source {source_id} artifact {name}")
        for ref in source_manifest.get("local_indexes") or []:
            scope = ref.get("scope") if isinstance(ref.get("scope"), dict) else {}
            if scope.get("source_id") != source_id:
                fail(f"local index source mismatch: {ref.get('index_id')}")
            if scope.get("source_id") not in expected_source_ids:
                fail(f"local index has unexpected source: {scope.get('source_id')}")
            light_payload = read_json(ensure_public_hashed_path(str(ref["light_index"]["path"]), f"local_light.{ref.get('index_id')}"))
            body_payload = read_json(ensure_public_hashed_path(str(ref["body_index"]["path"]), f"local_body.{ref.get('index_id')}"))
            if set((light_payload.get("field_codes") or {}).values()).difference({"t", "s", "n", "g", "a", "e", "y"}):
                fail(f"local light index has invalid field codes: {ref.get('index_id')}")
            if set((body_payload.get("field_codes") or {}).values()).difference({"m", "c"}):
                fail(f"local body index has invalid field codes: {ref.get('index_id')}")
            for label, payload in (("light", light_payload), ("body", body_payload)):
                if "tokens" in payload:
                    fail(f"local {label} index must not expose legacy tokens: {ref.get('index_id')}")
                if payload.get("scoring_model") != "impact-ordered-block-max-bm25f-lite-v2":
                    fail(f"local {label} index has unexpected scoring_model: {ref.get('index_id')}")
                if not isinstance(payload.get("terms"), dict):
                    fail(f"local {label} index missing impact terms: {ref.get('index_id')}")
                if int(payload.get("block_size") or 0) <= 0:
                    fail(f"local {label} index missing block_size: {ref.get('index_id')}")
            docs = light_payload.get("documents")
            if not isinstance(docs, list) or len(docs) != int(ref.get("doc_count", -1)):
                fail(f"local light index document count mismatch: {ref.get('index_id')}")
            for item in docs:
                if any(field in item for field in ("content", "summary", "attachments", "provenance")):
                    fail("local light index metadata must not contain content, summary, attachments, or raw provenance")
                for field in ("source_id", "date_kind", "task_kind", "authority_profile", "dedupe_key"):
                    if not item.get(field):
                        fail(f"local index metadata missing ranking field {field}: {item.get('id')}")
                local_documents.append(item)
    return local_documents


def validate_generated_index(packages: list[dict[str, Any]] | dict[str, Any]) -> dict[str, Any]:
    if isinstance(packages, dict):
        packages = [packages]
    aggregate_truth_counts = aggregate_counts(packages)
    expected_source_ids = {package_source_id(package) for package in packages}
    detail_urls = {
        str(item.get("url"))
        for package in packages
        for item in package["detail_pages"]
    }
    manifest_path = public_index.PUBLIC_INDEX_DIR / "manifest.json"
    if not manifest_path.exists():
        fail(f"required generated artifact missing: manifest: {manifest_path}")
    if public_index.OBSOLETE_INDEX_DIR.exists():
        fail(f"obsolete index directory must be removed: {public_index.OBSOLETE_INDEX_DIR}")
    for stale in (
        "documents.json",
        "task_frames.json",
        "ontology.json",
        "doc_meta.json",
        "inverted_index.json",
        "section_index.json",
        "attachment_index.json",
        "external_index.json",
        "query_aliases.json",
        "shard_catalog.json",
        "shard_filter.json",
    ):
        if (public_index.PUBLIC_INDEX_DIR / stale).exists():
            fail(f"{public_index.PUBLIC_INDEX_DIR}/{stale} must not exist in the hash-addressed routed contract")

    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        fail("generated collection manifest must be an object")
    ensure_no_obsolete_fields(manifest)
    if manifest.get("strategy") != "routed-verifiable-static-search":
        fail(f"manifest.strategy must be routed-verifiable-static-search, got {manifest.get('strategy')!r}")
    manifest_text = json.dumps(manifest, ensure_ascii=False)
    if "D:\\" in manifest_text or "D:/" in manifest_text:
        fail("public manifest must not expose local D: paths")
    for field in ("producer_repo", "producer_ref", "site_id", "collection_id", "artifact_path", "upstream_generated_at", "truth_counts"):
        if not manifest.get(field):
            fail(f"manifest missing required public producer field: {field}")
    if manifest.get("site_id") != manifest.get("collection_id"):
        fail("manifest.site_id must equal manifest.collection_id")
    if manifest.get("collection_id") != "njupt-public":
        fail(f"manifest.collection_id must be njupt-public, got {manifest.get('collection_id')!r}")
    if manifest.get("artifact_path") != "generated/collections/njupt-public":
        fail(f"manifest.artifact_path must be generated/collections/njupt-public, got {manifest.get('artifact_path')!r}")

    core_search = manifest.get("core_search") if isinstance(manifest.get("core_search"), dict) else {}
    if core_search.get("execution_model") != "pure_frontend_worker":
        fail("core_search.execution_model must be pure_frontend_worker")
    if core_search.get("readiness") != "routed_bootstrap":
        fail("core_search.readiness must be routed_bootstrap")
    if core_search.get("legacy_global_first_screen") is not False:
        fail("legacy global first-screen startup must be disabled")
    if core_search.get("first_screen_artifacts") != ["source_registry", "global_query_directory", "query_aliases"]:
        fail(f"unexpected first_screen_artifacts: {core_search.get('first_screen_artifacts')!r}")
    if any(name in (manifest.get("artifacts") or {}) for name in LEGACY_RUNTIME_ARTIFACTS):
        fail("legacy global runtime artifacts must not be manifest artifacts")
    if "full_shards" in (manifest.get("sitegraph") or {}):
        fail("bootstrap manifest must not embed full shard catalog")
    routing_contract = manifest.get("routing_contract") if isinstance(manifest.get("routing_contract"), dict) else {}
    for field in ("directory_contains_doc_postings", "startup_loads_local_indexes", "startup_loads_full_shards", "startup_loads_global_document_metadata"):
        if routing_contract.get(field) is not False:
            fail(f"routing_contract.{field} must be false")

    progressive_search = manifest.get("progressive_search") if isinstance(manifest.get("progressive_search"), dict) else {}
    coverage_contract = manifest.get("coverage_contract") if isinstance(manifest.get("coverage_contract"), dict) else {}
    if progressive_search.get("full_scan_supported") is not True:
        fail("manifest.progressive_search.full_scan_supported must be true")
    if progressive_search.get("progressive_events") is not True:
        fail("manifest.progressive_search.progressive_events must be true")
    for state in ("first_trusted_results", "top_results_hydrated", "partial_verified", "scoped_exhaustive_complete", "global_exhaustive_complete"):
        if state not in (coverage_contract.get("states") or []):
            fail(f"manifest.coverage_contract.states missing {state}")
    for field in ("title", "url", "section", "nav_path", "summary", "content", "attachments"):
        if field not in set(coverage_contract.get("coverage_fields") or []):
            fail(f"manifest.coverage_contract.coverage_fields missing {field}")
    verification_contract = manifest.get("verification_contract") if isinstance(manifest.get("verification_contract"), dict) else {}
    if verification_contract.get("shard_filter_supported") is not True:
        fail("manifest.verification_contract.shard_filter_supported must be true")
    if verification_contract.get("proved_skip_supported") is not True:
        fail("manifest.verification_contract.proved_skip_supported must be true")
    if verification_contract.get("scan_fallback_supported") is not True:
        fail("manifest.verification_contract.scan_fallback_supported must be true")
    if verification_contract.get("filter_artifact_family") != "shard_filters":
        fail("manifest.verification_contract.filter_artifact_family must be shard_filters")
    if verification_contract.get("proof_catalog_artifact_family") != "proof_catalogs":
        fail("manifest.verification_contract.proof_catalog_artifact_family must be proof_catalogs")
    if verification_contract.get("completion_requires_ledger") is not True:
        fail("manifest.verification_contract.completion_requires_ledger must be true")

    required_artifacts = (
        "source_registry",
        "global_query_directory",
        "query_aliases",
        "outcomes",
        "quality_report",
        "query_eval_report",
        "size_report",
    )
    for name in required_artifacts:
        artifact_path(manifest, name)

    source_registry = read_json(artifact_path(manifest, "source_registry"))
    sources = source_registry.get("sources")
    if not isinstance(sources, list) or not sources:
        fail("source_registry.sources must be non-empty")
    source_ids = {str(item.get("source_id")) for item in sources if isinstance(item, dict)}
    if expected_source_ids and source_ids != expected_source_ids:
        fail(f"source registry must match source packages: registry={sorted(source_ids)} expected={sorted(expected_source_ids)}")
    for item in sources:
        if item.get("artifact_manifest", {}).get("role") != "source_manifest":
            fail(f"source registry missing source manifest artifact: {item.get('source_id')}")
        for field in ("owner_unit", "authority_domains", "priority_by_intent", "freshness_policy", "doc_count", "quality_status", "coverage_status"):
            if field not in item:
                fail(f"source registry entry missing {field}: {item.get('source_id')}")

    query_directory = read_json(artifact_path(manifest, "global_query_directory"))
    if query_directory.get("version") != "sitegraph-global-query-directory-cost-v2":
        fail("global_query_directory has unexpected version")
    directory_text = json.dumps(query_directory, ensure_ascii=False)
    if "doc_index" in directory_text:
        fail("global_query_directory must not contain document-level postings")
    if not isinstance(query_directory.get("entries"), dict) or not query_directory["entries"]:
        fail("global_query_directory.entries must be non-empty")

    source_manifests = load_source_manifests(manifest)
    full_documents = load_full_documents(source_manifests)
    local_documents = validate_local_indexes(source_manifests, expected_source_ids)
    if len(local_documents) != len(full_documents):
        fail(f"local metadata/full document count mismatch: local={len(local_documents)} full={len(full_documents)}")
    if int(manifest.get("total_documents", -1)) != len(full_documents):
        fail(f"manifest total_documents mismatch: manifest={manifest.get('total_documents')} full={len(full_documents)}")
    if int(progressive_search.get("total_shards", -1)) != sum(len(item["full_shards"]) for item in source_manifests):
        fail("manifest.progressive_search.total_shards must equal source manifest shard total")
    if int(coverage_contract.get("total_documents", -1)) != int(manifest.get("total_documents", -2)):
        fail("manifest.coverage_contract.total_documents must equal manifest.total_documents")

    ids = [str(item.get("id") or "") for item in full_documents if isinstance(item, dict)]
    if len(ids) != len(set(ids)):
        fail("full documents contain duplicate ids")
    if len(ids) != len(full_documents):
        fail("full documents contain non-object or missing-id entries")
    ensure_no_obsolete_fields(full_documents)
    for document in full_documents:
        for field in ("source_id", "canonical_title", "date_kind", "date_confidence", "task_kind", "authority_profile", "dedupe_key"):
            if not document.get(field):
                fail(f"full document missing ranking field {field}: {document.get('id')}")
        if document.get("source_id") not in expected_source_ids:
            fail(f"full document has unexpected source_id: {document.get('source_id')}")
        provenance = document.get("provenance") if isinstance(document.get("provenance"), dict) else {}
        if document.get("source_id") != provenance.get("site_id"):
            fail(f"full document source_id/provenance.site_id mismatch: {document.get('id')}")
        if document.get("record_type") == "external":
            if document.get("published_at"):
                fail(f"external record must not treat recorded_at as published_at: {document.get('id')}")
            if not document.get("recorded_at"):
                fail(f"external record missing recorded_at: {document.get('id')}")

    detail_docs = {str(item.get("url")): item for item in full_documents if item.get("record_type") == "detail"}
    missing_detail_urls = sorted(detail_urls.difference(detail_docs))
    if missing_detail_urls:
        fail(f"detail pages missing search records: {missing_detail_urls[:10]}")
    if len(detail_docs) != aggregate_truth_counts["detail_pages"]:
        fail(f"detail document count mismatch: {len(detail_docs)} != {aggregate_truth_counts['detail_pages']}")

    outcomes = read_json(artifact_path(manifest, "outcomes"))
    if not isinstance(outcomes, dict):
        fail("outcomes must be an object")
    if len(outcomes.get("detail_page_records") or []) != aggregate_truth_counts["detail_pages"]:
        fail("outcomes.detail_page_records must cover every detail page")
    if len(outcomes.get("attachment_metadata_records") or []) != aggregate_truth_counts["attachments"]:
        fail("outcomes.attachment_metadata_records must cover every attachment")
    if len(outcomes.get("external_link_records") or []) != aggregate_truth_counts["external_links"]:
        fail("outcomes.external_link_records must cover every external link")

    sitegraph = manifest.get("sitegraph") if isinstance(manifest.get("sitegraph"), dict) else {}
    truth_counts = sitegraph.get("truth_counts") if isinstance(sitegraph.get("truth_counts"), dict) else {}
    for field, actual in aggregate_truth_counts.items():
        if int(truth_counts.get(field, -1) or 0) != int(actual):
            fail(f"manifest.sitegraph.truth_counts.{field} mismatch: manifest={truth_counts.get(field)} actual={actual}")
    source_counts = sitegraph.get("source_truth_counts") if isinstance(sitegraph.get("source_truth_counts"), dict) else {}
    for package in packages:
        source_id = package_source_id(package)
        if source_id not in source_counts:
            fail(f"manifest.sitegraph.source_truth_counts missing {source_id}")
        for field, actual in package["actual_counts"].items():
            if int(source_counts[source_id].get(field, -1) or 0) != int(actual):
                fail(f"manifest.sitegraph.source_truth_counts.{source_id}.{field} mismatch")

    shard_strategy = sitegraph.get("shard_strategy") if isinstance(sitegraph.get("shard_strategy"), dict) else {}
    if shard_strategy.get("sequential_fixed_size_shards") is not False:
        fail("full shards must not use sequential fixed-size strategy")
    for dimension in ("source_id", "facet", "record_type", "year", "top_nav_section", "hash_bucket"):
        if dimension not in (shard_strategy.get("dimensions") or []):
            fail(f"shard strategy missing dimension: {dimension}")

    full_text = json.dumps([local_documents, source_registry, query_directory], ensure_ascii=False)
    aliases = read_json(artifact_path(manifest, "query_aliases"))
    for query in REQUIRED_QUERIES:
        if query not in full_text and query not in aliases:
            fail(f"representative query lacks searchable routing text or alias: {query}")

    return {
        "passed": True,
        "total_documents": len(full_documents),
        "detail_page_records": len(detail_docs),
        "attachment_metadata_records": aggregate_truth_counts["attachments"],
        "external_link_records": aggregate_truth_counts["external_links"],
        "truth_counts": aggregate_truth_counts,
        "source_ids": sorted(source_ids),
        "source_manifest_count": len(source_manifests),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate source package and generated routed collection search artifacts.")
    parser.add_argument(
        "--source-package",
        dest="source_packages",
        action="append",
        type=Path,
        default=None,
        help="Path to an audited njupt-site-graph source package index. Repeat for multiple source packages.",
    )
    parser.add_argument("--collection", type=Path, default=None, help="Generated collection directory to validate")
    parser.add_argument("--skip-output", action="store_true", help="Only validate upstream sitegraph source packages")
    args = parser.parse_args()

    from .sitegraph_public_index import configure_collection_output

    configure_collection_output(output_dir=args.collection)
    source_packages = args.source_packages or load_collection_source_packages()
    resolved_packages = [path.resolve() for path in source_packages]
    packages = [validate_sitegraph_package(path) for path in resolved_packages]
    summary: dict[str, Any] = {
        "sitegraph_indexes": [str(path) for path in resolved_packages],
        "source_ids": [package_source_id(package) for package in packages],
        "package_valid": True,
        "truth_counts": aggregate_counts(packages),
        "quality": {package_source_id(package): package["manifest"].get("quality") for package in packages},
    }
    if not args.skip_output:
        summary["generated_index"] = validate_generated_index(packages)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
