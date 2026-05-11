import asyncio
import logging
import os
import time
from urllib.parse import urlparse, parse_qs

import httpx

logger = logging.getLogger(__name__)

_FIGMA_API = "https://api.figma.com/v1"

# ── Retry / backoff ──────────────────────────────────────────────────────────
_MAX_RETRIES = 5
_RETRY_BASE_S = 15          # first retry waits 15s, then 30s, 60s, 120s, 240s
_EXPORT_BATCH_SIZE = 5      # max node IDs per /images request — avoids 400 on large files

# ── Cache ────────────────────────────────────────────────────────────────────
_CACHE_TTL_S = 300          # 5 min — reuse frames across back-to-back jobs

# ── Throttle ─────────────────────────────────────────────────────────────────
_MIN_INTERVAL_S = 0.5       # ≤ 2 req/s to api.figma.com (well inside 120/min limit)
_MAX_CONCURRENT = 2         # semaphore: at most 2 simultaneous Figma API calls

# ── Runtime state (all lazy-initialised on first use) ────────────────────────
_frame_cache: dict[str, tuple[float, list[dict]]] = {}  # cache_key → (ts, frames)
_fetch_locks: dict[str, asyncio.Lock] = {}               # per-file-key dedup lock
_throttle_lock: asyncio.Lock | None = None
_api_semaphore: asyncio.Semaphore | None = None
_last_api_call_at: float = 0.0

# ── Persistent HTTP clients (reuse TCP connections across jobs) ──────────────
_api_client: httpx.AsyncClient | None = None    # api.figma.com  — short read timeout
_cdn_client: httpx.AsyncClient | None = None    # CDN PNG download — long read timeout


# ─────────────────────────────────────────────────────────────────────────────
# Initialisation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_api_client() -> httpx.AsyncClient:
    global _api_client
    if _api_client is None or _api_client.is_closed:
        _api_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10, read=60, write=10, pool=10),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
    return _api_client


def _get_cdn_client() -> httpx.AsyncClient:
    global _cdn_client
    if _cdn_client is None or _cdn_client.is_closed:
        _cdn_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10, read=120, write=10, pool=10),
            limits=httpx.Limits(max_keepalive_connections=3, max_connections=5),
        )
    return _cdn_client


def _get_throttle_lock() -> asyncio.Lock:
    global _throttle_lock
    if _throttle_lock is None:
        _throttle_lock = asyncio.Lock()
    return _throttle_lock


def _get_semaphore() -> asyncio.Semaphore:
    global _api_semaphore
    if _api_semaphore is None:
        _api_semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
    return _api_semaphore


# ─────────────────────────────────────────────────────────────────────────────
# Throttle
# ─────────────────────────────────────────────────────────────────────────────

async def _throttle() -> None:
    """Enforce _MIN_INTERVAL_S between consecutive calls to api.figma.com."""
    global _last_api_call_at
    async with _get_throttle_lock():
        gap = _MIN_INTERVAL_S - (time.monotonic() - _last_api_call_at)
        if gap > 0:
            await asyncio.sleep(gap)
        _last_api_call_at = time.monotonic()


# ─────────────────────────────────────────────────────────────────────────────
# Token validation
# ─────────────────────────────────────────────────────────────────────────────

def _get_token() -> str:
    token = os.environ.get("FIGMA_API_TOKEN", "")
    if not token:
        raise ValueError("FIGMA_API_TOKEN is not set. Add it to your .env file.")
    if not token.startswith("figd_"):
        raise ValueError(
            "FIGMA_API_TOKEN looks invalid — Figma personal access tokens must start with 'figd_'."
        )
    return token


# ─────────────────────────────────────────────────────────────────────────────
# URL parsing
# ─────────────────────────────────────────────────────────────────────────────

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

    node_id = None
    qs = parse_qs(parsed.query)
    raw_node = qs.get("node-id", [None])[0]
    if raw_node:
        node_id = raw_node.replace("-", ":")

    return file_key, node_id


# ─────────────────────────────────────────────────────────────────────────────
# Centralised API GET — throttle + semaphore + retry + structured logging
# ─────────────────────────────────────────────────────────────────────────────

async def _api_get(path: str, headers: dict, **kwargs) -> httpx.Response:
    """
    Single entry point for every call to api.figma.com.
    Applies throttling, concurrency cap, exponential backoff, and structured logging.
    """
    client = _get_api_client()
    semaphore = _get_semaphore()
    url = f"{_FIGMA_API}{path}"

    for attempt in range(_MAX_RETRIES):
        await _throttle()
        t0 = time.monotonic()

        try:
            async with semaphore:
                resp = await client.get(url, headers=headers, **kwargs)
        except httpx.TimeoutException as exc:
            elapsed = time.monotonic() - t0
            logger.warning(
                f"Figma timeout — path={path}, attempt={attempt + 1}/{_MAX_RETRIES}, "
                f"elapsed={elapsed:.2f}s: {exc}"
            )
            if attempt == _MAX_RETRIES - 1:
                raise RuntimeError(
                    f"Figma API timed out after {_MAX_RETRIES} attempts ({path})"
                ) from exc
            await asyncio.sleep(_RETRY_BASE_S * (2 ** attempt))
            continue

        elapsed = time.monotonic() - t0

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            wait = (
                int(retry_after)
                if retry_after and retry_after.isdigit()
                else _RETRY_BASE_S * (2 ** attempt)
            )
            logger.warning(
                f"Figma 429 — path={path}, attempt={attempt + 1}/{_MAX_RETRIES}, "
                f"retry_in={wait}s, elapsed={elapsed:.2f}s"
            )
            await asyncio.sleep(wait)
            continue

        if resp.status_code == 401:
            raise ValueError("Figma 401 — FIGMA_API_TOKEN is invalid or expired.")
        if resp.status_code == 403:
            raise ValueError("Figma 403 — token does not have access to this file.")
        if resp.status_code == 404:
            raise ValueError("Figma 404 — file not found. Check the URL and file permissions.")

        resp.raise_for_status()
        logger.info(
            f"Figma {resp.status_code} — path={path}, elapsed={elapsed:.2f}s, "
            f"response={len(resp.content)} bytes"
        )
        return resp

    raise RuntimeError(
        f"Figma API rate limit exceeded after {_MAX_RETRIES} retries ({path}). "
        "Wait a few minutes before submitting another job for the same file."
    )


# ─────────────────────────────────────────────────────────────────────────────
# CDN download — separate client, no throttle needed (not api.figma.com)
# ─────────────────────────────────────────────────────────────────────────────

async def _download_png(img_url: str, frame_name: str) -> bytes:
    """Download an exported PNG from Figma's CDN with timeout retry."""
    client = _get_cdn_client()
    for attempt in range(3):
        t0 = time.monotonic()
        try:
            resp = await client.get(img_url)
            resp.raise_for_status()
            elapsed = time.monotonic() - t0
            logger.info(
                f"CDN download OK — frame={frame_name}, "
                f"size={len(resp.content)} bytes, elapsed={elapsed:.2f}s"
            )
            return resp.content
        except httpx.TimeoutException as exc:
            elapsed = time.monotonic() - t0
            logger.warning(
                f"CDN timeout — frame={frame_name}, attempt={attempt + 1}/3, "
                f"elapsed={elapsed:.2f}s: {exc}"
            )
            if attempt == 2:
                raise RuntimeError(
                    f"CDN download timed out after 3 attempts for frame '{frame_name}'"
                ) from exc
            await asyncio.sleep(5 * (attempt + 1))

    raise RuntimeError(f"CDN download failed for frame '{frame_name}'")


# ─────────────────────────────────────────────────────────────────────────────
# Public API — cache + dedup lock layer
# ─────────────────────────────────────────────────────────────────────────────

async def extract_frames(figma_url: str) -> tuple[list[dict], dict]:
    """
    Return (frames, typography) where:
      frames     — list of { name, node_id, image_bytes, width, height }
      typography — { fonts, sizes, weights, colors } extracted from TEXT nodes

    Caches results for _CACHE_TTL_S seconds so back-to-back jobs for the same
    Figma file make zero additional API calls — eliminating the 429 chain.
    A per-file lock ensures only one in-flight fetch per file key at a time.
    """
    token = _get_token()
    file_key, node_id = parse_figma_url(figma_url)
    cache_key = f"{file_key}:{node_id or ''}"

    # ── Fast path: serve from cache ──────────────────────────────────────────
    cached = _frame_cache.get(cache_key)
    if cached:
        fetched_at, results, typography = cached
        age = time.monotonic() - fetched_at
        if age < _CACHE_TTL_S:
            logger.info(
                f"Figma cache hit — key={cache_key}, age={age:.0f}s, "
                f"ttl_remaining={_CACHE_TTL_S - age:.0f}s, frames={len(results)}"
            )
            return results, typography
        logger.info(f"Figma cache expired — key={cache_key}, age={age:.0f}s, re-fetching")

    # ── Dedup lock: one fetch per file at a time ─────────────────────────────
    if cache_key not in _fetch_locks:
        _fetch_locks[cache_key] = asyncio.Lock()

    async with _fetch_locks[cache_key]:
        # Another waiter may have populated the cache while we were waiting
        cached = _frame_cache.get(cache_key)
        if cached:
            fetched_at, results, typography = cached
            if time.monotonic() - fetched_at < _CACHE_TTL_S:
                logger.info(f"Figma cache hit (post-lock) — key={cache_key}, frames={len(results)}")
                return results, typography

        results, typography = await _fetch_frames(token, file_key, node_id)
        _frame_cache[cache_key] = (time.monotonic(), results, typography)
        logger.info(
            f"Figma frames cached — key={cache_key}, frames={len(results)}, "
            f"fonts={typography['fonts']}, ttl={_CACHE_TTL_S}s"
        )
        return results, typography


# ─────────────────────────────────────────────────────────────────────────────
# Internal fetch — called only through extract_frames
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_frames(token: str, file_key: str, node_id: str | None) -> list[dict]:
    """Hit the Figma API and download frame PNGs. No caching — use extract_frames."""
    headers = {"X-Figma-Token": token}

    # Step 1: file structure (depth 3 to reach TEXT nodes inside frames for typography)
    logger.info(f"Figma fetch start — key={file_key}, node_id={node_id or 'all'}")
    file_resp = await _api_get(f"/files/{file_key}", headers, params={"depth": 3})
    file_data = file_resp.json()

    frames = _collect_frames(file_data, node_id)
    if not frames:
        raise ValueError(
            "No frames found in the Figma file. "
            "Make sure the URL points to a file with top-level frames."
        )
    logger.info(f"Figma frames found — {len(frames)}: {[f['name'] for f in frames]}")

    # Step 2: export PNG URLs (batched to avoid 400 from URL-length limits)
    logger.info(f"Figma export request — {len(frames)} frame(s) at @2x PNG")
    image_urls: dict = {}
    for i in range(0, len(frames), _EXPORT_BATCH_SIZE):
        batch = frames[i:i + _EXPORT_BATCH_SIZE]
        node_ids = ",".join(f["node_id"] for f in batch)
        logger.info(f"Figma export batch {i // _EXPORT_BATCH_SIZE + 1}/{-(-len(frames) // _EXPORT_BATCH_SIZE)}: {len(batch)} frame(s)")
        img_resp = await _api_get(
            f"/images/{file_key}", headers,
            params={"ids": node_ids, "format": "png", "scale": 2},
        )
        img_data = img_resp.json()
        if img_data.get("err"):
            raise RuntimeError(f"Figma image export error: {img_data['err']}")
        image_urls.update(img_data.get("images", {}))

    # Step 3: download each PNG from CDN
    results = []
    for frame in frames:
        nid = frame["node_id"]
        img_url = image_urls.get(nid)
        if not img_url:
            logger.warning(f"No CDN URL for frame '{frame['name']}' ({nid}) — skipping")
            continue
        image_bytes = await _download_png(img_url, frame["name"])
        results.append({
            "name": frame["name"],
            "node_id": nid,
            "image_bytes": image_bytes,
            "width": frame.get("width"),
            "height": frame.get("height"),
        })

    typography = _collect_typography(file_data)
    logger.info(
        f"Figma fetch complete — key={file_key}, {len(results)} frame(s) downloaded, "
        f"fonts={typography['fonts']}"
    )
    return results, typography


# ─────────────────────────────────────────────────────────────────────────────
# Frame tree walker
# ─────────────────────────────────────────────────────────────────────────────

def _collect_frames(file_data: dict, target_node_id: str | None) -> list[dict]:
    """Walk the Figma document tree and collect frame nodes."""
    frames = []
    document = file_data.get("document", {})

    def walk(node: dict) -> None:
        node_type = node.get("type", "")
        node_id = node.get("id", "")
        name = node.get("name", "Untitled")
        bb = node.get("absoluteBoundingBox", {})
        w = bb.get("width")
        h = bb.get("height")

        if node_type in ("FRAME", "COMPONENT", "SECTION"):
            if target_node_id:
                if node_id == target_node_id or node_id.replace("-", ":") == target_node_id:
                    frames.append({"name": name, "node_id": node_id, "width": w, "height": h})
                    return
            else:
                frames.append({"name": name, "node_id": node_id, "width": w, "height": h})
                return

        for child in node.get("children", []):
            walk(child)

    pages = document.get("children", [])
    if not target_node_id:
        pages = pages[:1]  # first page only when no node targeted — avoids 400 from oversized /images requests
    for page in pages:
        for child in page.get("children", []):
            walk(child)

    return frames


# ─────────────────────────────────────────────────────────────────────────────
# Typography token extractor
# ─────────────────────────────────────────────────────────────────────────────

def _collect_typography(file_data: dict) -> dict:
    """
    Walk the full document tree and collect unique typography values from TEXT nodes.
    Returns { fonts, sizes, weights, colors } — all sorted lists of unique values.
    """
    fonts: set[str]   = set()
    sizes: set[int]   = set()
    weights: set[int] = set()
    colors: set[str]  = set()

    def walk(node: dict) -> None:
        if node.get("type") == "TEXT":
            style = node.get("style", {})
            if ff := style.get("fontFamily"):
                fonts.add(ff)
            if fs := style.get("fontSize"):
                sizes.add(int(fs))
            if fw := style.get("fontWeight"):
                weights.add(int(fw))
            for fill in node.get("fills", []):
                c = fill.get("color", {})
                if c:
                    r = int(c.get("r", 0) * 255)
                    g = int(c.get("g", 0) * 255)
                    b = int(c.get("b", 0) * 255)
                    colors.add(f"rgb({r},{g},{b})")
        for child in node.get("children", []):
            walk(child)

    document = file_data.get("document", {})
    for page in document.get("children", []):
        for child in page.get("children", []):
            walk(child)

    return {
        "fonts":   sorted(fonts),
        "sizes":   sorted(sizes),
        "weights": sorted(weights),
        "colors":  sorted(colors),
    }