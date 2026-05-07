import os
import json
import logging
import asyncio

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from dotenv import load_dotenv

from services.test_case_service import generate_test_cases
from services.bug_analysis_service import analyze_bug as basic_bug_analysis
from agents.bug_agent import analyze_bug as agent_analyze_bug
from agents.agent_manager import run_qa_ai
from services.test_runner import run_tests
from agents.visual_qa_agent import run_visual_qa
from services.db import get_history, get_history_item, delete_history_item, create_vqa_job, get_vqa_job

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Fail fast on missing required env vars — surface the problem at startup, not mid-request
_REQUIRED_ENV = ["GROQ_API_KEY"]
_OPTIONAL_ENV = {"FIGMA_API_TOKEN": "/visual-qa"}
for _var in _REQUIRED_ENV:
    if not os.environ.get(_var):
        raise RuntimeError(f"Missing required environment variable: {_var}. Check your .env file.")

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Testrix", version="2.0.0", description="AI-powered QA automation")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/ui", StaticFiles(directory="ui"), name="ui")


# ---------- Request models ----------

class FeatureRequest(BaseModel):
    feature: str = Field(..., min_length=3, max_length=2000)


class BugRequest(BaseModel):
    bug: str = Field(..., min_length=3, max_length=2000)


class QARequest(BaseModel):
    input_text: str = Field(..., min_length=5, max_length=2000)


class RunTestsRequest(BaseModel):
    base_url: str = Field(..., min_length=1, max_length=500)
    test_cases: list[dict] = Field(...)
    timeout_ms: int = Field(default=5000, ge=1000, le=30000)
    auth_token: str | None = None


class VisualQARequest(BaseModel):
    shopify_url: str = Field(..., min_length=8, max_length=500, description="Live Shopify store URL (https only)")
    figma_url: str = Field(..., min_length=8, max_length=500, description="Figma file or frame URL")
    pages: list[str] = Field(
        default=["home", "product", "collection", "cart"],
        description="Pages to test: home, product, collection, cart",
    )
    shopify_password: str | None = Field(default=None, description="Password for password-protected stores")
    diff_threshold: float = Field(default=0.05, ge=0.0, le=1.0, description="Pixel diff sensitivity (0–1)")


# ---------- Health ----------

@app.get("/")
async def home():
    return {"message": "Testrix Running", "version": "2.0.0"}


# ---------- Legacy endpoints ----------

@app.post("/test-cases", deprecated=True, tags=["Legacy"])
@limiter.limit("20/minute")
async def test_cases(request: Request, body: FeatureRequest):
    try:
        result = await generate_test_cases(body.feature)
        return {"result": result}
    except Exception as e:
        logger.error(f"/test-cases error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/bug-analysis", deprecated=True, tags=["Legacy"])
@limiter.limit("20/minute")
async def bug_analysis(request: Request, body: BugRequest):
    try:
        result = await basic_bug_analysis(body.bug)
        return {"result": result}
    except Exception as e:
        logger.error(f"/bug-analysis error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/analyze-bug", deprecated=True, tags=["Legacy"])
@limiter.limit("20/minute")
async def analyze_bug_api(request: Request, body: BugRequest):
    try:
        result = await agent_analyze_bug(body.bug)
        return {"result": result}
    except Exception as e:
        logger.error(f"/analyze-bug error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ---------- Main QA endpoint ----------

@app.post("/qa-ai", tags=["QA"])
@limiter.limit("10/minute")
async def qa_ai_api(request: Request, body: QARequest):
    try:
        logger.info(f"QA request: {body.input_text[:100]!r}")
        result = await run_qa_ai(body.input_text)
        return {"result": result}
    except Exception as e:
        logger.error(f"/qa-ai error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/qa-ai/stream", tags=["QA"])
@limiter.limit("10/minute")
async def qa_ai_stream(request: Request, body: QARequest):
    """SSE endpoint — sends a progress event then the full result."""

    async def event_stream():
        try:
            yield f"data: {json.dumps({'status': 'analyzing', 'message': 'Running bug analysis and generating test cases in parallel…'})}\n\n"

            result = await run_qa_ai(body.input_text)

            payload = {"status": "complete", "result": result}
            yield f"data: {json.dumps(payload)}\n\n"

        except Exception as e:
            logger.error(f"/qa-ai/stream error: {e}")
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- Playwright test runner ----------

@app.post("/run-tests", tags=["QA"])
@limiter.limit("5/minute")
async def run_tests_api(request: Request, body: RunTestsRequest):
    if not body.test_cases:
        return JSONResponse(status_code=422, content={"error": "test_cases must not be empty"})
    try:
        logger.info(f"Running {len(body.test_cases)} tests against {body.base_url}")
        result = await run_tests(
            base_url=body.base_url,
            test_cases=body.test_cases,
            timeout_ms=body.timeout_ms,
            auth_token=body.auth_token,
        )
        return result
    except Exception as e:
        logger.error(f"/run-tests error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ---------- Visual QA ----------

@app.post("/visual-qa", tags=["Visual QA"], status_code=202)
@limiter.limit("2/minute")
async def visual_qa_start(request: Request, body: VisualQARequest, background_tasks: BackgroundTasks):
    """
    Start a visual QA job. Returns immediately with a job_id.
    Poll GET /visual-qa/{job_id} for status and results.
    """
    # Warn if optional keys are missing — don't block the request
    missing = [v for v in ("FIGMA_API_TOKEN",) if not os.environ.get(v)]
    if missing:
        logger.warning(f"/visual-qa called but missing env vars: {missing}")

    try:
        from services.shopify_scraper import validate_url
        validate_url(body.shopify_url)
    except ValueError as e:
        return JSONResponse(status_code=422, content={"error": str(e)})

    job_id = await run_in_threadpool(
        create_vqa_job, body.shopify_url, body.figma_url, body.pages
    )

    background_tasks.add_task(
        run_visual_qa,
        job_id=job_id,
        shopify_url=body.shopify_url,
        figma_url=body.figma_url,
        pages=body.pages,
        shopify_password=body.shopify_password,
        diff_threshold=body.diff_threshold,
    )

    logger.info(f"Visual QA job started — id={job_id}, pages={body.pages}")
    return {"job_id": job_id, "status": "pending", "message": "Job started. Poll /visual-qa/{job_id} for results."}


@app.get("/visual-qa/{job_id}", tags=["Visual QA"])
async def visual_qa_status(job_id: str):
    """Poll job status. status: pending | running | complete | failed."""
    job = await run_in_threadpool(get_vqa_job, job_id)
    if not job:
        return JSONResponse(status_code=404, content={"error": "Job not found"})
    return job


# ---------- History ----------

@app.get("/history", tags=["History"])
async def list_history(limit: int = 10):
    """Return the last N analyses, newest first."""
    try:
        records = await run_in_threadpool(get_history, min(limit, 100))
        return {"records": records, "count": len(records)}
    except Exception as e:
        logger.error(f"/history error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/history/{history_id}", tags=["History"])
async def get_history_record(history_id: str):
    """Fetch a single history record by ID (for reloading into the UI)."""
    record = await run_in_threadpool(get_history_item, history_id)
    if not record:
        return JSONResponse(status_code=404, content={"error": "Not found"})
    return record


@app.delete("/history/{history_id}", tags=["History"])
async def remove_history_record(history_id: str):
    """Delete a history record by ID."""
    deleted = await run_in_threadpool(delete_history_item, history_id)
    if not deleted:
        return JSONResponse(status_code=404, content={"error": "Not found"})
    return {"deleted": True}