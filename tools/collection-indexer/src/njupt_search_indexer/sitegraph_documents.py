from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from typing import Any

from .sitegraph_text import (
    canonical_title,
    clean_text,
    doc_host,
    normalize_text,
    sha1_text,
    stable_slug,
    summarize,
    unique_strings,
)


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


def infer_task_kind(
    *,
    source_id: str,
    facet: str,
    record_type: str,
    title: str,
    section: str,
    nav_path: list[str],
    tags: list[str],
) -> str:
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


def section_label(section: dict[str, Any] | None) -> tuple[str, list[str], list[str]]:
    if not section:
        return "首页", ["首页"], []
    nav_path = [clean_text(item) for item in section.get("nav_path") or [] if clean_text(item)]
    if not nav_path:
        nav_path = [clean_text(section.get("name")) or clean_text(section.get("section_id"))]
    tags = [clean_text(item) for item in section.get("business_tags") or [] if clean_text(item)]
    return clean_text(section.get("name")) or nav_path[-1], nav_path, tags


def infer_facet(
    *,
    record_type: str,
    section: dict[str, Any] | None,
    title: str,
    content: str,
    external_category: str = "",
) -> str:
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


def attachment_metadata(
    item: dict[str, Any],
    *,
    parent_doc_id: str | None,
    section: dict[str, Any] | None,
) -> dict[str, Any]:
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
