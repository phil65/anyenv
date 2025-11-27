"""JVM language formatters (Kotlin, etc.)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from anyenv.language_formatters._base import FormatResult, LanguageFormatter, LintResult


if TYPE_CHECKING:
    from pathlib import Path


class KtlintFormatter(LanguageFormatter):
    """Kotlin formatter using ktlint."""

    @property
    def name(self) -> str:
        return "Kotlin"

    @property
    def command(self) -> str:
        return "ktlint"

    @property
    def extensions(self) -> list[str]:
        return [".kt", ".kts"]

    @property
    def pygments_lexers(self) -> list[str]:
        return ["kotlin", "kt"]

    async def format(self, path: Path) -> FormatResult:
        cmd = ["ktlint", "--format", str(path)]
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
        cmd = ["ktlint"]
        if fix:
            cmd.append("--format")
        cmd.append(str(path))
        success, stdout, stderr, duration, error_type = await self._execute_command(cmd)
        return LintResult(
            success=success,
            output=stdout,
            errors=stderr,
            duration=duration,
            error_type=error_type,
        )
