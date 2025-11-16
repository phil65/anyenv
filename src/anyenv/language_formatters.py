"""Language formatters with anyenv execution environments."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from anyenv.code_execution import ExecutionEnvironment, ExecutionEnvironmentStr


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
            from anyenv.code_execution import get_environment

            self._execution_env: ExecutionEnvironment = get_environment(execution_env)  # type: ignore[arg-type]
        else:
            # Direct ExecutionEnvironment instance
            self._execution_env = execution_env

    async def _execute_command(
        self, cmd: list[str]
    ) -> tuple[bool, str, str, float, str | None]:
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

    async def format_string(
        self, content: str, language: str | None = None
    ) -> FormatResult:
        """Format a string by creating a temporary file.

        Args:
            content: String content to format
            language: Language name (pygments lexer name) if extension can't be determined

        Returns:
            FormatResult with formatted content in output field
        """
        # Use primary extension for temp file
        extension = self.extensions[0] if self.extensions else ".txt"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=extension, delete=False
        ) as temp_file:
            temp_file.write(content)
            temp_path = Path(temp_file.name)

        try:
            result = await self.format(temp_path)
            if result.success:
                # Read the formatted content back
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
        # Use primary extension for temp file
        extension = self.extensions[0] if self.extensions else ".txt"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=extension, delete=False
        ) as temp_file:
            temp_file.write(content)
            temp_path = Path(temp_file.name)

        try:
            result = await self.lint(temp_path, fix=fix)
            if result.success and fix:
                # Read the potentially modified content back
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


class PythonFormatter(LanguageFormatter):
    """Python formatter using ruff."""

    @property
    def name(self) -> str:
        """Language name."""
        return "Python"

    @property
    def extensions(self) -> list[str]:
        """Supported file extensions."""
        return [".py", ".pyi"]

    @property
    def pygments_lexers(self) -> list[str]:
        """Pygments lexer names."""
        return ["python", "python3", "py"]

    async def format(self, path: Path) -> FormatResult:
        """Format Python file using ruff."""
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
        """Lint Python file using ruff."""
        cmd = ["uv", "run", "ruff", "check"]
        if fix:
            cmd.extend(["--fix", "--unsafe-fixes"])
        cmd.append(str(path))

        success, stdout, stderr, duration, error_type = await self._execute_command(cmd)

        return LintResult(
            success=success,
            output=stdout,
            errors=stderr,
            fixed_issues=0,  # Could parse output to count fixes
            remaining_issues=0,  # Could parse output to count remaining issues
            duration=duration,
            error_type=error_type,
        )


class TOMLFormatter(LanguageFormatter):
    """TOML formatter using tombi."""

    @property
    def name(self) -> str:
        """Language name."""
        return "TOML"

    @property
    def extensions(self) -> list[str]:
        """Supported file extensions."""
        return [".toml"]

    @property
    def pygments_lexers(self) -> list[str]:
        """Pygments lexer names."""
        return ["toml"]

    async def format(self, path: Path) -> FormatResult:
        """Format TOML file using tombi."""
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
        """Lint TOML file using tombi."""
        # tombi lint doesn't seem to have a --fix option, so we ignore the fix parameter
        cmd = ["uv", "run", "tombi", "lint", str(path)]
        success, stdout, stderr, duration, error_type = await self._execute_command(cmd)

        return LintResult(
            success=success,
            output=stdout,
            errors=stderr,
            fixed_issues=0,
            remaining_issues=0,
            duration=duration,
            error_type=error_type,
        )


class TypeScriptFormatter(LanguageFormatter):
    """TypeScript/JavaScript formatter using biome."""

    @property
    def name(self) -> str:
        """Language name."""
        return "TypeScript"

    @property
    def extensions(self) -> list[str]:
        """Supported file extensions."""
        return [".ts", ".tsx", ".js", ".jsx", ".json"]

    @property
    def pygments_lexers(self) -> list[str]:
        """Pygments lexer names."""
        return ["typescript", "ts", "javascript", "js", "jsx", "tsx", "json"]

    async def format(self, path: Path) -> FormatResult:
        """Format TypeScript/JavaScript file using biome."""
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
        """Lint TypeScript/JavaScript file using biome."""
        cmd = ["biome", "lint"]
        if fix:
            cmd.append("--write")
        cmd.append(str(path))

        success, stdout, stderr, duration, error_type = await self._execute_command(cmd)

        return LintResult(
            success=success,
            output=stdout,
            errors=stderr,
            fixed_issues=0,  # Could parse output to count fixes
            remaining_issues=0,  # Could parse output to count remaining issues
            duration=duration,
            error_type=error_type,
        )


class RustFormatter(LanguageFormatter):
    """Rust formatter using rustfmt and clippy."""

    @property
    def name(self) -> str:
        """Language name."""
        return "Rust"

    @property
    def extensions(self) -> list[str]:
        """Supported file extensions."""
        return [".rs"]

    @property
    def pygments_lexers(self) -> list[str]:
        """Pygments lexer names."""
        return ["rust", "rs"]

    async def format(self, path: Path) -> FormatResult:
        """Format Rust file using rustfmt."""
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
        """Lint Rust file using clippy."""
        cmd = ["cargo", "clippy"]
        if fix:
            cmd.append("--fix")
        cmd.extend(["--", "--", str(path)])

        success, stdout, stderr, duration, error_type = await self._execute_command(cmd)

        return LintResult(
            success=success,
            output=stdout,
            errors=stderr,
            fixed_issues=0,  # Could parse output to count fixes
            remaining_issues=0,  # Could parse output to count remaining issues
            duration=duration,
            error_type=error_type,
        )


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
        self.default_execution_env: ExecutionEnvironment | ExecutionEnvironmentStr = (
            execution_env
        )

    def register(self, formatter: LanguageFormatter) -> None:
        """Register a formatter."""
        self.formatters.append(formatter)

    def register_default_formatters(self) -> None:
        """Register all default formatters with the registry's execution environment."""
        self.register(PythonFormatter(self.default_execution_env))
        self.register(TOMLFormatter(self.default_execution_env))
        self.register(TypeScriptFormatter(self.default_execution_env))
        self.register(RustFormatter(self.default_execution_env))

    def get_formatter(self, path: Path) -> LanguageFormatter | None:
        """Get formatter for given file path."""
        return next((f for f in self.formatters if f.can_handle(path)), None)

    def get_formatter_by_language(self, language: str) -> LanguageFormatter | None:
        """Get formatter for given language name (pygments lexer)."""
        return next((f for f in self.formatters if f.can_handle_language(language)), None)

    def detect_language_from_content(self, content: str) -> str | None:
        """Detect language from content using pygments (if available)."""
        try:
            from pygments.lexers import guess_lexer

            lexer = guess_lexer(content)
            return lexer.name.lower()
        except ImportError:
            return None
        except Exception:  # noqa: BLE001
            # Pygments couldn't detect the language
            return None

    def get_supported_extensions(self) -> list[str]:
        """Get all supported file extensions."""
        return sorted({e for formatter in self.formatters for e in formatter.extensions})


# Example usage and testing
if __name__ == "__main__":

    async def main() -> None:
        """Example usage of language formatters."""
        # Create registry with default subprocess environment
        registry = FormatterRegistry()
        registry.register_default_formatters()

        print(f"Supported extensions: {registry.get_supported_extensions()}")

        # Example with Docker environment
        # Example with Docker environment (if available)
        try:
            from anyenv.code_execution import get_environment

            docker_env = get_environment("docker", image="python:3.13-slim")  # type: ignore
            docker_registry = FormatterRegistry(docker_env)
            docker_registry.register_default_formatters()
        except Exception:  # noqa: BLE001
            print("Docker environment not available")

        # Create test files
        test_py = Path("test.py")
        test_toml = Path("test.toml")

        test_py.write_text("def hello( ):\n    print('world')")
        test_toml.write_text('[section]\nkey="value"')

        try:
            # Test using registry
            py_formatter = registry.get_formatter(test_py)
            if py_formatter:
                result = await py_formatter.format_and_lint(test_py, fix=True)
                print(f"Python format success: {result.format_result.success}")
                print(f"Python lint success: {result.lint_result.success}")
                print(f"Total duration: {result.total_duration:.2f}s")

            toml_formatter = registry.get_formatter(test_toml)
            if toml_formatter:
                result = await toml_formatter.format_and_lint(test_toml)
                print(f"TOML format success: {result.format_result.success}")
                print(f"TOML lint success: {result.lint_result.success}")
                print(f"Total duration: {result.total_duration:.2f}s")

        finally:
            # Cleanup
            test_py.unlink(missing_ok=True)
            test_toml.unlink(missing_ok=True)

    asyncio.run(main())
