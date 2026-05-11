import base64
import io
import logging
import os

from openai import OpenAI
from PIL import Image

from services.visual_comparator import CompareResult, DiffRegion

logger = logging.getLogger(__name__)

_VISION_MODEL = "llama-3.2-11b-vision-preview"
_MAX_IMAGE_DIM = 1568
_SYSTEM_PROMPT = (
    "You are a senior QA engineer specializing in visual regression testing. "
    "You compare Figma design mockups against live Shopify storefronts and identify "
    "UI/UX discrepancies with precision. Be specific: name the element, describe what "
    "differs, and explain the user impact."
)


def _get_client() -> OpenAI:
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        raise ValueError("GROQ_API_KEY is not set. Add it to your .env file.")
    return OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")


def _encode_image(img_bytes: bytes, max_dim: int = _MAX_IMAGE_DIM) -> str:
    """Resize image and return base64 data-URL string."""
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    if img.width > max_dim or img.height > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.standard_b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


def analyze(
    figma_bytes: bytes,
    live_bytes: bytes,
    compare_result: CompareResult,
    page_name: str = "page",
) -> list[dict]:
    """
    Send Figma + live screenshots to Groq vision and get structured issue descriptions.
    Returns a list of issue dicts, one per diff region.
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

Return a JSON array with one object per region:
[
  {{
    "region_index": 1,
    "element": "element name",
    "description": "what differs",
    "user_impact": "how this affects users"
  }}
]

Return only the JSON array, no markdown fences."""

    logger.info(f"Sending {page_name} to Groq vision — {len(compare_result.regions)} regions")

    response = client.chat.completions.create(
        model=_VISION_MODEL,
        max_tokens=1024,
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

    return _parse_response(raw, compare_result.regions)


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
            for item in parsed:
                idx = item.get("region_index", 1) - 1
                if 0 <= idx < len(regions):
                    r = regions[idx]
                    item["x"] = r.x
                    item["y"] = r.y
                    item["width"] = r.width
                    item["height"] = r.height
                    item["diff_percent"] = r.diff_percent
            return parsed
    except Exception as e:
        logger.warning(f"Failed to parse Groq vision JSON: {e} — using fallback")

    return [
        {
            "region_index": i + 1,
            "element": "Unknown element",
            "description": raw[:300] if i == 0 else "See region 1 for full analysis",
            "user_impact": "Visual discrepancy detected",
            "x": r.x, "y": r.y, "width": r.width, "height": r.height,
            "diff_percent": r.diff_percent,
        }
        for i, r in enumerate(regions)
    ]