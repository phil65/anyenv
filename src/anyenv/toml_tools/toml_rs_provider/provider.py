"""TOML-RS provider implementation."""

from __future__ import annotations

from io import BytesIO, TextIOWrapper
from pathlib import Path
from typing import Any

from upath import UPath

from anyenv.toml_tools.base import TomlLoadError, TomlProviderBase


class TomlRsProvider(TomlProviderBase):
    """TOML-RS implementation of the TOML provider interface."""

    @staticmethod
    def load_toml(data: str | bytes | TextIOWrapper | Path | UPath) -> Any:
        """Load TOML using toml_rs."""
        import toml_rs

        try:
            match data:
                case Path() | UPath():
                    bytes_data = data.read_bytes()
                    return toml_rs.load(BytesIO(bytes_data))
                case TextIOWrapper():
                    content = data.read()
                    return toml_rs.loads(content)
                case bytes():
                    content = data.decode()
                    return toml_rs.loads(content)
                case str():
                    return toml_rs.loads(data)
        except Exception as exc:
            error_msg = f"Invalid TOML: {exc}"
            raise TomlLoadError(error_msg) from exc

    @staticmethod
    def dump_toml(
        data: Any,
        *,
        pretty: bool = False,
    ) -> str:
        """Dump data to TOML string using toml_rs."""
        import toml_rs

        return toml_rs.dumps(data, pretty=pretty)
