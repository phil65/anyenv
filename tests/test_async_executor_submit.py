"""Fire-and-forget submit keeps its task alive."""

import asyncio
import gc
from typing import Any
import weakref

from anyenv.calling.async_executor import function_spawner


async def test_submitted_task_survives_garbage_collection():
    """Tasks are held weakly by asyncio: submit() must keep a reference itself."""
    waiting: list[weakref.ref[asyncio.Future[Any]]] = []
    finished = asyncio.Event()

    @function_spawner
    async def work() -> None:
        # A future nothing else references: only the task keeps it (and itself) alive.
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        waiting.append(weakref.ref(future))
        await future
        finished.set()

    work.submit()
    await asyncio.sleep(0)
    gc.collect()
    future = waiting[0]()
    assert future is not None, "the submitted task was garbage-collected"
    future.set_result(None)
    await asyncio.wait_for(finished.wait(), 1)
