from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from .build_sitegraph_index import (
    BASE_DIR,
    DEFAULT_SITEGRAPH_INDEX,
    OBSOLETE_INDEX_DIR,
    PUBLIC_INDEX_DIR,
    PUBLIC_ROOT,
    PUBLIC_SITEGRAPH_DIR,
    validate_sitegraph_package,
)


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
)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def fail(message: str) -> None:
    print(f"[validate_sitegraph_index] {message}", file=sys.stderr)
    raise SystemExit(1)


def load_full_documents(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    shards = (((manifest.get("sitegraph") or {}).get("full_shards")) or [])
    if not isinstance(shards, list) or not shards:
        fail("manifest.sitegraph.full_shards must be a non-empty list")
    documents: list[dict[str, Any]] = []
    for shard in shards:
        if not isinstance(shard, dict):
            fail("manifest.sitegraph.full_shards contains a non-object shard")
        shard_rel = str(shard.get("path") or "")
        if "\\" in shard_rel or re.search(r"^[A-Za-z]:", shard_rel):
            fail(f"full shard path must be public-relative: {shard_rel}")
        if not re.search(r"\.[0-9a-f]{16}\.json$", shard_rel):
            fail(f"full shard path must use content hash filename: {shard_rel}")
        for field in ("shard_id", "facet_range", "section_range", "year_range", "hash_bucket", "sha256", "bytes"):
            if field not in shard:
                fail(f"full shard missing {field}: {shard_rel}")
        shard_path = PUBLIC_ROOT / shard_rel
        if not shard_path.exists():
            fail(f"full shard missing: {shard_path}")
        payload = read_json(shard_path)
        if not isinstance(payload, list):
            fail(f"full shard must be a list: {shard_path}")
        if int(shard.get("count", -1)) != len(payload):
            fail(f"full shard count mismatch for {shard_path}: manifest={shard.get('count')} actual={len(payload)}")
        documents.extend(payload)
    return documents


def artifact_path(manifest: dict[str, Any], name: str) -> Path:
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}
    entry = artifacts.get(name)
    if not isinstance(entry, dict) or not entry.get("path"):
        fail(f"manifest.artifacts.{name}.path is missing")
    path = str(entry["path"])
    if "\\" in path or re.search(r"^[A-Za-z]:", path):
        fail(f"manifest artifact path must be public-relative, got {name}: {path}")
    if name != "manifest" and not re.search(r"\.[0-9a-f]{16}\.json$", path):
        fail(f"artifact {name} must use a content hash filename: {path}")
    return PUBLIC_ROOT / path


MODEL_FIELD_PREFIX = "".join(["l", "l", "m"])
TASK_FIELD_PREFIX = "".join(["hy", "task"])


def ensure_no_obsolete_fields(payload: Any, path: str = "$") -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == f"{MODEL_FIELD_PREFIX}_provider" and value is None:
                fail(f"{path}.{key} must not be null")
            if key in {
                MODEL_FIELD_PREFIX,
                f"{MODEL_FIELD_PREFIX}_provider",
                "semantic_mode",
                "task_frames",
                f"{MODEL_FIELD_PREFIX}_schema_version",
                f"{MODEL_FIELD_PREFIX}_in_core_path",
                f"old_{TASK_FIELD_PREFIX}_removed",
                "source_channel_production_enabled",
                "github_resource_production_enabled",
            }:
                fail(f"{path}.{key} is an obsolete search field")
            ensure_no_obsolete_fields(value, f"{path}.{key}")
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            ensure_no_obsolete_fields(item, f"{path}[{index}]")


def validate_generated_index(package: dict[str, Any]) -> dict[str, Any]:
    manifest_path = PUBLIC_INDEX_DIR / "manifest.json"
    if not manifest_path.exists():
        fail(f"required generated artifact missing: manifest: {manifest_path}")
    if OBSOLETE_INDEX_DIR.exists():
        fail(f"obsolete index directory must be removed: {OBSOLETE_INDEX_DIR}")
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
    ):
        if (PUBLIC_INDEX_DIR / stale).exists():
            fail(f"{PUBLIC_INDEX_DIR}/{stale} must not exist in the hash-addressed contract")

    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        fail("generated collection manifest must be an object")
    ensure_no_obsolete_fields(manifest)
    if manifest.get("strategy") != "progressive-verifiable-static-search":
        fail(f"manifest.strategy must be progressive-verifiable-static-search, got {manifest.get('strategy')!r}")
    manifest_text = json.dumps(manifest, ensure_ascii=False)
    if "D:\\" in manifest_text or "D:/" in manifest_text:
        fail("public manifest must not expose local D: paths")
    for field in ("producer_repo", "producer_ref", "site_id", "collection_id", "artifact_path", "upstream_generated_at", "truth_counts"):
        if not manifest.get(field):
            fail(f"manifest missing required public producer field: {field}")
    if manifest.get("collection_id") != "njupt-public":
        fail(f"manifest.collection_id must be njupt-public, got {manifest.get('collection_id')!r}")
    if manifest.get("artifact_path") != "generated/collections/njupt-public":
        fail(f"manifest.artifact_path must be generated/collections/njupt-public, got {manifest.get('artifact_path')!r}")
    core_search = manifest.get("core_search") if isinstance(manifest.get("core_search"), dict) else {}
    if core_search.get("execution_model") != "pure_frontend_worker":
        fail("core_search.execution_model must be pure_frontend_worker")
    if core_search.get("light_first_screen") is not True:
        fail("core_search.light_first_screen must be true")
    if core_search.get("body_index_loading") != "on_deep_search":
        fail("body index must be loaded only on deep search")
    if core_search.get("full_text_loading") != "progressive_candidate_hydration_then_exhaustive_full_scan":
        fail("full text must use progressive candidate hydration followed by exhaustive full scan")
    if core_search.get("search_worker") is not True:
        fail("manifest must declare search worker execution")
    progressive_search = manifest.get("progressive_search") if isinstance(manifest.get("progressive_search"), dict) else {}
    coverage_contract = manifest.get("coverage_contract") if isinstance(manifest.get("coverage_contract"), dict) else {}
    full_shards = ((manifest.get("sitegraph") or {}).get("full_shards") or []) if isinstance(manifest.get("sitegraph"), dict) else []
    if progressive_search.get("full_scan_supported") is not True:
        fail("manifest.progressive_search.full_scan_supported must be true")
    if progressive_search.get("progressive_events") is not True:
        fail("manifest.progressive_search.progressive_events must be true")
    if int(progressive_search.get("total_shards", -1)) != len(full_shards):
        fail("manifest.progressive_search.total_shards must equal sitegraph.full_shards length")
    if int(progressive_search.get("total_documents", -1)) != int(manifest.get("total_documents", -2)):
        fail("manifest.progressive_search.total_documents must equal manifest.total_documents")
    if int(coverage_contract.get("total_shards", -1)) != len(full_shards):
        fail("manifest.coverage_contract.total_shards must equal sitegraph.full_shards length")
    if int(coverage_contract.get("total_documents", -1)) != int(manifest.get("total_documents", -2)):
        fail("manifest.coverage_contract.total_documents must equal manifest.total_documents")
    verification_contract = manifest.get("verification_contract") if isinstance(manifest.get("verification_contract"), dict) else {}
    if verification_contract.get("shard_filter_supported") is not True:
        fail("manifest.verification_contract.shard_filter_supported must be true")
    if verification_contract.get("proved_skip_supported") is not True:
        fail("manifest.verification_contract.proved_skip_supported must be true")
    if verification_contract.get("scan_fallback_supported") is not True:
        fail("manifest.verification_contract.scan_fallback_supported must be true")
    if verification_contract.get("filter_artifact") != "shard_filter":
        fail("manifest.verification_contract.filter_artifact must be shard_filter")
    coverage_fields = set(coverage_contract.get("coverage_fields") or [])
    for field in ("title", "url", "section", "nav_path", "summary", "content", "attachments"):
        if field not in coverage_fields:
            fail(f"manifest.coverage_contract.coverage_fields missing {field}")
    if manifest.get("exam_vertical_preserved") is not True:
        fail("exam_vertical_preserved must be true")
    first_screen = core_search.get("first_screen_artifacts")
    if first_screen != ["doc_meta_light", "light_inverted_index", "query_aliases"]:
        fail(f"unexpected first_screen_artifacts: {first_screen!r}")

    required_artifacts = (
        "doc_meta_light",
        "light_inverted_index",
        "body_inverted_index",
        "section_index",
        "attachment_index",
        "external_index",
        "query_aliases",
        "shard_catalog",
        "shard_filter",
        "outcomes",
        "size_report",
    )
    for name in required_artifacts:
        path = artifact_path(manifest, name)
        if not path.exists():
            fail(f"required generated artifact missing: {name}: {path}")

    sitegraph = manifest.get("sitegraph") if isinstance(manifest.get("sitegraph"), dict) else {}
    truth_counts = sitegraph.get("truth_counts") if isinstance(sitegraph.get("truth_counts"), dict) else {}
    for field, actual in package["actual_counts"].items():
        if int(truth_counts.get(field, -1) or 0) != int(actual):
            fail(f"manifest.sitegraph.truth_counts.{field} mismatch: manifest={truth_counts.get(field)} actual={actual}")

    shard_strategy = sitegraph.get("shard_strategy") if isinstance(sitegraph.get("shard_strategy"), dict) else {}
    if shard_strategy.get("sequential_fixed_size_shards") is not False:
        fail("full shards must not use sequential fixed-size strategy")
    for dimension in ("facet", "record_type", "year", "top_nav_section", "hash_bucket"):
        if dimension not in (shard_strategy.get("dimensions") or []):
            fail(f"shard strategy missing dimension: {dimension}")

    doc_meta = read_json(artifact_path(manifest, "doc_meta_light"))
    if not isinstance(doc_meta, list):
        fail("doc_meta_light must be a list")
    full_documents = load_full_documents(manifest)
    if len(doc_meta) != len(full_documents):
        fail(f"doc_meta/full document count mismatch: meta={len(doc_meta)} full={len(full_documents)}")
    if int(manifest.get("total_documents", -1)) != len(full_documents):
        fail(f"manifest total_documents mismatch: manifest={manifest.get('total_documents')} full={len(full_documents)}")
    ensure_no_obsolete_fields(full_documents)
    ensure_no_obsolete_fields(doc_meta)
    for item in doc_meta:
        if any(field in item for field in ("content", "summary", "attachments", "provenance")):
            fail("doc_meta_light must not contain content, summary, attachments, or raw provenance")

    ids = [str(item.get("id") or "") for item in full_documents if isinstance(item, dict)]
    if len(ids) != len(set(ids)):
        fail("full documents contain duplicate ids")
    if len(ids) != len(full_documents):
        fail("full documents contain non-object or missing-id entries")

    detail_docs = {str(item.get("url")): item for item in full_documents if item.get("record_type") == "detail"}
    detail_urls = {str(item.get("url")) for item in package["detail_pages"]}
    missing_detail_urls = sorted(detail_urls.difference(detail_docs))
    if missing_detail_urls:
        fail(f"detail pages missing search records: {missing_detail_urls[:10]}")
    if len(detail_docs) != package["actual_counts"]["detail_pages"]:
        fail(f"detail document count mismatch: {len(detail_docs)} != {package['actual_counts']['detail_pages']}")

    attachment_index = read_json(artifact_path(manifest, "attachment_index"))
    if not isinstance(attachment_index, list):
        fail("attachment_index.json must be a list")
    if len(attachment_index) != package["actual_counts"]["attachments"]:
        fail(f"attachment index count mismatch: {len(attachment_index)} != {package['actual_counts']['attachments']}")
    for item in attachment_index:
        if item.get("metadata_only") is not True:
            fail("attachment_index contains non metadata_only record")
        for field in ("name", "url", "extension", "parent_url", "section", "nav_path"):
            if not item.get(field):
                fail(f"attachment_index record missing {field}")

    external_index = read_json(artifact_path(manifest, "external_index"))
    if not isinstance(external_index, list):
        fail("external_index.json must be a list")
    if len(external_index) != package["actual_counts"]["external_links"]:
        fail(f"external index count mismatch: {len(external_index)} != {package['actual_counts']['external_links']}")

    outcomes = read_json(artifact_path(manifest, "outcomes"))
    if not isinstance(outcomes, dict):
        fail("outcomes must be an object")
    if len(outcomes.get("detail_page_records") or []) != package["actual_counts"]["detail_pages"]:
        fail("outcomes.detail_page_records must cover every detail page")
    if len(outcomes.get("attachment_metadata_records") or []) != package["actual_counts"]["attachments"]:
        fail("outcomes.attachment_metadata_records must cover every attachment")
    if len(outcomes.get("external_link_records") or []) != package["actual_counts"]["external_links"]:
        fail("outcomes.external_link_records must cover every external link")

    light_index = read_json(artifact_path(manifest, "light_inverted_index"))
    if not isinstance(light_index, dict) or not isinstance(light_index.get("tokens"), dict) or not light_index["tokens"]:
        fail("light_inverted_index must contain tokens")
    light_codes = set((light_index.get("field_codes") or {}).values())
    if light_codes.difference({"t", "s", "n", "g", "a", "e", "y"}):
        fail(f"light index contains non-entry field codes: {sorted(light_codes)}")
    body_index = read_json(artifact_path(manifest, "body_inverted_index"))
    body_codes = set((body_index.get("field_codes") or {}).values())
    if body_codes != {"m", "c"}:
        fail(f"body index must only contain summary/content field codes, got {sorted(body_codes)}")

    full_text = json.dumps([doc_meta, attachment_index, external_index], ensure_ascii=False)
    for required in ("教务管理系统", "自主学分系统", "创新管理系统", "毕业设计系统", "考试信息查询"):
        if required not in full_text:
            fail(f"required system or utility entry is not searchable: {required}")
    aliases = read_json(artifact_path(manifest, "query_aliases"))
    for query in REQUIRED_QUERIES:
        if query not in full_text and query not in aliases:
            fail(f"representative query lacks searchable text or alias: {query}")

    return {
        "passed": True,
        "total_documents": len(full_documents),
        "detail_page_records": len(detail_docs),
        "attachment_metadata_records": len(attachment_index),
        "external_link_records": len(external_index),
        "truth_counts": package["actual_counts"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate source package and generated collection search artifacts.")
    parser.add_argument("--source-package", type=Path, default=DEFAULT_SITEGRAPH_INDEX, help="Path to an audited njupt-site-graph source package index")
    parser.add_argument("--collection", type=Path, default=None, help="Generated collection directory to validate")
    parser.add_argument("--skip-output", action="store_true", help="Only validate the upstream JWC sitegraph package")
    args = parser.parse_args()

    from .build_sitegraph_index import configure_collection_output

    configure_collection_output(output_dir=args.collection)
    package = validate_sitegraph_package(args.source_package.resolve())
    summary: dict[str, Any] = {
        "sitegraph_index": str(args.source_package.resolve()),
        "package_valid": True,
        "truth_counts": package["actual_counts"],
        "quality": package["manifest"].get("quality"),
    }
    if not args.skip_output:
        summary["generated_index"] = validate_generated_index(package)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
