"""Task runner abstraction for various build tools.

Provides a unified interface for detecting, parsing, and running tasks
from various task runners like Make, Just, Task, Duty, Invoke, doit, and npm.
"""

from __future__ import annotations

from anyenv.task_runners._base import TaskInfo, TaskRunner, TaskRunnerStr
from anyenv.task_runners._cargo import CargoRunner
from anyenv.task_runners._just import JustRunner
from anyenv.task_runners._makefile import MakefileRunner
from anyenv.task_runners._npm import PackageJsonRunner
from anyenv.task_runners._python import DoitRunner, DutyRunner, InvokeRunner
from anyenv.task_runners._task import TaskfileRunner

ALL_RUNNERS: list[TaskRunner] = [
    MakefileRunner(),
    TaskfileRunner(),
    JustRunner(),
    DutyRunner(),
    InvokeRunner(),
    DoitRunner(),
    PackageJsonRunner(),
    CargoRunner(),
]

RUNNERS_BY_ID: dict[TaskRunnerStr, TaskRunner] = {r.id: r for r in ALL_RUNNERS}


def get_runner(runner_id: TaskRunnerStr) -> TaskRunner:
    """Get a task runner by ID.

    Args:
        runner_id: The task runner identifier

    Raises:
        KeyError: If the runner ID is not found
    """
    return RUNNERS_BY_ID[runner_id]


__all__ = [
    "ALL_RUNNERS",
    "RUNNERS_BY_ID",
    "CargoRunner",
    "DoitRunner",
    "DutyRunner",
    "InvokeRunner",
    "JustRunner",
    "MakefileRunner",
    "PackageJsonRunner",
    "TaskInfo",
    "TaskRunner",
    "TaskRunnerStr",
    "TaskfileRunner",
    "get_runner",
]
