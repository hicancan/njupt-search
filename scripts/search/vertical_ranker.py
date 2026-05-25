import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from search.query_router import route_query, load_query_routes

ROUTES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "query_routes.json")
_cached_routes = None


def get_routes():
    global _cached_routes
    if _cached_routes is None:
        _cached_routes = load_query_routes(ROUTES_PATH)
    return _cached_routes


def recall_documents(
    query: str,
    documents: List[Dict[str, Any]],
    query_aliases: Dict[str, Any] | None = None,
    *,
    limit: int | None = None,
) -> List[Dict[str, Any]]:
    """Recall relevant candidates only; returned order is published_at desc."""
    trimmed = str(query or "").strip()
    if len(trimmed) < 2:
        return []

    route = route_query(trimmed, get_routes())
    terms = query_terms(trimmed, query_aliases or {})
    recalled: List[Dict[str, Any]] = []

    for document in documents:
        reasons = recall_reasons(document, trimmed, terms, route)
        if not reasons:
            continue
        recalled.append(
            {
                **document,
                "score": 1.0,
                "score_reason": recall_reason_text(document, reasons),
            }
        )

    recalled.sort(key=lambda item: (-date_sort_value(item.get("published_at")), str(item.get("id") or "")))
    return recalled[: limit or 30]


def vertical_rank_documents(
    query: str,
    documents: List[Dict[str, Any]],
    query_aliases: Dict[str, Any] | None = None,
    *,
    limit: int | None = None,
) -> List[Dict[str, Any]]:
    """Legacy entry point kept for older eval callers; it no longer ranks."""
    return recall_documents(query, documents, query_aliases or {}, limit=limit)


def normalize(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").lower())


def tokenize(query: str) -> List[str]:
    normalized = str(query or "").strip()
    if not normalized:
        return []
    parts = [part.strip() for part in re.split(r"[\s,，、/|]+", normalized) if part.strip()]
    return parts if parts else [normalized]


def query_terms(query: str, query_aliases: Dict[str, Any]) -> List[str]:
    normalized_query = normalize(query)
    terms: List[str] = tokenize(query)
    for key, payload in (query_aliases or {}).items():
        aliases = [str(item) for item in payload.get("aliases", [])] if isinstance(payload, dict) else []
        candidates = [key, *aliases]
        if any(normalize(candidate) and normalize(candidate) in normalized_query for candidate in candidates):
            terms.extend(aliases)
    return list(dict.fromkeys(term for term in terms if str(term).strip()))


def collect_strings(value: Any, *, limit: int = 120) -> List[str]:
    result: List[str] = []

    def visit(item: Any) -> None:
        if len(result) >= limit or item is None:
            return
        if isinstance(item, (str, int, float, bool)):
            text = str(item).strip()
            if text:
                result.append(text)
            return
        if isinstance(item, list):
            for child in item:
                visit(child)
            return
        if isinstance(item, dict):
            for child in item.values():
                visit(child)

    visit(value)
    return result


def task_frame_text(document: Dict[str, Any]) -> str:
    parts: List[str] = []
    for frame in document.get("task_frames", []) or []:
        if not isinstance(frame, dict):
            continue
        action = frame.get("action") if isinstance(frame.get("action"), dict) else {}
        time = frame.get("time") if isinstance(frame.get("time"), dict) else {}
        location = frame.get("location") if isinstance(frame.get("location"), dict) else {}
        parts.extend(
            [
                str(frame.get("what") or ""),
                str(action.get("summary") or ""),
                str(action.get("verb") or ""),
                str(action.get("object") or ""),
                str(time.get("deadline") or ""),
                str(location.get("place") or ""),
                str(location.get("online") or ""),
                str(location.get("contact") or ""),
            ]
        )
        parts.extend(str(item.get("name") or "") for item in frame.get("materials", []) or [] if isinstance(item, dict))
        parts.extend(str(item.get("text") or "") for item in frame.get("evidence", []) or [] if isinstance(item, dict))
    return " ".join(part for part in parts if part)


def document_recall_text(document: Dict[str, Any]) -> str:
    llm = document.get("llm") if isinstance(document.get("llm"), dict) else {}
    parts: List[str] = [
        str(document.get("title") or ""),
        str(document.get("summary") or ""),
        str(document.get("content") or ""),
        str(document.get("source") or ""),
        str(document.get("source_id") or ""),
        str(document.get("channel") or ""),
        str(document.get("channel_id") or ""),
        str(document.get("source_domain") or ""),
        str(document.get("domain") or ""),
        str(document.get("intent") or ""),
        str(document.get("source_type") or ""),
        str(document.get("class_name") or ""),
        task_frame_text(document),
    ]
    parts.extend(str(item) for item in document.get("tags", []) or [])
    parts.extend(str(item) for item in document.get("evidence", []) or [])
    parts.extend(str(item) for item in document.get("required_materials", []) or [])
    for attachment in document.get("attachments", []) or []:
        if isinstance(attachment, dict):
            parts.extend(str(attachment.get(key) or "") for key in ("name", "role", "description"))
    parts.extend(collect_strings(document.get("typed_search_terms")))
    parts.extend(collect_strings(document.get("synonyms")))
    parts.extend(collect_strings(document.get("notice_card")))
    parts.extend(collect_strings([llm.get("semantic_queries"), llm.get("query_phrases"), llm.get("search_profile")]))
    return " ".join(part for part in parts if part)


def contains_any(text: str, terms: Iterable[Any]) -> bool:
    return any(normalize(term) and normalize(term) in text for term in terms)


def route_rejects_document(document: Dict[str, Any], route: Dict[str, Any], normalized_text: str) -> bool:
    blocked_domains = set(route.get("blocked_domains_for_top5", []) or [])
    blocked_sources = {normalize(item) for item in route.get("blocked_sources_for_top5", []) or []}
    if str(document.get("domain")) in blocked_domains:
        return True
    if normalize(document.get("source")) in blocked_sources or normalize(document.get("source_id")) in blocked_sources:
        return True
    if not route.get("allow_resource_top5", True) and document.get("source_type") == "github_resource":
        return True
    if contains_any(normalized_text, route.get("bad_result_terms", []) or []):
        return True
    must_include = route.get("must_include_terms_for_top_results", []) or []
    if must_include and not contains_any(normalized_text, must_include):
        return True
    return False


def recall_reasons(document: Dict[str, Any], query: str, terms: List[str], route: Dict[str, Any]) -> List[str]:
    normalized_text = normalize(document_recall_text(document))
    if route_rejects_document(document, route, normalized_text):
        return []

    normalized_query = normalize(query)
    title = normalize(document.get("title"))
    reasons: List[str] = []
    if normalized_query and normalized_query in title:
        reasons.append("标题命中")

    matched_terms = [term for term in terms if normalize(term) and normalize(term) in normalized_text][:6]
    if matched_terms:
        reasons.append("关键词/同义词: " + "、".join(matched_terms))
    if document.get("domain") in set(route.get("target_domains", []) or []):
        reasons.append("领域: " + str(document.get("domain")))
    if document.get("intent") in set(route.get("target_intents", []) or []):
        reasons.append("动作: " + str(document.get("intent")))

    if (matched_terms or (normalized_query and normalized_query in title)) and reasons:
        return reasons
    return []


def recall_reason_text(document: Dict[str, Any], reasons: List[str]) -> str:
    source = " · ".join(str(document.get(key) or "") for key in ("source", "channel") if document.get(key))
    return "；".join([*reasons, source, "按发布时间倒序"])


def parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value)
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def date_sort_value(value: Any) -> float:
    dt = parse_date(value)
    return dt.timestamp() * 1000 if dt else 0.0
