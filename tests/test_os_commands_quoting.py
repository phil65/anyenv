"""Hostile paths and names must reach os_commands as literals, never as shell syntax."""

from __future__ import annotations

import base64
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

from anyenv.os_commands._quoting import POWERSHELL_PREFIX, powershell_script
from anyenv.os_commands.batch import CommandBatch
from anyenv.os_commands.providers import get_os_command_provider


HOSTILE = [
    "$(touch CANARY)",
    "`touch CANARY`",
    'a" ; touch CANARY; "b',
    "it's",
    "with space",
    "~",
    "-rf",
    "$HOME",
    "x' ; touch CANARY; 'y",
]

unix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell")


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A working directory with a fake HOME, so a regression can only hurt tmp_path."""
    home = tmp_path / "home"
    home.mkdir()
    (home / "keep").write_text("keep")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(work)
    return work


def sh(cmd: str) -> subprocess.CompletedProcess[str]:
    """Run a command line in a POSIX shell."""
    return subprocess.run(
        ["/bin/sh", "-c", cmd], capture_output=True, text=True, timeout=10, check=False
    )


def assert_untouched(work: Path) -> None:
    """No injected command ran, and HOME survived."""
    assert not (work / "CANARY").exists()
    assert (Path(os.environ["HOME"]) / "keep").exists()


@unix_only
@pytest.mark.parametrize("name", HOSTILE)
def test_unix_commands_treat_names_as_literals(sandbox: Path, name: str):
    """Every path builder works on a file with a hostile name and runs nothing."""
    provider = get_os_command_provider("Linux")
    (sandbox / name).write_text("data")

    def run(command: str, *args, **kwargs) -> subprocess.CompletedProcess[str]:
        result = sh(provider.get_command(command).create_command(*args, **kwargs))  # type: ignore[call-overload]
        assert_untouched(sandbox)
        return result

    assert run("exists", name).returncode == 0
    assert run("is_file", name).returncode == 0
    assert run("is_directory", name).returncode != 0
    out = run("base64_encode", name).stdout
    assert base64.b64decode(out) == b"data"
    assert name in run("file_info", name).stdout
    find = run("find", ".", pattern=name, with_stats=False).stdout
    assert find.strip() == f"./{name}"
    assert run("copy_path", name, f"{name}.copy").returncode == 0
    assert (sandbox / f"{name}.copy").read_text() == "data"
    assert run("remove_path", name).returncode == 0
    assert not (sandbox / name).exists()
    assert run("create_directory", name, parents=False).returncode == 0
    assert (sandbox / name).is_dir()
    (sandbox / name / "inner").write_text("x")
    assert "inner" in run("list_directory", name).stdout
    assert run("remove_path", name, recursive=True).returncode == 0
    assert not (sandbox / name).exists()


@unix_only
def test_remove_path_cannot_reach_home(sandbox: Path):
    """The review's scenario: `x" ~ "y` once made `rm -rf "x" ~ "y"`."""
    cmd = get_os_command_provider("Linux").get_command("remove_path")
    sh(cmd.create_command('x" ~ "y', recursive=True))
    assert_untouched(sandbox)


@unix_only
@pytest.mark.parametrize("name", ["$(touch CANARY)", "A B", "X';touch CANARY;'"])
def test_unix_env_var_and_which_quote(sandbox: Path, name: str):
    """Names for printenv and which are literals too."""
    provider = get_os_command_provider("Linux")
    sh(provider.get_command("env_var").create_command(name))
    sh(provider.get_command("which").create_command(name))
    assert_untouched(sandbox)


def decode(command: str) -> str:
    """The script of an encoded PowerShell command."""
    assert command.startswith(POWERSHELL_PREFIX)
    # Nothing an outer shell (cmd.exe, PowerShell) could reinterpret.
    assert re.fullmatch(r"[A-Za-z0-9+/=]+", command.removeprefix(POWERSHELL_PREFIX))
    script = powershell_script(command)
    assert script is not None
    return script


@pytest.mark.parametrize("name", [*HOSTILE, "a\u2019b"])
def test_windows_commands_use_verbatim_literals(name: str):
    """PowerShell gets single-quoted literals with their quotes doubled."""
    provider = get_os_command_provider("Windows")
    literal = "'" + re.sub("['\u2019]", lambda m: m.group(0) * 2, name) + "'"
    commands = [
        provider.get_command(c).create_command(name)
        for c in ("exists", "is_file", "is_directory", "base64_encode", "file_info")
    ]
    commands += [
        provider.get_command("list_directory").create_command(name),
        provider.get_command("remove_path").create_command(name),
        provider.get_command("remove_path").create_command(name, recursive=True),
        provider.get_command("create_directory").create_command(name),
        provider.get_command("copy_path").create_command(name, name),
        provider.get_command("find").create_command(name, pattern=name),
        provider.get_command("which").create_command(name),
        provider.get_command("env_var").create_command(name),
    ]
    for command in commands:
        script = decode(command)
        assert literal in script, script
        assert script.replace(literal, "").count("'") % 2 == 0, script


def test_windows_batch_rewraps_scripts():
    """The batch unwraps each command's script and encodes the joined script."""
    provider = get_os_command_provider("Windows")
    batch = CommandBatch(platform="windows")
    batch.add(provider.get_command("exists"), "it's")
    batch.add(provider.get_command("pwd"))
    script = decode(batch.create_batch_command())
    assert "Test-Path -LiteralPath 'it''s'" in script
    assert "try { cd }" in script


@unix_only
def test_diagnostic_command_quotes_files(sandbox: Path):
    """File names joined into an LSP diagnostic command stay single arguments."""
    from anyenv.lsp_servers._servers.python_lsps import PYRIGHT

    files = ["$(touch CANARY).py", "with space.py"]
    command = PYRIGHT.build_diagnostic_command(files)
    out = sh(command.replace("pyright", "printf '%s\\n'", 1)).stdout
    assert out.splitlines() == ["--outputjson", *files]
    assert_untouched(sandbox)


@unix_only
async def test_task_runner_quotes_cwd_and_args(sandbox: Path):
    """A task's cwd and arguments are literals."""
    from anyenv.task_runners import JustRunner

    commands: list[str] = []

    class Result:
        success = True
        stdout = stderr = error = ""

    class Env:
        async def execute_command(self, command: str) -> Result:
            commands.append(command)
            return Result()

    hostile = "$(touch CANARY)"
    (sandbox / hostile).mkdir()
    await JustRunner().run_task(Env(), "build", hostile, cwd=hostile)  # type: ignore[arg-type]
    out = sh(commands[0].replace("just", "printf '%s\\n'", 1)).stdout
    assert out.splitlines() == ["build", hostile]
    assert_untouched(sandbox)
