import json
from ai_engine.llm import ask_ai


def extract_json(content: str):
    """
    Extract JSON safely from AI response (handles plain JSON + ```json blocks)
    """
    try:
        # Remove markdown if present
        if "```" in content:
            content = content.split("```")[1]

        start = content.find("{")
        end = content.rfind("}") + 1
        return json.loads(content[start:end])

    except Exception:
        return None


def analyze_bug(bug):
    prompt = f"""
You are a senior QA engineer and API testing expert.

Analyze the bug and return STRICT VALID JSON ONLY.

Bug:
{bug}

STRICT RULES:
- Login/auth bugs MUST be severity = Critical
- Never return 500 for invalid credentials
- Use correct HTTP codes:
  - 401 → invalid credentials
  - 400 → invalid payload
  - 200 → success
- Root cause must be specific technical reason (not generic)

MANDATORY TEST CASES (minimum 4):
1. Valid login
2. Invalid credentials
3. Empty payload
4. Malformed JSON

Use endpoint:
POST /api/login

OUTPUT JSON FORMAT:

{{
  "bug": {{
    "description": "...",
    "severity": "Critical"
  }},
  "root_cause": [
    "Unhandled exception when credentials invalid",
    "Missing validation mapping to 401 response"
  ],
  "expected_behavior": {{
    "invalid_credentials": "401 Unauthorized",
    "invalid_payload": "400 Bad Request"
  }},
  "testCases": [
    {{
      "id": 1,
      "description": "Valid login",
      "api": "POST /api/login",
      "payload": {{"username": "user", "password": "pass"}},
      "expectedResponse": {{
        "statusCode": 200,
        "body": {{"token": "<jwt_token>"}}
      }}
    }},
    {{
      "id": 2,
      "description": "Invalid credentials",
      "api": "POST /api/login",
      "payload": {{"username": "user", "password": "wrong"}},
      "expectedResponse": {{
        "statusCode": 401,
        "body": {{"error": "Invalid username or password"}}
      }}
    }},
    {{
      "id": 3,
      "description": "Empty payload",
      "api": "POST /api/login",
      "payload": {{}},
      "expectedResponse": {{
        "statusCode": 400
      }}
    }},
    {{
      "id": 4,
      "description": "Malformed JSON",
      "api": "POST /api/login",
      "payload": "invalid_json",
      "expectedResponse": {{
        "statusCode": 400
      }}
    }}
  ],
  "securityPayloads": [
    {{
      "type": "SQL Injection",
      "payload": "' OR 1=1 --"
    }},
    {{
      "type": "XSS",
      "payload": "<script>alert(1)</script>"
    }},
    {{
      "type": "Rate Limit",
      "description": "Send >100 requests/sec → expect 429"
    }}
  ],
  "regression_areas": [
    "Authentication",
    "Session management",
    "Password reset",
    "Signup API"
  ],
  "fix_suggestion": "Return 401 for invalid credentials, validate input, and handle exceptions properly"
}}

IMPORTANT:
- Output ONLY JSON
- No explanation
- No markdown
"""

    response = ask_ai(prompt)

    try:
        # Case 1: already dict
        if isinstance(response, dict):
            return response

        # Case 2: string → extract JSON
        if isinstance(response, str):
            parsed = extract_json(response)
            if parsed:
                return parsed

    except Exception:
        pass

    return {
        "error": "Invalid JSON from AI",
        "type": str(type(response)),
        "raw": response
    }