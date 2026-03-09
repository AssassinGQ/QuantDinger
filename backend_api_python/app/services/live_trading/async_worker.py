"""
AsyncWorker — unified task dispatcher with asyncio event loop + IO thread pool.

Provides a single `submit()` method that auto-detects whether the input is a
coroutine or a synchronous callable and routes it to the appropriate executor.
Returns a `concurrent.futures.Future` — the caller decides whether to block
with `.result(timeout)` or fire-and-forget by discarding the future.

This module is exchange-agnostic and can be reused by any trading client.
"""

import asyncio
import concurrent.futures
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Union, Callable, Coroutine


class AsyncWorker:
    """
    Manages a dedicated asyncio event-loop thread and an IO thread pool.

    - Coroutines run on the event-loop thread.
    - Synchronous callables run in the IO thread pool (so they never block
      the event loop).
    """

    def __init__(self, name: str = "async-worker", io_workers: int = 4):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._io_pool = ThreadPoolExecutor(
            max_workers=io_workers, thread_name_prefix=f"{name}-io",
        )
        self._name = name

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._ready.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name=self._name,
        )
        self._thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError(f"AsyncWorker '{self._name}' failed to start")

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()

    # ------------------------------------------------------------------

    def submit(
        self,
        fn_or_coro: Union[Coroutine, Callable[..., Any]],
    ) -> concurrent.futures.Future:
        """
        Submit a task and return a Future.

        *fn_or_coro* can be:
        - An already-created coroutine  (``async_fn()``)
        - An ``async def`` function      (``async_fn`` — will be called)
        - A regular callable / lambda    (runs in the IO thread pool)

        The caller controls blocking behaviour:
        - ``future.result(timeout=10)`` — block until done or timeout.
        - Ignore the future             — fire-and-forget.
        """
        if self._loop is None or self._loop.is_closed():
            raise RuntimeError("AsyncWorker is not running")
        coro = self._wrap(fn_or_coro)
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    # ------------------------------------------------------------------

    def _wrap(
        self,
        fn_or_coro: Union[Coroutine, Callable[..., Any]],
    ) -> Coroutine:
        if asyncio.iscoroutine(fn_or_coro):
            return fn_or_coro
        if asyncio.iscoroutinefunction(fn_or_coro):
            return fn_or_coro()
        if callable(fn_or_coro):
            return self._run_sync(fn_or_coro)
        raise TypeError(
            f"expected callable or coroutine, got {type(fn_or_coro).__name__}"
        )

    async def _run_sync(self, fn: Callable[..., Any]) -> Any:
        return await self._loop.run_in_executor(self._io_pool, fn)

    # ------------------------------------------------------------------

    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        return self._loop

    @property
    def running(self) -> bool:
        return (
            self._thread is not None
            and self._thread.is_alive()
            and self._loop is not None
            and self._loop.is_running()
        )

    def shutdown(self) -> None:
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._io_pool.shutdown(wait=False)
        self._loop = None
        self._thread = None
