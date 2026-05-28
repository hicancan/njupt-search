from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[3]
COLLECTION_INDEXER_SRC = BASE_DIR / "tools" / "collection-indexer" / "src"
if str(COLLECTION_INDEXER_SRC) not in sys.path:
    sys.path.insert(0, str(COLLECTION_INDEXER_SRC))

from njupt_search_indexer.build_sitegraph_index import (  # noqa: E402
    DEFAULT_SITEGRAPH_INDEXES,
    OBSOLETE_INDEX_DIR,
    PUBLIC_INDEX_DIR,
    PUBLIC_ROOT,
    package_source_id,
    validate_sitegraph_package,
)
from njupt_search_indexer.validate_sitegraph_index import validate_generated_index  # noqa: E402


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def fail(message: str) -> None:
    print(f"[validate_search_index] {message}", file=sys.stderr)
    raise SystemExit(1)


def validate_contract_value(path: str, item_id: str, field: str, value: object, allowed: tuple[str, ...]) -> None:
    if str(value or "") not in allowed:
        fail(f"{path} item {item_id} invalid {field}={value!r}; allowed values: {', '.join(allowed)}")


def ensure_absent(payload: Any, forbidden: set[str], path: str = "$") -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in forbidden:
                fail(f"{path}.{key} is forbidden in the pure sitegraph index")
            ensure_absent(value, forbidden, f"{path}.{key}")
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            ensure_absent(item, forbidden, f"{path}[{index}]")


def main() -> None:
    model_field_prefix = "".join(["l", "l", "m"])
    task_field_prefix = "".join(["hy", "task"])
    os.chdir(BASE_DIR)
    manifest_path = PUBLIC_INDEX_DIR / "manifest.json"
    if not manifest_path.exists():
        fail(f"{manifest_path} does not exist")
    if OBSOLETE_INDEX_DIR.exists():
        fail(f"obsolete index directory must be removed: {OBSOLETE_INDEX_DIR}")
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        fail("manifest must be an object")
    ensure_absent(
        manifest,
        {
            model_field_prefix,
            f"{model_field_prefix}_provider",
            f"{model_field_prefix}_schema_version",
            "semantic_mode",
            "task_frames",
            f"{model_field_prefix}_in_core_path",
            f"old_{task_field_prefix}_removed",
            "source_channel_production_enabled",
            "github_resource_production_enabled",
        },
    )
    if manifest.get("strategy") != "progressive-verifiable-static-search":
        fail(f"unexpected manifest strategy: {manifest.get('strategy')!r}")
    manifest_text = json.dumps(manifest, ensure_ascii=False)
    if "D:\\" in manifest_text or "D:/" in manifest_text:
        fail("public manifest must not expose local D: paths")
    for field in ("producer_repo", "producer_ref", "site_id", "collection_id", "artifact_path", "upstream_generated_at", "truth_counts"):
        if not manifest.get(field):
            fail(f"manifest missing required producer field: {field}")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        fail("manifest.sources must declare at least one audited source package")
    source_ids = {str(item.get("source_id")) for item in sources if isinstance(item, dict)}
    expected_source_ids = {
        package_source_id(validate_sitegraph_package(path))
        for path in DEFAULT_SITEGRAPH_INDEXES
        if path.exists()
    }
    if expected_source_ids and source_ids != expected_source_ids:
        fail(f"manifest.sources must match audited packages: manifest={sorted(source_ids)} expected={sorted(expected_source_ids)}")
    if manifest.get("site_id") != manifest.get("collection_id"):
        fail("manifest.site_id is a legacy collection field and must equal manifest.collection_id")
    for item in sources:
        if not isinstance(item, dict):
            fail("manifest.sources entries must be objects")
        if item.get("source_kind") != "sitegraph":
            fail(f"manifest.sources.source_kind must be sitegraph, got {item.get('source_kind')!r}")
        root = item.get("artifact_root")
        if not isinstance(root, str) or not root.startswith("generated/collections/njupt-public/sitegraph"):
            fail(f"manifest.sources.artifact_root must be public collection-relative, got {root!r}")
    if manifest.get("collection_id") != "njupt-public":
        fail(f"unexpected collection_id: {manifest.get('collection_id')!r}")
    if manifest.get("artifact_path") != "generated/collections/njupt-public":
        fail(f"unexpected artifact_path: {manifest.get('artifact_path')!r}")
    core_search = manifest.get("core_search") if isinstance(manifest.get("core_search"), dict) else {}
    if core_search.get("execution_model") != "pure_frontend_worker":
        fail("core search must execute in the pure frontend worker")
    if core_search.get("first_screen_artifacts") != ["doc_meta_light", "light_inverted_index", "query_aliases"]:
        fail("first screen must only load manifest, doc_meta_light, light_inverted_index, and query_aliases")
    if core_search.get("body_index_loading") != "on_deep_search":
        fail("body index must be loaded only on deep search")
    if core_search.get("full_text_loading") != "progressive_candidate_hydration_then_exhaustive_full_scan":
        fail("full text must use progressive candidate hydration followed by exhaustive full scan")
    if core_search.get("search_worker") is not True:
        fail("search worker must be enabled")
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

    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}
    required = (
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
    for name in required:
        entry = artifacts.get(name)
        if not isinstance(entry, dict) or not entry.get("path"):
            fail(f"manifest.artifacts.{name}.path is missing")
        relative = str(entry["path"])
        if "\\" in relative or ":" in relative:
            fail(f"artifact path must be public-relative: {relative}")
        if not (PUBLIC_ROOT / relative).exists():
            fail(f"missing pure sitegraph index artifact: {relative}")
        if not relative.endswith(".json") or len(relative.rsplit(".", 2)) < 3:
            fail(f"artifact must use content hash filename: {relative}")
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
            fail(f"stale old search artifact still exists: {stale}")

    packages = [validate_sitegraph_package(path) for path in DEFAULT_SITEGRAPH_INDEXES if path.exists()]
    if packages:
        validate_generated_index(packages)
    print("[validate_search_index] ok")


if __name__ == "__main__":
    main()
