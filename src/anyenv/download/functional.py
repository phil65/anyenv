"""High-level interface for HTTP requests and downloads.

Inside an ``async with anyenv.http_session(...)`` block the async helpers use the
session's client (connection reuse); otherwise each call opens its own client.
The ``*_sync`` helpers always use a client of their own.
"""

from typing import TYPE_CHECKING, Any, Unpack

from anyenv.download.session import _UNSET, session_for, without_session


if TYPE_CHECKING:
    from anyenv.download.base import (
        DataRetrievalOptions,
        HttpResponse,
        Method,
        ProgressCallback,
        StrPath,
    )
    from anyenv.download.http_types import (
        AuthType,
        FilesType,
        HeaderType,
        ParamsType,
        SecretStr,
    )


async def request(
    method: Method,
    url: str,
    *,
    params: ParamsType | None = None,
    headers: HeaderType | None = None,
    json: Any = None,
    data: Any = None,
    files: FilesType | None = None,
    timeout: float | None = _UNSET,
    cache: bool | None = None,
    cache_dir: StrPath | None = None,
    cache_ttl: int | str | None = None,
    api_key: str | SecretStr | None = None,
    auth_type: AuthType = "bearer",
    auth_username: str | None = None,
    auth_header_name: str | None = None,
) -> HttpResponse:
    """Make an HTTP request; the response's body is read already.

    Args:
        method: HTTP method to use
        url: URL to request (relative URLs resolve against the session's base_url)
        params: Query parameters
        headers: Request headers
        json: JSON body
        data: Form data or raw body
        files: Files to upload (multipart)
        timeout: Timeout in seconds. When omitted, uses the open session's timeout,
            or `DEFAULT_TIMEOUT` (30 s per operation, 10 s connect) outside a
            session. Pass `None` to disable timeouts.
        cache: Cache responses (default: as the open session does, else no)
        cache_dir: Directory of the cache database
        cache_ttl: How long cached responses are used: seconds or e.g. "1h", "2d"
        api_key: API key or token for authentication
        auth_type: How the api_key is sent ("bearer", "basic", "header", "query")
        auth_username: Username for basic authentication
        auth_header_name: Header name for auth_type="header" (default: X-API-Key)

    Raises:
        RequestError: The request failed (connection, timeout)
        ResponseError: The response has a 4xx / 5xx status
    """
    async with session_for(cache, cache_dir, cache_ttl, timeout) as session:
        extra: dict[str, Any] = {} if timeout is _UNSET else {"timeout": timeout}
        return await session.request(
            method,
            url,
            params=params,
            headers=headers,
            json=json,
            data=data,
            files=files,
            api_key=api_key,
            auth_type=auth_type,
            auth_username=auth_username,
            auth_header_name=auth_header_name,
            **extra,
        )


async def get(
    url: str,
    *,
    params: ParamsType | None = None,
    headers: HeaderType | None = None,
    timeout: float | None = _UNSET,
    cache: bool | None = None,
    cache_dir: StrPath | None = None,
    cache_ttl: int | str | None = None,
    api_key: str | SecretStr | None = None,
    auth_type: AuthType = "bearer",
    auth_username: str | None = None,
    auth_header_name: str | None = None,
) -> HttpResponse:
    """Make a GET request (options as for `request`)."""
    return await request(
        "GET",
        url,
        params=params,
        headers=headers,
        timeout=timeout,
        cache=cache,
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
    timeout: float | None = _UNSET,
    cache: bool | None = None,
    cache_dir: StrPath | None = None,
    cache_ttl: int | str | None = None,
    api_key: str | SecretStr | None = None,
    auth_type: AuthType = "bearer",
    auth_username: str | None = None,
    auth_header_name: str | None = None,
) -> HttpResponse:
    """Make a POST request (options as for `request`)."""
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
    timeout: float | None = _UNSET,
    cache: bool | None = None,
    cache_dir: StrPath | None = None,
    cache_ttl: int | str | None = None,
) -> None:
    """Download a file, written to ``<path>.part`` and renamed once complete.

    In httpx the read timeout applies per read (not to the whole download), so
    large downloads keep working as long as data keeps arriving.

    Args:
        url: URL to download
        path: Path where to save the file (an existing file stays if it fails)
        headers: Request headers
        progress_callback: Called (sync or async) with (bytes so far, total)
        timeout: Timeout in seconds. When omitted, uses the open session's timeout,
            or `DEFAULT_TIMEOUT` (30 s per operation, 10 s connect) outside a
            session. Pass `None` to disable timeouts.
        cache: Cache the response (default: as the open session does, else no)
        cache_dir: Directory of the cache database
        cache_ttl: How long cached responses are used: seconds or e.g. "1h", "2d"
    """
    async with session_for(cache, cache_dir, cache_ttl, timeout) as session:
        await session.download(
            url, path, headers=headers, progress_callback=progress_callback, timeout=timeout
        )


async def get_text(url: str, **kwargs: Unpack[DataRetrievalOptions]) -> str:
    """GET a URL and return the body as text (options as for `request`)."""
    return (await get(url, **kwargs)).text


async def get_bytes(url: str, **kwargs: Unpack[DataRetrievalOptions]) -> bytes:
    """GET a URL and return the body as bytes (options as for `request`)."""
    return (await get(url, **kwargs)).content


async def get_json[T](
    url: str,
    *,
    return_type: type[T] | None = None,
    **kwargs: Unpack[DataRetrievalOptions],
) -> T:
    """GET a URL and return the body parsed as JSON (options as for `request`).

    Args:
        url: URL to request
        return_type: Type to validate the data against (pydantic models, dataclasses,
            TypedDicts, ...); without it the data is returned as parsed
        kwargs: Options as for `request`
    """
    from anyenv.validate import validate_json_data

    return validate_json_data((await get(url, **kwargs)).json(), return_type)


async def post_json[T](
    url: str,
    json_data: Any,
    *,
    files: FilesType | None = None,
    return_type: type[T] | None = None,
    **kwargs: Unpack[DataRetrievalOptions],
) -> T:
    """POST JSON and return the response parsed as JSON (options as for `request`).

    Args:
        url: URL to request
        json_data: Data sent as JSON body (as form fields when `files` are given)
        files: Files to upload (multipart)
        return_type: Type to validate the response against
        kwargs: Options as for `request`
    """
    from anyenv.validate import validate_json_data

    if files:
        response = await post(url, data=json_data, files=files, **kwargs)
    else:
        response = await post(url, json=json_data, **kwargs)
    return validate_json_data(response.json(), return_type)


# Synchronous versions: each call runs on an event loop of its own, with its own client.


def request_sync(
    method: Method,
    url: str,
    *,
    json: Any = None,
    data: Any = None,
    files: FilesType | None = None,
    **kwargs: Unpack[DataRetrievalOptions],
) -> HttpResponse:
    """Synchronous version of `request`."""
    from anyenv.async_run import run_sync

    return run_sync(
        without_session(request(method, url, json=json, data=data, files=files, **kwargs))
    )


def get_sync(url: str, **kwargs: Unpack[DataRetrievalOptions]) -> HttpResponse:
    """Synchronous version of `get`."""
    return request_sync("GET", url, **kwargs)


def post_sync(
    url: str,
    *,
    json: Any = None,
    data: Any = None,
    files: FilesType | None = None,
    **kwargs: Unpack[DataRetrievalOptions],
) -> HttpResponse:
    """Synchronous version of `post`."""
    return request_sync("POST", url, json=json, data=data, files=files, **kwargs)


def download_sync(
    url: str,
    path: StrPath,
    *,
    headers: HeaderType | None = None,
    progress_callback: ProgressCallback | None = None,
    timeout: float | None = _UNSET,
    cache: bool | None = None,
    cache_dir: StrPath | None = None,
    cache_ttl: int | str | None = None,
) -> None:
    """Synchronous version of `download`."""
    from anyenv.async_run import run_sync

    coro = download(
        url,
        path,
        headers=headers,
        progress_callback=progress_callback,
        timeout=timeout,
        cache=cache,
        cache_dir=cache_dir,
        cache_ttl=cache_ttl,
    )
    run_sync(without_session(coro))


def get_text_sync(url: str, **kwargs: Unpack[DataRetrievalOptions]) -> str:
    """Synchronous version of `get_text`."""
    from anyenv.async_run import run_sync

    return run_sync(without_session(get_text(url, **kwargs)))


def get_bytes_sync(url: str, **kwargs: Unpack[DataRetrievalOptions]) -> bytes:
    """Synchronous version of `get_bytes`."""
    from anyenv.async_run import run_sync

    return run_sync(without_session(get_bytes(url, **kwargs)))


def get_json_sync[T](
    url: str,
    *,
    return_type: type[T] | None = None,
    **kwargs: Unpack[DataRetrievalOptions],
) -> T:
    """Synchronous version of `get_json`."""
    from anyenv.async_run import run_sync

    return run_sync(without_session(get_json(url, return_type=return_type, **kwargs)))


def post_json_sync[T](
    url: str,
    json_data: Any,
    *,
    files: FilesType | None = None,
    return_type: type[T] | None = None,
    **kwargs: Unpack[DataRetrievalOptions],
) -> T:
    """Synchronous version of `post_json`."""
    from anyenv.async_run import run_sync

    coro = post_json(url, json_data, files=files, return_type=return_type, **kwargs)
    return run_sync(without_session(coro))
