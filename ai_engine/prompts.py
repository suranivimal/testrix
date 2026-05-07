_CATEGORY_MAP = {
    "auth": [
        "login", "logout", "password", "session", "jwt", "token", "oauth",
        "2fa", "otp", "sso", "authentication", "credential", "sign in", "signin",
        "access token", "refresh token", "bearer",
    ],
    "payment": [
        "payment", "charge", "card", "checkout", "billing", "refund",
        "transaction", "invoice", "subscription", "webhook", "stripe", "paypal",
        "cvv", "pan", "amount", "price",
    ],
    "file": [
        "upload", "file", "image", "attachment", "download", "storage",
        "s3", "cdn", "multipart", "binary", "pdf", "video", "media",
    ],
    "search": [
        "search", "query", "filter", "pagination", "sort", "find",
        "listing", "elasticsearch", "index", "facet", "autocomplete",
    ],
    "registration": [
        "register", "signup", "sign up", "create account", "email verification",
        "onboarding", "activate", "confirm email",
    ],
    "api": [
        "api", "endpoint", "request", "response", "status code",
        "header", "payload", "rest", "graphql", "rate limit", "throttle",
    ],
    "security": [
        "injection", "xss", "sql", "nosql", "command", "csrf", "idor",
        "traversal", "bypass", "vulnerability", "exploit", "attack", "hack",
    ],
    "performance": [
        "slow", "timeout", "latency", "load", "concurrent", "memory",
        "cpu", "performance", "throughput", "stress", "bottleneck", "lag",
    ],
    "data": [
        "database", "data", "record", "crud", "delete", "update", "insert",
        "migration", "schema", "integrity", "constraint",
    ],
}

# Category-specific extras injected automatically based on detected input categories.
_CATEGORY_EXTRAS = {
    "auth": {
        "tests": [
            "Token expiry — 401 after TTL exceeded; successful refresh renews it correctly",
            "Account lockout — locked after N failed attempts; cannot be bypassed by IP rotation",
            "2FA completeness — second factor cannot be skipped via direct endpoint call",
            "Concurrent sessions — simultaneous login from two devices handled per policy",
            "Remember-me — long-lived token revoked immediately on explicit logout",
            "Password change — active sessions invalidated after password reset",
        ],
        "security": [
            'JWT "none" algorithm attack — alg header set to "none"; server must reject',
            "JWT payload tampering — modify sub/role claim but keep original signature; must fail",
            "Session fixation — force known session ID before login; server must rotate session",
            "Account enumeration — response time and body must not differ for valid vs invalid email",
            "Credential stuffing — 50 rapid attempts with different passwords should trigger lockout/429",
            "OTP replay — reuse same OTP within validity window; must be single-use",
        ],
    },
    "payment": {
        "tests": [
            "Idempotency — retry with same idempotency key must not create duplicate charge",
            "Declined card — must return 402 Payment Required, never 200 or 500",
            "Floating-point precision — $9.99 × 3 stored and returned exactly, no rounding error",
            "Partial refund — cannot exceed original transaction amount; returns 400 if attempted",
            "Timeout resilience — payment timeout leaves order in consistent state, not pending limbo",
            "Currency mismatch — sending amount in wrong currency returns clear 422 error",
        ],
        "security": [
            "Amount tampering — send $0.01 in payload for a $99 item; server must validate server-side",
            "IDOR on invoice IDs — sequential integer IDs allow accessing other users' receipts",
            "Webhook replay — same webhook payload replayed must be rejected via idempotency check",
            "PAN logging — card number must never appear in application logs or error responses",
            "Webhook signature bypass — unsigned or incorrectly signed webhook must be rejected 400",
        ],
    },
    "file": {
        "tests": [
            "MIME validation — .exe renamed to .jpg must be rejected based on magic bytes, not extension",
            "Server-side size limit — 10 MB+ file rejected with 413; client-side check is not enough",
            "Filename sanitization — spaces, path separators, Unicode stripped from stored filename",
            "Concurrent upload — two users uploading same filename handled without collision or overwrite",
            "Corrupt file — truncated or malformed binary returns 400, not 500",
        ],
        "security": [
            "Path traversal — filename ../../etc/passwd must be sanitized or rejected",
            "Polyglot file — JPEG with embedded JS payload; server must not execute on serve",
            "SVG XSS — SVG containing <script> must be sanitized before storage or serving",
            "Zip bomb — deeply nested archive must be rejected before extraction (size check on entry)",
            "Executable disguise — .sh/.bat renamed to .txt still rejected by content-type check",
        ],
    },
    "search": {
        "tests": [
            "Pagination consistency — no duplicate or missing items across page boundaries",
            "Empty query — returns sensible defaults or empty array, never 500",
            "Sort stability — same sort returns same order on repeated identical requests",
            "Scope isolation — user A's search results never include user B's private records",
            "Special characters in query — Unicode, apostrophes, wildcards handled without crash",
        ],
        "security": [
            "NoSQL injection — $where, $regex, $gt operators in query param must be sanitized",
            "IDOR via result IDs — accessing a private record ID returned in search results",
            "ReDoS — crafted regex query must not cause CPU spike or > 2s response time",
            "Full-text DoS — extremely long query string handled gracefully with 400 or truncation",
        ],
    },
    "registration": {
        "tests": [
            "Duplicate email — 409 Conflict returned; not silent success or 500",
            "Email format validation — invalid formats return 400 with specific field error",
            "Verification link — expires after configured TTL; single-use; cannot be reused",
            "Password strength — weak passwords rejected with clear descriptive message",
            "Required fields — missing each required field individually returns 422 with field name",
        ],
        "security": [
            "Email enumeration — registration response must not reveal whether email already exists",
            "Verification token tampering — modified token in URL is rejected with 400",
            "Mass assignment — extra undeclared fields in payload are silently stripped, not persisted",
        ],
    },
    "performance": {
        "tests": [
            "P95 latency under 50 concurrent users stays within SLA (e.g., < 2 s)",
            "Graceful degradation — returns 503 with Retry-After header under extreme load",
            "Memory stability — repeated calls over 5 minutes do not grow process RSS unboundedly",
            "Request timeout — long-running operation times out cleanly with 408 or 504, no hang",
        ],
        "security": [
            "Slowloris — server enforces request-read timeout; partial headers do not hold connection indefinitely",
            "Billion-laughs / XML bomb — deeply expanded entity rejected before parsing completes",
            "Oversized JSON array — 10 000-element payload handled or rejected with 413, not OOM crash",
        ],
    },
}


def _detect_categories(text: str) -> list[str]:
    """Score input against keyword lists; return up to 3 highest-scoring categories."""
    text_lower = text.lower()
    scores: dict[str, int] = {}
    for cat, keywords in _CATEGORY_MAP.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[cat] = score
    return sorted(scores, key=lambda c: scores[c], reverse=True)[:3]


def _build_extras_block(categories: list[str], kind: str) -> str:
    """Build a bullet list of extras for detected categories. kind='tests' or 'security'."""
    lines: list[str] = []
    for cat in categories:
        extras = _CATEGORY_EXTRAS.get(cat, {}).get(kind, [])
        for item in extras:
            lines.append(f"  - [{cat.upper()}] {item}")
    return "\n".join(lines) if lines else "  (none — use generic coverage)"


def bug_analysis_prompt(bug: str, context=None) -> str:
    context_block = (
        f"\nRelevant knowledge-base context:\n{context}\n" if context else ""
    )
    categories = _detect_categories(bug)
    cat_label = ", ".join(c.upper() for c in categories) if categories else "GENERAL"
    extra_tests = _build_extras_block(categories, "tests")
    extra_security = _build_extras_block(categories, "security")

    return f"""You are a senior QA engineer and API security expert.{context_block}

Auto-detected category: {cat_label}

Analyze the following bug thoroughly and return STRICT VALID JSON ONLY.

Bug:
{bug}

STRICT RULES:
- Login/auth bugs MUST be severity = Critical
- Never return 500 as the expected status for invalid credentials
- Use correct HTTP status codes: 200/201 success, 400 bad request, 401 unauthorized,
  403 forbidden, 404 not found, 409 conflict, 422 unprocessable, 429 rate limited, 500 server error
- Root causes must be specific and technical, not generic statements
- Infer realistic API paths and payloads from the bug description
- Every test case MUST have a unique scenario — no duplicates

MANDATORY BASE TEST CASES (at least 10 covering ALL):
1. Happy path / valid input (at least 2 variants)
2. Invalid credentials or wrong input values
3. Empty payload / missing required fields (each field individually)
4. Boundary values (min/max length, special characters, Unicode, whitespace-only)
5. Malformed or non-JSON request body
6. Unauthorized access (missing token, expired token, wrong role)
7. Duplicate or already-existing resource (idempotency)
8. Concurrent / race condition scenario
9. Oversized or stress payload
10. Cross-field validation (e.g., confirm-password mismatch, date-range conflicts)

AUTO-INJECTED CATEGORY-SPECIFIC TEST CASES (add these on top of the base 10):
{extra_tests}

MANDATORY BASE SECURITY PAYLOADS (at least 8):
- SQL Injection (classic and blind variants)
- XSS (reflected and stored)
- NoSQL Injection
- Command Injection
- Path Traversal
- IDOR (Insecure Direct Object Reference)
- Brute Force / Rate Limiting
- JWT tampering or missing auth header

AUTO-INJECTED CATEGORY-SPECIFIC SECURITY PAYLOADS (add these on top):
{extra_security}

MANDATORY: List at least 6 regression areas this bug could affect.

OUTPUT JSON SCHEMA (fill every field with real, specific values):

{{
  "bug": {{
    "description": "<concise description of what the bug is>",
    "severity": "<Critical | High | Medium | Low>",
    "affected_component": "<module, service, or endpoint affected>",
    "detected_category": "{cat_label}"
  }},
  "root_cause": [
    "<specific technical root cause 1>",
    "<specific technical root cause 2>",
    "<specific technical root cause 3>"
  ],
  "expected_behavior": {{
    "<scenario_key>": "<expected HTTP status and response description>",
    "<scenario_key_2>": "<expected HTTP status and response description>"
  }},
  "testCases": [
    {{
      "id": 1,
      "description": "<what this test verifies>",
      "category": "<Positive | Negative | Boundary | Security | Performance>",
      "api": "<HTTP_METHOD /api/path>",
      "headers": {{"Content-Type": "application/json"}},
      "payload": {{}},
      "expectedResponse": {{
        "statusCode": 200,
        "body": {{"<key>": "<expected value or description>"}}
      }}
    }}
  ],
  "securityPayloads": [
    {{
      "type": "<attack type>",
      "target_field": "<which request field to inject>",
      "payload": "<the actual malicious string or value>",
      "expected_behavior": "<what a secure API should return, e.g., 400 Bad Request>"
    }}
  ],
  "regression_areas": [
    "<area 1>", "<area 2>", "<area 3>",
    "<area 4>", "<area 5>", "<area 6>"
  ],
  "fix_suggestion": "<specific, actionable technical fix with implementation details>"
}}

IMPORTANT: Output ONLY valid JSON. No explanation. No markdown. No code fences.
Fill every placeholder with real content derived from the bug description.
"""


def test_case_prompt(feature: str, context=None) -> str:
    context_block = (
        f"\nRelevant knowledge-base context:\n{context}\n" if context else ""
    )
    categories = _detect_categories(feature)
    cat_label = ", ".join(c.upper() for c in categories) if categories else "GENERAL"
    extra_tests = _build_extras_block(categories, "tests")
    extra_security = _build_extras_block(categories, "security")

    return f"""You are a senior QA engineer and API testing expert.{context_block}

Auto-detected category: {cat_label}

Generate COMPREHENSIVE, PROFESSIONAL API test cases for the following feature or bug.

Feature/Bug:
{feature}

STRICT RULES:
- NEVER use 500 as expected result for invalid credentials
- Use correct HTTP status codes: 200/201 success, 400 bad input, 401 unauthorized,
  403 forbidden, 404 not found, 409 conflict, 413 payload too large,
  422 unprocessable, 429 rate limited
- Every test case must be unique — no duplicate scenarios
- Infer realistic API endpoints, payloads, and field names from the description
- Each test case must have actionable steps with specific values

MANDATORY BASE TEST CASES (at least 12):
1.  Valid happy path variant A (typical successful use)
2.  Valid happy path variant B (different valid data set)
3.  Invalid credentials or wrong input
4.  Missing required field — test each key field individually
5.  Empty string vs null value for required fields
6.  Boundary values — max length, min length, special characters, Unicode
7.  Malformed / non-JSON request body
8.  Missing or invalid auth token
9.  Expired or revoked session / token
10. Duplicate resource creation (idempotency / conflict)
11. Concurrent request race condition
12. SQL injection attempt
13. XSS injection attempt
14. Rate limiting / brute force (429 after N rapid requests)
15. Oversized payload

AUTO-INJECTED CATEGORY-SPECIFIC TEST CASES (add on top):
{extra_tests}

AUTO-INJECTED CATEGORY-SPECIFIC SECURITY TESTS (add on top):
{extra_security}

Return ONLY a JSON array — no explanation, no markdown, no code fences.

FORMAT — every element must have all these fields:
[
  {{
    "id": "TC-001",
    "title": "<specific test title describing exactly what is being tested>",
    "priority": "<Critical | High | Medium | Low>",
    "type": "<Positive | Negative | Boundary | Security | Performance>",
    "api": "<HTTP_METHOD /api/path>",
    "steps": [
      "<step 1: specific action with actual values>",
      "<step 2: what to observe or assert>"
    ],
    "expected": {{
      "status": 200,
      "response": "<specific description of expected response body or field values>"
    }}
  }}
]
"""