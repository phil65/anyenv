"""OS-specific command providers using the command classes."""

from __future__ import annotations

import platform
from typing import TYPE_CHECKING, Any, Literal

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
    from typing import Any


class OSCommandProvider:
    """Base class for OS-specific command providers using command classes."""

    def __init__(self) -> None:
        """Initialize the command provider with command instances."""
        self.list_directory: Any
        self.file_info: Any
        self.exists: Any
        self.is_file: Any
        self.is_directory: Any
        self.create_directory: Any
        self.remove_path: Any

    def list_directory_cmd(self, path: str = "", detailed: bool = True) -> str:
        """Create directory listing command."""
        return self.list_directory.create_command(path=path, detailed=detailed)

    def parse_list_output(
        self, output: str, path: str, detailed: bool
    ) -> list[Any] | list[str]:
        """Parse directory listing output."""
        return self.list_directory.parse_command(output, path=path, detailed=detailed)

    def file_info_cmd(self, path: str) -> str:
        """Create file info command."""
        return self.file_info.create_command(path=path)

    def parse_file_info(self, output: str, path: str) -> Any:
        """Parse file info output."""
        return self.file_info.parse_command(output, path=path)

    def exists_cmd(self, path: str) -> str:
        """Create existence test command."""
        return self.exists.create_command(path=path)

    def parse_exists_result(self, output: str, exit_code: int) -> bool:
        """Parse existence test result."""
        return self.exists.parse_command(output, exit_code)

    def is_file_cmd(self, path: str) -> str:
        """Create file type test command."""
        return self.is_file.create_command(path=path)

    def parse_file_test_result(self, output: str, exit_code: int) -> bool:
        """Parse file type test result."""
        return self.is_file.parse_command(output, exit_code)

    def is_directory_cmd(self, path: str) -> str:
        """Create directory test command."""
        return self.is_directory.create_command(path=path)

    def parse_directory_test_result(self, output: str, exit_code: int) -> bool:
        """Parse directory test result."""
        return self.is_directory.parse_command(output, exit_code)

    def create_directory_cmd(self, path: str, parents: bool = True) -> str:
        """Create directory creation command."""
        return self.create_directory.create_command(path=path, parents=parents)

    def parse_create_result(self, output: str, exit_code: int) -> bool:
        """Parse directory creation result."""
        return self.create_directory.parse_command(output, exit_code)

    def remove_path_cmd(self, path: str, recursive: bool = False) -> str:
        """Create removal command."""
        return self.remove_path.create_command(path=path, recursive=recursive)

    def parse_remove_result(self, output: str, exit_code: int) -> bool:
        """Parse removal result."""
        return self.remove_path.parse_command(output, exit_code)


class UnixCommandProvider(OSCommandProvider):
    """Unix/Linux command provider using GNU/POSIX tools."""

    def __init__(self) -> None:
        """Initialize Unix command provider with Unix command instances."""
        super().__init__()
        self.list_directory = UnixListDirectoryCommand()
        self.file_info = UnixFileInfoCommand()
        self.exists = UnixExistsCommand()
        self.is_file = UnixIsFileCommand()
        self.is_directory = UnixIsDirectoryCommand()
        self.create_directory = UnixCreateDirectoryCommand()
        self.remove_path = UnixRemovePathCommand()


class MacOSCommandProvider(OSCommandProvider):
    """macOS command provider using BSD tools."""

    def __init__(self) -> None:
        """Initialize macOS command provider with macOS command instances."""
        super().__init__()
        self.list_directory = MacOSListDirectoryCommand()
        self.file_info = MacOSFileInfoCommand()
        self.exists = MacOSExistsCommand()
        self.is_file = MacOSIsFileCommand()
        self.is_directory = MacOSIsDirectoryCommand()
        self.create_directory = MacOSCreateDirectoryCommand()
        self.remove_path = MacOSRemovePathCommand()


class WindowsCommandProvider(OSCommandProvider):
    """Windows command provider using PowerShell and CMD."""

    def __init__(self) -> None:
        """Initialize Windows command provider with Windows command instances."""
        super().__init__()
        self.list_directory = WindowsListDirectoryCommand()
        self.file_info = WindowsFileInfoCommand()
        self.exists = WindowsExistsCommand()
        self.is_file = WindowsIsFileCommand()
        self.is_directory = WindowsIsDirectoryCommand()
        self.create_directory = WindowsCreateDirectoryCommand()
        self.remove_path = WindowsRemovePathCommand()


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
