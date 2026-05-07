import base64
import logging
from datetime import datetime, timezone

from services.db import update_vqa_job
from services.visual_comparator import CompareResult

logger = logging.getLogger(__name__)


def _b64(data: bytes | None) -> str | None:
    return base64.b64encode(data).decode() if data else None


def build_page_report(
    page_name: str,
    shopify_url: str,
    figma_frame: dict,
    live_screenshot: bytes,
    compare_result: CompareResult,
    issues: list[dict],
) -> dict:
    """
    Build a structured report dict for one page comparison.
    Images are stored as base64 strings so they can be embedded in the dashboard.
    """
    severity_counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    for issue in issues:
        sev = issue.get("severity", "Low")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    # Overall page health: worst severity found
    if severity_counts["Critical"] > 0:
        overall = "Critical"
    elif severity_counts["High"] > 0:
        overall = "High"
    elif severity_counts["Medium"] > 0:
        overall = "Medium"
    elif severity_counts["Low"] > 0:
        overall = "Low"
    else:
        overall = "Pass"

    return {
        "page": page_name,
        "url": shopify_url,
        "figma_frame": figma_frame.get("name", "Unknown"),
        "overall_severity": overall,
        "diff_percent": compare_result.diff_percent,
        "issue_count": len(issues),
        "severity_counts": severity_counts,
        "issues": issues,
        "figma_image_b64": _b64(figma_frame.get("image_bytes")),
        "live_image_b64": _b64(live_screenshot),
        "diff_image_b64": _b64(compare_result.diff_image),
        "diff_mask_b64": _b64(compare_result.diff_mask),
        "compared_at": datetime.now(timezone.utc).isoformat(),
    }


def build_full_report(
    job_id: str,
    shopify_url: str,
    figma_url: str,
    page_reports: list[dict],
) -> dict:
    """
    Combine all page reports into a top-level report and persist to MongoDB.
    Never stores the raw FIGMA_API_TOKEN — only the URL/file key.
    """
    total_issues = sum(r["issue_count"] for r in page_reports)
    all_severities = [r["overall_severity"] for r in page_reports if r["overall_severity"] != "Pass"]

    severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Pass": 4}
    overall = min(all_severities, key=lambda s: severity_order.get(s, 99)) if all_severities else "Pass"

    # Aggregate severity counts across all pages
    total_counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    for r in page_reports:
        for sev, count in r.get("severity_counts", {}).items():
            total_counts[sev] = total_counts.get(sev, 0) + count

    report = {
        "job_id": job_id,
        "shopify_url": shopify_url,
        "figma_url": figma_url,
        "overall_severity": overall,
        "total_issues": total_issues,
        "severity_counts": total_counts,
        "pages_tested": len(page_reports),
        "pages_passed": sum(1 for r in page_reports if r["overall_severity"] == "Pass"),
        "page_reports": page_reports,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Persist result to MongoDB job record
    update_vqa_job(
        job_id,
        status="complete",
        progress="Done",
        result=_strip_heavy_images(report),
    )
    logger.info(
        f"Report saved — job={job_id}, overall={overall}, "
        f"issues={total_issues}, pages={len(page_reports)}"
    )

    return report


def _strip_heavy_images(report: dict) -> dict:
    """
    Return a copy of the report with per-page images removed from MongoDB storage.
    The full report (with images) is returned to the caller; MongoDB only stores metadata + issues.
    Images are large (~500KB each) — storing them all in MongoDB is fine for MVP
    but we strip from the DB copy to keep documents manageable.
    """
    import copy
    light = copy.deepcopy(report)
    for page in light.get("page_reports", []):
        page.pop("figma_image_b64", None)
        page.pop("live_image_b64", None)
        page.pop("diff_image_b64", None)
        page.pop("diff_mask_b64", None)
    return light