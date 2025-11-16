"""Exceptions for anyenv HTTP functionality."""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from anyenv.download.base import HttpResponse


class HttpError(Exception):
    """Base class for HTTP errors."""

    def __init__(self, message: str, response: HttpResponse | None = None) -> None:
        super().__init__(message)
        self.response = response


class RequestError(HttpError):
    """Exception raised when a request fails due to network or connection issues."""

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.__cause__ = original_error


class ResponseError(HttpError):
    """Exception raised when a response contains an error status code."""

    def __init__(self, message: str, response: HttpResponse) -> None:
        super().__init__(message, response)
        self.status_code = response.status_code


def check_response(response: HttpResponse) -> HttpResponse:
    """Check response status and raise appropriate exceptions.

    Args:
        response: The HTTP response to check

    Returns:
        The same response if status code is < 400

    Raises:
        ResponseError: If the status code is >= 400
    """
    if 400 <= response.status_code < 600:  # noqa: PLR2004
        message = f"HTTP Error {response.status_code}"
        raise ResponseError(message, response)
    return response
