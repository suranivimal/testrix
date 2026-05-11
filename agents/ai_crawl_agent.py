"""
AI Website Crawling Engine — full pipeline:
  1. Discover pages via sitemap + BFS (services/site_crawler)
  2. Inspect each page via Playwright multi-viewport (browser/browser_agent)
  3. Rule-based QA evaluation (qa/qa_engine)
  4. LLM GO/NO-GO review (agent/ai_reviewer)
  5. Persist result to MongoDB
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict

from fastapi.concurrency import run_in_threadpool

from agent.ai_reviewer import AIReviewer
from agent.llm_client import LLMClient
from browser.browser_agent import BrowserAgent
from config.settings import get_settings
from qa.models import RequirementModel
from qa.qa_engine import QAEngine
from services.db import update_ai_crawl_job
from services.site_crawler import discover_site

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


async def run_ai_crawl(
    job_id: str,
    seed_url: str,
    max_pages: int = 20,
    max_depth: int = 2,
) -> None:
    """
    Full AI crawl pipeline. Runs as a FastAPI BackgroundTask.
    Updates MongoDB job doc with progress; writes final result on completion.
    """
    settings = get_settings()

    try:
        # ── Step 1: Page discovery ────────────────────────────────────────────
        _update(job_id, "running", "Discovering pages via sitemap and link crawl…")

        crawl_graph = await run_in_threadpool(
            discover_site, seed_url, max_pages, max_depth, False
        )
        routes = crawl_graph["routes_for_pipeline"]
        pages_found = len(crawl_graph["pages"])
        logger.info("Job %s: discovered %d pages, %d routes", job_id, pages_found, len(routes))

        _update(
            job_id, "running",
            f"Found {pages_found} pages. Launching browser inspection…",
        )

        # ── Step 2: Playwright browser inspection (async, multi-viewport) ─────
        # Run in a dedicated thread with its own event loop: uvicorn uses
        # SelectorEventLoop on Windows which cannot launch subprocesses (Playwright).
        inspect_routes = routes[:max_pages]
        observations = await run_in_threadpool(
            _browser_inspect_sync,
            seed_url,
            inspect_routes,
            settings.browser_headless,
            settings.browser_timeout_ms,
            settings.screenshot_dir,
        )
        unique_pages = len({o.page for o in observations})
        logger.info("Job %s: inspected %d pages (%d observations)", job_id, unique_pages, len(observations))

        _update(job_id, "running", f"Inspected {unique_pages} pages. Running QA evaluation…")

        # ── Step 3: Rule-based QA evaluation ─────────────────────────────────
        # No requirements file needed — QAEngine still catches console errors,
        # network failures, accessibility issues, and responsive mismatches.
        requirements = RequirementModel(
            source_path=seed_url,
            features=[],
            acceptance_criteria=[],
            functional_flows=[],
            validation_logic=[],
            edge_cases=[],
            business_expectations=[],
        )
        qa_engine = QAEngine()
        qa_result = qa_engine.evaluate(requirements, None, observations)
        logger.info("Job %s: QA engine produced %d findings", job_id, len(qa_result.findings))

        _update(job_id, "running", "Generating AI review and GO/NO-GO recommendation…")

        # ── Step 4: LLM GO/NO-GO review ──────────────────────────────────────
        llm_client = LLMClient(settings)
        ai_reviewer = AIReviewer(llm_client)
        ai_review = await ai_reviewer.review(requirements, None, qa_result)

        # ── Compile final result ──────────────────────────────────────────────
        sorted_findings = sorted(
            [asdict(f) for f in qa_result.findings],
            key=lambda f: _SEVERITY_ORDER.get(f["severity"].lower(), 99),
        )

        findings_by_page: dict[str, list[dict]] = {}
        for f in sorted_findings:
            key = f.get("page") or "global"
            findings_by_page.setdefault(key, []).append(f)

        obs_summary = [
            {
                "page": obs.page,
                "url": obs.url,
                "viewport": obs.viewport,
                "console_errors": obs.console_errors,
                "network_failures": obs.network_failures,
                "accessibility_notes": obs.accessibility_notes,
                "error": obs.error,
            }
            for obs in observations
        ]

        result = {
            "seed_url": seed_url,
            "pages_discovered": pages_found,
            "pages_inspected": unique_pages,
            "routes": routes,
            "crawl_stats": crawl_graph.get("stats", {}),
            "findings": sorted_findings,
            "findings_by_page": findings_by_page,
            "severity_counts": _count_severity(qa_result.findings),
            "accessibility_gaps": qa_result.accessibility_gaps,
            "accessibility_blocker_count": qa_result.accessibility_blocker_count,
            "responsive_issues": qa_result.responsive_issues,
            "visual_mismatch_scores": qa_result.visual_mismatch_scores,
            "observations": obs_summary,
            "ai_review": ai_review,
            "recommendation": ai_review.get("recommendation", "NO-GO"),
        }

        _update(job_id, "complete", "Done.", result=result)
        logger.info(
            "Job %s complete — recommendation=%s, findings=%d",
            job_id, result["recommendation"], len(sorted_findings),
        )

    except Exception as exc:
        err_msg = repr(exc) or f"{type(exc).__name__}: (no message)"
        logger.error("AI crawl job %s failed: %s", job_id, err_msg, exc_info=True)
        _update(job_id, "failed", "Failed.", error=err_msg)
        raise


def _update(job_id: str, status: str, progress: str, result=None, error=None) -> None:
    fields: dict = {"status": status, "progress": progress}
    if result is not None:
        fields["result"] = result
    if error is not None:
        fields["error"] = error
    update_ai_crawl_job(job_id, **fields)


def _count_severity(findings) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in findings:
        key = f.severity.capitalize()
        counts[key] = counts.get(key, 0) + 1
    return counts


def _browser_inspect_sync(seed_url, routes, headless, timeout_ms, screenshot_dir):
    """
    Run BrowserAgent.inspect() in a dedicated thread with its own event loop.
    Required on Windows: uvicorn's SelectorEventLoop cannot launch subprocesses
    (Playwright needs ProactorEventLoop for browser process creation).
    """
    async def _inner():
        agent = BrowserAgent(headless=headless, timeout_ms=timeout_ms, screenshot_dir=screenshot_dir)
        return await agent.inspect(seed_url, routes)

    return asyncio.run(_inner())