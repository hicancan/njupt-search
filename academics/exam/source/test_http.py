from __future__ import annotations

import hashlib
import json
import socket
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from typing import cast

import pytest

from academics.exam.source import discovery as source


EXAM_TITLE = "2025-2026学年第二学期考试安排表"
ATTACHMENT_NAME = "学生考试安排.xlsx"
ATTACHMENT_BODY = b"current exam attachment"
PAGE_ONE = "/1594/list.htm"
PAGE_TWO = "/1594/list2.htm"
NOTICE = "/notice.htm"
ATTACHMENT = "/attachment.xlsx"


class ExamHttpServer(ThreadingHTTPServer):
    def __init__(self) -> None:
        self.accept_count = 0
        self.requests: list[tuple[str, int]] = []
        self.path_counts: Counter[str] = Counter()
        self.drop_page_two_once = False
        self.lock = Lock()
        super().__init__(("127.0.0.1", 0), ExamHttpHandler)

    def get_request(self) -> tuple[socket.socket, tuple[str, int]]:
        connection, address = super().get_request()
        with self.lock:
            self.accept_count += 1
        return connection, address


class ExamHttpHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        server = cast(ExamHttpServer, self.server)
        with server.lock:
            server.requests.append((self.path, self.client_address[1]))
            server.path_counts[self.path] += 1
            drop_connection = (
                server.drop_page_two_once
                and self.path == PAGE_TWO
                and server.path_counts[self.path] == 1
            )
        if drop_connection:
            self.close_connection = True
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return

        bodies = {
            PAGE_ONE: '<div class="col_news_con"><ul></ul></div>'.encode("utf-8"),
            PAGE_TWO: (
                '<div class="col_news_con"><ul><li class="news">'
                f'<span class="news_title"><a href="{NOTICE}">{EXAM_TITLE}</a></span>'
                "</li></ul></div>"
            ).encode("utf-8"),
            NOTICE: f'<a href="{ATTACHMENT}">{ATTACHMENT_NAME}</a>'.encode("utf-8"),
            ATTACHMENT: ATTACHMENT_BODY,
        }
        body = bodies.get(self.path, b"not found")
        self.send_response(200 if self.path in bodies else 404)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "keep-alive")
        if self.path == ATTACHMENT:
            self.send_header("Last-Modified", "Wed, 10 Jun 2026 08:00:00 GMT")
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()


@pytest.fixture
def exam_http_server(monkeypatch):
    server = ExamHttpServer()
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setattr(source, "JWC_LIST_URL", base_url + PAGE_ONE)
    monkeypatch.setattr(source, "JWC_LIST_URLS", (base_url + PAGE_ONE, base_url + PAGE_TWO))
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def discover_and_check_cache(tmp_path: Path, server: ExamHttpServer) -> None:
    output = tmp_path / "exam-source.json"
    cache = tmp_path / "cache"
    source.discover_exam_source(output, tls_verify=True, cache_root=cache)

    descriptor = json.loads(output.read_text(encoding="utf-8"))
    assert descriptor["format"] == "njupt-exam-source"
    assert descriptor["source_title"] == EXAM_TITLE
    assert descriptor["source_url"] == f"http://127.0.0.1:{server.server_port}{NOTICE}"
    assert descriptor["source_updated_at"] == "2026-06-10T08:00:00+00:00"
    assert len(descriptor["files"]) == 1
    assert descriptor["files"][0]["sha256"] == hashlib.sha256(ATTACHMENT_BODY).hexdigest()
    assert (cache / descriptor["source_id"] / ATTACHMENT_NAME).read_bytes() == ATTACHMENT_BODY


def test_discovery_reuses_connection_across_pages_notice_and_attachment(
    tmp_path: Path, exam_http_server: ExamHttpServer
) -> None:
    discover_and_check_cache(tmp_path, exam_http_server)

    assert [path for path, _port in exam_http_server.requests] == [
        PAGE_ONE, PAGE_TWO, NOTICE, ATTACHMENT
    ]
    assert exam_http_server.accept_count == 1
    assert len({port for _path, port in exam_http_server.requests}) == 1


def test_discovery_recovers_after_reused_connection_is_closed(
    tmp_path: Path, monkeypatch, exam_http_server: ExamHttpServer
) -> None:
    exam_http_server.drop_page_two_once = True
    sleeps = []
    monkeypatch.setattr(source.time, "sleep", sleeps.append)

    discover_and_check_cache(tmp_path, exam_http_server)

    assert [path for path, _port in exam_http_server.requests] == [
        PAGE_ONE, PAGE_TWO, PAGE_TWO, NOTICE, ATTACHMENT
    ]
    assert sleeps == [5]
    assert exam_http_server.accept_count == 2
    ports = [port for _path, port in exam_http_server.requests]
    assert ports[0] == ports[1]
    assert ports[1] != ports[2]
    assert ports[2] == ports[3] == ports[4]
