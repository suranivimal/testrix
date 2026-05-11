import asyncio
import logging
import os
import re
from urllib.parse import urlparse, parse_qs

import httpx

logger = logging.getLogger(__name__)

_FIGMA_API = "https://api.figma.com/v1"
_MAX_RETRIES = 3
_RETRY_BASE_S = 2


def _get_token() -> str:
    token = os.environ.get("FIGMA_API_TOKEN", "")
    if not token:
        raise ValueError("FIGMA_API_TOKEN is not set. Add it to your .env file.")
    return token


def parse_figma_url(figma_url: str) -> tuple[str, str | None]:
    """Return (file_key, node_id | None) from any Figma URL format."""
    parsed = urlparse(figma_url)
    parts = parsed.path.strip("/").split("/")

    file_key = None
    for i, part in enumerate(parts):
        if part in ("design", "file", "board", "slides", "make", "proto") and i + 1 < len(parts):
            file_key = parts[i + 1]
            # branch URLs: /design/:fileKey/branch/:branchKey/... → use branchKey
            if i + 3 < len(parts) and parts[i + 2] == "branch":
                file_key = parts[i + 3]
            break

    if not file_key:
        raise ValueError(f"Could not extract file key from Figma URL: {figma_url}")

    # node-id comes from query param, convert - to :
    node_id = None
    qs = parse_qs(parsed.query)
    raw_node = qs.get("node-id", [None])[0]
    if raw_node:
        node_id = raw_node.replace("-", ":")

    return file_key, node_id


async def _get_with_retry(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    for attempt in range(_MAX_RETRIES):
        resp = await client.get(url, **kwargs)
        if resp.status_code == 429:
            wait = _RETRY_BASE_S * (2 ** attempt)
            logger.warning(f"Figma rate limited — retrying in {wait}s (attempt {attempt + 1}/{_MAX_RETRIES})")
            await asyncio.sleep(wait)
            continue
        if resp.status_code == 401:
            raise ValueError("Figma API returned 401 — check your FIGMA_API_TOKEN")
        if resp.status_code == 403:
            raise ValueError("Figma API returned 403 — you don't have access to this file")
        if resp.status_code == 404:
            raise ValueError("Figma file not found — check the URL")
        resp.raise_for_status()
        return resp
    raise RuntimeError(f"Figma API rate limit exceeded after {_MAX_RETRIES} retries")


async def extract_frames(figma_url: str) -> list[dict]:
    """
    Return a list of frame dicts:
      { name, node_id, image_bytes, width, height }
    """
    token = _get_token()
    file_key, node_id = parse_figma_url(figma_url)
    headers = {"X-Figma-Token": token}

    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Get file structure to find top-level frames
        logger.info(f"Fetching Figma file structure — key={file_key}")
        file_resp = await _get_with_retry(
            client,
            f"{_FIGMA_API}/files/{file_key}",
            headers=headers,
            params={"depth": 2},
        )
        file_data = file_resp.json()

        frames = _collect_frames(file_data, node_id)
        if not frames:
            raise ValueError("No frames found in the Figma file. Make sure the URL points to a file with frames.")

        logger.info(f"Found {len(frames)} frame(s): {[f['name'] for f in frames]}")

        # 2. Export frames as PNG at @2x scale
        node_ids = ",".join(f["node_id"] for f in frames)
        logger.info(f"Exporting {len(frames)} frame(s) as PNG @2x")
        img_resp = await _get_with_retry(
            client,
            f"{_FIGMA_API}/images/{file_key}",
            headers=headers,
            params={"ids": node_ids, "format": "png", "scale": 2},
        )
        img_data = img_resp.json()
        image_urls: dict = img_data.get("images", {})

        if img_data.get("err"):
            raise RuntimeError(f"Figma image export error: {img_data['err']}")

        # 3. Download each exported PNG
        results = []
        for frame in frames:
            nid = frame["node_id"]
            img_url = image_urls.get(nid)
            if not img_url:
                logger.warning(f"No image URL for frame {frame['name']} ({nid}) — skipping")
                continue
            logger.info(f"Downloading frame image: {frame['name']}")
            dl_resp = await client.get(img_url, timeout=30)
            dl_resp.raise_for_status()
            results.append({
                "name": frame["name"],
                "node_id": nid,
                "image_bytes": dl_resp.content,
                "width": frame.get("width"),
                "height": frame.get("height"),
            })
            logger.info(f"Frame downloaded — {frame['name']}, {len(dl_resp.content)} bytes")

    return results


def _collect_frames(file_data: dict, target_node_id: str | None) -> list[dict]:
    """Walk the Figma document tree and collect frame nodes."""
    frames = []
    document = file_data.get("document", {})

    def walk(node: dict):
        node_type = node.get("type", "")
        node_id = node.get("id", "")
        name = node.get("name", "Untitled")
        bb = node.get("absoluteBoundingBox", {})
        w = bb.get("width")
        h = bb.get("height")

        if node_type in ("FRAME", "COMPONENT", "SECTION"):
            # If a specific node_id was given, only include matching frames
            if target_node_id:
                if node_id == target_node_id or node_id.replace("-", ":") == target_node_id:
                    frames.append({"name": name, "node_id": node_id, "width": w, "height": h})
                    return  # don't recurse into selected frame's children
            else:
                frames.append({"name": name, "node_id": node_id, "width": w, "height": h})
                return  # top-level frames only

        for child in node.get("children", []):
            walk(child)

    for page in document.get("children", []):
        for child in page.get("children", []):
            walk(child)

    return frames