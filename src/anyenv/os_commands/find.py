"""Find command implementations for different operating systems."""

from __future__ import annotations

from typing import Literal

from .base import FindCommand
from .models import DirectoryEntry


EntryType = Literal["file", "directory", "link"]


class UnixFindCommand(FindCommand):
    """Unix/Linux find command implementation."""

    def create_command(
        self,
        path: str,
        pattern: str | None = None,
        maxdepth: int | None = None,
        file_type: Literal["file", "directory", "all"] = "all",
        with_stats: bool = True,
    ) -> str:
        """Generate Unix find command.

        Args:
            path: Directory to search in
            pattern: Glob pattern for name matching (e.g., "*.py")
            maxdepth: Maximum directory depth to descend
            file_type: Filter by type - files only, directories only, or all
            with_stats: Include file stats using -printf (size, mtime, type, perms)

        Returns:
            The find command string
        """
        parts = ["find", f'"{path}"']

        if maxdepth is not None:
            parts.append(f"-maxdepth {maxdepth}")

        if file_type == "file":
            parts.append("-type f")
        elif file_type == "directory":
            parts.append("-type d")
        # "all" doesn't add a type filter

        if pattern:
            parts.append(f'-name "{pattern}"')

        if with_stats:
            # Use -printf to get file stats in tab-separated format:
            # %p = path, %s = size in bytes, %T@ = mtime as unix timestamp
            # %y = type (f=file, d=dir, l=link), %M = permissions like ls -l
            # Single quotes protect the format string from shell interpretation
            parts.append(r"-printf '%p\t%s\t%T@\t%y\t%M\n'")

        return " ".join(parts)

    def parse_command(self, output: str, base_path: str = "") -> list[DirectoryEntry]:
        """Parse Unix find output.

        Handles both plain path output and -printf formatted output with stats.
        Detects format automatically based on presence of tab separators.

        Args:
            output: Raw find command output
            base_path: Base path used in the find command

        Returns:
            List of DirectoryEntry objects
        """
        lines = output.strip().split("\n")
        if not lines or (len(lines) == 1 and not lines[0]):
            return []

        entries: list[DirectoryEntry] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check if this is -printf formatted output (contains tabs)
            if "\t" in line:
                # Parse tab-separated format: path\tsize\ttimestamp\ttype\tpermissions
                # Parse from the right since path may contain tabs (rare but possible)
                parts = line.rsplit("\t", 4)
                if len(parts) == 5:  # noqa: PLR2004
                    path_str, size_str, timestamp_str, type_char, permissions = parts

                    # Map find type char to our type
                    type_map: dict[str, EntryType] = {"f": "file", "d": "directory", "l": "link"}
                    entry_type: EntryType = type_map.get(type_char, "file")

                    # Parse size
                    try:
                        size = int(size_str)
                    except ValueError:
                        size = 0

                    # Extract name from path
                    name = path_str.rsplit("/", 1)[-1] if "/" in path_str else path_str

                    # Skip . and ..
                    if name in (".", ".."):
                        continue

                    entries.append(
                        DirectoryEntry(
                            name=name,
                            path=path_str,
                            type=entry_type,
                            size=size,
                            timestamp=timestamp_str,
                            permissions=permissions,
                        )
                    )
                    continue

            # Fallback: plain path output (no tabs)
            name = line.rsplit("/", 1)[-1] if "/" in line else line

            # Skip . and ..
            if name in (".", ".."):
                continue

            entries.append(
                DirectoryEntry(
                    name=name,
                    path=line,
                    type="file",  # Default; use file_type param to filter
                    size=0,
                    timestamp=None,
                    permissions=None,
                )
            )

        return entries


class MacOSFindCommand(FindCommand):
    """macOS find command implementation (BSD find)."""

    def create_command(
        self,
        path: str,
        pattern: str | None = None,
        maxdepth: int | None = None,
        file_type: Literal["file", "directory", "all"] = "all",
        with_stats: bool = True,
    ) -> str:
        """Generate macOS find command.

        BSD find doesn't support -printf, so we use -exec stat for file stats.

        Args:
            path: Directory to search in
            pattern: Glob pattern for name matching (e.g., "*.py")
            maxdepth: Maximum directory depth to descend
            file_type: Filter by type - files only, directories only, or all
            with_stats: Include file stats (uses -exec stat, slower than GNU -printf)

        Returns:
            The find command string
        """
        parts = ["find", f'"{path}"']

        if maxdepth is not None:
            parts.append(f"-maxdepth {maxdepth}")

        if file_type == "file":
            parts.append("-type f")
        elif file_type == "directory":
            parts.append("-type d")

        if pattern:
            parts.append(f'-name "{pattern}"')

        if with_stats:
            # BSD stat format: path\tsize\tmtime\ttype\tpermissions
            # %N = path, %z = size, %m = mtime (unix timestamp)
            # %HT = type (Regular File, Directory, etc.), %Sp = permissions
            # Single quotes protect the format string from shell interpretation
            parts.append(r"-exec stat -f '%N\t%z\t%m\t%HT\t%Sp' {} \;")

        return " ".join(parts)

    def parse_command(self, output: str, base_path: str = "") -> list[DirectoryEntry]:
        """Parse macOS find output.

        Handles both plain path output and stat-formatted output with stats.

        Args:
            output: Raw find command output
            base_path: Base path used in the find command

        Returns:
            List of DirectoryEntry objects
        """
        lines = output.strip().split("\n")
        if not lines or (len(lines) == 1 and not lines[0]):
            return []

        entries: list[DirectoryEntry] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check if this is stat-formatted output (contains tabs)
            if "\t" in line:
                parts = line.rsplit("\t", 4)
                if len(parts) == 5:  # noqa: PLR2004
                    path_str, size_str, timestamp_str, type_str, permissions = parts

                    # Map BSD stat type string to our type
                    if "Directory" in type_str:
                        entry_type: Literal["file", "directory", "link"] = "directory"
                    elif "Link" in type_str:
                        entry_type = "link"
                    else:
                        entry_type = "file"

                    try:
                        size = int(size_str)
                    except ValueError:
                        size = 0

                    name = path_str.rsplit("/", 1)[-1] if "/" in path_str else path_str

                    if name in (".", ".."):
                        continue

                    entries.append(
                        DirectoryEntry(
                            name=name,
                            path=path_str,
                            type=entry_type,
                            size=size,
                            timestamp=timestamp_str,
                            permissions=permissions,
                        )
                    )
                    continue

            # Fallback: plain path output
            name = line.rsplit("/", 1)[-1] if "/" in line else line

            if name in (".", ".."):
                continue

            entries.append(
                DirectoryEntry(
                    name=name,
                    path=line,
                    type="file",
                    size=0,
                    timestamp=None,
                    permissions=None,
                )
            )

        return entries


class WindowsFindCommand(FindCommand):
    """Windows find command implementation using PowerShell."""

    def create_command(
        self,
        path: str,
        pattern: str | None = None,
        maxdepth: int | None = None,
        file_type: Literal["file", "directory", "all"] = "all",
        with_stats: bool = True,
    ) -> str:
        """Generate Windows PowerShell Get-ChildItem command.

        Args:
            path: Directory to search in
            pattern: Glob pattern for name matching (e.g., "*.py")
            maxdepth: Maximum directory depth to descend
            file_type: Filter by type - files only, directories only, or all
            with_stats: Include file stats (always True for Windows, included for API consistency)

        Returns:
            The PowerShell command string
        """
        # Build Get-ChildItem command
        parts = [f'Get-ChildItem -Path \\"{path}\\" -Recurse']

        if maxdepth is not None:
            # PowerShell -Depth is 0-indexed (0 = immediate children only)
            # To match find behavior where maxdepth 1 = immediate children
            depth = maxdepth - 1 if maxdepth > 0 else 0
            parts.append(f"-Depth {depth}")

        if pattern:
            parts.append(f'-Filter \\"{pattern}\\"')

        if file_type == "file":
            parts.append("-File")
        elif file_type == "directory":
            parts.append("-Directory")

        # Output format: FullName|Length|Mode (pipe-separated for easy parsing)
        parts.append('| ForEach-Object { \\"$($_.FullName)|$($_.Length)|$($_.Mode)\\" }')

        return f'powershell -c "{" ".join(parts)}"'

    def parse_command(self, output: str, base_path: str = "") -> list[DirectoryEntry]:
        """Parse Windows PowerShell Get-ChildItem output.

        Args:
            output: Raw command output (path|size|mode per line)
            base_path: Base path used in the command

        Returns:
            List of DirectoryEntry objects
        """
        lines = output.strip().split("\n")
        if not lines or (len(lines) == 1 and not lines[0]):
            return []

        entries: list[DirectoryEntry] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue

            parts = line.split("|")
            if len(parts) < 3:  # noqa: PLR2004
                continue

            full_path = parts[0]
            size_str = parts[1]
            mode = parts[2]

            # Extract name from path
            name = full_path.rsplit("\\", 1)[-1] if "\\" in full_path else full_path

            # Skip . and ..
            if name in (".", ".."):
                continue

            # Determine type from mode
            file_type: Literal["file", "directory", "link"]
            file_type = "directory" if mode.startswith("d") else "file"

            # Parse size
            try:
                size = int(size_str) if size_str else 0
            except ValueError:
                size = 0

            entries.append(
                DirectoryEntry(
                    name=name,
                    path=full_path,
                    type=file_type,
                    size=size,
                    timestamp=None,
                    permissions=mode,
                )
            )

        return entries


if __name__ == "__main__":
    import subprocess
    import sys

    # Test on current platform
    if sys.platform == "win32":
        cmd = WindowsFindCommand()
    elif sys.platform == "darwin":
        cmd = MacOSFindCommand()
    else:
        cmd = UnixFindCommand()

    cmd_str = cmd.create_command(".", pattern="*.py", maxdepth=2, file_type="file")
    print(f"Command: {cmd_str}")

    result = subprocess.run(cmd_str, shell=True, capture_output=True, text=True)
    entries = cmd.parse_command(result.stdout, ".")

    print(f"\nFound {len(entries)} entries:")
    for entry in entries[:5]:  # Show first 5 entries
        print(f"  {entry.path} ({entry.type})")
