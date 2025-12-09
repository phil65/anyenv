"""TOML-RS provider implementation."""

from __future__ import annotations

from io import BytesIO, TextIOWrapper
from pathlib import Path
import re
from typing import Any

from upath import UPath

from anyenv.toml_tools.base import TomlLoadError, TomlProviderBase


def _extract_toml_rs_error_info(exc: Exception) -> tuple[str, int | None, int | None]:
    """Extract line and column info from toml_rs error message.

    toml_rs errors may include position info in various formats.
    """
    msg = str(exc)
    line: int | None = None
    column: int | None = None

    # Try pattern "at line X column Y" or "(at line X, column Y)"
    match = re.search(r"at line (\d+)[,]? column (\d+)", msg)
    if match:
        line = int(match.group(1))
        column = int(match.group(2))
    else:
        # Try pattern "line X"
        match = re.search(r"line (\d+)", msg)
        if match:
            line = int(match.group(1))

    return msg, line, column


class TomlRsProvider(TomlProviderBase):
    """TOML-RS implementation of the TOML provider interface."""

    @staticmethod
    def load_toml(data: str | bytes | TextIOWrapper | Path | UPath) -> Any:
        """Load TOML using toml_rs."""
        import toml_rs

        try:
            source_content: str | None = None
            source_path: Path | UPath | None = None
            match data:
                case Path() | UPath():
                    source_path = data
                    bytes_data = data.read_bytes()
                    source_content = bytes_data.decode(errors="replace")
                    return toml_rs.load(BytesIO(bytes_data))
                case TextIOWrapper():
                    content = data.read()
                    source_content = content
                    return toml_rs.loads(content)
                case bytes():
                    content = data.decode()
                    source_content = content
                    return toml_rs.loads(content)
                case str():
                    source_content = data
                    return toml_rs.loads(data)
        except Exception as exc:
            msg, line, column = _extract_toml_rs_error_info(exc)
            raise TomlLoadError(
                f"Invalid TOML: {msg}",
                line=line,
                column=column,
                source_path=source_path,
                source_content=source_content,
            ) from exc

    @staticmethod
    def dump_toml(data: Any, *, pretty: bool = False) -> str:
        """Dump data to TOML string using toml_rs."""
        import toml_rs

        return toml_rs.dumps(data, pretty=pretty)
