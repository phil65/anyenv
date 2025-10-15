"""Merge multiple async streams into a single async stream."""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio


if TYPE_CHECKING:
    from collections.abc import AsyncIterable


def merge_streams[T](*streams: AsyncIterable[T]) -> AsyncIterable[T]:
    """Merge multiple async streams into a single async stream."""

    async def merged():
        sender, receiver = anyio.create_memory_object_stream(0)
        async with anyio.create_task_group() as tg:

            async def consume_stream(stream: AsyncIterable[T]):
                async with sender.clone() as stream_sender:
                    try:
                        async for item in stream:
                            await stream_sender.send(item)
                    except Exception:  # noqa: BLE001
                        pass  # Stream ended or errored

            # Start all consumers
            for stream in streams:
                tg.start_soon(consume_stream, stream)

            # Close the original sender so receiver knows when all streams are done
            await sender.aclose()

        # Process items as they arrive
        async with receiver:
            async for item in receiver:
                yield item

    return merged()


# def merge_streams[T](*streams: AsyncIterable[T]) -> AsyncIterable[T]:
#     """Merge multiple async streams into a single async stream."""

#     async def merged():
#         queue: asyncio.Queue[T | None] = asyncio.Queue()

#         async def consume_stream(stream: AsyncIterable[T]):
#             try:
#                 async for item in stream:
#                     await queue.put(item)
#             except Exception:
#                 pass  # Stream ended or errored
#             finally:
#                 await queue.put(None)  # Signal this stream is done

#         # Start all consumers
#         _tasks = [asyncio.create_task(consume_stream(stream)) for stream in streams]
#         streams_alive = len(streams)

#         while streams_alive > 0:
#             item = await queue.get()
#             if item is None:
#                 streams_alive -= 1
#             else:
#                 yield item

#     return merged()
