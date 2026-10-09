import os
from typing import List, Optional
import httpx
from pydantic import BaseModel

GEMINI_MODEL = "gemini-3.8-flash"
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def get_api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


async def generate_gemini(prompt: str, system_instruction: str = "") -> str:
    key = get_api_key()
    if not key:
        raise ValueError("GEMINI_API_KEY is not configured")
    
    url = f"{API_BASE}/{GEMINI_MODEL}:generateContent?key={key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    if system_instruction:
        payload["system_instruction"] = {"parts": [{"text": system_instruction}]}
        
    async with httpx.AsyncClient(timeout=25.0) as client:
        r = await client.post(url, json=payload)
        if r.status_code != 200:
            raise RuntimeError(f"Gemini API error ({r.status_code}): {r.text[:200]}")
        data = r.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError):
            return "No response generated."


async def generate_questions(role: str = "Software Engineer", interview_type: str = "Coding", level: str = "Standard") -> List[str]:
    prompt = f"Generate 3 concise interview questions for a {level} level {role} ({interview_type}). Return only a JSON array of 3 string questions with no markdown wrappers."
    system = "You are an expert technical interviewer. Output valid JSON array only."
    raw = await generate_gemini(prompt, system)
    import json
    try:
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        items = json.loads(clean)
        if isinstance(items, list) and len(items) > 0:
            return [str(x) for x in items]
    except Exception:
        pass
    return [
        "Explain how you design scalable and secure distributed services.",
        "Describe a challenging bug you debugged and your step-by-step resolution.",
        "How do you ensure zero-trust security and data privacy in production applications?"
    ]


async def evaluate_code(code: str, language: str = "JavaScript", problem: str = "") -> dict:
    prompt = f"""Evaluate this {language} code solution for the problem: '{problem}'.
Code:
```
{code}
```
Provide a helpful concise assessment:
1. Correctness (Pass/Fail/Partial)
2. Edge cases handled
3. Time and Space complexity
4. Brief suggestion for improvement
Keep it friendly and under 150 words."""
    feedback = await generate_gemini(prompt, "You are a senior tech lead reviewing code.")
    return {"feedback": feedback}
