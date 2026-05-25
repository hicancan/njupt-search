import json
import os
import sys
from datetime import datetime

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from config.indexer_config import (
    BASE_DIR,
    DOCUMENTS_PATH,
    MANIFEST_PATH,
    SOURCE_CHANNEL_CONFIG_PATH,
    QUERY_ALIASES_PATH,
    ONTOLOGY_PATH,
)
from core.llm_scorer import BatchLLMResult, LLMRawResult
from models.search_contract import (
    SEARCH_CATEGORIES,
    SEARCH_DOCUMENT_KINDS,
    SEARCH_DOMAINS,
    SEARCH_INTENTS,
    SEARCH_LIFECYCLES,
    SEARCH_SEMANTIC_MODES,
    SEARCH_SOURCE_TYPES,
    TASK_FRAME_SOURCE_MODES,
    TASK_TYPES,
)


REQUIRED_DOCUMENT_FIELDS = {
    "id",
    "kind",
    "source_id",
    "channel_id",
    "channel",
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
    "tags",
    "hash",
    "canonical",
    "rule_guard",
    "task_frames",
    "semantic_pipeline_version",
    "raw_field_presence",
}
TASK_FRAMES_PATH = os.path.join(BASE_DIR, "public", "index", "task_frames.json")
PUBLIC_QUERY_ALIASES_PATH = os.path.join(BASE_DIR, "public", "index", "query_aliases.json")
PUBLIC_ONTOLOGY_PATH = os.path.join(BASE_DIR, "public", "index", "ontology.json")

MIN_EXPECTED_DOCUMENTS = 120
MIN_SOURCE_COUNT = 30
MIN_CHANNEL_COUNT = 60
MIN_PRODUCTION_CHANNEL_COUNT = 50
MAX_ERROR_SOURCE_RATIO = 0.1
MAX_ERROR_SOURCES = 3
CORE_SOURCE_IDS = {"jwc", "xsc", "pg", "ygb", "youth", "cxcy", "job", "lib"}


def read_json(path: str):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def fail(message: str) -> None:
    print(f"[validate_search_index] {message}", file=sys.stderr)
    raise SystemExit(1)


def contract_error(path: str, item_id: str, field: str, value: object, allowed: tuple[str, ...]) -> str:
    return (
        f"{path} item {item_id} invalid {field}={value!r}; "
        f"allowed values: {', '.join(allowed)}"
    )


def validate_contract_value(path: str, item_id: str, field: str, value: object, allowed: tuple[str, ...]) -> None:
    if str(value or "") not in allowed:
        fail(contract_error(path, item_id, field, value, allowed))


def validate_source_channels() -> None:
    payload = read_json(SOURCE_CHANNEL_CONFIG_PATH)
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        fail("config/source_channels.json must contain sources")
    source_ids: set[str] = set()
    channel_ids: set[str] = set()
    production_channel_count = 0
    for source in sources:
        if not isinstance(source, dict):
            fail("source_channels contains non-object source")
        source_id = str(source.get("id", "")).strip()
        if not source_id:
            fail("source_channels source missing id")
        if source_id in source_ids:
            fail(f"duplicate source_channels source id: {source_id}")
        source_ids.add(source_id)
        channels = source.get("channels")
        if not isinstance(channels, list) or not channels:
            fail(f"source {source_id} must contain at least one channel")
        for channel in channels:
            if not isinstance(channel, dict):
                fail(f"source {source_id} contains non-object channel")
            channel_id = str(channel.get("id", "")).strip()
            if not channel_id:
                fail(f"source {source_id} channel missing id")
            if channel_id in channel_ids:
                fail(f"duplicate channel id: {channel_id}")
            channel_ids.add(channel_id)
            if channel.get("source_id") != source_id:
                fail(f"channel {channel_id} source_id does not match source {source_id}")
            if not isinstance(channel.get("list_urls"), list) or not channel["list_urls"]:
                fail(f"channel {channel_id} must have list_urls")
            if bool(channel.get("production_enabled", True)):
                production_channel_count += 1
    if len(source_ids) < MIN_SOURCE_COUNT:
        fail(f"source_channels source_count {len(source_ids)} < {MIN_SOURCE_COUNT}")
    if len(channel_ids) < MIN_CHANNEL_COUNT:
        fail(f"source_channels channel_count {len(channel_ids)} < {MIN_CHANNEL_COUNT}")
    if production_channel_count < MIN_PRODUCTION_CHANNEL_COUNT:
        fail(f"source_channels production_channel_count {production_channel_count} < {MIN_PRODUCTION_CHANNEL_COUNT}")


def validate_llm_fixture() -> None:
    fixture = {
        "audience": ["本科生"],
        "category": "项目",
        "domain": "international",
        "intent": "apply",
        "sub_category": "海外交流",
        "tags": ["海外交流", "报名"],
        "deadline": "2026-04-23T12:00:00+08:00",
        "action_required": True,
        "action_type": "报名",
        "action_summary": "学生需在截止前提交申请材料。",
        "required_materials": ["申请表"],
        "student_summary": "本科生可报名海外交流项目。",
        "sensitive": False,
        "sensitive_types": [],
        "attachment_roles": [],
        "task_frames": [],
        "risk_flags": [],
        "evidence": ["需在截止前提交申请材料。"],
        "confidence": 0.86,
        "review_required": False,
    }
    LLMRawResult.model_validate(fixture)
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
        validate_contract_value(DOCUMENTS_PATH, doc_id, "kind", document["kind"], SEARCH_DOCUMENT_KINDS)
        validate_contract_value(DOCUMENTS_PATH, doc_id, "category", document["category"], SEARCH_CATEGORIES)
        validate_contract_value(DOCUMENTS_PATH, doc_id, "domain", document["domain"], SEARCH_DOMAINS)
        validate_contract_value(DOCUMENTS_PATH, doc_id, "intent", document["intent"], SEARCH_INTENTS)
        validate_contract_value(DOCUMENTS_PATH, doc_id, "source_type", document["source_type"], SEARCH_SOURCE_TYPES)
        validate_contract_value(DOCUMENTS_PATH, doc_id, "lifecycle", document["lifecycle"], SEARCH_LIFECYCLES)
        if document.get("semantic_mode") is not None:
            validate_contract_value(DOCUMENTS_PATH, doc_id, "semantic_mode", document["semantic_mode"], SEARCH_SEMANTIC_MODES)
        if not isinstance(document.get("canonical"), dict):
            fail(f"document {doc_id} has invalid canonical object")
        if not isinstance(document.get("rule_guard"), dict):
            fail(f"document {doc_id} has invalid rule_guard object")
        if not isinstance(document.get("task_frames"), list):
            fail(f"document {doc_id} has invalid task_frames")
        if document.get("status") == "restricted":
            if document.get("action_required"):
                fail(f"restricted document {doc_id} must not require action")
            if document.get("task_frames"):
                fail(f"restricted document {doc_id} must not have task_frames")
        rule_guard = document.get("rule_guard") if isinstance(document.get("rule_guard"), dict) else {}
        if (
            rule_guard.get("restricted")
            or rule_guard.get("sensitive")
            or rule_guard.get("low_evidence")
            or rule_guard.get("allow_llm") is False
        ) and document.get("task_frames"):
            fail(f"guarded document {doc_id} must not have task_frames")
        if document.get("notice_card") is not None and not isinstance(document.get("notice_card"), dict):
            fail(f"document {doc_id} has invalid notice_card")
        if document.get("typed_search_terms") is not None and not isinstance(document.get("typed_search_terms"), list):
            fail(f"document {doc_id} has invalid typed_search_terms")
        if document.get("synonyms") is not None and not isinstance(document.get("synonyms"), list):
            fail(f"document {doc_id} has invalid synonyms")
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
    total_documents = int(manifest.get("total_documents", 0) or 0)
    if total_documents <= 0:
        fail("manifest has no documents")
    if total_documents < MIN_EXPECTED_DOCUMENTS:
        fail(f"manifest has suspiciously few documents: {total_documents} < {MIN_EXPECTED_DOCUMENTS}")
    if not manifest.get("llm_schema_version"):
        fail("manifest missing llm_schema_version")
    for field in (
        "source_count",
        "channel_count",
        "audited_channel_count",
        "production_channel_count",
        "failed_channel_count",
        "task_frame_count",
        "documents_with_task_frame",
        "evidence_coverage",
        "review_required_count",
        "low_evidence_count",
    ):
        if field not in manifest:
            fail(f"manifest missing {field}")
    if int(manifest.get("source_count", 0) or 0) < MIN_SOURCE_COUNT:
        fail(f"manifest source_count {manifest.get('source_count')} < {MIN_SOURCE_COUNT}")
    if int(manifest.get("channel_count", 0) or 0) < MIN_CHANNEL_COUNT:
        fail(f"manifest channel_count {manifest.get('channel_count')} < {MIN_CHANNEL_COUNT}")
    if int(manifest.get("production_channel_count", 0) or 0) < MIN_PRODUCTION_CHANNEL_COUNT:
        fail(f"manifest production_channel_count {manifest.get('production_channel_count')} < {MIN_PRODUCTION_CHANNEL_COUNT}")
    if int(manifest.get("channel_count", 0) or 0) <= int(manifest.get("source_count", 0) or 0):
        fail("manifest channel_count must be greater than source_count")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        fail("manifest has no sources")
    error_sources = [source for source in sources if isinstance(source, dict) and source.get("status") == "error"]
    error_limit = max(MAX_ERROR_SOURCES, int(len(sources) * MAX_ERROR_SOURCE_RATIO))
    if len(error_sources) > error_limit:
        fail(f"too many source errors: {len(error_sources)} > {error_limit}")
    broken_core_sources = [
        str(source.get("id"))
        for source in error_sources
        if str(source.get("id")) in CORE_SOURCE_IDS
    ]
    if broken_core_sources:
        fail(f"core sources failed: {', '.join(sorted(broken_core_sources))}")

    # Coverage Gate
    critical_channels = {
        "jwc_exam", "jwc_degree", "jwc_transfer", "jwc_recommendation",
        "xsc_scholarship", "xsc_subsidy", "pg_degree", "pg_graduation"
    }
    critical_sources = {
        "hqc", "lib", "xxb", "archives"
    }
    
    channels_info = []
    for src in manifest.get("sources", []):
        for ch in src.get("channels", []):
            ch["source_id"] = src.get("id")
            channels_info.append(ch)
    
    source_docs = {s: 0 for s in critical_sources}
    channel_docs = {c: 0 for c in critical_channels}
    
    for ch in channels_info:
        ch_id = ch.get("id")
        src_id = ch.get("source_id")
        status = ch.get("status")
        docs = int(ch.get("documents", 0) or 0)
        cands = int(ch.get("candidates", 0) or 0)
        
        if cands > 0 and docs == 0:
            if status not in ("ok_no_recent_docs", "warning", "error", "ok_no_relevant_docs", "warning_filtered_all", "warning_selector_issue", "error_fetch_failed"):
                fail(f"Channel {ch_id} has {cands} candidates but 0 documents, missing valid reason. Status: {status}")
                
        if ch_id in channel_docs:
            channel_docs[ch_id] += docs
            if docs == 0 and status not in ("ok_no_recent_docs", "warning", "error", "ok_no_relevant_docs", "warning_filtered_all", "warning_selector_issue", "error_fetch_failed"):
                fail(f"Critical channel {ch_id} has 0 documents and no valid fallback status. Current status: {status}")
                
        if src_id in source_docs:
            source_docs[src_id] += docs
            
    for s_id, count in source_docs.items():
        if count == 0:
            has_valid_status = any(
                ch.get("status") in ("ok_no_recent_docs", "warning", "error", "ok_no_relevant_docs", "warning_filtered_all") 
                for ch in channels_info if ch.get("source_id") == s_id
            )
            if not has_valid_status:
                fail(f"Critical source {s_id} has 0 documents across all channels and no valid fallback status.")


def validate_task_frames_and_public_terms() -> None:
    for path in (TASK_FRAMES_PATH, PUBLIC_QUERY_ALIASES_PATH, PUBLIC_ONTOLOGY_PATH):
        if not os.path.exists(path):
            fail(f"required public index artifact missing: {path}")
    task_frames = read_json(TASK_FRAMES_PATH)
    if not isinstance(task_frames, list):
        fail("task_frames.json must be a list")
    for frame in task_frames:
        if not isinstance(frame, dict):
            fail("task_frames.json contains non-object frame")
        for field in ("task_id", "doc_id", "task_type", "who", "what", "action", "time", "source", "evidence", "risk"):
            if field not in frame:
                fail(f"task frame missing field {field}")
        frame_id = str(frame.get("task_id") or frame.get("doc_id") or "<unknown>")
        validate_contract_value(TASK_FRAMES_PATH, frame_id, "source_mode", frame.get("source_mode"), TASK_FRAME_SOURCE_MODES)
        validate_contract_value(TASK_FRAMES_PATH, frame_id, "task_type", frame.get("task_type"), TASK_TYPES)
        time_payload = frame.get("time") if isinstance(frame.get("time"), dict) else {}
        validate_contract_value(TASK_FRAMES_PATH, frame_id, "time.lifecycle", time_payload.get("lifecycle"), SEARCH_LIFECYCLES)

def main() -> None:
    os.chdir(BASE_DIR)
    validate_source_channels()
    validate_llm_fixture()
    validate_documents()
    validate_manifest()
    validate_task_frames_and_public_terms()
    print("[validate_search_index] ok")


if __name__ == "__main__":
    main()
