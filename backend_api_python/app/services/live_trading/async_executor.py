"""
AsyncExecutor — abstract interface for non-blocking task execution.

Two concrete implementations:
  - LoopExecutor:   runs coroutines on a dedicated asyncio event-loop thread.
  - ThreadsPoolExecutor: runs blocking callables in a ThreadPoolExecutor.
"""

import asyncio
import threading
from abc import ABC, abstractmethod
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from app.utils.logger import get_logger

logger = get_logger(__name__)


def _resolve(caller_future: Future, asyncio_future: asyncio.Future) -> None:
    """Bridge an asyncio.Future result into a concurrent.futures.Future."""
    if caller_future.done():
        return
    try:
        result = asyncio_future.result()
        caller_future.set_result(result)
    except asyncio.CancelledError:
        caller_future.cancel()
    except Exception as exc:
        caller_future.set_exception(exc)


class AsyncExecutor(ABC):
    """Non-blocking task executor.  ``execute`` must return immediately."""

    @abstractmethod
    def execute(self, fn: Any, future: Future) -> None:
        """Trigger *fn* asynchronously; write result into *future* when done."""

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def shutdown(self) -> None: ...


class LoopExecutor(AsyncExecutor):
    """Runs tasks on a dedicated asyncio event-loop thread.

    - Coroutines are scheduled directly on the loop.
    - Sync callables are wrapped in a trivial coroutine so they execute
      on the loop thread (ib_insync data structures are not thread-safe).
    """

    def __init__(self, name: str = "ib-loop"):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
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
            raise RuntimeError(f"IBExecutor '{self._name}' failed to start")

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()

    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        return self._loop

    def execute(self, fn: Any, future: Future) -> None:
        if self._loop is None or self._loop.is_closed():
            future.set_exception(RuntimeError("IBExecutor is not running"))
            return

        if asyncio.iscoroutine(fn):
            coro = fn
        else:
            async def _wrap():
                return fn()
            coro = _wrap()

        af = asyncio.run_coroutine_threadsafe(coro, self._loop)
        af.add_done_callback(lambda f: _resolve(future, f))

    def shutdown(self) -> None:
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._loop = None
        self._thread = None


class ThreadsPoolExecutor(AsyncExecutor):
    """Runs tasks in a thread pool (for DB, notifications, etc.)."""

    def __init__(self, max_workers: int = 4, name: str = "io"):
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix=name,
        )

    def start(self) -> None:
        pass

    def execute(self, fn: Any, future: Future) -> None:
        def _run() -> None:
            try:
                result = fn()
                future.set_result(result)
            except Exception as exc:
                future.set_exception(exc)

        self._pool.submit(_run)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False)
