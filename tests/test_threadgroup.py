from __future__ import annotations

import contextvars

import pytest

from anyenv.threadgroup.threadgroup import ThreadGroup


def test_threadgroup():
    ctx_var = contextvars.ContextVar("example", default="default")

    def test_with_context():
        return ctx_var.get()

    # Set a value in the main thread
    ctx_var.set("main thread value")

    # Without context preservation
    with ThreadGroup[str](preserve_context=False) as tg:
        tg.spawn(test_with_context)
    assert tg.results == ["default"]

    # With context preservation
    with ThreadGroup[str](preserve_context=True) as tg:
        tg.spawn(test_with_context)
    assert tg.results == ["main thread value"]


if __name__ == "__main__":
    pytest.main([__file__])
