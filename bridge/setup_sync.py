"""Setup checklist sync: your PC's System check, sent to your Citadel account so the Dashboard can show "is my setup done?" as a checklist.

    python bridge/setup_sync.py          run the System check and send the result
    python bridge/setup_sync.py --dry    run it and print what would be sent

The runner runs this every 5 minutes (catalog.json "periodic"), and the tool "Setup checklist: check now" runs it on demand. What is sent is the System check's own lines
(area, name, ok / needs a fix / optional / could not check, a short detail and the fix) and nothing else: no files, no data, no keys. Any text that looks like a key or a
token is hidden before it leaves the PC (the System check never prints one, this is a second lock). Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from dse import doctor  # noqa: E402

STATES = ("ok", "fix", "optional", "unknown")
MAX_ITEMS = 80
SECRET = re.compile(r"(sk-ant-[A-Za-z0-9_-]{8,}|hf_[A-Za-z0-9]{10,}|eyJ[A-Za-z0-9_-]{20,}|[A-Za-z0-9_-]{40,})")


def clean(text, n: int) -> str:
    return SECRET.sub("[hidden]", str(text or "")).strip()[:n]


def sanitize(items: list[dict]) -> list[dict]:
    """The System check's lines as plain strings, capped, with anything key-like hidden. Unknown states and malformed lines are dropped."""
    out = []
    for i in items or []:
        if not isinstance(i, dict) or i.get("state") not in STATES:
            continue
        out.append({"area": clean(i.get("area"), 60), "name": clean(i.get("name"), 120), "state": i["state"], "detail": clean(i.get("detail"), 300), "fix": clean(i.get("fix"), 500)})
        if len(out) >= MAX_ITEMS:
            break
    return out


def _runner():
    spec = importlib.util.spec_from_file_location("dse_runner", HERE / "runner.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    r = _runner()
    api = r.Api(r.load_env())
    items = sanitize(doctor.collect(api))
    if a.dry:
        for i in items:
            print(f"{i['state']:9} {i['area']}: {i['name']}")
        print(f"{len(items)} line(s) would be sent")
        return
    try:
        api.rpc("hq_setup_push", {"p_items": items})
    except RuntimeError as e:
        if "HTTP 404" in str(e) or "PGRST202" in str(e) or "Could not find" in str(e):
            sys.exit("the database update 20261122090000_setup_checklist.sql has not been run yet")
        raise
    n_fix = sum(1 for i in items if i["state"] == "fix")
    print(f"{dt.datetime.now():%H:%M:%S} setup checklist sent: {len(items)} line(s), {n_fix} to fix")


if __name__ == "__main__":
    main()
