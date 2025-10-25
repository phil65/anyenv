"""List directory command implementations for different operating systems."""

from __future__ import annotations

from typing import Any, Literal

from .base import ListDirectoryCommand
from .models import DirectoryEntry


# Constants for parsing directory listings
MIN_LS_PARTS = 7  # Minimum parts for valid ls -la line
MIN_LS_PARTS_3_TIMESTAMP = 9  # Parts needed for 3-part timestamp format
MIN_LS_PARTS_2_TIMESTAMP = 8  # Parts needed for 2-part timestamp format
MIN_WINDOWS_DIR_PARTS = 4  # Minimum parts for Windows dir output


class UnixListDirectoryCommand(ListDirectoryCommand):
    """Unix/Linux list directory command implementation."""

    def create_command(self, path: str = "", detailed: bool = True) -> str:
        """Generate Unix ls command.

        Args:
            path: Directory path to list
            detailed: Whether to include detailed information

        Returns:
            The ls command string
        """
        cmd = "ls -la" if detailed else "ls"
        return f'{cmd} "{path}"' if path else cmd

    def parse_command(
        self,
        output: str,
        path: str = "",
        detailed: bool = True,
    ) -> list[DirectoryEntry] | list[str]:
        """Parse Unix ls output.

        Args:
            output: Raw ls command output
            path: Base directory path
            detailed: Whether output contains detailed information

        Returns:
            List of DirectoryEntry objects or simple filenames
        """
        lines = output.strip().split("\n")
        if not lines:
            return []

        # Filter out total line and empty lines
        file_lines = [line for line in lines if line and not line.startswith("total ")]

        files: list[Any] = []
        for line in file_lines:
            if not line.strip():
                continue

            if detailed:
                parsed = self._parse_detailed_line(line, path)
                if parsed:
                    files.append(parsed)
            else:
                filename = self._parse_simple_line(line)
                if filename:
                    files.append(filename)

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

    def _parse_simple_line(self, line: str) -> str | None:
        """Parse simple ls output line to extract filename."""
        parts = line.split()
        if len(parts) < MIN_LS_PARTS:  # Not a valid ls -la line
            return line.strip() if line.strip() else None

        # Handle different timestamp formats for name extraction
        if (
            len(parts) >= MIN_LS_PARTS_3_TIMESTAMP
            and not parts[7].startswith("-")
            and not parts[7].startswith("d")
        ):
            return " ".join(parts[8:])  # 3-part timestamp
        if len(parts) >= MIN_LS_PARTS_2_TIMESTAMP:
            return " ".join(parts[7:])  # 2-part timestamp
        return " ".join(parts[6:])  # 1-part timestamp fallback


class MacOSListDirectoryCommand(ListDirectoryCommand):
    """macOS list directory command implementation."""

    def create_command(self, path: str = "", detailed: bool = True) -> str:
        """Generate BSD ls command (no --time-style support).

        Args:
            path: Directory path to list
            detailed: Whether to include detailed information

        Returns:
            The ls command string
        """
        cmd = "ls -la" if detailed else "ls"
        return f'{cmd} "{path}"' if path else cmd

    def parse_command(
        self,
        output: str,
        path: str = "",
        detailed: bool = True,
    ) -> list[DirectoryEntry] | list[str]:
        """Parse BSD ls output (same as Unix).

        Args:
            output: Raw ls command output
            path: Base directory path
            detailed: Whether output contains detailed information

        Returns:
            List of DirectoryEntry objects or simple filenames
        """
        # BSD ls output format is same as Unix, just different timestamp format
        unix_cmd = UnixListDirectoryCommand()
        return unix_cmd.parse_command(output, path=path, detailed=detailed)


class WindowsListDirectoryCommand(ListDirectoryCommand):
    """Windows list directory command implementation."""

    def create_command(self, path: str = "", detailed: bool = True) -> str:
        """Generate Windows dir command.

        Args:
            path: Directory path to list
            detailed: Whether to include detailed information

        Returns:
            The dir command string
        """
        if detailed:
            return f'dir "{path}"' if path else "dir"
        return f'dir /b "{path}"' if path else "dir /b"

    def parse_command(
        self,
        output: str,
        path: str = "",
        detailed: bool = True,
    ) -> list[DirectoryEntry] | list[str]:
        """Parse Windows dir output.

        Args:
            output: Raw dir command output
            path: Base directory path
            detailed: Whether output contains detailed information

        Returns:
            List of DirectoryEntry objects or simple filenames
        """
        lines = output.strip().split("\n")
        if not lines:
            return []

        files: list[Any] = []

        if not detailed:
            # Simple dir /b output - just filenames
            for line in lines:
                line = line.strip()
                if line:
                    files.append(line)
            return files

        # Parse detailed dir output
        for line in lines:
            line = line.strip()
            if self._should_skip_line(line):
                continue

            parsed = self._parse_detailed_line(line, path)
            if parsed:
                files.append(parsed)

        return files

    def _should_skip_line(self, line: str) -> bool:
        """Check if line should be skipped during parsing."""
        return (
            not line
            or line.startswith(("Volume", "Directory"))
            or "bytes" in line
            or "File(s)" in line
            or "Dir(s)" in line
        )

    def _parse_detailed_line(self, line: str, base_path: str) -> DirectoryEntry | None:
        """Parse detailed Windows dir output line."""
        parts = line.split()
        if len(parts) < MIN_WINDOWS_DIR_PARTS:
            return None

        try:
            # Extract date and time
            date_part = parts[0]
            time_part = f"{parts[1]} {parts[2]}"  # Include AM/PM
            timestamp = f"{date_part} {time_part}"

            # Check if it's a directory
            is_dir = parts[3] == "<DIR>"
            file_type: Literal["file", "directory", "link"]
            if is_dir:
                size = 0
                name = " ".join(parts[4:])
                file_type = "directory"
            else:
                size = int(parts[3]) if parts[3].isdigit() else 0
                name = " ".join(parts[4:])
                file_type = "file"

            # Build full path using Windows path separator
            full_path = f"{base_path}\\{name}" if base_path else name
        except (ValueError, IndexError):
            # Skip lines we can't parse
            return None
        else:
            return DirectoryEntry(
                name=name,
                path=full_path,
                type=file_type,
                size=size,
                timestamp=timestamp,
            )
