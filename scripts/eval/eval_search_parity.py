"""Frontend-as-truth search parity gate.

The gate has two jobs:
1. verify Python route fixtures still match query_routes.json;
2. require real TypeScript frontend recall output, then compare Python recall
   order against it for critical, non-data-gap search journeys.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))
sys.path.insert(0, os.path.join(BASE_DIR, "scripts", "eval"))

from search.query_router import route_query, load_query_routes
from search.vertical_ranker import vertical_rank_documents
CRITICAL_QUERIES = {
    "B250403",
    "B250403 高数",
    "医保",
    "参保",
    "报销",
    "转专业",
    "宣讲会",
    "招聘",
    "实习",
    "停电",
    "校园网",
    "大创",
    "奖学金",
    "助学金",
}


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def evaluate_route_parity() -> Dict[str, Any]:
    fixtures_path = os.path.join(BASE_DIR, "tests", "search_router_fixtures.json")
    if not os.path.exists(fixtures_path):
        return {
            "route_fixture_count": 0,
            "route_passed": 0,
            "route_failed": 0,
            "route_errors": ["Fixtures file not found"],
        }

    fixtures = load_json(fixtures_path)
    routes = load_query_routes(os.path.join(BASE_DIR, "config", "query_routes.json"))

    errors = []
    passes = 0
    for fixture in fixtures:
        query = fixture["query"]
        expected_type = fixture["expected_query_type"]
        expected_top1_exact = fixture.get("expected_top1_exact")

        result = route_query(query, routes)
        actual_type = result["query_type"]
        actual_top1_exact = result["top1_prefer_exact_title"]

        route_ok = actual_type == expected_type
        top1_exact_ok = expected_top1_exact is None or actual_top1_exact == expected_top1_exact

        if route_ok and top1_exact_ok:
            passes += 1
        else:
            msg_parts = []
            if not route_ok:
                msg_parts.append(f"route: expected {expected_type}, got {actual_type}")
            if not top1_exact_ok:
                msg_parts.append(f"top1_exact: expected {expected_top1_exact}, got {actual_top1_exact}")
            errors.append({"query": query, "errors": msg_parts})

    return {
        "route_fixture_count": len(fixtures),
        "route_passed": passes,
        "route_failed": len(fixtures) - passes,
        "route_errors": errors,
    }


def _load_notice_documents() -> List[Dict[str, Any]]:
    return load_json(os.path.join(BASE_DIR, "public", "index", "documents.json"))


def _metrics(details: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    items = list(details)
    total = len(items)
    top1_match_count = sum(1 for item in items if item["top1_match"])
    jaccard_sum = sum(float(item["jaccard"]) for item in items)
    kendall_sum = sum(float(item["kendall_tau"]) for item in items)
    source_match_count = sum(1 for item in items if item["top1_source_match"])
    return {
        "total_queries": total,
        "top1_match_count": top1_match_count,
        "top1_match_rate": round(top1_match_count / total, 4) if total else 0,
        "top1_source_match_count": source_match_count,
        "top1_source_match_rate": round(source_match_count / total, 4) if total else 0,
        "avg_jaccard": round(jaccard_sum / total, 4) if total else 0,
        "avg_kendall_tau": round(kendall_sum / total, 4) if total else 0,
    }


def evaluate_recall_parity(ts_results_path: str) -> Dict[str, Any]:
    if not ts_results_path or not os.path.exists(ts_results_path):
        raise FileNotFoundError("TS search results are required. Run eval_frontend_search.ts and pass --ts-results.")

    ts_results = load_json(ts_results_path)
    documents = _load_notice_documents()
    query_aliases = load_json(os.path.join(BASE_DIR, "config", "query_aliases.json"))
    cases = {case["query"]: case for case in load_json(os.path.join(BASE_DIR, "eval", "search_cases.json"))}
    doc_lookup = {str(doc.get("id", "")): doc for doc in documents}

    details = []
    for ts_case in ts_results:
        query = ts_case["query"]
        if not query.strip():
            continue

        py_ranked = vertical_rank_documents(query, documents, query_aliases=query_aliases, limit=5)
        py_top5_ids = [str(doc.get("id", "")) for doc in py_ranked[:5]]
        ts_top5_ids = [str(item) for item in ts_case.get("top5_ids", [])]

        py_set = set(py_top5_ids)
        ts_set = set(ts_top5_ids)
        union = py_set | ts_set
        intersection = py_set & ts_set
        jaccard = len(intersection) / len(union) if union else 1.0

        py_top1 = py_top5_ids[0] if py_top5_ids else ""
        ts_top1 = ts_top5_ids[0] if ts_top5_ids else ""
        py_doc = doc_lookup.get(py_top1, {})
        ts_doc = doc_lookup.get(ts_top1, {})
        both_empty = not py_top5_ids and not ts_top5_ids
        source_match = both_empty or (bool(py_doc and ts_doc) and (
            py_doc.get("source_id") == ts_doc.get("source_id")
            or py_doc.get("source") == ts_doc.get("source")
            or py_doc.get("domain") == ts_doc.get("domain")
        ))

        all_ids = list(dict.fromkeys(py_top5_ids + ts_top5_ids))
        kendall = 0.0
        if len(all_ids) >= 2:
            concordant = 0
            discordant = 0
            for i in range(len(all_ids)):
                for j in range(i + 1, len(all_ids)):
                    a_i = py_top5_ids.index(all_ids[i]) if all_ids[i] in py_top5_ids else 99
                    a_j = py_top5_ids.index(all_ids[j]) if all_ids[j] in py_top5_ids else 99
                    b_i = ts_top5_ids.index(all_ids[i]) if all_ids[i] in ts_top5_ids else 99
                    b_j = ts_top5_ids.index(all_ids[j]) if all_ids[j] in ts_top5_ids else 99
                    product = (a_i - a_j) * (b_i - b_j)
                    if product > 0:
                        concordant += 1
                    elif product < 0:
                        discordant += 1
            pairs = concordant + discordant
            kendall = (concordant - discordant) / pairs if pairs else 0.0

        case = cases.get(query, {})
        details.append(
            {
                "query": query,
                "py_top5": py_top5_ids,
                "ts_top5": ts_top5_ids,
                "jaccard": round(jaccard, 4),
                "top1_match": both_empty or bool(py_top1 and ts_top1 and py_top1 == ts_top1),
                "top1_source_match": source_match,
                "kendall_tau": round(kendall, 4),
                "is_data_gap_allowed": bool(case.get("data_gap_allowed", False)),
                "is_critical": bool(case.get("critical", query in CRITICAL_QUERIES)),
                "route_match": bool(ts_case.get("route_match", False)),
            }
        )

    all_metrics = _metrics(details)
    comparable_details = [item for item in details if not item["is_data_gap_allowed"]]
    critical_details = [item for item in details if item["is_critical"] and not item["is_data_gap_allowed"]]
    gate_details = critical_details or comparable_details
    gate_metrics = _metrics(gate_details)

    return {
        "parity_available": True,
        **gate_metrics,
        "all_metrics": all_metrics,
        "comparable_metrics": _metrics(comparable_details),
        "critical_metrics": _metrics(critical_details),
        "gate_sample": "critical_non_data_gap" if critical_details else "comparable_non_data_gap",
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Search Parity Check")
    parser.add_argument("--ts-results", type=str, default=None, help="Path to TS search results JSON")
    parser.add_argument("--min-top1-match-rate", type=float, default=0.60)
    parser.add_argument("--min-avg-jaccard", type=float, default=0.50)
    parser.add_argument("--min-critical-top1-match-rate", type=float, default=1.0)
    parser.add_argument("--min-critical-top1-source-match-rate", type=float, default=1.0)
    args = parser.parse_args()

    route_parity = evaluate_route_parity()
    try:
        recall_parity = evaluate_recall_parity(args.ts_results or "")
    except Exception as exc:
        recall_parity = {"parity_available": False, "note": str(exc)}

    report = {
        "timestamp": datetime.now().isoformat(),
        "thresholds": {
            "route_fixture": 1.0,
            "critical_top1_match_rate": args.min_critical_top1_match_rate,
            "top1_match_rate": args.min_top1_match_rate,
            "avg_jaccard": args.min_avg_jaccard,
            "critical_top1_source_match_rate": args.min_critical_top1_source_match_rate,
        },
        "route_parity": route_parity,
        "recall_parity": recall_parity,
    }

    reports_dir = os.path.join(BASE_DIR, "eval", "reports")
    os.makedirs(reports_dir, exist_ok=True)
    report_path = os.path.join(reports_dir, "search_parity_latest.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("=== Search Parity Results ===")
    print(f"Route Fixture: {route_parity['route_passed']}/{route_parity['route_fixture_count']} passed")
    if route_parity["route_errors"]:
        for err in route_parity["route_errors"]:
            query = err["query"]
            for e in err["errors"]:
                print(f"  [FAIL] {query}: {e}")

    failed = route_parity["route_failed"] > 0

    if recall_parity["parity_available"]:
        critical = recall_parity["critical_metrics"]
        print(
            "Recall Parity "
            f"({recall_parity['gate_sample']}): "
            f"top1_match={recall_parity['top1_match_rate']}, "
            f"avg_jaccard={recall_parity['avg_jaccard']}, "
            f"critical_source_match={critical['top1_source_match_rate']}"
        )
        if recall_parity["top1_match_rate"] < args.min_top1_match_rate:
            print(f"  [FAIL] top1_match_rate < {args.min_top1_match_rate}")
            failed = True
        if recall_parity["avg_jaccard"] < args.min_avg_jaccard:
            print(f"  [FAIL] avg_jaccard < {args.min_avg_jaccard}")
            failed = True
        if critical["top1_match_rate"] < args.min_critical_top1_match_rate:
            print(f"  [FAIL] critical top1 exact match < {args.min_critical_top1_match_rate}")
            failed = True
        if critical["top1_source_match_rate"] < args.min_critical_top1_source_match_rate:
            print(f"  [FAIL] critical top1 source match < {args.min_critical_top1_source_match_rate}")
            failed = True
    else:
        print(f"Recall Parity: {recall_parity.get('note', 'Not available')}")
        failed = True

    print(f"Report saved to: {report_path}")

    if failed:
        print("\n[FAILED] Search Parity Gate failed.")
        sys.exit(1)

    print("\n[PASS] Search Parity Gate passed.")


if __name__ == "__main__":
    main()
