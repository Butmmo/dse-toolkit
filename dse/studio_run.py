"""Tool Studio sandbox launcher. Run as:  python -I -u dse/studio_run.py <code file> <work folder> <inputs.json> <toolkit root>

-I (isolated mode) ignores PYTHONPATH and the user site; this file then puts only its own folder on the path to find studio_guard and studio_sdk.
The tool's code runs with a short list of builtins (no open, no eval, no getattr) and an import hook that lets it import only the allowed modules.
The parent (dse/studio.py) removes your keys from the environment, sets a time limit and caps the output. See studio_guard.py for what this is and is not.
"""
import builtins
import importlib
import json
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import studio_guard  # noqa: E402
import studio_sdk  # noqa: E402


def main() -> int:
    code_file, work, inputs_file, root = sys.argv[1:5]
    src = Path(code_file).read_text(encoding="utf-8")
    problems = studio_guard.scan(src)
    if problems:
        print("Refused by the Tool Studio guard:\n- " + "\n- ".join(problems))
        return 2
    values = json.loads(Path(inputs_file).read_text(encoding="utf-8"))
    studio_sdk.configure(root, work, values)

    allowed = set(studio_guard.SAFE_MODULES)
    # the tool gets only these names from the sdk (not the sdk module itself, which holds socket, urllib and friends)
    api = types.SimpleNamespace(**{n: getattr(studio_sdk, n) for n in studio_guard.SDK_API})

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level or name not in allowed:
            raise ImportError(f"'{name}' is not allowed in Tool Studio")
        if name == "dse_sdk":
            return api
        return importlib.import_module(name)

    safe = {n: getattr(builtins, n) for n in studio_guard.SAFE_BUILTIN_NAMES if hasattr(builtins, n)}
    safe["__import__"] = guarded_import
    safe["__build_class__"] = builtins.__build_class__
    safe["__name__"] = "tool"
    g = {"__builtins__": safe, "__name__": "tool"}
    try:
        exec(compile(src, "tool.py", "exec"), g)          # noqa: S102 (the point of this file: guarded, scanned code)
    except SystemExit as e:
        return int(e.code or 0) if isinstance(e.code, int) else 0
    except Exception as e:
        print(f"The tool stopped with an error: {type(e).__name__}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
