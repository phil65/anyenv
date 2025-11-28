"""Text sharing services for sharing content via paste services."""

from __future__ import annotations

from typing import Literal, assert_never, overload

from anyenv.text_sharing.base import ShareResult, TextSharer, Visibility
from anyenv.text_sharing.github_gist import GistSharer
from anyenv.text_sharing.paste_rs import PasteRsSharer
from anyenv.text_sharing.pastebin import PastebinSharer


TextSharerStr = Literal["gist", "pastebin", "paste_rs"]


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
        ```
    """
    match provider:
        case "gist":
            return GistSharer(**kwargs)  # type: ignore[arg-type]
        case "pastebin":
            return PastebinSharer(**kwargs)  # type: ignore[arg-type]
        case "paste_rs":
            return PasteRsSharer()
        case _ as unreachable:
            assert_never(unreachable)


__all__ = [
    "GistSharer",
    "PasteRsSharer",
    "PastebinSharer",
    "ShareResult",
    "TextSharer",
    "TextSharerStr",
    "Visibility",
    "get_sharer",
]
