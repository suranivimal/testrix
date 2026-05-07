import json
import re
import logging

logger = logging.getLogger(__name__)


def _strip_markdown(content: str) -> str:
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if match:
        return match.group(1)
    return content


def extract_json_object(content: str) -> dict | None:
    try:
        content = _strip_markdown(content)
        start = content.find("{")
        end = content.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        return json.loads(content[start:end])
    except Exception as e:
        logger.warning(f"JSON object extraction failed: {e}")
        return None


def extract_json_array(content: str) -> list | None:
    try:
        content = _strip_markdown(content)
        start = content.find("[")
        end = content.rfind("]") + 1
        if start == -1 or end == 0:
            return None
        return json.loads(content[start:end])
    except Exception as e:
        logger.warning(f"JSON array extraction failed: {e}")
        return None