"""Tests for the HTTP helpers and sessions against a local server."""

from __future__ import annotations

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sys
import threading
from typing import TYPE_CHECKING, Any

import pytest

import anyenv
from anyenv.download.exceptions import RequestError, ResponseError


if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


PAYLOAD = b"x" * 10_000


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.connections = 0
        self.requests: list[dict[str, str]] = []
        self.lock = threading.Lock()


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # keep-alive: lets a client reuse a connection
    server: _Server

    def setup(self) -> None:
        super().setup()
        with self.server.lock:
            self.server.connections += 1

    def log_message(self, *args: object) -> None:
        pass

    def _send(self, status: int, body: bytes, content_type: str = "text/plain") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        with self.server.lock:
            self.server.requests.append({"path": self.path, **dict(self.headers)})
        match self.path.split("?")[0]:
            case "/json":
                self._send(200, json.dumps({"ok": True}).encode(), "application/json")
            case "/text":
                self._send(200, "grüße".encode(), "text/plain; charset=utf-8")
            case "/headers":
                self._send(200, json.dumps(dict(self.headers)).encode(), "application/json")
            case "/file":
                self._send(200, PAYLOAD, "application/octet-stream")
            case "/truncated":
                # Promises more than it sends, then closes the connection.
                self.send_response(200)
                self.send_header("Content-Length", str(len(PAYLOAD) * 2))
                self.end_headers()
                self.wfile.write(PAYLOAD)
                self.wfile.flush()
                self.close_connection = True
            case "/redirect":
                self.send_response(302)
                self.send_header("Location", "/json")
                self.send_header("Content-Length", "0")
                self.end_headers()
            case _:
                self._send(404, b"not found")

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        self._send(200, self.rfile.read(length), "application/json")


@pytest.fixture
def server() -> Iterator[_Server]:
    """A local server counting its connections."""
    srv = _Server()
    thread = threading.Thread(target=srv.serve_forever, args=(0.05,), daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def server_url(server: _Server) -> str:
    """Server url."""
    return f"http://127.0.0.1:{server.server_address[1]}"


# Helpers (no session: a client per call)


async def test_get_json(server_url: str, httpx_flavour: str) -> None:
    """Get json."""
    assert await anyenv.get_json(f"{server_url}/json") == {"ok": True}


async def test_get_text_and_bytes(server_url: str) -> None:
    """Get text and bytes."""
    assert await anyenv.get_text(f"{server_url}/text") == "grüße"
    assert await anyenv.get_bytes(f"{server_url}/file") == PAYLOAD


async def test_get_json_validates_return_type(server_url: str) -> None:
    """Get json validates return type."""
    from typing import TypedDict

    class Ok(TypedDict):
        ok: bool

    assert await anyenv.get_json(f"{server_url}/json", return_type=Ok) == {"ok": True}
    with pytest.raises(TypeError):
        await anyenv.get_json(f"{server_url}/json", return_type=list)


async def test_response_accessors_are_sync(server_url: str, httpx_flavour: str) -> None:
    """Response accessors are sync."""
    response = await anyenv.get(f"{server_url}/text")
    assert response.status_code == 200  # noqa: PLR2004
    assert response.reason == "OK"
    assert response.url == f"{server_url}/text"
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.text == "grüße"
    assert response.content == "grüße".encode()
    response = await anyenv.get(f"{server_url}/json")
    assert response.json() == {"ok": True}
    assert response.validated_json(dict) == {"ok": True}


async def test_follows_redirects(server_url: str, httpx_flavour: str) -> None:
    """Follows redirects."""
    assert await anyenv.get_json(f"{server_url}/redirect") == {"ok": True}


async def test_post_json(server_url: str, httpx_flavour: str) -> None:
    """Post json."""
    response = await anyenv.post(f"{server_url}/echo", json={"a": 1})
    assert response.json() == {"a": 1}
    assert await anyenv.post_json(f"{server_url}/echo", {"b": 2}) == {"b": 2}


async def test_http_error(server_url: str, httpx_flavour: str) -> None:
    """Http error."""
    with pytest.raises(ResponseError) as info:
        await anyenv.get(f"{server_url}/missing")
    assert info.value.status_code == 404  # noqa: PLR2004
    assert info.value.response is not None
    assert info.value.response.text == "not found"


async def test_connection_error(httpx_flavour: str) -> None:
    """Connection error."""
    with pytest.raises(RequestError):
        await anyenv.get("http://127.0.0.1:1/", timeout=2)


async def test_timeout_raises_request_error(httpx_flavour: str) -> None:
    """Timeout raises request error."""
    import socket

    # A listening socket which never accepts or answers.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(0)
        url = f"http://127.0.0.1:{sock.getsockname()[1]}/"
        with pytest.raises(RequestError):
            await anyenv.get(url, timeout=0.5)


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({"api_key": "k"}, {"Authorization": "Bearer k"}),
        (
            {"api_key": "k", "auth_type": "basic", "auth_username": "u"},
            {"Authorization": "Basic dTpr"},
        ),
        ({"api_key": "k", "auth_type": "header"}, {"X-API-Key": "k"}),
        ({"api_key": "k", "auth_type": "header", "auth_header_name": "X-T"}, {"X-T": "k"}),
    ],
)
async def test_auth_headers(
    server_url: str, options: dict[str, Any], expected: dict[str, str]
) -> None:
    """Auth headers."""
    sent = await anyenv.get_json(f"{server_url}/headers", **options)
    assert {k: sent[k] for k in expected} == expected


async def test_query_auth(server: _Server, server_url: str) -> None:
    """Query auth."""
    await anyenv.get(f"{server_url}/json", api_key="k", auth_type="query", params={"a": 1})
    assert server.requests[-1]["path"] == "/json?a=1&api_key=k"


async def test_download(server_url: str, httpx_flavour: str, tmp_path: Path) -> None:
    """Streaming download writes file and reports progress (sync and async callbacks)."""
    target = tmp_path / "file.bin"
    progress: list[tuple[int, int]] = []

    async def on_progress(cur: int, total: int) -> None:
        progress.append((cur, total))

    await anyenv.download(f"{server_url}/file", target, progress_callback=on_progress)
    assert target.read_bytes() == PAYLOAD
    assert progress[-1] == (len(PAYLOAD), len(PAYLOAD))
    target.unlink()
    anyenv.download_sync(f"{server_url}/file", target, progress_callback=lambda c, t: None)
    assert target.read_bytes() == PAYLOAD


async def test_download_http_error_has_body(server_url: str, tmp_path: Path) -> None:
    """Download http error has body."""
    with pytest.raises(ResponseError) as info:
        await anyenv.download(f"{server_url}/missing", tmp_path / "x")
    assert info.value.response is not None
    assert info.value.response.text == "not found"
    assert list(tmp_path.iterdir()) == []


async def test_failed_download_leaves_target_alone(
    server_url: str, httpx_flavour: str, tmp_path: Path
) -> None:
    """A download cut short neither leaves a partial file nor clobbers the old one."""
    target = tmp_path / "file.bin"
    target.write_bytes(b"old")
    with pytest.raises(RequestError):
        await anyenv.download(f"{server_url}/truncated", target)
    assert target.read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["file.bin"]


def test_sync_helpers(server_url: str) -> None:
    """Sync helpers."""
    assert anyenv.get_json_sync(f"{server_url}/json") == {"ok": True}
    assert anyenv.get_text_sync(f"{server_url}/text") == "grüße"
    assert anyenv.get_bytes_sync(f"{server_url}/file") == PAYLOAD
    assert anyenv.get_sync(f"{server_url}/json").json() == {"ok": True}
    assert anyenv.post_sync(f"{server_url}/e", json=[1]).json() == [1]
    assert anyenv.post_json_sync(f"{server_url}/e", {"a": 1}) == {"a": 1}
    assert anyenv.request_sync("GET", f"{server_url}/json").status_code == 200  # noqa: PLR2004


def test_sync_helpers_apply_header_middlewares(
    server_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sync helpers apply header middlewares."""
    from anyenv.download.middleware import header_middlewares

    def middleware(url: str, headers: dict[str, str]) -> dict[str, str]:
        return {**headers, "X-Middleware": "yes"}

    header_middlewares.add(middleware)
    try:
        assert anyenv.get_json_sync(f"{server_url}/headers")["X-Middleware"] == "yes"
    finally:
        header_middlewares.remove(middleware)


# Sessions


async def test_session_reuses_one_connection(
    server: _Server, server_url: str, httpx_flavour: str
) -> None:
    """N requests in a session go over one TCP connection; without one, N connections."""
    for _ in range(5):
        await anyenv.get_json(f"{server_url}/json")
    assert server.connections == 5  # noqa: PLR2004

    server.connections = 0
    async with anyenv.http_session() as session:
        for _ in range(3):
            assert await session.get_json(f"{server_url}/json") == {"ok": True}
        for _ in range(3):  # the module helpers pick up the open session
            assert await anyenv.get_json(f"{server_url}/json") == {"ok": True}
        await anyenv.post_json(f"{server_url}/echo", {"a": 1})
        assert await anyenv.get_text(f"{server_url}/text") == "grüße"
    assert server.connections == 1


async def test_session_base_url_and_headers(server: _Server, server_url: str) -> None:
    """Session base url and headers."""
    async with anyenv.http_session(base_url=server_url, headers={"X-Token": "secret"}) as s:
        sent = await s.get_json("/headers")
        assert sent["X-Token"] == "secret"
        sent = await anyenv.get_json("headers", headers={"X-Other": "1"})
        assert sent["X-Token"] == "secret"
        assert sent["X-Other"] == "1"
        # Absolute URLs elsewhere don't get the session's headers (no leaked tokens).
        other = server_url.replace("127.0.0.1", "localhost")
        sent = await anyenv.get_json(f"{other}/headers")
        assert "X-Token" not in sent


async def test_session_headers_without_base_url_go_everywhere(server_url: str) -> None:
    """Session headers without base url go everywhere."""
    async with anyenv.http_session(headers={"X-Token": "t"}):
        assert (await anyenv.get_json(f"{server_url}/headers"))["X-Token"] == "t"


async def test_session_errors(server_url: str) -> None:
    """Session errors."""
    async with anyenv.http_session(base_url=server_url) as s:
        with pytest.raises(ResponseError):
            await s.get("/missing")
    async with anyenv.http_session(base_url="http://127.0.0.1:1") as s:
        with pytest.raises(RequestError):
            await s.get("/")


async def test_session_timeout(server_url: str) -> None:
    """Session timeout."""
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(0)
        url = f"http://127.0.0.1:{sock.getsockname()[1]}/"
        async with anyenv.http_session(timeout=0.3):
            with pytest.raises(RequestError):
                await anyenv.get(url)


async def test_session_download(server_url: str, tmp_path: Path) -> None:
    """Session download."""
    async with anyenv.http_session(base_url=server_url) as s:
        await s.download("/file", tmp_path / "f")
        await anyenv.download("/file", tmp_path / "g")
    assert (tmp_path / "f").read_bytes() == (tmp_path / "g").read_bytes() == PAYLOAD


async def test_nested_sessions_innermost_wins(server_url: str) -> None:
    """Nested sessions innermost wins."""
    from anyenv.download.session import current_session

    assert current_session() is None
    async with anyenv.http_session(headers={"X-Level": "outer"}) as outer:
        assert current_session() is outer
        async with anyenv.http_session(headers={"X-Level": "inner"}) as inner:
            assert current_session() is inner
            assert (await anyenv.get_json(f"{server_url}/headers"))["X-Level"] == "inner"
        assert current_session() is outer
        assert (await anyenv.get_json(f"{server_url}/headers"))["X-Level"] == "outer"
    assert current_session() is None


async def test_session_scope_across_tasks(server_url: str) -> None:
    """Tasks started inside a session use it; a session in one task doesn't leak to others."""
    from anyenv.download.session import current_session

    seen: dict[str, object] = {}
    entered = asyncio.Event()
    release = asyncio.Event()

    async def other_task() -> None:
        await entered.wait()
        seen["sibling"] = current_session()
        release.set()

    async def with_session() -> None:
        async with anyenv.http_session() as s:
            seen["own"] = s

            async def child() -> object:
                return current_session()

            seen["child"] = await asyncio.create_task(child())
            entered.set()
            await release.wait()

    await asyncio.gather(other_task(), with_session())
    assert seen["child"] is seen["own"]
    assert seen["sibling"] is None


async def test_task_outliving_its_session_gets_own_client(server_url: str) -> None:
    """Task outliving its session gets own client."""
    from anyenv.download.session import current_session

    async with anyenv.http_session():
        go = asyncio.Event()

        async def late() -> Any:
            await go.wait()
            return current_session(), await anyenv.get_json(f"{server_url}/json")

        task = asyncio.create_task(late())
    go.set()
    session, data = await task
    assert session is None
    assert data == {"ok": True}


async def test_sync_helpers_inside_session_use_own_client(server: _Server, server_url: str) -> None:
    """A *_sync helper runs on another loop, where the session's client can't work."""
    async with anyenv.http_session() as session:
        await session.get(f"{server_url}/json")
        assert anyenv.get_json_sync(f"{server_url}/json") == {"ok": True}
    assert server.connections == 2  # noqa: PLR2004


async def test_session_with_other_cache_options_uses_own_client(
    server: _Server, server_url: str, tmp_path: Path
) -> None:
    """Session with other cache options uses own client."""
    async with anyenv.http_session() as session:
        await session.get(f"{server_url}/json")
        await anyenv.get(f"{server_url}/json")  # same options: the session
        await anyenv.get(f"{server_url}/json", cache=False)  # same: the session
        await anyenv.get(f"{server_url}/json", cache=True, cache_dir=tmp_path)  # own client
    assert server.connections == 2  # noqa: PLR2004


# Pyodide


class _FakeJsResponse:
    def __init__(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.status = status
        self.headers = _FakeHeaders(headers)
        self._body = body

    async def arrayBuffer(self) -> Any:  # noqa: N802
        body = self._body

        class Buffer:
            def to_bytes(self) -> bytes:
                return body

        return Buffer()


class _FakeHeaders:
    def __init__(self, headers: dict[str, str]) -> None:
        self._headers = headers

    def entries(self) -> Iterator[tuple[str, str]]:
        return iter(self._headers.items())


@pytest.fixture
def fake_pyodide(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    """Pretend to run under Pyodide, with a `js.fetch` that records its calls."""
    import types

    calls: list[tuple[str, dict[str, Any]]] = []

    async def fetch(url: str, options: dict[str, Any]) -> _FakeJsResponse:
        calls.append((url, options))
        if url.endswith("/fail"):
            raise RuntimeError("TypeError: Failed to fetch")  # noqa: TRY003
        # The browser has decoded the gzip body already.
        return _FakeJsResponse(
            200,
            {"content-type": "application/json", "content-encoding": "gzip", "content-length": "1"},
            b'{"via": "fetch"}',
        )

    js = types.ModuleType("js")
    js.fetch = fetch  # type: ignore[attr-defined]
    js.Object = types.SimpleNamespace(fromEntries=dict)  # type: ignore[attr-defined]
    ffi = types.ModuleType("pyodide.ffi")
    ffi.to_js = lambda value, **kwargs: value  # type: ignore[attr-defined]
    pyodide = types.ModuleType("pyodide")
    pyodide.ffi = ffi  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "js", js)
    monkeypatch.setitem(sys.modules, "pyodide", pyodide)
    monkeypatch.setitem(sys.modules, "pyodide.ffi", ffi)
    monkeypatch.setattr(sys, "platform", "emscripten")
    return calls


async def test_pyodide_uses_fetch_transport(
    fake_pyodide: list[tuple[str, dict[str, Any]]], httpx_flavour: str
) -> None:
    """Pyodide uses fetch transport."""
    assert await anyenv.get_json("https://example.com/data", headers={"X-A": "1"}) == {
        "via": "fetch"
    }
    url, options = fake_pyodide[-1]
    assert url == "https://example.com/data"
    assert options["method"] == "GET"
    assert options["headers"]["x-a"] == "1"
    assert "body" not in options  # fetch() refuses a body on GET

    await anyenv.post("https://example.com/post", json={"a": 1})
    _, options = fake_pyodide[-1]
    assert options["body"] == b'{"a":1}'

    async with anyenv.http_session(base_url="https://example.com") as s:
        assert await s.get_json("/x") == {"via": "fetch"}
    assert fake_pyodide[-1][0] == "https://example.com/x"


async def test_pyodide_fetch_failure_is_request_error(
    fake_pyodide: list[tuple[str, dict[str, Any]]],
) -> None:
    """Pyodide fetch failure is request error."""
    with pytest.raises(RequestError):
        await anyenv.get("https://example.com/fail")


def test_pyodide_transport_is_not_used_elsewhere() -> None:
    """Pyodide transport is not used elsewhere."""
    from anyenv.download.httpx_backend import get_js_transport_class
    from anyenv.download.session import CacheSettings, create_client

    client, mod = create_client(CacheSettings.create(False))
    assert not isinstance(client._transport, get_js_transport_class(mod.__name__))  # noqa: SLF001
