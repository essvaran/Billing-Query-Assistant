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


def ask_llm(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
) -> tuple[str, int, int]:
    """Returns (text, input_tokens, output_tokens).

    Pass ``model`` to override the default configured model — used by replay
    to ensure the same model that generated the original trace is re-used.
    """
    if LLM_PROVIDER == "groq":
        return _ask_groq(system_prompt, user_prompt, model or GROQ_MODEL)
    return _ask_ollama(system_prompt, user_prompt, model or OLLAMA_MODEL)


def _ask_groq(system_prompt: str, user_prompt: str, model: str) -> tuple[str, int, int]:
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
        "model": model,
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
            f"Groq API request failed (model='{model}'). "
            f"Check your GROQ_API_KEY and network. Original error: {exc}"
        ) from exc

    data = response.json()
    text = data["choices"][0]["message"]["content"].strip()
    usage = data.get("usage", {})
    return text, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)


def _ask_ollama(system_prompt: str, user_prompt: str, model: str) -> tuple[str, int, int]:
    url = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": model,
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
            f"'{model}'. Is `ollama serve` running and has the model "
            f"been pulled (`ollama pull {model}`)? Original error: {exc}"
        ) from exc

    data = response.json()
    text = data["message"]["content"].strip()
    return text, data.get("prompt_eval_count", 0), data.get("eval_count", 0)
