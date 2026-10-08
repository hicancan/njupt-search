from __future__ import annotations

from pathlib import Path

import pytest
import requests

from academics.exam.source import discovery as source


@pytest.fixture
def http_session():
    with requests.Session() as session:
        yield session


@pytest.fixture
def closed_sessions(monkeypatch):
    sessions = []
    original_close = requests.Session.close

    def close(session):
        sessions.append(session)
        original_close(session)

    monkeypatch.setattr(requests.Session, "close", close)
    return sessions


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


@pytest.mark.parametrize(
    "exception_type",
    [requests.exceptions.SSLError, requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout],
)
def test_get_url_with_retries_recovers_from_transient_network_error(
    monkeypatch, http_session, capsys, exception_type
) -> None:
    calls = []
    sleeps = []

    def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) == 1:
            raise exception_type("transient network error detail")
        return make_response(200, b"stable")

    monkeypatch.setattr(source.requests.Session, "get", fake_get)
    monkeypatch.setattr(source.time, "sleep", sleeps.append)

    response = source.get_url_with_retries(
        "https://example.invalid/file.xlsx",
        session=http_session,
        timeout=60,
        verify=True,
        purpose="test download",
    )

    assert response.content == b"stable"
    assert len(calls) == 2
    assert sleeps == [5]
    assert all(args[0] is http_session for args, _kwargs in calls)
    assert all(kwargs["timeout"] == (10, 60) for _args, kwargs in calls)
    assert "transient network error detail" in capsys.readouterr().err


def test_get_url_with_retries_preserves_persistent_network_error(
    monkeypatch, http_session, capsys
) -> None:
    calls = []
    sleeps = []
    error = requests.exceptions.ConnectionError("connect failed: network is unreachable")

    def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        raise error

    monkeypatch.setattr(source.requests.Session, "get", fake_get)
    monkeypatch.setattr(source.time, "sleep", sleeps.append)

    with pytest.raises(source.ExamDataError, match="failed after 4 attempts.*network is unreachable") as caught:
        source.get_url_with_retries(
            source.JWC_LIST_URL,
            session=http_session,
            timeout=30,
            verify=True,
            purpose="test public source",
        )

    assert len(calls) == 4
    assert sleeps == [5, 10, 20]
    assert caught.value.__cause__ is error
    assert all(args[0] is http_session for args, _kwargs in calls)
    assert all(kwargs["timeout"] == (10, 30) for _args, kwargs in calls)
    assert "ConnectionError: connect failed: network is unreachable" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("url", "status_code"),
    [
        ("https://example.invalid/file.xlsx", 403),
        ("http://jwc.njupt.edu.cn/1594/list.htm", 403),
        (source.JWC_LIST_URL, 401),
        (source.JWC_LIST_URL, 404),
    ],
)
def test_get_url_with_retries_rejects_non_retryable_http(
    monkeypatch, http_session, url, status_code
) -> None:
    calls = []

    def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        return make_response(status_code, url=url)

    monkeypatch.setattr(source.requests.Session, "get", fake_get)
    monkeypatch.setattr(source.time, "sleep", lambda _seconds: None)

    with pytest.raises(source.ExamDataError, match=f"HTTP {status_code}"):
        source.get_url_with_retries(
            url,
            session=http_session,
            timeout=60,
            verify=True,
            purpose="test download",
        )
    assert len(calls) == 1


@pytest.mark.parametrize(
    "url",
    [source.JWC_LIST_URL, "https://jwc.njupt.edu.cn/_upload/article/files/exam.xlsx"],
)
def test_get_url_with_retries_recovers_from_public_source_forbidden(
    monkeypatch, http_session, url
) -> None:
    calls = []
    sleeps = []

    def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        return make_response(403 if len(calls) == 1 else 200, b"stable", url=url)

    monkeypatch.setattr(source.requests.Session, "get", fake_get)
    monkeypatch.setattr(source.time, "sleep", sleeps.append)

    response = source.get_url_with_retries(
        url, session=http_session, timeout=60, verify=True, purpose="test public source"
    )

    assert response.content == b"stable"
    assert len(calls) == 2
    assert sleeps == [5]
    assert all(kwargs["verify"] is True for _args, kwargs in calls)


def test_get_url_with_retries_preserves_persistent_public_source_forbidden(
    monkeypatch, http_session
) -> None:
    calls = []
    sleeps = []

    def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        return make_response(403, url=source.JWC_LIST_URL)

    monkeypatch.setattr(source.requests.Session, "get", fake_get)
    monkeypatch.setattr(source.time, "sleep", sleeps.append)

    with pytest.raises(source.ExamDataError, match="HTTP 403") as caught:
        source.get_url_with_retries(
            source.JWC_LIST_URL,
            session=http_session,
            timeout=30,
            verify=True,
            purpose="test public source",
        )

    assert len(calls) == 4
    assert sleeps == [5, 10, 20]
    assert isinstance(caught.value.__cause__, requests.exceptions.HTTPError)
    assert caught.value.__cause__.response.status_code == 403


def test_discover_latest_exam_notice_scans_paginated_notice_pages(monkeypatch, http_session) -> None:
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

    def fake_get_url(url, **kwargs):
        assert kwargs["session"] is http_session
        calls.append(url)
        return make_response(200, bodies[url])

    monkeypatch.setattr(source, "JWC_LIST_URLS", (page_one, page_two))
    monkeypatch.setattr(source, "get_url_with_retries", fake_get_url)

    notice_url, title = source.discover_latest_exam_notice(tls_verify=True, session=http_session)

    assert calls == [page_one, page_two]
    assert notice_url == "https://jwc.njupt.edu.cn/2026/0610/c1594a303974/page.htm"
    assert title == "【教务管理办公室】2025-2026学年第二学期考试安排表 2026-06-10"


@pytest.fixture
def downloadable_exam_source(monkeypatch, closed_sessions):
    notice_url = "https://jwc.njupt.edu.cn/2026/0610/c1594a303974/page.htm"
    attachment_url = "https://jwc.njupt.edu.cn/_upload/article/files/exam.xlsx"
    attachment_name = "学生考试安排.xlsx"
    attachment_body = b"current exam attachment"
    bodies = {
        source.JWC_LIST_URL: make_exam_list(
            [("2026-2027学年第一学期学生选课通知", "/2026/0610/other/page.htm")]
        ),
        source.JWC_LIST_URLS[1]: make_exam_list(
            [("2025-2026学年第二学期考试安排表", notice_url)]
        ),
        notice_url: f'<a href="{attachment_url}">{attachment_name}</a>'.encode("utf-8"),
        attachment_url: attachment_body,
    }
    calls = []
    request_sessions = []

    def fake_get(session, url, **_kwargs):
        calls.append(url)
        request_sessions.append(session)
        response = make_response(200, bodies[url], url=url)
        if url == attachment_url:
            response.headers["Last-Modified"] = "Wed, 10 Jun 2026 08:00:00 GMT"
            response.headers["ETag"] = '"current-exam"'
        return response

    monkeypatch.setattr(source.requests.Session, "get", fake_get)
    return calls, attachment_name, attachment_body, request_sessions


def test_discover_caches_downloads_for_materialization(
    tmp_path: Path, downloadable_exam_source, closed_sessions
) -> None:
    calls, name, content, request_sessions = downloadable_exam_source
    source_path = tmp_path / "exam-source.json"
    cache_root = tmp_path / "cache"
    exam_dir = tmp_path / "materialized"

    source.discover_exam_source(source_path, tls_verify=True, cache_root=cache_root)
    descriptor = source.read_json(source_path)
    discovery_calls = list(calls)
    source.materialize_exam_files(
        source_path=source_path, exam_dir=exam_dir, cache_root=cache_root
    )

    assert len(discovery_calls) == 4
    assert calls == discovery_calls
    assert all(session is request_sessions[0] for session in request_sessions)
    assert len(closed_sessions) == 2
    assert closed_sessions[0] is request_sessions[0]
    assert closed_sessions[1] is not closed_sessions[0]
    assert (cache_root / descriptor["source_id"] / name).read_bytes() == content
    assert (exam_dir / name).read_bytes() == content
    assert source.sha256_file(exam_dir / name) == descriptor["files"][0]["sha256"]
    assert source.read_json(exam_dir / "source_metadata.json")["source_id"] == descriptor["source_id"]


@pytest.mark.parametrize("download_matches", [True, False])
def test_materialize_does_not_trust_corrupt_cached_attachment(
    tmp_path: Path, monkeypatch, downloadable_exam_source, closed_sessions, download_matches: bool
) -> None:
    calls, name, content, request_sessions = downloadable_exam_source
    source_path = tmp_path / "exam-source.json"
    cache_root = tmp_path / "cache"
    exam_dir = tmp_path / "materialized"
    source.discover_exam_source(source_path, tls_verify=True, cache_root=cache_root)
    descriptor = source.read_json(source_path)
    cache_target = cache_root / descriptor["source_id"] / name
    cache_target.write_bytes(b"corrupt cache")
    calls.clear()

    def fake_get(session, url, **_kwargs):
        calls.append(url)
        request_sessions.append(session)
        return make_response(200, content if download_matches else b"changed source", url=url)

    monkeypatch.setattr(source.requests.Session, "get", fake_get)
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
    assert len(closed_sessions) == 2
    assert closed_sessions[-1] is request_sessions[-1]
    assert closed_sessions[-1] is not request_sessions[0]


def test_discover_closes_shared_session_after_page_network_failure(
    tmp_path: Path, monkeypatch, downloadable_exam_source, closed_sessions
) -> None:
    calls, _name, _content, request_sessions = downloadable_exam_source
    original_get = requests.Session.get
    sleeps = []

    def fake_get(session, url, **kwargs):
        if url == source.JWC_LIST_URLS[1]:
            calls.append(url)
            request_sessions.append(session)
            raise requests.exceptions.ConnectionError("page two connection failed")
        return original_get(session, url, **kwargs)

    monkeypatch.setattr(source.requests.Session, "get", fake_get)
    monkeypatch.setattr(source.time, "sleep", sleeps.append)
    source_path = tmp_path / "exam-source.json"

    with pytest.raises(source.ExamDataError, match="page two connection failed"):
        source.discover_exam_source(source_path, tls_verify=True, cache_root=tmp_path / "cache")

    assert calls == [source.JWC_LIST_URL] + [source.JWC_LIST_URLS[1]] * 4
    assert all(session is request_sessions[0] for session in request_sessions)
    assert closed_sessions == [request_sessions[0]]
    assert sleeps == [5, 10, 20]
    assert not source_path.exists()


def test_discover_reuses_session_after_page_network_error(
    tmp_path: Path, monkeypatch, downloadable_exam_source, closed_sessions
) -> None:
    calls, _name, _content, request_sessions = downloadable_exam_source
    original_get = requests.Session.get
    sleeps = []
    page_two_failed = False

    def fake_get(session, url, **kwargs):
        nonlocal page_two_failed
        if url == source.JWC_LIST_URLS[1] and not page_two_failed:
            page_two_failed = True
            calls.append(url)
            request_sessions.append(session)
            raise requests.exceptions.ConnectionError("page two transient error")
        return original_get(session, url, **kwargs)

    monkeypatch.setattr(source.requests.Session, "get", fake_get)
    monkeypatch.setattr(source.time, "sleep", sleeps.append)

    source.discover_exam_source(tmp_path / "exam-source.json", tls_verify=True)

    assert len(calls) == 5
    assert calls[1:3] == [source.JWC_LIST_URLS[1]] * 2
    assert all(session is request_sessions[0] for session in request_sessions)
    assert closed_sessions == [request_sessions[0]]
    assert sleeps == [5]


def test_materialize_shares_one_session_across_files_and_retries(
    tmp_path: Path, monkeypatch, downloadable_exam_source, closed_sessions
) -> None:
    calls, first_name, content, request_sessions = downloadable_exam_source
    source_path = tmp_path / "exam-source.json"
    source.discover_exam_source(source_path, tls_verify=True)
    descriptor = source.read_json(source_path)
    second_name = "另一份学生考试安排.xlsx"
    descriptor["files"].append(
        {**descriptor["files"][0], "name": second_name, "url": "https://jwc.njupt.edu.cn/exam2.xlsx"}
    )
    descriptor["source_id"] = source.source_descriptor_id(descriptor)
    source.write_json(source_path, descriptor)
    calls.clear()
    request_sessions.clear()
    sleeps = []

    def fake_get(session, url, **kwargs):
        calls.append(url)
        request_sessions.append(session)
        assert kwargs["timeout"] == (10, 60)
        if len(calls) == 1:
            raise requests.exceptions.ConnectionError("attachment connection failed")
        return make_response(200, content, url=url)

    monkeypatch.setattr(source.requests.Session, "get", fake_get)
    monkeypatch.setattr(source.time, "sleep", sleeps.append)
    exam_dir = tmp_path / "materialized"

    source.materialize_exam_files(
        source_path=source_path, exam_dir=exam_dir, cache_root=tmp_path / "cache"
    )

    assert calls == [descriptor["files"][0]["url"]] * 2 + [descriptor["files"][1]["url"]]
    assert all(session is request_sessions[0] for session in request_sessions)
    assert len(closed_sessions) == 2
    assert closed_sessions[-1] is request_sessions[0]
    assert closed_sessions[-1] is not closed_sessions[0]
    assert sleeps == [5]
    assert (exam_dir / first_name).read_bytes() == content
    assert (exam_dir / second_name).read_bytes() == content
