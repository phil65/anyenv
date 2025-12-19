"""Base dataclasses for LSP server configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
import posixpath
from typing import TYPE_CHECKING, Any, Literal


if TYPE_CHECKING:
    import os

    from fsspec.asyn import AsyncFileSystem  # type: ignore[import-untyped]


@dataclass
class RootDetection:
    """How to detect project root for LSP.

    Args:
        include_patterns: File patterns that indicate project root (e.g., ["pyproject.toml"])
        exclude_patterns: If these are found, skip this LSP (e.g., ["deno.json"] for typescript)
        workspace_marker: Content marker for workspace detection (e.g., "[workspace]" in Cargo.toml)
    """

    include_patterns: list[str]
    exclude_patterns: list[str] | None = None
    workspace_marker: str | None = None


@dataclass
class NpmInstall:
    """Install via npm/bun/pnpm."""

    package: str
    entry_path: str  # relative path from node_modules, e.g., "pyright/dist/pyright-langserver.js"


@dataclass
class GoInstall:
    """Install via go install."""

    package: str  # e.g., "golang.org/x/tools/gopls@latest"


@dataclass
class CargoInstall:
    """Install via cargo install."""

    package: str


@dataclass
class DotnetInstall:
    """Install via dotnet tool install."""

    package: str


@dataclass
class GemInstall:
    """Install via gem install."""

    package: str


@dataclass
class GitHubRelease:
    """Download binary from GitHub releases.

    Args:
        repo: Repository in "owner/repo" format
        asset_pattern: Pattern with placeholders: {version}, {arch}, {platform}, {ext}
        binary_name: Name of the binary after extraction
        extract_subdir: Subdirectory within archive containing the binary
    """

    repo: str
    asset_pattern: str
    binary_name: str
    extract_subdir: str | None = None


@dataclass
class Diagnostic:
    """A single diagnostic message from a tool."""

    file: str
    line: int
    column: int
    severity: Literal["error", "warning", "info", "hint"]
    message: str
    source: str
    code: str | None = None
    end_line: int | None = None
    end_column: int | None = None


@dataclass
class DiagnosticsResult:
    """Result of running diagnostics."""

    diagnostics: list[Diagnostic]
    success: bool
    duration: float
    error: str | None = None


@dataclass
class CLIDiagnosticConfig:
    """CLI configuration for running diagnostics without full LSP.

    Args:
        command: Command to run (may differ from LSP command)
        args: Arguments with {files} placeholder for file paths
        output_format: Expected output format
    """

    command: str
    args: list[str]
    output_format: Literal["json", "text"] = "json"


@dataclass
class LSPServerInfo:
    """Static configuration for an LSP server.

    Subclass and override `resolve_root` and/or `resolve_initialization` for
    servers that need custom behavior beyond the declarative configuration.

    Args:
        id: Unique identifier for this server
        extensions: File extensions this server handles (e.g., [".py", ".pyi"])
        root_detection: Configuration for finding project root
        command: Primary command to run the server
        args: Additional command-line arguments
        npm_install: npm installation config
        go_install: Go installation config
        cargo_install: Cargo installation config
        dotnet_install: .NET tool installation config
        gem_install: Ruby gem installation config
        github_release: GitHub release download config
        initialization: LSP initialization options sent to server
        env: Environment variables for the server process
        global_server: If True, use single global instance instead of per-project
        cli_diagnostics: CLI fallback for diagnostics
    """

    id: str
    extensions: list[str]
    root_detection: RootDetection
    command: str
    args: list[str] = field(default_factory=list)

    # Installation options (None = must be pre-installed)
    npm_install: NpmInstall | None = None
    go_install: GoInstall | None = None
    cargo_install: CargoInstall | None = None
    dotnet_install: DotnetInstall | None = None
    gem_install: GemInstall | None = None
    github_release: GitHubRelease | None = None
    # LSP initialization settings (static)
    initialization: dict[str, Any] = field(default_factory=dict)
    # Environment variables
    env: dict[str, str] = field(default_factory=dict)
    # If True, single global instance (not per-project)
    global_server: bool = False
    # CLI diagnostic fallback
    cli_diagnostics: CLIDiagnosticConfig | None = None

    def can_handle(self, extension: str) -> bool:
        """Check if this server handles the given file extension."""
        ext = extension if extension.startswith(".") else f".{extension}"
        return ext.lower() in [e.lower() for e in self.extensions]

    @property
    def has_auto_install(self) -> bool:
        """Check if this server can be auto-installed."""
        return any([
            self.npm_install,
            self.go_install,
            self.cargo_install,
            self.dotnet_install,
            self.gem_install,
            self.github_release,
        ])

    @property
    def has_cli_diagnostics(self) -> bool:
        """Check if this server supports CLI diagnostics."""
        return self.cli_diagnostics is not None

    async def resolve_root(
        self,
        file_path: str,
        project_root: str,
        fs: AsyncFileSystem,
    ) -> str | None:
        """Resolve the LSP root directory for a given file.

        Default implementation searches upward from file_path for include_patterns,
        respecting exclude_patterns. Override for custom behavior (e.g., workspace detection).

        Args:
            file_path: The file being edited
            project_root: The overall project/workspace root (stop boundary)
            fs: Filesystem to use for file operations

        Returns:
            The resolved root directory, or None if this LSP shouldn't be used
        """
        if self.root_detection.exclude_patterns:
            excluded = await self._find_nearest(
                posixpath.dirname(file_path),
                self.root_detection.exclude_patterns,
                project_root,
                fs,
            )
            if excluded:
                return None

        found = await self._find_nearest(
            posixpath.dirname(file_path),
            self.root_detection.include_patterns,
            project_root,
            fs,
        )
        return posixpath.dirname(found) if found else project_root

    async def resolve_initialization(self, root: str, fs: AsyncFileSystem) -> dict[str, Any]:
        """Resolve dynamic LSP initialization options.

        Default implementation returns the static `initialization` dict.
        Override for dynamic behavior (e.g., detecting virtualenv, tsdk path).

        Args:
            root: The resolved LSP root directory
            fs: Filesystem to use for file operations
        """
        return dict(self.initialization)

    async def resolve_env(self, root: str, fs: AsyncFileSystem) -> dict[str, str]:
        """Resolve environment variables for the server process.

        Default implementation returns the static `env` dict.
        Override for dynamic behavior.

        Args:
            root: The resolved LSP root directory
            fs: Filesystem to use for file operations
        """
        return dict(self.env)

    async def _find_nearest(
        self,
        start: str,
        patterns: list[str],
        stop: str,
        fs: AsyncFileSystem,
    ) -> str | None:
        """Find the nearest file matching any pattern, searching upward.

        Args:
            start: Directory to start searching from
            patterns: Glob patterns to match
            stop: Directory to stop searching at (inclusive)
            fs: Filesystem to use for file operations
        """
        import posixpath

        current = start.rstrip("/")
        stop = stop.rstrip("/")

        while True:
            for pattern in patterns:
                full_pattern = posixpath.join(current, pattern)
                try:
                    if matches := await fs._glob(full_pattern):  # noqa: SLF001
                        return matches[0]  # type: ignore[no-any-return] # pyright: ignore[reportArgumentType]
                except Exception:  # noqa: BLE001
                    # Filesystem might not support glob, try exists
                    try:
                        path = posixpath.join(current, pattern)
                        if await fs._exists(path):  # noqa: SLF001
                            return path
                    except Exception:  # noqa: BLE001
                        pass

            parent = posixpath.dirname(current)
            if current in (stop, parent) or current == fs.root_marker:
                break
            current = parent

        return None

    def get_full_command(self) -> list[str]:
        """Get the full command with arguments."""
        return [self.command, *self.args]

    def get_env(self, base_env: dict[str, str] | os._Environ[str] | None = None) -> dict[str, str]:
        """Get environment variables, merged with optional base environment."""
        if base_env is None:
            return dict(self.env)
        result = dict(base_env)
        result.update(self.env)
        return result

    def build_diagnostic_command(self, files: list[str]) -> str:
        """Build the CLI command for running diagnostics.

        Args:
            files: List of file paths to check

        Returns:
            The command string to execute
        """
        if not self.cli_diagnostics:
            msg = f"No CLI diagnostics configured for {self.id}"
            raise ValueError(msg)

        file_str = " ".join(files)
        args = [arg.replace("{files}", file_str) for arg in self.cli_diagnostics.args]
        return " ".join([self.cli_diagnostics.command, *args])

    def parse_diagnostics(self, stdout: str, stderr: str) -> list[Diagnostic]:
        """Parse CLI output into diagnostics.

        Override for custom output formats. Default handles common JSON formats.

        Args:
            stdout: Standard output from the command
            stderr: Standard error from the command
        """
        diagnostics: list[Diagnostic] = []

        if not self.cli_diagnostics:
            return diagnostics

        if self.cli_diagnostics.output_format == "json":
            diagnostics = self._parse_json_diagnostics(stdout)

        return diagnostics

    def _parse_json_diagnostics(self, output: str) -> list[Diagnostic]:
        """Parse JSON diagnostic output. Override for tool-specific formats."""
        return []


def severity_from_string(severity: str) -> Literal["error", "warning", "info", "hint"]:
    """Convert severity string to Diagnostic severity."""
    severity = severity.lower()
    match severity:
        case "error" | "err":
            return "error"
        case "warning" | "warn":
            return "warning"
        case "info" | "information":
            return "info"
        case "hint" | "note":
            return "hint"
        case _:
            return "warning"
