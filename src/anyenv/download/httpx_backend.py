"""HTTPX backend implementation for anyenv."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import hishel
import httpx

from anyenv.download.base import (
    HttpBackend,
    HttpResponse,
    Method,
    ProgressCallback,
    Session,
)
from anyenv.download.exceptions import RequestError, check_response


try:
    from upath import UPath as Path
except ImportError:
    from pathlib import Path  # type: ignore[assignment]

if TYPE_CHECKING:
    import os


class HttpxResponse(HttpResponse):
    """HTTPX implementation of HTTP response."""

    def __init__(self, response: httpx.Response):
        self._response = response

    @property
    def status_code(self) -> int:
        return self._response.status_code

    @property
    def headers(self) -> dict[str, str]:
        return dict(self._response.headers)

    async def text(self) -> str:
        return self._response.text

    async def json(self) -> Any:
        from anyenv.json_tools import loading

        return loading.load_json(self._response.content)

    async def bytes(self) -> bytes:
        return self._response.content


class HttpxSession(Session):
    """HTTPX implementation of HTTP session."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str | None = None,
    ):
        self._client = client
        self._base_url = base_url

    async def request(
        self,
        method: Method,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        json: Any = None,
        data: Any = None,
        timeout: float | None = None,
        cache: bool = False,
    ) -> HttpResponse:
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
                timeout=timeout if timeout else None,
            )
            httpx_response = HttpxResponse(response)
        except httpx.RequestError as exc:
            error_msg = f"Request failed: {exc!s}"
            raise RequestError(error_msg) from exc

        return check_response(httpx_response)

    async def close(self):
        await self._client.aclose()


class HttpxBackend(HttpBackend):
    """HTTPX implementation of HTTP backend."""

    def _create_client(
        self,
        cache: bool = False,
        base_url: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.AsyncClient:
        url = base_url or ""
        if cache:
            from anyenv.download.httpx_serializer import AnyEnvSerializer

            storage = hishel.AsyncFileStorage(
                serializer=AnyEnvSerializer(),
                base_path=self.cache_dir,
                ttl=self.cache_ttl,
            )
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
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        json: Any = None,
        data: Any = None,
        timeout: float | None = None,
        cache: bool = False,
    ) -> HttpResponse:
        try:
            async with self._create_client(cache=cache) as client:
                response = await client.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    json=json,
                    data=data,
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
        headers: dict[str, str] | None = None,
        progress_callback: ProgressCallback | None = None,
        cache: bool = False,
    ):
        from anyenv.download.exceptions import RequestError, ResponseError

        try:
            async with self._create_client(cache=cache) as client:  # noqa: SIM117
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
        headers: dict[str, str] | None = None,
        cache: bool = False,
    ) -> Session:
        client = self._create_client(
            cache=cache,
            base_url=base_url,
            headers=headers,
        )
        return HttpxSession(client, base_url)


if __name__ == "__main__":

    async def main():
        backend = HttpxBackend()
        await backend.download(
            url="http://speedtest.tele2.net/10MB.zip",
            path=Path.cwd() / "file.zip",
            headers={"User-Agent": "anyenv"},
        )

    import anyio

    anyio.run(main)
