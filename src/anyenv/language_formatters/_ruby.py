"""Ruby formatters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from anyenv.language_formatters._base import FormatResult, LanguageFormatter, LintResult


if TYPE_CHECKING:
    from pathlib import Path


class RubocopFormatter(LanguageFormatter):
    """Ruby formatter using rubocop."""

    @property
    def name(self) -> str:
        return "Ruby"

    @property
    def command(self) -> str:
        return "rubocop"

    @property
    def extensions(self) -> list[str]:
        return [".rb", ".rake", ".gemspec", ".ru"]

    @property
    def pygments_lexers(self) -> list[str]:
        return ["ruby", "rb"]

    async def format(self, path: Path) -> FormatResult:
        cmd = ["rubocop", "--autocorrect", str(path)]
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
        cmd = ["rubocop"]
        if fix:
            cmd.append("--autocorrect")
        cmd.append(str(path))
        success, stdout, stderr, duration, error_type = await self._execute_command(cmd)
        return LintResult(
            success=success,
            output=stdout,
            errors=stderr,
            duration=duration,
            error_type=error_type,
        )


class StandardRBFormatter(LanguageFormatter):
    """Ruby formatter using standardrb."""

    @property
    def name(self) -> str:
        return "Ruby"

    @property
    def command(self) -> str:
        return "standardrb"

    @property
    def extensions(self) -> list[str]:
        return [".rb", ".rake", ".gemspec", ".ru"]

    @property
    def pygments_lexers(self) -> list[str]:
        return ["ruby", "rb"]

    async def format(self, path: Path) -> FormatResult:
        cmd = ["standardrb", "--fix", str(path)]
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
        cmd = ["standardrb"]
        if fix:
            cmd.append("--fix")
        cmd.append(str(path))
        success, stdout, stderr, duration, error_type = await self._execute_command(cmd)
        return LintResult(
            success=success,
            output=stdout,
            errors=stderr,
            duration=duration,
            error_type=error_type,
        )
