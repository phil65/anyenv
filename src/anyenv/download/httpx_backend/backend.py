"""HTTPX backend implementation for anyenv."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from anyenv.download.base import HttpBackend, HttpResponse, Session, open_download_target
from anyenv.download.exceptions import RequestError, ResponseError, check_response
from anyenv.download.httpx_backend.module import HTTPX_MODULE_NAMES, get_httpx_module


if TYPE_CHECKING:
    import builtins
    import os
    from types import ModuleType

    import hishel
    import httpx2 as httpx

    from anyenv.download.base import Method, ProgressCallback, StrPath
    from anyenv.download.http_types import CacheType, FilesType, HeaderType, ParamsType


# Versioned name: hishel 2 refuses to open databases created by hishel 1.x.
CACHE_DB_NAME = "anyenv_cache_hishel2.db"


def get_storage(
    cache_backend: CacheType,
    cache_dir: StrPath,
    cache_ttl: int,
) -> hishel.AsyncSqliteStorage:
    """Get storage backend."""
    import hishel

    match cache_backend:
        case "sqlite" | "file":
            cache_path = Path(cache_dir) / CACHE_DB_NAME
            return hishel.AsyncSqliteStorage(database_path=str(cache_path), default_ttl=cache_ttl)
        case "memory":
            return hishel.AsyncSqliteStorage(database_path=":memory:", default_ttl=cache_ttl)
        case _:
            msg = f"Invalid cache backend: {cache_backend}"
            raise ValueError(msg)


class HttpxResponse(HttpResponse):
    """HTTPX implementation of HTTP response."""

    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    @property
    def status_code(self) -> int:
        """Status code of the response."""
        return self._response.status_code

    @property
    def reason(self) -> str:
        """Status code of the response."""
        return self._response.reason_phrase

    @property
    def url(self) -> str:
        """URL of the response."""
        return str(self._response.url)

    @property
    def headers(self) -> dict[str, str]:
        """Headers of the response."""
        return dict(self._response.headers)

    async def text(self) -> str:
        """Text content of the response."""
        return self._response.text

    async def json(self) -> Any:
        """JSON content of the response."""
        from anyenv import load_json

        return load_json(self._response.content)

    async def bytes(self) -> builtins.bytes:
        """Bytes content of the response."""
        return self._response.content


def _module_of_client(client: Any) -> ModuleType:
    """Return the httpx flavour module a client instance belongs to."""
    for klass in type(client).__mro__:
        root = klass.__module__.partition(".")[0]
        if root in HTTPX_MODULE_NAMES:
            return importlib.import_module(root)
    return get_httpx_module()


class HttpxSession(Session):
    """HTTPX implementation of HTTP session."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str | None = None,
        httpx_module: ModuleType | None = None,
    ) -> None:
        self._client = client
        self._base_url = base_url
        self._httpx = httpx_module or _module_of_client(client)

    async def request(
        self,
        method: Method,
        url: str,
        *,
        params: ParamsType | None = None,
        headers: HeaderType | None = None,
        json: Any = None,
        data: Any = None,
        files: FilesType | None = None,
        timeout: float | None = None,
        cache: bool | None = None,
    ) -> HttpResponse:
        """Request implementation using HTTPX."""
        httpx = self._httpx

        if self._base_url:
            url = f"{self._base_url.rstrip('/')}/{url.lstrip('/')}"

        try:
            request_headers = dict(headers or {})

            # Only modify caching behavior if explicitly specified
            if cache is False:
                # Add cache control header to disable caching for this request
                request_headers["Cache-Control"] = "no-store"
            elif cache is True:
                # Force caching for this request
                request_headers["Cache-Control"] = "max-age=3600"

            response = await self._client.request(
                method,
                url,
                params=params,
                headers=request_headers,
                json=json,
                data=data,
                files=files,
                timeout=timeout if timeout else None,
            )
            httpx_response = HttpxResponse(response)
        except httpx.RequestError as exc:
            error_msg = f"Request failed: {exc!s}"
            raise RequestError(error_msg) from exc

        return check_response(httpx_response)

    async def close(self) -> None:
        """Close the HTTPX client."""
        await self._client.aclose()


class HttpxBackend(HttpBackend):
    """HTTPX implementation of HTTP backend.

    Subclasses can target an API-compatible fork (e.g. httpx2) by overriding
    the module names below.
    """

    httpx_module_name: ClassVar[str] = "httpx"
    hishel_module_name: ClassVar[str] = "hishel.httpx"

    @property
    def _httpx(self) -> ModuleType:
        return importlib.import_module(self.httpx_module_name)

    def _create_client(
        self,
        cache: bool = False,
        base_url: str | None = None,
        headers: HeaderType | None = None,
        cache_backend: CacheType = "file",
    ) -> httpx.AsyncClient:
        """Create an HTTPX client."""
        httpx = self._httpx
        url = base_url or ""
        if cache:
            from anyenv.download.httpx_backend.cache import get_cache_client_class

            storage = get_storage(cache_backend, self.cache_dir, self.cache_ttl)
            # Cached responses expire after the backend's cache_ttl, regardless of
            # the server's Cache-Control headers (many APIs send max-age=0).
            # Bodies are stored decoded, and unusable entries are refetched.
            client_cls = get_cache_client_class(self.httpx_module_name, self.hishel_module_name)
            return client_cls(
                storage=storage,
                ttl=self.cache_ttl,
                headers=headers,
                base_url=url,
                follow_redirects=True,
            )
        # Follow redirects like the aiohttp and pyodide backends do.
        return httpx.AsyncClient(headers=headers, base_url=url, follow_redirects=True)

    async def request(
        self,
        method: Method,
        url: str,
        *,
        params: ParamsType | None = None,
        headers: HeaderType | None = None,
        json: Any = None,
        data: Any = None,
        files: FilesType | None = None,
        timeout: float | None = None,
        cache: bool = False,
        cache_backend: CacheType = "file",
    ) -> HttpResponse:
        """Request implementation using httpx."""
        httpx = self._httpx

        try:
            async with self._create_client(cache=cache, cache_backend=cache_backend) as client:
                response = await client.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    json=json,
                    data=data,
                    files=files,
                    timeout=timeout if timeout else None,
                )
                httpx_response = HttpxResponse(response)
        except httpx.RequestError as exc:
            error_msg = f"Request failed: {exc!s}"
            raise RequestError(error_msg) from exc

        # Outside the exception handler for request errors
        return check_response(httpx_response)

    async def download(
        self,
        url: str,
        path: str | os.PathLike[str],
        *,
        headers: HeaderType | None = None,
        progress_callback: ProgressCallback | None = None,
        cache: bool = False,
        cache_backend: CacheType = "file",
    ) -> None:
        """Download implementation using HTTPX."""
        httpx = self._httpx

        try:
            async with self._create_client(  # noqa: SIM117
                cache=cache, cache_backend=cache_backend
            ) as client:
                async with client.stream("GET", url, headers=headers) as response:
                    # Check for HTTP errors instead of using raise_for_status()
                    if 400 <= response.status_code < 600:  # noqa: PLR2004
                        message = f"HTTP Error {response.status_code}"
                        raise ResponseError(message, HttpxResponse(response))

                    total = int(response.headers.get("content-length", "0"))
                    current = 0

                    with open_download_target(path) as f:
                        async for chunk in response.aiter_bytes():
                            f.write(chunk)
                            current += len(chunk)
                            if progress_callback:
                                await self._handle_callback(progress_callback, current, total)
        except httpx.TransportError as exc:
            error_msg = f"Download failed: {exc!s}"
            raise RequestError(error_msg) from exc
        except httpx.RequestError as exc:
            error_msg = f"Download error: {exc!s}"
            raise RequestError(error_msg) from exc

    async def create_session(
        self,
        *,
        base_url: str | None = None,
        headers: HeaderType | None = None,
        cache: bool = False,
        cache_backend: CacheType = "file",
    ) -> Session:
        """Create a new HTTPX session."""
        client = self._create_client(
            cache=cache,
            base_url=base_url,
            headers=headers,
            cache_backend=cache_backend,
        )
        return HttpxSession(client, base_url, self._httpx)


class Httpx2Backend(HttpxBackend):
    """httpx2 (pydantic's httpx fork) implementation of HTTP backend."""

    httpx_module_name: ClassVar[str] = "httpx2"
    hishel_module_name: ClassVar[str] = "hishel.httpx2"


if __name__ == "__main__":

    async def main() -> None:
        """Test the HTTPX backend."""
        backend = HttpxBackend()
        path = Path.cwd() / "file.zip"
        url = "http://speedtest.tele2.net/10MB.zip"
        await backend.download(url=url, path=path, headers={"User-Agent": "anyenv"})

    import anyio

    anyio.run(main)
