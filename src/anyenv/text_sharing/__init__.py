"""Text sharing services for sharing content via paste services."""

from __future__ import annotations

from typing import Literal, assert_never, overload

from anyenv.text_sharing.base import ShareResult, TextSharer, Visibility
from anyenv.text_sharing.github_gist import GistSharer
from anyenv.text_sharing.opencode import OpenCodeSharer
from anyenv.text_sharing.paste_rs import PasteRsSharer
from anyenv.text_sharing.pastebin import PastebinSharer


TextSharerStr = Literal["gist", "pastebin", "paste_rs", "opencode"]


@overload
def get_sharer(
    provider: Literal["gist"],
    *,
    token: str | None = None,
) -> GistSharer: ...


@overload
def get_sharer(
    provider: Literal["pastebin"],
    *,
    api_key: str | None = None,
) -> PastebinSharer: ...


@overload
def get_sharer(
    provider: Literal["paste_rs"],
) -> PasteRsSharer: ...


@overload
def get_sharer(
    provider: Literal["opencode"],
    *,
    api_url: str | None = None,
) -> OpenCodeSharer: ...


def get_sharer(
    provider: TextSharerStr,
    **kwargs: str | None,
) -> TextSharer:
    """Get a text sharer based on provider name.

    Args:
        provider: The text sharing provider to use
        **kwargs: Keyword arguments to pass to the provider constructor

    Returns:
        An instance of the specified text sharer

    Example:
        ```python
        # GitHub Gist (reads GITHUB_TOKEN/GH_TOKEN from env)
        sharer = get_sharer("gist")

        # GitHub Gist with explicit token
        sharer = get_sharer("gist", token="ghp_...")

        # Pastebin (reads PASTEBIN_API_KEY from env)
        sharer = get_sharer("pastebin")

        # Pastebin with explicit key
        sharer = get_sharer("pastebin", api_key="...")

        # paste.rs (no auth needed)
        sharer = get_sharer("paste_rs")

        # OpenCode (no auth needed)
        sharer = get_sharer("opencode")

        # OpenCode with custom API URL
        sharer = get_sharer("opencode", api_url="https://api.dev.opencode.ai")
        ```
    """
    match provider:
        case "gist":
            return GistSharer(**kwargs)
        case "pastebin":
            return PastebinSharer(**kwargs)
        case "paste_rs":
            return PasteRsSharer()
        case "opencode":
            return OpenCodeSharer(**kwargs)  # type: ignore[arg-type]
        case _ as unreachable:
            assert_never(unreachable)


__all__ = [
    "GistSharer",
    "OpenCodeSharer",
    "PasteRsSharer",
    "PastebinSharer",
    "ShareResult",
    "TextSharer",
    "TextSharerStr",
    "Visibility",
    "get_sharer",
]
