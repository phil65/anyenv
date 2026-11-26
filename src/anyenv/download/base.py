"""Types and the response object of anyenv's HTTP functionality."""

from __future__ import annotations

from collections.abc import Callable
import contextlib
import os
import pathlib
from typing import TYPE_CHECKING, Any, Literal, NotRequired, TypedDict


if TYPE_CHECKING:
    from collections.abc import Generator
    from typing import BinaryIO

    import httpx2 as httpx

    from anyenv.download.http_types import AuthType, HeaderType, ParamsType, SecretStr

ProgressCallback = Callable[[int, int], Any]  # current, total -> Any
Method = Literal["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"]
StrPath = str | os.PathLike[str]
DEFAULT_TTL = 3600


@contextlib.contextmanager
def open_download_target(path: str | os.PathLike[str]) -> Generator[BinaryIO]:
    """Open a download's target for writing, replacing it only on success.

    Writes go to ``<path>.part``, renamed onto the path when the block completes;
    on an error the part file is removed and an existing file stays as it was.
    """
    target = pathlib.Path(path)
    part = target.with_name(f"{target.name}.part")
    try:
        with part.open("wb") as f:
            yield f
        part.replace(target)
    except BaseException:
        part.unlink(missing_ok=True)
        raise


class AuthOptions(TypedDict):
    """Authentication options for HTTP requests."""

    api_key: NotRequired[str | SecretStr | None]
    auth_type: NotRequired[AuthType]
    auth_username: NotRequired[str | None]
    auth_header_name: NotRequired[str | None]


class RequestOptions(AuthOptions):
    """Per-request options, also accepted by the methods of an `HttpSession`."""

    params: NotRequired[ParamsType | None]
    headers: NotRequired[HeaderType | None]
    timeout: NotRequired[float | None]


class DataRetrievalOptions(RequestOptions):
    """Options of the module-level helpers: per-request options plus caching."""

    cache: NotRequired[bool | None]
    cache_dir: NotRequired[StrPath | None]
    cache_ttl: NotRequired[int | str | None]


class HttpResponse:
    """An HTTP response with its body already read.

    A thin wrapper over the response of whichever httpx flavour is installed
    (httpx2 or httpx), so callers don't depend on the flavour.
    """

    __slots__ = ("_response",)

    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    def __repr__(self) -> str:
        return f"<HttpResponse [{self.status_code} {self.reason}] {self.url}>"

    @property
    def status_code(self) -> int:
        """HTTP status code."""
        return self._response.status_code

    @property
    def reason(self) -> str:
        """Reason phrase of the status (e.g. "Not Found")."""
        return self._response.reason_phrase

    @property
    def url(self) -> str:
        """Final URL of the response (after redirects)."""
        return str(self._response.url)

    @property
    def headers(self) -> dict[str, str]:
        """Response headers (lower-case names; repeated headers joined by commas)."""
        return dict(self._response.headers)

    @property
    def content(self) -> bytes:
        """Response body as bytes."""
        return self._response.content

    @property
    def text(self) -> str:
        """Response body decoded as text (charset from the headers, else guessed)."""
        return self._response.text

    def json(self) -> Any:
        """Response body parsed as JSON."""
        from anyenv import load_json

        return load_json(self._response.content)

    def validated_json[T](self, return_type: type[T]) -> T:
        """Response body parsed as JSON and validated against a type.

        Args:
            return_type: The type to validate the response against

        Raises:
            TypeError: If validation fails
        """
        from anyenv.validate import validate_json_data

        return validate_json_data(self.json(), return_type)
