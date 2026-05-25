import json
import re
from typing import Any

from core.tokenizer import tokenize_text


def load_query_aliases(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def understand_query(raw_query: str, aliases: dict[str, Any]) -> dict[str, Any]:
    normalized_query = re.sub(r"\s+", " ", str(raw_query or "")).strip()
    tokens = tokenize_text(normalized_query)
    expanded_aliases: list[str] = []
    target_domains: list[str] = []
    target_intents: list[str] = []
    exact_terms: list[str] = []

    for key, payload in aliases.items():
        terms = [key, *payload.get("aliases", [])]
        if any(term and term.lower() in normalized_query.lower() for term in terms):
            expanded_aliases.extend(str(item) for item in payload.get("aliases", []))
            target_domains.extend(str(item) for item in payload.get("domains", []))
            target_intents.extend(str(item) for item in payload.get("intents", []))
            exact_terms.append(str(key))

    return {
        "raw_query": raw_query,
        "normalized_query": normalized_query,
        "tokens": tokens,
        "aliases": unique(expanded_aliases),
        "target_domains": unique(target_domains),
        "target_intents": unique(target_intents),
        "target_audience": [],
        "time_constraint": infer_time_constraint(normalized_query),
        "exact_terms": unique(exact_terms),
        "search_mode": "recall",
        "semantic_queries": unique(build_semantic_queries(normalized_query, expanded_aliases)),
        "query_type": infer_query_type(normalized_query, target_domains, target_intents),
    }

def infer_query_type(query: str, domains: list[str], intents: list[str]) -> str:
    if "考试" in query or "exam" in domains or "schedule" in intents:
        return "exam"
    if any(term in query for term in ("资料", "题", "复习", "卷", "课件")) or "resource" in domains:
        return "resource"
    if any(term in query for term in ("报名", "申请", "提交", "参加")) or any(intent in intents for intent in ("apply", "register", "submit", "attend")):
        return "task"
    return "general"


def build_semantic_queries(query: str, aliases: list[str]) -> list[str]:
    candidates = [query]
    for alias in aliases[:6]:
        if alias not in query:
            candidates.append(f"{alias} {query}")
    if any(term in query for term in ("大创", "创新创业", "项目")):
        candidates.extend(["如何申请大创项目", "大学生创新创业训练计划报名", "本科生科研项目申报"])
    if any(term in query for term in ("保研", "推免")):
        candidates.extend(["推荐免试研究生申请", "推免资格公示", "保研材料提交"])
    return candidates


def infer_time_constraint(query: str) -> str | None:
    if any(term in query for term in ("今天", "今日")):
        return "today"
    if any(term in query for term in ("本周", "这周")):
        return "this_week"
    if any(term in query for term in ("截止", "ddl", "deadline")):
        return "deadline"
    return None


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
