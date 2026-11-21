"""Turn a plain-language grid calculation request into a candidate formula using local Ollama."""
from __future__ import annotations

import argparse
import json
import re
import urllib.request

from chat import ollama_model


SYSTEM = """You write formulas for DBI Citadel grid formula columns. Return exactly one formula and nothing else.
Use only the provided column names in curly braces, e.g. {Revenue}. Supported syntax includes + - * /, &, = != < <= > >=, parentheses, strings in double quotes, and functions IF, AND, OR, NOT, CONCAT, LOWER, UPPER, ROUND, ABS, MIN, MAX, COUNT, LEN, LEFT, RIGHT, MID, TRIM, TODAY, DATE, YEAR, MONTH, DAY, LOOKUP. Do not invent columns, functions, or spreadsheet syntax. If the request cannot be expressed with these tools, return exactly CANNOT_BUILD: followed by a short reason. The user must review the formula; do not claim it has been validated."""


def generate(request: str, columns: list[str], result_type: str, model: str = "auto", current_formula: str = "") -> str:
    if not request.strip() or len(request) > 2000:
        raise ValueError("Describe the calculation in 1 to 2,000 characters.")
    installed = ollama_model.installed(timeout=3)
    if model == "auto" or not model:
        chosen, _why = ollama_model.pick(have=installed, task="write a formula coding task")
    else:
        if not model.startswith("ollama:"):
            raise ValueError("Choose an installed local Ollama model.")
        chosen = model[7:]
        if chosen not in installed:
            raise ValueError("That model is no longer installed or Ollama is not running. Refresh the model list and try again.")
    if chosen not in installed:
        raise RuntimeError("Ollama is not running or no local model is installed on the selected PC.")
    prompt = {
        "request": request.strip(), "result_column_type": result_type[:20],
        "available_columns": columns[:100], "existing_formula_to_improve": current_formula[:500],
    }
    body = json.dumps({"model": chosen, "stream": False, "keep_alive": "15m",
                       "options": {"num_ctx": 4096, "num_predict": 300, "temperature": 0.1},
                       "messages": [{"role": "system", "content": SYSTEM},
                                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}]}).encode()
    req = urllib.request.Request("http://localhost:11434/api/chat", body, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=240) as response:
            result = json.loads(response.read())
    except Exception as exc:
        raise RuntimeError(f"Local model request failed ({type(exc).__name__}). Check that Ollama is running.") from exc
    answer = str((result.get("message") or {}).get("content") or "").strip()
    answer = re.sub(r"^```(?:[a-zA-Z]+)?\s*|\s*```$", "", answer).strip()
    answer = re.sub(r"^(?:formula\s*:\s*)", "", answer, flags=re.I).strip()
    answer = answer.splitlines()[0].strip() if answer else ""
    if not answer:
        raise RuntimeError("The local model returned no formula. Try a simpler description or another model.")
    return answer[:500]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dse.py formula-assist")
    parser.add_argument("--request", required=True)
    parser.add_argument("--columns", required=True, help="JSON array of available grid column names")
    parser.add_argument("--result-type", default="text")
    parser.add_argument("--model", default="auto")
    parser.add_argument("--current-formula", default="")
    args = parser.parse_args(argv)
    try:
        names = json.loads(args.columns)
        if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
            raise ValueError("The available columns were not a valid list.")
        formula = generate(args.request, names, args.result_type, args.model, args.current_formula)
        print("FORMULA_ASSIST_RESULT: " + formula)
        return 0
    except Exception as exc:
        print(f"Formula suggestion unavailable: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
