"""Tests for TaskQueue + LoopExecutor + ThreadsPoolExecutor architecture."""

import asyncio
import concurrent.futures
import threading
import time

import pytest

from app.services.live_trading.async_executor import LoopExecutor, ThreadsPoolExecutor
from app.services.live_trading.task_queue import TaskQueue


# ── fixtures ──────────────────────────────────────────────────────────

@pytest.fixture()
def tq():
    loop_exec = LoopExecutor(name="test-loop")
    pool_exec = ThreadsPoolExecutor(max_workers=2, name="test-pool")
    q = TaskQueue(loop_executor_name="test-loop", pool_executor_name="test-pool", pool_workers=2)
    q.start()
    yield q
    q.shutdown()


@pytest.fixture()
def loop_executor():
    e = LoopExecutor(name="test-loop-only")
    e.start()
    yield e
    e.shutdown()


@pytest.fixture()
def pool_executor():
    e = ThreadsPoolExecutor(max_workers=2, name="test-pool-only")
    e.start()
    yield e
    e.shutdown()


# ── LoopExecutor unit tests ──────────────────────────────────────────────

class TestLoopExecutor:
    def test_sync_callable_runs_on_loop_thread(self, loop_executor):
        f = concurrent.futures.Future()
        loop_executor.execute(lambda: threading.current_thread().name, f)
        assert f.result(timeout=5) == "test-loop-only"

    def test_coroutine_runs_on_loop_thread(self, loop_executor):
        async def get_name():
            return threading.current_thread().name

        f = concurrent.futures.Future()
        loop_executor.execute(get_name(), f)
        assert f.result(timeout=5) == "test-loop-only"

    def test_exception_propagation(self, loop_executor):
        def boom():
            raise ValueError("loop-boom")

        f = concurrent.futures.Future()
        loop_executor.execute(boom, f)
        with pytest.raises(ValueError, match="loop-boom"):
            f.result(timeout=5)

    def test_coroutine_exception(self, loop_executor):
        async def boom():
            raise RuntimeError("coro-boom")

        f = concurrent.futures.Future()
        loop_executor.execute(boom(), f)
        with pytest.raises(RuntimeError, match="coro-boom"):
            f.result(timeout=5)

    def test_not_running_sets_exception(self):
        e = LoopExecutor(name="dead")
        f = concurrent.futures.Future()
        e.execute(lambda: 1, f)
        with pytest.raises(RuntimeError, match="not running"):
            f.result(timeout=1)

    def test_double_start_is_safe(self, loop_executor):
        loop_executor.start()
        f = concurrent.futures.Future()
        loop_executor.execute(lambda: 42, f)
        assert f.result(timeout=5) == 42

    def test_loop_property(self, loop_executor):
        assert loop_executor.loop is not None
        assert loop_executor.loop.is_running()

    def test_shutdown(self):
        e = LoopExecutor(name="shut")
        e.start()
        e.shutdown()
        assert e.loop is None


# ── ThreadsPoolExecutor unit tests ──────────────────────────────────────────────

class TestThreadsPoolExecutor:
    def test_sync_callable(self, pool_executor):
        f = concurrent.futures.Future()
        pool_executor.execute(lambda: 99, f)
        assert f.result(timeout=5) == 99

    def test_runs_in_pool_thread(self, pool_executor):
        f = concurrent.futures.Future()
        pool_executor.execute(lambda: threading.current_thread().name, f)
        name = f.result(timeout=5)
        assert "test-pool" in name

    def test_exception_propagation(self, pool_executor):
        def boom():
            raise ValueError("pool-boom")

        f = concurrent.futures.Future()
        pool_executor.execute(boom, f)
        with pytest.raises(ValueError, match="pool-boom"):
            f.result(timeout=5)


# ── TaskQueue / Worker integration tests ──────────────────────────────────────

class TestTaskQueueNonBlocking:
    def test_submit_non_blocking_task(self, tq):
        future = tq.submit(lambda: 42, is_blocking=False)
        assert future.result(timeout=5) == 42

    def test_non_blocking_task_runs_on_loop_thread(self, tq):
        future = tq.submit(lambda: threading.current_thread().name, is_blocking=False)
        assert future.result(timeout=5) == "test-loop"

    def test_submit_non_blocking_coroutine(self, tq):
        async def add(a, b):
            return a + b

        future = tq.submit(add(3, 4), is_blocking=False)
        assert future.result(timeout=5) == 7


class TestTaskQueueBlocking:
    def test_submit_blocking_task(self, tq):
        future = tq.submit(lambda: "hello", is_blocking=True)
        assert future.result(timeout=5) == "hello"

    def test_blocking_task_runs_in_pool(self, tq):
        future = tq.submit(lambda: threading.current_thread().name, is_blocking=True)
        name = future.result(timeout=5)
        assert "test-pool" in name

    def test_blocking_exception(self, tq):
        def boom():
            raise RuntimeError("db-error")

        future = tq.submit(boom, is_blocking=True)
        with pytest.raises(RuntimeError, match="db-error"):
            future.result(timeout=5)


class TestTaskQueueMixed:
    def test_blocking_and_non_blocking_concurrent(self, tq):
        f_non_blocking = tq.submit(lambda: "loop-ok", is_blocking=False)
        f_blocking = tq.submit(lambda: "pool-ok", is_blocking=True)
        assert f_non_blocking.result(timeout=5) == "loop-ok"
        assert f_blocking.result(timeout=5) == "pool-ok"

    def test_concurrent_submits_from_multiple_threads(self, tq):
        results = []
        barrier = threading.Barrier(4)

        def submitter(value):
            barrier.wait(timeout=5)
            future = tq.submit(lambda v=value: v * 2, is_blocking=False)
            results.append(future.result(timeout=5))

        threads = [threading.Thread(target=submitter, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert sorted(results) == [0, 2, 4, 6]


class TestTaskQueueFireAndForget:
    def test_fire_and_forget_non_blocking(self, tq):
        container = []
        tq.submit(lambda: container.append("done"), is_blocking=False)
        time.sleep(0.5)
        assert container == ["done"]

    def test_fire_and_forget_blocking(self, tq):
        container = []
        tq.submit(lambda: container.append("pool-done"), is_blocking=True)
        time.sleep(0.5)
        assert container == ["pool-done"]


class TestTaskQueueLifecycle:
    def test_submit_when_stopped_raises(self):
        q = TaskQueue(loop_executor_name="test-loop", pool_executor_name="test-pool", pool_workers=2)
        with pytest.raises(RuntimeError, match="not running"):
            q.submit(lambda: 1)

    def test_double_start(self, tq):
        tq.start()
        future = tq.submit(lambda: 1, is_blocking=False)
        assert future.result(timeout=5) == 1

    def test_shutdown_and_restart(self):
        q = TaskQueue(loop_executor_name="re-loop", pool_executor_name="re-pool", pool_workers=2)
        q.start()
        assert q.submit(lambda: 1, is_blocking=False).result(timeout=5) == 1
        q.shutdown()


class TestTaskQueueTimeout:
    def test_non_blocking_timeout(self, tq):
        async def slow():
            await asyncio.sleep(10)
            return "never"

        future = tq.submit(slow(), is_blocking=False)
        with pytest.raises(concurrent.futures.TimeoutError):
            future.result(timeout=0.1)

    def test_blocking_timeout(self, tq):
        def slow():
            time.sleep(10)
            return "never"

        future = tq.submit(slow, is_blocking=True)
        with pytest.raises(concurrent.futures.TimeoutError):
            future.result(timeout=0.1)
