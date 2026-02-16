"""Tests fuer Resilience (Circuit Breaker + Retry)."""

import time

import pytest

from assistant.resilience import CircuitBreaker, CircuitState, retry_async


class TestCircuitBreaker:

    def test_initial_state_closed(self):
        cb = CircuitBreaker(name="test")
        assert cb.state == CircuitState.CLOSED
        assert cb.is_available is True

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.is_available is False

    def test_stays_closed_below_threshold(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        assert cb.is_available is True

    def test_success_resets_count(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_after_recovery(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.is_available is True

    def test_closes_after_success_in_half_open(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_reset(self):
        cb = CircuitBreaker(name="test", failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED


class TestRetryAsync:

    @pytest.mark.asyncio
    async def test_succeeds_first_try(self):
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await retry_async(func, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure(self):
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("fail")
            return "ok"

        result = await retry_async(func, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        async def func():
            raise ConnectionError("always fails")

        with pytest.raises(ConnectionError):
            await retry_async(func, max_retries=2, base_delay=0.01)

    @pytest.mark.asyncio
    async def test_respects_exception_filter(self):
        async def func():
            raise ValueError("wrong type")

        with pytest.raises(ValueError):
            await retry_async(
                func, max_retries=3, base_delay=0.01,
                exceptions=(ConnectionError,),
            )

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks(self):
        cb = CircuitBreaker(name="test", failure_threshold=1)
        cb.record_failure()  # Opens circuit

        async def func():
            return "ok"

        with pytest.raises(ConnectionError, match="Circuit Breaker"):
            await retry_async(func, circuit_breaker=cb)

    @pytest.mark.asyncio
    async def test_circuit_breaker_records_success(self):
        cb = CircuitBreaker(name="test")

        async def func():
            return "ok"

        await retry_async(func, circuit_breaker=cb)
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_breaker_records_failure(self):
        cb = CircuitBreaker(name="test", failure_threshold=5)

        async def func():
            raise ConnectionError("fail")

        with pytest.raises(ConnectionError):
            await retry_async(func, max_retries=2, base_delay=0.01, circuit_breaker=cb)
        assert cb._failure_count >= 1
