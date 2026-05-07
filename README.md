# Testrix — AI-Powered QA Automation Platform

![Python](https://img.shields.io/badge/Python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-green)
![Groq](https://img.shields.io/badge/LLM-Groq%20LLaMA%203.3%20%2B%20Vision-orange)
![MongoDB](https://img.shields.io/badge/Database-MongoDB-brightgreen)
![Playwright](https://img.shields.io/badge/Browser-Playwright-blueviolet)
![Status](https://img.shields.io/badge/Status-Active-success)

Testrix is an AI-powered QA automation platform that combines bug analysis, test case generation, security testing, and visual regression testing (Figma vs live Shopify) into a single system. All AI inference runs on Groq — no Anthropic or OpenAI keys needed.

---

## Features

### Bug Intelligence
- Root cause analysis with structured JSON output
- Severity detection and fix recommendations
- RAG-enhanced context from historical bugs (FAISS vector store)

### AI Test Case Generation
- Positive, negative, and edge case scenarios
- API test cases with HTTP method, headers, body, and expected response
- Security payloads: SQL injection, XSS, rate limit testing

### Playwright Test Runner
- Executes generated test cases against a live base URL
- Configurable timeout and optional auth token

### Visual QA — Figma vs Live Shopify (all 11 steps complete)
Async job-based pipeline: submit URLs, poll for results.

1. **Job creation** — MongoDB document created (`status: pending`)
2. **Parallel fetch** — Figma frames (REST API) + Shopify screenshots (Playwright) run concurrently
3. **Figma extraction** — parses 7+ URL formats, exports frames as PNG @2x via Figma REST API
4. **Shopify scraping** — SSRF-safe URL validator, Playwright sync in thread pool, `full_page=False` viewport-only screenshots @2x (avoids font-load timeouts)
5. **Image normalisation** — both images resized to 1440px canonical width before diff
6. **Pixel diff** — Pillow-based diff, BFS region detection, annotated diff image
7. **AI analysis** — Groq vision (`llama-3.2-11b-vision-preview`) called once per page with all regions batched
8. **Severity classification** — rule-based fast pass (Critical/Low trusted directly); LLM called only for borderline Medium/High
9. **Report assembly** — per-page reports + full report; base64 images returned to UI but stripped from MongoDB copy
10. **Job completion** — MongoDB updated to `status: complete` with full result
11. **UI rendering** — KPI row, per-page tabs, 3-panel viewer (Figma / Live / Diff), issue cards with severity badges, lightbox, JSON export

### History
- Every analysis auto-saved to MongoDB
- Reload any past result from the dashboard

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.13 |
| Web Framework | FastAPI + Uvicorn |
| LLM (text) | Groq — `llama-3.3-70b-versatile` |
| LLM (vision) | Groq — `llama-3.2-11b-vision-preview` |
| Vector Store | FAISS + HuggingFace Sentence-Transformers |
| Browser Automation | Playwright sync (thread pool) |
| Image Processing | Pillow |
| Database | MongoDB (pymongo) |
| Frontend | Vanilla HTML/CSS/JS SPA |

---

## Project Structure

```
testrix/
├── app.py                          # FastAPI entry point, all API routes
├── db.py                           # MongoDB: history + visual_qa_jobs collections
├── requirements.txt
├── .env                            # API keys (not committed)
├── .env.example                    # Key reference template
│
├── agents/
│   ├── agent_manager.py            # Orchestrates bug + test case flow (parallel)
│   ├── bug_agent.py                # Bug analysis → structured JSON
│   └── visual_qa_agent.py          # Visual QA pipeline orchestrator (11 steps)
│
├── ai_engine/
│   ├── llm.py                      # Groq AsyncOpenAI wrapper
│   ├── prompts.py                  # Reusable LLM prompt templates
│   └── utils.py                    # JSON extraction helpers
│
├── services/
│   ├── bug_analysis_service.py     # RAG-enhanced bug analysis
│   ├── test_case_service.py        # RAG-enhanced test case generation
│   ├── test_runner.py              # Playwright API test runner
│   ├── figma_extractor.py          # Figma REST API — fetch + export frames @2x
│   ├── shopify_scraper.py          # Playwright sync scraper (thread-safe, SSRF-safe)
│   ├── visual_comparator.py        # Pillow pixel diff + BFS region detection
│   ├── visual_ai_analyzer.py       # Groq vision — batched region analysis per page
│   ├── severity_classifier.py      # Rule-based + LLM severity scoring
│   └── bug_report_generator.py     # Page + full report builder
│
├── rag/
│   ├── data_loader.py              # Loads domain knowledge from /data
│   └── vector_store.py             # FAISS vector store, lazy-loaded & cached
│
├── data/
│   ├── bugs.txt                    # Known bugs (RAG training data)
│   └── test_cases.txt              # Example test case templates
│
└── ui/
    └── index.html                  # Frontend SPA (Bug QA + Visual QA tabs)
```

---

## Setup

### Step 1 — Clone and install dependencies

```bash
git clone https://github.com/suranivimal/testrix.git
cd testrix
pip install -r requirements.txt
```

### Step 2 — Install Playwright browser

```bash
playwright install chromium
```

> Required for Visual QA. The pip package alone does not include the browser binary.

### Step 3 — Configure environment

Copy `.env.example` to `.env` and fill in your keys:

```env
GROQ_API_KEY=gsk_your_key_here
GROQ_MODEL=llama-3.3-70b-versatile
FIGMA_API_TOKEN=your_figma_token_here
MONGODB_URI=mongodb://localhost:27017
CORS_ORIGINS=*
```

| Variable | Required | Where to get it |
|----------|----------|-----------------|
| `GROQ_API_KEY` | Yes | [console.groq.com](https://console.groq.com) → API Keys |
| `GROQ_MODEL` | No | Defaults to `llama-3.3-70b-versatile` |
| `FIGMA_API_TOKEN` | For Visual QA | Figma → Settings → Personal Access Tokens |
| `MONGODB_URI` | Yes | MongoDB Atlas connection string or `mongodb://localhost:27017` |
| `CORS_ORIGINS` | No | Defaults to `*` — restrict before production |

### Step 4 — Start the server

```bash
uvicorn app:app --reload
```

Verify it started:
```bash
curl http://localhost:8000/
# {"message":"Testrix Running","version":"2.0.0"}
```

### Step 5 — Open the dashboard

```
http://localhost:8000/ui/index.html
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check |
| `POST` | `/qa-ai` | Bug analysis + test case generation |
| `POST` | `/qa-ai/stream` | Same, SSE streaming |
| `POST` | `/run-tests` | Execute test cases via Playwright |
| `POST` | `/visual-qa` | Start Visual QA job — returns `job_id` (202) |
| `GET` | `/visual-qa/{job_id}` | Poll job status and results |
| `GET` | `/history` | List recent analyses |
| `GET` | `/history/{id}` | Fetch single history record |
| `DELETE` | `/history/{id}` | Delete history record |

### POST /qa-ai

```json
{ "input_text": "Login fails when password contains special characters" }
```

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
  "test_cases": [],
  "history_id": "..."
}
```

### POST /visual-qa

```json
{
  "shopify_url": "https://your-store.myshopify.com",
  "figma_url": "https://www.figma.com/design/FILE_KEY/...",
  "pages": ["home", "product", "collection", "cart"],
  "shopify_password": null,
  "diff_threshold": 0.05
}
```

Returns `{ "job_id": "...", "status": "pending" }`.
Poll `GET /visual-qa/{job_id}` every 2 s — status progresses `pending → running → complete | failed`.

---

## Visual QA Pipeline

```
POST /visual-qa
    └── Create MongoDB job (pending)
         └── BackgroundTask: run_visual_qa()
              ├── [parallel] Figma REST API → extract frames + download PNGs @2x
              ├── [parallel] Playwright (thread pool) → screenshot each Shopify page
              ├── Normalise both images to 1440px width
              ├── Pillow pixel diff → BFS region detection
              ├── Groq vision → analyse all regions in one call per page
              ├── Rule-based + LLM severity classification per issue
              ├── Build page reports + full report
              └── Save to MongoDB (complete) — base64 images in response, stripped from DB

GET /visual-qa/{job_id}  →  live progress + final result
```

---

## Data Flow — Bug Analysis

```
User Input
    └── Agent Manager (parallel asyncio.gather)
         ├── Bug Agent → Groq LLaMA 3.3 → JSON extraction → bug_analysis
         └── Test Case Service → FAISS RAG (top-2) → Groq with context → test_cases
              └── Both results saved to MongoDB history
```

---

## Known Limitations

- CORS allows all origins — set `CORS_ORIGINS` to your domain before production.
- No authentication on any endpoint.
- Playwright Visual QA runs sync in a thread pool — concurrent jobs share the default thread pool.
- LLM responses occasionally fail JSON parsing; regex fallback returns raw text.
- Rate limits: 10 req/min on `/qa-ai` and `/visual-qa`, 20 req/min on legacy endpoints.

---

## License

MIT License