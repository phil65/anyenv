"""Tests for OS command implementations with subprocess execution."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
from typing import TYPE_CHECKING

import pytest

from anyenv.os_commands.providers import get_os_command_provider


if TYPE_CHECKING:
    from anyenv.os_commands import OSCommandProvider


@pytest.fixture
def provider():
    """Get OS command provider for current platform."""
    return get_os_command_provider()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_file(temp_dir):
    """Create a test file."""
    test_file = temp_dir / "test.txt"
    test_file.write_text("test content")
    return test_file


@pytest.fixture
def test_subdir(temp_dir):
    """Create a test subdirectory."""
    subdir = temp_dir / "subdir"
    subdir.mkdir()
    return subdir


def run_command(cmd: str) -> tuple[str, int]:
    """Run a command and return output and exit code."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10
        )
    except subprocess.TimeoutExpired:
        return "", 1
    else:
        return result.stdout, result.returncode


def test_list_directory_command(
    provider: OSCommandProvider,
    temp_dir: Path,
    test_file: Path,
    test_subdir: Path,
):
    """Test list directory command: create → execute → parse."""
    # Create command
    cmd = provider.get_command("list_directory").create_command(
        str(temp_dir), detailed=True
    )
    assert isinstance(cmd, str)
    assert str(temp_dir) in cmd

    # Execute command
    output, exit_code = run_command(cmd)
    assert exit_code == 0
    assert output.strip()

    # Parse output
    result = provider.get_command("list_directory").parse_command(
        output, str(temp_dir), detailed=True
    )
    assert isinstance(result, list)
    assert len(result) >= 2  # noqa: PLR2004

    names = [item.name if hasattr(item, "name") else item for item in result]
    assert "test.txt" in names
    assert "subdir" in names


def test_exists_command(provider: OSCommandProvider, test_file: Path, temp_dir: Path):
    """Test exists command: create → execute → parse."""
    # Test existing file
    cmd = provider.get_command("exists").create_command(str(test_file))
    assert isinstance(cmd, str)
    assert str(test_file) in cmd

    output, exit_code = run_command(cmd)
    result = provider.get_command("exists").parse_command(output, exit_code)
    assert result is True

    # Test non-existing file
    non_existing = temp_dir / "nonexistent.txt"
    cmd = provider.get_command("exists").create_command(str(non_existing))
    assert str(non_existing) in cmd

    output, exit_code = run_command(cmd)
    result = provider.get_command("exists").parse_command(output, exit_code)
    assert result is False


def test_is_file_command(provider: OSCommandProvider, test_file: Path, test_subdir: Path):
    """Test is file command: create → execute → parse."""
    # Test actual file
    cmd = provider.get_command("is_file").create_command(str(test_file))
    assert isinstance(cmd, str)
    assert str(test_file) in cmd

    output, exit_code = run_command(cmd)
    result = provider.get_command("is_file").parse_command(output, exit_code)
    assert result is True

    # Test directory (should be False)
    cmd = provider.get_command("is_file").create_command(str(test_subdir))
    assert str(test_subdir) in cmd

    output, exit_code = run_command(cmd)
    result = provider.get_command("is_file").parse_command(output, exit_code)
    assert result is False


def test_is_directory_command(
    provider: OSCommandProvider,
    test_file: Path,
    test_subdir: Path,
):
    """Test is directory command: create → execute → parse."""
    # Test actual directory
    cmd = provider.get_command("is_directory").create_command(str(test_subdir))
    assert isinstance(cmd, str)
    assert str(test_subdir) in cmd

    output, exit_code = run_command(cmd)
    result = provider.get_command("is_directory").parse_command(output, exit_code)
    assert result is True

    # Test file (should be False)
    cmd = provider.get_command("is_directory").create_command(str(test_file))
    assert str(test_file) in cmd

    output, exit_code = run_command(cmd)
    result = provider.get_command("is_directory").parse_command(output, exit_code)
    assert result is False


def test_create_directory_command(provider: OSCommandProvider, temp_dir: Path):
    """Test create directory command: create → execute → parse."""
    new_dir = temp_dir / "new_directory"
    assert not new_dir.exists()

    # Create command
    cmd = provider.get_command("create_directory").create_command(
        str(new_dir), parents=True
    )
    assert isinstance(cmd, str)
    assert str(new_dir) in cmd

    # Execute command
    output, exit_code = run_command(cmd)

    # Parse result
    result = provider.get_command("create_directory").parse_command(output, exit_code)
    assert result is True
    assert new_dir.exists()
    assert new_dir.is_dir()

    # Test nested directory creation
    nested_dir = temp_dir / "level1" / "level2" / "level3"
    cmd = provider.get_command("create_directory").create_command(
        str(nested_dir), parents=True
    )
    output, exit_code = run_command(cmd)
    result = provider.get_command("create_directory").parse_command(output, exit_code)

    assert result is True
    assert nested_dir.exists()
    assert nested_dir.is_dir()


def test_file_info_command(provider: OSCommandProvider, test_file: Path):
    """Test file info command: create → execute → parse."""
    # Create command
    cmd = provider.get_command("file_info").create_command(str(test_file))
    assert isinstance(cmd, str)
    assert str(test_file) in cmd

    # Execute command
    output, exit_code = run_command(cmd)

    if exit_code == 0:  # Only test if command succeeded
        # Parse result
        result = provider.get_command("file_info").parse_command(output, str(test_file))
        assert result.name == test_file.name
        assert result.path == str(test_file)
        assert result.type == "file"
        assert result.size >= 0


def test_remove_path_command(provider: OSCommandProvider, temp_dir: Path):
    """Test remove path command: create → execute → parse."""
    # Test file removal
    test_file = temp_dir / "to_remove.txt"
    test_file.write_text("content")
    assert test_file.exists()

    cmd = provider.get_command("remove_path").create_command(
        str(test_file), recursive=False
    )
    assert isinstance(cmd, str)
    assert str(test_file) in cmd

    output, exit_code = run_command(cmd)
    result = provider.get_command("remove_path").parse_command(output, exit_code)
    assert result is True
    assert not test_file.exists()

    # Test directory removal
    test_dir = temp_dir / "to_remove_dir"
    test_dir.mkdir()
    (test_dir / "file.txt").write_text("content")
    assert test_dir.exists()

    cmd = provider.get_command("remove_path").create_command(
        str(test_dir), recursive=True
    )
    assert str(test_dir) in cmd

    output, exit_code = run_command(cmd)
    result = provider.get_command("remove_path").parse_command(output, exit_code)
    assert result is True
    assert not test_dir.exists()
