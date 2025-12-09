"""Base interface for JSON providers."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from io import TextIOWrapper


class JsonProviderBase(abc.ABC):
    """Base class for all JSON providers."""

    @staticmethod
    @abc.abstractmethod
    def load_json(data: str | bytes | TextIOWrapper) -> Any:
        """Load JSON data into Python objects."""

    @staticmethod
    @abc.abstractmethod
    def dump_json(
        data: Any,
        indent: bool = False,
        naive_utc: bool = False,
        serialize_numpy: bool = False,
        sort_keys: bool = False,
    ) -> str:
        """Dump Python objects to JSON string."""


@dataclass
class ParseErrorInfo:
    """Structured information about a parse error."""

    message: str
    line: int | None = None
    column: int | None = None
    source_path: str | Path | None = None
    source_content: str | None = None

    def format(
        self,
        context_lines: int = 2,
        use_color: bool = True,
    ) -> str:
        """Format error with source context for display.

        Args:
            context_lines: Number of lines to show before/after the error line.
            use_color: Whether to include ANSI color codes.
        """
        parts: list[str] = []

        # Header with location
        location = str(self.source_path) if self.source_path else "<string>"
        if self.line is not None:
            location += f":{self.line}"
            if self.column is not None:
                location += f":{self.column}"

        if use_color:
            parts.append(f"\x1b[1;31mJSON Parse Error\x1b[0m at \x1b[1m{location}\x1b[0m")
        else:
            parts.append(f"JSON Parse Error at {location}")

        parts.append(f"  {self.message}")

        # Source context
        if self.source_content and self.line is not None:
            parts.append("")
            lines = self.source_content.splitlines()
            start = max(0, self.line - 1 - context_lines)
            end = min(len(lines), self.line + context_lines)

            line_num_width = len(str(end))

            for i in range(start, end):
                line_num = i + 1
                line_content = lines[i] if i < len(lines) else ""
                prefix = ">" if line_num == self.line else " "

                if use_color and line_num == self.line:
                    parts.append(
                        f"\x1b[1;31m{prefix} {line_num:>{line_num_width}} │\x1b[0m {line_content}"
                    )
                else:
                    parts.append(f"{prefix} {line_num:>{line_num_width}} │ {line_content}")

                # Column indicator
                if line_num == self.line and self.column is not None:
                    indicator_padding = " " * (line_num_width + 4 + self.column - 1)
                    if use_color:
                        parts.append(f"\x1b[1;31m{indicator_padding}^\x1b[0m")
                    else:
                        parts.append(f"{indicator_padding}^")

        return "\n".join(parts)


class JsonLoadError(Exception):
    """Unified exception for all JSON parsing errors."""

    def __init__(
        self,
        message: str,
        *,
        line: int | None = None,
        column: int | None = None,
        source_path: str | Path | None = None,
        source_content: str | None = None,
    ):
        super().__init__(message)
        self.info = ParseErrorInfo(
            message=message,
            line=line,
            column=column,
            source_path=source_path,
            source_content=source_content,
        )

    @property
    def line(self) -> int | None:
        return self.info.line

    @property
    def column(self) -> int | None:
        return self.info.column

    @property
    def source_path(self) -> str | Path | None:
        return self.info.source_path

    @property
    def source_content(self) -> str | None:
        return self.info.source_content

    def format(self, context_lines: int = 2, use_color: bool = True) -> str:
        """Format error with source context for display.

        Args:
            context_lines: Number of lines to show before/after the error line.
            use_color: Whether to include ANSI color codes.
        """
        return self.info.format(context_lines=context_lines, use_color=use_color)


class JsonDumpError(Exception):
    """Unified exception for all JSON serialization errors."""
