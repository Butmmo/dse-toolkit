"""Optional, local-only advisory review of an HQ Tools result through Ollama."""
from __future__ import annotations

import importlib.util
import json
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


def review(tool_key: str, result: str, timeout: int = 240) -> tuple[str, str]:
    """Return (model, advice). Never edits files or calls another service."""
    spec = importlib.util.spec_from_file_location("hq_ollama_model", HERE / "ollama_model.py")
    if not spec or not spec.loader:
        raise RuntimeError("The local model helper is unavailable.")
    models = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(models)
    installed = models.installed()
    if not installed:
        raise RuntimeError("Ollama is not running or no local model is installed.")
    model, _ = models.pick(have=installed, task=tool_key)
    excerpt = (result or "").strip()[-12000:]
    if not excerpt:
        raise RuntimeError("The tool produced no text to review.")
    user = f"HQ tool: {tool_key}\n\nTool result (may be shortened to its final 12,000 characters):\n{excerpt}"
    body = json.dumps({
        "model": model,
        "stream": False,
        "keep_alive": "30m",
        "options": {"num_ctx": 8192, "num_predict": 450, "temperature": 0.2},
        "messages": [
            {"role": "system", "content": (
                "You are a careful local reviewer for a business tool. Review only the result shown. "
                "Do not invent facts, repeat personal data, call tools, suggest sending or changing anything without the user's approval, "
                "or claim you verified something the result does not show. Give up to three concise useful observations or next steps. "
                "If the result looks complete, say so. Your response is advisory and must not replace or alter the tool result."
            )},
            {"role": "user", "content": user},
        ],
    }).encode("utf-8")
    req = urllib.request.Request("http://localhost:11434/api/chat", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        answer = str((json.loads(response.read()).get("message") or {}).get("content", "")).strip()
    if not answer:
        raise RuntimeError("The local model returned no review.")
    return model, answer[:4000]
