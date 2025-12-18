import os
import json
import requests
from dotenv import load_dotenv

from llm.models import MODEL
from llm.prompts import CHAT_SYSTEM_PROMPT

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

def route_user_input(user_text: str) -> dict:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": CHAT_SYSTEM_PROMPT},
            {"role": "user", "content": user_text}
        ],
        "temperature": 0.3,
        "max_tokens": 300
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8501",
        "X-Title": "BusinessIQ Finder"
    }

    r = requests.post(
        OPENROUTER_URL,
        headers=headers,
        json=payload,
        timeout=30
    )

    r.raise_for_status()
    answer = r.json()["choices"][0]["message"]["content"]

    return {
        "intent": "chat",
        "sql": None,
        "response": answer
    }
