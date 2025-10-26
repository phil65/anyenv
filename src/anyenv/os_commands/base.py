"""Base protocol and classes for OS-specific commands."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Protocol


if TYPE_CHECKING:
    from .models import DirectoryEntry, FileInfo


class CommandProtocol(Protocol):
    """Protocol for all OS commands."""

    def create_command(self, *args: Any, **kwargs: Any) -> str:
        """Generate the OS-specific command string."""
        ...

    def parse_command(
        self, output: str, exit_code: int = 0, *args: Any, **kwargs: Any
    ) -> Any:
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
