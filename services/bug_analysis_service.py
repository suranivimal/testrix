from ai_engine.llm import ask_ai
from rag.vector_store import search_context

def analyze_bug(bug):
    context = search_context(bug)

    prompt = f"""
    You are a senior QA engineer.

    Use the below context to provide a better bug analysis.

    Context:
    {context}

    Bug: {bug}

    Provide:
    - Possible root cause
    - Severity
    - Fix suggestion
    """

    return ask_ai(prompt)