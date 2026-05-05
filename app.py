from fastapi import FastAPI
from pydantic import BaseModel

# Existing services
from services.test_case_service import generate_test_cases
from services.bug_analysis_service import analyze_bug as basic_bug_analysis

# Agent-based system
from agents.bug_agent import analyze_bug as agent_analyze_bug
from agents.agent_manager import run_qa_ai

# Middleware & Static files
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI()


# 🌐 CORS (for UI + API communication)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 📁 Serve UI folder
app.mount("/ui", StaticFiles(directory="ui"), name="ui")


# 📦 Request Models
class FeatureRequest(BaseModel):
    feature: str


class BugRequest(BaseModel):
    bug: str


class QARequest(BaseModel):
    input_text: str


# 🏠 Health Check
@app.get("/")
def home():
    return {"message": "Testrix Running 🚀"}


# 🧪 Test Case Generation (optional)
@app.post("/test-cases")
def test_cases(request: FeatureRequest):
    result = generate_test_cases(request.feature)
    return {"result": result}


# 🐞 Basic Bug Analysis (optional)
@app.post("/bug-analysis")
def bug_analysis(request: BugRequest):
    result = basic_bug_analysis(request.bug)
    return {"result": result}


# 🤖 Advanced Bug Analysis (Agent-based)
@app.post("/analyze-bug")
def analyze_bug_api(request: BugRequest):
    result = agent_analyze_bug(request.bug)
    return {"result": result}


# 🚀 MAIN AI SYSTEM (USE THIS)
@app.post("/qa-ai")
def qa_ai_api(request: QARequest):
    result = run_qa_ai(request.input_text)
    return {"result": result}