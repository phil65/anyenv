"""High-level interface for HTTP requests and downloads."""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING, Any, Literal, TypeVar


if TYPE_CHECKING:
    import os

    from anyenv.download.base import HttpBackend, HttpResponse, Method, ProgressCallback


T = TypeVar("T")
BackendType = Literal["httpx", "aiohttp", "pyodide"]


def _get_default_backend() -> HttpBackend:
    """Get the best available HTTP backend."""
    # Try httpx first
    if importlib.util.find_spec("httpx") and importlib.util.find_spec("hishel"):
        from anyenv.download.httpx_backend import HttpxBackend

        return HttpxBackend()

    # Try aiohttp next
    if importlib.util.find_spec("aiohttp") and importlib.util.find_spec(
        "aiohttp_client_cache"
    ):
        from anyenv.download.aiohttp_backend import AiohttpBackend

        return AiohttpBackend()

    # Fall back to pyodide if in browser environment
    if importlib.util.find_spec("pyodide"):
        from anyenv.download.pyodide_backend import PyodideBackend

        return PyodideBackend()

    # If none are available, raise an error
    msg = (
        "No HTTP backend available. Please install one of: "
        "httpx+hishel, aiohttp+aiohttp_client_cache"
    )
    raise ImportError(msg)


def get_backend(backend_type: BackendType | None = None) -> HttpBackend:
    """Get a specific HTTP backend or the best available one.

    Args:
        backend_type: Optional backend type to use. If None, uses the best available.

    Returns:
        An instance of the selected HTTP backend.

    Raises:
        ImportError: If the requested backend is not available.
    """
    if backend_type is None:
        return _get_default_backend()

    if backend_type == "httpx":
        if importlib.util.find_spec("httpx") and importlib.util.find_spec("hishel"):
            from anyenv.download.httpx_backend import HttpxBackend

            return HttpxBackend()
        msg = "httpx backend requested but httpx or hishel not installed"
        raise ImportError(msg)

    if backend_type == "aiohttp":
        if importlib.util.find_spec("aiohttp") and importlib.util.find_spec(
            "aiohttp_client_cache"
        ):
            from anyenv.download.aiohttp_backend import AiohttpBackend

            return AiohttpBackend()
        msg = (
            "aiohttp backend requested but aiohttp or aiohttp_client_cache not installed"
        )
        raise ImportError(msg)

    if backend_type == "pyodide":
        if importlib.util.find_spec("pyodide"):
            from anyenv.download.pyodide_backend import PyodideBackend

            return PyodideBackend()
        msg = "pyodide backend requested but pyodide not installed"
        raise ImportError(msg)

    msg = f"Unknown backend type: {backend_type}"
    raise ValueError(msg)


# High-level API functions


async def request(
    method: Method,
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    json: Any = None,
    data: Any = None,
    timeout: float | None = None,
    cache: bool = False,
    backend: BackendType | None = None,
) -> HttpResponse:
    """Make an HTTP request.

    Args:
        method: HTTP method to use
        url: URL to request
        params: Optional query parameters
        headers: Optional request headers
        json: Optional JSON body
        data: Optional request body
        timeout: Optional request timeout in seconds
        cache: Whether to use cached responses
        backend: Optional specific backend to use

    Returns:
        An HttpResponse object
    """
    http_backend = get_backend(backend)
    return await http_backend.request(
        method,
        url,
        params=params,
        headers=headers,
        json=json,
        data=data,
        timeout=timeout,
        cache=cache,
    )


async def get(
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
    cache: bool = False,
    backend: BackendType | None = None,
) -> HttpResponse:
    """Make a GET request.

    Args:
        url: URL to request
        params: Optional query parameters
        headers: Optional request headers
        timeout: Optional request timeout in seconds
        cache: Whether to use cached responses
        backend: Optional specific backend to use

    Returns:
        An HttpResponse object
    """
    return await request(
        "GET",
        url,
        params=params,
        headers=headers,
        timeout=timeout,
        cache=cache,
        backend=backend,
    )


async def post(
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    json: Any = None,
    data: Any = None,
    timeout: float | None = None,
    cache: bool = False,
    backend: BackendType | None = None,
) -> HttpResponse:
    """Make a POST request.

    Args:
        url: URL to request
        params: Optional query parameters
        headers: Optional request headers
        json: Optional JSON body
        data: Optional request body
        timeout: Optional request timeout in seconds
        cache: Whether to use cached responses
        backend: Optional specific backend to use

    Returns:
        An HttpResponse object
    """
    return await request(
        "POST",
        url,
        params=params,
        headers=headers,
        json=json,
        data=data,
        timeout=timeout,
        cache=cache,
        backend=backend,
    )


async def download(
    url: str,
    path: str | os.PathLike[str],
    *,
    headers: dict[str, str] | None = None,
    progress_callback: ProgressCallback | None = None,
    cache: bool = False,
    backend: BackendType | None = None,
) -> None:
    """Download a file with optional progress reporting.

    Args:
        url: URL to download
        path: Path where to save the file
        headers: Optional request headers
        progress_callback: Optional callback for progress reporting
        cache: Whether to use cached responses
        backend: Optional specific backend to use
    """
    http_backend = get_backend(backend)
    await http_backend.download(
        url,
        path,
        headers=headers,
        progress_callback=progress_callback,
        cache=cache,
    )


# Convenience methods for direct data retrieval


async def get_text(
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
    cache: bool = False,
    backend: BackendType | None = None,
) -> str:
    """Make a GET request and return the response text.

    Args:
        url: URL to request
        params: Optional query parameters
        headers: Optional request headers
        timeout: Optional request timeout in seconds
        cache: Whether to use cached responses
        backend: Optional specific backend to use

    Returns:
        The response body as text
    """
    response = await get(
        url, params=params, headers=headers, timeout=timeout, cache=cache, backend=backend
    )
    return await response.text()


async def get_json(
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
    cache: bool = False,
    backend: BackendType | None = None,
) -> Any:
    """Make a GET request and return the response as JSON.

    Args:
        url: URL to request
        params: Optional query parameters
        headers: Optional request headers
        timeout: Optional request timeout in seconds
        cache: Whether to use cached responses
        backend: Optional specific backend to use

    Returns:
        The response body parsed as JSON
    """
    response = await get(
        url, params=params, headers=headers, timeout=timeout, cache=cache, backend=backend
    )
    return await response.json()


async def get_bytes(
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
    cache: bool = False,
    backend: BackendType | None = None,
) -> bytes:
    """Make a GET request and return the response as bytes.

    Args:
        url: URL to request
        params: Optional query parameters
        headers: Optional request headers
        timeout: Optional request timeout in seconds
        cache: Whether to use cached responses
        backend: Optional specific backend to use

    Returns:
        The response body as bytes
    """
    response = await get(
        url, params=params, headers=headers, timeout=timeout, cache=cache, backend=backend
    )
    return await response.bytes()


# Synchronous versions of the API functions


def request_sync(
    method: Method,
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    json: Any = None,
    data: Any = None,
    timeout: float | None = None,
    cache: bool = False,
    backend: BackendType | None = None,
) -> HttpResponse:
    """Synchronous version of request."""
    http_backend = get_backend(backend)
    return http_backend.request_sync(
        method,
        url,
        params=params,
        headers=headers,
        json=json,
        data=data,
        timeout=timeout,
        cache=cache,
    )


def get_sync(
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
    cache: bool = False,
    backend: BackendType | None = None,
) -> HttpResponse:
    """Synchronous version of get."""
    return request_sync(
        "GET",
        url,
        params=params,
        headers=headers,
        timeout=timeout,
        cache=cache,
        backend=backend,
    )


def post_sync(
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    json: Any = None,
    data: Any = None,
    timeout: float | None = None,
    cache: bool = False,
    backend: BackendType | None = None,
) -> HttpResponse:
    """Synchronous version of post."""
    return request_sync(
        "POST",
        url,
        params=params,
        headers=headers,
        json=json,
        data=data,
        timeout=timeout,
        cache=cache,
        backend=backend,
    )


def download_sync(
    url: str,
    path: str | os.PathLike[str],
    *,
    headers: dict[str, str] | None = None,
    progress_callback: ProgressCallback | None = None,
    cache: bool = False,
    backend: BackendType | None = None,
) -> None:
    """Synchronous version of download."""
    http_backend = get_backend(backend)
    http_backend.download_sync(
        url,
        path,
        headers=headers,
        progress_callback=progress_callback,
        cache=cache,
    )


def get_text_sync(
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
    cache: bool = False,
    backend: BackendType | None = None,
) -> str:
    """Synchronous version of get_text."""
    from anyenv.async_run import run_sync

    return run_sync(
        get_text(
            url,
            params=params,
            headers=headers,
            timeout=timeout,
            cache=cache,
            backend=backend,
        )
    )


def get_json_sync(
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
    cache: bool = False,
    backend: BackendType | None = None,
) -> Any:
    """Synchronous version of get_json."""
    from anyenv.async_run import run_sync

    return run_sync(
        get_json(
            url,
            params=params,
            headers=headers,
            timeout=timeout,
            cache=cache,
            backend=backend,
        )
    )


def get_bytes_sync(
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
    cache: bool = False,
    backend: BackendType | None = None,
) -> bytes:
    """Synchronous version of get_bytes."""
    from anyenv.async_run import run_sync

    return run_sync(
        get_bytes(
            url,
            params=params,
            headers=headers,
            timeout=timeout,
            cache=cache,
            backend=backend,
        )
    )
