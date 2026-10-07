from __future__ import annotations

from pathlib import Path

import pytest
import requests

from academics.exam.source import discovery as source


def make_response(
    status_code: int,
    body: bytes = b"ok",
    *,
    url: str = "https://example.invalid/file.xlsx",
) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response._content = body
    response._content_consumed = True
    response.url = url
    return response


def make_exam_list(items: list[tuple[str, str]]) -> bytes:
    news_items = "\n".join(
        f'<li class="news"><span class="news_title"><a href="{href}" title="{title}">{title}</a></span></li>'
        for title, href in items
    )
    return f'<div class="col_news_con"><ul>{news_items}</ul></div>'.encode("utf-8")


def test_get_url_with_retries_recovers_from_transient_ssl(monkeypatch) -> None:
    calls = []

    def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) == 1:
            raise requests.exceptions.SSLError("transient eof")
        return make_response(200, b"stable")

    monkeypatch.setattr(source.requests, "get", fake_get)
    monkeypatch.setattr(source.time, "sleep", lambda _seconds: None)

    response = source.get_url_with_retries(
        "https://example.invalid/file.xlsx",
        timeout=60,
        verify=True,
        purpose="test download",
    )

    assert response.content == b"stable"
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("url", "status_code"),
    [
        ("https://example.invalid/file.xlsx", 403),
        ("http://jwc.njupt.edu.cn/1594/list.htm", 403),
        (source.JWC_LIST_URL, 401),
        (source.JWC_LIST_URL, 404),
    ],
)
def test_get_url_with_retries_rejects_non_retryable_http(monkeypatch, url, status_code) -> None:
    calls = []

    def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        return make_response(status_code, url=url)

    monkeypatch.setattr(source.requests, "get", fake_get)
    monkeypatch.setattr(source.time, "sleep", lambda _seconds: None)

    with pytest.raises(source.ExamDataError, match=f"HTTP {status_code}"):
        source.get_url_with_retries(
            url,
            timeout=60,
            verify=True,
            purpose="test download",
        )
    assert len(calls) == 1


@pytest.mark.parametrize(
    "url",
    [source.JWC_LIST_URL, "https://jwc.njupt.edu.cn/_upload/article/files/exam.xlsx"],
)
def test_get_url_with_retries_recovers_from_public_source_forbidden(monkeypatch, url) -> None:
    calls = []
    sleeps = []

    def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        return make_response(403 if len(calls) == 1 else 200, b"stable", url=url)

    monkeypatch.setattr(source.requests, "get", fake_get)
    monkeypatch.setattr(source.time, "sleep", sleeps.append)

    response = source.get_url_with_retries(
        url, timeout=60, verify=True, purpose="test public source"
    )

    assert response.content == b"stable"
    assert len(calls) == 2
    assert sleeps == [5]
    assert all(kwargs["verify"] is True for _args, kwargs in calls)


def test_get_url_with_retries_preserves_persistent_public_source_forbidden(monkeypatch) -> None:
    calls = []
    sleeps = []

    def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        return make_response(403, url=source.JWC_LIST_URL)

    monkeypatch.setattr(source.requests, "get", fake_get)
    monkeypatch.setattr(source.time, "sleep", sleeps.append)

    with pytest.raises(source.ExamDataError, match="HTTP 403") as caught:
        source.get_url_with_retries(
            source.JWC_LIST_URL, timeout=30, verify=True, purpose="test public source"
        )

    assert len(calls) == 4
    assert sleeps == [5, 10, 20]
    assert isinstance(caught.value.__cause__, requests.exceptions.HTTPError)
    assert caught.value.__cause__.response.status_code == 403


def test_discover_latest_exam_notice_scans_paginated_notice_pages(monkeypatch) -> None:
    page_one = "https://jwc.njupt.edu.cn/1594/list.htm"
    page_two = "https://jwc.njupt.edu.cn/1594/list2.htm"
    bodies = {
        page_one: make_exam_list(
            [
                ("【教务管理办公室】2026-2027学年第一学期学生选课通知", "/2026/0610/c1594a303951/page.htm"),
            ]
        ),
        page_two: make_exam_list(
            [
                ("【教务管理办公室】2025-2026学年第二学期考试安排表 2026-06-10", "/2026/0610/c1594a303974/page.htm"),
            ]
        ),
    }
    calls = []

    def fake_get_url(url, **_kwargs):
        calls.append(url)
        return make_response(200, bodies[url])

    monkeypatch.setattr(source, "JWC_LIST_URLS", (page_one, page_two))
    monkeypatch.setattr(source, "get_url_with_retries", fake_get_url)

    notice_url, title = source.discover_latest_exam_notice(tls_verify=True)

    assert calls == [page_one, page_two]
    assert notice_url == "https://jwc.njupt.edu.cn/2026/0610/c1594a303974/page.htm"
    assert title == "【教务管理办公室】2025-2026学年第二学期考试安排表 2026-06-10"


@pytest.fixture
def downloadable_exam_source(monkeypatch):
    notice_url = "https://jwc.njupt.edu.cn/2026/0610/c1594a303974/page.htm"
    attachment_url = "https://jwc.njupt.edu.cn/_upload/article/files/exam.xlsx"
    attachment_name = "学生考试安排.xlsx"
    attachment_body = b"current exam attachment"
    bodies = {
        source.JWC_LIST_URL: make_exam_list(
            [("2025-2026学年第二学期考试安排表", notice_url)]
        ),
        notice_url: f'<a href="{attachment_url}">{attachment_name}</a>'.encode("utf-8"),
        attachment_url: attachment_body,
    }
    calls = []

    def fake_get(url, **_kwargs):
        calls.append(url)
        response = make_response(200, bodies[url], url=url)
        if url == attachment_url:
            response.headers["Last-Modified"] = "Wed, 10 Jun 2026 08:00:00 GMT"
            response.headers["ETag"] = '"current-exam"'
        return response

    monkeypatch.setattr(source.requests, "get", fake_get)
    return calls, attachment_name, attachment_body


def test_discover_caches_downloads_for_materialization(
    tmp_path: Path, downloadable_exam_source
) -> None:
    calls, name, content = downloadable_exam_source
    source_path = tmp_path / "exam-source.json"
    cache_root = tmp_path / "cache"
    exam_dir = tmp_path / "materialized"

    source.discover_exam_source(source_path, tls_verify=True, cache_root=cache_root)
    descriptor = source.read_json(source_path)
    discovery_calls = list(calls)
    source.materialize_exam_files(
        source_path=source_path, exam_dir=exam_dir, cache_root=cache_root
    )

    assert len(discovery_calls) == 3
    assert calls == discovery_calls
    assert (cache_root / descriptor["source_id"] / name).read_bytes() == content
    assert (exam_dir / name).read_bytes() == content
    assert source.sha256_file(exam_dir / name) == descriptor["files"][0]["sha256"]
    assert source.read_json(exam_dir / "source_metadata.json")["source_id"] == descriptor["source_id"]


@pytest.mark.parametrize("download_matches", [True, False])
def test_materialize_does_not_trust_corrupt_cached_attachment(
    tmp_path: Path, monkeypatch, downloadable_exam_source, download_matches: bool
) -> None:
    calls, name, content = downloadable_exam_source
    source_path = tmp_path / "exam-source.json"
    cache_root = tmp_path / "cache"
    exam_dir = tmp_path / "materialized"
    source.discover_exam_source(source_path, tls_verify=True, cache_root=cache_root)
    descriptor = source.read_json(source_path)
    cache_target = cache_root / descriptor["source_id"] / name
    cache_target.write_bytes(b"corrupt cache")
    calls.clear()

    def fake_get(url, **_kwargs):
        calls.append(url)
        return make_response(200, content if download_matches else b"changed source", url=url)

    monkeypatch.setattr(source.requests, "get", fake_get)
    if download_matches:
        source.materialize_exam_files(
            source_path=source_path, exam_dir=exam_dir, cache_root=cache_root
        )
        assert (exam_dir / name).read_bytes() == content
        assert cache_target.read_bytes() == content
    else:
        with pytest.raises(source.ExamDataError, match="exam source hash mismatch"):
            source.materialize_exam_files(
                source_path=source_path, exam_dir=exam_dir, cache_root=cache_root
            )
        assert not (exam_dir / name).exists()
        assert not (exam_dir / "source_metadata.json").exists()
        assert not cache_target.with_suffix(cache_target.suffix + ".tmp").exists()

    assert calls == [descriptor["files"][0]["url"]]
