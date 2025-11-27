"""Web-related formatters (JS/TS/HTML/CSS)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from anyenv.language_formatters._base import (
    FormatResult,
    LanguageFormatter,
    LintResult,
)


if TYPE_CHECKING:
    from pathlib import Path


class BiomeFormatter(LanguageFormatter):
    """TypeScript/JavaScript/JSON formatter using biome."""

    @property
    def name(self) -> str:
        return "TypeScript"

    @property
    def command(self) -> str:
        return "biome"

    @property
    def extensions(self) -> list[str]:
        return [".ts", ".tsx", ".js", ".jsx", ".json", ".jsonc"]

    @property
    def pygments_lexers(self) -> list[str]:
        return ["typescript", "ts", "javascript", "js", "jsx", "tsx", "json"]

    async def format(self, path: Path) -> FormatResult:
        cmd = ["biome", "format", "--write", str(path)]
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
        cmd = ["biome", "lint"]
        if fix:
            cmd.append("--write")
        cmd.append(str(path))
        success, stdout, stderr, duration, error_type = await self._execute_command(cmd)
        return LintResult(
            success=success,
            output=stdout,
            errors=stderr,
            duration=duration,
            error_type=error_type,
        )


class PrettierFormatter(LanguageFormatter):
    """Multi-language formatter using prettier."""

    @property
    def name(self) -> str:
        return "Prettier"

    @property
    def command(self) -> str:
        return "prettier"

    @property
    def extensions(self) -> list[str]:
        return [".html", ".css", ".scss", ".less", ".md", ".markdown", ".yaml", ".yml", ".graphql"]

    @property
    def pygments_lexers(self) -> list[str]:
        return ["html", "css", "scss", "less", "markdown", "md", "yaml", "graphql"]

    async def format(self, path: Path) -> FormatResult:
        cmd = ["prettier", "--write", str(path)]
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
        # Prettier is format-only, check mode reports if file is formatted
        cmd = ["prettier", "--check", str(path)]
        success, stdout, stderr, duration, error_type = await self._execute_command(cmd)
        return LintResult(
            success=success,
            output=stdout,
            errors=stderr,
            duration=duration,
            error_type=error_type,
        )


class HtmlBeautifierFormatter(LanguageFormatter):
    """ERB formatter using htmlbeautifier."""

    @property
    def name(self) -> str:
        return "ERB"

    @property
    def command(self) -> str:
        return "htmlbeautifier"

    @property
    def extensions(self) -> list[str]:
        return [".erb", ".html.erb"]

    @property
    def pygments_lexers(self) -> list[str]:
        return ["erb", "rhtml"]

    async def format(self, path: Path) -> FormatResult:
        cmd = ["htmlbeautifier", str(path)]
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
        # htmlbeautifier is format-only, no lint mode
        return LintResult(
            success=True,
            output="",
            errors="",
            duration=0.0,
            error_type=None,
        )
