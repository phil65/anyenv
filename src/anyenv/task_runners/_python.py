"""Python-based task runner implementations (duty, invoke, doit)."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import posixpath
import re
from typing import TYPE_CHECKING, ClassVar, Literal

from anyenv.task_runners._base import TaskInfo, TaskRunner


if TYPE_CHECKING:
    from fsspec.asyn import AsyncFileSystem  # type: ignore[import-untyped]


@dataclass
class DutyRunner(TaskRunner):
    """Task runner for Duty (pawamoy/duty)."""

    id: ClassVar[Literal["duty"]] = "duty"
    website: ClassVar[str] = "https://github.com/pawamoy/duty"
    filenames: ClassVar[list[str]] = ["duties.py"]
    help_cmd: ClassVar[list[str]] = ["duty", "--list"]
    logo: ClassVar[str | None] = None

    async def get_tasks(self, fs: AsyncFileSystem, cwd: str) -> list[TaskInfo]:
        """Parse duties.py and return available tasks."""
        config_file = await self.get_config_file(fs, cwd)
        if config_file is None:
            return []

        content = await self._read_file(fs, config_file)
        return self._parse_duties(content)

    def _parse_duties(self, content: str) -> list[TaskInfo]:
        """Parse duties.py to extract @duty decorated functions."""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        tasks: list[TaskInfo] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue

            # Check if function has @duty decorator
            is_duty = any(
                (isinstance(d, ast.Name) and d.id == "duty")
                or (
                    isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "duty"
                )
                for d in node.decorator_list
            )

            if not is_duty:
                continue

            # Extract docstring as description
            description = ast.get_docstring(node)

            tasks.append(TaskInfo(name=node.name, description=description))

        return sorted(tasks, key=lambda t: t.name)

    def get_run_command(self, task_name: str, *args: str) -> list[str]:
        """Get the duty command for a specific task."""
        return ["duty", task_name, *args]


@dataclass
class InvokeRunner(TaskRunner):
    """Task runner for Invoke (pyinvoke.org)."""

    id: ClassVar[Literal["invoke"]] = "invoke"
    website: ClassVar[str] = "https://www.pyinvoke.org"
    filenames: ClassVar[list[str]] = [
        "tasks.py",
        "invoke.yaml",
        "invoke.yml",
        "invoke.json",
        "invoke.py",
    ]
    help_cmd: ClassVar[list[str]] = ["invoke", "--list"]
    logo: ClassVar[str | None] = None

    async def get_tasks(self, fs: AsyncFileSystem, cwd: str) -> list[TaskInfo]:
        """Parse tasks.py and return available tasks."""
        # Only parse tasks.py, not the config files
        tasks_file = posixpath.join(cwd, "tasks.py")
        try:
            if not await fs._isfile(tasks_file):  # noqa: SLF001
                return []
        except Exception:  # noqa: BLE001
            return []

        content = await self._read_file(fs, tasks_file)
        return self._parse_tasks(content)

    def _parse_tasks(self, content: str) -> list[TaskInfo]:
        """Parse tasks.py to extract @task decorated functions."""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        tasks: list[TaskInfo] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue

            # Check if function has @task decorator
            is_task = any(
                (isinstance(d, ast.Name) and d.id == "task")
                or (
                    isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "task"
                )
                for d in node.decorator_list
            )

            if not is_task:
                continue

            # Extract docstring as description
            description = ast.get_docstring(node)

            # Convert underscores to hyphens (invoke convention)
            task_name = node.name.replace("_", "-")

            tasks.append(TaskInfo(name=task_name, description=description))

        return sorted(tasks, key=lambda t: t.name)

    def get_run_command(self, task_name: str, *args: str) -> list[str]:
        """Get the invoke command for a specific task."""
        return ["invoke", task_name, *args]


@dataclass
class DoitRunner(TaskRunner):
    """Task runner for doit (pydoit.org)."""

    id: ClassVar[Literal["doit"]] = "doit"
    website: ClassVar[str] = "http://pydoit.org"
    filenames: ClassVar[list[str]] = ["dodo.py"]
    help_cmd: ClassVar[list[str]] = ["doit", "list"]
    logo: ClassVar[str | None] = "https://pydoit.org/_static/doit-logo.png"

    # Pattern for task_ function definitions
    _TASK_FUNC_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^def\s+(task_\w+)\s*\(")

    async def get_tasks(self, fs: AsyncFileSystem, cwd: str) -> list[TaskInfo]:
        """Parse dodo.py and return available tasks."""
        config_file = await self.get_config_file(fs, cwd)
        if config_file is None:
            return []

        content = await self._read_file(fs, config_file)
        return self._parse_dodo(content)

    def _parse_dodo(self, content: str) -> list[TaskInfo]:
        """Parse dodo.py to extract task_ functions."""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        tasks: list[TaskInfo] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue

            # doit tasks are functions named task_*
            if not node.name.startswith("task_"):
                continue

            # Task name is function name without task_ prefix
            task_name = node.name[5:]  # Remove "task_" prefix

            # Extract docstring as description
            description = ast.get_docstring(node)

            tasks.append(TaskInfo(name=task_name, description=description))

        return sorted(tasks, key=lambda t: t.name)

    def get_run_command(self, task_name: str, *args: str) -> list[str]:
        """Get the doit command for a specific task."""
        return ["doit", "run", task_name, *args]
