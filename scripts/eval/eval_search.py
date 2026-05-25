import argparse
import json
import math
import os
import sys
from datetime import datetime
from typing import Any

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(SCRIPTS_DIR)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from search.vertical_ranker import recall_documents


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def relevance(document: dict[str, Any], qrel: dict[str, Any]) -> int:
    text = " ".join([
        str(document.get("title") or ""),
        str(document.get("content") or ""),
        str(document.get("summary") or ""),
        " ".join(str(item) for item in document.get("tags", [])),
        " ".join(str(item) for item in document.get("evidence", [])),
    ])
    score = 0
    if str(document.get("domain")) in set(qrel.get("domains", [])):
        score += 1
    if str(document.get("intent")) in set(qrel.get("intents", [])):
        score += 1
    if any(str(term) and str(term).lower() in text.lower() for term in qrel.get("terms", [])):
        score += 2
    if document.get("task_frames"):
        score += 1
    return min(score, 3)


def precision_at(ranked: list[dict[str, Any]], qrel: dict[str, Any], k: int) -> float:
    top = ranked[:k]
    if not top:
        return 0.0
    return sum(1 for document in top if relevance(document, qrel) > 0) / len(top)


def recall_at(ranked: list[dict[str, Any]], qrel: dict[str, Any], k: int, documents: list[dict[str, Any]]) -> float:
    relevant_total = sum(1 for document in documents if relevance(document, qrel) > 0)
    if relevant_total == 0:
        return 0.0
    retrieved = sum(1 for document in ranked[:k] if relevance(document, qrel) > 0)
    return retrieved / relevant_total


def mrr_at(ranked: list[dict[str, Any]], qrel: dict[str, Any], k: int) -> float:
    for index, document in enumerate(ranked[:k], start=1):
        if relevance(document, qrel) > 0:
            return 1 / index
    return 0.0


def ndcg_at(ranked: list[dict[str, Any]], qrel: dict[str, Any], k: int, documents: list[dict[str, Any]]) -> float:
    gains = [relevance(document, qrel) for document in ranked[:k]]
    dcg = sum((2**gain - 1) / math.log2(index + 2) for index, gain in enumerate(gains))
    ideal = sorted((relevance(document, qrel) for document in documents), reverse=True)[:k]
    idcg = sum((2**gain - 1) / math.log2(index + 2) for index, gain in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate HyTask-RAG search quality.")
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()

    documents = read_json(os.path.join(BASE_DIR, "public", "index", "documents.json"))
    task_frames = read_json(os.path.join(BASE_DIR, "public", "index", "task_frames.json"))
    query_aliases = read_json(os.path.join(BASE_DIR, "public", "index", "query_aliases.json"))
    queries = read_json(os.path.join(BASE_DIR, "eval", "queries.json"))
    qrels = read_json(os.path.join(BASE_DIR, "eval", "qrels.json"))

    rows = []
    for query in queries:
        qid = str(query["id"])
        qrel = qrels.get(qid, {})
        ranked = recall_documents(str(query["query"]), documents, query_aliases=query_aliases, limit=20)
        rows.append({
            "id": qid,
            "query": query["query"],
            "precision_at_5": precision_at(ranked, qrel, 5),
            "recall_at_10": recall_at(ranked, qrel, 10, documents),
            "mrr_at_10": mrr_at(ranked, qrel, 10),
            "ndcg_at_10": ndcg_at(ranked, qrel, 10, documents),
            "top_ids": [item.get("id") for item in ranked[:5]],
        })

    summary = {
        "query_count": len(rows),
        "precision_at_5": average(rows, "precision_at_5"),
        "recall_at_10": average(rows, "recall_at_10"),
        "mrr_at_10": average(rows, "mrr_at_10"),
        "ndcg_at_10": average(rows, "ndcg_at_10"),
        "task_frame_count": len(task_frames),
        "evidence_coverage": evidence_coverage(task_frames),
        "restricted_count": sum(1 for document in documents if document.get("status") == "restricted" or (document.get("rule_guard") or {}).get("restricted")),
        "sensitive_count": sum(1 for document in documents if document.get("sensitive") or (document.get("rule_guard") or {}).get("sensitive")),
        "llm_cache_hit_rate": llm_cache_hit_rate(documents),
        "generated_at": datetime.now().isoformat(),
    }
    payload = {"summary": summary, "queries": rows}
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.write_report:
        reports_dir = os.path.join(BASE_DIR, "eval", "reports")
        os.makedirs(reports_dir, exist_ok=True)
        report_path = os.path.join(reports_dir, f"eval-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
        with open(report_path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        latest_path = os.path.join(reports_dir, "latest.json")
        with open(latest_path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")


def average(rows: list[dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    return round(sum(float(row[key]) for row in rows) / len(rows), 4)


def evidence_coverage(task_frames: list[dict[str, Any]]) -> float:
    if not task_frames:
        return 0.0
    return round(sum(1 for frame in task_frames if frame.get("evidence")) / len(task_frames), 4)


def llm_cache_hit_rate(documents: list[dict[str, Any]]) -> float:
    llm_docs = [document for document in documents if isinstance(document.get("llm"), dict)]
    if not llm_docs:
        return 0.0
    hits = sum(1 for document in llm_docs if document.get("llm", {}).get("used"))
    return round(hits / len(llm_docs), 4)


if __name__ == "__main__":
    main()
