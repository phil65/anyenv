"""Base protocol and classes for OS-specific commands."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Literal, Protocol


if TYPE_CHECKING:
    from .models import DirectoryEntry, FileInfo


class CommandProtocol(Protocol):
    """Protocol for all OS commands."""

    def create_command(self, *args: Any, **kwargs: Any) -> str:
        """Generate the OS-specific command string."""
        ...

    def parse_command(self, output: str, exit_code: int = 0, *args: Any, **kwargs: Any) -> Any:
        """Parse the command output."""
        ...


class ListDirectoryCommand(ABC):
    """Base class for list directory commands."""

    @abstractmethod
    def create_command(self, path: str = "") -> str:
        """Generate directory listing command."""

    @abstractmethod
    def parse_command(self, output: str, path: str = "") -> list[DirectoryEntry]:
        """Parse directory listing output."""


class FileInfoCommand(ABC):
    """Base class for file info commands."""

    @abstractmethod
    def create_command(self, path: str) -> str:
        """Generate file info command."""

    @abstractmethod
    def parse_command(self, output: str, path: str) -> FileInfo:
        """Parse file info output."""


class ExistsCommand(ABC):
    """Base class for exists commands."""

    @abstractmethod
    def create_command(self, path: str) -> str:
        """Generate exists test command."""

    @abstractmethod
    def parse_command(self, output: str, exit_code: int = 0) -> bool:
        """Parse exists test result."""


class IsFileCommand(ABC):
    """Base class for is file commands."""

    @abstractmethod
    def create_command(self, path: str) -> str:
        """Generate file test command."""

    @abstractmethod
    def parse_command(self, output: str, exit_code: int = 0) -> bool:
        """Parse file test result."""


class IsDirectoryCommand(ABC):
    """Base class for is directory commands."""

    @abstractmethod
    def create_command(self, path: str) -> str:
        """Generate directory test command."""

    @abstractmethod
    def parse_command(self, output: str, exit_code: int = 0) -> bool:
        """Parse directory test result."""


class CreateDirectoryCommand(ABC):
    """Base class for create directory commands."""

    @abstractmethod
    def create_command(self, path: str, parents: bool = True) -> str:
        """Generate directory creation command."""

    @abstractmethod
    def parse_command(self, output: str, exit_code: int = 0) -> bool:
        """Parse directory creation result."""


class RemovePathCommand(ABC):
    """Base class for remove path commands."""

    @abstractmethod
    def create_command(self, path: str, recursive: bool = False) -> str:
        """Generate removal command."""

    @abstractmethod
    def parse_command(self, output: str, exit_code: int = 0) -> bool:
        """Parse removal result."""


class Base64EncodeCommand(ABC):
    """Base class for base64 encode commands."""

    @abstractmethod
    def create_command(self, path: str) -> str:
        """Generate base64 encode command."""

    @abstractmethod
    def parse_command(self, output: str) -> bytes:
        """Parse base64 output and return decoded bytes."""


class WhichCommand(ABC):
    """Base class for which/where commands to locate executables."""

    @abstractmethod
    def create_command(self, executable: str) -> str:
        """Generate command to find executable path."""

    @abstractmethod
    def parse_command(self, output: str, exit_code: int = 0) -> str | None:
        """Parse output and return executable path or None if not found."""


class PwdCommand(ABC):
    """Base class for pwd (print working directory) commands."""

    @abstractmethod
    def create_command(self) -> str:
        """Generate command to get current working directory."""

    @abstractmethod
    def parse_command(self, output: str, exit_code: int = 0) -> str | None:
        """Parse output and return current directory or None on failure."""


class EnvVarCommand(ABC):
    """Base class for environment variable commands."""

    @abstractmethod
    def create_command(self, name: str) -> str:
        """Generate command to get environment variable value."""

    @abstractmethod
    def parse_command(self, output: str, exit_code: int = 0) -> str | None:
        """Parse output and return variable value or None if not set."""


class CopyPathCommand(ABC):
    """Base class for copy path commands."""

    @abstractmethod
    def create_command(self, source: str, destination: str, recursive: bool = False) -> str:
        """Generate copy command.

        Args:
            source: Source path to copy from
            destination: Destination path to copy to
            recursive: Whether to copy directories recursively
        """

    @abstractmethod
    def parse_command(self, output: str, exit_code: int = 0) -> bool:
        """Parse copy result.

        Returns:
            True if copy was successful, False otherwise
        """


class FindCommand(ABC):
    """Base class for recursive find commands.

    Used for efficiently finding files/directories recursively in a single
    command, rather than walking the tree with multiple list operations.
    """

    @abstractmethod
    def create_command(
        self,
        path: str,
        pattern: str | None = None,
        maxdepth: int | None = None,
        file_type: Literal["file", "directory", "all"] = "all",
        with_stats: bool = True,
    ) -> str:
        """Generate recursive find command.

        Args:
            path: Directory to search in
            pattern: Glob pattern for name matching (e.g., "*.py")
            maxdepth: Maximum directory depth to descend (None for unlimited)
            file_type: Filter by type - files only, directories only, or all
            with_stats: Include file stats (size, mtime, type, permissions)
        """

    @abstractmethod
    def parse_command(self, output: str, base_path: str = "") -> list[DirectoryEntry]:
        """Parse find output into DirectoryEntry objects.

        Args:
            output: Raw command output
            base_path: Base path used in the find command

        Returns:
            List of DirectoryEntry objects for found items
        """
