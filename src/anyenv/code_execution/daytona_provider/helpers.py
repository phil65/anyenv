"""Daytona Provider Helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, assert_never


if TYPE_CHECKING:
    from anyenv.code_execution.parse_output import Language


def convert_language(language: Language):
    """Converts the given language to the corresponding CodeLanguage enum."""
    from daytona.common.daytona import CodeLanguage

    match language:
        case "python":
            return CodeLanguage.PYTHON
        case "javascript":
            return CodeLanguage.JAVASCRIPT
        case "typescript":
            return CodeLanguage.TYPESCRIPT
        case _ as unreachable:
            assert_never(unreachable)
