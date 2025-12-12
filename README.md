# AnyEnv

[![PyPI License](https://img.shields.io/pypi/l/anyenv.svg)](https://pypi.org/project/anyenv/)
[![Package status](https://img.shields.io/pypi/status/anyenv.svg)](https://pypi.org/project/anyenv/)
[![Monthly downloads](https://img.shields.io/pypi/dm/anyenv.svg)](https://pypi.org/project/anyenv/)
[![Distribution format](https://img.shields.io/pypi/format/anyenv.svg)](https://pypi.org/project/anyenv/)
[![Wheel availability](https://img.shields.io/pypi/wheel/anyenv.svg)](https://pypi.org/project/anyenv/)
[![Python version](https://img.shields.io/pypi/pyversions/anyenv.svg)](https://pypi.org/project/anyenv/)
[![Implementation](https://img.shields.io/pypi/implementation/anyenv.svg)](https://pypi.org/project/anyenv/)
[![Releases](https://img.shields.io/github/downloads/phil65/anyenv/total.svg)](https://github.com/phil65/anyenv/releases)
[![Github Contributors](https://img.shields.io/github/contributors/phil65/anyenv)](https://github.com/phil65/anyenv/graphs/contributors)
[![Github Discussions](https://img.shields.io/github/discussions/phil65/anyenv)](https://github.com/phil65/anyenv/discussions)
[![Github Forks](https://img.shields.io/github/forks/phil65/anyenv)](https://github.com/phil65/anyenv/forks)
[![Github Issues](https://img.shields.io/github/issues/phil65/anyenv)](https://github.com/phil65/anyenv/issues)
[![Github Issues](https://img.shields.io/github/issues-pr/phil65/anyenv)](https://github.com/phil65/anyenv/pulls)
[![Github Watchers](https://img.shields.io/github/watchers/phil65/anyenv)](https://github.com/phil65/anyenv/watchers)
[![Github Stars](https://img.shields.io/github/stars/phil65/anyenv)](https://github.com/phil65/anyenv/stars)
[![Github Repository size](https://img.shields.io/github/repo-size/phil65/anyenv)](https://github.com/phil65/anyenv)
[![Github last commit](https://img.shields.io/github/last-commit/phil65/anyenv)](https://github.com/phil65/anyenv/commits)
[![Github release date](https://img.shields.io/github/release-date/phil65/anyenv)](https://github.com/phil65/anyenv/releases)
[![Github language count](https://img.shields.io/github/languages/count/phil65/anyenv)](https://github.com/phil65/anyenv)
[![Github commits this month](https://img.shields.io/github/commit-activity/m/phil65/anyenv)](https://github.com/phil65/anyenv)
[![Package status](https://codecov.io/gh/phil65/anyenv/branch/main/graph/badge.svg)](https://codecov.io/gh/phil65/anyenv/)
[![PyUp](https://pyup.io/repos/github/phil65/anyenv/shield.svg)](https://pyup.io/repos/github/phil65/anyenv/)

[Read the documentation!](https://phil65.github.io/anyenv/)

## Overview

AnyEnv provides a unified interface for executing code across different environments - local, subprocess, Docker containers, remote sandboxes, and more. Choose the right execution environment for your needs without changing your code.

## Getting Started


## HTTP Downloads

AnyEnv provides a unified interface for HTTP requests that works across different environments (including PyOdide):

```python
from anyenv import get, post, download, get_json, get_text, get_bytes

# Simple GET request
response = await get("https://api.example.com/data")
print(response.status_code, response.text)

# Get JSON data directly
data = await get_json("https://api.example.com/users")
print(data)  # Parsed JSON object

# Get text content
text = await get_text("https://example.com/page.html")

# Get binary data
data = await get_bytes("https://example.com/image.png")

# Download files
await download("https://example.com/file.zip", "local_file.zip")

# POST requests
response = await post("https://api.example.com/create", json={"name": "test"})

# POST JSON data directly
result = await post_json("https://api.example.com/api", {"key": "value"})
```

### Synchronous Versions
All async functions have synchronous counterparts:

```python
from anyenv import get_sync, get_json_sync, download_sync

# Synchronous versions (useful in non-async contexts)
response = get_sync("https://api.example.com/data")
data = get_json_sync("https://api.example.com/users")
download_sync("https://example.com/file.zip", "local_file.zip")
```

### Error Handling
```python
from anyenv import get, HttpError, RequestError, ResponseError

try:
    response = await get("https://api.example.com/data")
except RequestError as e:
    print(f"Request failed: {e}")
except ResponseError as e:
    print(f"Server error: {e}")
except HttpError as e:
    print(f"HTTP error: {e}")
```

## JSON Tools

Cross-platform JSON handling that works in all environments:

```python
from anyenv import load_json, dump_json, JsonLoadError, JsonDumpError

# Load JSON from various sources
data = load_json('{"key": "value"}')  # From string
data = load_json(Path("config.json"))  # From file
data = load_json(b'{"key": "value"}')  # From bytes

# Dump JSON to various targets
json_str = dump_json(data)  # To string
dump_json(data, Path("output.json"))  # To file
json_bytes = dump_json(data, return_bytes=True)  # To bytes

# Error handling
try:
    data = load_json('invalid json')
except JsonLoadError as e:
    print(f"Failed to parse JSON: {e}")

try:
    dump_json(set())  # Sets aren't JSON serializable
except JsonDumpError as e:
    print(f"Failed to serialize: {e}")
```

## Package Installation

Programmatically install Python packages across environments:

```python
from anyenv import install, install_sync

# Install packages asynchronously
await install("requests")
await install(["numpy", "pandas"])
await install("package>=1.0.0")

# Synchronous installation
install_sync("matplotlib")
install_sync(["scipy", "sklearn"])

# Install with specific options
await install("package", upgrade=True, user=True)
```

## Async Utilities

Utilities for running async/sync code and managing concurrency:

```python
from anyenv import run_sync, run_sync_in_thread, gather, call_and_gather

# Run async function from sync context
result = run_sync(async_function())

# Run sync function in thread from async context
result = await run_sync_in_thread(sync_function, arg1, arg2)

# Enhanced gather with better error handling
results = await gather(
    async_func1(),
    async_func2(),
    async_func3(),
    return_exceptions=True
)

# Call function and gather results
func_results = await call_and_gather(
    my_function,
    [arg1, arg2, arg3],  # Arguments to call function with
    max_workers=5
)
```

## Threading and Concurrency

Manage concurrent operations with ThreadGroup and spawners:

```python
from anyenv import ThreadGroup, function_spawner, method_spawner

# ThreadGroup for managing multiple concurrent operations
async with ThreadGroup() as group:
    # Add functions to run concurrently
    group.spawn(some_function, arg1, arg2)
    group.spawn(another_function, arg3)

    # Wait for all to complete
    results = await group.gather()

# Function spawner for reusable concurrent execution
spawner = function_spawner(my_function, max_workers=10)
results = await spawner([arg1, arg2, arg3, arg4])

# Method spawner for object methods
obj_spawner = method_spawner(my_object.method, max_workers=5)
results = await obj_spawner([data1, data2, data3])
```

## Testing Utilities

Tools for testing and development:

```python
from anyenv import open_in_playground

# Open interactive playground for testing (where supported)
await open_in_playground(locals())
```

## Backend Selection

Choose HTTP backends based on environment:

```python
from anyenv import get_backend, HttpBackend

# Get the best available backend for current environment
backend = get_backend()

# Use specific backend
backend = get_backend("httpx")  # or "urllib", "requests"
response = await backend.get("https://example.com")
```

## Environment Compatibility

All functionality automatically adapts to the execution environment:

- **PyOdide**: Uses browser-compatible implementations
- **Standard Python**: Uses optimal libraries (httpx, etc.)
- **Limited environments**: Falls back to stdlib implementations
- **Async contexts**: Provides async implementations
- **Sync contexts**: Provides synchronous alternatives

This ensures your code works consistently across web browsers, Jupyter notebooks, serverless functions, and traditional Python environments.
