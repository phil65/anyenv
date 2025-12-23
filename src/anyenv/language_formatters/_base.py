"""Base classes for language formatters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
import shutil
import tempfile
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from exxec import ExecutionEnvironment, ExecutionEnvironmentStr


@dataclass
class LintResult:
    """Result of a linting operation."""

    success: bool
    output: str
    errors: str
    fixed_issues: int = 0
    remaining_issues: int = 0
    duration: float = 0.0
    error_type: str | None = None


@dataclass
class FormatResult:
    """Result of a formatting operation."""

    success: bool
    output: str
    errors: str
    formatted: bool = False
    duration: float = 0.0
    error_type: str | None = None


@dataclass
class FormatAndLintResult:
    """Combined result of format and lint operations."""

    format_result: FormatResult
    lint_result: LintResult

    @property
    def success(self) -> bool:
        """Overall success if both operations succeeded."""
        return self.format_result.success and self.lint_result.success

    @property
    def total_duration(self) -> float:
        """Total duration of both operations."""
        return self.format_result.duration + self.lint_result.duration


class LanguageFormatter(ABC):
    """Abstract base class for language-specific formatters."""

    def __init__(
        self,
        execution_env: ExecutionEnvironment | ExecutionEnvironmentStr = "local",
    ) -> None:
        """Initialize formatter with execution environment.

        Args:
            execution_env: Execution environment - either a string provider name
                or a direct ExecutionEnvironment instance
        """
        if isinstance(execution_env, str):
            from exxec import get_environment

            self._execution_env: ExecutionEnvironment = get_environment(execution_env)
        else:
            self._execution_env = execution_env

    async def _execute_command(self, cmd: list[str]) -> tuple[bool, str, str, float, str | None]:
        """Execute command and return rich result information."""
        async with self._execution_env as env:
            result = await env.execute_command(" ".join(cmd))
            return (
                result.success,
                result.stdout or str(result.result) if result.result else "",
                result.stderr or result.error or "",
                result.duration,
                result.error_type,
            )

    @property
    @abstractmethod
    def name(self) -> str:
        """Language name (e.g., 'Python', 'TOML')."""

    @property
    @abstractmethod
    def command(self) -> str:
        """Primary CLI command required (e.g., 'ruff', 'biome', 'gofmt')."""

    @property
    @abstractmethod
    def extensions(self) -> list[str]:
        """File extensions this formatter handles (e.g., ['.py', '.pyi'])."""

    @property
    @abstractmethod
    def pygments_lexers(self) -> list[str]:
        """Pygments lexer names for this language (e.g., ['python', 'python3'])."""

    @abstractmethod
    async def format(self, path: Path) -> FormatResult:
        """Format a file."""

    @abstractmethod
    async def lint(self, path: Path, fix: bool = False) -> LintResult:
        """Lint a file, optionally fixing issues."""

    def is_available(self) -> bool:
        """Check if the formatter command is available on the system."""
        return shutil.which(self.command) is not None

    async def format_and_lint(self, path: Path, fix: bool = False) -> FormatAndLintResult:
        """Format and then lint a file."""
        format_result = await self.format(path)
        lint_result = await self.lint(path, fix=fix)
        return FormatAndLintResult(format_result, lint_result)

    def can_handle(self, path: Path) -> bool:
        """Check if this formatter can handle the given file."""
        return path.suffix.lower() in self.extensions

    def can_handle_language(self, language: str) -> bool:
        """Check if this formatter can handle the given language name."""
        return language.lower() in [lexer.lower() for lexer in self.pygments_lexers]

    async def format_string(self, content: str, language: str | None = None) -> FormatResult:
        """Format a string by creating a temporary file.

        Args:
            content: String content to format
            language: Language name (pygments lexer name) if extension can't be determined

        Returns:
            FormatResult with formatted content in output field
        """
        extension = self.extensions[0] if self.extensions else ".txt"

        with tempfile.NamedTemporaryFile(mode="w", suffix=extension, delete=False) as temp_file:
            temp_file.write(content)
            temp_path = Path(temp_file.name)

        try:
            result = await self.format(temp_path)
            if result.success:
                formatted_content = temp_path.read_text("utf-8")
                result.output = formatted_content
            return result
        finally:
            temp_path.unlink(missing_ok=True)

    async def lint_string(
        self, content: str, language: str | None = None, fix: bool = False
    ) -> LintResult:
        """Lint a string by creating a temporary file.

        Args:
            content: String content to lint
            language: Language name (pygments lexer name) if extension can't be determined
            fix: Whether to apply fixes

        Returns:
            LintResult with any fixes applied to output field
        """
        extension = self.extensions[0] if self.extensions else ".txt"

        with tempfile.NamedTemporaryFile(mode="w", suffix=extension, delete=False) as temp_file:
            temp_file.write(content)
            temp_path = Path(temp_file.name)

        try:
            result = await self.lint(temp_path, fix=fix)
            if result.success and fix:
                modified_content = temp_path.read_text("utf-8")
                result.output = modified_content
            return result
        finally:
            temp_path.unlink(missing_ok=True)

    async def format_and_lint_string(
        self, content: str, language: str | None = None, fix: bool = False
    ) -> FormatAndLintResult:
        """Format and lint a string."""
        format_result = await self.format_string(content, language)
        content_to_lint = format_result.output if format_result.success else content
        lint_result = await self.lint_string(content_to_lint, language, fix)
        return FormatAndLintResult(format_result, lint_result)
