"""R language formatter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from anyenv.language_formatters._base import FormatResult, LanguageFormatter, LintResult


if TYPE_CHECKING:
    from pathlib import Path


class AirFormatter(LanguageFormatter):
    """R formatter using air."""

    @property
    def name(self) -> str:
        return "R"

    @property
    def command(self) -> str:
        return "air"

    @property
    def extensions(self) -> list[str]:
        return [".R", ".r"]

    @property
    def pygments_lexers(self) -> list[str]:
        return ["r", "rlang", "splus"]

    async def format(self, path: Path) -> FormatResult:
        cmd = ["air", "format", str(path)]
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
        cmd = ["air", "format", "--check", str(path)]
        success, stdout, stderr, duration, error_type = await self._execute_command(cmd)
        return LintResult(
            success=success,
            output=stdout,
            errors=stderr,
            duration=duration,
            error_type=error_type,
        )
