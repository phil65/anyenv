"""Python language formatters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from anyenv.language_formatters._base import FormatResult, LanguageFormatter, LintResult


if TYPE_CHECKING:
    from pathlib import Path


class PythonRuffFormatter(LanguageFormatter):
    """Python formatter using ruff directly."""

    @property
    def name(self) -> str:
        return "Python"

    @property
    def command(self) -> str:
        return "ruff"

    @property
    def extensions(self) -> list[str]:
        return [".py", ".pyi"]

    @property
    def pygments_lexers(self) -> list[str]:
        return ["python", "python3", "py"]

    async def format(self, path: Path) -> FormatResult:
        cmd = ["ruff", "format", str(path)]
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
        cmd = ["ruff", "check"]
        if fix:
            cmd.extend(["--fix", "--unsafe-fixes"])
        cmd.append(str(path))
        success, stdout, stderr, duration, error_type = await self._execute_command(cmd)
        return LintResult(
            success=success,
            output=stdout,
            errors=stderr,
            duration=duration,
            error_type=error_type,
        )


class PythonUvFormatter(LanguageFormatter):
    """Python formatter using uv to run ruff."""

    @property
    def name(self) -> str:
        return "Python"

    @property
    def command(self) -> str:
        return "uv"

    @property
    def extensions(self) -> list[str]:
        return [".py", ".pyi"]

    @property
    def pygments_lexers(self) -> list[str]:
        return ["python", "python3", "py"]

    async def format(self, path: Path) -> FormatResult:
        cmd = ["uv", "run", "ruff", "format", str(path)]
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
        cmd = ["uv", "run", "ruff", "check"]
        if fix:
            cmd.extend(["--fix", "--unsafe-fixes"])
        cmd.append(str(path))
        success, stdout, stderr, duration, error_type = await self._execute_command(cmd)
        return LintResult(
            success=success,
            output=stdout,
            errors=stderr,
            duration=duration,
            error_type=error_type,
        )
