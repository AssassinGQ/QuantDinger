"""
TaskQueue — unified task submission for IBKRClient.

Components:
  - Task:      unit of work carrying a callable, a target ('ib'|'io'), and a Future.
  - TaskQueue: thread-safe submit() → Future; internal Worker dequeues and dispatches.
  - Worker:    daemon thread; loops over the queue and routes each Task to
               the appropriate AsyncExecutor (IBExecutor or IOExecutor) by target.
"""

import queue
import threading
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any, Callable, Dict

from app.services.live_trading.async_executor import AsyncExecutor
from app.utils.logger import get_logger

logger = get_logger(__name__)

IB = "ib"
IO = "io"


@dataclass
class Task:
    fn: Any
    target: str = IB
    future: Future = field(default_factory=Future)


class TaskQueue:
    """Single entry-point for all callers.

    Usage::

        tq = TaskQueue(executors={"ib": ib_executor, "io": io_executor})
        tq.start()
        future = tq.submit(lambda: ib.positions(), target="ib")
        positions = future.result(timeout=10)
    """

    def __init__(self, executors: Dict[str, AsyncExecutor]):
        self._executors = executors
        self._queue: queue.Queue[Task | None] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        for executor in self._executors.values():
            executor.start()
        self._running = True
        self._worker = threading.Thread(
            target=self._poll, daemon=True, name="tq-worker",
        )
        self._worker.start()

    def submit(self, fn: Callable, target: str = IB) -> Future:
        """Submit a callable and return a Future for its result."""
        if not self._running:
            raise RuntimeError("TaskQueue is not running")
        task = Task(fn=fn, target=target)
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
            executor = self._executors.get(task.target)
            if executor is None:
                task.future.set_exception(
                    ValueError(f"Unknown target: {task.target!r}"),
                )
                continue
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
        for executor in self._executors.values():
            executor.shutdown()
