"""PyTOMLPP provider implementation."""

from __future__ import annotations

from io import TextIOWrapper
from pathlib import Path
from typing import Any

from upath import UPath

from anyenv.toml_tools.base import TomlDumpError, TomlLoadError, TomlProviderBase


class PytomlppProvider(TomlProviderBase):
    """PyTOMLPP implementation of the TOML provider interface."""

    @staticmethod
    def load_toml(data: str | bytes | TextIOWrapper | Path | UPath) -> Any:
        """Load TOML using pytomlpp."""
        import pytomlpp

        try:
            match data:
                case Path() | UPath():
                    content = data.read_text()
                    return pytomlpp.loads(content)
                case TextIOWrapper():
                    content = data.read()
                    return pytomlpp.loads(content)
                case bytes():
                    content = data.decode()
                    return pytomlpp.loads(content)
                case str():
                    return pytomlpp.loads(data)
        except Exception as exc:
            error_msg = f"Invalid TOML: {exc}"
            raise TomlLoadError(error_msg) from exc

    @staticmethod
    def dump_toml(
        data: Any,
        *,
        pretty: bool = False,
    ) -> str:
        """Dump data to TOML string using pytomlpp."""
        import pytomlpp

        try:
            # pytomlpp doesn't have a pretty option, it always formats nicely
            return pytomlpp.dumps(data)
        except Exception as exc:
            error_msg = f"Cannot serialize to TOML: {exc}"
            raise TomlDumpError(error_msg) from exc
