"""Extended as_generated function."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import AsyncIterable, AsyncIterator, Iterable


async def as_generated[T](
    iterables: Iterable[AsyncIterable[T]] | None = None,
    queues: Iterable[asyncio.Queue[T]] | None = None,
    *,
    return_exceptions: bool = False,
) -> AsyncIterator[T]:
    """Yield results from async iterables and/or queues as they are produced.

    Like aioitertools.as_generated, but extended to also handle asyncio.Queue objects
    directly alongside async iterables. Creates separate tasks to drain each source
    and yields results in the order they are produced across all sources.

    Args:
        iterables: Async iterables to drain (generators, streams, etc.)
        queues: Asyncio queues to drain
        return_exceptions: If False, raise exceptions. If True, yield them as results.

    Example:
        async def generator(x):
            for i in range(x):
                yield f"gen-{i}"

        queue = asyncio.Queue()
        await queue.put("queue-item-1")
        await queue.put("queue-item-2")
        await queue.put(None)  # Signal end

        async for value in as_generated([generator(3)], [queue]):
            print(value)  # Mixed output from generator and queue
    """
    exc_queue: asyncio.Queue[Exception] = asyncio.Queue()
    result_queue: asyncio.Queue[T | None] = asyncio.Queue()

    async def drain_iterable(iterable: AsyncIterable[T]) -> None:
        try:
            async for item in iterable:
                await result_queue.put(item)
        except asyncio.CancelledError:
            if isinstance(iterable, AsyncGenerator):
                await iterable.aclose()
            raise
        except Exception as e:  # noqa: BLE001
            await exc_queue.put(e)
        finally:
            await result_queue.put(None)  # Signal this source is done

    async def drain_queue(queue: asyncio.Queue[T]) -> None:
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=0.1)
                    if item is None:  # None signals end of queue
                        break
                    await result_queue.put(item)
                except TimeoutError:
                    continue
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            await exc_queue.put(e)
        finally:
            await result_queue.put(None)  # Signal this source is done

    # Create tasks for all sources
    tasks = []
    source_count = 0

    if iterables:
        for iterable in iterables:
            tasks.append(asyncio.create_task(drain_iterable(iterable)))
            source_count += 1

    if queues:
        for queue in queues:
            tasks.append(asyncio.create_task(drain_queue(queue)))
            source_count += 1

    if source_count == 0:
        return

    sources_finished = 0

    try:
        while sources_finished < source_count:
            # Check for exceptions first
            try:
                exc = exc_queue.get_nowait()
                if return_exceptions:
                    yield exc  # type: ignore
                else:
                    raise exc
            except asyncio.QueueEmpty:
                pass

            # Get results
            try:
                value = await asyncio.wait_for(result_queue.get(), timeout=0.01)
                if value is None:  # Signal that a source finished
                    sources_finished += 1
                else:
                    yield value
            except TimeoutError:
                # No items available, check if any tasks completed
                for task in list(tasks):
                    if task.done():
                        tasks.remove(task)
                        try:
                            await task  # This will raise if task had exception
                        except Exception as e:
                            if return_exceptions:
                                yield e  # type: ignore
                            else:
                                raise
                continue

    except (asyncio.CancelledError, GeneratorExit):
        pass
    finally:
        # Cancel all remaining tasks
        for task in tasks:
            if not task.done():
                task.cancel()

        # Wait for all tasks to complete
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
