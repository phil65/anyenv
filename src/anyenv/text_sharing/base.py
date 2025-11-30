"""Base class for text sharing services."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Literal


Visibility = Literal["public", "unlisted", "private"]


@dataclass
class ShareResult:
    """Result of a text sharing operation."""

    url: str
    """URL to access the shared content."""

    raw_url: str | None = None
    """Direct URL to raw content, if available."""

    delete_url: str | None = None
    """URL to delete the content, if available."""

    id: str | None = None
    """Provider-specific ID of the shared content."""


class TextSharer(abc.ABC):
    """Base class for text sharing services."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Name of the sharing service."""

    @abc.abstractmethod
    async def share(
        self,
        content: str,
        *,
        title: str | None = None,
        syntax: str | None = None,
        visibility: Visibility = "unlisted",
        expires_in: int | None = None,
    ) -> ShareResult:
        """Share text content.

        Args:
            content: The text content to share
            title: Optional title/filename for the content
            syntax: Syntax highlighting hint (e.g. "python", "markdown")
            visibility: Visibility level (not all providers support all levels)
            expires_in: Expiration time in seconds (not supported by all providers)

        Returns:
            ShareResult with URL and metadata
        """

    def share_sync(
        self,
        content: str,
        *,
        title: str | None = None,
        syntax: str | None = None,
        visibility: Visibility = "unlisted",
        expires_in: int | None = None,
    ) -> ShareResult:
        """Synchronous version of share."""
        from anyenv import run_sync

        async def wrapper() -> ShareResult:
            return await self.share(
                content,
                title=title,
                syntax=syntax,
                visibility=visibility,
                expires_in=expires_in,
            )

        return run_sync(wrapper())
