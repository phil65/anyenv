"""List directory command implementations for different operating systems."""

from __future__ import annotations

from typing import Literal

from .base import ListDirectoryCommand
from .models import DirectoryEntry


# Constants for parsing directory listings
MIN_LS_PARTS = 7  # Minimum parts for valid ls -la line
MIN_LS_PARTS_3_TIMESTAMP = 9  # Parts needed for 3-part timestamp format
MIN_LS_PARTS_2_TIMESTAMP = 8  # Parts needed for 2-part timestamp format
MIN_WINDOWS_DIR_PARTS = 4  # Minimum parts for Windows dir output


class UnixListDirectoryCommand(ListDirectoryCommand):
    """Unix/Linux list directory command implementation."""

    def create_command(self, path: str = "") -> str:
        """Generate Unix ls command.

        Args:
            path: Directory path to list

        Returns:
            The ls command string
        """
        cmd = "ls -la"
        return f'{cmd} "{path}"' if path else cmd

    def parse_command(
        self,
        output: str,
        path: str = "",
    ) -> list[DirectoryEntry]:
        """Parse Unix ls output.

        Args:
            output: Raw ls command output
            path: Base directory path

        Returns:
            List of DirectoryEntry objects
        """
        lines = output.strip().split("\n")
        if not lines:
            return []

        # Filter out total line and empty lines
        file_lines = [line for line in lines if line and not line.startswith("total ")]

        files: list[DirectoryEntry] = []
        for line in file_lines:
            if not line.strip():
                continue

            parsed = self._parse_detailed_line(line, path)
            if parsed:
                files.append(parsed)

        return files

    def _parse_detailed_line(self, line: str, base_path: str) -> DirectoryEntry | None:
        """Parse detailed ls -la output line."""
        parts = line.split()
        if len(parts) < MIN_LS_PARTS:  # Minimum parts for valid ls -la line
            return None

        permissions = parts[0]
        size = int(parts[4]) if parts[4].isdigit() else 0

        # Handle different timestamp formats (2-part vs 3-part)
        if (
            len(parts) >= MIN_LS_PARTS_3_TIMESTAMP
            and not parts[7].startswith("-")
            and not parts[7].startswith("d")
        ):
            # 3-part timestamp: month day time/year
            timestamp = f"{parts[5]} {parts[6]} {parts[7]}"
            name = " ".join(parts[8:])
        elif len(parts) >= MIN_LS_PARTS_2_TIMESTAMP:
            # 2-part timestamp: date time
            timestamp = f"{parts[5]} {parts[6]}"
            name = " ".join(parts[7:])
        else:
            # Fallback: single part timestamp
            timestamp = parts[5]
            name = " ".join(parts[6:])

        # Determine file type
        file_type: Literal["file", "directory", "link"]
        if permissions.startswith("d"):
            file_type = "directory"
        elif permissions.startswith("l"):
            file_type = "link"
        else:
            file_type = "file"

        # Build full path
        full_path = f"{base_path.rstrip('/')}/{name}" if base_path else name

        return DirectoryEntry(
            name=name,
            path=full_path,
            type=file_type,
            size=size,
            timestamp=timestamp,
            permissions=permissions
            if permissions and not permissions.isspace()
            else None,
        )


class MacOSListDirectoryCommand(ListDirectoryCommand):
    """macOS list directory command implementation."""

    def create_command(self, path: str = "") -> str:
        """Generate BSD ls command (no --time-style support).

        Args:
            path: Directory path to list

        Returns:
            The ls command string
        """
        cmd = "ls -la"
        return f'{cmd} "{path}"' if path else cmd

    def parse_command(
        self,
        output: str,
        path: str = "",
    ) -> list[DirectoryEntry]:
        """Parse BSD ls output (same as Unix).

        Args:
            output: Raw ls command output
            path: Base directory path

        Returns:
            List of DirectoryEntry objects
        """
        # BSD ls output format is same as Unix, just different timestamp format
        unix_cmd = UnixListDirectoryCommand()
        return unix_cmd.parse_command(output, path=path)


class WindowsListDirectoryCommand(ListDirectoryCommand):
    """Windows list directory command implementation."""

    def create_command(self, path: str = "") -> str:
        """Generate Windows PowerShell dir command.

        Args:
            path: Directory path to list

        Returns:
            The PowerShell command string
        """
        if path:
            return f'powershell -c "Get-ChildItem -Path \\"{path}\\" | Format-Table -AutoSize Name, Mode, Length, LastWriteTime"'  # noqa: E501
        return 'powershell -c "Get-ChildItem | Format-Table -AutoSize Name, Mode, Length, LastWriteTime"'  # noqa: E501

    def parse_command(
        self,
        output: str,
        path: str = "",
    ) -> list[DirectoryEntry]:
        """Parse Windows PowerShell Get-ChildItem output.

        Args:
            output: Raw PowerShell command output
            path: Base directory path

        Returns:
            List of DirectoryEntry objects
        """
        lines = output.strip().split("\n")
        if not lines:
            return []

        files: list[DirectoryEntry] = []

        # Skip header lines and empty lines
        data_lines = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith(("----", "Name", "Mode")):
                continue
            data_lines.append(line)

        # Parse PowerShell Format-Table output
        for line in data_lines:
            parsed = self._parse_powershell_line(line, path)
            if parsed:
                files.append(parsed)

        return files

    def _parse_powershell_line(self, line: str, base_path: str) -> DirectoryEntry | None:
        """Parse PowerShell Format-Table output line."""
        # PowerShell Format-Table output: Name Mode Length LastWriteTime
        # Split by multiple spaces to handle columns
        parts = line.split()
        if len(parts) < MIN_WINDOWS_DIR_PARTS:
            return None

        try:
            name = parts[0]
            mode = parts[1]
            length_str = parts[2]
            # LastWriteTime might be split across multiple parts
            timestamp_parts = parts[3:]
            timestamp = " ".join(timestamp_parts) if timestamp_parts else ""

            # Determine file type from mode
            file_type: Literal["file", "directory", "link"]
            if mode.startswith("d") or "-" not in mode:
                file_type = "directory"
                size = 0
            else:
                file_type = "file"
                # Parse size, handle non-numeric values
                try:
                    size = int(length_str) if length_str.isdigit() else 0
                except (ValueError, AttributeError):
                    size = 0

            # Build full path
            full_path = f"{base_path}\\{name}".replace("/", "\\") if base_path else name

            return DirectoryEntry(
                name=name,
                path=full_path,
                type=file_type,
                size=size,
                timestamp=timestamp,
                permissions=mode,
            )
        except (ValueError, IndexError):
            return None
