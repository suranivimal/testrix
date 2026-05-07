import asyncio
import time
import logging
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

_MAX_CONCURRENT = 3  # run up to 3 tests in parallel to avoid overwhelming the target


def _parse_api(api_str: str) -> tuple[str, str]:
    """'POST /api/login' → ('POST', '/api/login')"""
    parts = (api_str or "GET /").strip().split(" ", 1)
    return (parts[0].upper(), parts[1]) if len(parts) == 2 else ("GET", "/")


def _get_payload(tc: dict) -> dict | None:
    p = tc.get("payload")
    return p if isinstance(p, dict) and p else None


def _get_expected_status(tc: dict) -> int | None:
    # test_case_prompt format
    if isinstance(tc.get("expected"), dict):
        v = tc["expected"].get("status")
        return int(v) if v is not None else None
    # bug_analysis_prompt format
    if isinstance(tc.get("expectedResponse"), dict):
        v = tc["expectedResponse"].get("statusCode")
        return int(v) if v is not None else None
    return None


async def _run_one(ctx, tc: dict, timeout_ms: int) -> dict:
    method, path = _parse_api(tc.get("api", "GET /"))
    expected = _get_expected_status(tc)
    payload  = _get_payload(tc)

    start        = time.monotonic()
    actual_status = None
    error        = None

    try:
        kwargs: dict = {"timeout": timeout_ms}
        if method in ("POST", "PUT", "PATCH"):
            kwargs["data"] = payload or {}

        resp = await ctx.fetch(path, method=method, **kwargs)
        actual_status = resp.status

    except Exception as e:
        error = str(e)

    elapsed = int((time.monotonic() - start) * 1000)
    passed  = (actual_status == expected) if (actual_status is not None and expected is not None) else False

    return {
        "id":              tc.get("id", ""),
        "title":           tc.get("title") or tc.get("description") or "Unnamed",
        "api":             tc.get("api", ""),
        "expected_status": expected,
        "actual_status":   actual_status,
        "passed":          passed,
        "error":           error,
        "response_time_ms": elapsed,
    }


async def run_tests(
    base_url: str,
    test_cases: list[dict],
    timeout_ms: int = 5000,
    auth_token: str | None = None,
) -> dict:
    sem = asyncio.Semaphore(_MAX_CONCURRENT)

    async with async_playwright() as p:
        extra_headers: dict = {}
        if auth_token:
            extra_headers["Authorization"] = f"Bearer {auth_token}"

        ctx = await p.request.new_context(
            base_url=base_url,
            extra_http_headers=extra_headers,
        )

        async def run_with_sem(tc: dict) -> dict:
            async with sem:
                return await _run_one(ctx, tc, timeout_ms)

        results = list(await asyncio.gather(*[run_with_sem(tc) for tc in test_cases]))
        await ctx.dispose()

    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed

    logger.info(f"Test run complete — total={len(results)}, passed={passed}, failed={failed}")

    return {
        "summary": {
            "total":  len(results),
            "passed": passed,
            "failed": failed,
        },
        "results": results,
    }