import json
from ai_engine.llm import ask_ai
from rag.vector_store import search_context


def extract_json_array(content: str):
    """
    Safely extract JSON array from AI response
    """
    try:
        # Remove markdown if present
        if "```" in content:
            content = content.split("```")[1]

        start = content.find("[")
        end = content.rfind("]") + 1
        return json.loads(content[start:end])

    except Exception:
        return None


def generate_test_cases(feature):
    # 🔍 Step 1: RAG Context
    context = search_context(feature)

    # 🧠 Step 2: Prompt
    prompt = f"""
You are a senior QA engineer.

Use the below context to generate PROFESSIONAL API test cases.

Context:
{context}

Feature:
{feature}

STRICT RULES:
- NEVER use 500 as expected result for invalid credentials
- Use:
  - 401 → invalid credentials
  - 400 → invalid payload
  - 200 → success

- Always generate at least 4 test cases:
  1. Valid login
  2. Invalid credentials
  3. Empty payload
  4. Malformed JSON

Return ONLY JSON array (no explanation).

FORMAT:

[
  {{
    "id": "TC-001",
    "title": "Valid login",
    "priority": "High",
    "type": "Positive",
    "steps": [
      "Send POST /api/login with valid credentials"
    ],
    "expected": {{
      "status": 200,
      "response": "token returned"
    }}
  }},
  {{
    "id": "TC-002",
    "title": "Invalid credentials",
    "priority": "High",
    "type": "Negative",
    "steps": [
      "Send POST /api/login with wrong password"
    ],
    "expected": {{
      "status": 401,
      "response": "Invalid username or password"
    }}
  }}
]
"""

    # 🤖 Step 3: AI Call
    response = ask_ai(prompt)

    # 🔥 Step 4: Safe JSON Parsing
    try:
        # ✅ Case 1: already list
        if isinstance(response, list):
            return response

        # ✅ Case 2: dict with raw_output
        if isinstance(response, dict):
            raw = response.get("raw_output")

            if isinstance(raw, str):
                parsed = extract_json_array(raw)
                if parsed:
                    return parsed

            return response  # fallback

        # ✅ Case 3: string
        if isinstance(response, str):
            parsed = extract_json_array(response)
            if parsed:
                return parsed

    except Exception:
        pass

    # ❌ fallback
    return {
        "error": "Invalid JSON from AI",
        "raw_output": response
    }