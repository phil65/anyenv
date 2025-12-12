"""Base classes for task runners."""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
import posixpath
import shutil
from typing import TYPE_CHECKING, ClassVar, Literal


if TYPE_CHECKING:
    from exxec import ExecutionEnvironment
    from fsspec.asyn import AsyncFileSystem  # type: ignore[import-untyped]


type TaskRunnerStr = Literal["makefile", "task", "just", "duty", "invoke", "doit", "npm", "cargo"]


@dataclass
class TaskInfo:
    """Information about a single task/target."""

    name: str
    description: str | None = None
    dependencies: list[str] = field(default_factory=list)


@dataclass
class TaskRunner:
    """Base class for task runner configurations.

    Each task runner implementation provides static metadata and implements
    methods for detecting, parsing, and running tasks via an ExecutionEnvironment.
    """

    id: ClassVar[TaskRunnerStr]
    website: ClassVar[str]
    filenames: ClassVar[list[str]]
    help_cmd: ClassVar[list[str]]
    logo: ClassVar[str | None] = None

    def is_available(self) -> bool:
        """Check if the task runner command is available locally."""
        return shutil.which(self.help_cmd[0]) is not None

    async def detect(self, fs: AsyncFileSystem, cwd: str) -> bool:
        """Check if this task runner is used in the given directory.

        Args:
            fs: Async filesystem to use for file operations
            cwd: Directory to check for task runner config files
        """
        for filename in self.filenames:
            filepath = posixpath.join(cwd, filename)
            try:
                if await fs._isfile(filepath):  # noqa: SLF001
                    return True
            except Exception:  # noqa: BLE001
                pass
        return False

    async def get_config_file(self, fs: AsyncFileSystem, cwd: str) -> str | None:
        """Get the config file path if it exists.

        Args:
            fs: Async filesystem to use for file operations
            cwd: Directory to check
        """
        for filename in self.filenames:
            filepath = posixpath.join(cwd, filename)
            try:
                if await fs._isfile(filepath):  # noqa: SLF001
                    return filepath
            except Exception:  # noqa: BLE001
                pass
        return None

    async def _read_file(self, fs: AsyncFileSystem, filepath: str) -> str:
        """Read file content as text.

        Args:
            fs: Async filesystem to use for file operations
            filepath: Path to the file
        """
        content = await fs._cat_file(filepath)  # noqa: SLF001
        return content.decode() if isinstance(content, bytes) else content

    @abstractmethod
    async def get_tasks(self, fs: AsyncFileSystem, cwd: str) -> list[TaskInfo]:
        """Parse and return available tasks from the config file.

        Args:
            fs: Async filesystem to use for file operations
            cwd: Directory containing the task runner config
        """
        ...

    def get_run_command(self, task_name: str, *args: str) -> list[str]:
        """Get the command to run a specific task.

        Args:
            task_name: Name of the task to run
            *args: Additional arguments to pass to the task
        """
        return [self.help_cmd[0], task_name, *args]

    async def run_task(
        self,
        env: ExecutionEnvironment,
        task_name: str,
        *args: str,
        cwd: str | None = None,
    ) -> tuple[bool, str, str]:
        """Run a specific task using the execution environment.

        Args:
            env: Execution environment to run the command in
            task_name: Name of the task to run
            *args: Additional arguments to pass to the task
            cwd: Working directory (optional)

        Returns:
            Tuple of (success, stdout, stderr)
        """
        cmd = self.get_run_command(task_name, *args)
        command_str = " ".join(cmd)
        if cwd:
            command_str = f"cd {cwd} && {command_str}"

        result = await env.execute_command(command_str)
        return (
            result.success,
            result.stdout or "",
            result.stderr or result.error or "",
        )

    async def list_tasks_via_cli(
        self,
        env: ExecutionEnvironment,
        *,
        cwd: str | None = None,
    ) -> str:
        """Get task list by running the help command.

        Fallback when file parsing isn't possible (e.g., remote without file access).

        Args:
            env: Execution environment to run the command in
            cwd: Working directory (optional)

        Returns:
            Raw output from the help command
        """
        command_str = " ".join(self.help_cmd)
        if cwd:
            command_str = f"cd {cwd} && {command_str}"

        result = await env.execute_command(command_str)
        return result.stdout or ""
