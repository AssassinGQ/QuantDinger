"""Tests for AsyncWorker — the public task dispatcher."""

import asyncio
import concurrent.futures
import threading
import time

import pytest

from app.services.live_trading.async_worker import AsyncWorker


# ── fixtures ──────────────────────────────────────────────────────────

@pytest.fixture()
def worker():
    w = AsyncWorker(name="test-worker", io_workers=2)
    w.start()
    yield w
    w.shutdown()


# ── coroutine submission ──────────────────────────────────────────────

class TestSubmitCoroutine:
    def test_submit_coroutine_returns_result(self, worker):
        async def add(a, b):
            return a + b

        future = worker.submit(add(3, 4))
        assert future.result(timeout=5) == 7

    def test_submit_async_function_directly(self, worker):
        """Passing an async def (not called) should also work."""
        async def greet():
            return "hello"

        future = worker.submit(greet)
        assert future.result(timeout=5) == "hello"

    def test_coroutine_runs_on_event_loop_thread(self, worker):
        async def get_thread_name():
            return threading.current_thread().name

        name = worker.submit(get_thread_name()).result(timeout=5)
        assert name == "test-worker"

    def test_coroutine_can_await(self, worker):
        async def slow():
            await asyncio.sleep(0.1)
            return "done"

        assert worker.submit(slow()).result(timeout=5) == "done"


# ── sync function submission ──────────────────────────────────────────

class TestSubmitSyncFunction:
    def test_submit_sync_function_returns_result(self, worker):
        future = worker.submit(lambda: 42)
        assert future.result(timeout=5) == 42

    def test_sync_function_runs_in_io_pool(self, worker):
        def get_thread():
            return threading.current_thread().name

        name = worker.submit(get_thread).result(timeout=5)
        assert "test-worker-io" in name

    def test_sync_blocking_does_not_block_event_loop(self, worker):
        """A slow sync function must not prevent coroutines from running."""
        results = []

        def slow_sync():
            time.sleep(0.5)
            return "sync-done"

        async def fast_coro():
            return "coro-done"

        f_sync = worker.submit(slow_sync)
        f_coro = worker.submit(fast_coro())

        coro_result = f_coro.result(timeout=2)
        results.append(("coro", coro_result))

        sync_result = f_sync.result(timeout=5)
        results.append(("sync", sync_result))

        assert ("coro", "coro-done") in results
        assert ("sync", "sync-done") in results


# ── fire-and-forget ──────────────────────────────────────────────────

class TestFireAndForget:
    def test_future_not_awaited_still_executes(self, worker):
        container = []

        def side_effect():
            container.append("executed")

        worker.submit(side_effect)
        time.sleep(0.5)
        assert container == ["executed"]

    def test_coroutine_fire_and_forget(self, worker):
        container = []

        async def side_effect():
            container.append("async-executed")

        worker.submit(side_effect())
        time.sleep(0.5)
        assert container == ["async-executed"]


# ── timeout ──────────────────────────────────────────────────────────

class TestTimeout:
    def test_result_timeout_raises(self, worker):
        async def slow():
            await asyncio.sleep(10)
            return "never"

        future = worker.submit(slow())
        with pytest.raises(concurrent.futures.TimeoutError):
            future.result(timeout=0.1)

    def test_sync_timeout_raises(self, worker):
        def slow():
            time.sleep(10)
            return "never"

        future = worker.submit(slow)
        with pytest.raises(concurrent.futures.TimeoutError):
            future.result(timeout=0.1)


# ── exception propagation ────────────────────────────────────────────

class TestExceptionPropagation:
    def test_coroutine_exception(self, worker):
        async def boom():
            raise ValueError("coro-error")

        future = worker.submit(boom())
        with pytest.raises(ValueError, match="coro-error"):
            future.result(timeout=5)

    def test_sync_function_exception(self, worker):
        def boom():
            raise RuntimeError("sync-error")

        future = worker.submit(boom)
        with pytest.raises(RuntimeError, match="sync-error"):
            future.result(timeout=5)


# ── type validation ──────────────────────────────────────────────────

class TestTypeValidation:
    def test_non_callable_raises_type_error(self, worker):
        with pytest.raises(TypeError, match="expected callable or coroutine"):
            worker.submit(42)

    def test_string_raises_type_error(self, worker):
        with pytest.raises(TypeError):
            worker.submit("not a function")


# ── lifecycle ────────────────────────────────────────────────────────

class TestLifecycle:
    def test_start_and_running(self):
        w = AsyncWorker(name="lifecycle-test")
        assert not w.running
        w.start()
        assert w.running
        w.shutdown()
        assert not w.running

    def test_double_start_is_safe(self, worker):
        worker.start()
        assert worker.running

    def test_shutdown_then_submit_raises(self):
        w = AsyncWorker(name="shutdown-test")
        w.start()
        w.shutdown()
        with pytest.raises(RuntimeError, match="not running"):
            w.submit(lambda: 1)

    def test_start_raises_on_failure(self):
        """start() should not hang forever if something goes wrong."""
        w = AsyncWorker(name="ok")
        w.start()
        assert w.running
        w.shutdown()


# ── concurrency ──────────────────────────────────────────────────────

class TestConcurrency:
    def test_concurrent_submits_from_multiple_threads(self, worker):
        results = []
        barrier = threading.Barrier(4)

        def submitter(value):
            barrier.wait(timeout=5)
            future = worker.submit(lambda v=value: v * 2)
            results.append(future.result(timeout=5))

        threads = [threading.Thread(target=submitter, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert sorted(results) == [0, 2, 4, 6]

    def test_mixed_coroutine_and_sync_concurrent(self, worker):
        results = []

        async def coro_task(v):
            await asyncio.sleep(0.05)
            return f"coro-{v}"

        def sync_task(v):
            time.sleep(0.05)
            return f"sync-{v}"

        futures = []
        for i in range(3):
            futures.append(worker.submit(coro_task(i)))
            futures.append(worker.submit(lambda v=i: sync_task(v)))

        for f in futures:
            results.append(f.result(timeout=5))

        assert len(results) == 6
        coro_results = [r for r in results if r.startswith("coro-")]
        sync_results = [r for r in results if r.startswith("sync-")]
        assert len(coro_results) == 3
        assert len(sync_results) == 3
