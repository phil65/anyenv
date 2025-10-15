"""Calling package."""

from __future__ import annotations

from anyenv.calling.threadgroup import ThreadGroup
from anyenv.calling.async_executor import method_spawner, function_spawner
from anyenv.calling.streams import merge_streams

__all__ = ["ThreadGroup", "function_spawner", "merge_streams", "method_spawner"]
