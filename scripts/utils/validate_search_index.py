import json
import os
import sys
from datetime import datetime
from urllib.parse import urlparse

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from config.indexer_config import BASE_DIR, CAMPUS_SOURCE_CONFIG_PATH, DOCUMENTS_PATH, MANIFEST_PATH
from core.llm_scorer import BatchLLMResult, LLMResult
from models.semantic_model import SEARCH_DOMAINS, SEARCH_INTENTS, SEARCH_LIFECYCLES, SEARCH_SOURCE_TYPES


REQUIRED_DOCUMENT_FIELDS = {
    "id",
    "kind",
    "title",
    "url",
    "source",
    "source_domain",
    "source_type",
    "category",
    "domain",
    "intent",
    "lifecycle",
    "audience",
    "published_at",
    "content",
    "attachments",
    "student_score",
    "freshness_score",
    "importance_score",
    "tags",
    "hash",
}


def read_json(path: str):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def fail(message: str) -> None:
    print(f"[validate_search_index] {message}", file=sys.stderr)
    raise SystemExit(1)


def validate_campus_sources() -> None:
    payload = read_json(CAMPUS_SOURCE_CONFIG_PATH)
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        fail("config/campus_sources.json must contain a non-empty sources array")

    seen: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            fail(f"campus source #{index} is not an object")
        source_id = str(source.get("id", "")).strip()
        if not source_id:
            fail(f"campus source #{index} has no id")
        if source_id in seen:
            fail(f"duplicate campus source id: {source_id}")
        seen.add(source_id)

        for field in ("name", "base_url", "list_urls", "source_type", "priority", "audience_hint", "adapter_kind"):
            if field not in source:
                fail(f"campus source {source_id} missing field {field}")

        parsed = urlparse(str(source["base_url"]))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            fail(f"campus source {source_id} has invalid base_url")
        if source["source_type"] not in SEARCH_SOURCE_TYPES:
            fail(f"campus source {source_id} has invalid source_type {source['source_type']}")
        if not isinstance(source["list_urls"], list) or not source["list_urls"]:
            fail(f"campus source {source_id} must have at least one list_url")
        if not isinstance(source["audience_hint"], list) or not source["audience_hint"]:
            fail(f"campus source {source_id} must have audience_hint")


def validate_llm_fixture() -> None:
    fixture = {
        "is_student_facing": True,
        "student_relevance": 0.92,
        "audience": ["本科生"],
        "category": "项目",
        "domain": "international",
        "intent": "apply",
        "sub_category": "海外交流",
        "tags": ["海外交流", "报名"],
        "importance_score": 0.88,
        "deadline": "2026-04-23T12:00:00+08:00",
        "action_required": True,
        "action_type": "报名",
        "action_summary": "学生需在截止前提交申请材料。",
        "required_materials": ["申请表"],
        "student_summary": "本科生可报名海外交流项目。",
        "sensitive": False,
        "sensitive_types": [],
        "attachment_roles": [],
        "risk_flags": [],
        "evidence": ["需在截止前提交申请材料。"],
        "confidence": 0.86,
        "review_required": False,
    }
    LLMResult.model_validate(fixture)
    BatchLLMResult.model_validate({"results": [{"id": "fixture-1", **fixture}]})


def validate_documents() -> None:
    if not os.path.exists(DOCUMENTS_PATH):
        fail("public/index/documents.json does not exist")

    documents = read_json(DOCUMENTS_PATH)
    if not isinstance(documents, list):
        fail("documents.json must be an array")

    seen: set[str] = set()
    for document in documents:
        if not isinstance(document, dict):
            fail("documents.json contains a non-object item")
        missing = REQUIRED_DOCUMENT_FIELDS.difference(document)
        if missing:
            fail(f"document {document.get('id', '<unknown>')} missing fields: {sorted(missing)}")
        doc_id = str(document["id"])
        if doc_id in seen:
            fail(f"duplicate document id: {doc_id}")
        seen.add(doc_id)
        if document["domain"] not in SEARCH_DOMAINS:
            fail(f"document {doc_id} has invalid domain {document['domain']}")
        if document["intent"] not in SEARCH_INTENTS:
            fail(f"document {doc_id} has invalid intent {document['intent']}")
        if document["source_type"] not in SEARCH_SOURCE_TYPES:
            fail(f"document {doc_id} has invalid source_type {document['source_type']}")
        if document["lifecycle"] not in SEARCH_LIFECYCLES:
            fail(f"document {doc_id} has invalid lifecycle {document['lifecycle']}")
        for field in ("student_score", "freshness_score", "importance_score"):
            value = document[field]
            if not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
                fail(f"document {doc_id} has invalid {field}: {value}")
        for date_field in ("published_at", "deadline"):
            value = document.get(date_field)
            if value:
                try:
                    datetime.fromisoformat(str(value))
                except ValueError:
                    fail(f"document {doc_id} has invalid {date_field}: {value}")


def validate_manifest() -> None:
    if not os.path.exists(MANIFEST_PATH):
        fail("public/index/manifest.json does not exist")
    manifest = read_json(MANIFEST_PATH)
    if not isinstance(manifest, dict):
        fail("manifest.json must be an object")
    if manifest.get("total_documents") is None or int(manifest.get("total_documents", 0)) <= 0:
        fail("manifest has no documents")
    if not manifest.get("llm_schema_version"):
        fail("manifest missing llm_schema_version")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        fail("manifest has no sources")


def main() -> None:
    os.chdir(BASE_DIR)
    validate_campus_sources()
    validate_llm_fixture()
    validate_documents()
    validate_manifest()
    print("[validate_search_index] ok")


if __name__ == "__main__":
    main()
