"""Pyodide backend implementation for anyenv."""

from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

from anyenv.download.base import HttpBackend, HttpResponse, Session
from anyenv.download.exceptions import RequestError, ResponseError, check_response


if TYPE_CHECKING:
    import os

    from pyodide.http import FetchResponse  # pyright:ignore[reportMissingImports]

    from anyenv.download.base import Method, ProgressCallback
    from anyenv.download.http_types import CacheType, FilesType, HeaderType, ParamsType


class PyodideResponse(HttpResponse):
    """Pyodide implementation of HTTP response."""

    def __init__(self, response: FetchResponse) -> None:
        self._response = response

    @property
    def status_code(self) -> int:
        """Status code implementation for PyodideResponse."""
        return self._response.status

    @property
    def reason(self) -> str:
        """Status code of the response."""
        # TODO
        return ""

    @property
    def url(self) -> str:
        """URL of the response."""
        return self._response.url

    @property
    def headers(self) -> dict[str, str]:
        """Headers implementation for PyodideResponse."""
        return dict(self._response.headers)

    async def text(self) -> str:
        """Text implementation for PyodideResponse."""
        return await self._response.text()

    async def json(self) -> Any:
        """JSON implementation for PyodideResponse."""
        from anyenv import load_json

        return await load_json(self._response)

    async def bytes(self) -> bytes:
        """Bytes implementation for PyodideResponse."""
        return await self._response.bytes()


class PyodideSession(Session):
    """Pyodide implementation of HTTP session.

    Note: In Pyodide/browser environment, we can't maintain persistent connections.
    Each request is independent, but we maintain consistent headers and base URL.
    """

    def __init__(
        self, base_url: str | None = None, headers: HeaderType | None = None
    ) -> None:
        self._base_url = base_url
        self._headers = headers or {}

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
        """Make a request using Pyodide's fetch."""
        from js import Array, Blob, FormData  # pyright: ignore
        from pyodide.http import pyfetch  # pyright:ignore[reportMissingImports]

        from anyenv import dump_json

        request_headers = self._headers.copy()
        if headers:
            request_headers.update(headers)

        if self._base_url:
            url = urljoin(self._base_url, url)

        options: dict[str, Any] = {
            "method": method,
            "headers": request_headers,
            "mode": "cors",
        }

        # Handle files using FormData
        if files:
            form_data = FormData.new()

            # Add regular form data if any
            if isinstance(data, dict):
                for key, value in data.items():
                    form_data.append(key, str(value))

            # Add files
            for field_name, file_info in files.items():
                match file_info:
                    case str() as content:
                        form_data.append(field_name, content)
                    case bytes() as content:
                        blob = Blob.new([Array.from_buffer(content)])
                        form_data.append(field_name, blob)
                    case tuple([filename, str() as content]):
                        form_data.append(field_name, content, filename)
                    case tuple([filename, bytes() as content]):
                        blob = Blob.new([Array.from_buffer(content)])
                        form_data.append(field_name, blob, filename)
                    case tuple([filename, str() as content, content_type]):
                        form_data.append(field_name, content, filename)
                    case tuple([filename, bytes() as content, content_type]):
                        blob = Blob.new(
                            [Array.from_buffer(content)], {"type": content_type}
                        )
                        form_data.append(field_name, blob, filename)

            options["body"] = form_data
        # Handle regular data
        elif json is not None:
            options["body"] = dump_json(json)
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

    async def close(self) -> None:
        """No-op in Pyodide as there's no persistent connection."""


class PyodideBackend(HttpBackend):
    """Pyodide implementation of HTTP backend."""

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
        """Request implementation for Pyodide."""
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
                files=files,
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
        headers: HeaderType | None = None,
        progress_callback: ProgressCallback | None = None,
        cache: bool = False,
        cache_backend: CacheType = "file",
    ) -> None:
        """Download implementation for Pyodide."""
        from pyodide.http import pyfetch  # pyright:ignore[reportMissingImports]

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
        headers: HeaderType | None = None,
        cache: bool = False,
        cache_backend: CacheType = "file",
    ) -> Session:
        """Create Pyodide Session."""
        return PyodideSession(base_url=base_url, headers=headers)
