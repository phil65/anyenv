"""Exceptions anyenv HTTP functionality."""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from anyenv.download.base import HttpResponse


class HttpError(Exception):
    """Base class for HTTP errors."""

    def __init__(self, message: str, response: HttpResponse | None = None):
        super().__init__(message)
        self.response = response
