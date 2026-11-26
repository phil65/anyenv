"""Extended as_generated function."""

import contextlib
from typing import TYPE_CHECKING

from anyenv.async_run import as_generated as merge


if TYPE_CHECKING:
    import asyncio
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
    A queue ends at a `None` item; iterables may yield `None` as a value.

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
    sources: list[AsyncIterable[T]] = [*(iterables or []), *map(_drain, queues or [])]
    async with contextlib.aclosing(merge(sources, return_exceptions=return_exceptions)) as merged:
        async for value in merged:
            yield value


async def _drain[T](queue: asyncio.Queue[T]) -> AsyncIterator[T]:
    while (item := await queue.get()) is not None:
        yield item
