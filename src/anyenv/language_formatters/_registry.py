"""Formatter registry for managing language formatters."""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pathlib import Path

    from exxec import ExecutionEnvironment, ExecutionEnvironmentStr

    from anyenv.language_formatters._base import LanguageFormatter


class FormatterRegistry:
    """Registry for language formatters."""

    def __init__(
        self,
        execution_env: ExecutionEnvironment | ExecutionEnvironmentStr = "local",
    ) -> None:
        """Initialize registry with default execution environment.

        Args:
            execution_env: Default execution environment for all formatters
        """
        self.formatters: list[LanguageFormatter] = []
        self.default_execution_env: ExecutionEnvironment | ExecutionEnvironmentStr = execution_env

    def register(self, formatter: LanguageFormatter) -> None:
        """Register a formatter."""
        self.formatters.append(formatter)

    def register_default_formatters(self) -> None:
        """Register all default formatters with the registry's execution environment."""
        from anyenv.language_formatters._elixir import ElixirFormatter
        from anyenv.language_formatters._jvm import KtlintFormatter
        from anyenv.language_formatters._python import PythonUvFormatter
        from anyenv.language_formatters._r import AirFormatter
        from anyenv.language_formatters._ruby import RubocopFormatter
        from anyenv.language_formatters._systems import (
            ClangFormatFormatter,
            GoFormatter,
            RustFormatter,
            ZigFormatter,
        )
        from anyenv.language_formatters._toml import TOMLFormatter
        from anyenv.language_formatters._web import (
            BiomeFormatter,
            HtmlBeautifierFormatter,
            PrettierFormatter,
        )

        self.register(PythonUvFormatter(self.default_execution_env))
        self.register(TOMLFormatter(self.default_execution_env))
        self.register(BiomeFormatter(self.default_execution_env))
        self.register(PrettierFormatter(self.default_execution_env))
        self.register(RustFormatter(self.default_execution_env))
        self.register(GoFormatter(self.default_execution_env))
        self.register(ElixirFormatter(self.default_execution_env))
        self.register(ZigFormatter(self.default_execution_env))
        self.register(ClangFormatFormatter(self.default_execution_env))
        self.register(KtlintFormatter(self.default_execution_env))
        self.register(RubocopFormatter(self.default_execution_env))
        self.register(HtmlBeautifierFormatter(self.default_execution_env))
        self.register(AirFormatter(self.default_execution_env))

    def get_formatter(self, path: Path) -> LanguageFormatter | None:
        """Get formatter for given file path."""
        return next((f for f in self.formatters if f.can_handle(path)), None)

    def get_formatter_by_language(self, language: str) -> LanguageFormatter | None:
        """Get formatter for given language name (pygments lexer)."""
        return next((f for f in self.formatters if f.can_handle_language(language)), None)

    def get_formatter_by_command(self, command: str) -> LanguageFormatter | None:
        """Get formatter by CLI command name."""
        return next((f for f in self.formatters if f.command == command), None)

    def get_available_formatters(self) -> list[LanguageFormatter]:
        """Get all formatters whose commands are available on the system."""
        return [f for f in self.formatters if f.is_available()]

    def detect_language_from_content(self, content: str) -> str | None:
        """Detect language from content using pygments (if available)."""
        try:
            from pygments.lexers import guess_lexer

            lexer = guess_lexer(content)
            return lexer.name.lower()  # type: ignore[attr-defined, no-any-return]
        except ImportError:
            return None
        except Exception:  # noqa: BLE001
            return None

    def get_supported_extensions(self) -> list[str]:
        """Get all supported file extensions."""
        return sorted({e for formatter in self.formatters for e in formatter.extensions})
