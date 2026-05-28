from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[4]
PUBLIC_ROOT = BASE_DIR / "apps" / "web" / "public"

from .sitegraph_search import recall_documents_with_stats


PUBLIC_INDEX_DIR = PUBLIC_ROOT / "generated" / "collections" / "njupt-public"


@dataclass(frozen=True)
class QueryExpectation:
    query: str
    title_contains: str
    facet: str
    nav_contains: str
    url_pattern: str
    reason_contains: str


QUERY_EXPECTATIONS = (
    QueryExpectation("校历", "校历", "notice_article", "首页", r"jwc\.njupt\.edu\.cn/.+/page\.htm$", "标题"),
    QueryExpectation("慕课考试", "在线开放课程", "exam", "通知公告", r"jwc\.njupt\.edu\.cn/.+/page\.htm$", "考试相关"),
    QueryExpectation("期末考试", "期末考试安排", "exam", "通知公告", r"jwc\.njupt\.edu\.cn/.+/page\.htm$", "考试相关"),
    QueryExpectation("转专业", "转专业管理办法", "policy", "规章制度", r"jwc\.njupt\.edu\.cn/.+/page\.htm$", "标题包含"),
    QueryExpectation("规章制度", "管理办法", "policy", "规章制度", r"jwc\.njupt\.edu\.cn/.+/page\.htm$", "政策制度"),
    QueryExpectation("办事流程", "申请", "workflow", "办事流程", r"jwc\.njupt\.edu\.cn/.+/page\.htm$", "办事流程"),
    QueryExpectation("学生相关文件及表格", "学生", "download", "学生相关文件及表格", r"jwc\.njupt\.edu\.cn/.+", "下载资源"),
    QueryExpectation("教务管理系统", "教务管理系统", "system", "首页", r"jwxt\.njupt\.edu\.cn/?$", "系统入口"),
    QueryExpectation("大创", "大学生创新", "notice_article", "大学生创新创业", r"jwc\.njupt\.edu\.cn/.+/page\.htm$", "词项"),
    QueryExpectation("推免", "免试攻读", "notice_article", "推免生", r"jwc\.njupt\.edu\.cn/.+/page\.htm$", "附件名"),
    QueryExpectation("成绩", "成绩复核", "exam", "通知公告", r"jwc\.njupt\.edu\.cn/.+/page\.htm$", "标题"),
    QueryExpectation("附件1", "考试通知", "exam", "通知公告", r"jwc\.njupt\.edu\.cn/.+/page\.htm$", "附件名命中"),
    QueryExpectation("xlsx", "xlsx", "external", "综合信息服务", r"^http://dag\.njupt\.edu\.cn/main\.htm$", "xlsx"),
    QueryExpectation("奖学金", "奖学金", "notice_article", "通知公告", r"xsc\.njupt\.edu\.cn/.+/page\.htm$", "标题包含"),
    QueryExpectation("辅导员", "辅导员", "notice_article", "辅导员队伍建设", r"xsc\.njupt\.edu\.cn/.+/page\.htm$", "标题包含"),
    QueryExpectation("双创", "双创信息管理系统", "system", "双创信息管理系统", r"^http://njupt\.cxcyedu\.com/tyds/index\.html$", "标题包含"),
    QueryExpectation("互联网+", "互联网+", "notice_article", "通知公告", r"cxcy\.njupt\.edu\.cn/.+/page\.htm$", "标题包含"),
)

SIZE_BUDGETS = {
    "first_screen_total_bytes": 16_000_000,
    "body_index_bytes": 19_000_000,
    "full_shard_count": 650,
    "max_full_shard_bytes": 512 * 1024,
    "avg_full_shard_bytes": 96 * 1024,
    "max_candidate_shards_per_query": 32,
}


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def fail(message: str, payload: Any | None = None) -> None:
    print(f"[sitegraph_query_smoke_test] {message}", file=sys.stderr)
    if payload is not None:
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
    raise SystemExit(1)


def result_matches(result: dict[str, Any], expectation: QueryExpectation) -> bool:
    title = str(result.get("title") or "")
    nav_path = str(result.get("nav_path_text") or "")
    score_reason = str(result.get("score_reason") or "")
    url = str(result.get("url") or "")
    return (
        expectation.title_contains in title
        and result.get("facet") == expectation.facet
        and expectation.nav_contains in nav_path
        and re.search(expectation.url_pattern, url) is not None
        and expectation.reason_contains in score_reason
    )


def validate_quality() -> dict[str, Any]:
    query_summaries: list[dict[str, Any]] = []
    failures: dict[str, Any] = {}
    for expectation in QUERY_EXPECTATIONS:
        payload = recall_documents_with_stats(expectation.query, limit=12)
        results = payload["results"]
        stats = payload["stats"]
        match = next((item for item in results if result_matches(item, expectation)), None)
        query_summaries.append(
            {
                "query": expectation.query,
                "quick_result_count": stats.get("quick_result_count", 0),
                "loaded_shard_count": stats.get("loaded_shard_count", 0),
                "candidate_shard_count": stats.get("candidate_shard_count", 0),
                "scanned_shards": stats.get("scanned_shards", 0),
                "proved_no_match_shards": stats.get("proved_no_match_shards", 0),
                "candidate_count": stats.get("candidate_count", 0),
                "used_body_index": stats.get("used_body_index", False),
                "exhaustive_complete": (stats.get("coverage") or {}).get("exhaustive_complete", False),
                "coverage": stats.get("coverage"),
                "matched_title": match.get("title") if match else None,
                "matched_facet": match.get("facet") if match else None,
                "matched_nav_path": match.get("nav_path_text") if match else None,
                "matched_url": match.get("url") if match else None,
                "matched_score_reason": match.get("score_reason") if match else None,
            }
        )
        if match is None:
            failures[expectation.query] = {
                "expected": expectation.__dict__,
                "top_results": [
                    {
                        "title": item.get("title"),
                        "facet": item.get("facet"),
                        "nav_path": item.get("nav_path_text"),
                        "url": item.get("url"),
                        "score_reason": item.get("score_reason"),
                    }
                    for item in results[:8]
                ],
            }
        if int(stats.get("quick_result_count", 0)) <= 0:
            failures[f"{expectation.query}:quick"] = {"reason": "quick phase returned no results"}
        coverage = stats.get("coverage") or {}
        if coverage.get("exhaustive_complete") is not True:
            failures[f"{expectation.query}:coverage"] = coverage
        covered_shards = int(coverage.get("proved_no_match_shards", 0)) + int(coverage.get("scanned_shards", 0))
        if covered_shards != int(coverage.get("total_shards", -2)):
            failures[f"{expectation.query}:shard_coverage"] = coverage
        if int(stats.get("candidate_shard_count", 0)) > SIZE_BUDGETS["max_candidate_shards_per_query"]:
            failures[f"{expectation.query}:candidate_shards"] = stats
    if failures:
        fail("representative query quality checks failed", failures)
    return {
        "queries": query_summaries,
        "max_candidate_shards": max((int(item["candidate_shard_count"]) for item in query_summaries), default=0),
        "max_loaded_shards": max((int(item["loaded_shard_count"]) for item in query_summaries), default=0),
        "max_scanned_shards": max((int(item["scanned_shards"]) for item in query_summaries), default=0),
        "note": "candidate_shards is the bounded hydration cost; loaded/scanned shards include exhaustive verification coverage.",
    }


def validate_size_budget() -> dict[str, Any]:
    manifest = read_json(PUBLIC_INDEX_DIR / "manifest.json")
    artifacts = manifest["artifacts"]
    first_screen_artifacts = manifest["core_search"]["first_screen_artifacts"]
    if first_screen_artifacts != ["doc_meta_light", "light_inverted_index", "query_aliases"]:
        fail("unexpected first-screen artifact list", first_screen_artifacts)
    if "body_inverted_index" in first_screen_artifacts:
        fail("body index must not be a first-screen artifact")

    size_report = read_json(PUBLIC_ROOT / artifacts["size_report"]["path"])
    budget_summary = {
        "first_screen_files": size_report["first_screen_files"],
        "first_screen_bytes": size_report["first_screen_bytes"],
        "first_screen_total_bytes": size_report["first_screen_total_bytes"],
        "body_index_bytes": size_report["body_index_bytes"],
        "full_scan_total_bytes": size_report["full_scan_total_bytes"],
        "shard_count": size_report["shard_count"],
        "max_shard_bytes": size_report["max_shard_bytes"],
        "avg_shard_bytes": size_report["avg_shard_bytes"],
        "representative_query_phase_timings": size_report["representative_query_phase_timings"],
        "full_shard_count": size_report["full_shard_count"],
        "max_full_shard_bytes": size_report["max_full_shard_bytes"],
        "avg_full_shard_bytes": size_report["avg_full_shard_bytes"],
        "max_full_shard_documents": size_report["max_full_shard_documents"],
        "avg_full_shard_documents": size_report["avg_full_shard_documents"],
    }
    failures = {
        key: {"actual": budget_summary[key], "budget": budget}
        for key, budget in SIZE_BUDGETS.items()
        if key in budget_summary and float(budget_summary[key]) > float(budget)
    }
    if failures:
        fail("sitegraph index size budget failed", failures)
    return budget_summary


def main() -> None:
    size_summary = validate_size_budget()
    quality_summary = validate_quality()
    print(
        json.dumps(
            {
                "quality": quality_summary,
                "size_budget": size_summary,
                "budgets": SIZE_BUDGETS,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
