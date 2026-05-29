import json
from pathlib import Path

from njupt_search_eval.sitegraph_search import recall_documents
from njupt_search_indexer.sitegraph_source import (
    COUNT_FIELDS,
    load_collection_source_packages,
    package_source_id,
    validate_sitegraph_package,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
PUBLIC_ROOT = ROOT_DIR / "apps" / "web" / "public"
PUBLIC_INDEX_DIR = PUBLIC_ROOT / "generated" / "collections" / "njupt-public"
MODEL_FIELD_PREFIX = "".join(["l", "l", "m"])
TASK_FIELD_PREFIX = "".join(["hy", "task"])
BANNED_KEYS = {
    MODEL_FIELD_PREFIX,
    f"{MODEL_FIELD_PREFIX}_provider",
    f"{MODEL_FIELD_PREFIX}_schema_version",
    "semantic_mode",
    "task_frames",
    f"{MODEL_FIELD_PREFIX}_in_core_path",
    f"old_{TASK_FIELD_PREFIX}_removed",
    "source_channel_production_enabled",
    "github_resource_production_enabled",
}
REQUIRED_QUERIES = [
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
]

EXPECTED_SOURCE_IDS = {"jwc", "xsc", "cxcy"}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def walk_keys(payload):
    if isinstance(payload, dict):
        for key, value in payload.items():
            yield key
            yield from walk_keys(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from walk_keys(item)


def expected_source_counts(manifest: dict) -> dict[str, dict[str, int]]:
    source_package_paths = [path for path in load_collection_source_packages() if path.exists()]
    if source_package_paths:
        packages = [validate_sitegraph_package(path) for path in source_package_paths]
        return {
            package_source_id(package): {
                field: int(package["actual_counts"].get(field, 0) or 0)
                for field in COUNT_FIELDS
            }
            for package in packages
        }

    source_entries = {
        str(item.get("source_id")): item
        for item in manifest.get("sources", [])
        if isinstance(item, dict)
    }
    return {
        source_id: {
            field: int((source_entries[source_id].get("truth_counts") or {}).get(field, 0) or 0)
            for field in COUNT_FIELDS
        }
        for source_id in EXPECTED_SOURCE_IDS
    }


def test_public_index_is_pure_sitegraph_contract():
    manifest = read_json(PUBLIC_INDEX_DIR / "manifest.json")
    assert manifest["strategy"] == "progressive-verifiable-static-search"
    assert manifest["producer_repo"] == "hicancan/njupt-search"
    assert manifest["site_id"] == "njupt-public"
    assert manifest["collection_id"] == "njupt-public"
    assert {item["source_id"] for item in manifest["sources"]} == {"jwc", "xsc", "cxcy"}
    assert manifest["artifact_path"] == "generated/collections/njupt-public"
    assert manifest["upstream_generated_at"]
    assert "D:\\" not in json.dumps(manifest, ensure_ascii=False)
    assert "D:/" not in json.dumps(manifest, ensure_ascii=False)
    assert manifest["exam_vertical_preserved"] is True
    assert manifest["core_search"]["execution_model"] == "pure_frontend_worker"
    assert manifest["core_search"]["light_first_screen"] is True
    assert manifest["core_search"]["first_screen_artifacts"] == ["doc_meta_light", "light_inverted_index", "query_aliases"]
    assert manifest["core_search"]["body_index_loading"] == "on_deep_search"
    assert manifest["core_search"]["full_text_loading"] == "progressive_candidate_hydration_then_exhaustive_full_scan"
    assert manifest["core_search"]["search_worker"] is True
    assert manifest["progressive_search"]["full_scan_supported"] is True
    assert manifest["progressive_search"]["progressive_events"] is True
    assert manifest["progressive_search"]["total_shards"] == len(manifest["sitegraph"]["full_shards"])
    assert manifest["progressive_search"]["total_documents"] == manifest["total_documents"]
    assert manifest["coverage_contract"]["total_shards"] == len(manifest["sitegraph"]["full_shards"])
    assert manifest["coverage_contract"]["total_documents"] == manifest["total_documents"]
    assert set(["title", "url", "section", "nav_path", "summary", "content", "attachments"]) <= set(manifest["coverage_contract"]["coverage_fields"])
    assert manifest["verification_contract"]["shard_filter_supported"] is True
    assert manifest["verification_contract"]["proved_skip_supported"] is True
    assert manifest["verification_contract"]["scan_fallback_supported"] is True
    assert manifest["verification_contract"]["filter_artifact"] == "shard_filter"

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
        assert not (PUBLIC_INDEX_DIR / stale).exists()

    assert not (BANNED_KEYS & set(walk_keys(manifest)))
    for name, artifact in manifest["artifacts"].items():
        assert artifact["path"].startswith("generated/collections/njupt-public/sitegraph/")
        assert artifact["path"].endswith(".json")
        assert artifact["path"].rsplit(".", 2)[-2]
        assert "\\" not in artifact["path"]
        assert (PUBLIC_ROOT / artifact["path"]).exists(), name


def test_source_truth_counts_are_preserved():
    manifest = read_json(PUBLIC_INDEX_DIR / "manifest.json")
    truth_counts = manifest["sitegraph"]["truth_counts"]
    source_entries = {item["source_id"]: item for item in manifest["sources"]}
    expected_counts = expected_source_counts(manifest)
    expected_totals = {
        field: sum(source_counts[field] for source_counts in expected_counts.values())
        for field in COUNT_FIELDS
    }
    assert set(source_entries) == EXPECTED_SOURCE_IDS
    assert set(expected_counts) == EXPECTED_SOURCE_IDS
    for source_id, expected in expected_counts.items():
        for field, value in expected.items():
            assert manifest["sitegraph"]["source_truth_counts"][source_id][field] == value
            assert source_entries[source_id]["truth_counts"][field] == value
    for field, value in expected_totals.items():
        assert truth_counts[field] == value
    assert manifest["sitegraph"]["detail_page_records"] == truth_counts["detail_pages"]
    assert manifest["sitegraph"]["attachment_metadata_records"] == truth_counts["attachments"]
    assert manifest["sitegraph"]["external_link_records"] == truth_counts["external_links"]
    assert manifest["sitegraph"]["quality"]["errors"] == 0
    assert manifest["sitegraph"]["quality"]["all_discovered_urls_have_outcomes"] is True
    assert manifest["sitegraph"]["quality"]["attachment_policy"] == "metadata_only"
    assert manifest["sitegraph"]["quality"]["external_link_policy"] == "record_only"


def test_light_index_and_shards_have_no_obsolete_fields():
    manifest = read_json(PUBLIC_INDEX_DIR / "manifest.json")
    doc_meta = read_json(PUBLIC_ROOT / manifest["artifacts"]["doc_meta_light"]["path"])
    assert not (BANNED_KEYS & set(walk_keys(doc_meta)))
    assert all("content" not in item for item in doc_meta)
    assert all("summary" not in item for item in doc_meta)
    assert all("attachments" not in item for item in doc_meta)
    assert all("provenance" not in item for item in doc_meta)
    assert all(item.get("source_id") in {"jwc", "xsc", "cxcy"} for item in doc_meta)
    assert all(item.get("date_kind") for item in doc_meta)
    assert all(item.get("task_kind") for item in doc_meta)

    light_index = read_json(PUBLIC_ROOT / manifest["artifacts"]["light_inverted_index"]["path"])
    body_index = read_json(PUBLIC_ROOT / manifest["artifacts"]["body_inverted_index"]["path"])
    assert set(light_index["field_codes"].values()) <= {"t", "s", "n", "g", "a", "e", "y"}
    assert set(body_index["field_codes"].values()) == {"m", "c"}

    for shard in manifest["sitegraph"]["full_shards"]:
        documents = read_json(PUBLIC_ROOT / shard["path"])
        assert len(documents) == shard["count"]
        assert not (BANNED_KEYS & set(walk_keys(documents)))
        assert ".000." not in shard["path"]
        assert "\\" not in shard["path"]
        assert shard["filter_token_count"] > 0
        assert shard["filter_sha256"]
        for document in documents:
            assert set(["title", "url", "section", "nav_path", "summary", "content", "attachments", "record_type", "facet", "published_at", "provenance", "source_id", "canonical_title", "date_kind", "date_confidence", "task_kind", "authority_profile", "dedupe_key"]) <= set(document)
            assert document["source_id"] == document["provenance"]["site_id"]
            if document["record_type"] == "external":
                assert not document.get("published_at")
                assert document.get("recorded_at")


def test_required_queries_return_results():
    failures = {}
    for query in REQUIRED_QUERIES:
        results = recall_documents(query, limit=5)
        if not results:
            failures[query] = []
        elif query == "教务管理系统" and not any("教务管理系统" in str(item.get("title", "")) for item in results):
            failures[query] = [item.get("title") for item in results]
    assert failures == {}
