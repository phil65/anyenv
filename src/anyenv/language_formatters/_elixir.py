"""Elixir language formatter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from anyenv.language_formatters._base import FormatResult, LanguageFormatter, LintResult


if TYPE_CHECKING:
    from pathlib import Path


class ElixirFormatter(LanguageFormatter):
    """Elixir formatter using mix format."""

    @property
    def name(self) -> str:
        return "Elixir"

    @property
    def command(self) -> str:
        return "mix"

    @property
    def extensions(self) -> list[str]:
        return [".ex", ".exs", ".eex", ".heex", ".leex", ".neex", ".sface"]

    @property
    def pygments_lexers(self) -> list[str]:
        return ["elixir", "ex", "exs", "eex", "heex"]

    async def format(self, path: Path) -> FormatResult:
        cmd = ["mix", "format", str(path)]
        success, stdout, stderr, duration, error_type = await self._execute_command(cmd)
        return FormatResult(
            success=success,
            output=stdout,
            errors=stderr,
            formatted=success,
            duration=duration,
            error_type=error_type,
        )

    async def lint(self, path: Path, fix: bool = False) -> LintResult:
        cmd = ["mix", "format", "--check-formatted", str(path)]
        success, stdout, stderr, duration, error_type = await self._execute_command(cmd)
        return LintResult(
            success=success,
            output=stdout,
            errors=stderr,
            duration=duration,
            error_type=error_type,
        )
