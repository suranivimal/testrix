# Testrix — AI-Powered QA Automation System

## Project Overview

Testrix is an AI-powered QA automation platform that analyzes bug descriptions, generates comprehensive API test cases, and provides security testing payloads. It uses Groq's LLaMA 3.3 70B model with RAG (Retrieval-Augmented Generation) for context-aware analysis.

## Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.x |
| Web Framework | FastAPI + Uvicorn |
| LLM Provider | Groq API (LLaMA 3.3 70B) |
| Vector Store | FAISS + HuggingFace Sentence-Transformers |
| Frontend | Vanilla HTML/CSS/JS (single-page app) |

## Project Structure

```
testrix/
├── app.py                        # FastAPI entry point, all API routes
├── requirements.txt              # Python dependencies
├── .env                          # GROQ_API_KEY (not committed)
│
├── agents/
│   ├── agent_manager.py         # Orchestrates bug + test case flow
│   └── bug_agent.py             # Bug analysis with structured JSON output
│
├── ai_engine/
│   ├── llm.py                   # Groq API wrapper (OpenAI-compatible)
│   └── prompts.py               # Reusable LLM prompt templates
│
├── services/
│   ├── bug_analysis_service.py  # RAG-enhanced bug analysis
│   └── test_case_service.py     # RAG-enhanced test case generation
│
├── rag/
│   ├── data_loader.py           # Loads domain knowledge from /data
│   └── vector_store.py          # FAISS vector store, lazy-loaded & cached
│
├── data/
│   ├── bugs.txt                 # Known bugs (RAG training data)
│   └── test_cases.txt           # Example test case templates
│
└── ui/
    └── index.html               # Frontend SPA
```

## Running the Project

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variable
# Create .env with: GROQ_API_KEY=<your_key>

# Start the server
uvicorn app:app --reload
```

The frontend is served statically at `http://localhost:8000/ui/index.html`.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check |
| `POST` | `/qa-ai` | **Main endpoint** — combined bug analysis + test case generation |
| `POST` | `/analyze-bug` | Agent-based bug analysis only |
| `POST` | `/test-cases` | Legacy test case generation |
| `POST` | `/bug-analysis` | Legacy basic bug analysis |

### Main Request/Response (`POST /qa-ai`)

**Request:**
```json
{ "input": "Login fails when password contains special characters" }
```

**Response:**
```json
{
  "input": "...",
  "bug_analysis": {
    "bug": {},
    "root_cause": [],
    "expected_behavior": {},
    "testCases": [],
    "securityPayloads": [],
    "regression_areas": [],
    "fix_suggestion": ""
  },
  "test_cases": []
}
```

## Data Flow

```
User Input
    └── Agent Manager (agent_manager.py)
         ├── Bug Agent → LLM → JSON extraction → bug_analysis
         └── Test Case Service → RAG search → LLM with context → test_cases
```

## Key Architecture Decisions

- **CORS** is open (`allow_origins=["*"]`) — frontend-first design, not hardened for production.
- **LLM model**: `llama-3.3-70b-versatile` via Groq's OpenAI-compatible endpoint.
- **RAG retrieval**: Top-2 similarity results from FAISS, seeded from `data/bugs.txt` and `data/test_cases.txt`.
- **Vector store**: Lazy-loaded on first request and cached in memory.
- **System prompt**: LLM is prompted as "a senior QA engineer".
- **JSON extraction**: LLM outputs are parsed with regex fallback to handle markdown-wrapped JSON blocks.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GROQ_API_KEY` | API key for Groq LLM service |

## No Test Framework

There are no unit or integration tests. The system relies on LLM-generated outputs and RAG context from `data/`. To expand test coverage, `pytest` with mocked LLM responses is the recommended path.

## Known Limitations

- CORS allows all origins — restrict before any production deployment.
- API key is stored in `.env`; ensure `.env` is in `.gitignore`.
- No rate limiting on endpoints.
- No authentication on the API.
- LLM responses can occasionally fail JSON parsing; the fallback returns raw text.

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore