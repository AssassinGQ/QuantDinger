"""
TaskQueue — unified task submission for IBKRClient.

Components:
  - Task:      unit of work carrying a callable, is_blocking flag, and a Future.
  - TaskQueue: thread-safe submit() → Future; internal Worker dequeues and dispatches.
  - Worker:    daemon thread; loops over the queue and routes each Task to
               the appropriate executor by is_blocking flag.
"""

import queue
import threading
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any, Callable

from app.services.live_trading.async_executor import LoopExecutor, ThreadsPoolExecutor
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Task:
    fn: Any
    is_blocking: bool = False
    future: Future = field(default_factory=Future)


class TaskQueue:
    """Single entry-point for all callers.

    Usage::

        tq = TaskQueue()
        tq.start()
        future = tq.submit(lambda: ib.positions(), is_blocking=False)
        positions = future.result(timeout=10)
    """

    def __init__(self, loop_executor_name: str, pool_executor_name: str, pool_workers: int = 4):
        self._loop_executor = LoopExecutor(name=loop_executor_name)
        self._thread_pool_executor = ThreadsPoolExecutor(max_workers=pool_workers, name=pool_executor_name)
        self._queue: queue.Queue[Task | None] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._loop_executor.start()
        self._thread_pool_executor.start()
        self._running = True
        self._worker = threading.Thread(
            target=self._poll, daemon=True, name="tq-worker",
        )
        self._worker.start()

    def submit(self, fn: Callable, is_blocking: bool = False) -> Future:
        """Submit a callable and return a Future for its result."""
        if not self._running:
            raise RuntimeError("TaskQueue is not running")
        task = Task(fn=fn, is_blocking=is_blocking)
        self._queue.put(task)
        return task.future

    def _poll(self) -> None:
        while self._running:
            try:
                task = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if task is None:
                break
            executor = self._thread_pool_executor if task.is_blocking else self._loop_executor
            try:
                executor.execute(task.fn, task.future)
            except Exception as exc:
                if not task.future.done():
                    task.future.set_exception(exc)

    def shutdown(self) -> None:
        self._running = False
        self._queue.put(None)
        if self._worker is not None:
            self._worker.join(timeout=5)
        self._loop_executor.shutdown()
        self._thread_pool_executor.shutdown()
