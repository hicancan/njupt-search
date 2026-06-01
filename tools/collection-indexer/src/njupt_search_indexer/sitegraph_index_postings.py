from __future__ import annotations

from collections import defaultdict
from time import perf_counter
from typing import Any

from .sitegraph_text import clean_text, normalize_text, sitegraph_tokens


QUERY_SYNONYMS: dict[str, list[str]] = {
    "校历": ["教学日历", "教学周历", "2025-2026学年校历"],
    "慕课考试": ["慕课", "MOOC", "SPOC", "在线开放课程", "线下考试"],
    "期末考试": ["期末", "考试安排", "考场安排", "考试周"],
    "四六级": ["四级", "六级", "大学英语四级", "大学英语六级", "CET-4", "CET-6"],
    "转专业": ["专业变更", "转入转出", "转专业管理办法"],
    "规章制度": ["规章", "制度", "管理办法", "政策文件"],
    "办事流程": ["流程", "办理指南", "办事指南", "申请流程"],
    "学生相关文件及表格": ["学生表格", "常用下载", "表格下载", "学生相关文件"],
    "教务管理系统": ["正方教务", "教务系统", "jwxt"],
    "信息门户": ["综合信息服务", "智慧校园", "统一身份认证", "教务管理系统", "考试信息查询", "正方教务", "jwxt"],
    "大创": ["大学生创新创业", "创新创业", "创新训练", "创业训练"],
    "推免": ["免试攻读研究生", "推荐免试", "推免生"],
    "成绩": ["成绩查询", "成绩单", "绩点", "成绩复核"],
    "附件1": ["附件 1", "附件一", "附件"],
    "xlsx": ["xls", "Excel", "表格"],
    "学工": ["学生工作", "学生工作部", "学工要闻"],
    "奖学金": ["助学金", "资助", "评奖评优"],
    "困难认定": ["家庭经济困难学生认定", "家庭经济困难", "困难学生认定", "资助认定"],
    "助学金": ["资助", "奖助学金", "家庭经济困难"],
    "辅导员": ["辅导员队伍建设", "辅导员宣讲团"],
    "心理健康": ["心理咨询", "心理中心"],
    "双创": ["双创信息管理系统", "双创基地"],
    "互联网+": [],
    "竞赛报名": ["创新创业竞赛报名", "学科竞赛报名", "大赛报名"],
}

FIELD_CODES = {
    "title": "t",
    "section": "s",
    "nav_path": "n",
    "attachment": "a",
    "external": "e",
    "system": "y",
    "tag": "g",
    "summary": "m",
    "content": "c",
}

LIGHT_FIELD_CODES = {key: FIELD_CODES[key] for key in ("title", "section", "nav_path", "attachment", "external", "system", "tag")}
BODY_FIELD_CODES = {key: FIELD_CODES[key] for key in ("summary", "content")}
FIELD_IMPACTS = {
    "t": 120,
    "a": 95,
    "e": 95,
    "y": 95,
    "s": 60,
    "n": 55,
    "g": 45,
    "m": 16,
    "c": 10,
}
IMPACT_BLOCK_SIZE = 32


def query_alias_payload() -> dict[str, dict[str, list[str]]]:
    return {
        key: {"aliases": aliases}
        for key, aliases in sorted(QUERY_SYNONYMS.items())
    }


def add_postings(index: dict[str, dict[str, set[int]]], doc_index: int, field_code: str, tokens: set[str]) -> None:
    for token in tokens:
        if not token:
            continue
        index[token][field_code].add(doc_index)


def compact_impact_terms(raw_index: dict[str, dict[str, set[int]]]) -> dict[str, dict[str, Any]]:
    terms: dict[str, dict[str, Any]] = {}
    for token, fields in raw_index.items():
        postings: dict[str, list[int]] = {}
        for field, ids in fields.items():
            doc_ids = sorted(ids)
            if not doc_ids:
                continue
            postings[field] = doc_ids
        if postings:
            terms[token] = postings
    return terms


def build_light_inverted_index(documents: list[dict[str, Any]]) -> dict[str, Any]:
    raw_index: dict[str, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    for document in documents:
        doc_index = int(document["doc_index"])
        add_postings(raw_index, doc_index, FIELD_CODES["title"], sitegraph_tokens(document.get("title"), cjk_max_n=4, cap=120))
        add_postings(raw_index, doc_index, FIELD_CODES["section"], sitegraph_tokens([document.get("section"), document.get("nav_path_text")], cjk_max_n=4, cap=80))
        add_postings(raw_index, doc_index, FIELD_CODES["nav_path"], sitegraph_tokens(" ".join(document.get("nav_path") or []), cjk_max_n=4, cap=80))
        add_postings(raw_index, doc_index, FIELD_CODES["tag"], sitegraph_tokens(" ".join(document.get("tags") or []), cjk_max_n=4))
        attachment_text = " ".join(
            " ".join(clean_text(attachment.get(field)) for field in ("name", "extension", "section"))
            for attachment in document.get("attachments") or []
        )
        add_postings(raw_index, doc_index, FIELD_CODES["attachment"], sitegraph_tokens(attachment_text, cjk_max_n=4, cap=80))
        if document.get("record_type") == "external":
            add_postings(raw_index, doc_index, FIELD_CODES["external"], sitegraph_tokens([document.get("title"), document.get("url")], cjk_max_n=5))
        if document.get("record_type") == "utility" or document.get("facet") == "system":
            add_postings(raw_index, doc_index, FIELD_CODES["system"], sitegraph_tokens([document.get("title"), document.get("url"), document.get("section")], cjk_max_n=5))

    return {
        "version": "sitegraph-local-light-impact-v2",
        "tokenizer": "nfkc-lower-cjk-ngram-code",
        "field_codes": LIGHT_FIELD_CODES,
        "field_impacts": {code: FIELD_IMPACTS[code] for code in LIGHT_FIELD_CODES.values()},
        "block_size": IMPACT_BLOCK_SIZE,
        "scoring_model": "impact-ordered-block-max-bm25f-lite-v2",
        "entry_fields": ["title", "section", "nav_path", "tag", "attachment", "external", "system"],
        "terms": compact_impact_terms(raw_index),
    }


def build_body_inverted_index(documents: list[dict[str, Any]]) -> dict[str, Any]:
    raw_index: dict[str, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    for document in documents:
        doc_index = int(document["doc_index"])
        add_postings(raw_index, doc_index, FIELD_CODES["summary"], sitegraph_tokens(document.get("summary"), cjk_max_n=4, cap=80))
        add_postings(raw_index, doc_index, FIELD_CODES["content"], sitegraph_tokens(document.get("content"), cjk_max_n=3, cap=180))
    return {
        "version": "sitegraph-local-body-impact-v2",
        "tokenizer": "nfkc-lower-cjk-ngram-code",
        "field_codes": BODY_FIELD_CODES,
        "field_impacts": {code: FIELD_IMPACTS[code] for code in BODY_FIELD_CODES.values()},
        "block_size": IMPACT_BLOCK_SIZE,
        "scoring_model": "impact-ordered-block-max-bm25f-lite-v2",
        "entry_fields": ["summary", "content"],
        "terms": compact_impact_terms(raw_index),
    }


def exhaustive_scan_blob(document: dict[str, Any]) -> str:
    attachment_text = " ".join(
        " ".join(clean_text(attachment.get(field)) for field in ("name", "extension", "url", "section", "parent_url"))
        for attachment in document.get("attachments") or []
    )
    return normalize_text(
        " ".join(
            [
                clean_text(document.get("title")),
                clean_text(document.get("section")),
                " ".join(clean_text(item) for item in document.get("nav_path") or []),
                clean_text(document.get("nav_path_text")),
                clean_text(document.get("summary")),
                clean_text(document.get("content")),
                clean_text(document.get("url")),
                attachment_text,
            ]
        )
    )


def measure_representative_full_scan_ms(documents: list[dict[str, Any]], query: str = "校历") -> float:
    normalized_query = normalize_text(query)
    terms = sitegraph_tokens(query, cjk_max_n=5)
    started = perf_counter()
    matches = 0
    for document in documents:
        blob = exhaustive_scan_blob(document)
        if (normalized_query and normalized_query in blob) or any(term in blob for term in terms):
            matches += 1
    elapsed_ms = (perf_counter() - started) * 1000
    # Touch the match count so the measurement cannot be optimized away by future rewrites.
    return round(elapsed_ms + (matches * 0), 3)
