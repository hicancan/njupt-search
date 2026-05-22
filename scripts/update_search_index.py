import base64
import fnmatch
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any
from urllib.parse import quote, urljoin, urlparse, urlunparse

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
INDEX_DIR = os.path.join(PUBLIC_DIR, "index")
DOCUMENTS_PATH = os.path.join(INDEX_DIR, "documents.json")
MANIFEST_PATH = os.path.join(INDEX_DIR, "manifest.json")
GITHUB_SOURCE_CONFIG_PATH = os.path.join(BASE_DIR, "config", "github_search_sources.json")

BEIJING_TZ = timezone(timedelta(hours=8))
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

MAX_DOCS_PER_SOURCE = 18
DETAIL_FETCH_LIMIT_PER_SOURCE = 14
REQUEST_TIMEOUT = 16
MIN_STUDENT_SCORE = 0.55
GITHUB_TOKEN_ENV = "NJUPT_SEARCH_GITHUB_TOKEN"
GITHUB_API_BASE = "https://api.github.com"
GITHUB_FILE_SIZE_LIMIT_BYTES = 250_000

ATTACHMENT_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".zip",
    ".rar",
}

STATIC_EXTENSIONS = {
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".webp",
    ".mp4",
    ".mp3",
}

NAV_TITLES = {
    "首页",
    "学校首页",
    "联系我们",
    "设为首页",
    "加入收藏",
    "更多",
    "more",
    "通知公告",
    "新闻动态",
    "下载专区",
    "规章制度",
    "政策文件",
    "工作职能",
    "部门领导",
    "机构设置",
    "学生事务",
    "教师事务",
    "教学运行",
    "联系我们",
    "信息公开",
    "校历查询",
    "办事流程",
    "常用下载",
    "旧版回顾",
}

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "考试": ["考试", "期末", "补考", "重修", "四六级", "考场", "准考证", "考试安排", "课程结束考试"],
    "选课": ["选课", "课程", "慕课", "教学安排", "培养方案", "成绩", "学籍", "校历", "转专业", "推免"],
    "竞赛": ["竞赛", "挑战杯", "互联网+", "大创", "创新创业", "创业", "科创", "iCAN", "校赛", "获奖"],
    "奖助": ["奖学金", "助学金", "资助", "困难认定", "评优", "公示", "助研", "助管", "助教"],
    "就业": ["就业", "招聘", "宣讲", "岗位", "实习", "双选会", "用人单位", "生源信息"],
    "讲座": ["讲座", "报告", "论坛", "学术", "活动预告", "沙龙", "培训"],
    "生活": ["宿舍", "返校", "离校", "医保", "体检", "停水", "停电", "交通", "消防", "户籍", "班车", "图书馆", "开放"],
    "学院": ["学院", "毕业设计", "答辩", "导师", "班级事务", "实验安排"],
    "研究生": ["研究生", "硕士", "博士", "学位", "答辩", "培养", "硕博连读", "研工"],
    "项目": ["项目", "课题", "基金", "申报", "科研", "成果转化", "专利"],
    "资料": ["资料", "下载", "手册", "指南", "流程", "表格"],
}

POSITIVE_KEYWORDS = [
    "考试",
    "选课",
    "课程",
    "成绩",
    "四六级",
    "重修",
    "补考",
    "转专业",
    "推免",
    "培养",
    "学位",
    "答辩",
    "毕业设计",
    "实习",
    "奖学金",
    "助学金",
    "困难认定",
    "评优",
    "公示",
    "宿舍",
    "返校",
    "离校",
    "医保",
    "体检",
    "停水",
    "停电",
    "交通管制",
    "讲座",
    "竞赛",
    "报名",
    "开放",
    "安排",
    "评选",
    "大创",
    "挑战杯",
    "互联网+",
    "校赛",
    "创新大赛",
    "创业基金",
    "社团",
    "志愿服务",
    "招聘",
    "宣讲会",
    "实习岗位",
]

NEGATIVE_KEYWORDS = [
    "党委理论学习",
    "巡察",
    "审计",
    "干部任免",
    "教职工",
    "职工",
    "离休人员",
    "离退休",
    "退休",
    "幼儿园",
    "会议纪要",
    "采购",
    "招标",
    "比选",
    "中标",
    "成交",
    "验收",
    "资产处置",
    "责任书签订",
    "签订仪式",
    "领导责任制",
    "党建研究",
    "行政统计",
    "工会活动",
]


@dataclass(frozen=True)
class SourceConfig:
    id: str
    name: str
    base_url: str
    list_urls: tuple[str, ...]
    audience: tuple[str, ...]
    source_weight: float


@dataclass(frozen=True)
class GitHubSourceConfig:
    repo: str
    label: str
    category: str
    audience: tuple[str, ...]
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    max_files: int
    source_weight: float
    enabled: bool


SOURCES: tuple[SourceConfig, ...] = (
    SourceConfig("jwc", "本科生院 / 教务处", "https://jwc.njupt.edu.cn/", ("https://jwc.njupt.edu.cn/1594/list.htm",), ("本科生",), 1.0),
    SourceConfig("xsc", "学生工作处", "https://xsc.njupt.edu.cn/", ("https://xsc.njupt.edu.cn/",), ("本科生",), 0.96),
    SourceConfig("pg", "研究生院", "https://pg.njupt.edu.cn/", ("https://pg.njupt.edu.cn/",), ("研究生",), 0.96),
    SourceConfig("ygb", "研究生工作部", "https://ygb.njupt.edu.cn/", ("https://ygb.njupt.edu.cn/",), ("研究生",), 0.92),
    SourceConfig("youth", "团委 / 青春南邮", "https://youth.njupt.edu.cn/", ("https://youth.njupt.edu.cn/",), ("本科生", "研究生"), 0.9),
    SourceConfig("cxcy", "创新创业教育学院", "https://cxcy.njupt.edu.cn/", ("https://cxcy.njupt.edu.cn/",), ("本科生", "研究生"), 0.9),
    SourceConfig("job", "就业信息网", "https://njupt.91job.org.cn/", ("https://njupt.91job.org.cn/",), ("本科生", "研究生"), 0.88),
    SourceConfig("lib", "图书馆", "https://lib.njupt.edu.cn/", ("https://lib.njupt.edu.cn/",), ("本科生", "研究生", "教职工"), 0.82),
    SourceConfig("bwc", "保卫处", "https://bwc.njupt.edu.cn/", ("https://bwc.njupt.edu.cn/",), ("本科生", "研究生", "教职工"), 0.8),
    SourceConfig("hqc", "后勤管理处", "https://hqc.njupt.edu.cn/", ("https://hqc.njupt.edu.cn/",), ("本科生", "研究生", "教职工"), 0.8),
)


def get_beijing_time() -> datetime:
    return datetime.now(timezone.utc).astimezone(BEIJING_TZ)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path, "", parsed.query, ""))


def same_domain(url: str, source: SourceConfig) -> bool:
    host = urlparse(url).netloc.lower()
    source_host = urlparse(source.base_url).netloc.lower()
    return host == source_host or host.endswith("." + source_host)


def extension_from_url(url: str) -> str:
    return os.path.splitext(urlparse(url).path.lower())[1]


def contains_relevant_keyword(text: str) -> bool:
    lowered = text.lower()
    all_keywords = POSITIVE_KEYWORDS + [keyword for keywords in CATEGORY_KEYWORDS.values() for keyword in keywords]
    return any(keyword.lower() in lowered for keyword in all_keywords)


def looks_like_notice_link(title: str, parent_text: str, url: str, now: datetime) -> bool:
    stripped_title = title.strip()
    lowered_title = stripped_title.lower()
    path = urlparse(url).path.lower()

    if stripped_title in NAV_TITLES or lowered_title in NAV_TITLES:
        return False
    if path.endswith("/main.htm") or path.endswith("main.htm") or path.endswith("list.htm"):
        return False
    if len(stripped_title) < 6:
        return False

    combined = f"{stripped_title} {parent_text} {url}"
    has_date = parse_date(combined, now) is not None
    has_detail_shape = bool(re.search(r"/20\d{2}/\d{4}/", path)) or path.endswith("page.htm")
    has_relevant_keyword = contains_relevant_keyword(combined)

    return has_detail_shape or (has_date and has_relevant_keyword)


def fetch_html(url: str) -> str:
    response = requests.get(url, headers=HEADERS, verify=False, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def post_json(url: str, body: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(url, json=body, headers=HEADERS, verify=False, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def parse_date(text: str, now: datetime) -> str | None:
    patterns = [
        r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})",
        r"(20\d{2})(\d{2})(\d{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            year, month, day = match.groups()
            try:
                return datetime(int(year), int(month), int(day), tzinfo=BEIJING_TZ).date().isoformat()
            except ValueError:
                return None

    month_day = re.search(r"(?<!\d)(\d{1,2})[-/.月](\d{1,2})(?:日)?(?!\d)", text)
    if month_day:
        month, day = month_day.groups()
        try:
            candidate = datetime(now.year, int(month), int(day), tzinfo=BEIJING_TZ)
            if (candidate - now).days > 30:
                candidate = datetime(now.year - 1, int(month), int(day), tzinfo=BEIJING_TZ)
            return candidate.date().isoformat()
        except ValueError:
            return None

    return None


def calculate_freshness(published_at: str | None, now: datetime) -> float:
    if not published_at:
        return 0.45
    try:
        published = datetime.fromisoformat(published_at).replace(tzinfo=BEIJING_TZ)
    except ValueError:
        return 0.45

    days = (now - published).days
    if days < 0:
        return 0.92
    if days <= 3:
        return 1.0
    if days <= 7:
        return 0.92
    if days <= 30:
        return 0.78
    if days <= 180:
        return 0.58
    return 0.42


def infer_category(text: str) -> str:
    scores: dict[str, int] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        scores[category] = sum(1 for keyword in keywords if keyword.lower() in text.lower())

    best_category = max(scores, key=scores.get)
    if scores[best_category] == 0:
        return "公告"
    return best_category


def infer_tags(text: str, category: str) -> list[str]:
    tags: list[str] = [category]
    for keyword in POSITIVE_KEYWORDS:
        if keyword.lower() in text.lower() and keyword not in tags:
            tags.append(keyword)
    return tags[:8]


def calculate_student_score(text: str, source_weight: float) -> float:
    positive_hits = sum(1 for keyword in POSITIVE_KEYWORDS if keyword.lower() in text.lower())
    category_hits = sum(
        1
        for keywords in CATEGORY_KEYWORDS.values()
        for keyword in keywords
        if keyword.lower() in text.lower()
    )
    negative_hits = sum(1 for keyword in NEGATIVE_KEYWORDS if keyword.lower() in text.lower())
    score = (
        0.32
        + positive_hits * 0.08
        + min(category_hits, 5) * 0.045
        + source_weight * 0.18
        - negative_hits * 0.16
    )
    return round(max(0.05, min(1.0, score)), 4)


def is_student_facing_document(document: dict[str, Any]) -> bool:
    text = f"{document['title']} {document.get('content', '')}"
    category = document.get("category", "公告")
    negative_hits = sum(1 for keyword in NEGATIVE_KEYWORDS if keyword.lower() in text.lower())
    threshold_by_category = {
        "公告": 0.68,
        "资料": 0.62,
        "学院": 0.58,
        "讲座": 0.56,
        "生活": 0.54,
        "项目": 0.56,
    }

    if negative_hits > 0 and document["student_score"] < 0.74:
        return False

    threshold = threshold_by_category.get(str(category), MIN_STUDENT_SCORE)
    return document["student_score"] >= threshold


def calculate_importance_score(text: str, category: str, attachments_count: int, source_weight: float) -> float:
    category_bonus = {
        "考试": 0.18,
        "选课": 0.14,
        "竞赛": 0.13,
        "奖助": 0.13,
        "就业": 0.12,
        "生活": 0.1,
        "研究生": 0.1,
    }.get(category, 0.04)
    title_bonus = 0.1 if any(keyword in text for keyword in ("通知", "公示", "安排", "报名", "开放")) else 0
    attachment_bonus = min(0.08, attachments_count * 0.025)
    score = 0.48 + source_weight * 0.18 + category_bonus + title_bonus + attachment_bonus
    return round(max(0.05, min(1.0, score)), 4)


def extract_attachments(soup: BeautifulSoup, page_url: str) -> list[dict[str, str]]:
    attachments: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a"):
        href = anchor.get("href")
        if not href:
            continue
        absolute_url = normalize_url(urljoin(page_url, href))
        extension = extension_from_url(absolute_url)
        if extension not in ATTACHMENT_EXTENSIONS:
            continue
        if absolute_url in seen:
            continue
        seen.add(absolute_url)
        name = clean_text(anchor.get_text(" ", strip=True)) or os.path.basename(urlparse(absolute_url).path)
        attachments.append({"name": name, "url": absolute_url, "type": extension.lstrip(".")})
    return attachments[:8]


def extract_article_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    selectors = [
        ".wp_articlecontent",
        ".article",
        ".article_content",
        ".news_content",
        ".v_news_content",
        "#wp_content_w6_0",
        ".content",
        "main",
        "body",
    ]
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            text = clean_text(node.get_text(" ", strip=True))
            if len(text) >= 20:
                return text[:2400]
    return clean_text(soup.get_text(" ", strip=True))[:2400]


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    return clean_text(BeautifulSoup(value, "html.parser").get_text(" ", strip=True))


def collect_candidates(source: SourceConfig, now: datetime) -> list[dict[str, str | None]]:
    candidates: list[dict[str, str | None]] = []
    seen: set[str] = set()

    for list_url in source.list_urls:
        html = fetch_html(list_url)
        soup = BeautifulSoup(html, "html.parser")

        for anchor in soup.find_all("a"):
            href = anchor.get("href")
            if not href:
                continue

            title = clean_text(anchor.get("title") or anchor.get_text(" ", strip=True))
            if len(title) < 4 or title in NAV_TITLES or title.lower() in NAV_TITLES:
                continue

            absolute_url = normalize_url(urljoin(list_url, href))
            parsed = urlparse(absolute_url)
            if parsed.scheme not in {"http", "https"} or not same_domain(absolute_url, source):
                continue

            extension = extension_from_url(absolute_url)
            if extension in STATIC_EXTENSIONS or extension in ATTACHMENT_EXTENSIONS:
                continue

            if absolute_url in seen:
                continue

            parent_text = clean_text(anchor.parent.get_text(" ", strip=True)) if anchor.parent else title
            if not looks_like_notice_link(title, parent_text, absolute_url, now):
                continue

            seen.add(absolute_url)
            date_text = " ".join([title, parent_text, absolute_url])
            candidates.append({
                "title": title,
                "url": absolute_url,
                "published_at": parse_date(date_text, now),
            })

    return candidates[:MAX_DOCS_PER_SOURCE * 2]


def enrich_candidate(source: SourceConfig, candidate: dict[str, str | None], now: datetime) -> dict[str, Any]:
    title = candidate["title"] or ""
    url = candidate["url"] or source.base_url
    published_at = candidate.get("published_at")
    content = title
    attachments: list[dict[str, str]] = []

    try:
        html = fetch_html(url)
        soup = BeautifulSoup(html, "html.parser")
        title_node = (
            soup.select_one(".arti_title")
            or soup.select_one(".articleTitle")
            or soup.select_one(".news_title")
            or soup.find("h1")
        )
        page_title = clean_text(title_node.get_text(" ", strip=True)) if title_node else ""
        if page_title and len(page_title) >= 4 and page_title not in NAV_TITLES:
            title = page_title
        content = extract_article_text(soup) or title
        attachments = extract_attachments(soup, url)
        published_at = published_at or parse_date(content, now)
    except Exception:
        content = title

    scoring_text = f"{title} {content}"
    category = infer_category(scoring_text)
    student_score = calculate_student_score(scoring_text, source.source_weight)
    freshness_score = calculate_freshness(published_at, now)
    importance_score = calculate_importance_score(scoring_text, category, len(attachments), source.source_weight)
    digest = hashlib.sha256(f"{title}|{url}|{content[:500]}".encode("utf-8")).hexdigest()[:20]

    return {
        "id": f"{source.id}-{digest}",
        "kind": "notice",
        "title": title,
        "url": url,
        "source": source.name,
        "source_domain": urlparse(source.base_url).netloc,
        "category": category,
        "audience": list(source.audience),
        "published_at": published_at,
        "content": content,
        "summary": content[:180],
        "attachments": attachments,
        "student_score": student_score,
        "freshness_score": freshness_score,
        "importance_score": importance_score,
        "source_weight": source.source_weight,
        "tags": infer_tags(scoring_text, category),
        "hash": digest,
    }


def build_job_document(
    source: SourceConfig,
    external_id: str,
    title: str,
    url: str,
    published_at: str | None,
    content: str,
    category: str,
    now: datetime,
) -> dict[str, Any]:
    scoring_text = f"{title} {content}"
    student_score = max(0.74, calculate_student_score(scoring_text, source.source_weight))
    freshness_score = calculate_freshness(published_at, now)
    importance_score = calculate_importance_score(scoring_text, category, 0, source.source_weight)
    digest = hashlib.sha256(f"{external_id}|{title}|{url}".encode("utf-8")).hexdigest()[:20]

    return {
        "id": f"{source.id}-{digest}",
        "kind": "notice",
        "title": title,
        "url": url,
        "source": source.name,
        "source_domain": urlparse(source.base_url).netloc,
        "category": category,
        "audience": list(source.audience),
        "published_at": published_at,
        "content": content or title,
        "summary": (content or title)[:180],
        "attachments": [],
        "student_score": student_score,
        "freshness_score": freshness_score,
        "importance_score": importance_score,
        "source_weight": source.source_weight,
        "tags": infer_tags(scoring_text, category),
        "hash": digest,
    }


def crawl_job_source(source: SourceConfig, now: datetime) -> list[dict[str, Any]]:
    api_base = "https://njupt.91job.org.cn/web/wsjysc/lbxq"
    station_code = "10293"
    documents: list[dict[str, Any]] = []

    meeting_body = {
        "current": 1,
        "xxxs": "",
        "fbsj": "",
        "ssxx": "",
        "keyword": "",
        "size": 10,
        "xxdm": station_code,
    }
    meeting_payload = post_json(f"{api_base}/getZphPageList", meeting_body)
    for item in meeting_payload.get("result", {}).get("records", [])[:10]:
        title = clean_text(str(item.get("zphmc", "")))
        if not title:
            continue
        start_time = clean_text(str(item.get("jbkssj", "")))
        end_time = clean_text(str(item.get("jbjssj", "")))
        location = clean_text(str(item.get("jbcd", "")))
        content = clean_text(" ".join([
            title,
            f"时间：{start_time} 至 {end_time}",
            f"地点：{location}",
            f"联系人：{item.get('lxr', '')}",
            f"电话：{item.get('lxdh', '')}",
        ]))
        external_id = str(item.get("zphid", ""))
        url = f"https://njupt.91job.org.cn/sub-station/recruitmentDetail?zphid={external_id}&xxdm={station_code}"
        documents.append(build_job_document(source, external_id, title, url, start_time[:10] or None, content, "就业", now))

    lecture_body = {
        "current": 1,
        "xxxs": "",
        "fbsj": "",
        "ssxx": "",
        "keyword": "",
        "size": 10,
        "xxdm": station_code,
    }
    lecture_payload = post_json(f"{api_base}/getXjhPageList", lecture_body)
    for item in lecture_payload.get("result", {}).get("records", [])[:8]:
        title = clean_text(str(item.get("xjhmc", "")))
        if not title:
            continue
        date = clean_text(str(item.get("jbrq", "")))
        time = clean_text(str(item.get("kssjd", "")) or str(item.get("jssjd", "")))
        location = clean_text(str(item.get("jbdd", "")))
        content = clean_text(" ".join([
            title,
            f"宣讲时间：{time}",
            f"地点：{location}",
            f"举办学校：{item.get('jbxx', '')}",
            f"联系人：{item.get('zplxr', '')}",
            f"电话：{item.get('lxdh', '')}",
            strip_html(str(item.get("xjhjs", ""))),
        ]))
        external_id = str(item.get("xjhid", ""))
        url = f"https://njupt.91job.org.cn/sub-station/lectureDetail?xjhid={external_id}&xxdm={station_code}"
        documents.append(build_job_document(source, external_id, title, url, date or None, content, "就业", now))

    return documents[:MAX_DOCS_PER_SOURCE]


def read_github_source_configs() -> tuple[GitHubSourceConfig, ...]:
    if not os.path.exists(GITHUB_SOURCE_CONFIG_PATH):
        return ()

    with open(GITHUB_SOURCE_CONFIG_PATH, "r", encoding="utf-8") as config_file:
        payload = json.load(config_file)

    raw_sources = payload.get("sources", []) if isinstance(payload, dict) else []
    sources: list[GitHubSourceConfig] = []
    for item in raw_sources:
        if not isinstance(item, dict):
            continue
        repo = clean_text(str(item.get("repo", "")))
        if "/" not in repo:
            continue
        include = item.get("include") if isinstance(item.get("include"), list) else ["README.md", "*.md", "docs/**/*.md"]
        exclude = item.get("exclude") if isinstance(item.get("exclude"), list) else []
        audience = item.get("audience") if isinstance(item.get("audience"), list) else ["本科生", "研究生"]
        sources.append(
            GitHubSourceConfig(
                repo=repo,
                label=clean_text(str(item.get("label") or repo)),
                category=clean_text(str(item.get("category") or "资料")),
                audience=tuple(str(value) for value in audience),
                include=tuple(str(value) for value in include),
                exclude=tuple(str(value) for value in exclude),
                max_files=max(1, min(int(item.get("max_files", 20)), 50)),
                source_weight=float(item.get("source_weight", 0.72)),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return tuple(sources)


def github_headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "njupt-search-indexer",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def github_api_get(endpoint: str, token: str | None) -> Any:
    response = requests.get(
        f"{GITHUB_API_BASE}{endpoint}",
        headers=github_headers(token),
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def matches_path(path: str, patterns: tuple[str, ...]) -> bool:
    normalized = path.replace("\\", "/")
    for pattern in patterns:
        normalized_pattern = pattern.replace("\\", "/")
        if "/" not in normalized_pattern and "/" in normalized:
            continue
        if fnmatch.fnmatch(normalized, normalized_pattern):
            return True
    return False


def select_github_files(source: GitHubSourceConfig, branch: str, token: str | None) -> list[dict[str, Any]]:
    tree_payload = github_api_get(
        f"/repos/{source.repo}/git/trees/{quote(branch, safe='')}?recursive=1",
        token,
    )
    files: list[dict[str, Any]] = []
    for item in tree_payload.get("tree", []):
        if item.get("type") != "blob":
            continue
        path = str(item.get("path", ""))
        size = int(item.get("size") or 0)
        if not path or size <= 0 or size > GITHUB_FILE_SIZE_LIMIT_BYTES:
            continue
        if source.exclude and matches_path(path, source.exclude):
            continue
        if not matches_path(path, source.include):
            continue
        files.append({"path": path, "size": size})

    files.sort(key=lambda file: (0 if file["path"].lower().endswith("readme.md") else 1, file["path"]))
    return files[: source.max_files]


def fetch_github_file_text(repo: str, branch: str, path: str, token: str | None) -> str:
    quoted_path = quote(path, safe="/")
    quoted_branch = quote(branch, safe="")
    payload = github_api_get(f"/repos/{repo}/contents/{quoted_path}?ref={quoted_branch}", token)
    content = payload.get("content", "")
    if payload.get("encoding") != "base64" or not isinstance(content, str):
        return ""
    return base64.b64decode(content).decode("utf-8", errors="replace")


def extract_markdown_title(path: str, text: str) -> str:
    for line in text.splitlines()[:50]:
        stripped = line.strip()
        if stripped.startswith("#"):
            title = clean_text(stripped.lstrip("#").strip())
            if title:
                return title
    return os.path.basename(path)


def normalize_markdown_text(text: str) -> str:
    without_fences = re.sub(r"```.*?```", " ", text, flags=re.S)
    without_markup = re.sub(r"[#>*_`|[\]()]+", " ", without_fences)
    return clean_text(without_markup)[:4000]


def build_github_document(
    source: GitHubSourceConfig,
    branch: str,
    path: str,
    text: str,
    repo_updated_at: str | None,
) -> dict[str, Any]:
    title = f"{source.label} · {extract_markdown_title(path, text)}"
    content = normalize_markdown_text(text) or title
    category = source.category if source.category in CATEGORY_KEYWORDS else infer_category(f"{title} {content}")
    scoring_text = f"{title} {content}"
    student_score = max(0.62, calculate_student_score(scoring_text, source.source_weight))
    published_at = repo_updated_at[:10] if repo_updated_at else None
    digest = hashlib.sha256(f"github|{source.repo}|{branch}|{path}|{content[:500]}".encode("utf-8")).hexdigest()[:20]

    return {
        "id": f"github-{source.repo.replace('/', '-')}-{digest}",
        "kind": "resource",
        "title": title,
        "url": f"https://github.com/{source.repo}/blob/{quote(branch, safe='')}/{quote(path, safe='/')}",
        "source": source.label,
        "source_domain": "github.com",
        "category": category,
        "audience": list(source.audience),
        "published_at": published_at,
        "content": content,
        "summary": content[:180],
        "attachments": [],
        "student_score": student_score,
        "freshness_score": calculate_freshness(published_at, get_beijing_time()),
        "importance_score": calculate_importance_score(scoring_text, category, 0, source.source_weight),
        "source_weight": source.source_weight,
        "tags": infer_tags(scoring_text, category) + ["GitHub资料"],
        "hash": digest,
    }


def crawl_github_resource_source(source: GitHubSourceConfig, now: datetime) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    print(f"Fetching GitHub resources {source.repo}")
    manifest_entry: dict[str, Any] = {
        "id": f"github:{source.repo}",
        "name": source.label,
        "domain": "github.com",
        "status": "ok",
        "documents": 0,
        "last_fetch_at": now.isoformat(),
    }

    if not source.enabled:
        return [], manifest_entry

    token = os.environ.get(GITHUB_TOKEN_ENV) or os.environ.get("GITHUB_TOKEN")
    try:
        repo_payload = github_api_get(f"/repos/{source.repo}", token)
        branch = repo_payload.get("default_branch") or "main"
        updated_at = repo_payload.get("pushed_at") or repo_payload.get("updated_at")
        selected_files = select_github_files(source, branch, token)

        documents: list[dict[str, Any]] = []
        for file_entry in selected_files:
            path = str(file_entry["path"])
            text = fetch_github_file_text(source.repo, branch, path, token)
            if clean_text(text):
                documents.append(build_github_document(source, branch, path, text, updated_at))

        manifest_entry["candidates"] = len(selected_files)
        manifest_entry["documents"] = len(documents)
        return documents, manifest_entry
    except Exception as exc:
        manifest_entry["status"] = "error"
        manifest_entry["error"] = str(exc)
        return [], manifest_entry


def crawl_source(source: SourceConfig, now: datetime) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    print(f"Fetching {source.name} ({urlparse(source.base_url).netloc})")
    manifest_entry: dict[str, Any] = {
        "id": source.id,
        "name": source.name,
        "domain": urlparse(source.base_url).netloc,
        "status": "ok",
        "documents": 0,
        "last_fetch_at": now.isoformat(),
    }

    try:
        if source.id == "job":
            documents = crawl_job_source(source, now)
            manifest_entry["documents"] = len(documents)
            return documents, manifest_entry

        candidates = collect_candidates(source, now)
        enriched: list[dict[str, Any]] = []
        for candidate in candidates[:DETAIL_FETCH_LIMIT_PER_SOURCE]:
            enriched.append(enrich_candidate(source, candidate, now))

        filtered = [document for document in enriched if is_student_facing_document(document)]
        enriched.sort(
            key=lambda item: (
                item["student_score"],
                item["freshness_score"],
                item["importance_score"],
                item["published_at"] or "",
            ),
            reverse=True,
        )
        filtered.sort(
            key=lambda item: (
                item["student_score"],
                item["freshness_score"],
                item["importance_score"],
                item["published_at"] or "",
            ),
            reverse=True,
        )
        documents = filtered[:MAX_DOCS_PER_SOURCE]
        manifest_entry["candidates"] = len(enriched)
        manifest_entry["filtered_out"] = len(enriched) - len(filtered)
        manifest_entry["documents"] = len(documents)
        return documents, manifest_entry
    except Exception as exc:
        manifest_entry["status"] = "error"
        manifest_entry["error"] = str(exc)
        return [], manifest_entry


def deduplicate_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    seen_urls: set[str] = set()

    for document in documents:
        title_key = re.sub(r"\s+", "", document["title"]).lower()
        if document["url"] in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(document["url"])
        seen_titles.add(title_key)
        deduped.append(document)

    return deduped


def write_json_if_changed(path: str, payload: Any) -> bool:
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as existing:
            if existing.read() == serialized:
                return False
    with open(path, "w", encoding="utf-8", newline="\n") as output:
        output.write(serialized)
        output.write("\n")
    return True


def main() -> None:
    os.makedirs(INDEX_DIR, exist_ok=True)
    now = get_beijing_time()
    all_documents: list[dict[str, Any]] = []
    source_entries: list[dict[str, Any]] = []

    for source in SOURCES:
        documents, manifest_entry = crawl_source(source, now)
        all_documents.extend(documents)
        source_entries.append(manifest_entry)

    for source in read_github_source_configs():
        documents, manifest_entry = crawl_github_resource_source(source, now)
        all_documents.extend(documents)
        source_entries.append(manifest_entry)

    all_documents = deduplicate_documents(all_documents)
    all_documents.sort(
        key=lambda item: (
            item["student_score"],
            item["freshness_score"],
            item["importance_score"],
            item["published_at"] or "",
        ),
        reverse=True,
    )

    manifest = {
        "generated_at": now.isoformat(),
        "total_documents": len(all_documents),
        "strategy": "phase1-public-campus-sources-generic-adapter",
        "sources": source_entries,
    }

    docs_changed = write_json_if_changed(DOCUMENTS_PATH, all_documents)
    manifest_changed = write_json_if_changed(MANIFEST_PATH, manifest)
    print(f"Generated {len(all_documents)} search documents")
    print(f"documents.json changed: {docs_changed}; manifest.json changed: {manifest_changed}")


if __name__ == "__main__":
    main()
