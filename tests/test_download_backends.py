"""Tests for the HTTP download backends against a local server."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import threading
from typing import TYPE_CHECKING

import pytest

from anyenv.download import functional
from anyenv.download.exceptions import RequestError, ResponseError


if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from anyenv.download.base import BackendType


PAYLOAD = b"x" * 10_000


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        pass

    def _send(self, status: int, body: bytes, content_type: str = "text/plain") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        match self.path.split("?")[0]:
            case "/json":
                self._send(200, json.dumps({"ok": True}).encode(), "application/json")
            case "/file":
                self._send(200, PAYLOAD, "application/octet-stream")
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


@pytest.fixture(scope="module")
def server_url() -> Iterator[str]:
    """Serve the test handler on a random local port."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "httpx2": ("httpx2", "hishel"),
    "httpx": ("httpx", "hishel"),
    "aiohttp": ("aiohttp", "aiohttp_client_cache", "aiofiles"),
}

BACKENDS = [
    pytest.param(
        name,
        marks=pytest.mark.skipif(
            not all(importlib.util.find_spec(m) for m in mods),
            reason=f"{name} not installed",
        ),
    )
    for name, mods in _REQUIREMENTS.items()
]


@pytest.fixture(params=BACKENDS)
def backend_type(request: pytest.FixtureRequest) -> BackendType:
    """Parametrize over installed backends."""
    return request.param


def test_default_backend_prefers_httpx2() -> None:
    """httpx2 is picked first when installed."""
    if not importlib.util.find_spec("httpx2"):
        pytest.skip("httpx2 not installed")
    from anyenv.download.httpx_backend import Httpx2Backend

    assert isinstance(functional.get_default_backend(), Httpx2Backend)


async def test_get_json(server_url: str, backend_type: BackendType) -> None:
    """GET + JSON decode works."""
    data = await functional.get_json(f"{server_url}/json", backend=backend_type)
    assert data == {"ok": True}


async def test_follows_redirects(server_url: str, backend_type: BackendType) -> None:
    """Redirects are followed."""
    data = await functional.get_json(f"{server_url}/redirect", backend=backend_type)
    assert data == {"ok": True}


async def test_post_json(server_url: str, backend_type: BackendType) -> None:
    """POST JSON body round-trips."""
    response = await functional.post(f"{server_url}/echo", json={"a": 1}, backend=backend_type)
    assert await response.json() == {"a": 1}


async def test_http_error(server_url: str, backend_type: BackendType) -> None:
    """4xx responses raise ResponseError."""
    with pytest.raises(ResponseError):
        await functional.get(f"{server_url}/missing", backend=backend_type)


async def test_connection_error(backend_type: BackendType) -> None:
    """Connection failures raise RequestError."""
    with pytest.raises(RequestError):
        await functional.get("http://127.0.0.1:1/", backend=backend_type, timeout=2)


async def test_download(server_url: str, backend_type: BackendType, tmp_path: Path) -> None:
    """Streaming download writes file and reports progress."""
    target = tmp_path / "file.bin"
    progress: list[tuple[int, int]] = []
    backend = functional.get_backend(backend_type)
    await backend.download(
        f"{server_url}/file",
        target,
        progress_callback=lambda cur, total: progress.append((cur, total)),
    )
    assert target.read_bytes() == PAYLOAD
    assert progress[-1] == (len(PAYLOAD), len(PAYLOAD))


async def test_session(server_url: str, backend_type: BackendType) -> None:
    """Sessions honor base_url and wrap transport errors."""
    backend = functional.get_backend(backend_type)
    session = await backend.create_session(base_url=server_url)
    try:
        response = await session.request("GET", "/json")
        assert await response.json() == {"ok": True}
        with pytest.raises(RequestError):
            await (await backend.create_session(base_url="http://127.0.0.1:1")).request("GET", "/")
    finally:
        await session.close()


async def test_cached_request(server_url: str, backend_type: BackendType, tmp_path: Path) -> None:
    """Cached requests work and survive a second hit."""
    backend = functional.get_backend(backend_type, cache_dir=tmp_path)
    for _ in range(2):
        response = await backend.request("GET", f"{server_url}/json", cache=True)
        assert await response.json() == {"ok": True}


async def test_timeout_raises_request_error(backend_type: BackendType) -> None:
    """Timeouts raise RequestError like other connection failures."""
    import socket

    # A listening socket which never accepts or answers.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(0)
        url = f"http://127.0.0.1:{sock.getsockname()[1]}/"
        with pytest.raises(RequestError):
            await functional.get(url, backend=backend_type, timeout=0.5)
