# Testrix — AI-Powered QA Automation Platform

![Python](https://img.shields.io/badge/Python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-green)
![Groq](https://img.shields.io/badge/LLM-Groq%20LLaMA%203.3%20%2B%20Vision-orange)
![MongoDB](https://img.shields.io/badge/Database-MongoDB-brightgreen)
![Playwright](https://img.shields.io/badge/Browser-Playwright-blueviolet)
![Status](https://img.shields.io/badge/Status-Active-success)

Testrix is an AI-powered QA automation platform. It analyzes bugs, generates test cases, and compares Figma designs against live Shopify storefronts — all powered by Groq LLaMA.

---

## Features

- **Bug Analysis** — root cause, severity, fix suggestions via LLM + RAG
- **Test Case Generation** — positive, negative, edge cases, and security payloads
- **Visual QA** — pixel diff between Figma designs and live Shopify pages, with AI-generated issue reports
- **Playwright Test Runner** — execute generated test cases against a live URL
- **History** — every analysis saved to MongoDB, reloadable from the dashboard

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Uvicorn |
| LLM | Groq — LLaMA 3.3 70B (text) + LLaMA 3.2 Vision (images) |
| Vector Store | FAISS + HuggingFace Sentence-Transformers |
| Browser | Playwright |
| Database | MongoDB |
| Frontend | Vanilla HTML/CSS/JS |

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure environment

Create a `.env` file in the project root:

```env
GROQ_API_KEY=gsk_your_key_here
FIGMA_API_TOKEN=your_figma_token_here
MONGODB_URI=mongodb://localhost:27017
```

| Variable | Required | Where to get it |
|----------|----------|-----------------|
| `GROQ_API_KEY` | Yes | [console.groq.com](https://console.groq.com) → API Keys |
| `FIGMA_API_TOKEN` | For Visual QA | Figma → Settings → Personal Access Tokens |
| `MONGODB_URI` | Yes | MongoDB Atlas URI or `mongodb://localhost:27017` |

### 3. Run

```bash
uvicorn app:app --reload
```

- Dashboard: `http://localhost:8000/ui/index.html`
- API docs: `http://localhost:8000/docs`

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check |
| `POST` | `/qa-ai` | Bug analysis + test case generation |
| `POST` | `/qa-ai/stream` | Same, SSE streaming |
| `POST` | `/run-tests` | Execute test cases via Playwright |
| `POST` | `/visual-qa` | Start Visual QA job (async) |
| `GET` | `/visual-qa/{job_id}` | Poll job status and results |
| `GET` | `/history` | List recent analyses |

---

## License

MIT License