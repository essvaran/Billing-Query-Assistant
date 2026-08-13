import os

import requests
from dotenv import load_dotenv

load_dotenv()

# Set LLM_PROVIDER=groq in .env to use Groq, otherwise defaults to Ollama.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = os.getenv("LLM_MODEL", "llama-3.1-8b-instant")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("LLM_MODEL", "llama3.2:latest")


class LLMRequestError(Exception):
    pass


def ask_llm(system_prompt: str, user_prompt: str) -> str:
    if LLM_PROVIDER == "groq":
        return _ask_groq(system_prompt, user_prompt)
    return _ask_ollama(system_prompt, user_prompt)


def _ask_groq(system_prompt: str, user_prompt: str) -> str:
    if not GROQ_API_KEY:
        raise LLMRequestError(
            "GROQ_API_KEY is not set. Add it to your .env file."
        )

    url = f"{GROQ_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.0,
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise LLMRequestError(
            f"Groq API request failed (model='{GROQ_MODEL}'). "
            f"Check your GROQ_API_KEY and network. Original error: {exc}"
        ) from exc

    return response.json()["choices"][0]["message"]["content"].strip()


def _ask_ollama(system_prompt: str, user_prompt: str) -> str:
    url = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.0},
    }

    try:
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise LLMRequestError(
            f"Could not reach Ollama at {OLLAMA_BASE_URL} with model "
            f"'{OLLAMA_MODEL}'. Is `ollama serve` running and has the model "
            f"been pulled (`ollama pull {OLLAMA_MODEL}`)? Original error: {exc}"
        ) from exc

    return response.json()["message"]["content"].strip()
