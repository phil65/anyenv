"""HTTPX backend implementation for anyenv."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from anyenv.anypath import Path
from anyenv.download.base import (
    HttpBackend,
    HttpResponse,
    Method,
    ProgressCallback,
    Session,
)
from anyenv.download.exceptions import RequestError, check_response


if TYPE_CHECKING:
    import os

    import httpx

    from anyenv.download.http_types import CacheType, FilesType, HeaderType, ParamsType


class HttpxResponse(HttpResponse):
    """HTTPX implementation of HTTP response."""

    def __init__(self, response: httpx.Response):
        self._response = response

    @property
    def status_code(self) -> int:
        """Status code of the response."""
        return self._response.status_code

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

    def __init__(self, client: httpx.AsyncClient, base_url: str | None = None):
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
        cache: bool = False,
    ) -> HttpResponse:
        """Request implementation using HTTPX."""
        import httpx

        if self._base_url:
            url = f"{self._base_url.rstrip('/')}/{url.lstrip('/')}"

        try:
            response = await self._client.request(
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

        return check_response(httpx_response)

    async def close(self):
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
        import hishel
        import httpx

        url = base_url or ""
        if cache:
            from anyenv.download.httpx_backend.serializer import AnyEnvSerializer

            match cache_backend:
                case "sqlite":
                    storage: hishel.AsyncBaseStorage = hishel.AsyncSQLiteStorage(
                        serializer=AnyEnvSerializer(),
                        connection=...,
                        ttl=self.cache_ttl,
                    )
                case "file":
                    storage = hishel.AsyncFileStorage(
                        serializer=AnyEnvSerializer(),
                        base_path=self.cache_dir,
                        ttl=self.cache_ttl,
                    )
                case "memory":
                    storage = hishel.AsyncInMemoryStorage(
                        serializer=AnyEnvSerializer(),
                        ttl=self.cache_ttl,
                    )
                case _:
                    msg = f"Invalid cache backend: {cache_backend}"
                    raise ValueError(msg)

            ctl = hishel.Controller(
                cacheable_methods=["GET"],
                cacheable_status_codes=[200],
                allow_stale=True,
            )
            tp = httpx.AsyncHTTPTransport()
            transport = hishel.AsyncCacheTransport(tp, storage=storage, controller=ctl)
            return httpx.AsyncClient(transport=transport, headers=headers, base_url=url)
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
    ):
        """Download implementation using HTTPX."""
        import httpx

        from anyenv.download.exceptions import RequestError, ResponseError

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

    async def main():
        """Test the HTTPX backend."""
        backend = HttpxBackend()
        await backend.download(
            url="http://speedtest.tele2.net/10MB.zip",
            path=Path.cwd() / "file.zip",
            headers={"User-Agent": "anyenv"},
        )

    import anyio

    anyio.run(main)
