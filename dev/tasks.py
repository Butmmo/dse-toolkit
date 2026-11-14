"""Named tasks per language: install, build, test, lint. Nothing is a shell string: each task is a fixed list of programs and arguments.

The ecosystem is detected from the files in the workspace. A missing toolchain is not an error you have to decode: you get the name of the
program and the Windows command that installs it.

  JavaScript / TypeScript  package.json          npm install (scripts OFF by default), npm run build, npm test, npm run <script name>
  Python                   pyproject / requirements / setup.py   a .venv, pip install, pytest or unittest, compileall
  Java                     pom.xml               mvn package / test
  Kotlin and Java          build.gradle(.kts)    gradle build / test (the project's gradlew if it has one)
  C#                       *.csproj / *.sln      dotnet build / test
  C and C++                CMakeLists.txt        cmake configure and build, ctest   (a Makefile: make)
  Dart and Flutter         pubspec.yaml          dart or flutter pub get / analyze / test / build apk
  Rust, Go                 Cargo.toml, go.mod    cargo build/test, go build/test/vet
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from . import config
from .sandbox import Refused, run

INSTALL_HINT = {
    "npm": "winget install OpenJS.NodeJS.LTS", "node": "winget install OpenJS.NodeJS.LTS", "python": "winget install Python.Python.3.12", "mvn": "winget install Apache.Maven",
    "gradle": "winget install Gradle.Gradle", "java": "winget install EclipseAdoptium.Temurin.21.JDK", "dotnet": "winget install Microsoft.DotNet.SDK.8", "cmake": "winget install Kitware.CMake",
    "make": "winget install GnuWin32.Make (or use CMake)", "gcc": "winget install MSYS2.MSYS2 then install mingw-w64-ucrt-x86_64-gcc", "flutter": "winget install Google.Flutter (or flutter.dev/docs/get-started/install)",
    "dart": "winget install Google.DartSDK", "cargo": "winget install Rustlang.Rustup", "go": "winget install GoLang.Go", "git": "winget install Git.Git",
}
TASKS = ("install", "build", "test", "lint", "script")


def detect(ws: Path) -> list[str]:
    eco = []
    has = lambda *n: any((ws / x).exists() for x in n)  # noqa: E731
    if has("package.json"):
        eco.append("node")
    if has("pyproject.toml", "requirements.txt", "setup.py", "setup.cfg"):
        eco.append("python")
    if has("pom.xml"):
        eco.append("maven")
    if has("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"):
        eco.append("gradle")
    if list(ws.glob("*.csproj")) or list(ws.glob("*.sln")) or list(ws.glob("*/*.csproj")):
        eco.append("dotnet")
    if has("CMakeLists.txt"):
        eco.append("cmake")
    elif has("Makefile"):
        eco.append("make")
    if has("pubspec.yaml"):
        eco.append("flutter" if "flutter:" in (ws / "pubspec.yaml").read_text(encoding="utf-8", errors="replace") else "dart")
    if has("Cargo.toml"):
        eco.append("rust")
    if has("go.mod"):
        eco.append("go")
    return eco


def npm_scripts(ws: Path) -> dict:
    try:
        return json.loads((ws / "package.json").read_text(encoding="utf-8")).get("scripts", {})
    except (OSError, ValueError):
        return {}


def venv_python(ws: Path) -> str:
    v = ws / ".venv"
    for rel in ("Scripts/python.exe", "bin/python"):
        if (v / rel).exists():
            return str(v / rel)
    return sys.executable


def plan(ws: Path, eco: str, task: str, script: str = "") -> list[list[str]]:
    cfg = config.load()
    g = ws / "gradlew.bat"
    gradle = [str(g)] if g.exists() and sys.platform == "win32" else ([str(ws / "gradlew")] if (ws / "gradlew").exists() else ["gradle"])
    if eco == "node":
        if task == "install":
            return [["npm", "install", "--no-audit", "--no-fund"] + ([] if cfg["npm_scripts"] else ["--ignore-scripts"])]
        if task == "script":
            if not re.fullmatch(r"[A-Za-z0-9:_-]{1,40}", script or "") or script not in npm_scripts(ws):
                raise Refused(f"'{script}' is not a script in package.json. Scripts here: {', '.join(npm_scripts(ws)) or 'none'}.")
            return [["npm", "run", script]]
        return [["npm", "run", {"build": "build", "lint": "lint", "test": "test"}[task], "--if-present"]] if task != "test" else [["npm", "test"]]
    if eco == "python":
        py = venv_python(ws)
        req = (ws / "requirements.txt").exists()
        if task == "install":
            steps = [[sys.executable, "-m", "venv", str(ws / ".venv")]]
            vp = str(ws / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python"))
            steps.append([vp, "-m", "pip", "install", "-q", "-r", "requirements.txt"] if req else [vp, "-m", "pip", "install", "-q", "-e", "."])
            return steps
        if task == "test":
            has_pytest = (ws / "pytest.ini").exists() or "pytest" in ((ws / "requirements.txt").read_text(encoding="utf-8", errors="replace") if req else "")
            return [[py, "-m", "pytest", "-q"]] if has_pytest else [[py, "-m", "unittest", "discover", "-s", "tests" if (ws / "tests").is_dir() else ".", "-v"]]
        if task in ("lint", "build"):
            return [[py, "-m", "compileall", "-q", "."]]
    if eco == "maven":
        return {"install": [["mvn", "-q", "-B", "dependency:resolve"]], "build": [["mvn", "-q", "-B", "package", "-DskipTests"]], "test": [["mvn", "-q", "-B", "test"]], "lint": [["mvn", "-q", "-B", "compile"]]}.get(task, [])
    if eco == "gradle":
        return {"install": [gradle + ["--quiet", "dependencies"]], "build": [gradle + ["build", "-x", "test", "--console=plain"]], "test": [gradle + ["test", "--console=plain"]], "lint": [gradle + ["check", "--console=plain"]]}.get(task, [])
    if eco == "dotnet":
        return {"install": [["dotnet", "restore"]], "build": [["dotnet", "build", "--nologo", "-v", "q"]], "test": [["dotnet", "test", "--nologo", "-v", "q"]], "lint": [["dotnet", "build", "--nologo", "-v", "q"]]}.get(task, [])
    if eco == "cmake":
        return {"install": [], "build": [["cmake", "-S", ".", "-B", "build"], ["cmake", "--build", "build"]], "test": [["cmake", "-S", ".", "-B", "build"], ["cmake", "--build", "build"], ["ctest", "--test-dir", "build", "--output-on-failure"]],
                "lint": [["cmake", "-S", ".", "-B", "build"]]}.get(task, [])
    if eco == "make":
        return {"install": [], "build": [["make"]], "test": [["make", "test"]], "lint": [["make", "-n"]]}.get(task, [])
    if eco in ("dart", "flutter"):
        t = eco
        return {"install": [[t, "pub", "get"]], "build": [["flutter", "build", "apk", "--debug"]] if eco == "flutter" else [["dart", "compile", "exe", "bin/main.dart", "-o", "build/app.exe"]],
                "test": [[t, "test"]], "lint": [[t, "analyze"]]}.get(task, [])
    if eco == "rust":
        return {"install": [["cargo", "fetch"]], "build": [["cargo", "build"]], "test": [["cargo", "test"]], "lint": [["cargo", "check"]]}.get(task, [])
    if eco == "go":
        return {"install": [["go", "mod", "download"]], "build": [["go", "build", "./..."]], "test": [["go", "test", "./..."]], "lint": [["go", "vet", "./..."]]}.get(task, [])
    return []


def run_task(ws: Path, task: str, script: str = "", eco: str = "") -> str:
    if not config.load()["allow_run"]:
        raise Refused("Running tasks is switched off at this PC (allow_run).")
    if task not in TASKS:
        raise Refused(f"Task must be one of: {', '.join(TASKS)}.")
    found = detect(ws)
    if not found:
        raise Refused("I could not tell what kind of project this is (no package.json, pyproject.toml, pom.xml, build.gradle, *.csproj, CMakeLists.txt, pubspec.yaml, Cargo.toml or go.mod).")
    chosen = [eco] if eco else found
    reports = []
    for e in chosen:
        steps = plan(ws, e, task, script)
        if not steps:
            reports.append(f"[{e}] has nothing to do for '{task}'.")
            continue
        for argv in steps:
            code, out = run(argv, ws)
            shown = " ".join(Path(a).name if i == 0 else a for i, a in enumerate(argv))
            if code == 127:
                tool = Path(argv[0]).name.replace(".exe", "").replace(".bat", "")
                hint = INSTALL_HINT.get(tool, "")
                reports.append(f"[{e}] {shown}\n{out.strip()}" + (f"\nInstall it on this PC with: {hint}" if hint else ""))
                break
            reports.append(f"[{e}] {shown}  ->  {'OK' if code == 0 else 'FAILED (exit ' + str(code) + ')'}\n{out.strip()}")
            if code != 0:
                break
    return "\n\n".join(reports)
