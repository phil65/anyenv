"""OS-specific terminal command abstractions for cross-platform filesystem operations.

This package provides a clean abstraction layer for executing OS-specific terminal
commands across Unix/Linux, macOS, and Windows platforms. Commands are grouped
by OS and individual command types for better organization and maintainability.
"""

from __future__ import annotations

from .base import (
    Base64EncodeCommand,
    CopyPathCommand,
    CreateDirectoryCommand,
    ExistsCommand,
    FileInfoCommand,
    FindCommand,
    IsDirectoryCommand,
    IsFileCommand,
    ListDirectoryCommand,
    PwdCommand,
    RemovePathCommand,
    WhichCommand,
    EnvVarCommand,
)
from .models import (
    CommandResult,
    CreateDirectoryResult,
    DirectoryEntry,
    ExistsResult,
    FileInfo,
    RemovePathResult,
)
from .base64_encode import (
    MacOSBase64EncodeCommand,
    UnixBase64EncodeCommand,
    WindowsBase64EncodeCommand,
)
from .copy_path import (
    MacOSCopyPathCommand,
    UnixCopyPathCommand,
    WindowsCopyPathCommand,
)
from .create_directory import (
    MacOSCreateDirectoryCommand,
    UnixCreateDirectoryCommand,
    WindowsCreateDirectoryCommand,
)
from .exists import MacOSExistsCommand, UnixExistsCommand, WindowsExistsCommand
from .file_info import MacOSFileInfoCommand, UnixFileInfoCommand, WindowsFileInfoCommand
from .find import MacOSFindCommand, UnixFindCommand, WindowsFindCommand
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
from .pwd import (
    MacOSPwdCommand,
    UnixPwdCommand,
    WindowsPwdCommand,
)
from .env_var import (
    MacOSEnvVarCommand,
    UnixEnvVarCommand,
    WindowsEnvVarCommand,
)
from .which import (
    MacOSWhichCommand,
    UnixWhichCommand,
    WindowsWhichCommand,
)
from .batch import CommandBatch

__all__ = [
    # Base classes
    "Base64EncodeCommand",
    # Batch execution
    "CommandBatch",
    # Models
    "CommandResult",
    "CopyPathCommand",
    "CreateDirectoryCommand",
    "CreateDirectoryResult",
    "DirectoryEntry",
    # EnvVar commands
    "EnvVarCommand",
    "ExistsCommand",
    "ExistsResult",
    "FileInfo",
    "FileInfoCommand",
    # Find command
    "FindCommand",
    "IsDirectoryCommand",
    "IsFileCommand",
    "ListDirectoryCommand",
    "MacOSBase64EncodeCommand",
    "MacOSCommandProvider",
    "MacOSCopyPathCommand",
    "MacOSCreateDirectoryCommand",
    "MacOSEnvVarCommand",
    "MacOSExistsCommand",
    "MacOSFileInfoCommand",
    "MacOSFindCommand",
    "MacOSIsDirectoryCommand",
    "MacOSIsFileCommand",
    "MacOSListDirectoryCommand",
    "MacOSPwdCommand",
    "MacOSRemovePathCommand",
    "MacOSWhichCommand",
    # Providers
    "OSCommandProvider",
    # Pwd commands
    "PwdCommand",
    "RemovePathCommand",
    "RemovePathResult",
    # Base64 encode commands
    "UnixBase64EncodeCommand",
    "UnixCommandProvider",
    # Copy path commands
    "UnixCopyPathCommand",
    # Create directory commands
    "UnixCreateDirectoryCommand",
    "UnixEnvVarCommand",
    # Exists commands
    "UnixExistsCommand",
    # File info commands
    "UnixFileInfoCommand",
    # Find commands
    "UnixFindCommand",
    # Is directory commands
    "UnixIsDirectoryCommand",
    # Is file commands
    "UnixIsFileCommand",
    # List directory commands
    "UnixListDirectoryCommand",
    "UnixPwdCommand",
    # Remove path commands
    "UnixRemovePathCommand",
    "UnixWhichCommand",
    # Which commands
    "WhichCommand",
    "WindowsBase64EncodeCommand",
    "WindowsCommandProvider",
    "WindowsCopyPathCommand",
    "WindowsCreateDirectoryCommand",
    "WindowsEnvVarCommand",
    "WindowsExistsCommand",
    "WindowsFileInfoCommand",
    "WindowsFindCommand",
    "WindowsIsDirectoryCommand",
    "WindowsIsFileCommand",
    "WindowsListDirectoryCommand",
    "WindowsPwdCommand",
    "WindowsRemovePathCommand",
    "WindowsWhichCommand",
    "get_os_command_provider",
]
