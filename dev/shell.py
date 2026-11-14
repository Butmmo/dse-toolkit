"""Run a PowerShell command inside a workspace. OFF by default; only a person at this PC can turn it on (allow_shell).

    python dse.py dev config --set allow_shell=true

Be clear about what this is. The command runs as YOU, in the workspace folder, with your tokens removed from its environment, a time limit and a capped
output. A deny list refuses the commands that are most dangerous (deleting outside the workspace, formatting disks, changing the registry, execution
policy or scheduled tasks, downloading and running code, encoded commands, elevation, shutting down). A deny list is NOT a sandbox: a determined command can
still do harm inside what you can do. Turn this on only on a PC where you accept that, and never run a command you do not understand.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from . import config
from .sandbox import Refused, run

DENY = [
    (r"-EncodedCommand|\s-enc\s|FromBase64String", "encoded commands hide what they do"),
    (r"\b(iex|invoke-expression)\b", "running text as code (Invoke-Expression)"),
    (r"(invoke-webrequest|iwr|invoke-restmethod|irm|curl|wget|start-bitstransfer)\b[^|;]*\|\s*(iex|invoke-expression|powershell|pwsh|cmd|bash|sh)\b", "downloading and running code"),
    (r"\b(format-volume|clear-disk|remove-partition|initialize-disk|diskpart|format\.com)\b", "disk operations"),
    (r"\b(stop-computer|restart-computer|shutdown(\.exe)?)\b", "shutting down or restarting the PC"),
    (r"\b(set-executionpolicy|new-itemproperty|set-itemproperty|remove-itemproperty|reg(\.exe)?\s+(add|delete|import))\b|\bHK(LM|CU|CR|U|CC):|\bhklm\\|\bhkcu\\", "the registry or execution policy"),
    (r"\b(schtasks|register-scheduledtask|new-scheduledtask|new-service|sc\.exe|set-service|net\s+(user|localgroup))\b", "scheduled tasks, services or accounts"),
    (r"-Verb\s+RunAs|\bstart-process\b[^;|]*-verb", "asking for administrator rights"),
    (r"\b(add-mppreference|set-mppreference|disable-windowsoptionalfeature|bcdedit|netsh\s+advfirewall)\b", "security settings"),
    (r"\bremove-item\b[^;|]*(\.\.|[A-Za-z]:[\\/]|~|\$env:|\$home|\\\\)", "deleting outside the workspace"),
    (r"\b(rm|del|rd|rmdir|ri)\b\s+(-r|-recurse|/s)[^;|]*(\.\.|[A-Za-z]:[\\/]|~|\$env:|\$home|\\\\|\s/\s*$)", "deleting outside the workspace"),
    (r"(\.\.[\\/]){2,}", "reaching out of the workspace"),
    (r"\b(copy-item|move-item|set-content|out-file|add-content|new-item)\b[^;|]*(\.\.[\\/]|[A-Za-z]:[\\/](windows|program files|users)[\\/])", "writing outside the workspace"),
]


def check(cmd: str) -> None:
    c = (cmd or "").strip()
    if not c or len(c) > 2000 or "\n" in c.strip() and len(c.splitlines()) > 40:
        raise Refused("Give one PowerShell command (up to 2000 characters).")
    for rx, why in DENY:
        if re.search(rx, c, re.I):
            raise Refused(f"Refused: that command involves {why}. If you really need it, run it yourself in a PowerShell window on this PC.")


def shell(ws: Path, cmd: str) -> str:
    cfg = config.load()
    if not cfg["allow_shell"]:
        raise Refused("Running PowerShell commands is switched off. Only you, at this PC, can turn it on: python dse.py dev config --set allow_shell=true  (read the warning in dev/shell.py first).")
    check(cmd)
    exe = shutil.which("pwsh") or shutil.which("powershell")
    if not exe:
        raise Refused("PowerShell was not found on this PC.")
    code, out = run([exe, "-NoProfile", "-NonInteractive", "-Command", cmd], ws)
    return f"PowerShell exit {code}\n{out.strip()}"
