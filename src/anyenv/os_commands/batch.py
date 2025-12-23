"""Command batching for executing multiple commands in a single shell call."""

from __future__ import annotations

from dataclasses import dataclass, field
import platform
from typing import TYPE_CHECKING, Any, Literal


if TYPE_CHECKING:
    from .base import CommandProtocol


# Delimiters for parsing batched output
DELIMITER = ":::CMDDELIM:::"
EXIT_MARKER = ":::EXIT:"
END_MARKER = ":::"


@dataclass
class PendingCommand:
    """A command pending execution in a batch."""

    command_str: str
    command: CommandProtocol
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


@dataclass
class CommandBatch:
    """Batch multiple commands into a single shell call.

    This class allows you to combine multiple OS commands into a single
    shell invocation, reducing round-trips when commands are executed
    over a protocol (SSH, containers, etc.).

    Example:
        >>> provider = get_os_command_provider()
        >>> which_cmd = provider.get_command("which")
        >>> exists_cmd = provider.get_command("exists")
        >>>
        >>> batch = CommandBatch()
        >>> batch.add(which_cmd, "python")
        >>> batch.add(which_cmd, "node")
        >>> batch.add(exists_cmd, "/tmp/test.txt")
        >>>
        >>> # Execute single combined command
        >>> combined = batch.create_batch_command()
        >>> result = subprocess.run(combined, shell=True, capture_output=True, text=True)
        >>>
        >>> # Parse back to individual results
        >>> python_path, node_path, exists = batch.parse_batch_output(result.stdout)
    """

    platform: Literal["unix", "windows"] = field(default_factory=lambda: _detect_platform())
    _commands: list[PendingCommand] = field(default_factory=list)

    def add(self, command: CommandProtocol, *args: Any, **kwargs: Any) -> CommandBatch:
        """Add a command with its arguments to the batch.

        Args:
            command: The command instance (e.g., WhichCommand, ExistsCommand)
            *args: Positional arguments to pass to create_command
            **kwargs: Keyword arguments to pass to create_command

        Returns:
            Self for method chaining
        """
        cmd_str = command.create_command(*args, **kwargs)
        self._commands.append(PendingCommand(cmd_str, command, args, kwargs))
        return self

    def create_batch_command(self) -> str:
        """Generate the combined shell command string.

        Returns:
            A single shell command that executes all batched commands
            and captures their individual outputs and exit codes.
        """
        if not self._commands:
            return ""

        if self.platform == "windows":
            return self._create_windows_batch()
        return self._create_unix_batch()

    def _create_unix_batch(self) -> str:
        """Generate Unix/macOS batch command."""
        # Wrap each command to capture its exit code
        # Using subshell to isolate each command
        parts = [f'({c.command_str}; echo "{EXIT_MARKER}$?{END_MARKER}")' for c in self._commands]
        return f'; echo "{DELIMITER}"; '.join(parts)

    def _create_windows_batch(self) -> str:
        """Generate Windows PowerShell batch command."""
        parts = []
        for cmd in self._commands:
            # Extract the actual command from powershell -c "..." wrapper if present
            inner_cmd = cmd.command_str
            if inner_cmd.startswith('powershell -c "') and inner_cmd.endswith('"'):
                # Extract inner command, will be re-wrapped
                inner_cmd = inner_cmd[15:-1]

            # Build PowerShell script block that captures exit code
            # Use try/catch to handle command failures gracefully
            parts.append(
                f"try {{ {inner_cmd} }} catch {{ }}; "
                f"Write-Host '{EXIT_MARKER}' -NoNewline; "
                f"Write-Host $LASTEXITCODE -NoNewline; "
                f"Write-Host '{END_MARKER}'"
            )

        # Join with delimiter output between commands
        delimiter_cmd = f"Write-Host '{DELIMITER}'"
        script = f"; {delimiter_cmd}; ".join(parts)
        return f'powershell -c "{script}"'

    def parse_batch_output(self, output: str) -> list[Any]:
        """Parse the combined output back to individual command results.

        Args:
            output: The raw output from executing the batch command

        Returns:
            List of parsed results, one per command in the batch,
            in the same order they were added.
        """
        if not self._commands:
            return []

        results = []
        segments = output.split(DELIMITER)

        for i, segment in enumerate(segments):
            if i >= len(self._commands):
                break

            pending = self._commands[i]

            # Extract exit code from segment
            cmd_output, exit_code = self._extract_exit_code(segment)

            # Call the command's parser with appropriate arguments
            result = self._parse_command_output(pending, cmd_output, exit_code)
            results.append(result)

        return results

    def _extract_exit_code(self, segment: str) -> tuple[str, int]:
        """Extract the exit code from a command output segment.

        Args:
            segment: Raw output segment including exit code marker

        Returns:
            Tuple of (cleaned output, exit code)
        """
        if EXIT_MARKER in segment:
            parts = segment.rsplit(EXIT_MARKER, 1)
            cmd_output = parts[0]
            # Extract exit code, removing the end marker
            exit_str = parts[1].split(END_MARKER)[0].strip()
            try:
                exit_code = int(exit_str)
            except ValueError:
                exit_code = 0
        else:
            cmd_output = segment
            exit_code = 0

        return cmd_output.strip(), exit_code

    def _parse_command_output(self, pending: PendingCommand, output: str, exit_code: int) -> Any:
        """Parse a single command's output using its parser.

        Handles the different parse_command signatures by inspecting
        what arguments the parser expects.

        Args:
            pending: The pending command with its original args
            output: The command's output
            exit_code: The command's exit code

        Returns:
            The parsed result from the command's parser
        """
        # Most parsers take (output, exit_code) or (output, some_original_arg)
        # We need to handle both cases

        # Try the standard (output, exit_code) signature first
        # Commands like WhichCommand, ExistsCommand, etc.
        try:
            # Check if the parse_command expects the original args
            # FileInfoCommand.parse_command(output, path) needs the path
            # ListDirectoryCommand.parse_command(output, path) needs the path
            import inspect

            sig = inspect.signature(pending.command.parse_command)
            params = list(sig.parameters.keys())

            # If second param is 'exit_code', pass exit_code
            # Otherwise, pass the first positional arg from create_command
            if len(params) >= 2:  # noqa: PLR2004
                second_param = params[1]
                if second_param == "exit_code":
                    return pending.command.parse_command(output, exit_code)
                if pending.args:
                    # Pass the first arg (usually 'path')
                    return pending.command.parse_command(output, pending.args[0])

            # Fallback: just pass output
            return pending.command.parse_command(output)

        except Exception:  # noqa: BLE001
            # Last resort fallback
            return pending.command.parse_command(output, exit_code)

    def clear(self) -> None:
        """Clear all pending commands from the batch."""
        self._commands.clear()

    def __len__(self) -> int:
        """Return the number of pending commands."""
        return len(self._commands)


def _detect_platform() -> Literal["unix", "windows"]:
    """Detect the current platform for batch command generation."""
    if platform.system() == "Windows":
        return "windows"
    return "unix"
