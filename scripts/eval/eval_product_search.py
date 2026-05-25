import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))

from search.vertical_ranker import vertical_rank_documents
from search.query_router import route_query, load_query_routes

BEIJING_TZ = timezone(timedelta(hours=8))

STATUS_STRICT_PASS = "strict_pass"
STATUS_DATA_GAP = "data_gap"
STATUS_FAIL = "fail"


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_documents() -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    documents = load_json(os.path.join(BASE_DIR, "public", "index", "documents.json"))
    return documents, {str(doc.get("id", "")): doc for doc in documents}


def _norm(value: Any) -> str:
    return str(value or "").lower()


def _doc_text(doc: Dict[str, Any]) -> str:
    parts: List[str] = [
        str(doc.get("title", "")),
        str(doc.get("summary", "")),
        str(doc.get("content", "")),
        str(doc.get("source", "")),
        str(doc.get("source_id", "")),
        str(doc.get("channel", "")),
        str(doc.get("channel_id", "")),
        str(doc.get("domain", "")),
        str(doc.get("intent", "")),
    ]
    parts.extend(str(item) for item in doc.get("tags", []) or [])
    parts.extend(str(item) for item in doc.get("evidence", []) or [])
    return " ".join(parts).lower()


def _doc_display_text(doc: Dict[str, Any]) -> str:
    parts: List[str] = [
        str(doc.get("title", "")),
        str(doc.get("summary", "")),
    ]
    parts.extend(str(item) for item in doc.get("tags", []) or [])
    return " ".join(parts).lower()


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(_norm(term) in text for term in terms if str(term).strip())


def _matches_all_groups(text: str, groups: Iterable[Iterable[str]]) -> bool:
    return all(_contains_any(text, group) for group in groups)


def _terms(case: Dict[str, Any], *keys: str) -> List[str]:
    result: List[str] = []
    for key in keys:
        result.extend(str(item) for item in case.get(key, []) or [])
    return result


def _is_relevant(doc: Dict[str, Any], case: Dict[str, Any]) -> bool:
    text = _doc_text(doc)
    groups = case.get("relevance_terms_all_groups", []) or []
    any_terms = _terms(case, "relevance_terms_any")

    if groups and not _matches_all_groups(text, groups):
        return False
    if any_terms and not _contains_any(text, any_terms):
        return False

    # Backward-compatible fields are treated as weak relevance only when the
    # v1.3 fields are absent.
    if not groups and not any_terms:
        legacy_terms = _terms(case, "top3_must_include_any_terms", "top5_must_include_any_terms")
        if legacy_terms:
            return _contains_any(text, legacy_terms)
    return True


def _source_matches(doc: Dict[str, Any], expected: str) -> bool:
    values = {str(doc.get("source", "")), str(doc.get("source_id", ""))}
    return any(value == expected or value.startswith(f"{expected}:") for value in values)


def _source_matches_any(doc: Dict[str, Any], expected_values: Iterable[str]) -> bool:
    return any(_source_matches(doc, str(expected)) for expected in expected_values)


def _simplify_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": doc.get("id"),
        "title": doc.get("title"),
        "domain": doc.get("domain"),
        "intent": doc.get("intent"),
        "source": doc.get("source"),
        "source_id": doc.get("source_id"),
        "channel_id": doc.get("channel_id"),
        "kind": doc.get("kind"),
    }


def _load_manifest_channels() -> Dict[str, Dict[str, Any]]:
    manifest = load_json(os.path.join(BASE_DIR, "public", "index", "manifest.json"))
    channels: Dict[str, Dict[str, Any]] = {}
    for source in manifest.get("sources", []) or []:
        for channel in source.get("channels", []) or []:
            channels[str(channel.get("id"))] = {
                **channel,
                "source_id": source.get("id"),
                "source_name": source.get("name"),
            }
    return channels


def _coverage_gap_channels(
    case: Dict[str, Any],
    notice_documents: List[Dict[str, Any]],
    channels: Dict[str, Dict[str, Any]],
) -> List[str]:
    coverage_channels = [str(item) for item in case.get("coverage_channels", []) or []]
    if not coverage_channels:
        return []

    gap_channels: List[str] = []
    for channel_id in coverage_channels:
        channel = channels.get(channel_id, {})
        channel_docs = [doc for doc in notice_documents if str(doc.get("channel_id")) == channel_id]
        docs_count = int(channel.get("documents", len(channel_docs)) or 0)
        status = str(channel.get("status", "missing"))

        hard_empty = docs_count == 0 or status == "warning_filtered_all" or status == "missing"
        has_relevant_doc = any(_is_relevant(doc, case) for doc in channel_docs)
        if hard_empty or not has_relevant_doc:
            gap_channels.append(channel_id)

    return gap_channels


def _evaluate_result_set(
    case: Dict[str, Any],
    top5: List[Dict[str, Any]],
    route_ok: bool,
    route_obj: Dict[str, Any],
    label: str,
) -> Dict[str, Any]:
    reasons: List[str] = []
    top3 = top5[:3]
    top1 = top5[0] if top5 else None

    if not route_ok:
        reasons.append(f"{label}: route mismatch expected {case.get('route')}, got {route_obj.get('query_type')}")

    if not top5 and not case.get("allow_empty", False):
        reasons.append(f"{label}: top5 is empty")

    if top1:
        top1_source = case.get("top1_must_source")
        if top1_source and not _source_matches(top1, str(top1_source)):
            reasons.append(f"{label}: top1 source is {top1.get('source_id') or top1.get('source')}, expected {top1_source}")

        top1_domains = set(case.get("top1_must_domain_any", []) or [])
        if top1_domains and top1.get("domain") not in top1_domains:
            reasons.append(f"{label}: top1 domain {top1.get('domain')} not in {sorted(top1_domains)}")

        top1_terms = _terms(case, "top1_must_include_any_terms", "top1_should_include_any_terms")
        if top1_terms and not _contains_any(_doc_text(top1), top1_terms):
            reasons.append(f"{label}: top1 does not contain any of {top1_terms}")
    elif case.get("top1_must_source") or case.get("top1_must_include_any_terms"):
        reasons.append(f"{label}: top1 requirement cannot be checked because top5 is empty")

    top3_min = case.get("top3_min_relevant_count")
    if top3_min is None and case.get("top3_must_include_any_terms"):
        top3_min = 1
    if top3_min is not None:
        relevant = sum(1 for doc in top3 if _is_relevant(doc, case))
        if relevant < int(top3_min):
            reasons.append(f"{label}: top3 relevant count {relevant} < {top3_min}")

    top5_min = case.get("top5_min_relevant_count")
    if top5_min is None and case.get("top5_must_include_any_terms"):
        top5_min = 1
    if top5_min is not None:
        relevant = sum(1 for doc in top5 if _is_relevant(doc, case))
        if relevant < int(top5_min):
            reasons.append(f"{label}: top5 relevant count {relevant} < {top5_min}")

    required_sources = set(case.get("top5_must_include_source_any", []) or [])
    if required_sources and not any(_source_matches_any(doc, required_sources) for doc in top5):
        reasons.append(f"{label}: top5 missing required source {sorted(required_sources)}")

    required_domains = set(case.get("top5_must_include_domain_any", []) or [])
    if required_domains and not any(doc.get("domain") in required_domains for doc in top5):
        reasons.append(f"{label}: top5 missing required domain {sorted(required_domains)}")

    forbidden_terms = _terms(case, "forbidden_terms", "top5_must_not_include_any_terms")
    forbidden_sources = set(case.get("forbidden_sources", []) or []) | set(case.get("top5_must_not_source_any", []) or [])
    forbidden_domains = set(case.get("forbidden_domains", []) or []) | set(case.get("top5_must_not_domain_any", []) or [])
    for doc in top5:
        text = _doc_display_text(doc)
        for term in forbidden_terms:
            if _norm(term) in text:
                reasons.append(f"{label}: doc '{doc.get('title')}' contains forbidden term '{term}'")
        if _source_matches_any(doc, forbidden_sources):
            reasons.append(f"{label}: doc '{doc.get('title')}' uses forbidden source")
        if doc.get("domain") in forbidden_domains:
            reasons.append(f"{label}: doc '{doc.get('title')}' uses forbidden domain")

    return {
        "passed": len(reasons) == 0,
        "failure_reasons": reasons,
    }


def _frontend_top5(
    case: Dict[str, Any],
    ts_results_by_query: Dict[str, Dict[str, Any]],
    document_lookup: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], bool, Dict[str, Any]]:
    ts_case = ts_results_by_query.get(case["query"])
    if not ts_case:
        return [], False, {"query_type": None}
    top5 = [document_lookup[doc_id] for doc_id in ts_case.get("top5_ids", []) if doc_id in document_lookup]
    route_obj = {
        "query_type": ts_case.get("route_type"),
        "top1_prefer_exact_title": ts_case.get("top1_prefer_exact_title"),
    }
    return top5, bool(ts_case.get("route_match")), route_obj


def evaluate_cases(mode: str, ts_results_path: Optional[str], max_data_gap_groups: int) -> Dict[str, Any]:
    index_dir = os.path.join(BASE_DIR, "public", "index")
    notice_documents = load_json(os.path.join(index_dir, "documents.json"))
    documents, document_lookup = load_documents()
    query_aliases = load_json(os.path.join(BASE_DIR, "config", "query_aliases.json"))
    routes = load_query_routes(os.path.join(BASE_DIR, "config", "query_routes.json"))
    channels = _load_manifest_channels()
    cases = load_json(os.path.join(BASE_DIR, "eval", "search_cases.json"))

    selected_modes = [mode] if mode in {"python", "frontend"} else ["python", "frontend"]
    blocking_modes = ["frontend"] if mode == "both" else selected_modes
    ts_results_by_query: Dict[str, Dict[str, Any]] = {}
    if "frontend" in selected_modes:
        if not ts_results_path or not os.path.exists(ts_results_path):
            raise FileNotFoundError("--ts-results is required when mode is frontend or both")
        ts_results = load_json(ts_results_path)
        ts_results_by_query = {item["query"]: item for item in ts_results}

    status_counts = {STATUS_STRICT_PASS: 0, STATUS_DATA_GAP: 0, STATUS_FAIL: 0}
    data_gap_cases: List[str] = []
    data_gap_channels: Dict[str, List[str]] = {}
    data_gap_groups: set[str] = set()
    route_correct = 0
    case_details: List[Dict[str, Any]] = []

    for case in cases:
        query = case["query"]
        expected_route = case.get("route")
        py_route_obj = route_query(query, routes)
        py_route_ok = not expected_route or py_route_obj["query_type"] == expected_route
        if py_route_ok:
            route_correct += 1

        python_top5: List[Dict[str, Any]] = []
        frontend_top5: List[Dict[str, Any]] = []
        evals: Dict[str, Dict[str, Any]] = {}

        if "python" in selected_modes:
            python_top5 = vertical_rank_documents(query, documents, query_aliases=query_aliases, limit=5)
            evals["python"] = _evaluate_result_set(case, python_top5, py_route_ok, py_route_obj, "python")

        if "frontend" in selected_modes:
            frontend_top5, frontend_route_ok, frontend_route_obj = _frontend_top5(case, ts_results_by_query, document_lookup)
            evals["frontend"] = _evaluate_result_set(case, frontend_top5, frontend_route_ok, frontend_route_obj, "frontend")

        blocking_evals = [evals[name] for name in blocking_modes if name in evals]
        selected_pass = all(result["passed"] for result in blocking_evals)
        failure_reasons = [reason for result in evals.values() for reason in result["failure_reasons"]]
        blocking_failure_reasons = [reason for result in blocking_evals for reason in result["failure_reasons"]]

        gap_channels = _coverage_gap_channels(case, notice_documents, channels)
        is_data_gap = (
            not selected_pass
            and bool(case.get("data_gap_allowed", False))
            and bool(case.get("coverage_channels"))
            and set(gap_channels) == set(str(item) for item in case.get("coverage_channels", []) or [])
        )

        if selected_pass:
            status = STATUS_STRICT_PASS
        elif is_data_gap:
            status = STATUS_DATA_GAP
            data_gap_cases.append(query)
            data_gap_channels[query] = gap_channels
            data_gap_groups.add(str(case.get("data_gap_group") or query))
        else:
            status = STATUS_FAIL

        status_counts[status] += 1
        case_details.append(
            {
                "query": query,
                "status": status,
                "python_pass": evals.get("python", {}).get("passed", False),
                "frontend_pass": evals.get("frontend", {}).get("passed", False),
                "python_top5": [_simplify_doc(doc) for doc in python_top5],
                "frontend_top5": [_simplify_doc(doc) for doc in frontend_top5],
                "failure_reasons": failure_reasons,
                "blocking_failure_reasons": blocking_failure_reasons,
                "non_blocking_failure_reasons": [
                    reason for reason in failure_reasons if reason not in blocking_failure_reasons
                ],
                "data_gap_channels": gap_channels if status == STATUS_DATA_GAP else [],
                "route_obj": py_route_obj,
            }
        )

    report = {
        "timestamp": datetime.now(BEIJING_TZ).isoformat(),
        "mode": mode,
        "evaluated_modes": selected_modes,
        "blocking_modes": blocking_modes,
        "total_cases": len(cases),
        "route_accuracy": route_correct / len(cases) if cases else 0,
        "status_counts": status_counts,
        "strict_pass_count": status_counts[STATUS_STRICT_PASS],
        "data_gap_count": len(data_gap_groups),
        "data_gap_case_count": len(data_gap_cases),
        "fail_count": status_counts[STATUS_FAIL],
        "data_gap_cases": data_gap_cases,
        "data_gap_channels": data_gap_channels,
        "data_gap_groups": sorted(data_gap_groups),
        "max_data_gap_groups": max_data_gap_groups,
        "case_details": case_details,
    }

    reports_dir = os.path.join(BASE_DIR, "eval", "reports")
    os.makedirs(reports_dir, exist_ok=True)
    report_path = os.path.join(reports_dir, "product_search_latest.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    report["report_path"] = report_path
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Product Search Quality Gate")
    parser.add_argument("--mode", choices=["python", "frontend", "both"], default="python")
    parser.add_argument("--ts-results", default=None, help="JSON from eval_frontend_search.ts")
    parser.add_argument("--max-data-gap-groups", type=int, default=3)
    args = parser.parse_args()

    try:
        report = evaluate_cases(args.mode, args.ts_results, args.max_data_gap_groups)
    except Exception as exc:
        print(f"[FAILED] Product Search Quality Gate setup error: {exc}")
        sys.exit(1)

    counts = report["status_counts"]
    print("=== Product Search Gate Results ===")
    print(f"Mode: {report['mode']}")
    print(f"Total Cases: {report['total_cases']}")
    print(f"Route Accuracy: {report['route_accuracy']:.3f}")
    print(
        "Status Counts: "
        f"strict={counts[STATUS_STRICT_PASS]}, "
        f"data_gap={counts[STATUS_DATA_GAP]}, "
        f"fail={counts[STATUS_FAIL]}"
    )
    print(f"Data Gap Groups: {report['data_gap_count']}/{report['max_data_gap_groups']} {report['data_gap_groups']}")
    print(f"Report saved to: {report['report_path']}")

    if counts[STATUS_FAIL] > 0:
        print("\nErrors Found:")
        for detail in report["case_details"]:
            if detail["status"] == STATUS_FAIL:
                print(f" - {detail['query']}: {'; '.join(detail['blocking_failure_reasons'])}")

    failed = (
        counts[STATUS_FAIL] > 0
        or report["route_accuracy"] < 1.0
        or report["data_gap_count"] > report["max_data_gap_groups"]
    )
    if failed:
        print("\n[FAILED] Product Search Quality Gate failed.")
        sys.exit(1)

    print("\n[PASS] Product Search Quality Gate passed.")


if __name__ == "__main__":
    main()
