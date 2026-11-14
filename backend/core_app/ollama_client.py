"""Thin client for a local Ollama server (https://ollama.com)."""
import requests
from django.conf import settings

_session = requests.Session()  # keep-alive connection reuse


def _post_ollama(body: dict, timeout: int = 60):
    r = _session.post(f"{settings.OLLAMA_URL}/api/chat", json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()


def chat_generic(req: dict, timeout: int = 60):
    model = getattr(settings, "OLLAMA_MODEL", "qwen3")
    body = {
        "model": model,
        "messages": req["messages"],
        "stream": False,
        "keep_alive": "15m",
        "options": {
            "temperature": req.get("temperature", 0.2),
            "num_ctx": req.get("num_ctx", 8192),
            "num_predict": req.get("num_predict", 512),
        },
    }
    if model.split(":")[0] in ("qwen3", "deepseek-r1"):
        body["think"] = False  # reasoning models: we only want the final answer
    if req.get("format") == "json":
        body["format"] = "json"
    return _post_ollama(body, timeout=timeout)
