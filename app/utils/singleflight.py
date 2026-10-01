"""Share identical in-flight reads without sharing cancellation between callers."""
import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class _Flight:
    task: asyncio.Task
    waiters: int = 0


class SingleFlight:
    def __init__(self):
        self._pending: dict[tuple[asyncio.AbstractEventLoop, str], _Flight] = {}

    async def run(self, key: str, factory: Callable[[], Awaitable[Any]]) -> Any:
        # Tasks may not cross event loops (notably independent test/app lifecycles).
        identity = (asyncio.get_running_loop(), key)
        flight = self._pending.get(identity)
        if flight is None or flight.task.done():
            flight = _Flight(asyncio.create_task(factory()))
            self._pending[identity] = flight

            def finished(task):
                if self._pending.get(identity) is flight:
                    self._pending.pop(identity, None)
                if not task.cancelled():
                    task.exception()  # Also consume failures if every caller went away.

            flight.task.add_done_callback(finished)
        flight.waiters += 1
        try:
            return await asyncio.shield(flight.task)
        finally:
            flight.waiters -= 1
            if flight.waiters == 0 and not flight.task.done():
                if self._pending.get(identity) is flight:
                    self._pending.pop(identity, None)
                flight.task.cancel()
                await asyncio.gather(flight.task, return_exceptions=True)
