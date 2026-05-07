import asyncio
import logging

from fastapi.concurrency import run_in_threadpool

from agents.bug_agent import analyze_bug
from services.test_case_service import generate_test_cases
from db import save_history

logger = logging.getLogger(__name__)


async def run_qa_ai(feature_or_bug: str) -> dict:
    bug_result, test_result = await asyncio.gather(
        analyze_bug(feature_or_bug),
        generate_test_cases(feature_or_bug),
    )

    history_id = None
    try:
        history_id = await run_in_threadpool(
            save_history,
            feature_or_bug,
            bug_result if isinstance(bug_result, dict) else {},
            test_result if isinstance(test_result, list) else [],
        )
    except Exception as e:
        logger.warning(f"History save failed (non-fatal): {e}")

    return {
        "input": feature_or_bug,
        "bug_analysis": bug_result,
        "test_cases": test_result,
        "history_id": history_id,
    }