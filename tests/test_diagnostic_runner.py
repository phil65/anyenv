"""Tests for DiagnosticRunner."""

from __future__ import annotations

import shlex

from anyenv.lsp_servers._runner import DiagnosticRunner, SimpleCommandResult
from anyenv.lsp_servers._servers.python_lsps import PYRIGHT


async def test_run_all_passes_every_matching_file_to_a_server():
    """A server handling several extensions gets the files of all of them."""
    commands: list[list[str]] = []

    async def executor(command: str) -> SimpleCommandResult:
        commands.append(shlex.split(command))
        return SimpleCommandResult(stdout="{}", stderr="", exit_code=0, duration=0.0)

    runner = DiagnosticRunner(executor)
    runner.register(PYRIGHT)  # handles .py and .pyi
    await runner.run_all(["a.py", "b.pyi", "c.py"])
    assert len(commands) == 1
    assert commands[0][-3:] == ["a.py", "b.pyi", "c.py"]
