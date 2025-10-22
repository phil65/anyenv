"""RTOML provider implementation."""

from __future__ import annotations

from io import TextIOWrapper
from pathlib import Path
from typing import Any

from upath import UPath

from anyenv.toml_tools.base import TomlDumpError, TomlLoadError, TomlProviderBase


class RtomlProvider(TomlProviderBase):
    """RTOML implementation of the TOML provider interface."""

    @staticmethod
    def load_toml(data: str | bytes | TextIOWrapper | Path | UPath) -> Any:
        """Load TOML using rtoml."""
        import rtoml

        try:
            match data:
                case Path():
                    return rtoml.load(data)
                case UPath():
                    content = data.read_text()
                    return rtoml.loads(content)
                case TextIOWrapper():
                    content = data.read()
                    return rtoml.loads(content)
                case bytes():
                    content = data.decode()
                    return rtoml.loads(content)
                case str():
                    return rtoml.loads(data)
        except Exception as exc:
            error_msg = f"Invalid TOML: {exc}"
            raise TomlLoadError(error_msg) from exc

    @staticmethod
    def dump_toml(
        data: Any,
        *,
        pretty: bool = False,
    ) -> str:
        """Dump data to TOML string using rtoml."""
        import rtoml

        try:
            return rtoml.dumps(data, pretty=pretty)
        except Exception as exc:
            error_msg = f"Cannot serialize to TOML: {exc}"
            raise TomlDumpError(error_msg) from exc
