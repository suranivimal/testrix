import ipaddress
import logging
import socket
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

_PAGE_PATHS = {
    "home": "/",
    "product": "/products",
    "collection": "/collections/all",
    "cart": "/cart",
}

_VIEWPORT_DESKTOP = {"width": 1440, "height": 900}


def validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"Only https:// URLs are allowed, got: {parsed.scheme}://")
    if not parsed.hostname:
        raise ValueError("URL has no hostname")
    try:
        ip_str = socket.gethostbyname(parsed.hostname)
        ip = ipaddress.ip_address(ip_str)
    except socket.gaierror:
        raise ValueError(f"Cannot resolve hostname: {parsed.hostname}")
    for network in _BLOCKED_NETWORKS:
        if ip in network:
            raise ValueError(f"Private/internal URLs are not allowed: {parsed.hostname}")


def _screenshot_page(context, url: str, timeout_ms: int) -> bytes:
    page = None
    try:
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(2000)
        return page.screenshot(
            full_page=False,
            animations="disabled",
            timeout=timeout_ms,
        )
    finally:
        if page is not None:
            page.close()


def capture_pages(
    base_url: str,
    pages: list[str],
    password: str | None = None,
    timeout_ms: int = 30000,
) -> list[dict]:
    """
    Sync Playwright implementation — must be called from a worker thread,
    not directly from the asyncio event loop.
    """
    validate_url(base_url)
    base_url = base_url.rstrip("/")

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport=_VIEWPORT_DESKTOP,
                device_scale_factor=2,
            )

            if password:
                unlock_url = f"{base_url}/password"
                page = context.new_page()
                try:
                    page.goto(unlock_url, wait_until="domcontentloaded", timeout=timeout_ms)
                    pwd_input = page.locator("input[type='password']")
                    if pwd_input.count() > 0:
                        pwd_input.fill(password)
                        page.locator("input[type='submit'], button[type='submit']").first.click()
                        page.wait_for_load_state("networkidle", timeout=timeout_ms)
                        logger.info("Shopify store unlocked with password")
                finally:
                    page.close()

            browser_alive = True
            for page_name in pages:
                if not browser_alive:
                    results.append({"page": page_name, "url": f"{base_url}{_PAGE_PATHS.get(page_name, f'/{page_name}')}", "screenshot": None, "error": "Browser closed unexpectedly"})
                    continue
                path = _PAGE_PATHS.get(page_name, f"/{page_name}")
                url = f"{base_url}{path}"
                logger.info(f"Screenshotting {page_name} → {url}")
                try:
                    screenshot_bytes = _screenshot_page(context, url, timeout_ms)
                    results.append({
                        "page": page_name,
                        "url": url,
                        "screenshot": screenshot_bytes,
                        "error": None,
                    })
                    logger.info(f"Screenshot OK — {page_name}, {len(screenshot_bytes)} bytes")
                except Exception as e:
                    err_str = str(e)
                    logger.warning(f"Screenshot failed for {page_name}: {e}")
                    results.append({
                        "page": page_name,
                        "url": url,
                        "screenshot": None,
                        "error": err_str,
                    })
                    if "closed" in err_str.lower() or "Target closed" in err_str:
                        logger.error("Browser/context closed unexpectedly — stopping remaining screenshots")
                        browser_alive = False

        finally:
            browser.close()

    return results