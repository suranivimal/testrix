# 🚀 Testrix — AI QA Intelligence Platform

![Python](https://img.shields.io/badge/Python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-green)
![AI](https://img.shields.io/badge/AI-LLM-orange)
![Status](https://img.shields.io/badge/Status-Active-success)

---

## 🧠 Overview

Testrix is an **AI-powered QA system** designed to automate and enhance software testing workflows using:

* 🤖 AI (LLM-based reasoning)
* 🔍 RAG (context-aware analysis)
* 🧩 Agent-based architecture

It transforms QA from **manual effort → intelligent decision-making**.

---

## 📸 Dashboard Preview

![Dashboard](ui/screenshot.png)

---

## ⚡ Key Capabilities

### 🐞 Bug Intelligence

* Root cause analysis
* Severity detection
* Fix recommendations

### 🧪 Test Automation (AI-generated)

* Positive test cases
* Negative scenarios
* Edge cases

### 🔐 Security Testing

* SQL Injection detection
* XSS payload testing
* Rate limit validation

### 🧠 Smart Context (RAG)

* Uses previous bugs/logs
* Improves accuracy dynamically

---

## 🚀 Demo Flow

### Input:

```text
Login API returns 500 error on invalid credentials
```

### Output:

* Severity: Critical
* Root Cause: Error handling issue
* API Test Cases
* Security payloads
* Fix suggestions

---

## 🏗️ System Architecture

```
User Input
   ↓
Agent Manager
   ↓
--------------------------
| Bug Agent              |
| Test Case Agent        |
| Security Agent         |
--------------------------
   ↓
LLM (Groq/OpenAI)
   ↓
Structured JSON Output
   ↓
Dashboard UI
```

---

## 🛠️ Tech Stack

| Layer        | Technology        |
| ------------ | ----------------- |
| Backend      | FastAPI (Python)  |
| AI Engine    | LLM (Groq/OpenAI) |
| RAG          | Vector Search     |
| Frontend     | HTML + JS         |
| Architecture | Agent-based       |

---

## 📂 Project Structure

```
testrix/
│
├── agents/              # AI agents (bug, test cases)
├── ai_engine/           # LLM integration
├── rag/                 # context + vector DB
├── services/            # core logic
├── ui/                  # dashboard UI
├── app.py               # FastAPI entry
├── requirements.txt
├── README.md
└── .gitignore
```

---

## ⚙️ Installation & Setup

### 1. Clone repository

```bash
git clone https://github.com/suranivimal/testrix.git
cd testrix
```

---

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

---

### 3. Setup environment

Create `.env` file:

```env
GROQ_API_KEY=your_api_key_here
```

---

### 4. Run application

```bash
uvicorn app:app --reload
```

---

## 🌐 Access Points

| Service      | URL                                 |
| ------------ | ----------------------------------- |
| API Docs     | http://127.0.0.1:8000/docs          |
| Dashboard UI | http://127.0.0.1:8000/ui/index.html |

---

## 🧪 Example API Usage

```bash
POST /qa-ai
```

```json
{
  "input_text": "Login API returns 500 error"
}
```

---

## 🔮 Roadmap

* 🔐 Authentication (multi-user SaaS)
* 🗂️ Bug/Test history storage (MongoDB)
* ⚙️ CI/CD integration
* 🤖 Playwright automation execution
* ☁️ Cloud deployment (Render / Railway)

---

## 💡 Why Testrix?

| Traditional QA   | Testrix                 |
| ---------------- | ----------------------- |
| Manual testing   | AI-driven insights      |
| Static scripts   | Dynamic test generation |
| Slow debugging   | Instant root cause      |
| Limited coverage | Smart coverage          |

---

## 👨‍💻 Author

**Vimal Surani**

---

## ⭐ Support

If you like this project:

👉 Star the repo
👉 Share with others

---

## 📜 License

MIT License
