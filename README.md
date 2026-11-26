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

Install anyenv with its HTTP extra. HTTP goes through
[httpx2](https://github.com/pydantic/httpx2), pydantic's maintained fork of httpx:

```bash
pip install "anyenv[httpx2]"  # recommended
pip install "anyenv[httpx]"  # legacy: original httpx, kept for compatibility
```

When both are installed, `httpx2` is used. anyenv itself never needs the legacy `httpx`
package once `httpx2` is installed. Under Pyodide (`sys.platform == "emscripten"`), the
client sends its requests through the browser's `fetch`.


## HTTP

```python
import anyenv

# GET: the response's body is read already, its accessors are plain attributes
response = await anyenv.get("https://api.example.com/data")
print(response.status_code, response.reason, response.headers["content-type"])
print(response.text)  # str
print(response.content)  # bytes
print(response.json())  # parsed JSON
user = response.validated_json(User)  # validated (pydantic models, dataclasses, ...)

# The body directly
data = await anyenv.get_json("https://api.example.com/users")
text = await anyenv.get_text("https://example.com/page.html")
blob = await anyenv.get_bytes("https://example.com/image.png")

# POST
response = await anyenv.post("https://api.example.com/create", json={"name": "test"})
result = await anyenv.post_json("https://api.example.com/api", {"key": "value"})

# Downloads (written to <path>.part, renamed when complete)
await anyenv.download("https://example.com/file.zip", "file.zip", progress_callback=print)

# Authentication: bearer (default), basic, a header or a query parameter
data = await anyenv.get_json(url, api_key=token)
data = await anyenv.get_json(url, api_key=key, auth_type="header", auth_header_name="X-Key")
```

### Sessions: one client for many requests

Without a session, every call opens (and closes) its own client: a new TCP and TLS
connection per request. `http_session()` keeps one client open; while it is, the helpers
above use it too, also when a library you call uses them:

```python
async with anyenv.http_session(base_url="https://api.github.com", timeout=30) as s:
    repo = await s.get_json("/repos/phil65/anyenv")  # relative to base_url
    issues = await anyenv.get_json("/repos/phil65/anyenv/issues")  # same client
```

- `base_url` resolves relative URLs; `headers` go with every request to `base_url`
  (without a `base_url`: with every request through the session).
- Sessions nest: the innermost open one is used; leaving it restores the outer one.
  Tasks started inside a session inherit it (a `ContextVar`); other tasks don't see it.
- A helper call asking for other cache settings than the session's (`cache=`,
  `cache_dir=`, `cache_ttl=`) uses a client of its own.
- The session object has the same methods: `request`, `get`, `post`, `get_json`,
  `get_text`, `get_bytes`, `post_json`, `download`.

### Caching

Responses can be cached with [hishel](https://github.com/karpetrosyan/hishel), for a TTL
anyenv sets (servers' `Cache-Control: max-age=0` is ignored). Entries are keyed by URL and
request headers, credentials included: one API key's response is never served for another.

```python
data = await anyenv.get_json(url, cache=True, cache_ttl="1d")  # SQLite file in the user cache dir
async with anyenv.http_session(cache=True, cache_backend="memory"):  # for the session only
    ...
```

### Synchronous versions

Every helper has a `*_sync` counterpart (`get_sync`, `get_json_sync`, `download_sync`, ...)
with the same options. Each call runs on an event loop of its own, with its own client
(also inside an `http_session` block).

### Error handling

```python
from anyenv import HttpError, RequestError, ResponseError

try:
    response = await anyenv.get("https://api.example.com/data")
except RequestError as e:  # connection failed, timeout
    print(f"Request failed: {e}")
except ResponseError as e:  # 4xx / 5xx; e.response has the body
    print(f"Server error {e.status_code}: {e.response.text}")
```

### Migrating from 2.x

anyenv 3.0 has one HTTP stack (httpx) and synchronous response accessors:

| 2.x | 3.0 |
|---|---|
| `await r.text()`, `await r.json()`, `await r.bytes()` | `r.text`, `r.json()`, `r.content` |
| `await r.validated_json(T)` | `r.validated_json(T)` |
| `backend=...`, `get_backend()`, `HttpBackend`, `BackendType` | gone: httpx2 (or httpx) only |
| `anyenv[aiohttp]`, the pyodide backend | gone: `anyenv[httpx2]`; Pyodide uses `fetch` through httpx |
| `Session`, `backend.create_session()` | `async with anyenv.http_session(...) as s:` |

The body helpers (`get_json`, `get_text`, `post_json`, ...) and their `*_sync` versions
keep their API.

## LSP diagnostics

`DiagnosticRunner` runs the CLI diagnostics of language servers (pyright, mypy, ty, ...);
`run_all(files, concurrency=n)` runs up to `n` servers at once (default: one after another).

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
results = await gather(async_func1(), async_func2(), async_func3(), return_exceptions=True)

# Call function and gather results
func_results = await call_and_gather(
    my_function,
    [arg1, arg2, arg3],  # Arguments to call function with
    max_workers=5,
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

## Environment Compatibility

All functionality automatically adapts to the execution environment:

- **PyOdide**: Uses browser-compatible implementations (HTTP through `fetch`)
- **Standard Python**: HTTP through httpx2 (or legacy httpx)
- **Limited environments**: Falls back to stdlib implementations
- **Async contexts**: Provides async implementations
- **Sync contexts**: Provides synchronous alternatives

This ensures your code works consistently across web browsers, Jupyter notebooks, serverless functions, and traditional Python environments.
