import asyncio
import logging

from fastapi.concurrency import run_in_threadpool

from db import update_vqa_job
from services.bug_report_generator import build_full_report, build_page_report
from services.figma_extractor import extract_frames
from services.severity_classifier import classify_all
from services.shopify_scraper import capture_pages
from services.visual_ai_analyzer import analyze
from services.visual_comparator import compare

logger = logging.getLogger(__name__)

_DEFAULT_PAGES = ["home", "product", "collection", "cart"]


async def run_visual_qa(
    job_id: str,
    shopify_url: str,
    figma_url: str,
    pages: list[str] | None = None,
    shopify_password: str | None = None,
    diff_threshold: float = 0.05,
) -> dict:
    """
    Full visual QA pipeline. Runs as a FastAPI BackgroundTask.
    Writes progress updates to MongoDB so the polling endpoint reflects live status.
    Returns the full report dict (also persisted to MongoDB on completion).
    """
    if not pages:
        pages = _DEFAULT_PAGES

    try:
        # ── Step 1: Fetch Figma frames + Shopify screenshots in parallel ──────
        await _progress(job_id, "running", "Fetching Figma frames and Shopify screenshots...")

        figma_task = asyncio.create_task(extract_frames(figma_url))
        shopify_task = asyncio.create_task(
            run_in_threadpool(capture_pages, shopify_url, pages, shopify_password)
        )

        try:
            figma_frames, shopify_pages = await asyncio.gather(figma_task, shopify_task)
        except Exception as e:
            await _fail(job_id, f"Fetch failed: {e}")
            raise

        logger.info(
            f"Job {job_id}: {len(figma_frames)} Figma frame(s), "
            f"{len(shopify_pages)} Shopify page(s)"
        )

        if not figma_frames:
            await _fail(job_id, "No frames found in the Figma file.")
            raise ValueError("No frames found in the Figma file.")

        # ── Step 2: Match pages to Figma frames ──────────────────────────────
        # Strategy: match by name similarity, fall back to first frame
        page_frame_pairs = _match_pages_to_frames(shopify_pages, figma_frames)

        # ── Step 3: Compare + analyse each page ──────────────────────────────
        page_reports = []
        total = len(page_frame_pairs)

        for idx, (shopify_page, figma_frame) in enumerate(page_frame_pairs, 1):
            page_name = shopify_page["page"]

            if shopify_page["error"] or not shopify_page["screenshot"]:
                logger.warning(f"Job {job_id}: skipping {page_name} — screenshot failed: {shopify_page['error']}")
                continue

            await _progress(
                job_id, "running",
                f"Comparing {page_name} ({idx}/{total})..."
            )

            # Visual diff
            compare_result = compare(
                figma_bytes=figma_frame["image_bytes"],
                live_bytes=shopify_page["screenshot"],
                diff_threshold=diff_threshold,
            )
            logger.info(
                f"Job {job_id} / {page_name}: {compare_result.diff_percent}% diff, "
                f"{len(compare_result.regions)} region(s)"
            )

            # AI analysis (only if there are diff regions)
            if compare_result.regions:
                await _progress(job_id, "running", f"Analysing {page_name} with AI...")
                issues = analyze(
                    figma_bytes=figma_frame["image_bytes"],
                    live_bytes=shopify_page["screenshot"],
                    compare_result=compare_result,
                    page_name=page_name,
                )
                issues = await classify_all(issues)
            else:
                issues = []

            page_report = build_page_report(
                page_name=page_name,
                shopify_url=shopify_page["url"],
                figma_frame=figma_frame,
                live_screenshot=shopify_page["screenshot"],
                compare_result=compare_result,
                issues=issues,
            )
            page_reports.append(page_report)

        if not page_reports:
            await _fail(job_id, "All page screenshots failed — nothing to compare.")
            raise RuntimeError("All page screenshots failed.")

        # ── Step 4: Build + persist full report ──────────────────────────────
        await _progress(job_id, "running", "Building report...")

        report = build_full_report(
            job_id=job_id,
            shopify_url=shopify_url,
            figma_url=figma_url,
            page_reports=page_reports,
        )

        logger.info(
            f"Job {job_id} complete — overall={report['overall_severity']}, "
            f"issues={report['total_issues']}"
        )
        return report

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        await _fail(job_id, str(e))
        raise


def _match_pages_to_frames(
    shopify_pages: list[dict],
    figma_frames: list[dict],
) -> list[tuple[dict, dict]]:
    """
    Pair each Shopify page with the best-matching Figma frame by name.
    Falls back to the first frame if no name match found.
    """
    pairs = []
    for page in shopify_pages:
        page_name = page["page"].lower()
        best = None
        for frame in figma_frames:
            frame_name = frame["name"].lower()
            if page_name in frame_name or frame_name in page_name:
                best = frame
                break
        if best is None:
            best = figma_frames[0]
        pairs.append((page, best))
    return pairs


async def _progress(job_id: str, status: str, message: str) -> None:
    update_vqa_job(job_id, status=status, progress=message)
    logger.info(f"Job {job_id} [{status}]: {message}")


async def _fail(job_id: str, reason: str) -> None:
    update_vqa_job(job_id, status="failed", error=reason, progress="Failed")
    logger.error(f"Job {job_id} failed: {reason}")