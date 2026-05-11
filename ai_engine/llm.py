import os
import logging
from openai import AsyncOpenAI
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

logger = logging.getLogger(__name__)

client = AsyncOpenAI(
    api_key=os.environ.get("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
_SYSTEM_PROMPT = "You are a senior QA engineer and API testing expert."


async def ask_ai(prompt: str) -> str:
    try:
        logger.info(f"LLM call — model={MODEL}, prompt_chars={len(prompt)}")
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
        )
        content = response.choices[0].message.content
        logger.info(f"LLM response — chars={len(content)}")
        return content
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")