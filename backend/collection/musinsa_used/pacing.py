from __future__ import annotations

import time
from contextlib import contextmanager
from threading import BoundedSemaphore, Lock
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


class AdaptiveBackoffPolicy:
    """Bounded backoff used only after a retryable live-request failure."""

    def __init__(
        self,
        *,
        max_retries: int,
        initial_delay_sec: float,
        multiplier: float,
        max_delay_sec: float,
        sleep_fn=time.sleep,
        now_fn=lambda: datetime.now(timezone.utc),
    ):
        self.max_retries = max(0, int(max_retries))
        self.initial_delay_sec = max(0.0, float(initial_delay_sec))
        self.multiplier = max(1.0, float(multiplier))
        self.max_delay_sec = max(0.0, float(max_delay_sec))
        self._sleep = sleep_fn
        self._now = now_fn

    def delay_for_retry(self, retry_number: int, response=None) -> float:
        """Return Retry-After when supplied, otherwise capped exponential delay."""
        retry_after = self._retry_after(response)
        if retry_after is not None:
            return retry_after
        exponent = max(0, int(retry_number) - 1)
        return min(
            self.max_delay_sec,
            self.initial_delay_sec * (self.multiplier ** exponent),
        )

    def sleep_before_retry(self, retry_number: int, response=None) -> float:
        delay = self.delay_for_retry(retry_number, response)
        if delay > 0:
            self._sleep(delay)
        return delay

    def _retry_after(self, response) -> float | None:
        headers = getattr(response, "headers", None)
        value = headers.get("Retry-After") if headers is not None else None
        if value is None:
            return None
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            pass
        try:
            retry_at = parsedate_to_datetime(str(value))
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, (retry_at - self._now()).total_seconds())
        except (TypeError, ValueError, IndexError, OverflowError):
            return None


class InFlightRequestLimiter:
    """Bound concurrent MUSINSA USED HTTP requests across product workers."""

    def __init__(self, max_inflight_requests: int):
        self.max_inflight_requests = max(1, int(max_inflight_requests))
        self._semaphore = BoundedSemaphore(self.max_inflight_requests)

    @contextmanager
    def slot(self):
        self._semaphore.acquire()
        try:
            yield
        finally:
            self._semaphore.release()


class TargetCooldownCoordinator:
    """Serialize MUSINSA USED Targets and wait before the next one starts."""

    def __init__(
        self,
        *,
        cooldown_seconds: float,
        sleep_fn=time.sleep,
        monotonic_fn=time.monotonic,
    ):
        self.cooldown_seconds = float(cooldown_seconds)
        if not 60.0 <= self.cooldown_seconds <= 180.0:
            raise ValueError("Target cooldown must be between 60 and 180 seconds.")
        self._sleep = sleep_fn
        self._monotonic = monotonic_fn
        self._execution_lock = Lock()
        self._next_target_at = 0.0

    @contextmanager
    def execution(self):
        with self._execution_lock:
            remaining = self._next_target_at - self._monotonic()
            if remaining > 0:
                self._sleep(remaining)
            try:
                yield
            finally:
                self._next_target_at = self._monotonic() + self.cooldown_seconds


class HostBackoffCoordinator:
    """Thread-safe cooldown shared by MUSINSA USED live request clients."""

    def __init__(self, *, sleep_fn=time.sleep, monotonic_fn=time.monotonic):
        self._sleep = sleep_fn
        self._monotonic = monotonic_fn
        self._lock = Lock()
        self._next_allowed_at = 0.0
        self.cooldown_imposed_count = 0

    def wait_if_needed(self) -> float:
        """Wait for the latest shared cooldown, if another worker set one."""
        total_wait = 0.0
        while True:
            with self._lock:
                remaining = self._next_allowed_at - self._monotonic()
            if remaining <= 0:
                return total_wait
            self._sleep(remaining)
            total_wait += remaining

    def impose_cooldown(self, seconds: float) -> bool:
        """Keep the later cooldown when multiple workers report throttling."""
        candidate = self._monotonic() + max(0.0, float(seconds))
        with self._lock:
            if candidate <= self._next_allowed_at:
                return False
            self._next_allowed_at = candidate
            self.cooldown_imposed_count += 1
            return True

    @property
    def next_allowed_at(self) -> float:
        with self._lock:
            return self._next_allowed_at
