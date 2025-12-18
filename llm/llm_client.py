# llm_client.py
import requests
import json
import os
import time
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Load multiple API keys
raw_keys = (
    os.getenv("OPEN_ROUTER_API_KEY")
    or os.getenv("OPEN_ROUTER_API_KEY")
    or ""
)

API_KEYS = [k.strip() for k in raw_keys.split(",") if k.strip()]

if not API_KEYS:
    raise RuntimeError("No OpenRouter API keys found")

def call_llm(messages, model, max_retries=2):
    last_error = None

    for _ in range(max_retries):
        for key in API_KEYS:
            try:
                response = requests.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "http://localhost",
                        "X-Title": "HBD-Local-Business-AI"
                    },
                    json={
                        "model": model,
                        "messages": messages
                    },
                    timeout=30
                )

                # 🔴 LOG REAL ERROR FROM OPENROUTER
                if response.status_code != 200:
                    print("OPENROUTER ERROR STATUS:", response.status_code)
                    print("OPENROUTER ERROR BODY:", response.text)

                if response.status_code == 429:
                    continue

                response.raise_for_status()
                return response.json()["choices"][0]["message"]

            except requests.exceptions.HTTPError as e:
                last_error = e
                if response.status_code in (400, 401):
                    # These will NEVER succeed on retry
                    raise RuntimeError(
                        f"OpenRouter rejected request: {response.text}"
                    )
                continue

            except requests.exceptions.RequestException as e:
                last_error = e
                continue

    raise RuntimeError(f"LLM call failed after retries: {last_error}")
