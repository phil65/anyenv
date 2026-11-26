"""HTTP sessions: one httpx client shared by many requests.

``http_session()`` opens a client and, while it is open, makes it the one the
module-level helpers (``anyenv.get_json`` and friends) use in the current context
(a ``ContextVar``: the innermost open session wins; tasks started inside inherit
it). Without a session every helper call creates and closes its own client.
"""

import asyncio
import base64
import contextlib
from contextvars import ContextVar
from dataclasses import dataclass
import inspect
import logging
import pathlib
import sys
from typing import TYPE_CHECKING, Any, Self, Unpack, assert_never

from anyenv.download.base import DEFAULT_TTL, HttpResponse, open_download_target
from anyenv.download.exceptions import RequestError, ResponseError, check_response
from anyenv.download.http_types import SecretStr
from anyenv.download.middleware import header_middlewares


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from types import ModuleType

    import httpx2 as httpx

    from anyenv.download.base import Method, ProgressCallback, RequestOptions, StrPath
    from anyenv.download.http_types import (
        AuthType,
        CacheType,
        FilesType,
        HeaderType,
        ParamsType,
    )


logger = logging.getLogger(__name__)

_current_session: ContextVar[HttpSession | None] = ContextVar("anyenv_http_session", default=None)


@dataclass(frozen=True, slots=True)
class CacheSettings:
    """Where and how long responses are cached (``enabled=False``: not at all)."""

    enabled: bool
    directory: pathlib.Path
    ttl: int
    backend: CacheType = "file"

    @classmethod
    def create(
        cls,
        cache: bool | None = False,
        cache_dir: StrPath | None = None,
        cache_ttl: int | str | None = None,
        cache_backend: CacheType = "file",
    ) -> CacheSettings:
        """Resolve the defaults (user cache dir, one hour) and parse a TTL like "1d"."""
        from appdirs import user_cache_dir  # type: ignore[import-untyped]

        return cls(
            enabled=bool(cache),
            directory=pathlib.Path(cache_dir or user_cache_dir("anyenv", False)),
            ttl=parse_ttl(cache_ttl),
            backend=cache_backend,
        )


def parse_ttl(cache_ttl: int | str | None) -> int:
    """Seconds for a TTL given as seconds or a period like "1h", "2d", "1w 2d"."""
    if isinstance(cache_ttl, str):
        from anyenv.parse_time import parse_time_period

        return int(parse_time_period(cache_ttl).total_seconds())
    return cache_ttl or DEFAULT_TTL


def _is_absolute(url: str) -> bool:
    return "://" in url.split("?", 1)[0]


def create_client(
    cache: CacheSettings, timeout: float | None = None
) -> tuple[httpx.AsyncClient, ModuleType]:
    """Create an httpx client (httpx2 if installed, else httpx) and return its module.

    Under Pyodide (``sys.platform == "emscripten"``) the client sends requests
    through the browser's ``fetch``.
    """
    from anyenv.download.httpx_backend import js_transport
    from anyenv.download.httpx_backend.module import get_httpx_module

    httpx_mod = get_httpx_module()
    kwargs: dict[str, Any] = {"follow_redirects": True, "timeout": timeout}
    if sys.platform == "emscripten":
        kwargs["transport"] = js_transport.get_js_transport_class(httpx_mod.__name__)()
    if not cache.enabled:
        return httpx_mod.AsyncClient(**kwargs), httpx_mod

    from anyenv.download.httpx_backend.cache import get_cache_client_class, get_storage

    storage = get_storage(cache.backend, cache.directory, cache.ttl)
    # Cached responses expire after the TTL, regardless of the server's
    # Cache-Control headers (many APIs send max-age=0). Bodies are stored decoded,
    # and unusable entries are refetched.
    client_cls = get_cache_client_class(httpx_mod.__name__, f"hishel.{httpx_mod.__name__}")
    return client_cls(storage=storage, ttl=cache.ttl, **kwargs), httpx_mod


def apply_auth(
    headers: HeaderType,
    params: ParamsType | None,
    *,
    api_key: str | SecretStr | None,
    auth_type: AuthType = "bearer",
    auth_username: str | None = None,
    auth_header_name: str | None = None,
) -> tuple[HeaderType, ParamsType | None]:
    """Return headers and params with the API key added as `auth_type` says."""
    if api_key is None:
        return headers, params
    key = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
    headers = dict(headers)
    match auth_type:
        case "bearer":
            headers["Authorization"] = f"Bearer {key}"
        case "basic":
            if auth_username is None:
                msg = "auth_username is required for basic authentication"
                raise ValueError(msg)
            encoded = base64.b64encode(f"{auth_username}:{key}".encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
        case "header":
            headers[auth_header_name or "X-API-Key"] = key
        case "query":
            params = {**(params or {}), "api_key": key}
        case _ as unreachable:
            assert_never(unreachable)
    return headers, params


class HttpSession:
    """One httpx client for many requests (connection reuse); see `http_session`.

    ``base_url`` resolves relative URLs. The session's ``headers`` go with requests
    to ``base_url`` (relative URLs and absolute ones under it); without a
    ``base_url``, with every request through the session, including those of
    libraries that use anyenv's helpers inside the ``async with`` block.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        headers: HeaderType | None = None,
        cache: CacheSettings | None = None,
        timeout: float | None = None,
    ) -> None:
        self.base_url = base_url
        self.headers: HeaderType = dict(headers or {})
        self.cache = cache or CacheSettings.create(False)
        self.timeout = timeout
        self._client, self._httpx = create_client(self.cache, timeout)
        self._closed = False
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def closed(self) -> bool:
        """Whether the session's client was closed."""
        return self._closed

    async def aclose(self) -> None:
        """Close the client (and its connections)."""
        self._closed = True
        self._loop = None  # no reference that keeps a finished loop alive
        await self._client.aclose()

    async def __aenter__(self) -> Self:
        self._loop = asyncio.get_running_loop()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    def usable_here(self) -> bool:
        """Whether this context can use the client: it's open and on its event loop.

        (Another loop may see the session through a copied context, e.g. in
        ``run_sync``; a client can't be shared between loops.)
        """
        if self._closed:
            return False
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return False
        return self._loop is None or self._loop is loop

    def accepts(
        self,
        cache: bool | None,
        cache_dir: StrPath | None,
        cache_ttl: int | str | None,
    ) -> bool:
        """Whether a helper call with these cache options can go through this session."""
        if self._closed:
            return False
        if cache is not None and cache != self.cache.enabled:
            return False
        if cache_dir is not None and pathlib.Path(cache_dir) != self.cache.directory:
            return False
        return cache_ttl is None or parse_ttl(cache_ttl) == self.cache.ttl

    def resolve(self, url: str) -> str:
        """The absolute URL of a request (relative URLs are appended to ``base_url``)."""
        if self.base_url is None or _is_absolute(url):
            return url
        return f"{self.base_url.rstrip('/')}/{url.lstrip('/')}"

    def _under_base_url(self, url: str) -> bool:
        if self.base_url is None:
            return True
        base = self.base_url.rstrip("/")
        return url == base or url.startswith((f"{base}/", f"{base}?"))

    def _headers_for(self, url: str, headers: HeaderType | None) -> HeaderType:
        own = self.headers if self._under_base_url(url) else {}
        return header_middlewares.apply(url, {**own, **(headers or {})})

    async def request(
        self,
        method: Method,
        url: str,
        *,
        json: Any = None,
        data: Any = None,
        files: FilesType | None = None,
        **options: Unpack[RequestOptions],
    ) -> HttpResponse:
        """Send a request; returns the response once its body is read.

        Raises:
            RequestError: The request failed (connection, timeout)
            ResponseError: The response has a 4xx / 5xx status
        """
        url = self.resolve(url)
        headers, params = apply_auth(
            self._headers_for(url, options.get("headers")),
            options.get("params"),
            api_key=options.get("api_key"),
            auth_type=options.get("auth_type", "bearer"),
            auth_username=options.get("auth_username"),
            auth_header_name=options.get("auth_header_name"),
        )
        extra: dict[str, Any] = {}
        if (timeout := options.get("timeout")) is not None:
            extra["timeout"] = timeout
        try:
            response = await self._client.request(
                method,
                url,
                params=params,
                headers=headers,
                json=json,
                data=data,
                files=files,
                **extra,
            )
        except self._httpx.RequestError as exc:
            msg = f"Request failed: {exc!s}"
            raise RequestError(msg) from exc
        return check_response(HttpResponse(response))

    async def get(self, url: str, **options: Unpack[RequestOptions]) -> HttpResponse:
        """Send a GET request."""
        return await self.request("GET", url, **options)

    async def post(
        self,
        url: str,
        *,
        json: Any = None,
        data: Any = None,
        files: FilesType | None = None,
        **options: Unpack[RequestOptions],
    ) -> HttpResponse:
        """Send a POST request."""
        return await self.request("POST", url, json=json, data=data, files=files, **options)

    async def get_text(self, url: str, **options: Unpack[RequestOptions]) -> str:
        """GET a URL and return the body as text."""
        return (await self.get(url, **options)).text

    async def get_bytes(self, url: str, **options: Unpack[RequestOptions]) -> bytes:
        """GET a URL and return the body as bytes."""
        return (await self.get(url, **options)).content

    async def get_json[T](
        self, url: str, *, return_type: type[T] | None = None, **options: Unpack[RequestOptions]
    ) -> T:
        """GET a URL and return the body parsed as JSON (validated if `return_type`)."""
        from anyenv.validate import validate_json_data

        return validate_json_data((await self.get(url, **options)).json(), return_type)

    async def post_json[T](
        self,
        url: str,
        json_data: Any,
        *,
        files: FilesType | None = None,
        return_type: type[T] | None = None,
        **options: Unpack[RequestOptions],
    ) -> T:
        """POST JSON (form data with `files`) and return the response parsed as JSON."""
        from anyenv.validate import validate_json_data

        if files:
            response = await self.post(url, data=json_data, files=files, **options)
        else:
            response = await self.post(url, json=json_data, **options)
        return validate_json_data(response.json(), return_type)

    async def download(
        self,
        url: str,
        path: StrPath,
        *,
        headers: HeaderType | None = None,
        progress_callback: ProgressCallback | None = None,
        timeout: float | None = None,
    ) -> None:
        """Stream a URL into a file (``<path>.part`` until complete)."""
        url = self.resolve(url)
        extra: dict[str, Any] = {} if timeout is None else {"timeout": timeout}
        try:
            async with self._client.stream(
                "GET", url, headers=self._headers_for(url, headers), **extra
            ) as response:
                if 400 <= response.status_code < 600:  # noqa: PLR2004
                    await response.aread()
                    message = f"HTTP Error {response.status_code}"
                    raise ResponseError(message, HttpResponse(response))
                total = int(response.headers.get("content-length", "0"))
                current = 0
                with open_download_target(path) as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)
                        current += len(chunk)
                        if progress_callback:
                            result = progress_callback(current, total)
                            if inspect.isawaitable(result):
                                await result
        except self._httpx.RequestError as exc:
            msg = f"Download failed: {exc!s}"
            raise RequestError(msg) from exc


@contextlib.asynccontextmanager
async def http_session(
    *,
    base_url: str | None = None,
    headers: HeaderType | None = None,
    cache: bool = False,
    cache_dir: StrPath | None = None,
    cache_ttl: int | str | None = None,
    cache_backend: CacheType = "file",
    timeout: float | None = None,
) -> AsyncGenerator[HttpSession]:
    """Open one HTTP client for many requests.

    While the block runs, the module-level helpers (``anyenv.get_json(...)`` etc.)
    in this context use the session too; leaving it restores the outer session (if
    any). Helper calls asking for other cache settings get a client of their own.

    Args:
        base_url: Prefix for relative URLs; the session's headers only go to it
        headers: Headers for every request (see `HttpSession`)
        cache: Cache responses (hishel; keyed by URL and credentials)
        cache_dir: Directory of the cache database (default: the user cache dir)
        cache_ttl: How long cached responses are used: seconds or e.g. "1h", "2d"
        cache_backend: "file" (an SQLite file in `cache_dir`, also "sqlite") or "memory"
        timeout: Default timeout per request in seconds (default: none)

    Example:
        ```python
        async with anyenv.http_session(base_url="https://api.github.com") as s:
            repo = await s.get_json("/repos/phil65/anyenv")
            user = await anyenv.get_json("https://api.github.com/users/phil65")
        ```
    """
    settings = CacheSettings.create(cache, cache_dir, cache_ttl, cache_backend)
    session = HttpSession(base_url=base_url, headers=headers, cache=settings, timeout=timeout)
    token = _current_session.set(session)
    try:
        async with session:
            yield session
    finally:
        _current_session.reset(token)


def current_session() -> HttpSession | None:
    """The innermost open `http_session` of this context and event loop, if any."""
    session = _current_session.get()
    return session if session is not None and session.usable_here() else None


@contextlib.asynccontextmanager
async def session_for(
    cache: bool | None = None,
    cache_dir: StrPath | None = None,
    cache_ttl: int | str | None = None,
    timeout: float | None = None,
) -> AsyncGenerator[HttpSession]:
    """The current session if it fits the cache options, else a client for one call."""
    session = current_session()
    if session is not None:
        if session.accepts(cache, cache_dir, cache_ttl):
            yield session
            return
        logger.debug("Cache options differ from the open http_session: using an own client")
    settings = CacheSettings.create(cache, cache_dir, cache_ttl)
    async with HttpSession(cache=settings, timeout=timeout) as own:
        yield own


async def without_session[T](coro: Any) -> T:
    """Await `coro` with no session in its context (for the ``*_sync`` helpers).

    They run on an event loop of their own, where a session's client can't be used.
    """
    token = _current_session.set(None)
    try:
        return await coro  # type: ignore[no-any-return]
    finally:
        _current_session.reset(token)


__all__ = ["HttpSession", "current_session", "http_session"]
