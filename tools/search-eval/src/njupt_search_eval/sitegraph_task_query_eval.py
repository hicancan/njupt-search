from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .sitegraph_search import BASE_DIR, recall_documents_with_stats


QUERY_DIR = BASE_DIR / "tools" / "search-eval" / "queries"
EXPECTED_RESULTS_PATH = QUERY_DIR / "expected_results.json"
EXAM_DATA_PATH = BASE_DIR / "apps" / "web" / "public" / "generated" / "exam" / "all_exams.json"
CLASS_LOOKUP_PATTERN = re.compile(r"^[BFPQY]\d{2,}(?:\([A-Z0-9]+\))?$", re.IGNORECASE)
COMPLETE_CLASS_PATTERN = re.compile(r"^[BFPQY]\d{6}(?:\([A-Z0-9]+\))?$", re.IGNORECASE)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def fail(message: str, payload: Any | None = None) -> None:
    print(f"[sitegraph_task_query_eval] {message}", file=sys.stderr)
    if payload is not None:
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
    raise SystemExit(1)


def effective_date_value(item: dict[str, Any]) -> float:
    for field in ("published_at", "version_date"):
        value = item.get(field)
        if not value:
            continue
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        except ValueError:
            continue
    return 0.0


def text_contains_any(value: Any, expected: list[Any]) -> bool:
    text = str(value or "")
    return any(str(part) in text for part in expected)


def item_matches(item: dict[str, Any], check: dict[str, Any]) -> bool:
    if check.get("source_id") and item.get("source_id") != check["source_id"]:
        return False
    if check.get("facet") and item.get("facet") != check["facet"]:
        return False
    if check.get("record_type") and item.get("record_type") != check["record_type"]:
        return False
    if check.get("task_kind") and item.get("task_kind") != check["task_kind"]:
        return False
    if check.get("title_contains_any") and not text_contains_any(item.get("title"), check["title_contains_any"]):
        return False
    if check.get("title_equals_any") and str(item.get("title") or "") not in {str(value) for value in check["title_equals_any"]}:
        return False
    if check.get("nav_contains_any") and not text_contains_any(item.get("nav_path_text"), check["nav_contains_any"]):
        return False
    if check.get("url_regex") and re.search(str(check["url_regex"]), str(item.get("url") or "")) is None:
        return False
    if check.get("min_effective_date"):
        try:
            minimum = datetime.fromisoformat(str(check["min_effective_date"])).timestamp()
        except ValueError:
            minimum = 0.0
        if effective_date_value(item) < minimum:
            return False
    return True


def class_search_result(exams: list[dict[str, Any]], query: str) -> dict[str, Any]:
    normalized = query.strip().upper()
    if len(normalized) < 2 or CLASS_LOOKUP_PATTERN.match(normalized) is None:
        return {"mode": "EMPTY", "classes": [], "exams": []}
    matched_exams = [
        item for item in exams
        if normalized in str(item.get("class_name") or "").upper()
    ]
    classes = sorted({str(item.get("class_name") or "") for item in matched_exams if item.get("class_name")})
    if not classes:
        return {"mode": "NOT_FOUND", "classes": [], "exams": []}
    if len(classes) == 1 and COMPLETE_CLASS_PATTERN.match(normalized) is not None:
        return {"mode": "DETAIL", "classes": classes, "exams": matched_exams}
    return {"mode": "LIST", "classes": classes, "exams": []}


def validate_exam_vertical_expectation(expectation: dict[str, Any]) -> dict[str, Any]:
    query = str(expectation.get("query") or "")
    exams = read_json(EXAM_DATA_PATH)
    if not isinstance(exams, list):
        fail("exam all_exams.json must contain a list")
    result = class_search_result(exams, query)
    expected_mode = str(expectation.get("exam_mode") or "DETAIL")
    failures: dict[str, Any] = {}
    if result["mode"] != expected_mode:
        failures["mode"] = {"expected": expected_mode, "actual": result["mode"]}
    class_contains = expectation.get("class_contains")
    if class_contains and not any(str(class_contains).upper() in item.upper() for item in result["classes"]):
        failures["class_contains"] = {"expected": class_contains, "actual": result["classes"][:12]}
    min_exam_count = int(expectation.get("min_exam_count") or 1)
    if expected_mode == "DETAIL" and len(result["exams"]) < min_exam_count:
        failures["min_exam_count"] = {"expected": min_exam_count, "actual": len(result["exams"])}
    if failures:
        fail(f"{query}: exam vertical expectation failed", failures)
    return {
        "query": query,
        "status": "passed_exam_vertical",
        "mode": result["mode"],
        "class_count": len(result["classes"]),
        "exam_count": len(result["exams"]),
        "first_class": result["classes"][0] if result["classes"] else None,
    }


def summarize_result(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": item.get("title"),
        "source_id": item.get("source_id"),
        "facet": item.get("facet"),
        "record_type": item.get("record_type"),
        "published_at": item.get("published_at"),
        "version_date": item.get("version_date"),
        "task_kind": item.get("task_kind"),
        "nav_path": item.get("nav_path_text"),
        "url": item.get("url"),
        "score": item.get("score"),
        "score_reason": item.get("score_reason"),
    }


def validate_expectation(expectation: dict[str, Any], *, default_limit: int) -> dict[str, Any]:
    query = str(expectation.get("query") or "")
    if not query:
        fail("expected_results entry missing query", expectation)
    if expectation.get("expected_vertical") == "exam":
        return validate_exam_vertical_expectation(expectation)
    payload = recall_documents_with_stats(query, limit=int(expectation.get("limit") or default_limit))
    results = payload["results"]
    stats = payload["stats"]

    if expectation.get("allow_empty") and not results:
        return {"query": query, "status": "passed_empty", "result_count": 0}
    if not results:
        fail(f"{query}: expected results but got none")

    failures: dict[str, Any] = {}
    top1 = expectation.get("top1")
    if isinstance(top1, dict) and not item_matches(results[0], top1):
        failures["top1"] = {"expected": top1, "actual": summarize_result(results[0])}

    top_n = expectation.get("top_n")
    if isinstance(top_n, dict):
        n = int(top_n.get("n") or 5)
        check = {key: value for key, value in top_n.items() if key != "n"}
        match = next((item for item in results[:n] if item_matches(item, check)), None)
        if match is None:
            failures["top_n"] = {
                "expected": top_n,
                "actual": [summarize_result(item) for item in results[:n]],
            }

    forbid = expectation.get("forbid_top_n")
    if isinstance(forbid, dict):
        n = int(forbid.get("n") or 5)
        check = {key: value for key, value in forbid.items() if key != "n"}
        forbidden = [item for item in results[:n] if item_matches(item, check)]
        if forbidden:
            failures["forbid_top_n"] = {
                "expected_absent": forbid,
                "actual": [summarize_result(item) for item in forbidden],
            }

    coverage = stats.get("coverage") or {}
    if coverage.get("exhaustive_complete") is not True:
        failures["coverage"] = coverage
    if failures:
        fail(f"{query}: task query expectation failed", failures)
    return {
        "query": query,
        "status": "passed",
        "top_title": results[0].get("title"),
        "top_source_id": results[0].get("source_id"),
        "top_facet": results[0].get("facet"),
        "top_score": results[0].get("score"),
        "loaded_shard_count": stats.get("loaded_shard_count"),
        "candidate_shard_count": stats.get("candidate_shard_count"),
    }


def validate_task_queries(path: Path = EXPECTED_RESULTS_PATH) -> dict[str, Any]:
    config = read_json(path)
    expectations = config.get("expectations")
    if not isinstance(expectations, list) or not expectations:
        fail("expected_results.json must contain a non-empty expectations list")
    default_limit = int((config.get("defaults") or {}).get("limit") or 12)
    summaries = [validate_expectation(item, default_limit=default_limit) for item in expectations]
    return {
        "expectation_count": len(expectations),
        "passed": len(summaries),
        "queries": summaries,
    }
