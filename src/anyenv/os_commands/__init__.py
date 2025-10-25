"""OS-specific terminal command abstractions for cross-platform filesystem operations.

This package provides a clean abstraction layer for executing OS-specific terminal
commands across Unix/Linux, macOS, and Windows platforms. Commands are grouped
by OS and individual command types for better organization and maintainability.
"""

from __future__ import annotations

from .base import (
    CreateDirectoryCommand,
    ExistsCommand,
    FileInfoCommand,
    IsDirectoryCommand,
    IsFileCommand,
    ListDirectoryCommand,
    RemovePathCommand,
)
from .models import (
    CommandResult,
    CreateDirectoryResult,
    DirectoryEntry,
    ExistsResult,
    FileInfo,
    RemovePathResult,
)
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
from .providers import (
    MacOSCommandProvider,
    OSCommandProvider,
    UnixCommandProvider,
    WindowsCommandProvider,
    get_os_command_provider,
)
from .remove_path import (
    MacOSRemovePathCommand,
    UnixRemovePathCommand,
    WindowsRemovePathCommand,
)

__all__ = [
    # Models
    "CommandResult",
    # Base classes
    "CreateDirectoryCommand",
    "CreateDirectoryResult",
    "DirectoryEntry",
    "ExistsCommand",
    "ExistsResult",
    "FileInfo",
    "FileInfoCommand",
    "IsDirectoryCommand",
    "IsFileCommand",
    "ListDirectoryCommand",
    "MacOSCommandProvider",
    "MacOSCreateDirectoryCommand",
    "MacOSExistsCommand",
    "MacOSFileInfoCommand",
    "MacOSIsDirectoryCommand",
    "MacOSIsFileCommand",
    "MacOSListDirectoryCommand",
    "MacOSRemovePathCommand",
    # Providers
    "OSCommandProvider",
    "RemovePathCommand",
    "RemovePathResult",
    "UnixCommandProvider",
    # Create directory commands
    "UnixCreateDirectoryCommand",
    # Exists commands
    "UnixExistsCommand",
    # File info commands
    "UnixFileInfoCommand",
    # Is directory commands
    "UnixIsDirectoryCommand",
    # Is file commands
    "UnixIsFileCommand",
    # List directory commands
    "UnixListDirectoryCommand",
    # Remove path commands
    "UnixRemovePathCommand",
    "WindowsCommandProvider",
    "WindowsCreateDirectoryCommand",
    "WindowsExistsCommand",
    "WindowsFileInfoCommand",
    "WindowsIsDirectoryCommand",
    "WindowsIsFileCommand",
    "WindowsListDirectoryCommand",
    "WindowsRemovePathCommand",
    "get_os_command_provider",
]
