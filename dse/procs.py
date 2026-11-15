"""Run a program with a time limit, streaming its lines. Shared by My tools (recipes) and Tool Studio. Standard library only."""
from __future__ import annotations

import os
import subprocess
import threading


def kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        proc.kill()


def run_streaming(argv: list[str], cwd: str, env: dict, timeout_s: float, emit=print, cap_chars: int = 400_000) -> tuple[int, bool]:
    """Runs argv, passes each output line to emit(line). Returns (exit code, timed_out). A program that prints more than cap_chars is stopped."""
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    proc = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env, creationflags=flags)
    state = {"timed_out": False, "chars": 0}

    def stop():
        state["timed_out"] = True
        kill_tree(proc)

    timer = threading.Timer(timeout_s, stop)
    timer.daemon = True
    timer.start()
    try:
        for raw in iter(proc.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            state["chars"] += len(line) + 1
            if state["chars"] > cap_chars:
                emit("-- output limit reached: stopping --")
                kill_tree(proc)
                break
            emit(line)
    finally:
        timer.cancel()
    proc.wait()
    return proc.returncode, state["timed_out"]
