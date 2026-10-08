from __future__ import annotations

import hashlib
import json
import sys
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from ..records.model import ExamDataError, parse_exam_period

JWC_LIST_URL = "https://jwc.njupt.edu.cn/1594/list.htm"
JWC_LIST_PAGE_COUNT = 6
JWC_LIST_URLS = (JWC_LIST_URL,) + tuple(f"https://jwc.njupt.edu.cn/1594/list{page}.htm" for page in range(2, JWC_LIST_PAGE_COUNT + 1))
JWC_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Referer": "https://jwc.njupt.edu.cn/",
}
REQUIRED_EXAM_TITLE_KEYWORDS = ("学年", "学期")
TARGET_EXAM_TITLE_KEYWORDS = ("考试安排表", "期末考试", "课程结束考试")
EXCLUDED_EXAM_TITLE_KEYWORDS = ("阶段性", "补考", "清欠", "分级", "补学", "换证", "重修", "选拔", "竞赛", "发车", "监考")
RETRYABLE_HTTP_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
RETRYABLE_REQUEST_EXCEPTIONS = (
    requests.exceptions.ChunkedEncodingError,
    requests.exceptions.ConnectionError,
    requests.exceptions.SSLError,
    requests.exceptions.Timeout,
)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ExamDataError(f"{path} must contain a JSON object")
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_url_with_retries(
    url: str,
    *,
    session: requests.Session,
    headers: dict[str, str] | None = None,
    timeout: int,
    verify: bool,
    purpose: str,
    attempts: int = 4,
) -> requests.Response:
    if attempts < 1:
        raise ExamDataError("download attempts must be positive")
    retryable_http_status_codes = RETRYABLE_HTTP_STATUS_CODES
    parsed_url = urlsplit(url)
    if parsed_url.scheme == "https" and parsed_url.hostname == "jwc.njupt.edu.cn":
        # This public source intermittently returns 403 to cloud runners.
        retryable_http_status_codes = retryable_http_status_codes | {403}
    for attempt in range(1, attempts + 1):
        try:
            response = session.get(url, headers=headers, timeout=(10, timeout), verify=verify)
            if response.status_code in retryable_http_status_codes and attempt < attempts:
                print(
                    f"[exam_source] {purpose} returned HTTP {response.status_code}; retrying {attempt}/{attempts}",
                    file=sys.stderr,
                    flush=True,
                )
                delay = min(5 * 2 ** (attempt - 1), 20) if response.status_code == 403 else min(2 ** (attempt - 1), 8)
                response.close()
                time.sleep(delay)
                continue
            response.raise_for_status()
            return response
        except RETRYABLE_REQUEST_EXCEPTIONS as exc:
            detail = f"{exc.__class__.__name__}: {exc}"
            if attempt >= attempts:
                raise ExamDataError(
                    f"{purpose} failed after {attempts} attempts: {url}; {detail}"
                ) from exc
            print(
                f"[exam_source] {purpose} failed with {detail}; retrying {attempt}/{attempts}",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(min(5 * 2 ** (attempt - 1), 20))
        except requests.exceptions.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code in retryable_http_status_codes and attempt < attempts:
                print(
                    f"[exam_source] {purpose} returned HTTP {status_code}; retrying {attempt}/{attempts}",
                    file=sys.stderr,
                    flush=True,
                )
                delay = min(5 * 2 ** (attempt - 1), 20) if status_code == 403 else min(2 ** (attempt - 1), 8)
                if exc.response is not None:
                    exc.response.close()
                time.sleep(delay)
                continue
            raise ExamDataError(f"{purpose} returned HTTP {status_code}: {url}") from exc
    raise ExamDataError(f"{purpose} failed without returning a response: {url}")


def is_valid_exam_title(title: str) -> bool:
    return (
        all(keyword in title for keyword in REQUIRED_EXAM_TITLE_KEYWORDS)
        and any(keyword in title for keyword in TARGET_EXAM_TITLE_KEYWORDS)
        and not any(keyword in title for keyword in EXCLUDED_EXAM_TITLE_KEYWORDS)
    )


def is_student_exam_file(name: str) -> bool:
    return "学生" in name


def is_teacher_exam_file(name: str) -> bool:
    return any(keyword in name for keyword in ("监考", "教师", "巡考", "教务员"))


def discover_latest_exam_notice(*, tls_verify: bool, session: requests.Session) -> tuple[str, str]:
    seen_urls: set[str] = set()
    response = get_url_with_retries(
        JWC_LIST_URL,
        session=session,
        headers=JWC_HEADERS,
        timeout=30,
        verify=tls_verify,
        purpose="discover latest exam notice list",
    )
    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")
    container = soup.select_one("div.col_news_con")
    if container is None:
        raise ExamDataError(f"exam notice list container div.col_news_con was not found in {JWC_LIST_URL}")
    for list_url in JWC_LIST_URLS:
        if list_url != JWC_LIST_URL:
            response = get_url_with_retries(
                list_url,
                session=session,
                headers=JWC_HEADERS,
                timeout=30,
                verify=tls_verify,
                purpose=f"discover latest exam notice list {list_url}",
            )
            response.encoding = "utf-8"
            soup = BeautifulSoup(response.text, "html.parser")
            container = soup.select_one("div.col_news_con")
            if container is None:
                raise ExamDataError(f"exam notice list container div.col_news_con was not found in {list_url}")
        for item in container.select("li.news"):
            title_span = item.select_one("span.news_title")
            link = title_span.find("a") if title_span else item.find("a")
            if link is None:
                continue
            title = str(link.get("title") or link.get_text(strip=True)).strip()
            href = str(link.get("href") or "").strip()
            notice_url = urljoin(list_url, href)
            if not href or notice_url in seen_urls:
                continue
            seen_urls.add(notice_url)
            if is_valid_exam_title(title):
                return notice_url, title
    raise ExamDataError(f"no valid current exam schedule notice found in {len(JWC_LIST_URLS)} notice pages")


def discover_exam_files(
    source_url: str, *, tls_verify: bool, session: requests.Session
) -> list[dict[str, str]]:
    response = get_url_with_retries(
        source_url,
        session=session,
        headers=JWC_HEADERS,
        timeout=30,
        verify=tls_verify,
        purpose="discover exam files",
    )
    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")
    candidates: list[dict[str, str]] = []
    for link in soup.find_all("a"):
        href = str(link.get("href") or "").strip()
        if not href.lower().endswith((".xls", ".xlsx")):
            continue
        name = str(link.get_text(strip=True) or Path(href).name).strip()
        if not name.lower().endswith((".xls", ".xlsx")):
            name = Path(href).name
        candidates.append({"name": name, "url": urljoin(source_url, href)})
    if not candidates:
        raise ExamDataError(f"no Excel attachments found in {source_url}")
    student_files = [item for item in candidates if is_student_exam_file(item["name"])]
    selected = student_files or [item for item in candidates if not is_teacher_exam_file(item["name"])]
    if not selected:
        raise ExamDataError(f"no student/non-teacher Excel attachments found in {source_url}")
    return selected


EXAM_SOURCE_FORMAT = "njupt-exam-source"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def source_descriptor_id(descriptor: dict[str, Any]) -> str:
    identity = {key: value for key, value in descriptor.items() if key != "source_id"}
    return hashlib.sha256(_canonical_json(identity)).hexdigest()


def discover_exam_source(
    output_path: Path, *, tls_verify: bool, cache_root: Path | None = None
) -> None:
    if output_path.exists():
        raise ExamDataError(f"Refusing to overwrite exam source descriptor: {output_path}")
    files = []
    downloaded_content: list[tuple[str, bytes]] = []
    with requests.Session() as session:
        source_url, source_title = discover_latest_exam_notice(
            tls_verify=tls_verify, session=session
        )
        for item in discover_exam_files(source_url, tls_verify=tls_verify, session=session):
            response = get_url_with_retries(
                item["url"],
                session=session,
                headers=JWC_HEADERS,
                timeout=60,
                verify=tls_verify,
                purpose=f"download exam source candidate {item['name']}",
            )
            content = response.content
            if cache_root is not None:
                downloaded_content.append((item["name"], content))
            files.append(
                {
                    "name": item["name"],
                    "url": item["url"],
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "etag": response.headers.get("etag"),
                    "last_modified": response.headers.get("last-modified"),
                }
            )
    updated_values = []
    for item in files:
        raw_value = item.get("last_modified")
        if not raw_value:
            raise ExamDataError(
                f"exam source file has no Last-Modified timestamp: {item['name']}"
            )
        try:
            updated_values.append(parsedate_to_datetime(raw_value))
        except (TypeError, ValueError) as exc:
            raise ExamDataError(
                f"exam source file has invalid Last-Modified timestamp: {item['name']}"
            ) from exc
    descriptor = {
        "format": EXAM_SOURCE_FORMAT,
        "source_url": source_url,
        "source_title": source_title,
        "source_updated_at": max(updated_values).isoformat(),
        "tls_verify": tls_verify,
        "files": files,
    }
    descriptor["source_id"] = source_descriptor_id(descriptor)
    if cache_root is not None:
        cache_dir = cache_root / descriptor["source_id"]
        cache_dir.mkdir(parents=True, exist_ok=True)
        for name, content in downloaded_content:
            cache_target = cache_dir / name
            tmp_target = cache_target.with_suffix(cache_target.suffix + ".tmp")
            tmp_target.write_bytes(content)
            tmp_target.replace(cache_target)
    write_json(output_path, descriptor)


def materialize_exam_files(*, source_path: Path, exam_dir: Path, cache_root: Path) -> None:
    source = read_json(source_path)
    if source.get("format") != EXAM_SOURCE_FORMAT:
        raise ExamDataError(f"{source_path} is not an {EXAM_SOURCE_FORMAT} descriptor")
    source_id = str(source.get("source_id") or "")
    if source_id != source_descriptor_id(source):
        raise ExamDataError(f"{source_path} source_id does not match its content")
    source_updated_at = str(source.get("source_updated_at") or "").strip()
    if not source_updated_at:
        raise ExamDataError(f"{source_path} missing source_updated_at")
    files = source.get("files")
    if not isinstance(files, list) or not files:
        raise ExamDataError(f"{source_path} files must be a non-empty list")

    exam_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = cache_root / source_id
    cache_dir.mkdir(parents=True, exist_ok=True)
    downloaded_names: list[str] = []
    verify_tls = str(source.get("tls_verify", True)).strip().lower() not in {"0", "false", "no"}
    with requests.Session() as session:
        for item in files:
            if not isinstance(item, dict):
                raise ExamDataError(f"{source_path} files entries must be objects")
            name = str(item.get("name") or "").strip()
            url = str(item.get("url") or "").strip()
            expected_sha256 = str(item.get("sha256") or "").strip().lower()
            if not name or not url or not expected_sha256:
                raise ExamDataError(f"{source_path} file entry missing name/url/sha256")
            target = exam_dir / name
            cache_target = cache_dir / name
            if target.exists() and sha256_file(target) == expected_sha256:
                pass
            elif cache_target.exists() and sha256_file(cache_target) == expected_sha256:
                target.write_bytes(cache_target.read_bytes())
            else:
                response = get_url_with_retries(
                    url,
                    session=session,
                    headers=JWC_HEADERS,
                    timeout=60,
                    verify=verify_tls,
                    purpose=f"download exam file {name}",
                )
                tmp_target = cache_target.with_suffix(cache_target.suffix + ".tmp")
                tmp_target.write_bytes(response.content)
                actual_sha256 = sha256_file(tmp_target)
                if actual_sha256 != expected_sha256:
                    tmp_target.unlink(missing_ok=True)
                    raise ExamDataError(
                        f"exam source hash mismatch for {name}: expected {expected_sha256}, got {actual_sha256}"
                    )
                tmp_target.replace(cache_target)
                target.write_bytes(cache_target.read_bytes())
            downloaded_names.append(name)

    expected_names = set(downloaded_names)
    actual_names = {path.name for path in exam_dir.glob("*.xls*")}
    if actual_names != expected_names:
        raise ExamDataError(
            f"materialized exam file set mismatch: expected {sorted(expected_names)}, "
            f"got {sorted(actual_names)}"
        )

    period = parse_exam_period(source.get("source_title"))
    write_json(
        exam_dir / "source_metadata.json",
        {
            "source_url": source.get("source_url"),
            "source_title": source.get("source_title"),
            "exam_period_id": period.exam_period_id,
            "academic_year": period.academic_year,
            "term_number": period.term_number,
            "term_label": period.term_label,
            "downloaded_files": downloaded_names,
            "source_updated_at": source_updated_at,
            "source_id": source_id,
        },
    )

