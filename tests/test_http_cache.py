"""Regression tests for the HTTP response cache of the httpx backends.

All requests go to a local test server which counts how often each path was hit.
"""

from __future__ import annotations

from collections import Counter
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import threading
import time
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import pytest

import anyenv
from anyenv.download import functional
from anyenv.download.httpx_backend.backend import CACHE_DB_NAME


if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from anyenv.download.base import BackendType


BODY = b'{"answer": 42}'
HITS: Counter[str] = Counter()
_LOCK = threading.Lock()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        with _LOCK:
            HITS[self.path] += 1
        body = BODY
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        # Like many APIs: tell clients not to cache. anyenv caches anyway.
        self.send_header("Cache-Control", "max-age=0")
        if path == "/gzip":
            body = gzip.compress(BODY)
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def server_url() -> Iterator[str]:
    """Serve the counting handler on a random local port."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def url(server_url: str, request: pytest.FixtureRequest) -> str:
    """A URL unique to the running test, so hit counts don't leak between tests."""
    name = "".join(c if c.isalnum() else "_" for c in request.node.name)
    return f"{server_url}/gzip?test={name}"


def _hits(url: str) -> int:
    parts = urlsplit(url)
    return HITS[f"{parts.path}?{parts.query}"]


BACKENDS = [
    pytest.param(
        name,
        marks=pytest.mark.skipif(
            not (importlib.util.find_spec(name) and importlib.util.find_spec("hishel")),
            reason=f"{name} not installed",
        ),
    )
    for name in ("httpx", "httpx2")
]


def _shift_time(monkeypatch: pytest.MonkeyPatch, seconds: float) -> None:
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + seconds)


def test_get_backend_honors_cache_settings(tmp_path: Path) -> None:
    """Get backend honors cache settings."""
    backend = functional.get_backend(None, cache_dir=tmp_path, cache_ttl="1w")
    assert backend.cache_dir == tmp_path
    assert backend.cache_ttl == 7 * 24 * 3600


def test_default_backend_without_settings_keeps_defaults() -> None:
    """Default backend without settings keeps defaults."""
    backend = functional.get_default_backend()
    assert backend.cache_ttl == 3600  # noqa: PLR2004


def test_backends_are_reused_per_cache_config(tmp_path: Path) -> None:
    """Backends are reused per cache config."""
    get = functional._backend_for_request  # noqa: SLF001
    a = get(None, tmp_path, "1w")
    b = get(None, str(tmp_path), "1w")
    c = get(None, tmp_path, "1d")
    assert a is b
    assert a is not c


@pytest.mark.parametrize("backend", BACKENDS)
async def test_repeated_requests_hit_cache(backend: BackendType, url: str, tmp_path: Path) -> None:
    """Repeated requests hit cache."""
    for _ in range(4):
        data = await anyenv.get_bytes(
            url, cache=True, cache_ttl="1w", cache_dir=tmp_path, backend=backend
        )
        assert data == BODY
    assert _hits(url) == 1
    assert (tmp_path / CACHE_DB_NAME).exists()


@pytest.mark.parametrize("backend", BACKENDS)
def test_repeated_sync_requests_hit_cache(backend: BackendType, url: str, tmp_path: Path) -> None:
    """Repeated sync requests hit cache."""
    for _ in range(4):
        data = anyenv.get_json_sync(
            url, cache=True, cache_ttl="1w", cache_dir=tmp_path, backend=backend
        )
        assert data == {"answer": 42}
    assert _hits(url) == 1


async def test_sync_requests_inside_event_loop_hit_cache(url: str, tmp_path: Path) -> None:
    """Sync requests inside event loop hit cache."""
    # run_sync falls back to a worker thread when a loop is already running.
    for _ in range(3):
        assert anyenv.get_bytes_sync(url, cache=True, cache_dir=tmp_path) == BODY
    assert _hits(url) == 1


async def test_default_backend_uses_given_cache_dir(url: str, tmp_path: Path) -> None:
    """Default backend uses given cache dir."""
    await anyenv.get_bytes(url, cache=True, cache_dir=tmp_path)
    await anyenv.get_bytes(url, cache=True, cache_dir=tmp_path)
    assert (tmp_path / CACHE_DB_NAME).exists()
    assert _hits(url) == 1


async def test_cache_false_always_fetches(url: str, tmp_path: Path) -> None:
    """Cache false always fetches."""
    await anyenv.get_bytes(url, cache=True, cache_dir=tmp_path)
    await anyenv.get_bytes(url, cache=False, cache_dir=tmp_path)
    assert _hits(url) == 2  # noqa: PLR2004


@pytest.mark.parametrize("backend", BACKENDS)
async def test_cache_ttl_is_honored(
    backend: BackendType, url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cache ttl is honored."""
    opts = {"cache": True, "cache_dir": tmp_path, "backend": backend}
    await anyenv.get_bytes(url, cache_ttl="1w", **opts)  # type: ignore[arg-type]
    # Past the old hard-coded 1h default, but within the requested week.
    _shift_time(monkeypatch, 2 * 3600)
    await anyenv.get_bytes(url, cache_ttl="1w", **opts)  # type: ignore[arg-type]
    assert _hits(url) == 1
    # A caller with a shorter TTL treats the 2h old entry as stale.
    await anyenv.get_bytes(url, cache_ttl="1h", **opts)  # type: ignore[arg-type]
    assert _hits(url) == 2  # noqa: PLR2004


async def test_entry_expires_after_ttl(
    url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Entry expires after ttl."""
    await anyenv.get_bytes(url, cache=True, cache_ttl=60, cache_dir=tmp_path)
    _shift_time(monkeypatch, 120)
    assert await anyenv.get_bytes(url, cache=True, cache_ttl=60, cache_dir=tmp_path) == BODY
    assert _hits(url) == 2  # noqa: PLR2004


async def _stored_entries(tmp_path: Path, url: str) -> list[tuple[dict[str, str], bytes]]:
    import hishel

    from anyenv.download.httpx_backend.cache import cache_key

    storage = hishel.AsyncSqliteStorage(database_path=str(tmp_path / CACHE_DB_NAME))
    try:
        result = []
        for entry in await storage.get_entries(cache_key("GET", url)):
            body = b"".join([chunk async for chunk in entry.response.stream])  # type: ignore[union-attr]
            result.append((dict(entry.response.headers), body))
        return result
    finally:
        await storage.close()


@pytest.mark.parametrize("backend", BACKENDS)
async def test_bodies_are_stored_decoded(backend: BackendType, url: str, tmp_path: Path) -> None:
    """Bodies are stored decoded."""
    await anyenv.get_bytes(url, cache=True, cache_dir=tmp_path, backend=backend)
    [(headers, body)] = await _stored_entries(tmp_path, url)
    assert body == BODY
    assert "content-encoding" not in {k.lower() for k in headers}


async def _store_legacy_entry(tmp_path: Path, url: str, encoding: str, body: bytes) -> None:
    """Write an entry like hishel does without anyenv's decoding layer."""
    import hishel

    from anyenv.download.httpx_backend.cache import cache_key

    storage = hishel.AsyncSqliteStorage(database_path=str(tmp_path / CACHE_DB_NAME))
    try:
        request = hishel.Request(method="GET", url=url, headers=hishel.Headers({}))

        async def stream() -> object:
            yield body

        response = hishel.Response(
            status_code=200,
            headers=hishel.Headers({"content-encoding": encoding}),
            stream=stream(),  # type: ignore[arg-type]
        )
        entry = await storage.create_entry(request, response, cache_key("GET", url))
        async for _ in entry.response.stream:  # type: ignore[union-attr]
            pass  # the entry is committed once its stream was read
    finally:
        await storage.close()
    assert len(await _stored_entries(tmp_path, url)) == 1


@pytest.mark.parametrize("backend", BACKENDS)
async def test_entry_with_unsupported_encoding_is_refetched(
    backend: BackendType, url: str, tmp_path: Path
) -> None:
    """Entry with unsupported encoding is refetched."""
    # E.g. stored zstd-encoded by an environment that supports zstd.
    await _store_legacy_entry(tmp_path, url, "x-unsupported", b"\x28\xb5\x2f\xfd garbage")
    data = await anyenv.get_json(url, cache=True, cache_dir=tmp_path, backend=backend)
    assert data == {"answer": 42}
    assert _hits(url) == 1
    # The refetched entry replaced the broken one and is served from now on.
    assert await anyenv.get_json(url, cache=True, cache_dir=tmp_path, backend=backend) == data
    assert _hits(url) == 1


@pytest.mark.parametrize("backend", BACKENDS)
async def test_corrupt_entry_is_refetched(backend: BackendType, url: str, tmp_path: Path) -> None:
    """Corrupt entry is refetched."""
    await _store_legacy_entry(tmp_path, url, "gzip", b"definitely not gzip")
    data = await anyenv.get_bytes(url, cache=True, cache_dir=tmp_path, backend=backend)
    assert data == BODY
    assert _hits(url) == 1


async def test_legacy_decodable_entry_is_served(url: str, tmp_path: Path) -> None:
    """Legacy decodable entry is served."""
    await _store_legacy_entry(tmp_path, url, "gzip", gzip.compress(BODY))
    assert await anyenv.get_bytes(url, cache=True, cache_dir=tmp_path) == BODY
    assert _hits(url) == 0


def test_corrupt_database_is_a_cache_miss(url: str, tmp_path: Path) -> None:
    """Corrupt database is a cache miss."""
    (tmp_path / CACHE_DB_NAME).write_bytes(b"this is not a sqlite database" * 100)
    assert anyenv.get_bytes_sync(url, cache=True, cache_dir=tmp_path) == BODY
    assert _hits(url) == 1


async def test_session_requests_hit_cache(server_url: str, tmp_path: Path) -> None:
    """Session requests hit cache."""
    backend = functional.get_backend("httpx", cache_dir=tmp_path, cache_ttl="1d")
    path = "/gzip?test=session"
    async with await backend.create_session(base_url=server_url, cache=True) as session:
        for _ in range(3):
            response = await session.request("GET", path)
            assert await response.bytes() == BODY
    assert HITS[path] == 1
