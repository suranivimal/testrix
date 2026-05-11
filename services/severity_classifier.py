import asyncio
import logging
import re

from ai_engine.llm import ask_ai

logger = logging.getLogger(__name__)

# Severity levels ordered highest → lowest
SEVERITIES = ("Critical", "High", "Medium", "Low")

# Keywords in element names that map to a severity floor
_CRITICAL_KEYWORDS = (
    "nav", "navigation", "header", "checkout", "cart", "payment",
    "add to cart", "buy", "purchase", "cta", "call to action",
    "login", "signup", "sign up", "menu",
)
_HIGH_KEYWORDS = (
    "hero", "banner", "headline", "title", "price", "product image",
    "featured", "promotion", "sale", "discount", "badge",
)
_LOW_KEYWORDS = (
    "footer", "shadow", "border", "icon", "tooltip", "hover",
    "background", "divider", "separator",
)


def _rule_based(element: str, diff_percent: float) -> str:
    """
    Fast deterministic pass — returns severity based on element name + diff size.
    This is always run first; LLM confirms or upgrades for borderline cases.
    """
    el = element.lower()

    # Critical: key conversion elements regardless of diff size
    if any(kw in el for kw in _CRITICAL_KEYWORDS):
        return "Critical"

    # High: above-the-fold content with significant diff
    if any(kw in el for kw in _HIGH_KEYWORDS):
        return "High" if diff_percent >= 5.0 else "Medium"

    # Low: decorative elements
    if any(kw in el for kw in _LOW_KEYWORDS):
        return "Low"

    # Fallback — classify purely by diff percentage
    if diff_percent >= 30.0:
        return "Critical"
    if diff_percent >= 15.0:
        return "High"
    if diff_percent >= 5.0:
        return "Medium"
    return "Low"


_LLM_PROMPT = """You are classifying UI bugs by severity for a Shopify storefront.

Bug details:
- Element: {element}
- Description: {description}
- User impact: {user_impact}
- Pixel diff: {diff_percent}% of the region differs
- Rule-based initial severity: {rule_severity}

Severity definitions:
- Critical: breaks core user journey (checkout, navigation, add-to-cart, login)
- High: above-the-fold content mismatch that harms brand trust or readability
- Medium: layout/spacing/typography issues visible but not blocking
- Low: minor cosmetic differences (shadows, borders, decorative elements)

Reply with exactly one word — the severity level: Critical, High, Medium, or Low.
Do not explain."""


async def classify_issue(issue: dict) -> dict:
    """
    Classify a single issue dict (from visual_ai_analyzer) and add 'severity' field.
    Mutates and returns the issue dict.
    """
    element = issue.get("element", "Unknown element")
    description = issue.get("description", "")
    user_impact = issue.get("user_impact", "")
    diff_percent = issue.get("diff_percent", 0.0)

    # Step 1: rule-based fast pass
    rule_severity = _rule_based(element, diff_percent)

    # Step 2: LLM confirmation — only call for Medium/borderline cases to save cost
    if rule_severity in ("Critical", "Low") and diff_percent > 1.0:
        # High confidence from rules — trust them directly
        final_severity = rule_severity
        logger.debug(f"Rule-based severity for '{element}': {final_severity} (skipping LLM)")
    else:
        try:
            prompt = _LLM_PROMPT.format(
                element=element,
                description=description[:300],
                user_impact=user_impact[:200],
                diff_percent=diff_percent,
                rule_severity=rule_severity,
            )
            raw = await ask_ai(prompt)
            final_severity = _parse_severity(raw, fallback=rule_severity)
            logger.debug(f"LLM severity for '{element}': {final_severity} (rule was {rule_severity})")
        except Exception as e:
            logger.warning(f"LLM severity classification failed for '{element}': {e} — using rule-based")
            final_severity = rule_severity

    issue["severity"] = final_severity
    issue["rule_severity"] = rule_severity
    return issue


async def classify_all(issues: list[dict]) -> list[dict]:
    """Classify all issues and sort by severity (Critical first)."""
    classified = await asyncio.gather(*[classify_issue(issue) for issue in issues])
    severity_order = {s: i for i, s in enumerate(SEVERITIES)}
    return sorted(classified, key=lambda x: severity_order.get(x.get("severity", "Low"), 99))


def _parse_severity(raw: str, fallback: str) -> str:
    """Extract severity word from LLM response; fall back if not recognized."""
    clean = raw.strip().split()[0] if raw.strip() else ""
    # Capitalize first letter only
    clean = clean.capitalize()
    if clean in SEVERITIES:
        return clean
    # Try case-insensitive search anywhere in response
    for s in SEVERITIES:
        if re.search(s, raw, re.IGNORECASE):
            return s
    logger.warning(f"Could not parse severity from: {raw!r} — using fallback: {fallback}")
    return fallback