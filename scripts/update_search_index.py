import argparse
import base64
import fnmatch
import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Any
from urllib.parse import quote, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from config.indexer_config import (
    BASE_DIR, PUBLIC_DIR, INDEX_DIR, DOCUMENTS_PATH, MANIFEST_PATH, GITHUB_SOURCE_CONFIG_PATH,
    LLM_CACHE_PATH, QUERY_ALIASES_PATH, ONTOLOGY_PATH, SOURCE_CHANNEL_CONFIG_PATH,
    BEIJING_TZ, HEADERS, MAX_DOCS_PER_SOURCE, DETAIL_FETCH_LIMIT_PER_SOURCE, REQUEST_TIMEOUT,
    MIN_STUDENT_SCORE, GITHUB_TOKEN_ENV, GITHUB_API_BASE, GITHUB_FILE_SIZE_LIMIT_BYTES,
    NEGATIVE_KEYWORDS, SourceConfig, GitHubSourceConfig, SOURCES,
    ChannelConfig, JOB_API_BASE, JOB_STATION_CODE, CATEGORY_KEYWORDS,
    NAV_TITLES, STATIC_EXTENSIONS, ATTACHMENT_EXTENSIONS, POSITIVE_KEYWORDS,
    clean_env_value,
)
from core.llm_scorer import (
    LLM_BATCH_MAX_CHARS, LLM_BATCH_MAX_DOCS, LLM_BATCH_MAX_OUTPUT_TOKENS,
    LLM_SCHEMA_VERSION, active_model_name, active_provider_name,
    analyze_documents_batch_with_llm, llm_enabled, public_llm_result, split_llm_batches,
)

_DOC_CACHE: dict[str, dict[str, Any]] = {}
_LLM_CACHE: dict[str, dict[str, Any]] = {}
_LLM_CACHE_CHANGED = False
_RUN_CONFIG: dict[str, Any] = {
    "force_llm": False,
    "no_llm": False,
    "llm_schema_version": LLM_SCHEMA_VERSION,
    "source_filter": set(),
    "llm_limit": None,
    "dry_run": False,
    "no_github": False,
    "llm_provider": "auto",
    "llm_batch_size": LLM_BATCH_MAX_DOCS,
    "llm_batch_max_chars": LLM_BATCH_MAX_CHARS,
    "llm_batch_max_output_tokens": LLM_BATCH_MAX_OUTPUT_TOKENS,
}
_RUN_STATS: dict[str, int] = {
    "cache_reused": 0,
    "llm_reused": 0,
    "llm_attempted": 0,
    "llm_reprocessed": 0,
    "llm_failed": 0,
    "llm_fallback": 0,
    "llm_skipped_by_limit": 0,
    "llm_batches_attempted": 0,
    "llm_batch_docs_attempted": 0,
    "candidate_llm_cache_reused": 0,
    "restricted": 0,
}
from core.heuristics import (
    RESTRICTED_TEXT_PATTERNS, ACTION_KEYWORDS, SENSITIVE_PATTERNS, SENSITIVE_MATERIAL_PATTERNS,
    clean_text, parse_date, is_expired, is_restricted_content, parse_deadline_candidate,
    infer_deadline, infer_action, infer_attachment_role, enrich_attachment_metadata,
    detect_sensitive_info, is_low_evidence_content, metadata_only_summary
)
from models.semantic_model import (
    derive_display_category, extract_evidence, infer_domain, infer_intent, infer_lifecycle,
    normalize_domain, normalize_intent, normalize_source_type
)
from models.canonical_document import RawDocument, canonicalize_raw_document
from models.source_graph import load_source_channel_graph
from core.rule_guard import evaluate_rule_guard, restricted_summary
from core.task_extractor import extract_task_frames
from core.semantic_verifier import verify_search_document

SOURCE_PRIORITY = {
    "本科生院 / 教务处": 1.0,
    "研究生院": 0.98,
    "学生工作处": 0.96,
    "研究生工作部": 0.94,
    "创新创业教育学院": 0.92,
    "团委 / 青春南邮": 0.88,
    "就业信息网": 0.86,
    "图书馆": 0.78,
    "保卫处": 0.72,
    "后勤管理处": 0.72,
}

TASK_FRAMES_PATH = os.path.join(INDEX_DIR, "task_frames.json")
PUBLIC_QUERY_ALIASES_PATH = os.path.join(INDEX_DIR, "query_aliases.json")
PUBLIC_ONTOLOGY_PATH = os.path.join(INDEX_DIR, "ontology.json")
SEMANTIC_FIELDS_TO_TRACK = [
    "category",
    "domain",
    "intent",
    "deadline",
    "action_required",
    "action_summary",
    "required_materials",
    "summary",
    "evidence",
    "sensitive",
    "review_required",
    "task_frames",
]


def read_json_file(path: str, fallback: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return fallback

def load_document_cache() -> None:
    global _DOC_CACHE
    if os.path.exists(DOCUMENTS_PATH):
        try:
            with open(DOCUMENTS_PATH, "r", encoding="utf-8") as f:
                docs = json.load(f)
                for doc in docs:
                    if "hash" in doc:
                        _DOC_CACHE[doc["hash"]] = doc
                    if "cache_key" in doc:
                        _DOC_CACHE[doc["cache_key"]] = doc
        except Exception:
            pass


def load_llm_cache() -> None:
    global _LLM_CACHE
    if not os.path.exists(LLM_CACHE_PATH):
        return
    try:
        with open(LLM_CACHE_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        entries = payload.get("entries", {}) if isinstance(payload, dict) else {}
        if isinstance(entries, dict):
            _LLM_CACHE = {str(key): value for key, value in entries.items() if isinstance(value, dict)}
    except Exception:
        _LLM_CACHE = {}


def save_llm_cache(now: datetime) -> bool:
    if not _LLM_CACHE_CHANGED or _RUN_CONFIG["dry_run"]:
        return False
    os.makedirs(os.path.dirname(LLM_CACHE_PATH), exist_ok=True)
    
    # Merge with existing cache to prevent overwriting concurrent updates
    try:
        if os.path.exists(LLM_CACHE_PATH):
            with open(LLM_CACHE_PATH, "r", encoding="utf-8") as f:
                existing_payload = json.load(f)
            existing_entries = existing_payload.get("entries", {})
            if isinstance(existing_entries, dict):
                existing_entries.update(_LLM_CACHE)
                _LLM_CACHE.clear()
                _LLM_CACHE.update(existing_entries)
    except Exception:
        pass

    payload = {
        "schema_version": active_llm_schema_version(),
        "updated_at": now.isoformat(),
        "entries": _LLM_CACHE,
    }
    return write_json_if_changed(LLM_CACHE_PATH, payload)



def get_beijing_time() -> datetime:
    return datetime.now(timezone.utc).astimezone(BEIJING_TZ)





def clamp01(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def cache_is_current(cached: dict[str, Any] | None) -> bool:
    if not cached:
        return False
    if _RUN_CONFIG["force_llm"] and not _RUN_CONFIG["no_llm"]:
        return False
    from core.semantic_pipeline import SEMANTIC_PIPELINE_VERSION
    if cached.get("semantic_pipeline_version") != SEMANTIC_PIPELINE_VERSION:
        return False
    if cached.get("llm_schema_version") != active_llm_schema_version():
        return False
    if cache_needs_reprocessing(cached):
        return False
    if cached.get("status") == "restricted":
        return True
    llm_meta = cached.get("llm") if isinstance(cached.get("llm"), dict) else {}
    if _RUN_CONFIG["no_llm"] and llm_meta.get("used"):
        return False
    if runtime_llm_enabled() and not llm_meta.get("used"):
        return False
    if runtime_llm_enabled() and llm_meta.get("used"):
        cached_provider = llm_meta.get("provider")
        cached_model = llm_meta.get("model")
        if cached_provider and cached_provider != runtime_llm_provider_name():
            return False
        if cached_model and cached_model != runtime_llm_model_name():
            return False
    return True


def cache_needs_reprocessing(cached: dict[str, Any]) -> bool:
    sensitive_types = {str(item) for item in cached.get("sensitive_types", [])}
    if cached.get("sensitive") and sensitive_types and sensitive_types.issubset(set(SENSITIVE_MATERIAL_PATTERNS)):
        return True
    return False


def cached_with_freshness(cached: dict[str, Any], published_at: str | None, now: datetime) -> dict[str, Any]:
    _RUN_STATS["cache_reused"] += 1
    llm_meta = cached.get("llm") if isinstance(cached.get("llm"), dict) else {}
    if llm_meta.get("used"):
        _RUN_STATS["llm_reused"] += 1
    return dict(cached)


def cached_documents_for_source_id(id_prefix: str) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for document in _DOC_CACHE.values():
        doc_id = str(document.get("id", ""))
        if doc_id.startswith(id_prefix):
            unique[doc_id] = document
    return list(unique.values())


def active_llm_schema_version() -> str:
    return str(_RUN_CONFIG.get("llm_schema_version") or LLM_SCHEMA_VERSION)


def runtime_llm_enabled() -> bool:
    return bool(not _RUN_CONFIG["no_llm"] and llm_enabled(runtime_llm_provider()))


def runtime_llm_provider() -> str:
    return str(_RUN_CONFIG.get("llm_provider") or "auto")


def runtime_llm_provider_name() -> str:
    return active_provider_name(runtime_llm_provider()) if runtime_llm_enabled() else "none"


def runtime_llm_model_name() -> str | None:
    return active_model_name(runtime_llm_provider()) if runtime_llm_enabled() else None


def effective_llm_batch_size() -> int:
    configured = int(_RUN_CONFIG["llm_batch_size"])
    if runtime_llm_provider_name() == "gemini":
        return min(configured, int(os.environ.get("GEMINI_BATCH_MAX_DOCS", "6")))
    return configured


def effective_llm_batch_max_output_tokens() -> int:
    configured = int(_RUN_CONFIG["llm_batch_max_output_tokens"])
    if runtime_llm_provider_name() == "gemini":
        return min(configured, int(os.environ.get("GEMINI_BATCH_MAX_OUTPUT_TOKENS", "8192")))
    return configured


def source_selected(source_id: str) -> bool:
    filters = _RUN_CONFIG.get("source_filter") or set()
    return not filters or source_id in filters


def llm_cache_key(source_id: str, url: str, content: str, attachments: list[dict[str, Any]]) -> str:
    attachment_digest = document_hash(attachments)
    content_digest = document_hash(content)
    provider_name = runtime_llm_provider_name()
    model_name = runtime_llm_model_name() or "rule"
    from core.semantic_pipeline import SEMANTIC_PIPELINE_VERSION
    return document_hash(
        source_id,
        normalize_url(url),
        content_digest,
        attachment_digest,
        active_llm_schema_version(),
        provider_name,
        model_name,
        SEMANTIC_PIPELINE_VERSION,
    )


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path, "", parsed.query, ""))


def same_domain(url: str, source: SourceConfig) -> bool:
    host = urlparse(url).netloc.lower()
    source_host = urlparse(source.base_url).netloc.lower()
    return host == source_host or host.endswith("." + source_host)


def extension_from_url(url: str) -> str:
    return os.path.splitext(urlparse(url).path.lower())[1]


def document_hash(*parts: Any) -> str:
    serialized = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:20]


def contains_relevant_keyword(text: str) -> bool:
    lowered = text.lower()
    all_keywords = POSITIVE_KEYWORDS + [keyword for keywords in CATEGORY_KEYWORDS.values() for keyword in keywords]
    return any(keyword.lower() in lowered for keyword in all_keywords)


def looks_like_notice_link(title: str, parent_text: str, url: str, now: datetime) -> bool:
    stripped_title = title.strip()
    lowered_title = stripped_title.lower()
    path = urlparse(url).path.lower()

    if stripped_title in NAV_TITLES or lowered_title in NAV_TITLES:
        return False
    if path.endswith("/main.htm") or path.endswith("main.htm") or path.endswith("list.htm"):
        return False
    if len(stripped_title) < 6:
        return False

    combined = f"{stripped_title} {parent_text} {url}"
    has_date = parse_date(combined, now) is not None
    has_detail_shape = bool(re.search(r"/20\d{2}/\d{4}/", path)) or path.endswith("page.htm")
    has_relevant_keyword = contains_relevant_keyword(combined)

    return has_detail_shape or (has_date and has_relevant_keyword)


def matches_source_patterns(url: str, title: str, source: SourceConfig) -> bool:
    values = (url, urlparse(url).path, title, f"{url} {title}")
    if source.include_patterns:
        include_hit = any(fnmatch.fnmatch(value, pattern) for pattern in source.include_patterns for value in values)
        if not include_hit:
            return False
    if source.exclude_patterns:
        exclude_hit = any(fnmatch.fnmatch(value, pattern) for pattern in source.exclude_patterns for value in values)
        if exclude_hit:
            return False
    return True


def discover_next_list_urls(soup: BeautifulSoup, list_url: str, source: SourceConfig) -> list[str]:
    urls: list[str] = []
    for anchor in soup.find_all("a"):
        text = clean_text(anchor.get_text(" ", strip=True))
        if "下一页" not in text:
            continue
        href = anchor.get("href")
        if not href:
            continue
        absolute_url = normalize_url(urljoin(list_url, href))
        if same_domain(absolute_url, source):
            urls.append(absolute_url)
    return urls


def request_verify_for(source: SourceConfig | None = None) -> bool:
    return not bool(source and source.allow_insecure_tls)


def fetch_html(url: str, source: SourceConfig | None = None) -> str:
    response = requests.get(url, headers=HEADERS, verify=request_verify_for(source), timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def post_json(url: str, body: dict[str, Any], source: SourceConfig | None = None) -> dict[str, Any]:
    response = requests.post(url, json=body, headers=HEADERS, verify=request_verify_for(source), timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def normalize_title_for_dedupe(title: str) -> str:
    normalized = re.sub(r"^【[^】]+】", "", title)
    normalized = re.sub(r"^(关于|南京邮电大学)", "", normalized)
    normalized = re.sub(r"[，,。；;：:\s\"“”'‘’（）()《》<>·\-—_]+", "", normalized)
    return normalized.lower()


def llm_metadata(
    used: bool,
    confidence: float | None = None,
    review_required: bool = False,
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    return {
        "used": used,
        "provider": provider if used else None,
        "model": model or (runtime_llm_model_name() if used else None),
        "prompt_version": active_llm_schema_version(),
        "confidence": confidence,
        "review_required": review_required,
    }





def build_restricted_document(
    source: SourceConfig,
    channel: ChannelConfig,
    title: str,
    url: str,
    published_at: str | None,
    content: str,
    now: datetime,
) -> dict[str, Any]:
    _RUN_STATS["restricted"] += 1
    digest = document_hash("restricted", title, url, content)
    scoring_text = f"{title} {content}"
    category = infer_category(scoring_text)
    domain = infer_domain(scoring_text, category, source.source_type)
    intent = infer_intent(scoring_text, False, 0)
    return {
        "id": f"{source.id}-{digest}",
        "kind": "notice",
        "status": "restricted",
        "source_id": source.id,
        "channel_id": channel.id,
        "channel": channel.name,
        "title": title,
        "url": url,
        "source": source.name,
        "source_domain": urlparse(source.base_url).netloc,
        "source_type": normalize_source_type(source.source_type),
        "category": category,
        "domain": domain,
        "intent": intent,
        "lifecycle": infer_lifecycle(published_at, None, now),
        "evidence": extract_evidence(scoring_text, ["校内", "登录", title]),
        "confidence": 0.35,
        "sub_category": None,
        "deadline": None,
        "action_required": False,
        "action_type": None,
        "action_summary": None,
        "required_materials": [],
        "sensitive": False,
        "sensitive_types": [],
        "review_required": True,
        "risk_flags": ["restricted_content"],
        "audience": list(source.audience),
        "published_at": published_at,
        "content": title,
        "summary": restricted_summary(),
        "attachments": [],
        "tags": infer_tags(scoring_text, category),
        "hash": digest,
        "cache_key": llm_cache_key(source.id, url, content, []),
        "llm_schema_version": active_llm_schema_version(),
        "llm": llm_metadata(False, review_required=True),
        "canonical": {
            "doc_id": f"{source.id}-{digest}",
            "canonical_url": normalize_url(url),
            "content_hash": document_hash(title),
            "dedupe_key": document_hash(source.id, channel.id, title),
        },
        "rule_guard": {
            "restricted": True,
            "sensitive": False,
            "low_evidence": False,
            "duplicate": False,
            "expired": False,
            "evergreen": False,
            "risk_flags": ["restricted_content"],
            "allow_llm": False,
            "allow_full_text_display": False,
            "review_required": True,
        },
        "task_frames": [],
    }


from core.indexer_scoring import infer_category, infer_tags


def extract_attachments(soup: BeautifulSoup, page_url: str, selector: str | None = None) -> list[dict[str, str]]:
    attachments: list[dict[str, str]] = []
    seen: set[str] = set()
    roots = soup.select(selector) if selector else [soup]
    if selector and not roots:
        roots = [soup]
    anchors = []
    for root in roots:
        if getattr(root, "name", None) == "a":
            anchors.append(root)
        else:
            anchors.extend(root.find_all("a"))
    for anchor in anchors:
        href = anchor.get("href")
        if not href:
            continue
        absolute_url = normalize_url(urljoin(page_url, href))
        extension = extension_from_url(absolute_url)
        if extension not in ATTACHMENT_EXTENSIONS:
            continue
        if absolute_url in seen:
            continue
        seen.add(absolute_url)
        name = clean_text(anchor.get_text(" ", strip=True)) or os.path.basename(urlparse(absolute_url).path)
        attachments.append({"name": name, "url": absolute_url, "type": extension.lstrip(".")})
    return attachments[:8]


def extract_article_text_with_strategy(soup: BeautifulSoup, selector: str | None = None) -> tuple[str, str]:
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    if selector:
        for node in soup.select(selector):
            text = clean_text(node.get_text(" ", strip=True))
            if len(text) >= 20:
                return text[:2400], "channel_content_selector"

    selectors = [
        ".wp_articlecontent",
        ".article",
        ".article_content",
        ".news_content",
        ".v_news_content",
        "#wp_content_w6_0",
        ".content",
        "main",
        "body",
    ]
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            text = clean_text(node.get_text(" ", strip=True))
            if len(text) >= 20:
                return text[:2400], "global_content_selector"
    return clean_text(soup.get_text(" ", strip=True))[:2400], "body_text_fallback"


def extract_article_text(soup: BeautifulSoup, selector: str | None = None) -> str:
    return extract_article_text_with_strategy(soup, selector)[0]


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    return clean_text(BeautifulSoup(value, "html.parser").get_text(" ", strip=True))


def llm_cache_result_for_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    if _RUN_CONFIG["no_llm"]:
        return None
    if _RUN_CONFIG["force_llm"] and runtime_llm_enabled():
        return None
    cached = _LLM_CACHE.get(str(entry["cache_key"]))
    if not isinstance(cached, dict):
        return None
    if cached.get("schema_version") != active_llm_schema_version():
        return None
    result = cached.get("result")
    if not isinstance(result, dict):
        return None
    cached_provider = str(cached.get("provider") or "")
    cached_model = str(cached.get("model") or "")
    if runtime_llm_enabled():
        if cached_provider and cached_provider != runtime_llm_provider_name():
            return None
        if cached_model and cached_model != runtime_llm_model_name():
            return None
    restored = dict(result)
    restored["__llm_provider"] = cached_provider or runtime_llm_provider_name()
    restored["__llm_model"] = cached_model or str(runtime_llm_model_name() or "")
    return restored


def store_llm_cache_result(entry: dict[str, Any], result: dict[str, Any], now: datetime) -> None:
    global _LLM_CACHE_CHANGED
    cache_key = str(entry["cache_key"])
    _LLM_CACHE[cache_key] = {
        "schema_version": active_llm_schema_version(),
        "provider": str(result.get("__llm_provider") or runtime_llm_provider_name()),
        "model": str(result.get("__llm_model") or runtime_llm_model_name() or ""),
        "source_id": str(entry.get("source_id", "")),
        "url": str(entry.get("url", "")),
        "normalized_url": normalize_url(str(entry.get("url", ""))),
        "title": str(entry.get("title", "")),
        "content_hash": document_hash(str(entry.get("content", ""))),
        "attachment_hash": document_hash(entry.get("attachments", [])),
        "updated_at": now.isoformat(),
        "result": public_llm_result(result),
    }
    _LLM_CACHE_CHANGED = True


def llm_payload_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    guard = entry.get("rule_guard") if isinstance(entry.get("rule_guard"), dict) else {}
    content = entry.get("content", "")
    if not guard.get("allow_full_text_display", True):
        content = " ".join([str(entry.get("title", "")), *[str(item.get("name", "")) for item in entry.get("attachments", [])]])
    return {
        "id": str(entry["cache_key"]),
        "doc_id": str(entry.get("id", "")),
        "source_id": entry.get("source_id", ""),
        "channel_id": entry.get("channel_id", ""),
        "title": entry.get("title", ""),
        "source": entry.get("source", ""),
        "channel": entry.get("channel", ""),
        "source_domain": entry.get("source_domain", ""),
        "published_at": entry.get("published_at"),
        "content": content,
        "attachments": entry.get("attachments", []),
        "rule_guard": guard,
    }


def should_skip_llm_entry(entry: dict[str, Any]) -> bool:
    guard = entry.get("rule_guard") if isinstance(entry.get("rule_guard"), dict) else {}
    if guard and not guard.get("allow_llm", True):
        return True
    if str(entry.get("source_type")) in {"github_resource", "job_platform"}:
        return False
    content = str(entry.get("content", ""))
    attachments = list(entry.get("attachments", []))
    if is_low_evidence_content(content, attachments):
        return True
    text = f"{entry.get('title', '')} {content}"
    obvious_admin_terms = ("采购", "招标", "比选", "中标", "成交", "验收", "资产处置", "巡察", "审计")
    return any(term in text for term in obvious_admin_terms) and not contains_relevant_keyword(text)


def analyze_prepared_documents(prepared: list[dict[str, Any]], now: datetime) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    pending: list[dict[str, Any]] = []

    for entry in prepared:
        if should_skip_llm_entry(entry):
            _RUN_STATS["llm_fallback"] += 1
            continue
        cached_result = llm_cache_result_for_entry(entry)
        if cached_result:
            _RUN_STATS["candidate_llm_cache_reused"] += 1
            _RUN_STATS["llm_reused"] += 1
            results[str(entry["cache_key"])] = cached_result
        else:
            pending.append(entry)

    if not pending:
        return results

    if _RUN_CONFIG["no_llm"] or not llm_enabled(runtime_llm_provider()):
        _RUN_STATS["llm_fallback"] += len(pending)
        return results

    llm_limit = _RUN_CONFIG.get("llm_limit")
    if llm_limit is not None:
        remaining = max(0, int(llm_limit) - _RUN_STATS["llm_attempted"])
        if remaining <= 0:
            _RUN_STATS["llm_skipped_by_limit"] += len(pending)
            _RUN_STATS["llm_fallback"] += len(pending)
            return results
        if remaining < len(pending):
            skipped = pending[remaining:]
            _RUN_STATS["llm_skipped_by_limit"] += len(skipped)
            _RUN_STATS["llm_fallback"] += len(skipped)
            pending = pending[:remaining]

    payloads = [llm_payload_from_entry(entry) for entry in pending]
    entry_by_cache_key = {str(entry["cache_key"]): entry for entry in pending}
    batches = split_llm_batches(
        payloads,
        max_docs=effective_llm_batch_size(),
        max_chars=int(_RUN_CONFIG["llm_batch_max_chars"]),
    )

    def process_batch(current_batch: list[dict[str, Any]], attempts: int = 1) -> dict[str, dict[str, Any]]:
        if not current_batch:
            return {}
        batch_ids = {str(item["id"]) for item in current_batch}
        _RUN_STATS["llm_batches_attempted"] += 1
        
        batch_results = analyze_documents_batch_with_llm(
            current_batch,
            provider=runtime_llm_provider(),
            enabled=True,
            schema_version=active_llm_schema_version(),
            max_output_tokens=effective_llm_batch_max_output_tokens(),
        )
        
        missing = batch_ids - set(batch_results)
        if missing and attempts < 3:
            # Batch failed partially or completely, try splitting
            print(f"Batch failed ({len(missing)} missing). Splitting and retrying (attempt {attempts+1})...")
            mid = max(1, len(current_batch) // 2)
            left_batch = current_batch[:mid]
            right_batch = current_batch[mid:]
            res_left = process_batch(left_batch, attempts + 1)
            res_right = process_batch(right_batch, attempts + 1)
            
            # Merge results
            for k, v in res_left.items(): batch_results[k] = v
            for k, v in res_right.items(): batch_results[k] = v
            
            # Recalculate missing
            missing = batch_ids - set(batch_results)
            
        if missing:
            _RUN_STATS["llm_failed"] += len(missing)
            _RUN_STATS["llm_fallback"] += len(missing)
            for missing_id in missing:
                if missing_id in entry_by_cache_key:
                    batch_results[missing_id] = {
                        "llm_failure": {
                            "attempted": True,
                            "provider_attempts": provider_chain(runtime_llm_provider()),
                            "failure_reason": "provider_error_or_dropped",
                            "retry_count": attempts,
                            "fallback_mode": "heuristic_degraded"
                        }
                    }
        return batch_results

    for batch in batches:
        _RUN_STATS["llm_batch_docs_attempted"] += len(batch)
        _RUN_STATS["llm_attempted"] += len(batch)
        batch_results = process_batch(batch)
        
        for cache_key, result in batch_results.items():
            if cache_key not in entry_by_cache_key:
                continue
            results[cache_key] = result
            if "llm_failure" not in result:
                store_llm_cache_result(entry_by_cache_key[cache_key], result, now)
                _RUN_STATS["llm_reprocessed"] += 1

    return results


def build_search_document_from_prepared(
    entry: dict[str, Any],
    llm_result: dict[str, Any] | None,
    now: datetime,
) -> dict[str, Any]:
    guard = entry.get("rule_guard") if isinstance(entry.get("rule_guard"), dict) else {}
    if not guard:
        guard = evaluate_rule_guard(
            title=str(entry.get("title", "")),
            content=str(entry.get("content", "")),
            attachments=list(entry.get("attachments", [])),
            published_at=entry.get("published_at"),
            lifecycle="active",
            domain=entry.get("domain", "news"),
            intent=entry.get("intent", "read"),
            source_type=entry.get("source_type"),
        )
        
    from core.semantic_pipeline import route_semantic_pipeline
    semantic = route_semantic_pipeline(entry, llm_result, guard, _RUN_CONFIG, now)

    for tag in entry.get("extra_tags", []):
        if tag and tag not in semantic.tags:
            semantic.tags.append(tag)

    lifecycle = semantic.lifecycle
    if entry.get("lifecycle_kind") == "resource":
        lifecycle = infer_lifecycle(entry.get("published_at"), semantic.deadline, now, "resource")

    document = {
        "id": entry["id"],
        "kind": entry["kind"],
        "source_id": entry.get("source_id", ""),
        "channel_id": entry.get("channel_id", ""),
        "channel": entry.get("channel", ""),
        "title": entry["title"],
        "url": entry["url"],
        "source": entry["source"],
        "source_domain": entry["source_domain"],
        "source_type": normalize_source_type(entry["source_type"]),
        "category": semantic.category,
        "domain": semantic.domain,
        "intent": semantic.intent,
        "lifecycle": lifecycle,
        "evidence": semantic.evidence,
        "confidence": semantic.confidence,
        "sub_category": getattr(semantic, "sub_category", None),
        "deadline": semantic.deadline,
        "action_required": semantic.action_required,
        "action_type": semantic.action_type,
        "action_summary": semantic.action_summary,
        "required_materials": semantic.required_materials,
        "sensitive": semantic.sensitive,
        "sensitive_types": semantic.sensitive_types,
        "review_required": semantic.review_required,
        "risk_flags": semantic.risk_flags,
        "audience": list(entry.get("audience", [])),
        "published_at": entry.get("published_at"),
        "content": semantic.content,
        "summary": semantic.summary,
        "attachments": semantic.attachments,
        "tags": semantic.tags[:10],
        "hash": entry["hash"],
        "cache_key": entry["cache_key"],
        "llm_schema_version": active_llm_schema_version(),
        "llm": semantic.llm,
        "semantic_mode": semantic.semantic_mode,
        "field_sources": semantic.field_sources,
        "canonical": entry.get("canonical", {}),
        "rule_guard": guard,
        "semantic_pipeline_version": "semantic-router-v2",
        "llm_prompt_version": "v2",
        "llm_input_pack_version": "v1",
        "raw_field_presence": semantic.raw_field_presence,
        "llm_failure": semantic.llm_failure,
        "crawler": entry.get("crawler", {}),
    }
    document["task_frames"] = extract_task_frames(document, llm_result=llm_result, rule_guard=document["rule_guard"])
    document = verify_search_document(document)
    
    document["search_profile"] = {
        "route_domains": list(set([semantic.domain, *[tag for tag in semantic.tags if tag in ["international", "project", "academic", "exam"]]])),
        "route_intents": list(set([semantic.intent, *[frame.get("action", {}).get("verb") for frame in document["task_frames"] if isinstance(frame.get("action"), dict) and frame.get("action").get("verb")]])),
        "eligible_query_types": ["task_search", "general_search"] if document["task_frames"] else ["general_search"],
        "blocked_query_types": [],
        "strong_terms": semantic.tags[:3],
        "weak_terms": semantic.tags[3:],
        "exact_terms": [semantic.category],
        "audience_terms": list(entry.get("audience", []))
    }
    
    return document


def prepare_notice_candidate(
    source: SourceConfig,
    channel: ChannelConfig,
    candidate: dict[str, str | None],
    now: datetime,
) -> dict[str, Any] | None:
    title = candidate["title"] or ""
    url = candidate["url"] or source.base_url
    published_at = candidate.get("published_at")
    content = title
    attachments: list[dict[str, str]] = []
    selector_warnings = list(candidate.get("selector_warnings") or [])
    selector_strategy = str(candidate.get("selector_strategy") or "global_anchor_fallback")

    try:
        html = fetch_html(url, source)
        soup = BeautifulSoup(html, "html.parser")
        title_node = soup.select_one(channel.selectors.title) if channel.selectors.title else None
        if not title_node:
            title_node = (
                soup.select_one(".arti_title")
                or soup.select_one(".articleTitle")
                or soup.select_one(".news_title")
                or soup.find("h1")
            )
        page_title = clean_text(title_node.get_text(" ", strip=True)) if title_node else ""
        if page_title and len(page_title) >= 4 and page_title not in NAV_TITLES:
            title = page_title
        content, content_strategy = extract_article_text_with_strategy(soup, channel.selectors.content)
        content = content or title
        selector_strategy = f"{selector_strategy}+{content_strategy}"
        if channel.selectors.content and content_strategy != "channel_content_selector":
            selector_warnings.append(f"{channel.id}: content selector {channel.selectors.content!r} did not produce article text")
        attachments = extract_attachments(soup, url, channel.selectors.attachments)
        if channel.selectors.attachments and not attachments:
            selector_warnings.append(f"{channel.id}: attachment selector {channel.selectors.attachments!r} found no attachments")
        if channel.selectors.date:
            date_node = soup.select_one(channel.selectors.date)
            if date_node:
                published_at = published_at or parse_date(date_node.get_text(" ", strip=True), now)
            else:
                selector_warnings.append(f"{channel.id}: date selector {channel.selectors.date!r} found no date")
        published_at = published_at or parse_date(content, now)
    except Exception as exc:
        selector_warnings.append(f"{channel.id}: detail fetch/extraction failed for {url}: {exc}")
        content = title

    if is_expired(published_at, now):
        return None

    if is_restricted_content(content):
        return {"ready_document": build_restricted_document(source, channel, title, url, published_at, content, now)}

    digest = document_hash(title, url, content, attachments)
    cache_key = llm_cache_key(source.id, url, content, attachments)
    cached = _DOC_CACHE.get(cache_key) or _DOC_CACHE.get(digest)
    if cache_is_current(cached):
        return {"ready_document": cached_with_freshness(cached, published_at, now)}

    raw = RawDocument(
        raw_id=f"{source.id}-{digest}",
        source_id=source.id,
        channel_id=channel.id,
        url=url,
        title=title,
        raw_text=content,
        fetched_at=now.isoformat(),
        http_status=200,
        published_at=published_at,
        attachments=attachments,
    )
    canonical = canonicalize_raw_document(raw, base_url=source.base_url)
    provisional_domain = infer_domain(f"{title} {content}", infer_category(f"{title} {content}"), source.source_type)
    provisional_intent = infer_intent(f"{title} {content}", False, len(attachments))
    rule_guard = evaluate_rule_guard(
        title=title,
        content=content,
        attachments=attachments,
        published_at=published_at,
        domain=provisional_domain,
        intent=provisional_intent,
        source_type=source.source_type,
    )

    return {
        "id": f"{source.id}-{digest}",
        "kind": "notice",
        "source_id": source.id,
        "channel_id": channel.id,
        "channel": channel.name,
        "title": title,
        "url": url,
        "source": source.name,
        "source_domain": urlparse(source.base_url).netloc,
        "source_type": normalize_source_type(source.source_type),
        "audience": list(source.audience),
        "published_at": published_at,
        "content": content,
        "attachments": attachments,
        "default_category": infer_category(f"{title} {content}"),
        "source_weight": max(source.source_weight, channel.priority, channel.student_value),
        "channel_priority": channel.priority,
        "channel_student_value": channel.student_value,
        "hash": digest,
        "cache_key": cache_key,
        "lifecycle_kind": "notice",
        "canonical": canonical.model_dump(),
        "rule_guard": rule_guard,
        "crawler": {
            "selector_strategy": selector_strategy,
            "warnings": selector_warnings[:6],
            "allow_insecure_tls": source.allow_insecure_tls,
        },
    }


def channel_has_list_selectors(channel: ChannelConfig) -> bool:
    selectors = channel.selectors
    return any((selectors.list_item, selectors.title, selectors.date, selectors.link))


def select_relative_text(node: Any, selector: str | None) -> str:
    if selector:
        selected = node.select_one(selector)
        if selected:
            return clean_text(selected.get("title") or selected.get_text(" ", strip=True))
        return ""
    return clean_text(node.get("title") or node.get_text(" ", strip=True))


def select_relative_link(node: Any, selector: str | None) -> tuple[str, str]:
    link_node = node.select_one(selector) if selector else None
    if link_node is None:
        link_node = node if getattr(node, "name", None) == "a" else node.find("a")
    if not link_node:
        return "", ""
    href = str(link_node.get("href") or "")
    text = clean_text(link_node.get("title") or link_node.get_text(" ", strip=True))
    return href, text


def collect_selector_candidates(
    soup: BeautifulSoup,
    *,
    list_url: str,
    source: SourceConfig,
    channel: ChannelConfig,
    now: datetime,
    seen: set[str],
) -> tuple[list[dict[str, str | None]], list[str]]:
    selectors = channel.selectors
    warnings: list[str] = []
    nodes = soup.select(selectors.list_item) if selectors.list_item else []
    if not nodes and selectors.list_item:
        warnings.append(f"{channel.id}: list_item selector {selectors.list_item!r} matched no nodes")
        return [], warnings
    if not nodes:
        nodes = soup.find_all("a")

    candidates: list[dict[str, str | None]] = []
    for node in nodes:
        href, link_text = select_relative_link(node, selectors.link)
        if not href:
            continue
        title = select_relative_text(node, selectors.title) or link_text
        if len(title) < 4 or title in NAV_TITLES or title.lower() in NAV_TITLES:
            continue
        absolute_url = normalize_url(urljoin(list_url, href))
        parsed = urlparse(absolute_url)
        if parsed.scheme not in {"http", "https"} or not same_domain(absolute_url, source):
            continue
        extension = extension_from_url(absolute_url)
        if extension in STATIC_EXTENSIONS or extension in ATTACHMENT_EXTENSIONS:
            continue
        if absolute_url in seen or not matches_source_patterns(absolute_url, title, source):
            continue

        parent_text = clean_text(node.get_text(" ", strip=True))
        if not looks_like_notice_link(title, parent_text, absolute_url, now):
            continue
        channel_text = f"{title} {parent_text}"
        if any(keyword and keyword in channel_text for keyword in channel.negative_keywords):
            if not any(keyword and keyword in channel_text for keyword in channel.positive_keywords):
                continue

        seen.add(absolute_url)
        date_text = ""
        if selectors.date:
            date_node = node.select_one(selectors.date)
            if date_node:
                date_text = clean_text(date_node.get_text(" ", strip=True))
        published_at = parse_date(" ".join([date_text, title, parent_text, absolute_url]), now)
        if is_expired(published_at, now):
            continue
        candidates.append({
            "title": title,
            "url": absolute_url,
            "published_at": published_at,
            "selector_strategy": "channel_list_selector" if channel_has_list_selectors(channel) else "global_anchor_fallback",
            "selector_warnings": warnings[:3],
        })
    return candidates, warnings


def collect_candidates(source: SourceConfig, channel: ChannelConfig, now: datetime) -> tuple[list[dict[str, Any]], list[str]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    list_errors: list[str] = []
    pending = list(channel.list_urls or source.list_urls)
    visited_list_urls: set[str] = set()
    max_list_pages = max(1, len(pending) * max(source.max_pages, channel.crawl_depth))

    while pending and len(visited_list_urls) < max_list_pages:
        list_url = pending.pop(0)
        if list_url in visited_list_urls:
            continue
        visited_list_urls.add(list_url)
        try:
            html = fetch_html(list_url, source)
        except Exception as exc:
            list_errors.append(f"{list_url}: {exc}")
            continue
        soup = BeautifulSoup(html, "html.parser")

        selector_candidates: list[dict[str, Any]] = []
        if channel_has_list_selectors(channel):
            selector_candidates, selector_warnings = collect_selector_candidates(
                soup,
                list_url=list_url,
                source=source,
                channel=channel,
                now=now,
                seen=seen,
            )
            candidates.extend(selector_candidates)
            list_errors.extend(selector_warnings[:3])
            if selector_candidates:
                if source.max_pages > 1:
                    for next_url in discover_next_list_urls(soup, list_url, source):
                        if next_url not in visited_list_urls and next_url not in pending:
                            pending.append(next_url)
                continue
            list_errors.append(f"{channel.id}: channel selectors produced no usable candidates for {list_url}; using global anchor fallback")

        for anchor in soup.find_all("a"):
            href = anchor.get("href")
            if not href:
                continue

            title = clean_text(anchor.get("title") or anchor.get_text(" ", strip=True))
            if len(title) < 4 or title in NAV_TITLES or title.lower() in NAV_TITLES:
                continue

            absolute_url = normalize_url(urljoin(list_url, href))
            parsed = urlparse(absolute_url)
            if parsed.scheme not in {"http", "https"} or not same_domain(absolute_url, source):
                continue

            extension = extension_from_url(absolute_url)
            if extension in STATIC_EXTENSIONS or extension in ATTACHMENT_EXTENSIONS:
                continue

            if absolute_url in seen:
                continue
            if not matches_source_patterns(absolute_url, title, source):
                continue

            parent_text = clean_text(anchor.parent.get_text(" ", strip=True)) if anchor.parent else title
            if not looks_like_notice_link(title, parent_text, absolute_url, now):
                continue
            channel_text = f"{title} {parent_text}"
            if any(keyword and keyword in channel_text for keyword in channel.negative_keywords):
                if not any(keyword and keyword in channel_text for keyword in channel.positive_keywords):
                    continue

            seen.add(absolute_url)
            date_text = " ".join([title, parent_text, absolute_url])
            published_at = parse_date(date_text, now)
            
            if is_expired(published_at, now):
                continue

            candidates.append({
                "title": title,
                "url": absolute_url,
                "published_at": published_at,
                "selector_strategy": "global_anchor_fallback",
                "selector_warnings": [],
            })

        if source.max_pages > 1:
            for next_url in discover_next_list_urls(soup, list_url, source):
                if next_url not in visited_list_urls and next_url not in pending:
                    pending.append(next_url)

    return candidates[:MAX_DOCS_PER_SOURCE * 2], list_errors[:8]


def prepare_job_entry(
    source: SourceConfig,
    channel: ChannelConfig,
    external_id: str,
    title: str,
    url: str,
    published_at: str | None,
    content: str,
    category: str,
    now: datetime,
) -> dict[str, Any] | None:
    if is_expired(published_at, now):
        return None
    digest = document_hash("job", external_id, title, url, content)
    cache_key = llm_cache_key(source.id, url, content, [])
    cached = _DOC_CACHE.get(cache_key) or _DOC_CACHE.get(digest)
    if cache_is_current(cached):
        return {"ready_document": cached_with_freshness(cached, published_at, now)}

    return {
        "id": f"{source.id}-{digest}",
        "kind": "notice",
        "source_id": source.id,
        "channel_id": channel.id,
        "channel": channel.name,
        "title": title,
        "url": url,
        "source": source.name,
        "source_domain": urlparse(source.base_url).netloc,
        "source_type": normalize_source_type(source.source_type),
        "audience": list(source.audience),
        "published_at": published_at,
        "content": content or title,
        "attachments": [],
        "default_category": category,
        "source_weight": source.source_weight,
        "channel_priority": channel.priority,
        "channel_student_value": channel.student_value,
        "hash": digest,
        "cache_key": cache_key,
        "lifecycle_kind": "notice",
        "canonical": canonicalize_raw_document(RawDocument(
            raw_id=f"{source.id}-{digest}",
            source_id=source.id,
            channel_id=channel.id,
            url=url,
            title=title,
            raw_text=content or title,
            fetched_at=now.isoformat(),
            http_status=200,
            published_at=published_at,
            attachments=[],
        ), base_url=source.base_url).model_dump(),
        "rule_guard": evaluate_rule_guard(
            title=title,
            content=content or title,
            attachments=[],
            published_at=published_at,
            domain="employment",
            intent="attend",
            source_type=source.source_type,
        ),
    }


def crawl_job_source(source: SourceConfig, now: datetime) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    prepared: list[dict[str, Any]] = []
    channel = source.channels[0] if source.channels else ChannelConfig(
        id=f"{source.id}_job",
        source_id=source.id,
        name="就业信息",
        list_urls=source.list_urls,
        student_value=source.source_weight,
        priority=source.source_weight,
    )

    meeting_body = {
        "current": 1,
        "xxxs": "",
        "fbsj": "",
        "ssxx": "",
        "keyword": "",
        "size": 10,
        "xxdm": JOB_STATION_CODE,
    }
    meeting_payload = post_json(f"{JOB_API_BASE}/getZphPageList", meeting_body, source)
    for item in meeting_payload.get("result", {}).get("records", [])[:10]:
        title = clean_text(str(item.get("zphmc", "")))
        if not title:
            continue
        start_time = clean_text(str(item.get("jbkssj", "")))
        end_time = clean_text(str(item.get("jbjssj", "")))
        location = clean_text(str(item.get("jbcd", "")))
        content = clean_text(" ".join([
            title,
            f"时间：{start_time} 至 {end_time}",
            f"地点：{location}",
            f"联系人：{item.get('lxr', '')}",
            f"电话：{item.get('lxdh', '')}",
        ]))
        external_id = str(item.get("zphid", ""))
        url = f"https://njupt.91job.org.cn/sub-station/recruitmentDetail?zphid={external_id}&xxdm={JOB_STATION_CODE}"
        entry = prepare_job_entry(source, channel, external_id, title, url, start_time[:10] or None, content, "就业", now)
        if entry:
            if entry.get("ready_document"):
                documents.append(entry["ready_document"])
            else:
                prepared.append(entry)

    lecture_body = {
        "current": 1,
        "xxxs": "",
        "fbsj": "",
        "ssxx": "",
        "keyword": "",
        "size": 10,
        "xxdm": JOB_STATION_CODE,
    }
    lecture_payload = post_json(f"{JOB_API_BASE}/getXjhPageList", lecture_body, source)
    for item in lecture_payload.get("result", {}).get("records", [])[:8]:
        title = clean_text(str(item.get("xjhmc", "")))
        if not title:
            continue
        date = clean_text(str(item.get("jbrq", "")))
        time = clean_text(str(item.get("kssjd", "")) or str(item.get("jssjd", "")))
        location = clean_text(str(item.get("jbdd", "")))
        content = clean_text(" ".join([
            title,
            f"宣讲时间：{time}",
            f"地点：{location}",
            f"举办学校：{item.get('jbxx', '')}",
            f"联系人：{item.get('zplxr', '')}",
            f"电话：{item.get('lxdh', '')}",
            strip_html(str(item.get("xjhjs", ""))),
        ]))
        external_id = str(item.get("xjhid", ""))
        url = f"https://njupt.91job.org.cn/sub-station/lectureDetail?xjhid={external_id}&xxdm={JOB_STATION_CODE}"
        entry = prepare_job_entry(source, channel, external_id, title, url, date or None, content, "就业", now)
        if entry:
            if entry.get("ready_document"):
                documents.append(entry["ready_document"])
            else:
                prepared.append(entry)

    llm_results = analyze_prepared_documents(prepared, now)
    for entry in prepared:
        documents.append(build_search_document_from_prepared(entry, llm_results.get(str(entry["cache_key"])), now))
    return documents[:MAX_DOCS_PER_SOURCE]


def read_github_source_configs() -> tuple[GitHubSourceConfig, ...]:
    if not os.path.exists(GITHUB_SOURCE_CONFIG_PATH):
        return ()

    with open(GITHUB_SOURCE_CONFIG_PATH, "r", encoding="utf-8") as config_file:
        payload = json.load(config_file)

    raw_sources = payload.get("sources", []) if isinstance(payload, dict) else []
    sources: list[GitHubSourceConfig] = []
    for item in raw_sources:
        if not isinstance(item, dict):
            continue
        repo = clean_text(str(item.get("repo", "")))
        if "/" not in repo:
            continue
        include = item.get("include") if isinstance(item.get("include"), list) else ["README.md", "*.md", "docs/**/*.md"]
        exclude = item.get("exclude") if isinstance(item.get("exclude"), list) else []
        audience = item.get("audience") if isinstance(item.get("audience"), list) else ["本科生", "研究生"]
        sources.append(
            GitHubSourceConfig(
                repo=repo,
                label=clean_text(str(item.get("label") or repo)),
                category=clean_text(str(item.get("category") or "资料")),
                audience=tuple(str(value) for value in audience),
                include=tuple(str(value) for value in include),
                exclude=tuple(str(value) for value in exclude),
                max_files=max(1, min(int(item.get("max_files", 20)), 50)),
                source_weight=float(item.get("source_weight", 0.72)),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return tuple(sources)


def github_headers(token: str | None) -> dict[str, str]:
    token = str(token or "").strip().lstrip("\ufeff").strip() or None
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "njupt-search-indexer",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def github_api_get(endpoint: str, token: str | None) -> Any:
    response = requests.get(
        f"{GITHUB_API_BASE}{endpoint}",
        headers=github_headers(token),
        timeout=REQUEST_TIMEOUT,
    )
    if token and response.status_code in {401, 403}:
        response = requests.get(
            f"{GITHUB_API_BASE}{endpoint}",
            headers=github_headers(None),
            timeout=REQUEST_TIMEOUT,
        )
    response.raise_for_status()
    return response.json()


def matches_path(path: str, patterns: tuple[str, ...]) -> bool:
    normalized = path.replace("\\", "/")
    for pattern in patterns:
        normalized_pattern = pattern.replace("\\", "/")
        if "/" not in normalized_pattern and "/" in normalized:
            continue
        if fnmatch.fnmatch(normalized, normalized_pattern):
            return True
    return False


def select_github_files(source: GitHubSourceConfig, branch: str, token: str | None) -> list[dict[str, Any]]:
    tree_payload = github_api_get(
        f"/repos/{source.repo}/git/trees/{quote(branch, safe='')}?recursive=1",
        token,
    )
    files: list[dict[str, Any]] = []
    for item in tree_payload.get("tree", []):
        if item.get("type") != "blob":
            continue
        path = str(item.get("path", ""))
        size = int(item.get("size") or 0)
        if not path or size <= 0 or size > GITHUB_FILE_SIZE_LIMIT_BYTES:
            continue
        if source.exclude and matches_path(path, source.exclude):
            continue
        if not matches_path(path, source.include):
            continue
        files.append({"path": path, "size": size})

    files.sort(key=lambda file: (0 if file["path"].lower().endswith("readme.md") else 1, file["path"]))
    return files[: source.max_files]


def fetch_github_file_text(repo: str, branch: str, path: str, token: str | None) -> str:
    quoted_path = quote(path, safe="/")
    quoted_branch = quote(branch, safe="")
    payload = github_api_get(f"/repos/{repo}/contents/{quoted_path}?ref={quoted_branch}", token)
    content = payload.get("content", "")
    if payload.get("encoding") != "base64" or not isinstance(content, str):
        return ""
    return base64.b64decode(content).decode("utf-8", errors="replace")


def extract_markdown_title(path: str, text: str) -> str:
    for line in text.splitlines()[:50]:
        stripped = line.strip()
        if stripped.startswith("#"):
            title = clean_text(stripped.lstrip("#").strip())
            if title:
                return title
    return os.path.basename(path)


def normalize_markdown_text(text: str) -> str:
    without_fences = re.sub(r"```.*?```", " ", text, flags=re.S)
    without_markup = re.sub(r"[#>*_`|[\]()]+", " ", without_fences)
    return clean_text(without_markup)[:4000]


def prepare_github_entry(
    source: GitHubSourceConfig,
    branch: str,
    path: str,
    text: str,
    repo_updated_at: str | None,
    now: datetime,
) -> dict[str, Any] | None:
    title = f"{source.label} · {extract_markdown_title(path, text)}"
    content = normalize_markdown_text(text) or title
    digest = document_hash("github", source.repo, branch, path, content)
    published_at = repo_updated_at[:10] if repo_updated_at else None
    url = f"https://github.com/{source.repo}/{path}"
    cache_key = llm_cache_key(f"github:{source.repo}", url, content, [])
    cached = _DOC_CACHE.get(cache_key) or _DOC_CACHE.get(digest)
    if cache_is_current(cached):
        return {"ready_document": cached_with_freshness(cached, published_at, now)}

    return {
        "id": f"github-{source.repo.replace('/', '-')}-{digest}",
        "kind": "resource",
        "source_id": f"github:{source.repo}",
        "channel_id": f"github:{source.repo}:resource",
        "channel": "GitHub 资源",
        "title": title,
        "url": f"https://github.com/{source.repo}/blob/{quote(branch, safe='')}/{quote(path, safe='/')}",
        "source": source.label,
        "source_domain": "github.com",
        "source_type": "github_resource",
        "audience": list(source.audience),
        "published_at": published_at,
        "content": content,
        "attachments": [],
        "default_category": source.category,
        "source_weight": source.source_weight,
        "hash": digest,
        "cache_key": cache_key,
        "lifecycle_kind": "resource",
        "extra_tags": ["GitHub资料"],
        "canonical": canonicalize_raw_document(RawDocument(
            raw_id=f"github-{source.repo.replace('/', '-')}-{digest}",
            source_id=f"github:{source.repo}",
            channel_id=f"github:{source.repo}:resource",
            url=f"https://github.com/{source.repo}/blob/{quote(branch, safe='')}/{quote(path, safe='/')}",
            title=title,
            raw_text=content,
            fetched_at=now.isoformat(),
            http_status=200,
            published_at=published_at,
            attachments=[],
        ), base_url=f"https://github.com/{source.repo}/").model_dump(),
        "rule_guard": evaluate_rule_guard(
            title=title,
            content=content,
            attachments=[],
            published_at=published_at,
            lifecycle="evergreen",
            domain="resource",
            intent="read",
            source_type="github_resource",
        ),
    }


def crawl_github_resource_source(source: GitHubSourceConfig, now: datetime) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    print(f"Fetching GitHub resources {source.repo}")
    manifest_entry: dict[str, Any] = {
        "id": f"github:{source.repo}",
        "name": source.label,
        "domain": "github.com",
        "source_type": "github_resource",
        "status": "ok",
        "documents": 0,
        "last_fetch_at": now.isoformat(),
    }

    if not source.enabled:
        return [], manifest_entry

    token = clean_env_value(GITHUB_TOKEN_ENV) or clean_env_value("GITHUB_TOKEN") or None
    try:
        repo_payload = github_api_get(f"/repos/{source.repo}", token)
        branch = repo_payload.get("default_branch") or "main"
        updated_at = repo_payload.get("pushed_at") or repo_payload.get("updated_at")
        selected_files = select_github_files(source, branch, token)

        documents: list[dict[str, Any]] = []
        prepared: list[dict[str, Any]] = []
        for file_entry in selected_files:
            path = str(file_entry["path"])
            text = fetch_github_file_text(source.repo, branch, path, token)
            if clean_text(text):
                entry = prepare_github_entry(source, branch, path, text, updated_at, now)
                if entry:
                    if entry.get("ready_document"):
                        documents.append(entry["ready_document"])
                    else:
                        prepared.append(entry)

        llm_results = analyze_prepared_documents(prepared, now)
        for entry in prepared:
            documents.append(build_search_document_from_prepared(entry, llm_results.get(str(entry["cache_key"])), now))

        manifest_entry["candidates"] = len(selected_files)
        manifest_entry["documents"] = len(documents)
        return documents, manifest_entry
    except Exception as exc:
        stale_documents = cached_documents_for_source_id(f"github-{source.repo.replace('/', '-')}")
        if stale_documents:
            manifest_entry["status"] = "ok"
            manifest_entry["warning"] = f"GitHub fetch failed; reused stale cached documents: {exc}"
            manifest_entry["documents"] = len(stale_documents)
            return stale_documents, manifest_entry
        if "rate limit" in str(exc).lower():
            manifest_entry["status"] = "ok"
            manifest_entry["warning"] = f"GitHub fetch rate-limited; skipped this optional resource source: {exc}"
            manifest_entry["documents"] = 0
            return [], manifest_entry
        manifest_entry["status"] = "error"
        manifest_entry["error"] = str(exc)
        return [], manifest_entry


def crawl_source(source: SourceConfig, now: datetime) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    print(f"Fetching {source.name} ({urlparse(source.base_url).netloc})")
    manifest_entry: dict[str, Any] = {
        "id": source.id,
        "name": source.name,
        "domain": urlparse(source.base_url).netloc,
        "source_type": normalize_source_type(source.source_type),
        "adapter_kind": source.adapter_kind,
        "allow_insecure_tls": source.allow_insecure_tls,
        "priority": source.source_weight,
        "requires_devtools_audit": source.requires_devtools_audit,
        "channel_count": len(source.channels),
        "channels": [
            {
                "id": channel.id,
                "name": channel.name,
                "priority": channel.priority,
                "student_value": channel.student_value,
                "audit_status": channel.audit_status,
                "selectors": {
                    "list_item": channel.selectors.list_item,
                    "title": channel.selectors.title,
                    "date": channel.selectors.date,
                    "link": channel.selectors.link,
                    "content": channel.selectors.content,
                    "attachments": channel.selectors.attachments,
                },
                "status": "ok",
                "documents": 0,
            }
            for channel in source.channels
        ],
        "status": "ok",
        "documents": 0,
        "last_fetch_at": now.isoformat(),
    }

    try:
        if source.adapter_kind == "job_api" or source.id == "job":
            documents = crawl_job_source(source, now)
            manifest_entry["documents"] = len(documents)
            return documents, manifest_entry

        candidates: list[dict[str, Any]] = []
        list_errors: list[str] = []
        channel_stats: dict[str, dict[str, Any]] = {}
        for channel in source.channels:
            channel_candidates, channel_errors = collect_candidates(source, channel, now)
            for candidate in channel_candidates:
                candidate["channel_id"] = channel.id
                candidate["channel_name"] = channel.name
            candidates.extend(channel_candidates)
            list_errors.extend(channel_errors)
            selector_strategies: dict[str, int] = {}
            selector_warnings: list[str] = []
            for candidate in channel_candidates:
                strategy = str(candidate.get("selector_strategy") or "unknown")
                selector_strategies[strategy] = selector_strategies.get(strategy, 0) + 1
                selector_warnings.extend(str(item) for item in candidate.get("selector_warnings", []) if str(item))
            channel_stats[channel.id] = {
                "candidates": len(channel_candidates),
                "list_errors": channel_errors[:3],
                "documents": 0,
                "selector_strategies": selector_strategies,
                "selector_warnings": list(dict.fromkeys(selector_warnings))[:5],
            }
        if list_errors:
            manifest_entry["list_errors"] = list_errors[:8]
        enriched: list[dict[str, Any]] = []
        prepared: list[dict[str, Any]] = []
        for candidate in candidates[:DETAIL_FETCH_LIMIT_PER_SOURCE]:
            channel_id = str(candidate.get("channel_id") or "")
            channel = next((item for item in source.channels if item.id == channel_id), source.channels[0])
            entry = prepare_notice_candidate(source, channel, candidate, now)
            if not entry:
                continue
            if entry.get("ready_document"):
                enriched.append(entry["ready_document"])
                channel_stats.setdefault(channel.id, {"candidates": 0, "list_errors": [], "documents": 0})["documents"] += 1
            else:
                prepared.append(entry)

        llm_results = analyze_prepared_documents(prepared, now)
        for entry in prepared:
            doc = build_search_document_from_prepared(entry, llm_results.get(str(entry["cache_key"])), now)
            if doc:
                enriched.append(doc)
                channel_stats.setdefault(str(doc.get("channel_id")), {"candidates": 0, "list_errors": [], "documents": 0})["documents"] += 1

        enriched.sort(
            key=lambda item: (
                item.get("published_at") or "",
                item.get("id") or "",
            ),
            reverse=True,
        )
        documents = enriched[:MAX_DOCS_PER_SOURCE]
        manifest_entry["candidates"] = len(enriched)
        manifest_entry["filtered_out"] = 0
        manifest_entry["capped_out"] = max(0, len(enriched) - len(documents))
        manifest_entry["documents"] = len(documents)
        enriched_channels = []
        for channel_entry in manifest_entry["channels"]:
            stat = channel_stats.get(channel_entry["id"], {})
            merged = {**channel_entry, **stat}
            cands = stat.get("candidates", 0)
            docs = stat.get("documents", 0)
            errs = stat.get("list_errors", [])
            
            if docs > 0:
                merged["status"] = "ok_with_docs"
            elif errs:
                merged["status"] = "error_fetch_failed"
            elif cands > 0 and docs == 0:
                merged["status"] = "warning_filtered_all"
            else:
                merged["status"] = "ok_no_recent_docs"
                
            enriched_channels.append(merged)
            
        manifest_entry["channels"] = enriched_channels
        return documents, manifest_entry
    except Exception as exc:
        manifest_entry["status"] = "error"
        manifest_entry["error"] = str(exc)
        return [], manifest_entry


def deduplicate_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_key: dict[str, dict[str, Any]] = {}
    url_keys: set[str] = set()

    def rank(document: dict[str, Any]) -> tuple[str, float, int]:
        return (
            str(document.get("published_at") or ""),
            SOURCE_PRIORITY.get(str(document.get("source")), float(document.get("source_weight", 0.5))),
            len(str(document.get("content", ""))),
        )

    for document in documents:
        title_key = normalize_title_for_dedupe(str(document.get("title", "")))
        if len(title_key) < 10:
            title_key = str(document.get("url", ""))
        key = title_key or str(document.get("url", ""))
        current = best_by_key.get(key)
        if current is None or rank(document) > rank(current):
            best_by_key[key] = document

    deduped = sorted(best_by_key.values(), key=rank, reverse=True)
    result: list[dict[str, Any]] = []
    for document in deduped:
        url = str(document.get("url", ""))
        if url in url_keys:
            continue
        url_keys.add(url)
        result.append(document)

    return result


def write_json_if_changed(path: str, payload: Any) -> bool:
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as existing:
            if existing.read() == serialized:
                return False
    with open(path, "w", encoding="utf-8", newline="\n") as output:
        output.write(serialized)
        output.write("\n")
    return True


def infer_cached_semantic_mode(document: dict[str, Any]) -> str:
    mode = str(document.get("semantic_mode") or "").strip()
    if mode:
        return mode
    if document.get("source_type") == "exam_vertical":
        return "structured_exam"

    field_sources = document.get("field_sources")
    llm_payload = document.get("llm") if isinstance(document.get("llm"), dict) else {}
    if isinstance(field_sources, dict) and field_sources:
        return "llm" if any(str(value).startswith("llm") for value in field_sources.values()) else "heuristic"
    if llm_payload.get("used") is False:
        return "heuristic"
    if llm_payload.get("raw_field_presence") or llm_payload.get("__llm_provider"):
        return "llm"
    return "unprocessed"


def llm_field_source(field: str, raw_presence: dict[str, bool]) -> str:
    raw_field = "student_summary" if field == "summary" else field
    return "llm" if raw_presence.get(raw_field) else "llm_missing"


def default_field_sources_for(document: dict[str, Any], semantic_mode: str, raw_presence: dict[str, bool]) -> dict[str, str]:
    if semantic_mode == "llm":
        return {
            "category": llm_field_source("category", raw_presence),
            "domain": llm_field_source("domain", raw_presence),
            "intent": llm_field_source("intent", raw_presence),
            "deadline": llm_field_source("deadline", raw_presence),
            "action_required": llm_field_source("action_required", raw_presence),
            "action_summary": llm_field_source("action_summary", raw_presence),
            "required_materials": llm_field_source("required_materials", raw_presence),
            "summary": llm_field_source("summary", raw_presence),
            "evidence": llm_field_source("evidence", raw_presence),
            "sensitive": llm_field_source("sensitive", raw_presence),
            "review_required": llm_field_source("review_required", raw_presence),
            "task_frames": "llm_raw_task_frame" if document.get("task_frames") else "empty_not_applicable",
        }
    if semantic_mode == "structured_exam":
        return {field: "structured_exam_data" for field in SEMANTIC_FIELDS_TO_TRACK}
    if semantic_mode == "guarded_metadata":
        return {field: "rule_guard" for field in SEMANTIC_FIELDS_TO_TRACK}
    if semantic_mode in {"heuristic", "heuristic_degraded"}:
        sources = {field: "heuristic" for field in SEMANTIC_FIELDS_TO_TRACK}
        sources["task_frames"] = "heuristic_rule_frame"
        return sources
    return {field: "unprocessed" for field in SEMANTIC_FIELDS_TO_TRACK}


def ensure_document_provenance(document: dict[str, Any]) -> dict[str, Any]:
    from core.semantic_pipeline import SEMANTIC_PIPELINE_VERSION

    semantic_mode = infer_cached_semantic_mode(document)
    document["semantic_mode"] = semantic_mode

    llm_payload = document.get("llm") if isinstance(document.get("llm"), dict) else {}
    raw_presence = document.get("raw_field_presence") if isinstance(document.get("raw_field_presence"), dict) else None
    if raw_presence is None:
        raw_presence = llm_payload.get("raw_field_presence") if isinstance(llm_payload.get("raw_field_presence"), dict) else {}
    document["raw_field_presence"] = raw_presence

    field_sources = document.get("field_sources") if isinstance(document.get("field_sources"), dict) else {}
    for field, source in default_field_sources_for(document, semantic_mode, raw_presence).items():
        field_sources.setdefault(field, source)
    document["field_sources"] = field_sources

    document.setdefault("semantic_pipeline_version", SEMANTIC_PIPELINE_VERSION)
    document.setdefault("llm_failure", None)
    return document


def source_mode_for_document(document: dict[str, Any]) -> str:
    semantic_mode = str(document.get("semantic_mode") or "")
    task_source = str((document.get("field_sources") or {}).get("task_frames") or "")
    if task_source in {"llm_raw_task_frame", "generated_from_llm_fields", "heuristic_rule_frame"}:
        return task_source
    if semantic_mode == "llm":
        return "generated_from_llm_fields"
    if semantic_mode == "structured_exam":
        return "exam_structured_data"
    if semantic_mode == "guarded_metadata":
        return "guarded_metadata_empty"
    if semantic_mode in {"heuristic", "heuristic_degraded"}:
        return "heuristic_rule_frame"
    return "unprocessed"


def normalize_existing_task_frames(document: dict[str, Any]) -> None:
    frames = document.get("task_frames")
    if not isinstance(frames, list):
        document["task_frames"] = []
        return
    source_mode = source_mode_for_document(document)
    field_sources = document.get("field_sources") if isinstance(document.get("field_sources"), dict) else {}
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        if not frame.get("source_mode") or frame.get("source_mode") == "unknown":
            frame["source_mode"] = source_mode
        if not isinstance(frame.get("field_sources"), dict) or not frame.get("field_sources"):
            frame["field_sources"] = field_sources


def unique_text_values(values: list[Any], limit: int = 32) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_text(str(value or ""))
        if not text:
            continue
        key = re.sub(r"\s+", "", text).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def frame_list(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [frame for frame in document.get("task_frames", []) or [] if isinstance(frame, dict)]


def query_alias_synonyms_for_document(document: dict[str, Any], query_aliases: dict[str, Any]) -> list[str]:
    recall_text = " ".join(
        [
            str(document.get("title") or ""),
            str(document.get("summary") or ""),
            " ".join(str(item) for item in document.get("tags", []) or []),
            " ".join(str(item) for item in document.get("required_materials", []) or []),
        ]
    )
    normalized_text = re.sub(r"\s+", "", recall_text).lower()
    values: list[str] = []
    for key, payload in (query_aliases or {}).items():
        if not isinstance(payload, dict):
            continue
        aliases = [str(item) for item in payload.get("aliases", []) or []]
        terms = [str(key), *aliases]
        text_match = any(re.sub(r"\s+", "", term).lower() in normalized_text for term in terms if term)
        if text_match:
            values.extend(terms)
    return unique_text_values(values, limit=40)


def build_notice_card(document: dict[str, Any]) -> dict[str, Any]:
    frames = frame_list(document)
    actions: list[Any] = [document.get("action_type"), document.get("action_summary")]
    objects: list[Any] = [document.get("title")]
    deadlines: list[Any] = [document.get("deadline")]
    materials: list[Any] = list(document.get("required_materials") or [])
    locations: list[Any] = []
    evidence: list[Any] = list(document.get("evidence") or [])

    for frame in frames:
        action = frame.get("action") if isinstance(frame.get("action"), dict) else {}
        time_payload = frame.get("time") if isinstance(frame.get("time"), dict) else {}
        location = frame.get("location") if isinstance(frame.get("location"), dict) else {}
        objects.extend([frame.get("what"), action.get("object")])
        actions.extend([action.get("verb"), action.get("summary")])
        deadlines.append(time_payload.get("deadline"))
        materials.extend(
            item.get("name")
            for item in frame.get("materials", []) or []
            if isinstance(item, dict)
        )
        locations.extend([location.get("place"), location.get("online"), location.get("contact")])
        evidence.extend(
            item.get("text")
            for item in frame.get("evidence", []) or []
            if isinstance(item, dict)
        )

    attachments = [
        {
            "name": attachment.get("name"),
            "url": attachment.get("url"),
            "type": attachment.get("type"),
            "role": attachment.get("role"),
            "description": attachment.get("description"),
            "sensitive": bool(attachment.get("sensitive", False)),
        }
        for attachment in document.get("attachments", []) or []
        if isinstance(attachment, dict)
    ]
    guard = document.get("rule_guard") if isinstance(document.get("rule_guard"), dict) else {}
    deadline_values = unique_text_values(deadlines, limit=8)
    return {
        "title": document.get("title"),
        "summary": document.get("summary"),
        "source": {
            "source_id": document.get("source_id"),
            "channel_id": document.get("channel_id"),
            "name": document.get("source"),
            "channel": document.get("channel"),
            "url": document.get("url"),
            "published_at": document.get("published_at"),
        },
        "audience": list(document.get("audience") or []),
        "category": document.get("category"),
        "domain": document.get("domain"),
        "intent": document.get("intent"),
        "objects": unique_text_values(objects, limit=20),
        "actions": unique_text_values(actions, limit=20),
        "deadline": deadline_values[0] if deadline_values else None,
        "deadlines": deadline_values,
        "materials": unique_text_values(materials, limit=24),
        "locations": unique_text_values(locations, limit=16),
        "attachments": attachments,
        "risk": {
            "sensitive": bool(document.get("sensitive")),
            "review_required": bool(document.get("review_required")),
            "restricted": bool(document.get("status") == "restricted" or guard.get("restricted")),
            "low_evidence": bool(guard.get("low_evidence")),
            "risk_flags": list(document.get("risk_flags") or []),
        },
        "evidence": unique_text_values(evidence, limit=20),
    }


def build_typed_search_terms(document: dict[str, Any], synonyms: list[str]) -> list[dict[str, str]]:
    terms: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(term_type: str, value: Any, source: str) -> None:
        text = clean_text(str(value or ""))
        if not text:
            return
        key = (term_type, re.sub(r"\s+", "", text).lower())
        if key in seen:
            return
        seen.add(key)
        terms.append({"type": term_type, "term": text, "source": source})

    for term_type, values, source in (
        ("title", [document.get("title")], "source"),
        ("summary", [document.get("summary")], "evidence"),
        ("source", [document.get("source"), document.get("channel"), document.get("source_id"), document.get("channel_id")], "source"),
        ("category", [document.get("category"), document.get("domain"), document.get("intent")], "semantic"),
        ("audience", list(document.get("audience") or []), "semantic"),
        ("tag", list(document.get("tags") or []), "semantic"),
        ("material", list(document.get("required_materials") or []), "semantic"),
        ("evidence", list(document.get("evidence") or []), "evidence"),
        ("synonym", synonyms, "query_aliases"),
    ):
        for value in values:
            add(term_type, value, source)

    for attachment in document.get("attachments", []) or []:
        if isinstance(attachment, dict):
            add("attachment", attachment.get("name"), "source")
            add("attachment", attachment.get("description"), "source")

    for frame in frame_list(document):
        action = frame.get("action") if isinstance(frame.get("action"), dict) else {}
        time_payload = frame.get("time") if isinstance(frame.get("time"), dict) else {}
        location = frame.get("location") if isinstance(frame.get("location"), dict) else {}
        add("object", frame.get("what"), "task_frame")
        add("object", action.get("object"), "task_frame")
        add("action", action.get("verb"), "task_frame")
        add("action", action.get("summary"), "task_frame")
        add("deadline", time_payload.get("deadline"), "task_frame")
        add("location", location.get("place"), "task_frame")
        add("location", location.get("online"), "task_frame")
        add("location", location.get("contact"), "task_frame")
        for material in frame.get("materials", []) or []:
            if isinstance(material, dict):
                add("material", material.get("name"), "task_frame")
        for evidence in frame.get("evidence", []) or []:
            if isinstance(evidence, dict):
                add("evidence", evidence.get("text"), "task_frame")
    return terms[:120]


def attach_notice_card_and_terms(document: dict[str, Any], query_aliases: dict[str, Any]) -> dict[str, Any]:
    doc = dict(document)
    synonyms = query_alias_synonyms_for_document(doc, query_aliases)
    doc["notice_card"] = build_notice_card(doc)
    doc["synonyms"] = synonyms
    doc["typed_search_terms"] = build_typed_search_terms(doc, synonyms)
    return doc


def finalize_hytask_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    finalized: list[dict[str, Any]] = []
    seen_dedupe: set[str] = set()
    for document in documents:
        doc = dict(document)
        doc = ensure_document_provenance(doc)
        doc["source_type"] = normalize_source_type(doc.get("source_type"))
        doc["domain"] = normalize_domain(doc.get("domain"))
        doc["intent"] = normalize_intent(doc.get("intent"))
        if not doc.get("source_id"):
            doc["source_id"] = infer_source_id_from_document(doc)
        if not doc.get("channel_id"):
            doc["channel_id"] = f"{doc['source_id']}_default"
        if not doc.get("channel"):
            doc["channel"] = "默认公开栏目"
        if not doc.get("canonical"):
            canonical = canonicalize_raw_document(RawDocument(
                raw_id=str(doc.get("id")),
                source_id=str(doc.get("source_id")),
                channel_id=str(doc.get("channel_id")),
                url=str(doc.get("url")),
                title=str(doc.get("title")),
                raw_text=str(doc.get("content") or doc.get("summary") or doc.get("title")),
                fetched_at=get_beijing_time().isoformat(),
                http_status=200,
                published_at=doc.get("published_at"),
                attachments=list(doc.get("attachments") or []),
            ), base_url=str(doc.get("url") or ""))
            doc["canonical"] = canonical.model_dump()
        if not doc.get("rule_guard"):
            doc["rule_guard"] = evaluate_rule_guard(
                title=str(doc.get("title", "")),
                content=str(doc.get("content", "")),
                attachments=list(doc.get("attachments") or []),
                published_at=doc.get("published_at"),
                lifecycle=doc.get("lifecycle"),
                domain=doc.get("domain"),
                intent=doc.get("intent"),
                source_type=doc.get("source_type"),
            )
        dedupe_key = str((doc.get("canonical") or {}).get("dedupe_key") or doc.get("hash") or doc.get("id"))
        duplicate = dedupe_key in seen_dedupe
        seen_dedupe.add(dedupe_key)
        if duplicate:
            doc["rule_guard"]["duplicate"] = True
            doc["rule_guard"]["risk_flags"] = sorted(set(doc["rule_guard"].get("risk_flags", []) + ["duplicate"]))
        doc["review_required"] = bool(doc.get("review_required") or doc["rule_guard"].get("review_required"))
        doc["sensitive"] = bool(doc.get("sensitive") or doc["rule_guard"].get("sensitive"))
        doc["risk_flags"] = sorted(set(list(doc.get("risk_flags") or []) + list(doc["rule_guard"].get("risk_flags") or [])))
        if doc["rule_guard"].get("restricted"):
            doc["status"] = "restricted"
            doc["action_required"] = False
            doc["summary"] = restricted_summary()
        if not doc.get("task_frames"):
            doc["task_frames"] = extract_task_frames(doc, llm_result=None, rule_guard=doc["rule_guard"])
        normalize_existing_task_frames(doc)
        doc = verify_search_document(doc)
        finalized.append(doc)
    return finalized


def infer_source_id_from_document(document: dict[str, Any]) -> str:
    source_domain = str(document.get("source_domain") or "")
    source = str(document.get("source") or "")
    for candidate in SOURCES:
        if candidate.id in source or candidate.name == source or urlparse(candidate.base_url).netloc == source_domain:
            return candidate.id
    if str(document.get("source_type")) == "github_resource":
        return f"github:{source}"
    return "unknown"


def calculate_evidence_coverage(task_frames: list[dict[str, Any]]) -> dict[str, Any]:
    fields = ["audience", "action", "deadline", "materials", "location", "sensitive"]
    if not task_frames:
        return {"overall": 0, **{field: 0 for field in fields}}
    coverage: dict[str, float] = {}
    for field in fields:
        count = 0
        applicable = 0
        for frame in task_frames:
            evidence = frame.get("evidence") if isinstance(frame.get("evidence"), list) else []
            if not evidence_field_applicable(frame, field):
                continue
            applicable += 1
            if any(isinstance(item, dict) and str(item.get("field", "")).lower() == field for item in evidence):
                count += 1
            elif field == "action" and (frame.get("action") or {}).get("summary") and evidence:
                count += 1
            elif field == "deadline" and (frame.get("time") or {}).get("deadline") and evidence:
                count += 1
            elif field == "audience" and (frame.get("who") or {}).get("audience") and evidence:
                count += 1
        coverage[field] = round(count / applicable, 4) if applicable else 0.0
    applicable_values = [
        coverage[field]
        for field in fields
        if any(evidence_field_applicable(frame, field) for frame in task_frames)
    ]
    coverage["overall"] = round(sum(applicable_values) / len(applicable_values), 4) if applicable_values else 0
    return coverage


def evidence_field_applicable(frame: dict[str, Any], field: str) -> bool:
    if field == "audience":
        return bool((frame.get("who") or {}).get("audience"))
    if field == "action":
        action = frame.get("action") or {}
        return bool(action.get("summary") or action.get("verb") or action.get("required"))
    if field == "deadline":
        return bool((frame.get("time") or {}).get("deadline"))
    if field == "materials":
        return bool(frame.get("materials"))
    if field == "location":
        location = frame.get("location") or {}
        return bool(location.get("place") or location.get("online") or location.get("contact"))
    if field == "sensitive":
        return bool((frame.get("risk") or {}).get("sensitive"))
    return False


def verifier_removal_counts(documents: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for document in documents:
        verifier = document.get("semantic_verifier") if isinstance(document.get("semantic_verifier"), dict) else {}
        removals = verifier.get("removals") if isinstance(verifier.get("removals"), dict) else {}
        for field, value in removals.items():
            try:
                counts[str(field)] += int(value)
            except (TypeError, ValueError):
                counts[str(field)] += 1
    return dict(sorted(counts.items()))


def field_grounding_metrics(documents: list[dict[str, Any]], removals: dict[str, int]) -> dict[str, Any]:
    total = max(1, len(documents))
    field_getters = {
        "deadline": lambda doc: bool(doc.get("deadline")),
        "action_required": lambda doc: bool(doc.get("action_required")),
        "required_materials": lambda doc: bool(doc.get("required_materials")),
        "task_frames": lambda doc: bool(doc.get("task_frames")),
    }
    non_null_rates: dict[str, float] = {}
    grounded_rates: dict[str, float] = {}
    for field, getter in field_getters.items():
        non_null = sum(1 for document in documents if getter(document))
        non_null_rates[field] = round(non_null / total, 4)
        removed = int(removals.get(field, 0) or removals.get(f"task_frame_{field}", 0) or 0)
        grounded_rates[field] = round(max(0, non_null - removed) / non_null, 4) if non_null else 0.0
    return {
        "non_null_field_rates": non_null_rates,
        "grounded_field_rates": grounded_rates,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the njupt-search campus search index.")
    parser.add_argument("--force-llm", action="store_true", help="Ignore cached LLM enrichments and reprocess documents.")
    parser.add_argument("--llm-schema-version", default=LLM_SCHEMA_VERSION, help="Override the LLM schema/cache version.")
    parser.add_argument("--llm-provider", choices=["auto", "deepseek", "gemini"], default="auto", help="LLM provider preference. auto prefers DeepSeek, then Gemini.")
    parser.add_argument("--llm-batch-size", type=int, default=LLM_BATCH_MAX_DOCS, help="Maximum documents per LLM batch.")
    parser.add_argument("--llm-batch-max-chars", type=int, default=LLM_BATCH_MAX_CHARS, help="Maximum approximate characters per LLM batch.")
    parser.add_argument("--llm-batch-max-output-tokens", type=int, default=LLM_BATCH_MAX_OUTPUT_TOKENS, help="Maximum output tokens for one LLM batch.")
    parser.add_argument("--source", action="append", default=[], help="Only crawl the given source id. Can be repeated.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of documents to send to LLM in this run.")
    parser.add_argument("--dry-run", action="store_true", help="Run crawling/enrichment without writing index files.")
    parser.add_argument("--no-github", action="store_true", help="Skip GitHub resource sources.")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM enrichment and use rule fallbacks only.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    _RUN_CONFIG.update({
        "force_llm": bool(args.force_llm),
        "no_llm": bool(args.no_llm),
        "llm_schema_version": str(args.llm_schema_version or LLM_SCHEMA_VERSION),
        "source_filter": set(args.source or []),
        "llm_limit": args.limit,
        "dry_run": bool(args.dry_run),
        "no_github": bool(args.no_github),
        "llm_provider": str(args.llm_provider or "auto"),
        "llm_batch_size": max(1, int(args.llm_batch_size or LLM_BATCH_MAX_DOCS)),
        "llm_batch_max_chars": max(2000, int(args.llm_batch_max_chars or LLM_BATCH_MAX_CHARS)),
        "llm_batch_max_output_tokens": max(1024, int(args.llm_batch_max_output_tokens or LLM_BATCH_MAX_OUTPUT_TOKENS)),
    })
    load_document_cache()
    load_llm_cache()
    os.makedirs(INDEX_DIR, exist_ok=True)
    now = get_beijing_time()
    all_documents: list[dict[str, Any]] = []
    source_entries: list[dict[str, Any]] = []

    for source in SOURCES:
        if not source_selected(source.id):
            continue
        documents, manifest_entry = crawl_source(source, now)
        all_documents.extend(documents)
        source_entries.append(manifest_entry)

    if not _RUN_CONFIG["no_github"]:
        for source in read_github_source_configs():
            github_id = f"github:{source.repo}"
            if not source_selected(github_id):
                continue
            documents, manifest_entry = crawl_github_resource_source(source, now)
            all_documents.extend(documents)
            source_entries.append(manifest_entry)

    all_documents = deduplicate_documents(all_documents)
    all_documents = finalize_hytask_documents(all_documents)
    query_aliases = read_json_file(QUERY_ALIASES_PATH, {})
    ontology = read_json_file(ONTOLOGY_PATH, {})
    all_documents = [attach_notice_card_and_terms(document, query_aliases) for document in all_documents]
    task_frames = [frame for document in all_documents for frame in document.get("task_frames", [])]
    all_documents.sort(
        key=lambda item: (
            item.get("published_at") or "",
            item.get("id") or "",
        ),
        reverse=True,
    )
    source_graph = load_source_channel_graph(SOURCE_CHANNEL_CONFIG_PATH)
    evidence_coverage = calculate_evidence_coverage(task_frames)
    semantic_verifier_removals = verifier_removal_counts(all_documents)
    grounding_metrics = field_grounding_metrics(all_documents, semantic_verifier_removals)

    from core.semantic_pipeline import SEMANTIC_PIPELINE_VERSION

    semantic_mode_counts: dict[str, int] = {}
    for document in all_documents:
        mode = str(document.get("semantic_mode") or "unprocessed")
        semantic_mode_counts[mode] = semantic_mode_counts.get(mode, 0) + 1
    for mode in ("llm", "heuristic", "heuristic_degraded", "guarded_metadata", "unprocessed"):
        semantic_mode_counts.setdefault(mode, 0)

    field_source_counts = {field: {} for field in SEMANTIC_FIELDS_TO_TRACK}
    for doc in all_documents:
        sources = doc.get("field_sources", {})
        for field in SEMANTIC_FIELDS_TO_TRACK:
            src = sources.get(field, "null")
            field_source_counts[field][src] = field_source_counts[field].get(src, 0) + 1
            
    llm_missing_field_counts = {
        field: sum(1 for doc in all_documents if doc.get("field_sources", {}).get(field) == "llm_missing")
        for field in SEMANTIC_FIELDS_TO_TRACK
    }
    
    task_frame_source_mode_counts = {}
    for frame in task_frames:
        src_mode = frame.get("source_mode", "unknown")
        task_frame_source_mode_counts[src_mode] = task_frame_source_mode_counts.get(src_mode, 0) + 1
        
    training_eligible_count = sum(1 for d in all_documents if d.get("semantic_mode") == "llm" and not d.get("review_required") and float(d.get("confidence", 0) or 0) >= 0.8)
    heuristic_degraded_count = semantic_mode_counts.get("heuristic_degraded", 0)
    
    # llm_purity_rate: percentage of llm mode docs that don't have heuristic field sources
    llm_docs = [d for d in all_documents if d.get("semantic_mode") == "llm"]
    pure_llm_docs = sum(1 for d in llm_docs if "heuristic" not in d.get("field_sources", {}).values())
    llm_purity_rate = (pure_llm_docs / len(llm_docs)) if llm_docs else 0.0

    manifest = {
        "generated_at": now.isoformat(),
        "total_documents": len(all_documents),
        "strategy": "source-fidelity-offline-llm-card-recall-chronological-v1",
        "semantic_pipeline_version": SEMANTIC_PIPELINE_VERSION,
        "llm_schema_version": active_llm_schema_version(),
        "llm_enabled": runtime_llm_enabled(),
        "llm_provider": runtime_llm_provider_name(),
        "llm_model": runtime_llm_model_name(),
        "llm_batch_size": effective_llm_batch_size(),
        "llm_batch_max_chars": int(_RUN_CONFIG["llm_batch_max_chars"]),
        "llm_batch_max_output_tokens": effective_llm_batch_max_output_tokens(),
        "llm_stats": dict(_RUN_STATS),
        "semantic_mode_counts": semantic_mode_counts,
        "field_source_counts": field_source_counts,
        "task_frame_source_mode_counts": task_frame_source_mode_counts,
        "llm_missing_field_counts": llm_missing_field_counts,
        "training_eligible_count": training_eligible_count,
        "heuristic_degraded_count": heuristic_degraded_count,
        "llm_purity_rate": llm_purity_rate,
        "source_count": len(source_graph.sources),
        "channel_count": source_graph.channel_count(),
        "audited_channel_count": source_graph.audited_channel_count(),
        "production_channel_count": source_graph.production_channel_count(),
        "failed_channel_count": source_graph.failed_channel_count(),
        "task_frame_count": len(task_frames),
        "documents_with_task_frame": sum(1 for document in all_documents if document.get("task_frames")),
        "evidence_coverage": evidence_coverage,
        "non_null_field_rates": grounding_metrics["non_null_field_rates"],
        "grounded_field_rates": grounding_metrics["grounded_field_rates"],
        "verifier_removal_counts": semantic_verifier_removals,
        "task_frame_grounded_rate": evidence_coverage.get("overall", 0),
        "review_required_count": sum(1 for document in all_documents if document.get("review_required")),
        "low_evidence_count": sum(1 for document in all_documents if (document.get("rule_guard") or {}).get("low_evidence")),
        "restricted_count": sum(1 for document in all_documents if document.get("status") == "restricted" or (document.get("rule_guard") or {}).get("restricted")),
        "sensitive_count": sum(1 for document in all_documents if document.get("sensitive") or (document.get("rule_guard") or {}).get("sensitive")),
        "sources": source_entries,
    }

    if _RUN_CONFIG["dry_run"]:
        print(json.dumps({
            "generated_documents": len(all_documents),
            "source_count": len(source_entries),
            "llm_provider": runtime_llm_provider_name(),
            "llm_model": runtime_llm_model_name(),
            "llm_batch_size": effective_llm_batch_size(),
            "llm_stats": _RUN_STATS,
            "task_frame_count": len(task_frames),
            "channel_count": manifest["channel_count"],
            "evidence_coverage": evidence_coverage,
            "sources": source_entries,
        }, ensure_ascii=False, indent=2))
        return

    docs_changed = write_json_if_changed(DOCUMENTS_PATH, all_documents)
    tasks_changed = write_json_if_changed(TASK_FRAMES_PATH, task_frames)
    aliases_changed = write_json_if_changed(PUBLIC_QUERY_ALIASES_PATH, query_aliases)
    ontology_changed = write_json_if_changed(PUBLIC_ONTOLOGY_PATH, ontology)
    manifest_changed = write_json_if_changed(MANIFEST_PATH, manifest)
    llm_cache_changed = save_llm_cache(now)
    print(f"Generated {len(all_documents)} search documents")
    print(f"Generated {len(task_frames)} task frames")
    print(f"documents.json changed: {docs_changed}; task_frames.json changed: {tasks_changed}; query_aliases.json changed: {aliases_changed}; ontology.json changed: {ontology_changed}; manifest.json changed: {manifest_changed}; LLM cache changed: {llm_cache_changed}")


if __name__ == "__main__":
    main()
