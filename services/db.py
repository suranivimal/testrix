import os
import logging
from datetime import datetime, timezone

from pymongo import MongoClient, DESCENDING
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_client = MongoClient(os.environ.get("MONGODB_URI", "mongodb://localhost:27017"))
_db = _client["testrix"]
_history = _db["history"]
_vqa_jobs = _db["visual_qa_jobs"]


def save_history(input_text: str, bug_analysis: dict, test_cases: list) -> str:
    doc = {
        "input_text": input_text,
        "bug_analysis": bug_analysis,
        "test_cases": test_cases,
        "timestamp": datetime.now(timezone.utc),
    }
    result = _history.insert_one(doc)
    logger.info(f"History saved — id={result.inserted_id}")
    return str(result.inserted_id)


def _serialize(doc: dict) -> dict:
    doc["_id"] = str(doc["_id"])
    if isinstance(doc.get("timestamp"), datetime):
        doc["timestamp"] = doc["timestamp"].isoformat()
    return doc


def get_history(limit: int = 10) -> list[dict]:
    projection = {
        "input_text": 1,
        "timestamp": 1,
        "bug_analysis.bug": 1,
    }
    cursor = _history.find({}, projection).sort("timestamp", DESCENDING).limit(limit)
    return [_serialize(doc) for doc in cursor]


def get_history_item(history_id: str) -> dict | None:
    try:
        oid = ObjectId(history_id)
    except Exception:
        return None
    doc = _history.find_one({"_id": oid})
    return _serialize(doc) if doc else None


def delete_history_item(history_id: str) -> bool:
    try:
        oid = ObjectId(history_id)
    except Exception:
        return False
    result = _history.delete_one({"_id": oid})
    return result.deleted_count == 1


# ---------- Visual QA jobs ----------

def create_vqa_job(shopify_url: str, figma_url: str, pages: list[str]) -> str:
    doc = {
        "shopify_url": shopify_url,
        "figma_file_key": _extract_figma_key(figma_url),
        "figma_url": figma_url,
        "pages": pages,
        "status": "pending",
        "progress": "",
        "result": None,
        "error": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    result = _vqa_jobs.insert_one(doc)
    logger.info(f"VQA job created — id={result.inserted_id}")
    return str(result.inserted_id)


def update_vqa_job(job_id: str, **fields) -> None:
    try:
        oid = ObjectId(job_id)
    except Exception:
        return
    fields["updated_at"] = datetime.now(timezone.utc)
    _vqa_jobs.update_one({"_id": oid}, {"$set": fields})


def get_vqa_job(job_id: str) -> dict | None:
    try:
        oid = ObjectId(job_id)
    except Exception:
        return None
    doc = _vqa_jobs.find_one({"_id": oid})
    return _serialize_vqa(doc) if doc else None


def _serialize_vqa(doc: dict) -> dict:
    doc["_id"] = str(doc["_id"])
    for key in ("created_at", "updated_at"):
        if isinstance(doc.get(key), datetime):
            doc[key] = doc[key].isoformat()
    return doc


def _extract_figma_key(figma_url: str) -> str:
    parts = figma_url.split("/")
    for i, part in enumerate(parts):
        if part in ("design", "file", "board", "slides", "make") and i + 1 < len(parts):
            return parts[i + 1]
    return ""