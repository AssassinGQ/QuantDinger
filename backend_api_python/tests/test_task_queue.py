"""Tests for TaskQueue + IBExecutor + IOExecutor architecture."""

import asyncio
import concurrent.futures
import threading
import time

import pytest

from app.services.live_trading.async_executor import IBExecutor, IOExecutor
from app.services.live_trading.task_queue import IB, IO, TaskQueue


# ── fixtures ──────────────────────────────────────────────────────────

@pytest.fixture()
def tq():
    ib_exec = IBExecutor(name="test-ib")
    io_exec = IOExecutor(max_workers=2, name="test-io")
    q = TaskQueue(executors={IB: ib_exec, IO: io_exec})
    q.start()
    yield q
    q.shutdown()


@pytest.fixture()
def ib_executor():
    e = IBExecutor(name="test-ib-only")
    e.start()
    yield e
    e.shutdown()


@pytest.fixture()
def io_executor():
    e = IOExecutor(max_workers=2, name="test-io-only")
    yield e
    e.shutdown()


# ── IBExecutor unit tests ──────────────────────────────────────────────

class TestIBExecutor:
    def test_sync_callable_runs_on_loop_thread(self, ib_executor):
        f = concurrent.futures.Future()
        ib_executor.execute(lambda: threading.current_thread().name, f)
        assert f.result(timeout=5) == "test-ib-only"

    def test_coroutine_runs_on_loop_thread(self, ib_executor):
        async def get_name():
            return threading.current_thread().name

        f = concurrent.futures.Future()
        ib_executor.execute(get_name(), f)
        assert f.result(timeout=5) == "test-ib-only"

    def test_exception_propagation(self, ib_executor):
        def boom():
            raise ValueError("ib-boom")

        f = concurrent.futures.Future()
        ib_executor.execute(boom, f)
        with pytest.raises(ValueError, match="ib-boom"):
            f.result(timeout=5)

    def test_coroutine_exception(self, ib_executor):
        async def boom():
            raise RuntimeError("coro-boom")

        f = concurrent.futures.Future()
        ib_executor.execute(boom(), f)
        with pytest.raises(RuntimeError, match="coro-boom"):
            f.result(timeout=5)

    def test_not_running_sets_exception(self):
        e = IBExecutor(name="dead")
        f = concurrent.futures.Future()
        e.execute(lambda: 1, f)
        with pytest.raises(RuntimeError, match="not running"):
            f.result(timeout=1)

    def test_double_start_is_safe(self, ib_executor):
        ib_executor.start()
        f = concurrent.futures.Future()
        ib_executor.execute(lambda: 42, f)
        assert f.result(timeout=5) == 42

    def test_loop_property(self, ib_executor):
        assert ib_executor.loop is not None
        assert ib_executor.loop.is_running()

    def test_shutdown(self):
        e = IBExecutor(name="shut")
        e.start()
        e.shutdown()
        assert e.loop is None


# ── IOExecutor unit tests ──────────────────────────────────────────────

class TestIOExecutor:
    def test_sync_callable(self, io_executor):
        f = concurrent.futures.Future()
        io_executor.execute(lambda: 99, f)
        assert f.result(timeout=5) == 99

    def test_runs_in_pool_thread(self, io_executor):
        f = concurrent.futures.Future()
        io_executor.execute(lambda: threading.current_thread().name, f)
        name = f.result(timeout=5)
        assert "test-io" in name

    def test_exception_propagation(self, io_executor):
        def boom():
            raise ValueError("io-boom")

        f = concurrent.futures.Future()
        io_executor.execute(boom, f)
        with pytest.raises(ValueError, match="io-boom"):
            f.result(timeout=5)


# ── TaskQueue / Worker 集成测试 ──────────────────────────────────────

class TestTaskQueueIBTarget:
    def test_submit_ib_task(self, tq):
        future = tq.submit(lambda: 42, target=IB)
        assert future.result(timeout=5) == 42

    def test_ib_task_runs_on_loop_thread(self, tq):
        future = tq.submit(lambda: threading.current_thread().name, target=IB)
        assert future.result(timeout=5) == "test-ib"

    def test_submit_ib_coroutine(self, tq):
        async def add(a, b):
            return a + b

        future = tq.submit(add(3, 4), target=IB)
        assert future.result(timeout=5) == 7


class TestTaskQueueIOTarget:
    def test_submit_io_task(self, tq):
        future = tq.submit(lambda: "hello", target=IO)
        assert future.result(timeout=5) == "hello"

    def test_io_task_runs_in_pool(self, tq):
        future = tq.submit(lambda: threading.current_thread().name, target=IO)
        name = future.result(timeout=5)
        assert "test-io" in name

    def test_io_exception(self, tq):
        def boom():
            raise RuntimeError("db-error")

        future = tq.submit(boom, target=IO)
        with pytest.raises(RuntimeError, match="db-error"):
            future.result(timeout=5)


class TestTaskQueueMixed:
    def test_ib_and_io_concurrent(self, tq):
        f_ib = tq.submit(lambda: "ib-ok", target=IB)
        f_io = tq.submit(lambda: "io-ok", target=IO)
        assert f_ib.result(timeout=5) == "ib-ok"
        assert f_io.result(timeout=5) == "io-ok"

    def test_concurrent_submits_from_multiple_threads(self, tq):
        results = []
        barrier = threading.Barrier(4)

        def submitter(value):
            barrier.wait(timeout=5)
            future = tq.submit(lambda v=value: v * 2, target=IB)
            results.append(future.result(timeout=5))

        threads = [threading.Thread(target=submitter, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert sorted(results) == [0, 2, 4, 6]


class TestTaskQueueFireAndForget:
    def test_fire_and_forget_ib(self, tq):
        container = []
        tq.submit(lambda: container.append("done"), target=IB)
        time.sleep(0.5)
        assert container == ["done"]

    def test_fire_and_forget_io(self, tq):
        container = []
        tq.submit(lambda: container.append("io-done"), target=IO)
        time.sleep(0.5)
        assert container == ["io-done"]


class TestTaskQueueLifecycle:
    def test_submit_when_stopped_raises(self):
        q = TaskQueue(executors={IB: IBExecutor(), IO: IOExecutor()})
        with pytest.raises(RuntimeError, match="not running"):
            q.submit(lambda: 1)

    def test_double_start(self, tq):
        tq.start()
        future = tq.submit(lambda: 1, target=IB)
        assert future.result(timeout=5) == 1

    def test_unknown_target_raises(self, tq):
        future = tq.submit(lambda: 1, target="unknown")
        with pytest.raises(ValueError, match="Unknown target"):
            future.result(timeout=5)

    def test_shutdown_and_restart(self):
        ib = IBExecutor(name="re")
        io = IOExecutor(name="re-io")
        q = TaskQueue(executors={IB: ib, IO: io})
        q.start()
        assert q.submit(lambda: 1, target=IB).result(timeout=5) == 1
        q.shutdown()


class TestTaskQueueTimeout:
    def test_ib_timeout(self, tq):
        async def slow():
            await asyncio.sleep(10)
            return "never"

        future = tq.submit(slow(), target=IB)
        with pytest.raises(concurrent.futures.TimeoutError):
            future.result(timeout=0.1)

    def test_io_timeout(self, tq):
        def slow():
            time.sleep(10)
            return "never"

        future = tq.submit(slow, target=IO)
        with pytest.raises(concurrent.futures.TimeoutError):
            future.result(timeout=0.1)
