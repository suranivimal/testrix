# Testrix — AI-Powered QA Automation Platform

![Python](https://img.shields.io/badge/Python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-green)
![Groq](https://img.shields.io/badge/LLM-Groq%20LLaMA%203.3%20%2B%20Vision-orange)
![MongoDB](https://img.shields.io/badge/Database-MongoDB-brightgreen)
![Playwright](https://img.shields.io/badge/Browser-Playwright-blueviolet)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Status](https://img.shields.io/badge/Status-Active-success)

Testrix is an AI-powered QA automation platform that eliminates manual effort from bug analysis, test case writing, and visual regression testing. Describe a bug or paste a Shopify + Figma URL — Testrix handles the rest.

---

## Demo

> Dashboard screenshot — `ui/index.html` running locally.

![Dashboard](ui/screenshot.png)

---

## Features

- **Bug Analysis** — root cause, severity, and fix suggestions powered by LLM + RAG
- **Test Case Generation** — positive, negative, edge cases, and security payloads (SQLi, XSS, rate limits)
- **Visual QA** — pixel diff between Figma design frames and live Shopify pages, with AI-generated issue reports and severity scores
- **Playwright Test Runner** — execute generated test cases against any live base URL
- **History** — every analysis saved to MongoDB and reloadable from the dashboard

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Uvicorn |
| LLM (text) | Groq — LLaMA 3.3 70B |
| LLM (vision) | Groq — LLaMA 3.2 11B Vision |
| Vector Store | FAISS + HuggingFace Sentence-Transformers |
| Browser Automation | Playwright |
| Database | MongoDB |
| Frontend | Vanilla HTML/CSS/JS |

---

## Prerequisites

Before you begin, make sure you have:

- Python 3.13+
- MongoDB running locally or a [MongoDB Atlas](https://www.mongodb.com/atlas) account
- A [Groq API key](https://console.groq.com) (free tier works)
- A [Figma Personal Access Token](https://www.figma.com/settings) (only needed for Visual QA)

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/suranivimal/testrix.git
cd testrix
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Configure environment

```bash
cp .env.example .env
```

Then open `.env` and fill in your keys:

```env
GROQ_API_KEY=gsk_your_key_here
FIGMA_API_TOKEN=your_figma_token_here
MONGODB_URI=mongodb://localhost:27017
```

| Variable | Required | Where to get it |
|----------|----------|-----------------|
| `GROQ_API_KEY` | Yes | [console.groq.com](https://console.groq.com) → API Keys |
| `FIGMA_API_TOKEN` | For Visual QA | Figma → Settings → Personal Access Tokens |
| `MONGODB_URI` | Yes | Atlas URI or `mongodb://localhost:27017` |

### 4. Run

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
| `POST` | `/visual-qa` | Start Visual QA job (async, returns `job_id`) |
| `GET` | `/visual-qa/{job_id}` | Poll job status and results |
| `GET` | `/history` | List recent analyses |

---

## Production Notes

This project is built for local and demo use. Before any public deployment:

- Set `CORS_ORIGINS` to your specific domain instead of `*`
- Add authentication — all endpoints are currently open
- Run behind a reverse proxy (nginx, Caddy) with HTTPS
- Never commit your `.env` file — it is already in `.gitignore`

---

## Contributing

Contributions are welcome. To get started:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes and open a pull request

Please keep PRs focused — one feature or fix per PR.

---

## Author

**Vimal Surani** — built Testrix as an AI-first approach to QA automation.

Feel free to open an issue or reach out via GitHub.

---

## License

This project is licensed under the [MIT License](LICENSE).