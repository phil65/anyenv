"""Tests for OS command implementations."""

from __future__ import annotations

import pytest

from anyenv.os_commands.providers import get_os_command_provider


@pytest.fixture
def provider():
    """Get OS command provider for current platform."""
    return get_os_command_provider()


def test_list_directory_command(provider):
    """Test list directory command generation."""
    cmd = provider.get_command("list_directory").create_command("/tmp", detailed=True)
    assert isinstance(cmd, str)
    assert "/tmp" in cmd


def test_exists_command(provider):
    """Test exists command generation."""
    cmd = provider.get_command("exists").create_command("/tmp/test")
    assert isinstance(cmd, str)
    assert "/tmp/test" in cmd


def test_is_file_command(provider):
    """Test is file command generation."""
    cmd = provider.get_command("is_file").create_command("/tmp/test.txt")
    assert isinstance(cmd, str)
    assert "/tmp/test.txt" in cmd


def test_is_directory_command(provider):
    """Test is directory command generation."""
    cmd = provider.get_command("is_directory").create_command("/tmp/test")
    assert isinstance(cmd, str)
    assert "/tmp/test" in cmd


def test_create_directory_command(provider):
    """Test create directory command generation."""
    cmd = provider.get_command("create_directory").create_command(
        "/tmp/newdir", parents=True
    )
    assert isinstance(cmd, str)
    assert "/tmp/newdir" in cmd


def test_remove_path_command(provider):
    """Test remove path command generation."""
    cmd = provider.get_command("remove_path").create_command("/tmp/test", recursive=True)
    assert isinstance(cmd, str)
    assert "/tmp/test" in cmd


def test_file_info_command(provider):
    """Test file info command generation."""
    cmd = provider.get_command("file_info").create_command("/tmp/test.txt")
    assert isinstance(cmd, str)
    assert "/tmp/test.txt" in cmd
