"""File info command implementations for different operating systems."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from .base import FileInfoCommand
from .models import FileInfo


# Constants for parsing file info output
EXPECTED_STAT_PARTS = 4
EXPECTED_POWERSHELL_PARTS = 4


class UnixFileInfoCommand(FileInfoCommand):
    """Unix/Linux file info command implementation."""

    def create_command(self, path: str) -> str:
        """Generate GNU stat command.

        Args:
            path: Path to get information about

        Returns:
            The stat command string
        """
        return f'stat -c "%n|%s|%F|%Y" "{path}"'

    def parse_command(self, output: str, path: str) -> FileInfo:
        """Parse GNU stat output format: name|size|file_type|mtime.

        Args:
            output: Raw stat command output
            path: Original path requested

        Returns:
            FileInfo object with parsed information
        """
        parts = output.strip().split("|")
        if len(parts) < EXPECTED_STAT_PARTS:
            msg = f"Unexpected stat output format: {output}"
            raise ValueError(msg)

        name = Path(path).name
        size = int(parts[1]) if parts[1].isdigit() else 0
        file_type_str = parts[2].lower()
        mtime = int(parts[3]) if parts[3].isdigit() else 0

        # Map stat file types to our types
        file_type: Literal["file", "directory", "link"]
        if "directory" in file_type_str:
            file_type = "directory"
        elif "symbolic link" in file_type_str:
            file_type = "link"
        else:
            file_type = "file"

        return FileInfo(
            name=name,
            path=path,
            type=file_type,
            size=size,
            mtime=mtime,
        )


class MacOSFileInfoCommand(FileInfoCommand):
    """macOS file info command implementation."""

    def create_command(self, path: str) -> str:
        """Generate BSD stat command.

        Args:
            path: Path to get information about

        Returns:
            The stat command string
        """
        return f'stat -f "%N|%z|%HT|%m" "{path}"'

    def parse_command(self, output: str, path: str) -> FileInfo:
        """Parse BSD stat output format: name|size|file_type|mtime.

        Args:
            output: Raw stat command output
            path: Original path requested

        Returns:
            FileInfo object with parsed information
        """
        parts = output.strip().split("|")
        if len(parts) < EXPECTED_STAT_PARTS:
            msg = f"Unexpected stat output format: {output}"
            raise ValueError(msg)

        name = Path(path).name
        size = int(parts[1]) if parts[1].isdigit() else 0
        file_type_str = parts[2].lower()
        mtime = int(parts[3]) if parts[3].isdigit() else 0

        # Map BSD file types to our types
        file_type: Literal["file", "directory", "link"]
        if "directory" in file_type_str:
            file_type = "directory"
        elif "symbolic link" in file_type_str:
            file_type = "link"
        else:
            file_type = "file"

        return FileInfo(
            name=name,
            path=path,
            type=file_type,
            size=size,
            mtime=mtime,
        )


class WindowsFileInfoCommand(FileInfoCommand):
    """Windows file info command implementation."""

    def create_command(self, path: str) -> str:
        """Generate PowerShell file info command.

        Args:
            path: Path to get information about

        Returns:
            The PowerShell command string
        """
        return (
            f'powershell -c "'
            f'$item = Get-Item \\"{path}\\" -ErrorAction Stop; '
            f'$item.Name + \\"||\\" + $item.Length + \\"||\\" + '
            f'($item.GetType().Name) + \\"||\\" + '
            f'[int][double]::Parse($item.LastWriteTime.ToString(\\"yyyyMMddHHmmss\\"))'
            f'"'
        )

    def parse_command(self, output: str, path: str) -> FileInfo:
        """Parse PowerShell output format: name||size||type||mtime.

        Args:
            output: Raw PowerShell command output
            path: Original path requested

        Returns:
            FileInfo object with parsed information
        """
        parts = output.strip().split("||")
        if len(parts) < EXPECTED_POWERSHELL_PARTS:
            msg = f"Unexpected PowerShell output format: {output}"
            raise ValueError(msg)

        file_type: Literal["file", "directory", "link"] = (
            "directory" if "directory" in parts[2].lower() else "file"
        )

        return FileInfo(
            name=parts[0],
            path=path,
            type=file_type,
            size=int(parts[1]) if parts[1].isdigit() else 0,
            mtime=int(parts[3]) if parts[3].isdigit() else 0,
        )
