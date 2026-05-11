import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def with_retry(
    func: Callable[[], Awaitable[T]],
    retries: int = 3,
    base_delay: float = 1.0,
) -> T:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return await func()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt == retries - 1:
                break
            await asyncio.sleep(base_delay * (2**attempt))
    assert last_error is not None
    raise last_error
