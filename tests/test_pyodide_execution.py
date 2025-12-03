"""Tests for PyodideExecutionEnvironment."""

import shutil

import pytest

from anyenv.code_execution import PyodideExecutionEnvironment


# Skip all tests if deno is not installed
pytestmark = pytest.mark.skipif(
    shutil.which("deno") is None,
    reason="Deno is not installed",
)


async def test_pyodide_simple_execution():
    """Test simple code execution."""
    code = "x = 2 + 3; x"

    async with PyodideExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result == 5
    assert result.duration >= 0
    assert result.error is None


async def test_pyodide_execution_with_print():
    """Test execution with stdout capture."""
    code = "print('Hello from Pyodide!')"

    async with PyodideExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.stdout is not None
    assert "Hello from Pyodide!" in result.stdout


async def test_pyodide_execution_state_persistence():
    """Test that state persists within a session."""
    async with PyodideExecutionEnvironment() as env:
        # First execution - define variable
        result1 = await env.execute("x = 42")
        assert result1.success is True

        # Second execution - use the variable
        result2 = await env.execute("x * 2")
        assert result2.success is True
        assert result2.result == 84


async def test_pyodide_execution_error_handling():
    """Test error handling for syntax errors."""
    code = "x = 5; y = x +"

    async with PyodideExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is False
    assert result.error is not None
    assert "SyntaxError" in result.stderr or "SyntaxError" in result.error


async def test_pyodide_execution_runtime_error():
    """Test error handling for runtime errors."""
    code = "undefined_variable"

    async with PyodideExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is False
    assert result.error is not None
    assert "NameError" in result.stderr or "NameError" in result.error


async def test_pyodide_execution_division_by_zero():
    """Test error handling for division by zero."""
    code = "x = 1 / 0"

    async with PyodideExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is False
    assert result.error is not None
    assert "ZeroDivisionError" in result.stderr or "ZeroDivisionError" in result.error


async def test_pyodide_auto_install_package():
    """Test auto-installation of packages via micropip."""
    code = """
import numpy as np
x = np.array([1, 2, 3])
int(x.sum())
"""

    async with PyodideExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    # Pyodide may convert numpy scalars to dicts, so extract value if needed
    if isinstance(result.result, dict):
        assert 6 in result.result.values()
    else:
        assert result.result == 6


async def test_pyodide_streaming_execution():
    """Test streaming code execution."""
    code = """
for i in range(3):
    print(f"Line {i}")
"""
    events = []

    async with PyodideExecutionEnvironment() as env:
        async for event in env.stream_code(code):
            events.append(event)

    # Should have at least started + some output + completed
    assert len(events) >= 2

    event_types = [e.event_type for e in events]
    assert "started" in event_types
    assert "completed" in event_types or "error" in event_types


async def test_pyodide_pre_installed_dependencies():
    """Test pre-installing dependencies on startup."""
    async with PyodideExecutionEnvironment(dependencies=["six"]) as env:
        result = await env.execute("import six; six.PY3")

    assert result.success is True
    assert result.result is True


async def test_pyodide_complex_data_types():
    """Test handling of complex Python data types."""
    code = """
result = {
    'list': [1, 2, 3],
    'dict': {'a': 1, 'b': 2},
    'tuple': (1, 2, 3),
    'set': {1, 2, 3},
}
result
"""
    async with PyodideExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result is not None
    assert result.result["list"] == [1, 2, 3]
    assert result.result["dict"] == {"a": 1, "b": 2}


async def test_pyodide_multiple_print_statements():
    """Test multiple print statements are captured."""
    code = """
print("First line")
print("Second line")
print("Third line")
"""
    async with PyodideExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.stdout is not None
    assert "First line" in result.stdout
    assert "Second line" in result.stdout
    assert "Third line" in result.stdout


# =============================================================================
# Filesystem Tests
# =============================================================================


async def test_pyodide_fs_write_and_read():
    """Test writing and reading files via PyodideFS."""
    async with PyodideExecutionEnvironment() as env:
        fs = env.get_fs()

        # Write a file
        test_content = b"Hello from PyodideFS!"
        await fs._pipe_file("/tmp/test_file.txt", test_content)

        # Read it back
        content = await fs._cat_file("/tmp/test_file.txt")
        assert content == test_content


async def test_pyodide_fs_mkdir_and_ls():
    """Test creating directories and listing contents."""
    async with PyodideExecutionEnvironment() as env:
        fs = env.get_fs()

        # Create directory
        await fs._mkdir("/tmp/test_dir")

        # Write some files
        await fs._pipe_file("/tmp/test_dir/file1.txt", b"content1")
        await fs._pipe_file("/tmp/test_dir/file2.txt", b"content2")

        # List directory
        entries = await fs._ls("/tmp/test_dir", detail=True)
        names = [e["name"] for e in entries]

        assert any("file1.txt" in n for n in names)
        assert any("file2.txt" in n for n in names)


async def test_pyodide_fs_exists():
    """Test checking if paths exist."""
    async with PyodideExecutionEnvironment() as env:
        fs = env.get_fs()

        # File shouldn't exist yet
        assert not await fs._exists("/tmp/nonexistent_file.txt")

        # Create it
        await fs._pipe_file("/tmp/exists_test.txt", b"test")

        # Now it should exist
        assert await fs._exists("/tmp/exists_test.txt")


async def test_pyodide_fs_info():
    """Test getting file info."""
    async with PyodideExecutionEnvironment() as env:
        fs = env.get_fs()

        # Write a file with known content
        content = b"12345"
        await fs._pipe_file("/tmp/info_test.txt", content)

        # Get info
        info = await fs._info("/tmp/info_test.txt")
        assert info["type"] == "file"
        assert info["size"] == len(content)


async def test_pyodide_fs_rm():
    """Test removing files."""
    async with PyodideExecutionEnvironment() as env:
        fs = env.get_fs()

        # Create and verify
        await fs._pipe_file("/tmp/to_delete.txt", b"delete me")
        assert await fs._exists("/tmp/to_delete.txt")

        # Delete
        await fs._rm_file("/tmp/to_delete.txt")

        # Verify deleted
        assert not await fs._exists("/tmp/to_delete.txt")


async def test_pyodide_fs_isfile_isdir():
    """Test isfile and isdir checks."""
    async with PyodideExecutionEnvironment() as env:
        fs = env.get_fs()

        # Create a file and directory
        await fs._mkdir("/tmp/is_dir_test")
        await fs._pipe_file("/tmp/is_file_test.txt", b"test")

        # Check types
        assert await fs._isdir("/tmp/is_dir_test")
        assert not await fs._isfile("/tmp/is_dir_test")
        assert await fs._isfile("/tmp/is_file_test.txt")
        assert not await fs._isdir("/tmp/is_file_test.txt")


async def test_pyodide_fs_integration_with_code():
    """Test that files written via FS are visible to executed code."""
    async with PyodideExecutionEnvironment() as env:
        fs = env.get_fs()

        # Write a file via filesystem
        await fs._pipe_file("/tmp/from_fs.txt", b"Written via PyodideFS")

        # Read it via executed code (need to return the value explicitly)
        result = await env.execute("""
def read_file():
    with open('/tmp/from_fs.txt', 'r') as f:
        return f.read()

read_file()
""")

        assert result.success is True
        assert result.result == "Written via PyodideFS"


async def test_pyodide_fs_code_writes_fs_reads():
    """Test that files written by code are visible via FS."""
    async with PyodideExecutionEnvironment() as env:
        fs = env.get_fs()

        # Write via executed code
        result = await env.execute("""
with open('/tmp/from_code.txt', 'w') as f:
    f.write('Written via Python code')
""")
        assert result.success is True

        # Read via filesystem
        content = await fs._cat_file("/tmp/from_code.txt")
        assert content == b"Written via Python code"


if __name__ == "__main__":
    pytest.main(["-v", __file__])
