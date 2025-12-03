"""Pyodide execution environment that runs Python in WASM via Deno."""

from __future__ import annotations

from anyenv.code_execution.pyodide_provider.filesystem import PyodideFS
from anyenv.code_execution.pyodide_provider.provider import PyodideExecutionEnvironment

__all__ = ["PyodideExecutionEnvironment", "PyodideFS"]
