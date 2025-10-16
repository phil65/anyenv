"""Calling package."""

from __future__ import annotations

from anyenv.calling.threadgroup import ThreadGroup
from anyenv.calling.async_executor import method_spawner, function_spawner

__all__ = ["ThreadGroup", "function_spawner", "method_spawner"]
