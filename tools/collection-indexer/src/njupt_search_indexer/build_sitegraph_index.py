from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parents[4]
PUBLIC_ROOT = BASE_DIR / "apps" / "web" / "public"
COLLECTION_ID = "njupt-public"
DEFAULT_COLLECTION_CONFIG = BASE_DIR / "config" / "collections" / "njupt-public.sitegraph.json"
DEFAULT_SITEGRAPH_REPO = BASE_DIR.parent / "njupt-site-graph"
DEFAULT_SOURCE_PACKAGE_PATHS = ("data/sites/jwc/index", "data/sites/xsc/index", "data/sites/cxcy/index")
UNKNOWN_ALLOWLIST_FILE = "unknown_url_allowlist.json"


def _resolve_path(value: str, base_dir: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def load_collection_source_packages(config_path: Path | None = None) -> list[Path]:
    path = config_path or DEFAULT_COLLECTION_CONFIG
    if not path.exists():
        return [(DEFAULT_SITEGRAPH_REPO / source_path).resolve() for source_path in DEFAULT_SOURCE_PACKAGE_PATHS]

    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict):
        raise ValueError(f"{path} must be a JSON object")
    if config.get("collection_id") != COLLECTION_ID:
        raise ValueError(f"{path} collection_id must be {COLLECTION_ID!r}")

    env_name = str(config.get("sitegraph_repo_env") or "NJUPT_SITEGRAPH_REPO")
    sitegraph_repo_value = os.environ.get(env_name) or str(config.get("sitegraph_repo") or "../njupt-site-graph")
    sitegraph_repo = _resolve_path(sitegraph_repo_value, BASE_DIR)
    source_packages = config.get("source_packages")
    if not isinstance(source_packages, list) or not source_packages:
        raise ValueError(f"{path} source_packages must be a non-empty list")

    resolved: list[Path] = []
    for source_package in source_packages:
        if not isinstance(source_package, str) or not source_package:
            raise ValueError(f"{path} source_packages entries must be non-empty strings")
        resolved.append(_resolve_path(source_package, sitegraph_repo))
    return resolved


DEFAULT_SITEGRAPH_INDEXES = tuple(load_collection_source_packages())
DEFAULT_SITEGRAPH_INDEX = DEFAULT_SITEGRAPH_INDEXES[0]
PUBLIC_INDEX_DIR = PUBLIC_ROOT / "generated" / "collections" / COLLECTION_ID
PUBLIC_SITEGRAPH_DIR = PUBLIC_INDEX_DIR / "sitegraph"
PUBLIC_ARTIFACT_DIR = PUBLIC_SITEGRAPH_DIR / "artifacts"
PUBLIC_SHARD_DIR = PUBLIC_SITEGRAPH_DIR / "shards"
OBSOLETE_INDEX_DIR = PUBLIC_ROOT / "index"


def configure_collection_output(collection_id: str = COLLECTION_ID, output_dir: Path | None = None) -> None:
    global COLLECTION_ID, PUBLIC_INDEX_DIR, PUBLIC_SITEGRAPH_DIR, PUBLIC_ARTIFACT_DIR, PUBLIC_SHARD_DIR

    if collection_id != "njupt-public":
        raise ValueError("Only collection-id njupt-public is currently supported")
    target = (output_dir.resolve() if output_dir is not None else PUBLIC_ROOT / "generated" / "collections" / collection_id)
    try:
        target.relative_to(PUBLIC_ROOT)
    except ValueError as exc:
        raise ValueError(f"collection output must be under {PUBLIC_ROOT}") from exc

    COLLECTION_ID = collection_id
    PUBLIC_INDEX_DIR = target
    PUBLIC_SITEGRAPH_DIR = PUBLIC_INDEX_DIR / "sitegraph"
    PUBLIC_ARTIFACT_DIR = PUBLIC_SITEGRAPH_DIR / "artifacts"
    PUBLIC_SHARD_DIR = PUBLIC_SITEGRAPH_DIR / "shards"

REQUIRED_SITEGRAPH_FILES = {
    "manifest.json",
    "site.json",
    "sections.json",
    "list_pages.jsonl",
    "detail_pages.jsonl",
    "attachments.jsonl",
    "external_links.jsonl",
    "edges.jsonl",
}

COUNT_FIELDS = (
    "sections",
    "nav_nodes",
    "homepage_modules",
    "list_pages",
    "detail_pages",
    "low_content_detail_pages",
    "attachments",
    "external_links",
    "edges",
    "url_outcomes",
)

QUERY_SYNONYMS: dict[str, list[str]] = {
    "校历": ["教学日历", "教学周历", "2025-2026学年校历"],
    "慕课考试": ["慕课", "MOOC", "SPOC", "在线开放课程", "线下考试"],
    "期末考试": ["期末", "考试安排", "考场安排", "考试周"],
    "转专业": ["专业变更", "转入转出", "转专业管理办法"],
    "规章制度": ["规章", "制度", "管理办法", "政策文件"],
    "办事流程": ["流程", "办理指南", "办事指南", "申请流程"],
    "学生相关文件及表格": ["学生表格", "常用下载", "表格下载", "学生相关文件"],
    "教务管理系统": ["正方教务", "教务系统", "jwxt"],
    "信息门户": ["综合信息服务", "智慧校园", "统一身份认证"],
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

FACET_ORDER = ("notice_article", "policy", "workflow", "download", "system", "exam", "news", "external")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path} line {line_number} is not valid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path} line {line_number} must be a JSON object")
            rows.append(row)
    return rows


def write_json(path: Path, payload: Any, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        if compact:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")


def json_bytes(payload: Any, *, compact: bool = True) -> bytes:
    if compact:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    return text.encode("utf-8")


def write_hashed_json(directory: Path, logical_name: str, payload: Any, *, compact: bool = True) -> dict[str, Any]:
    data = json_bytes(payload, compact=compact)
    digest = hashlib.sha256(data).hexdigest()
    filename = f"{logical_name}.{digest[:16]}.json"
    path = directory / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {
        "path": str(path.relative_to(PUBLIC_ROOT)).replace("\\", "/"),
        "sha256": digest,
        "bytes": len(data),
    }


def sha1_text(text: str, length: int = 20) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def sha256_text(text: str, length: int = 16) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def filter_token_hash(text: str) -> str:
    value = 2166136261
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * 16777619) & 0xFFFFFFFF
    return f"{value:08x}"


def filter_token_hash_int(text: str, seed: int) -> int:
    value = (2166136261 ^ seed) & 0xFFFFFFFF
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * 16777619) & 0xFFFFFFFF
    return value


def build_filter_bitset(tokens: list[str], *, bit_count: int = 16384, hash_count: int = 3) -> dict[str, Any]:
    data = bytearray(bit_count // 8)
    for token in tokens:
        for seed in range(hash_count):
            bit = filter_token_hash_int(token, seed) % bit_count
            data[bit // 8] |= 1 << (bit % 8)
    return {
        "bitset_base64": base64.b64encode(bytes(data)).decode("ascii"),
        "bit_count": bit_count,
        "hash_count": hash_count,
    }


def stable_slug(value: Any, *, fallback: str = "unknown", max_length: int = 48) -> str:
    text = normalize_text(value)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff_-]+", "-", text).strip("-")
    if not text:
        text = fallback
    return text[:max_length]


def producer_ref() -> str:
    for env_name in ("GITHUB_SHA", "GITHUB_REF_NAME"):
        value = os.environ.get(env_name)
        if value:
            return value
    try:
        return subprocess.check_output(["git", "rev-parse", "--short=12", "HEAD"], cwd=BASE_DIR, text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "local-unversioned"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    return re.sub(r"\s+", "", text)


def normalize_iso_date(raw: str | None) -> str | None:
    text = clean_text(raw)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.date().isoformat()


def valid_iso_date(year: int, month: int, day: int) -> str | None:
    if year < 1990 or year > 2035:
        return None
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None


def infer_academic_year(value: Any) -> str | None:
    text = clean_text(value)
    match = re.search(r"(20\d{2})\s*[-—~至]\s*(20\d{2})\s*学年", text)
    if match:
        start, end = int(match.group(1)), int(match.group(2))
        if end == start + 1:
            return f"{start}-{end}"
    match = re.search(r"(20\d{2})\s*[-—~]\s*(20\d{2})", text)
    if match:
        start, end = int(match.group(1)), int(match.group(2))
        if end == start + 1:
            return f"{start}-{end}"
    return None


def infer_term(value: Any) -> str | None:
    text = normalize_text(value)
    if any(term in text for term in ("第二学期", "下学期", "-2学期", "2学期")):
        return "2"
    if any(term in text for term in ("第一学期", "上学期", "-1学期", "1学期")):
        return "1"
    return None


def infer_version_date(value: Any, *, published_at: str | None = None) -> str | None:
    text = unicodedata.normalize("NFKC", str(value or ""))
    for pattern in (
        r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?",
        r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
    ):
        match = re.search(pattern, text)
        if match:
            parsed = valid_iso_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            if parsed:
                return parsed
    compact = re.search(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)", text)
    if compact:
        parsed = valid_iso_date(int(compact.group(1)), int(compact.group(2)), int(compact.group(3)))
        if parsed:
            return parsed
    if published_at:
        year_match = re.search(r"(20\d{2})", normalize_iso_date(published_at) or "")
        month_day = re.search(r"(?<!\d)(\d{1,2})[-/.](\d{1,2})(?!\d)", text)
        if year_match and month_day:
            parsed = valid_iso_date(int(year_match.group(1)), int(month_day.group(1)), int(month_day.group(2)))
            if parsed:
                return parsed
    return None


def canonical_title(value: Any) -> str:
    text = clean_text(value)
    text = re.sub(r"^【[^】]{1,24}】", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -_")
    return text or clean_text(value)


def infer_task_kind(*, source_id: str, facet: str, record_type: str, title: str, section: str, nav_path: list[str], tags: list[str]) -> str:
    text = normalize_text(" ".join([title, section, " ".join(nav_path), " ".join(tags), facet, record_type]))
    if facet == "system":
        return "system_entry"
    if record_type == "attachment" or facet == "download" or any(term in text for term in ("申请表", "表格", "下载", "附件", "xls", "xlsx", "doc", "pdf")):
        return "form_download"
    if any(term in text for term in ("期末考试", "考试安排", "补考", "重修考试", "考场", "慕课", "mooc")):
        return "exam_schedule"
    if any(term in text for term in ("校历", "教学周历", "教学日历", "放假安排")):
        return "academic_calendar"
    if any(term in text for term in ("转专业", "推免", "免试攻读", "培养方案", "学籍", "管理办法")):
        return "academic_policy"
    if any(term in text for term in ("选课", "成绩", "学分", "课程")):
        return "course_grade_credit"
    if source_id == "xsc" and any(term in text for term in ("奖学金", "助学金", "资助", "家庭经济困难", "困难学生认定", "评奖评优")):
        return "scholarship_aid"
    if source_id == "xsc":
        return "student_affairs"
    if source_id == "cxcy" or any(term in text for term in ("双创", "创新创业", "大创", "互联网+", "挑战杯", "竞赛")):
        return "innovation_entrepreneurship"
    return "broad_exploratory"


def authority_profile_for(source_id: str, task_kind: str) -> str:
    if source_id == "jwc":
        return "jwc_academic"
    if source_id == "xsc":
        return "xsc_student_affairs"
    if source_id == "cxcy":
        return "cxcy_innovation"
    return f"{source_id}_{task_kind}"


def unique_strings(values: list[Any], *, limit: int | None = None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if limit is not None and len(result) >= limit:
            break
    return result


def count_nav_nodes(nav_tree: dict[str, Any]) -> int:
    nodes = nav_tree.get("nodes")
    return len(nodes) if isinstance(nodes, list) else 0


def unknown_url_outcomes(manifest: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    outcomes = manifest.get("url_outcomes")
    if not isinstance(outcomes, dict):
        return []
    return [
        (str(url), record)
        for url, record in outcomes.items()
        if isinstance(record, dict)
        and ("unknown" in str(record.get("target_type") or "") or "unknown" in str(record.get("outcome") or ""))
    ]


def assert_unknown_url_outcomes_allowlisted(index_dir: Path, source_id: str, manifest: dict[str, Any]) -> None:
    unknown = unknown_url_outcomes(manifest)
    if not unknown:
        return

    allowlist_path = index_dir / UNKNOWN_ALLOWLIST_FILE
    if not allowlist_path.exists():
        raise ValueError(f"{source_id} manifest contains unknown URL outcomes but no {UNKNOWN_ALLOWLIST_FILE}")

    allowlist = read_json(allowlist_path)
    if not isinstance(allowlist, dict):
        raise ValueError(f"{source_id} {UNKNOWN_ALLOWLIST_FILE} must be a JSON object")
    if clean_text(allowlist.get("site_id")) != source_id:
        raise ValueError(f"{source_id} {UNKNOWN_ALLOWLIST_FILE} site_id must match the package site_id")
    rules = allowlist.get("allowed_unknowns")
    if not isinstance(rules, list) or not rules:
        raise ValueError(f"{source_id} {UNKNOWN_ALLOWLIST_FILE} allowed_unknowns must be a non-empty list")

    compiled_rules: list[tuple[dict[str, Any], re.Pattern[str]]] = []
    for index, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict):
            raise ValueError(f"{source_id} {UNKNOWN_ALLOWLIST_FILE} rule {index} must be an object")
        if not clean_text(rule.get("reason")):
            raise ValueError(f"{source_id} {UNKNOWN_ALLOWLIST_FILE} rule {index} must include a reason")
        pattern = clean_text(rule.get("url_pattern"))
        if not pattern:
            raise ValueError(f"{source_id} {UNKNOWN_ALLOWLIST_FILE} rule {index} must include url_pattern")
        try:
            compiled_rules.append((rule, re.compile(pattern)))
        except re.error as exc:
            raise ValueError(f"{source_id} {UNKNOWN_ALLOWLIST_FILE} rule {index} has invalid url_pattern: {exc}") from exc

    unexpected: list[dict[str, Any]] = []
    matched_rules: set[int] = set()
    for url, record in unknown:
        matched = False
        for index, (rule, pattern) in enumerate(compiled_rules):
            if not pattern.search(url):
                continue
            if rule.get("target_type") and rule["target_type"] != record.get("target_type"):
                continue
            if rule.get("outcome") and rule["outcome"] != record.get("outcome"):
                continue
            matched = True
            matched_rules.add(index)
            break
        if not matched:
            unexpected.append({"url": url, "target_type": record.get("target_type"), "outcome": record.get("outcome")})

    if unexpected:
        raise ValueError(f"{source_id} manifest has unallowlisted unknown URL outcomes: {json.dumps(unexpected[:10], ensure_ascii=False)}")

    stale_rules = [
        str(rule.get("url_pattern"))
        for index, (rule, _pattern) in enumerate(compiled_rules)
        if index not in matched_rules
    ]
    if stale_rules:
        raise ValueError(f"{source_id} {UNKNOWN_ALLOWLIST_FILE} contains stale rules: {json.dumps(stale_rules, ensure_ascii=False)}")


def sitegraph_tokens(value: Any, *, cjk_max_n: int = 3, cap: int | None = None) -> set[str]:
    text = normalize_text(value)
    tokens: set[str] = set()
    if not text:
        return tokens
    for match in re.finditer(r"[\u4e00-\u9fff]{2,}|[a-z0-9][a-z0-9._-]{1,}", text):
        part = match.group(0)
        if re.fullmatch(r"[\u4e00-\u9fff]+", part):
            if len(part) <= 16:
                tokens.add(part)
            for size in range(2, cjk_max_n + 1):
                if len(part) < size:
                    continue
                for index in range(0, len(part) - size + 1):
                    tokens.add(part[index : index + size])
                    if cap is not None and len(tokens) >= cap:
                        return tokens
        else:
            tokens.add(part)
        if cap is not None and len(tokens) >= cap:
            return tokens
    return tokens


def query_alias_payload() -> dict[str, dict[str, list[str]]]:
    return {
        key: {"aliases": aliases}
        for key, aliases in sorted(QUERY_SYNONYMS.items())
    }


def validate_sitegraph_package(index_dir: Path) -> dict[str, Any]:
    missing = sorted(name for name in REQUIRED_SITEGRAPH_FILES if not (index_dir / name).exists())
    if missing:
        raise ValueError(f"sitegraph package missing required files: {', '.join(missing)}")

    manifest = read_json(index_dir / "manifest.json")
    if not isinstance(manifest, dict):
        raise ValueError("manifest.json must be a JSON object")
    source_id = clean_text(manifest.get("site_id")) or index_dir.parent.name or "sitegraph"
    quality = manifest.get("quality") if isinstance(manifest.get("quality"), dict) else {}
    if int(quality.get("errors", -1)) != 0:
        raise ValueError(f"{source_id} manifest quality.errors must be 0, got {quality.get('errors')}")
    if quality.get("all_discovered_urls_have_outcomes") is not True:
        raise ValueError(f"{source_id} manifest all_discovered_urls_have_outcomes must be true")
    if quality.get("attachment_policy") != "metadata_only":
        raise ValueError(f"{source_id} attachment_policy must be metadata_only, got {quality.get('attachment_policy')!r}")
    if quality.get("external_link_policy") != "record_only":
        raise ValueError(f"{source_id} external_link_policy must be record_only, got {quality.get('external_link_policy')!r}")
    assert_unknown_url_outcomes_allowlisted(index_dir, source_id, manifest)

    site = read_json(index_dir / "site.json")
    sections = read_json(index_dir / "sections.json")
    homepage_modules_payload = read_json(index_dir / "homepage_modules.json") if (index_dir / "homepage_modules.json").exists() else []
    homepage_modules = homepage_modules_payload.get("modules") if isinstance(homepage_modules_payload, dict) else homepage_modules_payload
    nav_tree = read_json(index_dir / "nav_tree.json") if (index_dir / "nav_tree.json").exists() else {}
    list_pages = read_jsonl(index_dir / "list_pages.jsonl")
    detail_pages = read_jsonl(index_dir / "detail_pages.jsonl")
    attachments = read_jsonl(index_dir / "attachments.jsonl")
    external_links = read_jsonl(index_dir / "external_links.jsonl")
    edges = read_jsonl(index_dir / "edges.jsonl")

    if not isinstance(site, dict):
        raise ValueError("site.json must be an object")
    if not isinstance(sections, list):
        raise ValueError("sections.json must be a list")
    if not isinstance(homepage_modules, list):
        raise ValueError("homepage_modules.json must be a list")

    actual_counts = {
        "sections": len(sections),
        "nav_nodes": count_nav_nodes(nav_tree if isinstance(nav_tree, dict) else {}),
        "homepage_modules": len(homepage_modules),
        "list_pages": len(list_pages),
        "detail_pages": len(detail_pages),
        "low_content_detail_pages": sum(1 for row in detail_pages if row.get("content_status") == "low_content"),
        "attachments": len(attachments),
        "external_links": len(external_links),
        "edges": len(edges),
        "url_outcomes": len(manifest.get("url_outcomes") if isinstance(manifest.get("url_outcomes"), dict) else {}),
    }
    manifest_totals = manifest.get("totals") if isinstance(manifest.get("totals"), dict) else {}
    mismatches = {
        field: {"manifest": int(manifest_totals.get(field, -1) or 0), "actual": actual_counts[field]}
        for field in COUNT_FIELDS
        if int(manifest_totals.get(field, -1) or 0) != actual_counts[field]
    }
    if mismatches:
        raise ValueError(f"{source_id} sitegraph package count mismatch: {json.dumps(mismatches, ensure_ascii=False)}")

    return {
        "source_index_dir": index_dir,
        "manifest": manifest,
        "site": site,
        "sections": sections,
        "homepage_modules": homepage_modules,
        "nav_tree": nav_tree,
        "list_pages": list_pages,
        "detail_pages": detail_pages,
        "attachments": attachments,
        "external_links": external_links,
        "edges": edges,
        "actual_counts": actual_counts,
    }


def section_label(section: dict[str, Any] | None) -> tuple[str, list[str], list[str]]:
    if not section:
        return "首页", ["首页"], []
    nav_path = [clean_text(item) for item in section.get("nav_path") or [] if clean_text(item)]
    if not nav_path:
        nav_path = [clean_text(section.get("name")) or clean_text(section.get("section_id"))]
    tags = [clean_text(item) for item in section.get("business_tags") or [] if clean_text(item)]
    return clean_text(section.get("name")) or nav_path[-1], nav_path, tags


def infer_facet(*, record_type: str, section: dict[str, Any] | None, title: str, content: str, external_category: str = "") -> str:
    section_name, nav_path, tags = section_label(section)
    text = normalize_text(" ".join([section_name, " ".join(nav_path), " ".join(tags), title, content, external_category]))
    if record_type == "external":
        return "system" if "external_system" in external_category else "external"
    if record_type == "attachment":
        return "download"
    if any(term in text for term in ("考试", "补考", "重修", "四六级", "慕课", "mooc", "考场")):
        return "exam"
    if any(term in text for term in ("规章", "制度", "管理办法", "policy", "regulation")):
        return "policy"
    if any(term in text for term in ("办事流程", "办理", "流程", "申请", "指南")):
        return "workflow"
    if any(term in text for term in ("下载", "表格", "附件", "resource", "download", "forms")):
        return "download"
    if any(term in text for term in ("新闻", "快讯", "动态", "news")):
        return "news"
    return "notice_article"


def summarize(content: str, title: str, limit: int = 180) -> str:
    text = clean_text(content)
    title_text = clean_text(title)
    if text.startswith(title_text):
        text = text[len(title_text):].strip()
    return text[:limit] if text else title_text


def attachment_metadata(item: dict[str, Any], *, parent_doc_id: str | None, section: dict[str, Any] | None) -> dict[str, Any]:
    section_name, nav_path, _ = section_label(section)
    return {
        "attachment_id": clean_text(item.get("attachment_id")) or sha1_text(str(item.get("url") or item.get("name"))),
        "name": clean_text(item.get("name")) or "未命名附件",
        "url": clean_text(item.get("url")),
        "extension": clean_text(item.get("extension")).lower() or None,
        "parent_url": clean_text(item.get("parent_url")),
        "parent_doc_id": parent_doc_id,
        "section_id": clean_text(section.get("section_id")) if section else None,
        "section": section_name,
        "nav_path": nav_path,
        "metadata_only": True,
        "position": item.get("position"),
    }


def doc_host(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc


def package_source_id(package: dict[str, Any]) -> str:
    return clean_text(package.get("site", {}).get("site_id")) or clean_text(package.get("manifest", {}).get("site_id")) or "sitegraph"


def site_source_id(site: dict[str, Any]) -> str:
    return clean_text(site.get("site_id")) or stable_slug(site.get("domain") or site.get("name"), fallback="site")


def site_display_name(site: dict[str, Any]) -> str:
    return clean_text(site.get("name")) or site_source_id(site)


def make_doc_meta(
    *,
    doc_index: int,
    doc_id: str,
    record_type: str,
    title: str,
    url: str,
    site: dict[str, Any],
    section: dict[str, Any] | None,
    page_type: str,
    published_at: str | None,
    publisher: str | None,
    summary: str,
    content_hash: str,
    attachment_count: int,
    facet: str,
    outcome: str,
    source_url: str | None = None,
    external_category: str | None = None,
    tags: list[str] | None = None,
    updated_at: str | None = None,
    recorded_at: str | None = None,
    version_date: str | None = None,
) -> dict[str, Any]:
    section_name, nav_path, section_tags = section_label(section)
    source_domain = clean_text(site.get("domain")) or doc_host(clean_text(site.get("base_url")))
    source_id = site_source_id(site)
    title_text = clean_text(title) or clean_text(url)
    canonical = canonical_title(title_text)
    all_tags = unique_strings([*(tags or []), *section_tags, facet, record_type], limit=16)
    published_clean = normalize_iso_date(published_at) or clean_text(published_at) or None
    updated_clean = normalize_iso_date(updated_at) or clean_text(updated_at) or None
    recorded_clean = clean_text(recorded_at) or None
    version_clean = (
        normalize_iso_date(version_date)
        or infer_version_date(" ".join([title_text, summary, " ".join(all_tags)]), published_at=published_clean)
    )
    if published_clean and version_clean and version_clean != published_clean:
        date_kind = "published_and_version"
        date_confidence = "source_published_and_title_version"
    elif published_clean:
        date_kind = "published"
        date_confidence = "source_published"
    elif version_clean:
        date_kind = "version"
        date_confidence = "title_or_attachment"
    elif recorded_clean:
        date_kind = "recorded"
        date_confidence = "recorded_only"
    else:
        date_kind = "undated"
        date_confidence = "unknown"
    task_kind = infer_task_kind(
        source_id=source_id,
        facet=facet,
        record_type=record_type,
        title=title_text,
        section=section_name,
        nav_path=nav_path,
        tags=all_tags,
    )
    academic_year = infer_academic_year(" ".join([title_text, summary]))
    term = infer_term(" ".join([title_text, summary]))
    return {
        "doc_index": doc_index,
        "id": doc_id,
        "record_type": record_type,
        "page_type": page_type,
        "facet": facet,
        "title": title_text,
        "url": clean_text(url),
        "source_id": source_id,
        "source": site_display_name(site),
        "source_domain": source_domain,
        "section_id": clean_text(section.get("section_id")) if section else None,
        "section": section_name,
        "nav_path": nav_path,
        "nav_path_text": " / ".join(nav_path),
        "canonical_title": canonical,
        "published_at": published_clean,
        "updated_at": updated_clean,
        "recorded_at": recorded_clean,
        "version_date": version_clean,
        "date_kind": date_kind,
        "date_confidence": date_confidence,
        "academic_year": academic_year,
        "term": term,
        "task_kind": task_kind,
        "authority_profile": authority_profile_for(source_id, task_kind),
        "dedupe_key": f"{source_id}:{record_type}:{sha1_text(normalize_text(canonical), length=16)}",
        "publisher": clean_text(publisher) or None,
        "summary": clean_text(summary),
        "attachment_count": int(attachment_count or 0),
        "hash": content_hash,
        "tags": all_tags,
        "collection_method": outcome,
        "provenance": {
            "site_id": source_id,
            "section_id": clean_text(section.get("section_id")) if section else None,
            "nav_path": nav_path,
            "source_url": source_url,
            "outcome": outcome,
            "external_category": external_category,
        },
    }


def build_documents(package: dict[str, Any]) -> dict[str, Any]:
    site = package["site"]
    source_id = site_source_id(site)
    source_name = site_display_name(site)
    sections_by_id = {clean_text(item.get("section_id")): item for item in package["sections"]}
    list_pages_by_url = {clean_text(item.get("url")): item for item in package["list_pages"]}
    detail_urls = {clean_text(item.get("url")) for item in package["detail_pages"]}
    detail_id_by_url: dict[str, str] = {}
    attachments_by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for attachment in package["attachments"]:
        attachments_by_parent[clean_text(attachment.get("parent_url"))].append(attachment)

    docs: list[dict[str, Any]] = []
    attachment_index: list[dict[str, Any]] = []
    external_index: list[dict[str, Any]] = []
    outcomes = {
        "detail_page_records": [],
        "attachment_metadata_records": [],
        "direct_attachment_records": [],
        "external_link_records": [],
        "utility_link_records": [],
    }

    for page in package["detail_pages"]:
        url = clean_text(page.get("url"))
        section = sections_by_id.get(clean_text(page.get("section_id")))
        title = clean_text(page.get("title")) or url
        content = clean_text(page.get("content_text"))
        doc_id = f"{source_id}-detail-{clean_text(page.get('page_id')) or sha1_text(url)}"
        detail_id_by_url[url] = doc_id
        attachments = [
            attachment_metadata(item, parent_doc_id=doc_id, section=section)
            for item in attachments_by_parent.get(url, [])
        ]
        facet = infer_facet(record_type="detail", section=section, title=title, content=content)
        meta = make_doc_meta(
            doc_index=len(docs),
            doc_id=doc_id,
            record_type="detail",
            title=title,
            url=url,
            site=site,
            section=section,
            page_type=clean_text(page.get("page_type")) or "detail_article_page",
            published_at=clean_text(page.get("published_at")) or None,
            updated_at=clean_text(page.get("updated_at")) or None,
            publisher=clean_text(page.get("publisher")) or None,
            summary=summarize(content, title),
            content_hash=clean_text(page.get("content_hash")) or sha1_text(content or title),
            attachment_count=len(attachments),
            facet=facet,
            outcome="search_record",
            source_url=url,
            tags=[clean_text(item) for item in page.get("headings") or []],
        )
        docs.append({**meta, "content": content or title, "attachments": attachments})
        outcomes["detail_page_records"].append({"url": url, "document_id": doc_id, "outcome": "search_record"})

    for attachment in package["attachments"]:
        parent_url = clean_text(attachment.get("parent_url"))
        parent_doc_id = detail_id_by_url.get(parent_url)
        section = None
        if parent_doc_id:
            parent_page = next((item for item in package["detail_pages"] if clean_text(item.get("url")) == parent_url), None)
            section = sections_by_id.get(clean_text(parent_page.get("section_id"))) if parent_page else None
        else:
            list_page = list_pages_by_url.get(parent_url)
            section = sections_by_id.get(clean_text(list_page.get("section_id"))) if list_page else None
        metadata = attachment_metadata(attachment, parent_doc_id=parent_doc_id, section=section)
        attachment_index.append(metadata)
        outcomes["attachment_metadata_records"].append(
            {
                "url": metadata["url"],
                "name": metadata["name"],
                "parent_url": metadata["parent_url"],
                "parent_doc_id": parent_doc_id,
                "outcome": "attachment_metadata_only",
            }
        )
        if parent_doc_id is None:
            doc_id = f"{source_id}-attachment-{metadata['attachment_id']}"
            metadata["parent_doc_id"] = doc_id
            title = metadata["name"]
            facet = "download"
            meta = make_doc_meta(
                doc_index=len(docs),
                doc_id=doc_id,
                record_type="attachment",
                title=title,
                url=metadata["url"],
                site=site,
            section=section,
            page_type="attachment_metadata",
            published_at=None,
            version_date=infer_version_date(title),
            publisher=None,
            summary=f"附件元数据：{title}。来源栏目：{metadata['section']}。",
            content_hash=sha1_text(metadata["url"] or title),
                attachment_count=1,
                facet=facet,
                outcome="attachment_metadata_only",
                source_url=metadata["parent_url"],
                tags=[metadata.get("extension") or "", "附件", "下载"],
            )
            docs.append({**meta, "content": meta["summary"], "attachments": [metadata]})
            outcomes["direct_attachment_records"].append(
                {"url": metadata["url"], "name": title, "document_id": doc_id, "outcome": "search_record"}
            )

    for link in package["external_links"]:
        label = clean_text(link.get("label")) or clean_text(link.get("url"))
        url = clean_text(link.get("url"))
        section = sections_by_id.get(clean_text(link.get("source_section_id")))
        category = clean_text(link.get("category")) or "external_link"
        doc_id = f"{source_id}-external-{clean_text(link.get('external_id')) or sha1_text(url + label)}"
        facet = infer_facet(record_type="external", section=section, title=label, content=url, external_category=category)
        meta = make_doc_meta(
            doc_index=len(docs),
            doc_id=doc_id,
            record_type="external",
            title=label,
            url=url,
            site=site,
            section=section,
            page_type="external_link_record",
            published_at=None,
            recorded_at=clean_text(link.get("recorded_at")) or None,
            version_date=infer_version_date(label),
            publisher=None,
            summary=f"{source_name}记录的外链：{label}。该链接只记录入口，不递归抓取内容。",
            content_hash=sha1_text(url + label),
            attachment_count=0,
            facet=facet,
            outcome="external_record_only",
            source_url=clean_text(link.get("source_url")),
            external_category=category,
            tags=[category, doc_host(url), label],
        )
        docs.append({**meta, "content": meta["summary"], "attachments": []})
        external_index.append(
            {
                "external_id": clean_text(link.get("external_id")) or sha1_text(url + label),
                "label": label,
                "url": url,
                "category": category,
                "source_url": clean_text(link.get("source_url")),
                "source_section_id": clean_text(link.get("source_section_id")) or None,
                "document_id": doc_id,
                "outcome": "external_record_only",
            }
        )
        outcomes["external_link_records"].append({"url": url, "label": label, "document_id": doc_id, "outcome": "external_record_only"})

    for edge in package["edges"]:
        label = clean_text(edge.get("anchor_text"))
        if label != "考试信息查询":
            continue
        target_url = clean_text(edge.get("to_url"))
        section = None
        target_list = list_pages_by_url.get(target_url)
        if target_list:
            section = sections_by_id.get(clean_text(target_list.get("section_id")))
        doc_id = f"{source_id}-utility-{clean_text(edge.get('edge_id')) or sha1_text(target_url + label)}"
        meta = make_doc_meta(
            doc_index=len(docs),
            doc_id=doc_id,
            record_type="utility",
            title=label,
            url=target_url,
            site=site,
            section=section,
            page_type="utility_link_record",
            published_at=None,
            publisher=None,
            summary=f"{source_name}首页记录的考试信息查询入口。",
            content_hash=sha1_text(target_url + label),
            attachment_count=0,
            facet="exam",
            outcome="search_record",
            source_url=clean_text(edge.get("from_url")),
            tags=["考试", "查询", "入口"],
        )
        docs.append({**meta, "content": meta["summary"], "attachments": []})
        outcomes["utility_link_records"].append({"url": target_url, "label": label, "document_id": doc_id, "outcome": "search_record"})

    return {
        "documents": docs,
        "attachment_index": attachment_index,
        "external_index": external_index,
        "outcomes": outcomes,
    }


def add_postings(index: dict[str, dict[str, set[int]]], doc_index: int, field_code: str, tokens: set[str]) -> None:
    for token in tokens:
        if not token:
            continue
        index[token][field_code].add(doc_index)


def compact_postings(raw_index: dict[str, dict[str, set[int]]]) -> dict[str, dict[str, list[int]]]:
    tokens: dict[str, dict[str, list[int]]] = {}
    for token, fields in raw_index.items():
        compact_fields: dict[str, list[int]] = {}
        for field, ids in fields.items():
            compact_fields[field] = sorted(ids)
        tokens[token] = compact_fields
    return tokens


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
        "version": "sitegraph-light-inverted-progressive",
        "tokenizer": "nfkc-lower-cjk-ngram-code",
        "field_codes": LIGHT_FIELD_CODES,
        "entry_fields": ["title", "section", "nav_path", "tag", "attachment", "external", "system"],
        "tokens": compact_postings(raw_index),
    }


def build_body_inverted_index(documents: list[dict[str, Any]]) -> dict[str, Any]:
    raw_index: dict[str, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    for document in documents:
        doc_index = int(document["doc_index"])
        add_postings(raw_index, doc_index, FIELD_CODES["summary"], sitegraph_tokens(document.get("summary"), cjk_max_n=4, cap=80))
        add_postings(raw_index, doc_index, FIELD_CODES["content"], sitegraph_tokens(document.get("content"), cjk_max_n=3, cap=180))
    return {
        "version": "sitegraph-body-inverted-progressive",
        "tokenizer": "nfkc-lower-cjk-ngram-code",
        "field_codes": BODY_FIELD_CODES,
        "entry_fields": ["summary", "content"],
        "tokens": compact_postings(raw_index),
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


def shard_year(document: dict[str, Any]) -> str:
    date_text = clean_text(document.get("published_at")) or clean_text(document.get("version_date"))
    match = re.search(r"(20\d{2}|19\d{2})", date_text)
    return match.group(1) if match else "undated"


def shard_section(document: dict[str, Any]) -> str:
    nav_path = document.get("nav_path") if isinstance(document.get("nav_path"), list) else []
    section = nav_path[0] if nav_path else document.get("section_id") or document.get("section")
    return stable_slug(section, fallback="root", max_length=32)


def shard_bucket(document: dict[str, Any], bucket_count: int = 4) -> str:
    digest = hashlib.sha1(str(document.get("id") or "").encode("utf-8")).hexdigest()
    return f"b{int(digest[:2], 16) % bucket_count}"


def shard_id_for_document(document: dict[str, Any]) -> str:
    return "__".join(
        [
            stable_slug(document.get("facet"), fallback="facet"),
            stable_slug(document.get("record_type"), fallback="record"),
            shard_year(document),
            shard_section(document),
            shard_bucket(document),
        ]
    )


def build_locality_shards(documents: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for document in documents:
        groups[shard_id_for_document(document)].append(document)

    shard_refs: list[dict[str, Any]] = []
    shard_by_id: dict[str, dict[str, Any]] = {}
    shard_filter: dict[str, dict[str, Any]] = {}
    for shard_id in sorted(groups):
        shard_docs = sorted(groups[shard_id], key=lambda item: int(item["doc_index"]))
        facets = sorted({str(item.get("facet")) for item in shard_docs})
        record_types = sorted({str(item.get("record_type")) for item in shard_docs})
        sections = sorted({str(item.get("section_id") or "unknown") for item in shard_docs})
        years = sorted({shard_year(item) for item in shard_docs})
        payload_docs = [
            {key: value for key, value in document.items() if key != "shard"}
            for document in shard_docs
        ]
        filter_tokens = sorted({
            token
            for document in payload_docs
            for token in sitegraph_tokens(exhaustive_scan_blob(document), cjk_max_n=5)
        })
        filter_bitset = build_filter_bitset(filter_tokens)
        filter_hash = sha256_text(filter_bitset["bitset_base64"], length=32)
        artifact = write_hashed_json(PUBLIC_SHARD_DIR, f"full.{shard_id}", payload_docs, compact=True)
        shard_ref = {
            "shard_id": shard_id,
            "path": artifact["path"],
            "sha256": artifact["sha256"],
            "bytes": artifact["bytes"],
            "count": len(shard_docs),
            "contains": "full_documents",
            "facet_range": facets,
            "record_type_range": record_types,
            "section_range": sections[:24],
            "year_range": years,
            "hash_bucket": shard_id.rsplit("__", 1)[-1],
            "filter_token_count": len(filter_tokens),
            "filter_sha256": filter_hash,
        }
        shard_filter[shard_id] = {
            **filter_bitset,
            "token_count": len(filter_tokens),
            "sha256": filter_hash,
            "hash_algorithm": "bloom-fnv1a32-utf8",
            "coverage_fields": ["title", "section", "nav_path", "summary", "content", "attachments", "url"],
        }
        shard_refs.append(shard_ref)
        shard_by_id[shard_id] = shard_ref
        for document in shard_docs:
            document["shard"] = {
                "shard_id": shard_id,
            }
    return shard_refs, shard_by_id, shard_filter


def artifact_entry(artifact: dict[str, Any], *, role: str, count: int | None = None, load: str = "on_demand") -> dict[str, Any]:
    entry = {
        "path": artifact["path"],
        "sha256": artifact["sha256"],
        "bytes": artifact["bytes"],
        "role": role,
        "load": load,
    }
    if count is not None:
        entry["count"] = count
    return entry


def aggregate_counts(packages: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for package in packages:
        counts.update({field: int(package["actual_counts"].get(field, 0) or 0) for field in COUNT_FIELDS})
    return {field: int(counts.get(field, 0)) for field in COUNT_FIELDS}


def source_truth_counts(packages: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    return {package_source_id(package): dict(package["actual_counts"]) for package in packages}


def aggregate_quality(packages: list[dict[str, Any]]) -> dict[str, Any]:
    qualities = [
        package.get("manifest", {}).get("quality")
        for package in packages
        if isinstance(package.get("manifest", {}).get("quality"), dict)
    ]
    return {
        "all_discovered_urls_have_outcomes": all(item.get("all_discovered_urls_have_outcomes") is True for item in qualities),
        "errors": sum(int(item.get("errors", 0) or 0) for item in qualities),
        "attachment_policy": "metadata_only" if all(item.get("attachment_policy") == "metadata_only" for item in qualities) else "mixed",
        "external_link_policy": "record_only" if all(item.get("external_link_policy") == "record_only" for item in qualities) else "mixed",
        "sources": {
            package_source_id(package): package.get("manifest", {}).get("quality")
            for package in packages
        },
    }


def latest_upstream_generated_at(packages: list[dict[str, Any]]) -> str | None:
    values = [
        clean_text(package.get("manifest", {}).get("generated_at"))
        for package in packages
        if clean_text(package.get("manifest", {}).get("generated_at"))
    ]
    return max(values) if values else None


def source_entries(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for package in packages:
        source_id = package_source_id(package)
        entries.append(
            {
                "source_id": source_id,
                "source_kind": "sitegraph",
                "artifact_root": f"generated/collections/{COLLECTION_ID}/sitegraph",
                "upstream_generated_at": clean_text(package["manifest"].get("generated_at")) or None,
                "display_name": site_display_name(package["site"]),
                "truth_counts": dict(package["actual_counts"]),
                "quality": package["manifest"].get("quality"),
            }
        )
    return entries


def merge_built_packages(built_packages: list[dict[str, Any]]) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    attachment_index: list[dict[str, Any]] = []
    external_index: list[dict[str, Any]] = []
    outcomes: dict[str, list[dict[str, Any]]] = {
        "detail_page_records": [],
        "attachment_metadata_records": [],
        "direct_attachment_records": [],
        "external_link_records": [],
        "utility_link_records": [],
    }
    for built in built_packages:
        for document in built["documents"]:
            document["doc_index"] = len(documents)
            documents.append(document)
        attachment_index.extend(built["attachment_index"])
        external_index.extend(built["external_index"])
        for key in outcomes:
            outcomes[key].extend(built["outcomes"].get(key) or [])
    return {
        "documents": documents,
        "attachment_index": attachment_index,
        "external_index": external_index,
        "outcomes": outcomes,
    }


def write_public_index(packages: list[dict[str, Any]], built: dict[str, Any], *, shard_size: int) -> dict[str, Any]:
    # Removing the directories prevents stale fixed-name or obsolete indexes from being deployed.
    for directory in (PUBLIC_INDEX_DIR, OBSOLETE_INDEX_DIR):
        if directory.exists():
            shutil.rmtree(directory)
    PUBLIC_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_SHARD_DIR.mkdir(parents=True, exist_ok=True)

    documents = built["documents"]
    full_shards, _, shard_filter = build_locality_shards(documents)

    doc_meta_light_fields = {
        "doc_index",
        "id",
        "record_type",
        "facet",
        "title",
        "source_id",
        "section",
        "nav_path_text",
        "published_at",
        "version_date",
        "date_kind",
        "task_kind",
        "shard",
    }
    doc_meta_light = [
        {key: document.get(key) for key in doc_meta_light_fields if key in document}
        for document in documents
    ]
    light_inverted_index = build_light_inverted_index(documents)
    body_inverted_index = build_body_inverted_index(documents)

    section_counts = Counter(clean_text(document.get("section_id")) or "unknown" for document in documents)
    section_index = []
    for package in packages:
        source_id = package_source_id(package)
        source = site_display_name(package["site"])
        for section in package["sections"]:
            section_id = clean_text(section.get("section_id"))
            section_name, nav_path, tags = section_label(section)
            section_index.append(
                {
                    "source_id": source_id,
                    "source": source,
                    "section_id": section_id,
                    "name": section_name,
                    "url": clean_text(section.get("url")),
                    "section_type": clean_text(section.get("section_type")),
                    "nav_path": nav_path,
                    "business_tags": tags,
                    "document_count": section_counts.get(section_id, 0),
                }
            )

    query_aliases = query_alias_payload()
    artifacts: dict[str, dict[str, Any]] = {}
    doc_meta_artifact = write_hashed_json(PUBLIC_ARTIFACT_DIR, "doc_meta_light", doc_meta_light, compact=True)
    light_index_artifact = write_hashed_json(PUBLIC_ARTIFACT_DIR, "light_inverted_index", light_inverted_index, compact=True)
    body_index_artifact = write_hashed_json(PUBLIC_ARTIFACT_DIR, "body_inverted_index", body_inverted_index, compact=True)
    section_artifact = write_hashed_json(PUBLIC_ARTIFACT_DIR, "section_index", section_index, compact=True)
    attachment_artifact = write_hashed_json(PUBLIC_ARTIFACT_DIR, "attachment_index", built["attachment_index"], compact=True)
    external_artifact = write_hashed_json(PUBLIC_ARTIFACT_DIR, "external_index", built["external_index"], compact=True)
    aliases_artifact = write_hashed_json(PUBLIC_ARTIFACT_DIR, "query_aliases", query_aliases, compact=False)
    shard_catalog_artifact = write_hashed_json(PUBLIC_ARTIFACT_DIR, "shard_catalog", full_shards, compact=True)
    shard_filter_artifact = write_hashed_json(PUBLIC_ARTIFACT_DIR, "shard_filter", shard_filter, compact=True)
    outcomes_artifact = write_hashed_json(PUBLIC_ARTIFACT_DIR, "outcomes", built["outcomes"], compact=True)

    artifacts["doc_meta_light"] = artifact_entry(doc_meta_artifact, role="doc_meta_light", count=len(doc_meta_light), load="initial")
    artifacts["light_inverted_index"] = artifact_entry(light_index_artifact, role="light_inverted_index", load="initial")
    artifacts["query_aliases"] = artifact_entry(aliases_artifact, role="query_aliases", count=len(query_aliases), load="initial")
    artifacts["body_inverted_index"] = artifact_entry(body_index_artifact, role="body_inverted_index", load="deep_search")
    artifacts["section_index"] = artifact_entry(section_artifact, role="section_index", count=len(section_index), load="on_demand")
    artifacts["attachment_index"] = artifact_entry(attachment_artifact, role="attachment_index", count=len(built["attachment_index"]), load="on_demand")
    artifacts["external_index"] = artifact_entry(external_artifact, role="external_index", count=len(built["external_index"]), load="on_demand")
    artifacts["shard_catalog"] = artifact_entry(shard_catalog_artifact, role="shard_catalog", count=len(full_shards), load="verify")
    artifacts["shard_filter"] = artifact_entry(shard_filter_artifact, role="shard_filter", count=len(shard_filter), load="verify")
    artifacts["outcomes"] = artifact_entry(outcomes_artifact, role="outcomes", load="audit")

    upstream_counts = aggregate_counts(packages)
    per_source_truth_counts = source_truth_counts(packages)
    upstream_quality = aggregate_quality(packages)
    record_counts = Counter(document["record_type"] for document in documents)
    facet_counts = Counter(document["facet"] for document in documents)
    first_screen_artifacts = ["doc_meta_light", "light_inverted_index", "query_aliases"]
    total_full_scan_bytes = sum(int(item["bytes"]) for item in full_shards)
    max_full_shard_bytes = max((int(item["bytes"]) for item in full_shards), default=0)
    avg_full_shard_bytes = round(total_full_scan_bytes / max(1, len(full_shards)), 2)
    first_screen_bytes = sum(int(artifacts[name]["bytes"]) for name in first_screen_artifacts)
    representative_full_scan_ms = measure_representative_full_scan_ms(documents, "校历")
    size_report = {
        "generated_at": now_iso(),
        "first_screen_files": [
            {"name": name, "path": artifacts[name]["path"], "bytes": artifacts[name]["bytes"]}
            for name in first_screen_artifacts
        ],
        "first_screen_bytes": first_screen_bytes,
        "first_screen_total_bytes": first_screen_bytes,
        "body_index_bytes": artifacts["body_inverted_index"]["bytes"],
        "full_scan_total_bytes": total_full_scan_bytes,
        "shard_count": len(full_shards),
        "max_shard_bytes": max_full_shard_bytes,
        "avg_shard_bytes": avg_full_shard_bytes,
        "full_shard_count": len(full_shards),
        "max_full_shard_bytes": max_full_shard_bytes,
        "avg_full_shard_bytes": avg_full_shard_bytes,
        "max_full_shard_documents": max((int(item["count"]) for item in full_shards), default=0),
        "avg_full_shard_documents": round(sum(int(item["count"]) for item in full_shards) / max(1, len(full_shards)), 2),
        "representative_query_phase_timings": {
            "query": "校历",
            "quick_ms": 0,
            "body_ms": 0,
            "hydrate_ms": 0,
            "verify_scan_ms": representative_full_scan_ms,
        },
        "exhaustive_scan": {
            "shard_count": len(full_shards),
            "max_shard_bytes": max_full_shard_bytes,
            "avg_shard_bytes": avg_full_shard_bytes,
            "estimated_full_scan_bytes": total_full_scan_bytes,
            "representative_query": "校历",
            "representative_query_full_scan_time_ms": representative_full_scan_ms,
        },
    }
    size_artifact = write_hashed_json(PUBLIC_ARTIFACT_DIR, "size_report", size_report, compact=False)
    artifacts["size_report"] = artifact_entry(size_artifact, role="size_report", load="audit")

    generated_at = now_iso()
    upstream_generated_at = latest_upstream_generated_at(packages) or generated_at
    manifest = {
        "generated_at": generated_at,
        "strategy": "progressive-verifiable-static-search",
        "producer_repo": os.environ.get("GITHUB_REPOSITORY") or "hicancan/njupt-search",
        "producer_ref": producer_ref(),
        "site_id": COLLECTION_ID,
        "collection_id": COLLECTION_ID,
        "sources": source_entries(packages),
        "artifact_path": f"generated/collections/{COLLECTION_ID}",
        "upstream_generated_at": upstream_generated_at,
        "truth_counts": upstream_counts,
        "total_documents": len(documents),
        "record_counts": dict(record_counts),
        "facet_counts": dict(facet_counts),
        "exam_vertical_preserved": True,
        "core_search": {
            "algorithm": "progressive exhaustive static search: light inverted recall, body inverted recall, candidate shard hydration, then complete full shard scan",
            "execution_model": "pure_frontend_worker",
            "light_first_screen": True,
            "first_screen_artifacts": first_screen_artifacts,
            "body_index_loading": "on_deep_search",
            "full_text_loading": "progressive_candidate_hydration_then_exhaustive_full_scan",
            "search_worker": True,
        },
        "progressive_search": {
            "total_shards": len(full_shards),
            "total_documents": len(documents),
            "full_scan_supported": True,
            "progressive_events": True,
            "artifact_roles": [
                "manifest",
                "doc_meta_light",
                "light_inverted_index",
                "query_aliases",
                "body_inverted_index",
                "shard_catalog",
                "shard_filter",
                "full_shards",
                "size_report",
                "outcomes",
            ],
        },
        "coverage_contract": {
            "coverage_fields": ["title", "section", "nav_path", "summary", "content", "attachments", "url"],
            "proof": {
                "indexed_fields": ["title", "section", "nav_path", "tags", "attachments", "external", "system", "summary", "content"],
                "full_scan_fields": ["title", "section", "nav_path", "summary", "content", "attachments", "url"],
            },
            "total_shards": len(full_shards),
            "total_documents": len(documents),
        },
        "verification_contract": {
            "shard_filter_supported": True,
            "proved_skip_supported": True,
            "scan_fallback_supported": True,
            "filter_artifact": "shard_filter",
            "catalog_artifact": "shard_catalog",
        },
        "artifacts": artifacts,
        "sitegraph": {
            "truth_counts": upstream_counts,
            "source_truth_counts": per_source_truth_counts,
            "quality": upstream_quality,
            "upstream_generated_at": upstream_generated_at,
            "detail_page_records": record_counts.get("detail", 0),
            "attachment_metadata_records": len(built["attachment_index"]),
            "direct_attachment_records": record_counts.get("attachment", 0),
            "external_link_records": len(built["external_index"]),
            "external_document_records": record_counts.get("external", 0),
            "utility_link_records": record_counts.get("utility", 0),
            "attachment_policy": "metadata_only",
            "external_link_policy": "record_only",
            "full_shards": full_shards,
            "shard_strategy": {
                "version": "locality-facet-record-year-section-hash-progressive",
                "dimensions": ["facet", "record_type", "year", "top_nav_section", "hash_bucket"],
                "hash_bucket_count": 4,
                "sequential_fixed_size_shards": False,
            },
            "indexes": artifacts,
        },
    }
    write_json(PUBLIC_INDEX_DIR / "manifest.json", manifest)
    return manifest


def build_sitegraph_indexes(index_dirs: list[Path] | tuple[Path, ...], *, shard_size: int = 1000) -> dict[str, Any]:
    packages = [validate_sitegraph_package(index_dir) for index_dir in index_dirs]
    built = merge_built_packages([build_documents(package) for package in packages])
    manifest = write_public_index(packages, built, shard_size=shard_size)
    return {
        "sitegraph_indexes": [str(index_dir) for index_dir in index_dirs],
        "source_ids": [package_source_id(package) for package in packages],
        "generated_documents": manifest["total_documents"],
        "detail_page_records": manifest["sitegraph"]["detail_page_records"],
        "attachment_metadata_records": manifest["sitegraph"]["attachment_metadata_records"],
        "direct_attachment_records": manifest["sitegraph"]["direct_attachment_records"],
        "external_link_records": manifest["sitegraph"]["external_link_records"],
        "utility_link_records": manifest["sitegraph"]["utility_link_records"],
        "truth_counts": manifest["sitegraph"]["truth_counts"],
        "full_shards": manifest["sitegraph"]["full_shards"],
        "public_index": str(PUBLIC_INDEX_DIR),
    }


def build_sitegraph_index(index_dir: Path, *, shard_size: int = 1000) -> dict[str, Any]:
    return build_sitegraph_indexes([index_dir], shard_size=shard_size)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build generated collection search artifacts for njupt-search.")
    parser.add_argument(
        "--source-package",
        dest="source_packages",
        action="append",
        type=Path,
        default=None,
        help="Path to an audited njupt-site-graph source package index. Repeat for multiple source packages.",
    )
    parser.add_argument("--collection-id", default=COLLECTION_ID)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--shard-size", type=int, default=1000, help="Number of full documents per shard")
    args = parser.parse_args()
    configure_collection_output(args.collection_id, args.out)
    source_packages = args.source_packages or load_collection_source_packages()
    summary = build_sitegraph_indexes([path.resolve() for path in source_packages], shard_size=args.shard_size)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
