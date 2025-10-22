"""TOMLLIB provider implementation."""

from __future__ import annotations

from io import BytesIO, TextIOWrapper
from pathlib import Path
from typing import Any

from upath import UPath

from anyenv.toml_tools.base import TomlDumpError, TomlLoadError, TomlProviderBase


class TomlLibProvider(TomlProviderBase):
    """TOMLLIB implementation of the TOML provider interface."""

    @staticmethod
    def load_toml(data: str | bytes | TextIOWrapper | Path | UPath) -> Any:
        """Load TOML using tomllib."""
        import tomllib

        try:
            match data:
                case Path() | UPath():
                    content = data.read_bytes()
                    return tomllib.load(BytesIO(content))
                case TextIOWrapper():
                    content = data.read().encode()
                    return tomllib.loads(content.decode())
                case bytes():
                    return tomllib.loads(data.decode())
                case str():
                    return tomllib.loads(data)
        except tomllib.TOMLDecodeError as exc:
            error_msg = f"Invalid TOML: {exc}"
            raise TomlLoadError(error_msg) from exc

    @staticmethod
    def dump_toml(
        data: Any,
        *,
        pretty: bool = False,
    ) -> str:
        """Dump data to TOML string using tomllib."""
        # tomllib is read-only, so we need to fallback to another library
        # or raise an error
        msg = "tomllib does not support writing TOML files (read-only library)"
        raise TomlDumpError(msg)
