import json
from pathlib import Path

from njupt_search_eval.sitegraph_search import recall_documents
from njupt_search_indexer.sitegraph_binary_index import unpack_impact_index
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


def read_artifact(artifact: dict):
    return read_json(PUBLIC_ROOT / artifact["path"])


def load_source_registry(manifest: dict) -> dict:
    return read_artifact(manifest["artifacts"]["source_registry"])


def load_source_manifests(manifest: dict) -> list[dict]:
    return [
        read_artifact(manifest["sitegraph"]["source_manifests"][source_id])
        for source_id in sorted(manifest["sitegraph"]["source_manifests"])
    ]


def load_proof_catalogs(source_manifests: list[dict]) -> list[dict]:
    return [
        read_artifact(source_manifest["artifacts"]["proof_catalog"])
        for source_manifest in source_manifests
    ]


def proof_catalog_shards(proof_catalogs: list[dict]) -> list[dict]:
    return [
        shard
        for catalog in proof_catalogs
        for shard in catalog["shards"]
    ]


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

    source_registry = load_source_registry(manifest)
    source_entries = {
        str(item.get("source_id")): item
        for item in source_registry.get("sources", [])
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
    assert manifest["strategy"] == "routed-verifiable-static-search"
    assert manifest["producer_repo"] == "hicancan/njupt-search"
    assert manifest["site_id"] == "njupt-public"
    assert manifest["collection_id"] == "njupt-public"
    assert "sources" not in manifest
    assert manifest["artifact_path"] == "generated/collections/njupt-public"
    assert manifest["upstream_generated_at"]
    assert "D:\\" not in json.dumps(manifest, ensure_ascii=False)
    assert "D:/" not in json.dumps(manifest, ensure_ascii=False)
    assert manifest["exam_vertical_preserved"] is True
    assert manifest["core_search"]["execution_model"] == "pure_frontend_worker"
    assert manifest["core_search"]["readiness"] == "routed_bootstrap"
    assert manifest["core_search"]["legacy_global_first_screen"] is False
    assert manifest["core_search"]["first_screen_artifacts"] == ["source_registry", "global_query_directory", "query_aliases"]
    assert manifest["core_search"]["local_index_loading"] == "query_planned_on_demand"
    assert manifest["core_search"]["body_index_loading"] == "query_planned_on_demand"
    assert manifest["core_search"]["full_text_loading"] == "lazy_candidate_hydration_then_verified_scope_scan"
    assert manifest["core_search"]["search_worker"] is True
    assert manifest["progressive_search"]["full_scan_supported"] is True
    assert manifest["progressive_search"]["progressive_events"] is True
    assert "full_shards" not in manifest["sitegraph"]
    source_manifests = load_source_manifests(manifest)
    source_registry = load_source_registry(manifest)
    assert {item["source_id"] for item in source_registry["sources"]} == {"jwc", "xsc", "cxcy"}
    proof_catalogs = load_proof_catalogs(source_manifests)
    total_shards = len(proof_catalog_shards(proof_catalogs))
    assert manifest["progressive_search"]["total_shards"] == total_shards
    assert manifest["progressive_search"]["total_documents"] == manifest["total_documents"]
    assert manifest["coverage_contract"]["total_shards"] == total_shards
    assert manifest["coverage_contract"]["total_documents"] == manifest["total_documents"]
    assert set(["title", "url", "section", "nav_path", "summary", "content", "attachments"]) <= set(manifest["coverage_contract"]["coverage_fields"])
    assert set(["metadata_only", "filename_only", "text_extracted", "snippet", "full_content"]) <= set(manifest["coverage_contract"]["attachment_evidence_levels"])
    assert manifest["verification_contract"]["shard_filter_supported"] is True
    assert manifest["verification_contract"]["proved_skip_supported"] is True
    assert manifest["verification_contract"]["scan_fallback_supported"] is True
    assert manifest["verification_contract"]["filter_artifact_family"] == "shard_filters"
    assert manifest["verification_contract"]["proof_catalog_artifact_family"] == "proof_catalogs"
    assert manifest["verification_contract"]["completion_requires_ledger"] is True
    assert manifest["routing_contract"]["planner"] == "cost_authority_proof_ledger_planner_v2"
    assert manifest["routing_contract"]["directory_contains_doc_postings"] is False
    assert manifest["routing_contract"]["startup_loads_local_indexes"] is False
    assert manifest["routing_contract"]["startup_loads_full_shards"] is False
    assert manifest["routing_contract"]["startup_loads_global_document_metadata"] is False
    assert "doc_meta_light" not in manifest["artifacts"]
    assert "light_inverted_index" not in manifest["artifacts"]

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

    source_manifest_artifacts = manifest["sitegraph"]["source_manifests"]
    for source in source_registry["sources"]:
        source_id = source["source_id"]
        assert source["artifact_manifest"]["path"] == source_manifest_artifacts[source_id]["path"]
        assert source["artifact_manifest"]["load"] == "query_planned"
    for source_manifest, proof_catalog in zip(source_manifests, proof_catalogs, strict=True):
        assert "full_shards" not in source_manifest
        assert proof_catalog["source_id"] == source_manifest["source_id"]
        assert {"pending", "failed"} <= set(proof_catalog["complete_requires_no_states"])
        assert proof_catalog["shards"]

    query_directory = read_artifact(manifest["artifacts"]["global_query_directory"])
    assert query_directory["entry_count"] == len(query_directory["entries"])
    assert query_directory["fallback"]["mode"] == "cost_sort_authority_manifests_then_proof_ledger_verify"
    assert not {"doc_index", "postings", "documents"} & set(walk_keys(query_directory))


def test_source_truth_counts_are_preserved():
    manifest = read_json(PUBLIC_INDEX_DIR / "manifest.json")
    truth_counts = manifest["sitegraph"]["truth_counts"]
    source_registry = load_source_registry(manifest)
    source_entries = {item["source_id"]: item for item in source_registry["sources"]}
    source_manifests = {item["source_id"]: item for item in load_source_manifests(manifest)}
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
        assert source_manifests[source_id]["doc_count"] == source_entries[source_id]["doc_count"]
        assert source_manifests[source_id]["attachment_count"] == source_entries[source_id]["attachment_count"]
    for field, value in expected_totals.items():
        assert truth_counts[field] == value
    assert manifest["sitegraph"]["detail_page_records"] == truth_counts["detail_pages"]
    assert manifest["sitegraph"]["attachment_metadata_records"] == truth_counts["attachments"]
    assert manifest["sitegraph"]["external_link_records"] == truth_counts["external_links"]
    assert manifest["sitegraph"]["quality"]["errors"] == 0
    assert manifest["sitegraph"]["quality"]["all_discovered_urls_have_outcomes"] is True
    assert manifest["sitegraph"]["quality"]["attachment_policy"] == "metadata_only"
    assert manifest["sitegraph"]["attachment_evidence_policy"] == "metadata_and_filename_only_no_extracted_attachment_content"
    assert manifest["sitegraph"]["attachment_evidence_coverage"]["total"] == truth_counts["attachments"]
    assert manifest["sitegraph"]["attachment_evidence_coverage"]["filename_only"] == truth_counts["attachments"]
    assert manifest["sitegraph"]["attachment_evidence_coverage"]["text_extracted"] == 0
    assert manifest["sitegraph"]["attachment_evidence_coverage"]["snippet"] == 0
    assert manifest["sitegraph"]["attachment_evidence_coverage"]["full_content"] == 0
    assert manifest["sitegraph"]["quality"]["external_link_policy"] == "record_only"


def test_light_index_and_shards_have_no_obsolete_fields():
    manifest = read_json(PUBLIC_INDEX_DIR / "manifest.json")
    for source_manifest in load_source_manifests(manifest):
        assert source_manifest["source_id"] in EXPECTED_SOURCE_IDS
        assert source_manifest["local_indexes"]
        for ref in source_manifest["local_indexes"]:
            assert ref["scope"]["source_id"] == source_manifest["source_id"]
            assert ref["index_id"] == ref["scope"]["index_id"]
            assert {item["shard_id"] for item in ref["shards"]} == set(ref["scope"]["shard_ids"])
            for shard_ref in ref["shards"]:
                assert shard_ref["path"].startswith("generated/collections/njupt-public/sitegraph/full_shards/")
                assert shard_ref["bytes"] > 0
                assert shard_ref["count"] > 0
            light_meta_index = read_json(PUBLIC_ROOT / ref["light_index_meta"]["path"])
            packed_light_index = unpack_impact_index((PUBLIC_ROOT / ref["light_index_packed"]["path"]).read_bytes())
            light_index = {**light_meta_index, "terms": packed_light_index.get("terms")}
            body_index = read_json(PUBLIC_ROOT / ref["body_index"]["path"])
            packed_body_index = unpack_impact_index((PUBLIC_ROOT / ref["body_index_packed"]["path"]).read_bytes())
            assert "light_index" not in ref
            assert light_index["scope"] == ref["scope"]
            assert light_meta_index["scope"] == ref["scope"]
            assert packed_light_index["scope"] == ref["scope"]
            assert body_index["scope"] == ref["scope"]
            assert packed_body_index["scope"] == ref["scope"]
            assert set(light_index["field_codes"].values()) <= {"t", "s", "n", "g", "a", "e", "y"}
            assert set(body_index["field_codes"].values()) == {"m", "c"}
            assert "tokens" not in light_index
            assert "tokens" not in body_index
            assert light_index["scoring_model"] == "impact-ordered-block-max-bm25f-lite-v2"
            assert body_index["scoring_model"] == "impact-ordered-block-max-bm25f-lite-v2"
            assert isinstance(light_index["terms"], dict)
            assert isinstance(body_index["terms"], dict)
            assert "terms" not in light_meta_index
            assert "documents" not in packed_light_index
            assert packed_body_index["terms"] == body_index["terms"]
            assert len(light_index["documents"]) == ref["doc_count"]
            assert not (BANNED_KEYS & set(walk_keys(light_index)))
            for item in light_index["documents"]:
                assert "content" not in item
                assert "summary" not in item
                assert "attachments" not in item
                assert "provenance" not in item
                assert item.get("source_id") == source_manifest["source_id"]
                assert item.get("date_kind")
                assert item.get("task_kind")

        proof_catalog = read_artifact(source_manifest["artifacts"]["proof_catalog"])
        for shard in proof_catalog["shards"]:
            documents = read_json(PUBLIC_ROOT / shard["path"])
            assert len(documents) == shard["document_count"]
            assert not (BANNED_KEYS & set(walk_keys(documents)))
            assert ".000." not in shard["path"]
            assert "\\" not in shard["path"]
            assert shard["source_id"] == source_manifest["source_id"]
            assert shard["filter_contract"]["filter_token_count"] > 0
            assert shard["filter_contract"]["filter_sha256"]
            for document in documents:
                assert set(["title", "url", "section", "nav_path", "summary", "content", "attachments", "record_type", "facet", "published_at", "provenance", "source_id", "canonical_title", "date_kind", "date_confidence", "task_kind", "authority_profile", "dedupe_key"]) <= set(document)
                assert document["source_id"] == document["provenance"]["site_id"]
                for attachment in document.get("attachments", []):
                    assert attachment["metadata_only"] is True
                    assert attachment["evidence_level"] == "filename_only"
                    assert {"metadata_only", "filename_only"} <= set(attachment.get("available_evidence", ["metadata_only", "filename_only"]))
                    assert {"text_extracted", "snippet", "full_content"} <= set(attachment.get("unavailable_evidence", ["text_extracted", "snippet", "full_content"]))
                    assert attachment["text_extracted"] is False
                    assert attachment["snippet_available"] is False
                    assert attachment["full_content_available"] is False
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
