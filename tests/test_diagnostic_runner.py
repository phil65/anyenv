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


async def _run_with_concurrency(concurrency: int | None) -> tuple[int, list[str]]:
    import asyncio

    from anyenv.lsp_servers._servers.python_lsps import MYPY, TY

    in_flight = peak = 0

    async def executor(command: str) -> SimpleCommandResult:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1
        return SimpleCommandResult(stdout="", stderr="", exit_code=0, duration=0.0)

    runner = DiagnosticRunner(executor)
    for server in (PYRIGHT, MYPY, TY):
        runner.register(server)
    if concurrency is None:
        results = await runner.run_all(["a.py"])
    else:
        results = await runner.run_all(["a.py"], concurrency=concurrency)
    return peak, list(results)


async def test_run_all_runs_servers_one_at_a_time_by_default():
    """Without a concurrency, servers run sequentially."""
    peak, order = await _run_with_concurrency(None)
    assert peak == 1
    assert order == ["pyright", "mypy", "ty"]


async def test_run_all_runs_servers_in_parallel_up_to_concurrency():
    """concurrency=n runs up to n servers at once; results keep registration order."""
    peak, order = await _run_with_concurrency(2)
    assert peak == 2  # noqa: PLR2004
    assert order == ["pyright", "mypy", "ty"]
