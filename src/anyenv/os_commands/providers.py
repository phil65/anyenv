"""OS-specific command providers using the command classes."""

from __future__ import annotations

import platform
from typing import TYPE_CHECKING, Literal, overload

from .create_directory import (
    MacOSCreateDirectoryCommand,
    UnixCreateDirectoryCommand,
    WindowsCreateDirectoryCommand,
)
from .exists import MacOSExistsCommand, UnixExistsCommand, WindowsExistsCommand
from .file_info import MacOSFileInfoCommand, UnixFileInfoCommand, WindowsFileInfoCommand
from .is_directory import (
    MacOSIsDirectoryCommand,
    UnixIsDirectoryCommand,
    WindowsIsDirectoryCommand,
)
from .is_file import MacOSIsFileCommand, UnixIsFileCommand, WindowsIsFileCommand
from .list_directory import (
    MacOSListDirectoryCommand,
    UnixListDirectoryCommand,
    WindowsListDirectoryCommand,
)
from .remove_path import (
    MacOSRemovePathCommand,
    UnixRemovePathCommand,
    WindowsRemovePathCommand,
)


if TYPE_CHECKING:
    from .base import (
        CreateDirectoryCommand,
        ExistsCommand,
        FileInfoCommand,
        IsDirectoryCommand,
        IsFileCommand,
        ListDirectoryCommand,
        RemovePathCommand,
    )

CommandType = Literal[
    "list_directory",
    "file_info",
    "exists",
    "is_file",
    "is_directory",
    "create_directory",
    "remove_path",
]


class OSCommandProvider:
    """Base class for OS-specific command providers using command classes."""

    def __init__(self) -> None:
        """Initialize the command provider with command instances."""
        self.commands: dict[
            str,
            ListDirectoryCommand
            | FileInfoCommand
            | ExistsCommand
            | IsFileCommand
            | IsDirectoryCommand
            | CreateDirectoryCommand
            | RemovePathCommand,
        ] = {}

    @overload
    def get_command(
        self, command_type: Literal["list_directory"]
    ) -> ListDirectoryCommand: ...

    @overload
    def get_command(self, command_type: Literal["file_info"]) -> FileInfoCommand: ...

    @overload
    def get_command(self, command_type: Literal["exists"]) -> ExistsCommand: ...

    @overload
    def get_command(self, command_type: Literal["is_file"]) -> IsFileCommand: ...

    @overload
    def get_command(
        self, command_type: Literal["is_directory"]
    ) -> IsDirectoryCommand: ...

    @overload
    def get_command(
        self, command_type: Literal["create_directory"]
    ) -> CreateDirectoryCommand: ...

    @overload
    def get_command(self, command_type: Literal["remove_path"]) -> RemovePathCommand: ...

    def get_command(
        self, command_type: CommandType
    ) -> (
        ListDirectoryCommand
        | FileInfoCommand
        | ExistsCommand
        | IsFileCommand
        | IsDirectoryCommand
        | CreateDirectoryCommand
        | RemovePathCommand
    ):
        """Get command instance by type."""
        return self.commands[command_type]


class UnixCommandProvider(OSCommandProvider):
    """Unix/Linux command provider using GNU/POSIX tools."""

    def __init__(self) -> None:
        """Initialize Unix command provider with Unix command instances."""
        super().__init__()
        self.commands = {
            "list_directory": UnixListDirectoryCommand(),
            "file_info": UnixFileInfoCommand(),
            "exists": UnixExistsCommand(),
            "is_file": UnixIsFileCommand(),
            "is_directory": UnixIsDirectoryCommand(),
            "create_directory": UnixCreateDirectoryCommand(),
            "remove_path": UnixRemovePathCommand(),
        }


class MacOSCommandProvider(OSCommandProvider):
    """macOS command provider using BSD tools."""

    def __init__(self) -> None:
        """Initialize macOS command provider with macOS command instances."""
        super().__init__()
        self.commands = {
            "list_directory": MacOSListDirectoryCommand(),
            "file_info": MacOSFileInfoCommand(),
            "exists": MacOSExistsCommand(),
            "is_file": MacOSIsFileCommand(),
            "is_directory": MacOSIsDirectoryCommand(),
            "create_directory": MacOSCreateDirectoryCommand(),
            "remove_path": MacOSRemovePathCommand(),
        }


class WindowsCommandProvider(OSCommandProvider):
    """Windows command provider using PowerShell and CMD."""

    def __init__(self) -> None:
        """Initialize Windows command provider with Windows command instances."""
        super().__init__()
        self.commands = {
            "list_directory": WindowsListDirectoryCommand(),
            "file_info": WindowsFileInfoCommand(),
            "exists": WindowsExistsCommand(),
            "is_file": WindowsIsFileCommand(),
            "is_directory": WindowsIsDirectoryCommand(),
            "create_directory": WindowsCreateDirectoryCommand(),
            "remove_path": WindowsRemovePathCommand(),
        }


def get_os_command_provider(
    system: Literal["Windows", "Darwin", "Linux"] | None = None,
) -> OSCommandProvider:
    """Auto-detect OS and return appropriate command provider.

    Args:
        system: The system to use. If None, the current system is used.

    Returns:
        OS-specific command provider based on current platform
    """
    system_ = system or platform.system()

    if system_ == "Windows":
        return WindowsCommandProvider()
    if system_ == "Darwin":  # macOS
        return MacOSCommandProvider()
    # Linux and other Unix-like systems
    return UnixCommandProvider()
