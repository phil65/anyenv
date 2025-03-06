"""Pyodide backend implementation for anyenv."""

from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

from anyenv.download.base import (
    HttpBackend,
    HttpResponse,
    Method,
    ProgressCallback,
    Session,
)


if TYPE_CHECKING:
    import os

    from pyodide.http import FetchResponse  # pyright:ignore[reportMissingImports]


class PyodideResponse(HttpResponse):
    """Pyodide implementation of HTTP response."""

    def __init__(self, response: FetchResponse):
        self._response = response

    @property
    def status_code(self) -> int:
        return self._response.status

    @property
    def headers(self) -> dict[str, str]:
        return dict(self._response.headers)

    async def text(self) -> str:
        return await self._response.string()

    async def json(self) -> Any:
        return await self._response.json()

    async def bytes(self) -> bytes:
        return await self._response.bytes()


class PyodideSession(Session):
    """Pyodide implementation of HTTP session.

    Note: In Pyodide/browser environment, we can't maintain persistent connections.
    Each request is independent, but we maintain consistent headers and base URL.
    """

    def __init__(
        self,
        base_url: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        self._base_url = base_url
        self._headers = headers or {}

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
        # Merge session headers with request headers
        from pyodide.http import pyfetch  # pyright:ignore[reportMissingImports]

        from anyenv.download.exceptions import RequestError, check_response
        from anyenv.json_tools import dumping

        request_headers = self._headers.copy()
        if headers:
            request_headers.update(headers)

        # Handle base URL
        if self._base_url:
            url = urljoin(self._base_url, url)

        # Prepare request options
        options: dict[str, Any] = {
            "method": method,
            "headers": request_headers,
            "mode": "cors",
        }

        # Handle body data
        if json is not None:
            options["body"] = dumping.dump_json(json)
            request_headers["Content-Type"] = "application/json"
        elif data is not None:
            options["body"] = data

        options["cache"] = "force-cache" if cache else "no-store"

        try:
            response = await pyfetch(url, **options)
            pyodide_response = PyodideResponse(response)
        except Exception as exc:
            # Pyodide might throw different error types, so we catch a general Exception
            error_msg = f"Request failed: {exc!s}"
            raise RequestError(error_msg) from exc

        # Check for HTTP status errors
        return check_response(pyodide_response)

    async def close(self):
        """No-op in Pyodide as there's no persistent connection."""


class PyodideBackend(HttpBackend):
    """Pyodide implementation of HTTP backend."""

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
        from anyenv.download.exceptions import RequestError, check_response

        try:
            session = PyodideSession()
            response = await session.request(
                method,
                url,
                params=params,
                headers=headers,
                json=json,
                data=data,
                timeout=timeout,
                cache=cache,
            )
        except RequestError:
            # Re-raise existing RequestErrors without wrapping
            raise
        except Exception as exc:
            # Catch any other exceptions
            error_msg = f"Request failed: {exc!s}"
            raise RequestError(error_msg) from exc

        # Check for HTTP status errors (although session.request should have done this)
        return check_response(response)

    async def download(
        self,
        url: str,
        path: str | os.PathLike[str],
        *,
        headers: dict[str, str] | None = None,
        progress_callback: ProgressCallback | None = None,
        cache: bool = False,
    ):
        from pyodide.http import pyfetch  # pyright:ignore[reportMissingImports]

        from anyenv.download.exceptions import RequestError, ResponseError

        try:
            # In browser environment, we need to get the full response first
            response = await pyfetch(
                url,
                headers=headers,
                cache="force-cache" if cache else "no-store",
            )

            # Check for HTTP errors
            if 400 <= response.status < 600:  # noqa: PLR2004
                pyodide_response = PyodideResponse(response)
                message = f"HTTP Error {response.status}"
                raise ResponseError(message, pyodide_response)  # noqa: TRY301

            content = await response.bytes()
            total = len(content)

            # Write to file and handle progress
            with pathlib.Path(path).open("wb") as f:
                if progress_callback:
                    await self._handle_callback(progress_callback, 0, total)
                f.write(content)
                if progress_callback:
                    await self._handle_callback(progress_callback, total, total)

        except ResponseError:
            # Re-raise ResponseErrors
            raise
        except Exception as exc:
            # Catch any other exceptions
            error_msg = f"Download failed: {exc!s}"
            raise RequestError(error_msg) from exc

    async def create_session(
        self,
        *,
        base_url: str | None = None,
        headers: dict[str, str] | None = None,
        cache: bool = False,
    ) -> Session:
        return PyodideSession(base_url=base_url, headers=headers)
