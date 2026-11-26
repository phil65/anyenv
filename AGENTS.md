# AGENTS.md

## Overview

Compatibility layer for some basic operations to allow painless operation in PyOdide and Python pre-releases

## Commands

```bash
uv sync --all-extras          # setup
uv run pytest                 # tests
uv run ruff check . && uv run ruff format --check .
uv run ty check               # type check (warnings fail too)
uv run mknodes build          # docs (README + auto-generated pages)
uv build
```

## HTTP layer (`src/anyenv/download/`)

- One stack: httpx2 (preferred) or legacy httpx (`httpx_backend/module.py` picks the
  flavour); under Pyodide the client gets the fetch transport (`httpx_backend/js_transport.py`).
- `session.py`: `HttpSession` (one client, `base_url`, headers only to `base_url`) and
  `http_session()`, which sets a `ContextVar` so the helpers in `functional.py` use the open
  session. Without one, each helper call opens its own client (`session_for`). The `*_sync`
  helpers run with no session (`without_session`): their loop can't use another loop's client.
- `base.py`: `HttpResponse`, a thin wrapper with sync accessors (`text`, `content`, `json()`).
- Caching: hishel only (`httpx_backend/cache.py`); keys include credentials and other
  request headers.
- Tests run against local servers; `httpx_flavour` (tests/conftest.py) runs a test per
  installed flavour.

## Pyodide

- Supported Pyodide version: **314.x** (Python 3.14; checked against 314.0.8). Older 0.x
  releases are not supported (`requires-python = ">=3.14"`).
- Detection uses `sys.platform == "emscripten"`; HTTP goes through `httpx_backend/js_transport.py`
  (`js.fetch`, `js.AbortSignal.timeout`, `pyodide.ffi.to_js`), and package installation uses
  `micropip`.
- Try it in a browser using the Pyodide console (<https://pyodide.org/en/stable/console.html>):

  ```python
  import micropip

  await micropip.install(["anyenv", "httpx2"])
  import anyenv

  await anyenv.get_json("https://httpbin.org/get")
  ```

## Specs

Protocols / APIs this project implements (keep the Targets column up to date when touching
protocol code). Write "unpinned (tracks latest)" if no version is targeted.

| Spec | URL | Targets | Code | Update check |
|---|---|---|---|---|
