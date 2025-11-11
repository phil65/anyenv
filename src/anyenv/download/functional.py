"""High-level interface for HTTP requests and downloads."""

from __future__ import annotations

import base64
import importlib.util
import os
from typing import TYPE_CHECKING, Any, Unpack, assert_never

from anyenv.download.http_types import SecretStr


StrPath = str | os.PathLike[str]


if TYPE_CHECKING:
    from anyenv.download.base import (
        BackendType,
        DataRetrievalOptions,
        HttpBackend,
        HttpResponse,
        Method,
        ProgressCallback,
    )
    from anyenv.download.http_types import AuthType, FilesType, HeaderType, ParamsType


def get_default_backend() -> HttpBackend:
    """Get the best available HTTP backend."""
    if importlib.util.find_spec("httpx"):
        from anyenv.download.httpx_backend import HttpxBackend

        return HttpxBackend()

    # Try aiohttp next
    if importlib.util.find_spec("aiohttp"):
        from anyenv.download.aiohttp_backend import AiohttpBackend

        return AiohttpBackend()

    # Fall back to pyodide if in browser environment
    if importlib.util.find_spec("pyodide"):
        from anyenv.download.pyodide_backend import PyodideBackend

        return PyodideBackend()

    msg = (
        "No HTTP backend available. Please install one of: "
        "httpx+hishel, aiohttp+aiohttp_client_cache"
    )
    raise ImportError(msg)


def get_backend(
    backend_type: BackendType | None = None,
    cache_dir: StrPath | None = None,
    cache_ttl: int | str | None = None,
) -> HttpBackend:
    """Get a specific HTTP backend or the best available one.

    Args:
        backend_type: Optional backend type to use. If None, uses the best available.
        cache_dir: Optional path to use for caching. If None, uses a default path.
        cache_ttl: Optional TTL for cached responses. If None, uses a default TTL.

    Returns:
        An instance of the selected HTTP backend.

    Raises:
        ImportError: If the requested backend is not available.
    """
    if backend_type is None:
        return get_default_backend()

    if backend_type == "httpx":
        if importlib.util.find_spec("httpx") and importlib.util.find_spec("hishel"):
            from anyenv.download.httpx_backend import HttpxBackend

            return HttpxBackend(cache_dir=cache_dir, cache_ttl=cache_ttl)
        msg = "httpx backend requested but httpx or hishel not installed"
        raise ImportError(msg)

    if backend_type == "aiohttp":
        if importlib.util.find_spec("aiohttp") and importlib.util.find_spec(
            "aiohttp_client_cache"
        ):
            from anyenv.download.aiohttp_backend import AiohttpBackend

            return AiohttpBackend(cache_dir=cache_dir, cache_ttl=cache_ttl)
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
    params: ParamsType | None = None,
    headers: HeaderType | None = None,
    json: Any = None,
    data: Any = None,
    files: FilesType | None = None,
    timeout: float | None = None,
    cache: bool = False,
    backend: BackendType | None = None,
    cache_dir: StrPath | None = None,
    cache_ttl: int | str | None = None,
    api_key: str | SecretStr | None = None,
    auth_type: AuthType = "bearer",
    auth_username: str | None = None,
    auth_header_name: str | None = None,
) -> HttpResponse:
    """Make an HTTP request.

    Args:
        method: HTTP method to use
        url: URL to request
        params: Optional query parameters
        headers: Optional request headers
        json: Optional JSON body
        data: Optional request body
        files: Optional files to upload
        timeout: Optional request timeout in seconds
        cache: Whether to use cached responses
        backend: Optional specific backend to use
        cache_dir: Optional directory to store cached responses
        cache_ttl: Optional TTL for cached responses. Can be specified as seconds (int)
                   or as a time period string (e.g. "1h", "2d", "1w 2d").
        api_key: Optional API key or token for authentication
        auth_type: Authentication type to use with the api_key:
                   - "bearer": Authorization: Bearer {api_key}
                   - "basic": Authorization: Basic {base64(auth_username:api_key)}
                   - "header": Uses auth_header_name: {api_key}
                   - "query": Adds api_key as query parameter
        auth_username: Username for basic authentication (only used with auth_type basic)
        auth_header_name: Header name to use when auth_type="header"
                          Defaults to "X-API-Key"

    Returns:
        An HttpResponse object
    """
    if auth_header_name is None:
        auth_header_name = "X-API-Key"

    http_backend = get_backend(backend, cache_dir=cache_dir, cache_ttl=cache_ttl)

    # Apply authentication if api_key is provided
    processed_params = params
    processed_headers = headers or {}

    if api_key is not None:
        key_value = (
            api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        )

        match auth_type:
            case "bearer":
                processed_headers = dict(processed_headers)
                processed_headers["Authorization"] = f"Bearer {key_value}"

            case "basic":
                if auth_username is None:
                    msg = "auth_username is required for basic authentication"
                    raise ValueError(msg)

                auth_str = f"{auth_username}:{key_value}"
                encoded = base64.b64encode(auth_str.encode()).decode()
                processed_headers = dict(processed_headers)
                processed_headers["Authorization"] = f"Basic {encoded}"

            case "header":
                processed_headers = dict(processed_headers)
                processed_headers[auth_header_name] = key_value

            case "query":
                processed_params = dict(params or {})
                processed_params["api_key"] = key_value

            case _ as unreachable:
                assert_never(unreachable)

    return await http_backend.request(
        method,
        url,
        params=processed_params,
        headers=processed_headers,
        json=json,
        data=data,
        files=files,
        timeout=timeout,
        cache=cache,
    )


async def get(
    url: str,
    *,
    params: ParamsType | None = None,
    headers: HeaderType | None = None,
    timeout: float | None = None,
    cache: bool = False,
    backend: BackendType | None = None,
    cache_dir: StrPath | None = None,
    cache_ttl: int | str | None = None,
    api_key: str | SecretStr | None = None,
    auth_type: AuthType = "bearer",
    auth_username: str | None = None,
    auth_header_name: str | None = None,
) -> HttpResponse:
    """Make a GET request.

    Args:
        url: URL to request
        params: Optional query parameters
        headers: Optional request headers
        timeout: Optional request timeout in seconds
        cache: Whether to use cached responses
        backend: Optional specific backend to use
        cache_dir: Optional directory to store cached responses
        cache_ttl: Optional TTL for cached responses. Can be specified as seconds (int)
                   or as a time period string (e.g. "1h", "2d", "1w 2d").
        api_key: Optional API key for authentication
        auth_type: Type of authentication to use (bearer, basic, header, query)
        auth_username: Username for basic authentication
        auth_header_name: Header name for header authentication

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
        cache_dir=cache_dir,
        cache_ttl=cache_ttl,
        api_key=api_key,
        auth_type=auth_type,
        auth_username=auth_username,
        auth_header_name=auth_header_name,
    )


async def post(
    url: str,
    *,
    params: ParamsType | None = None,
    headers: HeaderType | None = None,
    json: Any = None,
    data: Any = None,
    files: FilesType | None = None,
    timeout: float | None = None,
    cache: bool = False,
    backend: BackendType | None = None,
    cache_dir: StrPath | None = None,
    cache_ttl: int | str | None = None,
    api_key: str | SecretStr | None = None,
    auth_type: AuthType = "bearer",
    auth_username: str | None = None,
    auth_header_name: str | None = None,
) -> HttpResponse:
    """Make a POST request.

    Args:
        url: URL to request
        params: Optional query parameters
        headers: Optional request headers
        json: Optional JSON body
        data: Optional request body
        files: Optional files to upload
        timeout: Optional request timeout in seconds
        cache: Whether to use cached responses
        backend: Optional specific backend to use
        cache_dir: Optional path to use for caching
        cache_ttl: Optional TTL for cached responses. Can be specified as seconds (int)
                   or as a time period string (e.g. "1h", "2d", "1w 2d").
        api_key: Optional API key for authentication
        auth_type: Optional authentication type
        auth_username: Optional username for authentication
        auth_header_name: Optional header name for authentication

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
        files=files,
        timeout=timeout,
        cache=cache,
        backend=backend,
        cache_dir=cache_dir,
        cache_ttl=cache_ttl,
        api_key=api_key,
        auth_type=auth_type,
        auth_username=auth_username,
        auth_header_name=auth_header_name,
    )


async def download(
    url: str,
    path: StrPath,
    *,
    headers: HeaderType | None = None,
    progress_callback: ProgressCallback | None = None,
    cache: bool = False,
    backend: BackendType | None = None,
    cache_dir: StrPath | None = None,
    cache_ttl: int | str | None = None,
) -> None:
    """Download a file with optional progress reporting.

    Args:
        url: URL to download
        path: Path where to save the file
        headers: Optional request headers
        progress_callback: Optional callback for progress reporting
        cache: Whether to use cached responses
        backend: Optional specific backend to use
        cache_dir: Optional directory to use for caching
        cache_ttl: Optional TTL for cached responses. Can be specified as seconds (int)
                   or as a time period string (e.g. "1h", "2d", "1w 2d").
    """
    http_backend = get_backend(backend, cache_dir=cache_dir, cache_ttl=cache_ttl)
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
    params: ParamsType | None = None,
    headers: HeaderType | None = None,
    timeout: float | None = None,
    cache: bool = False,
    backend: BackendType | None = None,
    cache_dir: StrPath | None = None,
    cache_ttl: int | str | None = None,
    api_key: str | SecretStr | None = None,
    auth_type: AuthType = "bearer",
    auth_username: str | None = None,
    auth_header_name: str | None = None,
) -> str:
    """Make a GET request and return the response text.

    Args:
        url: URL to request
        params: Optional query parameters
        headers: Optional request headers
        timeout: Optional request timeout in seconds
        cache: Whether to use cached responses
        backend: Optional specific backend to use
        cache_dir: Optional directory to store cached responses
        cache_ttl: Optional TTL for cached responses. Can be specified as seconds (int)
                   or as a time period string (e.g. "1h", "2d", "1w 2d").
        api_key: Optional API key for authentication
        auth_type: Authentication type ("bearer", "basic", etc.)
        auth_username: Optional username for authentication
        auth_header_name: Optional header name for authentication

    Returns:
        The response body as text
    """
    response = await get(
        url,
        params=params,
        headers=headers,
        timeout=timeout,
        cache=cache,
        backend=backend,
        cache_dir=cache_dir,
        cache_ttl=cache_ttl,
        api_key=api_key,
        auth_type=auth_type,
        auth_username=auth_username,
        auth_header_name=auth_header_name,
    )
    return await response.text()


async def get_json[T](
    url: str,
    *,
    return_type: type[T] | None = None,
    params: ParamsType | None = None,
    headers: HeaderType | None = None,
    timeout: float | None = None,
    cache: bool = False,
    backend: BackendType | None = None,
    cache_dir: StrPath | None = None,
    cache_ttl: int | str | None = None,
    api_key: str | SecretStr | None = None,
    auth_type: AuthType = "bearer",
    auth_username: str | None = None,
    auth_header_name: str | None = None,
) -> T:
    """Make a GET request and return the response as JSON.

    Args:
        url: URL to request
        return_type: Optional type to validate the response against
        params: Optional query parameters
        headers: Optional request headers
        timeout: Optional request timeout in seconds
        cache: Whether to use cached responses
        backend: Optional specific backend to use
        cache_dir: Optional directory to store cached responses
        cache_ttl: Optional TTL for cached responses. Can be specified as seconds (int)
                   or as a time period string (e.g. "1h", "2d", "1w 2d").
        api_key: Optional API key for authentication
        auth_type: Authentication type (default: "bearer")
        auth_username: Optional username for basic authentication
        auth_header_name: Optional header name for custom authentication

    Returns:
        The response body parsed as JSON
    """
    from anyenv.validate import validate_json_data

    response = await get(
        url,
        params=params,
        headers=headers,
        timeout=timeout,
        cache=cache,
        backend=backend,
        cache_dir=cache_dir,
        cache_ttl=cache_ttl,
        api_key=api_key,
        auth_type=auth_type,
        auth_username=auth_username,
        auth_header_name=auth_header_name,
    )
    data = await response.json()
    return validate_json_data(data, return_type)


async def get_bytes(
    url: str,
    *,
    params: ParamsType | None = None,
    headers: HeaderType | None = None,
    timeout: float | None = None,
    cache: bool = False,
    backend: BackendType | None = None,
    cache_dir: StrPath | None = None,
    cache_ttl: int | str | None = None,
    api_key: str | SecretStr | None = None,
    auth_type: AuthType = "bearer",
    auth_username: str | None = None,
    auth_header_name: str | None = None,
) -> bytes:
    """Make a GET request and return the response as bytes.

    Args:
        url: URL to request
        params: Optional query parameters
        headers: Optional request headers
        timeout: Optional request timeout in seconds
        cache: Whether to use cached responses
        backend: Optional specific backend to use
        cache_dir: Optional directory to store cached responses
        cache_ttl: Optional TTL for cached responses. Can be specified as seconds (int)
                   or as a time period string (e.g. "1h", "2d", "1w 2d").
        api_key: Optional API key for authentication
        auth_type: Authentication type (default: "bearer")
        auth_username: Optional username for authentication
        auth_header_name: Optional header name for authentication

    Returns:
        The response body as bytes
    """
    response = await get(
        url,
        params=params,
        headers=headers,
        timeout=timeout,
        cache=cache,
        backend=backend,
        cache_dir=cache_dir,
        cache_ttl=cache_ttl,
        api_key=api_key,
        auth_type=auth_type,
        auth_username=auth_username,
        auth_header_name=auth_header_name,
    )
    return await response.bytes()


# Synchronous versions of the API functions


def request_sync(
    method: Method,
    url: str,
    *,
    json: Any = None,
    data: Any = None,
    files: FilesType | None = None,
    params: ParamsType | None = None,
    headers: HeaderType | None = None,
    timeout: float | None = None,
    cache: bool = False,
    backend: BackendType | None = None,
    cache_dir: StrPath | None = None,
    cache_ttl: int | str | None = None,
    api_key: str | SecretStr | None = None,
    auth_type: AuthType = "bearer",
    auth_username: str | None = None,
    auth_header_name: str | None = None,
) -> HttpResponse:
    """Synchronous version of request."""
    if auth_header_name is None:
        auth_header_name = "X-API-Key"

    http_backend = get_backend(backend, cache_dir=cache_dir, cache_ttl=cache_ttl)
    processed_params = params
    processed_headers = headers or {}

    if api_key is not None:
        key_value = (
            api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        )

        match auth_type:
            case "bearer":
                processed_headers = dict(processed_headers)
                processed_headers["Authorization"] = f"Bearer {key_value}"

            case "basic":
                if auth_username is None:
                    msg = "auth_username is required for basic authentication"
                    raise ValueError(msg)

                auth_str = f"{auth_username}:{key_value}"
                encoded = base64.b64encode(auth_str.encode()).decode()
                processed_headers = dict(processed_headers)
                processed_headers["Authorization"] = f"Basic {encoded}"

            case "header":
                processed_headers = dict(processed_headers)
                processed_headers[auth_header_name] = key_value

            case "query":
                processed_params = dict(params or {})
                processed_params["api_key"] = key_value

            case _ as unreachable:
                assert_never(unreachable)

    return http_backend.request_sync(
        method,
        url,
        params=processed_params,
        headers=processed_headers,
        json=json,
        data=data,
        files=files,
        timeout=timeout,
        cache=cache,
    )


def get_sync(url: str, **kwargs: Unpack[DataRetrievalOptions]) -> HttpResponse:
    """Synchronous version of get."""
    return request_sync("GET", url, **kwargs)


def post_sync(
    url: str,
    *,
    json: Any = None,
    data: Any = None,
    files: FilesType | None = None,
    **kwargs: Unpack[DataRetrievalOptions],
) -> HttpResponse:
    """Synchronous version of post."""
    return request_sync(
        "POST",
        url,
        json=json,
        data=data,
        files=files,
        **kwargs,
    )


def download_sync(
    url: str,
    path: StrPath,
    *,
    headers: HeaderType | None = None,
    progress_callback: ProgressCallback | None = None,
    cache: bool = False,
    backend: BackendType | None = None,
    cache_dir: StrPath | None = None,
    cache_ttl: int | str | None = None,
) -> None:
    """Synchronous version of download."""
    http_backend = get_backend(backend, cache_dir=cache_dir, cache_ttl=cache_ttl)
    http_backend.download_sync(
        url,
        path,
        headers=headers,
        progress_callback=progress_callback,
        cache=cache,
    )


def get_text_sync(url: str, **kwargs: Unpack[DataRetrievalOptions]) -> str:
    """Synchronous version of get_text."""
    from anyenv.async_run import run_sync

    return run_sync(get_text(url, **kwargs))


def get_json_sync[T](
    url: str,
    *,
    return_type: type[T] | None = None,
    **kwargs: Unpack[DataRetrievalOptions],
) -> T:
    """Synchronous version of get_json."""
    from anyenv.async_run import run_sync

    return run_sync(get_json(url, return_type=return_type, **kwargs))


def get_bytes_sync(url: str, **kwargs: Unpack[DataRetrievalOptions]) -> bytes:
    """Synchronous version of get_bytes."""
    from anyenv.async_run import run_sync

    return run_sync(get_bytes(url, **kwargs))


async def post_json[T](  # noqa: D417
    url: str,
    json_data: Any,
    *,
    files: FilesType | None = None,
    return_type: type[T] | None = None,
    **kwargs: Unpack[DataRetrievalOptions],
) -> T:
    """Make a POST request with JSON data and return the response as JSON.

    Args:
        url: URL to request
        json_data: Data to send as JSON in the request body
        files: Optional files to send in the request body
        params: Optional query parameters
        headers: Optional request headers
        timeout: Optional request timeout in seconds
        cache: Whether to use cached responses
        backend: Optional specific backend to use
        cache_dir: Optional directory to store cached responses
        cache_ttl: Optional TTL for cached responses. Can be specified as seconds (int)
                   or as a time period string (e.g. "1h", "2d", "1w 2d").
        return_type: Optional type to validate the response against
        api_key: Optional API key for authentication
        auth_type: Authentication type (default: "bearer")
        auth_username: Optional username for authentication
        auth_header_name: Optional header name for authentication

    Returns:
        The response body parsed as JSON
    """
    from anyenv.validate import validate_json_data

    if files:
        response = await post(url, data=json_data, files=files, **kwargs)
    else:
        response = await post(url, json=json_data, **kwargs)
    data = await response.json()
    return validate_json_data(data, return_type)


def post_json_sync[T](
    url: str,
    json_data: Any,
    *,
    files: FilesType | None = None,
    return_type: type[T] | None = None,
    **kwargs: Unpack[DataRetrievalOptions],
) -> T:
    """Synchronous version of post_json."""
    from anyenv.async_run import run_sync

    return run_sync(
        post_json(url, json_data, files=files, return_type=return_type, **kwargs)
    )


if __name__ == "__main__":
    import asyncio

    asyncio.run(post_json("https://example.com", {"key": "value"}))
