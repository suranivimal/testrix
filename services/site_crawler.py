"""
Bounded site discovery: sitemap(s) + same-host BFS HTML link crawl.
Produces a normalized page list + coarse page-type hints for QA pipelines.

SPA-heavy sites may under-report links (server HTML only); use Playwright
discovery later if you need client-rendered routes.
"""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass, asdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse

import httpx

from services.shopify_scraper import validate_url

logger = logging.getLogger(__name__)

_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
_DEFAULT_UA = "TestrixSiteCrawler/1.0 (+https://github.com/testrix)"
_ARTIFACTS_DIR = Path("artifacts") / "crawl"


def canonicalize_url(url: str, base: str | None = None) -> str:
    """Strip fragment, resolve against base, normalize scheme/host casing."""
    raw = url.strip()
    if base:
        raw = urljoin(base, raw)
    raw, _frag = urldefrag(raw)
    p = urlparse(raw)
    if not p.scheme or not p.netloc:
        return ""
    scheme = p.scheme.lower()
    netloc = p.netloc.lower()
    path = p.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    normalized = urlunparse((scheme, netloc, path, "", p.query, ""))
    return normalized


def classify_page_type(path: str) -> str:
    """Heuristic template label (Shopify-oriented + generic)."""
    p = (path or "/").lower()
    if p in ("/", ""):
        return "home"
    if p == "/cart" or p.startswith("/cart/"):
        return "cart"
    if "/collections/" in p or p.startswith("/collections"):
        return "collection"
    if "/products/" in p or p == "/products" or p.startswith("/products"):
        return "product"
    if "/blogs/" in p or "/blog/" in p or p.startswith("/blogs") or p.startswith("/blog"):
        return "blog"
    if "/pages/" in p or p.startswith("/pages"):
        return "page"
    if "/search" in p:
        return "search"
    return "other"


class _HrefCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for k, v in attrs:
            if k.lower() == "href" and v:
                self.hrefs.append(v)
                return


def _extract_hrefs(html: str) -> list[str]:
    parser = _HrefCollector()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass
    return parser.hrefs


def _page_signals(html: str) -> dict[str, int]:
    return {
        "forms": len(re.findall(r"<form\b", html, re.I)),
        "inputs": len(re.findall(r"<input\b", html, re.I)),
        "textareas": len(re.findall(r"<textarea\b", html, re.I)),
        "selects": len(re.findall(r"<select\b", html, re.I)),
        "buttons": len(re.findall(r"<button\b", html, re.I)),
        "anchors": len(re.findall(r"<a\b", html, re.I)),
        "roles_button": len(re.findall(r"""role\s*=\s*['"]button['"]""", html, re.I)),
    }


def _same_site(url: str, allowed_netloc: str) -> bool:
    p = urlparse(url)
    return bool(p.netloc) and p.netloc.lower() == allowed_netloc.lower()


def _fetch_text(client: httpx.Client, url: str) -> tuple[str | None, int | None]:
    try:
        r = client.get(url, follow_redirects=True)
        ct = (r.headers.get("content-type") or "").lower()
        if r.status_code >= 400:
            return None, r.status_code
        if "xml" in ct and url.rsplit("?", 1)[0].lower().endswith(".xml"):
            return r.text, r.status_code
        if "html" in ct or "text/" in ct or ct == "":
            return r.text, r.status_code
        return None, r.status_code
    except Exception as e:
        logger.debug("fetch fail %s: %s", url, e)
        return None, None


def _parse_sitemap_locs(xml_text: str) -> tuple[list[str], list[str]]:
    """Return (page urls, nested sitemap urls)."""
    urls: list[str] = []
    sitemaps: list[str] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return urls, sitemaps

    tag = root.tag
    if tag.endswith("urlset"):
        for loc in root.findall(f".//{_NS}loc"):
            if loc.text and loc.text.strip():
                urls.append(loc.text.strip())
    elif tag.endswith("sitemapindex"):
        for loc in root.findall(f".//{_NS}loc"):
            if loc.text and loc.text.strip():
                sitemaps.append(loc.text.strip())
    else:
        for el in root.iter():
            if el.tag.endswith("loc") and el.text and el.text.strip():
                t = el.text.strip()
                if "sitemap" in el.tag.lower() or t.endswith(".xml"):
                    sitemaps.append(t)
                else:
                    urls.append(t)
    return urls, sitemaps


def _collect_sitemap_urls(client: httpx.Client, origin: str, max_urls: int) -> list[str]:
    found: list[str] = []
    seen_sm: set[str] = set()
    queue: deque[str] = deque()

    for path in ("/sitemap.xml", "/sitemap_index.xml"):
        queue.append(urljoin(origin, path))

    while queue and len(found) < max_urls:
        sm_url = queue.popleft()
        sm_c = canonicalize_url(sm_url, origin)
        if not sm_c or sm_c in seen_sm:
            continue
        seen_sm.add(sm_c)
        body, code = _fetch_text(client, sm_c)
        if not body or code != 200:
            continue
        pages, nested = _parse_sitemap_locs(body)
        for p in pages:
            c = canonicalize_url(p, origin)
            if c and _same_site(c, urlparse(origin).netloc):
                found.append(c)
                if len(found) >= max_urls:
                    break
        for n in nested:
            nc = canonicalize_url(n, origin)
            if nc and nc not in seen_sm:
                queue.append(nc)
    return found[:max_urls]


@dataclass
class CrawledPage:
    url: str
    path: str
    page_type: str
    depth: int
    signals: dict[str, int]
    source: str  # sitemap | crawl


def discover_site(
    seed_url: str,
    max_pages: int = 50,
    max_depth: int = 2,
    persist: bool = True,
    timeout_s: float = 12.0,
) -> dict:
    """
    Validate seed (SSRF-safe), pull sitemap URLs, then BFS same-host HTML pages.

    Returns JSON-serializable dict including ``routes_for_pipeline`` (path strings)
    for BrowserAgent / main.py.
    """
    validate_url(seed_url)
    seed = canonicalize_url(seed_url)
    if not seed:
        raise ValueError("Invalid seed URL")

    parsed = urlparse(seed)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    allowed_netloc = parsed.netloc.lower()

    pages_by_url: dict[str, CrawledPage] = {}
    stats = {"from_sitemap": 0, "from_crawl": 0, "fetched_html": 0, "skipped": 0}

    timeout = httpx.Timeout(timeout_s, connect=min(10.0, timeout_s))
    limits = httpx.Limits(max_connections=10)

    with httpx.Client(
        timeout=timeout,
        limits=limits,
        headers={"User-Agent": _DEFAULT_UA},
        follow_redirects=True,
    ) as client:
        sm_urls = _collect_sitemap_urls(client, origin, max_urls=max_pages * 2)
        for u in sm_urls:
            c = canonicalize_url(u, origin)
            if not c or not _same_site(c, allowed_netloc):
                continue
            path = urlparse(c).path or "/"
            if c not in pages_by_url:
                pages_by_url[c] = CrawledPage(
                    url=c,
                    path=path,
                    page_type=classify_page_type(path),
                    depth=0,
                    signals={},
                    source="sitemap",
                )
                stats["from_sitemap"] += 1

        if seed not in pages_by_url:
            path0 = urlparse(seed).path or "/"
            pages_by_url[seed] = CrawledPage(
                url=seed,
                path=path0,
                page_type=classify_page_type(path0),
                depth=0,
                signals={},
                source="seed",
            )

        queue: deque[tuple[str, int]] = deque()
        for u in list(pages_by_url.keys())[:max_pages]:
            queue.append((u, 0))
        if not any(u == seed for u, _ in queue):
            queue.appendleft((seed, 0))

        seen_fetch: set[str] = set()

        while queue and len(pages_by_url) < max_pages:
            current, depth = queue.popleft()
            cur_c = canonicalize_url(current, origin)
            if not cur_c or not _same_site(cur_c, allowed_netloc):
                stats["skipped"] += 1
                continue
            if depth > max_depth:
                continue
            if cur_c in seen_fetch:
                continue
            seen_fetch.add(cur_c)

            html, status = _fetch_text(client, cur_c)
            if not html or status != 200:
                stats["skipped"] += 1
                continue
            stats["fetched_html"] += 1
            signals = _page_signals(html)

            if cur_c in pages_by_url:
                pages_by_url[cur_c].signals = signals
            else:
                pth = urlparse(cur_c).path or "/"
                pages_by_url[cur_c] = CrawledPage(
                    url=cur_c,
                    path=pth,
                    page_type=classify_page_type(pth),
                    depth=depth,
                    signals=signals,
                    source="crawl",
                )
                stats["from_crawl"] += 1

            if depth >= max_depth:
                continue

            for href in _extract_hrefs(html):
                nxt = canonicalize_url(href, cur_c)
                if not nxt or not _same_site(nxt, allowed_netloc):
                    continue
                if nxt in pages_by_url:
                    continue
                if len(pages_by_url) >= max_pages:
                    break
                pth2 = urlparse(nxt).path or "/"
                if any(pth2.lower().endswith(ext) for ext in (
                    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
                    ".css", ".js", ".mjs", ".woff", ".woff2", ".ttf", ".pdf", ".zip",
                )):
                    continue
                pages_by_url[nxt] = CrawledPage(
                    url=nxt,
                    path=pth2,
                    page_type=classify_page_type(pth2),
                    depth=depth + 1,
                    signals={},
                    source="crawl",
                )
                stats["from_crawl"] += 1
                queue.append((nxt, depth + 1))
            if len(pages_by_url) >= max_pages:
                break

    ordered = sorted(pages_by_url.values(), key=lambda x: (x.depth, x.path))
    routes_for_pipeline = []
    seen_paths: set[str] = set()
    for p in ordered:
        route = p.path if p.path.startswith("/") else "/" + p.path
        if route not in seen_paths:
            seen_paths.add(route)
            routes_for_pipeline.append(route)

    by_type: dict[str, list[str]] = {}
    for p in ordered:
        by_type.setdefault(p.page_type, []).append(p.path)

    graph = {
        "seed": seed,
        "allowed_host": allowed_netloc,
        "max_pages": max_pages,
        "max_depth": max_depth,
        "stats": stats,
        "pages": [asdict(x) for x in ordered],
        "by_type": {k: sorted(set(v)) for k, v in by_type.items()},
        "routes_for_pipeline": routes_for_pipeline,
    }

    persist_path: str | None = None
    if persist:
        _ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        out = _ARTIFACTS_DIR / "latest.json"
        out.write_text(json.dumps(graph, indent=2), encoding="utf-8")
        persist_path = str(out.resolve())
        graph["persist_path"] = persist_path
        logger.info("Crawl graph saved — %s (%d pages)", persist_path, len(ordered))

    return graph
