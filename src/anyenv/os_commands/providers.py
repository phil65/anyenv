"""OS-specific command providers using the command classes."""

from __future__ import annotations

import platform
from typing import TYPE_CHECKING, Literal, overload

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
from .env_var import MacOSEnvVarCommand, UnixEnvVarCommand, WindowsEnvVarCommand
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
from .pwd import MacOSPwdCommand, UnixPwdCommand, WindowsPwdCommand
from .remove_path import (
    MacOSRemovePathCommand,
    UnixRemovePathCommand,
    WindowsRemovePathCommand,
)
from .which import MacOSWhichCommand, UnixWhichCommand, WindowsWhichCommand


if TYPE_CHECKING:
    from .base import (
        Base64EncodeCommand,
        CopyPathCommand,
        CreateDirectoryCommand,
        EnvVarCommand,
        ExistsCommand,
        FileInfoCommand,
        FindCommand,
        IsDirectoryCommand,
        IsFileCommand,
        ListDirectoryCommand,
        PwdCommand,
        RemovePathCommand,
        WhichCommand,
    )

CommandType = Literal[
    "list_directory",
    "file_info",
    "exists",
    "is_file",
    "is_directory",
    "create_directory",
    "remove_path",
    "copy_path",
    "base64_encode",
    "which",
    "pwd",
    "env_var",
    "find",
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
            | RemovePathCommand
            | CopyPathCommand
            | Base64EncodeCommand
            | WhichCommand
            | PwdCommand
            | EnvVarCommand
            | FindCommand,
        ] = {}

    @overload
    def get_command(self, command_type: Literal["list_directory"]) -> ListDirectoryCommand: ...

    @overload
    def get_command(self, command_type: Literal["file_info"]) -> FileInfoCommand: ...

    @overload
    def get_command(self, command_type: Literal["exists"]) -> ExistsCommand: ...

    @overload
    def get_command(self, command_type: Literal["is_file"]) -> IsFileCommand: ...

    @overload
    def get_command(self, command_type: Literal["is_directory"]) -> IsDirectoryCommand: ...

    @overload
    def get_command(self, command_type: Literal["create_directory"]) -> CreateDirectoryCommand: ...

    @overload
    def get_command(self, command_type: Literal["remove_path"]) -> RemovePathCommand: ...

    @overload
    def get_command(self, command_type: Literal["copy_path"]) -> CopyPathCommand: ...

    @overload
    def get_command(self, command_type: Literal["base64_encode"]) -> Base64EncodeCommand: ...

    @overload
    def get_command(self, command_type: Literal["which"]) -> WhichCommand: ...

    @overload
    def get_command(self, command_type: Literal["pwd"]) -> PwdCommand: ...

    @overload
    def get_command(self, command_type: Literal["env_var"]) -> EnvVarCommand: ...

    @overload
    def get_command(self, command_type: Literal["find"]) -> FindCommand: ...

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
        | CopyPathCommand
        | Base64EncodeCommand
        | WhichCommand
        | PwdCommand
        | EnvVarCommand
        | FindCommand
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
            "copy_path": UnixCopyPathCommand(),
            "base64_encode": UnixBase64EncodeCommand(),
            "which": UnixWhichCommand(),
            "pwd": UnixPwdCommand(),
            "env_var": UnixEnvVarCommand(),
            "find": UnixFindCommand(),
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
            "copy_path": MacOSCopyPathCommand(),
            "base64_encode": MacOSBase64EncodeCommand(),
            "which": MacOSWhichCommand(),
            "pwd": MacOSPwdCommand(),
            "env_var": MacOSEnvVarCommand(),
            "find": MacOSFindCommand(),
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
            "copy_path": WindowsCopyPathCommand(),
            "base64_encode": WindowsBase64EncodeCommand(),
            "which": WindowsWhichCommand(),
            "pwd": WindowsPwdCommand(),
            "env_var": WindowsEnvVarCommand(),
            "find": WindowsFindCommand(),
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
