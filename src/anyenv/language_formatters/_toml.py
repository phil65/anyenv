"""TOML formatter using tombi."""

from __future__ import annotations

from typing import TYPE_CHECKING

from anyenv.language_formatters._base import FormatResult, LanguageFormatter, LintResult


if TYPE_CHECKING:
    from pathlib import Path


class TOMLFormatter(LanguageFormatter):
    """TOML formatter using tombi."""

    @property
    def name(self) -> str:
        return "TOML"

    @property
    def command(self) -> str:
        return "tombi"

    @property
    def extensions(self) -> list[str]:
        return [".toml"]

    @property
    def pygments_lexers(self) -> list[str]:
        return ["toml"]

    async def format(self, path: Path) -> FormatResult:
        cmd = ["uv", "run", "tombi", "format", str(path)]
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
        cmd = ["uv", "run", "tombi", "lint", str(path)]
        success, stdout, stderr, duration, error_type = await self._execute_command(cmd)
        return LintResult(
            success=success,
            output=stdout,
            errors=stderr,
            duration=duration,
            error_type=error_type,
        )
