"""Systems language formatters (Go, Rust, Zig, C/C++)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from anyenv.language_formatters._base import (
    FormatResult,
    LanguageFormatter,
    LintResult,
)


if TYPE_CHECKING:
    from pathlib import Path


class GoFormatter(LanguageFormatter):
    """Go formatter using gofmt."""

    @property
    def name(self) -> str:
        return "Go"

    @property
    def command(self) -> str:
        return "gofmt"

    @property
    def extensions(self) -> list[str]:
        return [".go"]

    @property
    def pygments_lexers(self) -> list[str]:
        return ["go", "golang"]

    async def format(self, path: Path) -> FormatResult:
        cmd = ["gofmt", "-w", str(path)]
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
        # gofmt is format-only, use go vet for basic linting
        cmd = ["go", "vet", str(path)]
        success, stdout, stderr, duration, error_type = await self._execute_command(cmd)
        return LintResult(
            success=success,
            output=stdout,
            errors=stderr,
            duration=duration,
            error_type=error_type,
        )


class RustFormatter(LanguageFormatter):
    """Rust formatter using rustfmt and clippy."""

    @property
    def name(self) -> str:
        return "Rust"

    @property
    def command(self) -> str:
        return "rustfmt"

    @property
    def extensions(self) -> list[str]:
        return [".rs"]

    @property
    def pygments_lexers(self) -> list[str]:
        return ["rust", "rs"]

    async def format(self, path: Path) -> FormatResult:
        cmd = ["rustfmt", str(path)]
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
        cmd = ["cargo", "clippy"]
        if fix:
            cmd.append("--fix")
        cmd.extend(["--", "--", str(path)])
        success, stdout, stderr, duration, error_type = await self._execute_command(cmd)
        return LintResult(
            success=success,
            output=stdout,
            errors=stderr,
            duration=duration,
            error_type=error_type,
        )


class ZigFormatter(LanguageFormatter):
    """Zig formatter using zig fmt."""

    @property
    def name(self) -> str:
        return "Zig"

    @property
    def command(self) -> str:
        return "zig"

    @property
    def extensions(self) -> list[str]:
        return [".zig", ".zon"]

    @property
    def pygments_lexers(self) -> list[str]:
        return ["zig"]

    async def format(self, path: Path) -> FormatResult:
        cmd = ["zig", "fmt", str(path)]
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
        # zig fmt --check for lint-like behavior
        cmd = ["zig", "fmt", "--check", str(path)]
        success, stdout, stderr, duration, error_type = await self._execute_command(cmd)
        return LintResult(
            success=success,
            output=stdout,
            errors=stderr,
            duration=duration,
            error_type=error_type,
        )


class ClangFormatFormatter(LanguageFormatter):
    """C/C++ formatter using clang-format."""

    @property
    def name(self) -> str:
        return "C/C++"

    @property
    def command(self) -> str:
        return "clang-format"

    @property
    def extensions(self) -> list[str]:
        return [".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx", ".ino"]

    @property
    def pygments_lexers(self) -> list[str]:
        return ["c", "cpp", "c++", "cxx"]

    async def format(self, path: Path) -> FormatResult:
        cmd = ["clang-format", "-i", str(path)]
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
        # clang-format --dry-run --Werror for lint-like behavior
        cmd = ["clang-format", "--dry-run", "--Werror", str(path)]
        success, stdout, stderr, duration, error_type = await self._execute_command(cmd)
        return LintResult(
            success=success,
            output=stdout,
            errors=stderr,
            duration=duration,
            error_type=error_type,
        )
