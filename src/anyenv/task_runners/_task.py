"""Task (taskfile.dev) task runner implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Literal

from anyenv.task_runners._base import TaskInfo, TaskRunner


if TYPE_CHECKING:
    from fsspec.asyn import AsyncFileSystem  # type: ignore[import-untyped]


@dataclass
class TaskfileRunner(TaskRunner):
    """Task runner for Taskfile (taskfile.dev)."""

    id: ClassVar[Literal["task"]] = "task"
    website: ClassVar[str] = "https://taskfile.dev/"
    filenames: ClassVar[list[str]] = [
        "Taskfile.yml",
        "taskfile.yml",
        "Taskfile.yaml",
        "taskfile.yaml",
        "Taskfile.dist.yml",
        "taskfile.dist.yml",
        "Taskfile.dist.yaml",
        "taskfile.dist.yaml",
    ]
    help_cmd: ClassVar[list[str]] = ["task", "--list"]
    logo: ClassVar[str | None] = "https://taskfile.dev/img/logo.svg"

    async def get_tasks(self, fs: AsyncFileSystem, cwd: str) -> list[TaskInfo]:
        """Parse Taskfile and return available tasks."""
        config_file = await self.get_config_file(fs, cwd)
        if config_file is None:
            return []

        content = await self._read_file(fs, config_file)
        return self._parse_taskfile(content)

    def _parse_taskfile(self, content: str) -> list[TaskInfo]:
        """Parse Taskfile YAML content to extract tasks."""
        import yaml

        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError:
            return []

        if not isinstance(data, dict):
            return []

        tasks_section = data.get("tasks", {})
        if not isinstance(tasks_section, dict):
            return []

        tasks: list[TaskInfo] = []
        for name, task_def in tasks_section.items():
            # Skip internal tasks (prefixed with _)
            if name.startswith("_"):
                continue

            description = None
            deps: list[str] = []

            if isinstance(task_def, dict):
                description = task_def.get("desc") or task_def.get("summary")
                raw_deps = task_def.get("deps", [])
                if isinstance(raw_deps, list):
                    deps = [
                        d if isinstance(d, str) else d.get("task", "")
                        for d in raw_deps
                        if isinstance(d, str | dict)
                    ]

            tasks.append(TaskInfo(name=name, description=description, dependencies=deps))

        return sorted(tasks, key=lambda t: t.name)

    def get_run_command(self, task_name: str, *args: str) -> list[str]:
        """Get the task command for a specific task."""
        return ["task", task_name, *args]
