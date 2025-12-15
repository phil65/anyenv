"""File info command implementations for different operating systems."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from .base import FileInfoCommand
from .models import FileInfo


# Constants for parsing file info output
MIN_LS_PARTS = 9  # Minimum parts for valid ls -la line with 3-part timestamp
MIN_LS_PARTS_2_TIMESTAMP = 8  # Parts needed for 2-part timestamp format
EXPECTED_POWERSHELL_PARTS = 4


class UnixFileInfoCommand(FileInfoCommand):
    """Unix/Linux file info command implementation using ls -la."""

    def create_command(self, path: str) -> str:
        """Generate ls -la command for file info.

        Uses ls -la instead of stat to avoid shell expansion issues with
        format specifiers like %s, %F, etc.

        Args:
            path: Path to get information about

        Returns:
            The ls command string
        """
        return f'ls -lad "{path}"'

    def parse_command(self, output: str, path: str) -> FileInfo:
        """Parse ls -la output for a single file/directory.

        Args:
            output: Raw ls -la command output
            path: Original path requested

        Returns:
            FileInfo object with parsed information
        """
        line = output.strip()
        if not line:
            msg = f"Empty output for path: {path}"
            raise ValueError(msg)

        parts = line.split()
        if len(parts) < MIN_LS_PARTS_2_TIMESTAMP:
            msg = f"Unexpected ls output format: {output}"
            raise ValueError(msg)

        permissions = parts[0]
        size = int(parts[4]) if parts[4].isdigit() else 0

        # Determine file type from permissions
        file_type: Literal["file", "directory", "link"]
        if permissions.startswith("d"):
            file_type = "directory"
        elif permissions.startswith("l"):
            file_type = "link"
        else:
            file_type = "file"

        # Extract timestamp - handle different formats
        # Format can be: "Mon DD HH:MM" or "Mon DD YYYY" or "YYYY-MM-DD HH:MM"
        if len(parts) >= MIN_LS_PARTS:
            # 3-part timestamp: month day time/year
            timestamp_str = f"{parts[5]} {parts[6]} {parts[7]}"
        else:
            # 2-part timestamp fallback
            timestamp_str = f"{parts[5]} {parts[6]}"

        # Convert timestamp to unix time (approximate - ls doesn't give precise timestamps)
        # For now, just use 0 since we can't reliably parse all date formats
        mtime = 0

        return FileInfo(
            name=Path(path).name,
            path=path,
            type=file_type,
            size=size,
            mtime=mtime,
            permissions=permissions,
            timestamp=timestamp_str,
        )


class MacOSFileInfoCommand(FileInfoCommand):
    """macOS file info command implementation using ls -la."""

    def create_command(self, path: str) -> str:
        """Generate ls -la command for file info.

        Uses ls -la instead of stat to avoid shell expansion issues with
        format specifiers.

        Args:
            path: Path to get information about

        Returns:
            The ls command string
        """
        return f'ls -lad "{path}"'

    def parse_command(self, output: str, path: str) -> FileInfo:
        """Parse ls -la output for a single file/directory.

        BSD ls output format is same as Unix.

        Args:
            output: Raw ls -la command output
            path: Original path requested

        Returns:
            FileInfo object with parsed information
        """
        # BSD ls output format is same as Unix
        unix_cmd = UnixFileInfoCommand()
        return unix_cmd.parse_command(output, path)


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


if __name__ == "__main__":
    import subprocess

    cmd = UnixFileInfoCommand()
    cmd_str = cmd.create_command(".")
    result = subprocess.run(cmd_str, shell=True, capture_output=True, text=True)
    info = cmd.parse_command(result.stdout, ".")
    print(f"{info.name}: {info.type}, {info.size} bytes")
