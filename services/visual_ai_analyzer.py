import base64
import io
import logging
import os
from pathlib import Path

from openai import OpenAI
from PIL import Image

from services.visual_comparator import CompareResult, DiffRegion

logger = logging.getLogger(__name__)

_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
_MAX_IMAGE_DIM = 1568
_CANONICAL_WIDTH = 1440   # must match visual_comparator._CANONICAL_WIDTH
_CROP_PADDING = 30        # px of context around each diff region
_SYSTEM_PROMPT = (
    "You are a senior QA engineer specializing in visual regression testing. "
    "You compare Figma design mockups against live Shopify storefronts and identify "
    "UI/UX discrepancies with precision. Be specific: name the element, describe what "
    "differs, and explain the user impact."
)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        key = os.environ.get("GROQ_API_KEY", "")
        if not key:
            raise ValueError("GROQ_API_KEY is not set. Add it to your .env file.")
        _client = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
    return _client


def _encode_image(img_bytes: bytes, max_dim: int = _MAX_IMAGE_DIM) -> str:
    """Resize image and return base64 data-URL string."""
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    if img.width > max_dim or img.height > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.standard_b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


def _crop_region(img_bytes: bytes, x: int, y: int, w: int, h: int) -> str:
    """
    Normalize image to canonical width, crop the diff region with padding,
    and return a plain base64 JPEG string (no data-URL prefix).
    Coordinates are in normalized (1440px) space.
    """
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    scale = _CANONICAL_WIDTH / img.width
    new_h = int(img.height * scale)
    img = img.resize((_CANONICAL_WIDTH, new_h), Image.LANCZOS)

    x1 = max(0, x - _CROP_PADDING)
    y1 = max(0, y - _CROP_PADDING)
    x2 = min(img.width, x + w + _CROP_PADDING)
    y2 = min(img.height, y + h + _CROP_PADDING)

    cropped = img.crop((x1, y1, x2, y2))
    buf = io.BytesIO()
    cropped.save(buf, format="JPEG", quality=85)
    return base64.standard_b64encode(buf.getvalue()).decode()


def _save_crop(b64_str: str, out_dir: Path, filename: str) -> str:
    """Decode base64 JPEG and write to disk. Returns the file path as string."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    path.write_bytes(base64.b64decode(b64_str))
    return str(path)


def analyze(
    figma_bytes: bytes,
    live_bytes: bytes,
    compare_result: CompareResult,
    page_name: str = "page",
    job_id: str = "",
) -> list[dict]:
    """
    Send Figma + live screenshots to Groq vision and get structured issue descriptions.
    Returns a list of issue dicts, one per diff region. Each issue carries:
      expected_crop_b64  — Figma region JPEG (base64)
      actual_crop_b64    — Live region JPEG (base64)
      diff_crop_b64      — Diff heatmap region JPEG (base64)
      expected_screenshot_path / actual_screenshot_path / diff_screenshot_path
        — saved to artifacts/screenshots/{expected|current|diff}/{job_id}/ when job_id is given
    """
    if not compare_result.regions:
        logger.info(f"No diff regions for {page_name} — skipping AI analysis")
        return []

    client = _get_client()

    figma_data_url = _encode_image(figma_bytes)
    live_data_url = _encode_image(live_bytes)

    region_lines = []
    for i, r in enumerate(compare_result.regions, 1):
        region_lines.append(
            f"  Region {i}: position ({r.x},{r.y}), size {r.width}x{r.height}px, "
            f"{r.diff_percent}% of pixels differ"
        )
    region_summary = "\n".join(region_lines)

    prompt = f"""I'm comparing a Figma design mockup (Image 1) against the live Shopify store screenshot (Image 2) for the **{page_name}** page.

The automated pixel diff found {len(compare_result.regions)} changed region(s) with an overall {compare_result.diff_percent}% pixel difference:

{region_summary}

For each region, examine both images and describe:
1. What UI element is in that area (e.g. navigation bar, hero banner, product card, CTA button)
2. What specifically differs between the design and the live site
3. The likely user impact
4. A concise suggested fix (code or design change) to make the live site match the Figma design

Return a JSON array with one object per region:
[
  {{
    "region_index": 1,
    "element": "element name",
    "description": "what specifically differs",
    "user_impact": "how this affects users",
    "suggested_fix": "recommended change to match the Figma design"
  }}
]

Return only the JSON array, no markdown fences."""

    logger.info(f"Sending {page_name} to Groq vision — {len(compare_result.regions)} regions")

    response = client.chat.completions.create(
        model=_VISION_MODEL,
        max_tokens=1500,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Image 1 — Figma design mockup:"},
                    {"type": "image_url", "image_url": {"url": figma_data_url}},
                    {"type": "text", "text": "Image 2 — Live Shopify screenshot:"},
                    {"type": "image_url", "image_url": {"url": live_data_url}},
                    {"type": "text", "text": prompt},
                ],
            },
        ],
    )

    raw = response.choices[0].message.content.strip()
    logger.info(f"Groq vision response for {page_name}: {len(raw)} chars")

    issues = _parse_response(raw, compare_result.regions)

    # Directories for disk-saving crops (only when job_id is provided)
    output_root = Path(os.environ.get("OUTPUT_DIR", "artifacts")) / "screenshots"
    current_dir  = output_root / "current"  / (job_id or "tmp")
    expected_dir = output_root / "expected" / (job_id or "tmp")
    diff_dir     = output_root / "diff"     / (job_id or "tmp")

    for i, issue in enumerate(issues):
        if not all(k in issue for k in ("x", "y", "width", "height")):
            continue
        x, y, w, h = issue["x"], issue["y"], issue["width"], issue["height"]
        slug = f"{page_name}_i{i+1}.jpg"   # use position, not region_index, to avoid collisions
        try:
            issue["expected_crop_b64"] = _crop_region(figma_bytes, x, y, w, h)
            issue["actual_crop_b64"]   = _crop_region(live_bytes,  x, y, w, h)
            issue["diff_crop_b64"]     = _crop_region(compare_result.diff_mask, x, y, w, h)

            if job_id:
                issue["expected_screenshot_path"] = _save_crop(issue["expected_crop_b64"], expected_dir, slug)
                issue["actual_screenshot_path"]   = _save_crop(issue["actual_crop_b64"],   current_dir,  slug)
                issue["diff_screenshot_path"]     = _save_crop(issue["diff_crop_b64"],     diff_dir,     slug)
                # Browser-accessible URLs served by FastAPI /screenshots static mount
                issue["expected_screenshot_url"]  = f"/screenshots/expected/{job_id}/{slug}"
                issue["actual_screenshot_url"]    = f"/screenshots/current/{job_id}/{slug}"
                issue["diff_screenshot_url"]      = f"/screenshots/diff/{job_id}/{slug}"
                logger.info(f"Crops saved — job={job_id}, page={page_name}, issue={i+1}")
        except Exception as exc:
            logger.warning(f"Crop failed — page={page_name}, region={idx}: {exc}")

    return issues


def _parse_response(raw: str, regions: list[DiffRegion]) -> list[dict]:
    """Parse Groq's JSON response, fall back to basic issue list on failure."""
    import json
    import re

    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        raw = match.group(0)

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            for i, item in enumerate(parsed):
                # Try to match by the AI-supplied region_index first
                ai_idx = item.get("region_index", 1) - 1
                r = regions[ai_idx] if 0 <= ai_idx < len(regions) else None
                # Positional fallback: if region_index is out of range or already
                # used (AI often returns 1 for every issue), fall back to position i
                if r is None or ("x" in item):
                    r = regions[i] if i < len(regions) else regions[-1]
                item["x"] = r.x
                item["y"] = r.y
                item["width"] = r.width
                item["height"] = r.height
                item["diff_percent"] = r.diff_percent
                # Normalise region_index so it matches the actual region used
                item["region_index"] = regions.index(r) + 1
            return parsed
    except Exception as e:
        logger.warning(f"Failed to parse Groq vision JSON: {e} — using fallback")

    return [
        {
            "region_index": i + 1,
            "element": "Unknown element",
            "description": raw[:300] if i == 0 else "See region 1 for full analysis",
            "user_impact": "Visual discrepancy detected",
            "suggested_fix": "",
            "x": r.x, "y": r.y, "width": r.width, "height": r.height,
            "diff_percent": r.diff_percent,
        }
        for i, r in enumerate(regions)
    ]