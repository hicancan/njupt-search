import json
import os
import sys
from typing import Any

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(SCRIPTS_DIR)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from search.vertical_ranker import recall_documents
from eval_search import read_json
from eval_product_search import _coverage_gap_channels, _load_manifest_channels


REQUIRED_QUERIES = {
    "保研",
    "推免",
    "奖学金",
    "助学金",
    "困难认定",
    "大创",
    "挑战杯",
    "蓝桥杯",
    "宣讲会",
    "实习",
    "停电",
    "停水",
    "图书馆开放",
    "四六级",
    "补考",
    "转专业",
    "毕业设计",
    "论文答辩",
    "海外交流",
    "校园网",
    "医保",
    "档案",
    "高数",
    "离散数学",
}


def main() -> None:
    documents = read_json(os.path.join(BASE_DIR, "public", "index", "documents.json"))
    query_aliases = read_json(os.path.join(BASE_DIR, "public", "index", "query_aliases.json"))
    queries = read_json(os.path.join(BASE_DIR, "eval", "queries.json"))
    query_texts = [str(item.get("query") or "") for item in queries]
    search_cases = {
        str(item.get("query")): item
        for item in read_json(os.path.join(BASE_DIR, "eval", "search_cases.json"))
    }
    notice_documents = read_json(os.path.join(BASE_DIR, "public", "index", "documents.json"))
    manifest_channels = _load_manifest_channels()

    missing = sorted(REQUIRED_QUERIES.difference(query_texts))
    failures: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    if missing:
        failures.append({"type": "missing_query", "queries": missing})

    for query in query_texts:
        case = search_cases.get(query, {})
        data_gap_channels = _coverage_gap_channels(case, notice_documents, manifest_channels) if case.get("data_gap_allowed") else []
        is_data_gap = bool(case.get("data_gap_allowed")) and bool(case.get("coverage_channels")) and set(data_gap_channels) == set(str(item) for item in case.get("coverage_channels", []))
        ranked = recall_documents(query, documents, query_aliases=query_aliases, limit=5)
        top = ranked[:5]
        if not top:
            if is_data_gap:
                rows.append({"query": query, "top_ids": [], "status": "data_gap", "data_gap_channels": data_gap_channels})
            else:
                failures.append({"type": "empty_top5", "query": query})
                rows.append({"query": query, "top_ids": [], "status": "fail"})
            continue

        if is_data_gap:
            rows.append({
                "query": query,
                "top_ids": [item.get("id") for item in top],
                "top_sources": [item.get("source_id") for item in top],
                "status": "data_gap",
                "data_gap_channels": data_gap_channels,
            })
            continue

        if any(not item.get("score_reason") for item in top):
            failures.append({"type": "missing_score_reason", "query": query})
        if len({item.get("id") for item in top}) != len(top):
            failures.append({"type": "duplicate_top5", "query": query})
        if any((item.get("rule_guard") or {}).get("restricted") and not item.get("review_required") for item in top):
            failures.append({"type": "restricted_without_review", "query": query})
        rows.append({
            "query": query,
            "top_ids": [item.get("id") for item in top],
            "top_sources": [item.get("source_id") for item in top],
            "status": "ok",
        })

    payload = {
        "query_count": len(query_texts),
        "passed": not failures,
        "failure_count": len(failures),
        "failures": failures,
        "queries": rows,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
