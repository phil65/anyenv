"""Executors must come from their defining module, not the lazy `concurrent.futures` facade.

On Python 3.15 `concurrent.futures` exposes its executors as lazy imports; some import
hooks (e.g. PySide6/shiboken) hand those out unresolved, so subclassing
`concurrent.futures.ThreadPoolExecutor` raised "cannot create 'lazy_import' instances".
"""

from __future__ import annotations

from concurrent.futures.thread import ThreadPoolExecutor

from anyenv.calling import async_executor, threadgroup


def test_context_executor_subclasses_real_thread_pool():
    """ContextExecutor subclasses the real ThreadPoolExecutor class."""
    assert threadgroup.ContextExecutor.__mro__[1] is ThreadPoolExecutor
    assert threadgroup.ThreadPoolExecutor is ThreadPoolExecutor


def test_async_executor_uses_real_thread_pool():
    """The async executor uses the real ThreadPoolExecutor class."""
    assert async_executor.ThreadPoolExecutor is ThreadPoolExecutor
