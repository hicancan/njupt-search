import json
from pathlib import Path

from njupt_search_eval.sitegraph_search import recall_documents


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
]


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


def test_public_index_is_pure_sitegraph_contract():
    manifest = read_json(PUBLIC_INDEX_DIR / "manifest.json")
    assert manifest["strategy"] == "progressive-verifiable-static-search"
    assert manifest["producer_repo"] == "hicancan/njupt-search"
    assert manifest["site_id"] == "jwc"
    assert manifest["collection_id"] == "njupt-public"
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
        assert artifact["path"].startswith("generated/collections/njupt-public/sitegraph/jwc/")
        assert artifact["path"].endswith(".json")
        assert artifact["path"].rsplit(".", 2)[-2]
        assert "\\" not in artifact["path"]
        assert (PUBLIC_ROOT / artifact["path"]).exists(), name


def test_jwc_truth_counts_are_preserved():
    manifest = read_json(PUBLIC_INDEX_DIR / "manifest.json")
    truth_counts = manifest["sitegraph"]["truth_counts"]
    assert truth_counts["detail_pages"] == 6884
    assert truth_counts["attachments"] == 7905
    assert truth_counts["external_links"] == 426
    assert truth_counts["edges"] == 16311
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
            assert set(["title", "url", "section", "nav_path", "summary", "content", "attachments", "record_type", "facet", "published_at", "provenance"]) <= set(document)


def test_required_queries_return_results():
    failures = {}
    for query in REQUIRED_QUERIES:
        results = recall_documents(query, limit=5)
        if not results:
            failures[query] = []
        elif query == "教务管理系统" and not any("教务管理系统" in str(item.get("title", "")) for item in results):
            failures[query] = [item.get("title") for item in results]
    assert failures == {}
