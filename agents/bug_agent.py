import logging
from ai_engine.llm import ask_ai
from ai_engine.prompts import bug_analysis_prompt
from ai_engine.utils import extract_json_object

logger = logging.getLogger(__name__)


async def analyze_bug(bug: str) -> dict:
    prompt = bug_analysis_prompt(bug)
    raw = await ask_ai(prompt)

    parsed = extract_json_object(raw)
    if parsed:
        return parsed

    logger.warning("Bug agent could not parse JSON — returning raw response")
    return {"error": "Invalid JSON from AI", "raw": raw}