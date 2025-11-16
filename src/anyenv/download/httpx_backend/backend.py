"""HTTPX backend implementation for anyenv."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from anyenv.download.base import HttpBackend, HttpResponse, Session
from anyenv.download.exceptions import RequestError, ResponseError, check_response


if TYPE_CHECKING:
    import os

    import hishel
    import httpx

    from anyenv.download.base import Method, ProgressCallback, StrPath
    from anyenv.download.http_types import CacheType, FilesType, HeaderType, ParamsType


def get_storage(
    cache_backend: CacheType,
    cache_dir: StrPath,
    cache_ttl: int,
) -> hishel.AsyncBaseStorage:
    """Get storage backend."""
    import hishel

    match cache_backend:
        case "sqlite":
            return hishel.AsyncSqliteStorage(
                database_path="anyenv_cache.db",
                default_ttl=cache_ttl,
                refresh_ttl_on_access=True,
            )
        case "memory":
            # Use sqlite storage with in-memory database as fallback
            # since hishel 1.0 doesn't have AsyncInMemoryStorage
            return hishel.AsyncSqliteStorage(
                database_path=":memory:",
                default_ttl=cache_ttl,
                refresh_ttl_on_access=True,
            )
        case "file":
            # Use sqlite storage with file path
            cache_path = Path(cache_dir) / "anyenv_cache.db"
            return hishel.AsyncSqliteStorage(
                database_path=str(cache_path),
                default_ttl=cache_ttl,
                refresh_ttl_on_access=True,
            )
        case _:
            msg = f"Invalid cache backend: {cache_backend}"
            raise ValueError(msg)


def get_cache_policy() -> hishel.CachePolicy:
    """Get cache policy for HTTP caching."""
    import hishel

    # Use SpecificationPolicy for RFC 9111 compliant caching
    cache_options = hishel.CacheOptions(
        shared=False,  # Private cache (browser-like)
        supported_methods=["GET", "HEAD"],  # Only cache safe methods
        allow_stale=True,  # Allow serving stale responses
    )

    return hishel.SpecificationPolicy(cache_options=cache_options)


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

    async def bytes(self) -> bytes:
        """Bytes content of the response."""
        return self._response.content


class HttpxSession(Session):
    """HTTPX implementation of HTTP session."""

    def __init__(self, client: httpx.AsyncClient, base_url: str | None = None) -> None:
        self._client = client
        self._base_url = base_url

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
        import httpx

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
    """HTTPX implementation of HTTP backend."""

    def _create_client(
        self,
        cache: bool = False,
        base_url: str | None = None,
        headers: HeaderType | None = None,
        cache_backend: CacheType = "file",
    ) -> httpx.AsyncClient:
        """Create an HTTPX client."""
        from hishel.httpx import AsyncCacheClient
        import httpx

        url = base_url or ""
        if cache:
            storage = get_storage(cache_backend, self.cache_dir, self.cache_ttl)
            policy = get_cache_policy()

            # Create the cached client directly using hishel's AsyncCacheClient
            return AsyncCacheClient(
                storage=storage,
                policy=policy,
                headers=headers,
                base_url=url,
            )
        return httpx.AsyncClient(headers=headers, base_url=url)

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
        import httpx

        try:
            async with self._create_client(
                cache=cache, cache_backend=cache_backend
            ) as client:
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
        import httpx

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

                    with Path(path).open("wb") as f:
                        async for chunk in response.aiter_bytes():
                            f.write(chunk)
                            current += len(chunk)
                            if progress_callback:
                                await self._handle_callback(
                                    progress_callback, current, total
                                )
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
        return HttpxSession(client, base_url)


if __name__ == "__main__":

    async def main() -> None:
        """Test the HTTPX backend."""
        backend = HttpxBackend()
        await backend.download(
            url="http://speedtest.tele2.net/10MB.zip",
            path=Path.cwd() / "file.zip",
            headers={"User-Agent": "anyenv"},
        )

    import anyio

    anyio.run(main)
