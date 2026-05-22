import base64
import fnmatch
import hashlib
import json
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any
from urllib.parse import quote, urljoin, urlparse, urlunparse

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from indexer_config import (
    BASE_DIR, PUBLIC_DIR, INDEX_DIR, DOCUMENTS_PATH, MANIFEST_PATH, GITHUB_SOURCE_CONFIG_PATH,
    BEIJING_TZ, HEADERS, MAX_DOCS_PER_SOURCE, DETAIL_FETCH_LIMIT_PER_SOURCE, REQUEST_TIMEOUT,
    MIN_STUDENT_SCORE, GITHUB_TOKEN_ENV, GITHUB_API_BASE, GITHUB_FILE_SIZE_LIMIT_BYTES,
    NEGATIVE_KEYWORDS, SourceConfig, GitHubSourceConfig, SOURCES,
    JOB_API_BASE, JOB_STATION_CODE, CATEGORY_KEYWORDS,
    NAV_TITLES, STATIC_EXTENSIONS, ATTACHMENT_EXTENSIONS, POSITIVE_KEYWORDS
)
from llm_scorer import analyze_document_with_llm

_DOC_CACHE: dict[str, dict[str, Any]] = {}

def load_document_cache() -> None:
    global _DOC_CACHE
    if os.path.exists(DOCUMENTS_PATH):
        try:
            with open(DOCUMENTS_PATH, "r", encoding="utf-8") as f:
                docs = json.load(f)
                for doc in docs:
                    if "hash" in doc:
                        _DOC_CACHE[doc["hash"]] = doc
        except Exception:
            pass



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


def is_expired(published_at: str | None, now: datetime) -> bool:
    if not published_at:
        return False
    try:
        pub_date = datetime.fromisoformat(published_at).date()
        return (now.date() - pub_date).days > 365
    except Exception:
        return False



from indexer_scoring import (
    calculate_freshness, infer_category, infer_tags, calculate_student_score,
    is_student_facing_document, calculate_importance_score
)


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
            published_at = parse_date(date_text, now)
            
            if is_expired(published_at, now):
                continue

            candidates.append({
                "title": title,
                "url": absolute_url,
                "published_at": published_at,
            })

    return candidates[:MAX_DOCS_PER_SOURCE * 2]


def enrich_candidate(source: SourceConfig, candidate: dict[str, str | None], now: datetime) -> dict[str, Any] | None:
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

    if is_expired(published_at, now):
        return None

    digest = hashlib.sha256(f"{title}|{url}|{content[:500]}".encode("utf-8")).hexdigest()[:20]

    cached = _DOC_CACHE.get(digest)
    if cached:
        return {**cached, "freshness_score": calculate_freshness(cached.get("published_at"), now)}

    scoring_text = f"{title} {content}"
    llm_result = analyze_document_with_llm(title, content, urlparse(source.base_url).netloc)

    if llm_result:
        category = llm_result.get("category", "公告")
        student_score = 1.0 if llm_result.get("is_student_facing", True) else 0.0
        importance_score = float(llm_result.get("importance_score", 0.5))
        tags = llm_result.get("tags", [])
        summary = llm_result.get("student_summary", content[:180])
        sub_category = llm_result.get("sub_category")
        deadline = llm_result.get("deadline")
        action_required = llm_result.get("action_required", False)
        action_type = llm_result.get("action_type")
        action_summary = llm_result.get("action_summary")
        sensitive = llm_result.get("sensitive", False)
    else:
        category = infer_category(scoring_text)
        student_score = calculate_student_score(scoring_text, source.source_weight)
        importance_score = calculate_importance_score(scoring_text, category, len(attachments), source.source_weight)
        tags = infer_tags(scoring_text, category)
        summary = content[:180]
        sub_category = None
        deadline = None
        action_required = False
        action_type = None
        action_summary = None
        sensitive = False

    freshness_score = calculate_freshness(published_at, now)

    return {
        "id": f"{source.id}-{digest}",
        "kind": "notice",
        "title": title,
        "url": url,
        "source": source.name,
        "source_domain": urlparse(source.base_url).netloc,
        "category": category,
        "sub_category": sub_category,
        "deadline": deadline,
        "action_required": action_required,
        "action_type": action_type,
        "action_summary": action_summary,
        "sensitive": sensitive,
        "audience": list(source.audience),
        "published_at": published_at,
        "content": content,
        "summary": summary,
        "attachments": attachments,
        "student_score": student_score,
        "freshness_score": freshness_score,
        "importance_score": importance_score,
        "source_weight": source.source_weight,
        "tags": tags,
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
) -> dict[str, Any] | None:
    if is_expired(published_at, now):
        return None
    digest = hashlib.sha256(f"{external_id}|{title}|{url}".encode("utf-8")).hexdigest()[:20]

    cached = _DOC_CACHE.get(digest)
    if cached:
        return {**cached, "freshness_score": calculate_freshness(cached.get("published_at"), now)}

    scoring_text = f"{title} {content}"
    llm_result = analyze_document_with_llm(title, content, urlparse(source.base_url).netloc)

    if llm_result:
        cat = llm_result.get("category", category)
        student_score = 1.0 if llm_result.get("is_student_facing", True) else 0.0
        importance_score = float(llm_result.get("importance_score", 0.5))
        tags = llm_result.get("tags", [])
        summary = llm_result.get("student_summary", (content or title)[:180])
        sub_category = llm_result.get("sub_category")
        deadline = llm_result.get("deadline")
        action_required = llm_result.get("action_required", False)
        action_type = llm_result.get("action_type")
        action_summary = llm_result.get("action_summary")
        sensitive = llm_result.get("sensitive", False)
    else:
        cat = category
        student_score = max(0.74, calculate_student_score(scoring_text, source.source_weight))
        importance_score = calculate_importance_score(scoring_text, cat, 0, source.source_weight)
        tags = infer_tags(scoring_text, cat)
        summary = (content or title)[:180]
        sub_category = None
        deadline = None
        action_required = False
        action_type = None
        action_summary = None
        sensitive = False

    freshness_score = calculate_freshness(published_at, now)

    return {
        "id": f"{source.id}-{digest}",
        "kind": "notice",
        "title": title,
        "url": url,
        "source": source.name,
        "source_domain": urlparse(source.base_url).netloc,
        "category": cat,
        "sub_category": sub_category,
        "deadline": deadline,
        "action_required": action_required,
        "action_type": action_type,
        "action_summary": action_summary,
        "sensitive": sensitive,
        "audience": list(source.audience),
        "published_at": published_at,
        "content": content or title,
        "summary": summary,
        "attachments": [],
        "student_score": student_score,
        "freshness_score": freshness_score,
        "importance_score": importance_score,
        "source_weight": source.source_weight,
        "tags": tags,
        "hash": digest,
    }


def crawl_job_source(source: SourceConfig, now: datetime) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []

    meeting_body = {
        "current": 1,
        "xxxs": "",
        "fbsj": "",
        "ssxx": "",
        "keyword": "",
        "size": 10,
        "xxdm": JOB_STATION_CODE,
    }
    meeting_payload = post_json(f"{JOB_API_BASE}/getZphPageList", meeting_body)
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
        url = f"https://njupt.91job.org.cn/sub-station/recruitmentDetail?zphid={external_id}&xxdm={JOB_STATION_CODE}"
        doc = build_job_document(source, external_id, title, url, start_time[:10] or None, content, "就业", now)
        if doc:
            documents.append(doc)

    lecture_body = {
        "current": 1,
        "xxxs": "",
        "fbsj": "",
        "ssxx": "",
        "keyword": "",
        "size": 10,
        "xxdm": JOB_STATION_CODE,
    }
    lecture_payload = post_json(f"{JOB_API_BASE}/getXjhPageList", lecture_body)
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
        url = f"https://njupt.91job.org.cn/sub-station/lectureDetail?xjhid={external_id}&xxdm={JOB_STATION_CODE}"
        doc = build_job_document(source, external_id, title, url, date or None, content, "就业", now)
        if doc:
            documents.append(doc)

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
) -> dict[str, Any] | None:
    title = f"{source.label} · {extract_markdown_title(path, text)}"
    content = normalize_markdown_text(text) or title
    digest = hashlib.sha256(f"github|{source.repo}|{branch}|{path}|{content[:500]}".encode("utf-8")).hexdigest()[:20]
    published_at = repo_updated_at[:10] if repo_updated_at else None

    if is_expired(published_at, get_beijing_time()):
        return None

    cached = _DOC_CACHE.get(digest)
    if cached:
        return {**cached, "freshness_score": calculate_freshness(published_at, get_beijing_time())}

    scoring_text = f"{title} {content}"
    llm_result = analyze_document_with_llm(title, content, "github.com")

    if llm_result:
        category = llm_result.get("category", source.category)
        student_score = 1.0 if llm_result.get("is_student_facing", True) else 0.0
        importance_score = float(llm_result.get("importance_score", 0.5))
        tags = llm_result.get("tags", []) + ["GitHub资料"]
        summary = llm_result.get("student_summary", content[:180])
        sub_category = llm_result.get("sub_category")
        deadline = llm_result.get("deadline")
        action_required = llm_result.get("action_required", False)
        action_type = llm_result.get("action_type")
        action_summary = llm_result.get("action_summary")
        sensitive = llm_result.get("sensitive", False)
    else:
        category = source.category if source.category in CATEGORY_KEYWORDS else infer_category(scoring_text)
        student_score = max(0.62, calculate_student_score(scoring_text, source.source_weight))
        importance_score = calculate_importance_score(scoring_text, category, 0, source.source_weight)
        tags = infer_tags(scoring_text, category) + ["GitHub资料"]
        summary = content[:180]
        sub_category = None
        deadline = None
        action_required = False
        action_type = None
        action_summary = None
        sensitive = False

    return {
        "id": f"github-{source.repo.replace('/', '-')}-{digest}",
        "kind": "resource",
        "title": title,
        "url": f"https://github.com/{source.repo}/blob/{quote(branch, safe='')}/{quote(path, safe='/')}",
        "source": source.label,
        "source_domain": "github.com",
        "category": category,
        "sub_category": sub_category,
        "deadline": deadline,
        "action_required": action_required,
        "action_type": action_type,
        "action_summary": action_summary,
        "sensitive": sensitive,
        "audience": list(source.audience),
        "published_at": published_at,
        "content": content,
        "summary": summary,
        "attachments": [],
        "student_score": student_score,
        "freshness_score": calculate_freshness(published_at, get_beijing_time()),
        "importance_score": importance_score,
        "source_weight": source.source_weight,
        "tags": tags,
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
                doc = build_github_document(source, branch, path, text, updated_at)
                if doc:
                    documents.append(doc)

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
            doc = enrich_candidate(source, candidate, now)
            if doc:
                enriched.append(doc)

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
    load_document_cache()
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
