"""Tool Studio guard: the static check every studio tool's code must pass before it is tested, approved or run.

Pure standard library and no relative imports, because the sandbox launcher (studio_run.py) imports it as a top-level module.

What this is, honestly: a guard against mistakes and against code an AI wrote, so a tool cannot by accident (or by a model's whim) delete files,
run programs, open network connections or read your keys. It is NOT a security boundary against a hostile author: that is why Tool Studio is off
until you turn it on on your own PC, why a tool runs only after you have read it and approved its exact code (a hash), and why code is never
shared through Citadel (a tool for everyone travels in the toolkit repository, where you review the commit).
"""
from __future__ import annotations

import ast
import re

MAX_SOURCE = 40_000

# the only modules the tool's own code may import (it gets files and the web through dse_sdk, which applies its own limits)
SDK_API = ["inputs", "log", "read_text", "read_csv", "write_text", "write_csv", "http_get", "to_json", "quote", "unquote", "urlencode", "urljoin", "urlparse"]
SAFE_MODULES = {
    "json", "csv", "re", "math", "datetime", "collections", "itertools", "functools", "statistics", "string", "textwrap", "html",
    "unicodedata", "decimal", "fractions", "random", "time", "hashlib", "base64", "typing", "dataclasses", "operator", "heapq", "bisect",
    "difflib", "enum", "uuid", "dse_sdk",
}
SAFE_DOTTED: set = set()          # nothing dotted: web helpers (quote, urlencode, urljoin, urlparse) come from dse_sdk

FORBIDDEN_NAMES = {
    "eval", "exec", "compile", "open", "__import__", "getattr", "setattr", "delattr", "globals", "locals", "vars", "dir", "input", "breakpoint",
    "memoryview", "exit", "quit", "help", "license", "credits", "copyright", "id", "hasattr", "callable", "classmethod_", "super_",
}

# builtins the sandbox gives the tool's code (nothing else exists for it)
SAFE_BUILTIN_NAMES = [
    "abs", "all", "any", "bool", "bytes", "chr", "dict", "divmod", "enumerate", "filter", "float", "format", "frozenset", "hash", "hex", "int",
    "isinstance", "issubclass", "iter", "len", "list", "map", "max", "min", "next", "oct", "ord", "pow", "print", "range", "repr", "reversed",
    "round", "set", "slice", "sorted", "str", "sum", "tuple", "zip", "object", "property", "staticmethod", "super", "type", "bytearray", "ascii",
    "True", "False", "None", "Exception", "ValueError", "KeyError", "TypeError", "IndexError", "StopIteration", "ZeroDivisionError", "RuntimeError",
    "AttributeError", "NotImplementedError", "ArithmeticError", "LookupError", "OverflowError", "UnicodeError", "AssertionError", "NameError", "SystemExit",
]


def scan(source: str) -> list[str]:
    """Problems found in the code, in plain words. An empty list means it passes the guard."""
    problems: list[str] = []
    if not isinstance(source, str) or not source.strip():
        return ["the code is empty"]
    if len(source) > MAX_SOURCE:
        return [f"the code is longer than {MAX_SOURCE:,} characters"]
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [f"the code does not parse (line {e.lineno}): {e.msg}"]
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        where = f" (line {line})" if line else ""
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name not in SAFE_MODULES and a.name not in SAFE_DOTTED:
                    problems.append(f"import {a.name} is not allowed{where}: tools may use only {', '.join(sorted(SAFE_MODULES - {'dse_sdk'}))} and dse_sdk")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level or (mod not in SAFE_MODULES and mod not in SAFE_DOTTED):
                problems.append(f"from {'.' * node.level}{mod} import ... is not allowed{where}")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES:
                problems.append(f"'{node.id}' is not allowed{where}")
            elif node.id.startswith("__") and node.id not in ("__name__",):
                problems.append(f"'{node.id}' is not allowed{where}")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                problems.append(f"the attribute '{node.attr}' is not allowed{where} (names starting with an underscore reach hidden parts of Python: use plain names)")
            elif node.attr in ("format_map", "mro", "gi_frame", "cr_frame", "f_globals", "f_locals", "f_back", "tb_frame", "func_globals"):
                problems.append(f"the attribute '{node.attr}' is not allowed{where}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "__" in node.value and re.search(r"__\w", node.value):
                problems.append(f"a text containing '__' is not allowed{where} (it can be used to reach hidden parts of Python)")
            elif re.search(r"\{[0-9A-Za-z_]*[.\[]", node.value):
                problems.append(f"a format text that reaches into an object ('{{x.y}}' or '{{x[0]}}') is not allowed{where}: build the text with f-strings or +")
        elif isinstance(node, (ast.Global, ast.AsyncFunctionDef, ast.Await, ast.AsyncFor, ast.AsyncWith)):
            problems.append(f"{type(node).__name__} is not allowed{where}")
        elif isinstance(node, ast.FunctionDef) and node.name.startswith("__") and node.name not in ("__init__", "__repr__", "__str__", "__len__", "__iter__", "__eq__", "__lt__", "__hash__"):
            problems.append(f"defining '{node.name}' is not allowed{where}")
    seen, out = set(), []
    for p in problems:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out[:25]
