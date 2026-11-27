"""Publish a website build to Cloudflare Pages, guided end to end.

    python builder/publish.py <build> [--project <name>] [--dry]

The App Builder deliberately publishes nothing: the member deploys themselves. This is
the guided version of that last step, for website builds only, on the pattern the house
itself uses (Cloudflare Pages, a free pages.dev address, no server to run):

  1. The site files at the top of the build folder (pages, styles, scripts, images) are
     staged into builds/<slug>/publish/, exactly as they stand. Specs, notes and backups
     never leave the PC. If you edited the words in My builds, Render there first.
  2. With the member's own Cloudflare API token and account id in two Windows user
     variables (CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, never in a file), the site
     is deployed with Wrangler (Cloudflare's own tool, fetched by npx) and the live
     address is printed as a PUBLISHED line.
  3. Without them, nothing is uploaded: the tool prints the short setup (an account, a
     token with Pages edit permission, the two setx lines) and the manual route, which
     is dragging the staged publish folder into the Cloudflare Pages dashboard.

Publishing puts the member's own site on the member's own account, only when they run
this tool. It never runs on a schedule and never touches any other build.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build as builder  # noqa: E402  builder/build.py, beside this file

SITE_EXTS = {".html", ".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".txt", ".xml"}
SKIP_NAMES = {"preview.html"}
URL_RE = re.compile(r"https://[^\s\"'<>]+\.pages\.dev")


def find_build(ref: str) -> Path:
    out = builder.OUT
    cand = out / ref
    if cand.is_dir():
        return cand
    slug = builder.slugify(ref or "")
    if out.is_dir():
        for d in sorted(out.iterdir()):
            if d.is_dir() and (d.name == slug or d.name.startswith(slug)):
                return d
    raise SystemExit(f"No build called '{ref}' in {out}. Open My builds in Citadel to see the builds on this PC.")


def read_spec(dst: Path) -> dict:
    f = dst / "spec.json"
    if not f.is_file():
        raise SystemExit(f"{dst.name} has no spec.json, so it is not an App Builder build. Nothing was published.")
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        raise SystemExit(f"{dst.name}'s spec.json cannot be read. Nothing was published.") from None


def stage(dst: Path) -> Path:
    """Copy the site files (and only the site files) into builds/<slug>/publish/."""
    pub = dst / "publish"
    if pub.exists():
        shutil.rmtree(pub)
    pub.mkdir()
    for f in sorted(dst.iterdir()):
        if f.is_file() and f.suffix.lower() in SITE_EXTS and f.name not in SKIP_NAMES:
            shutil.copyfile(f, pub / f.name)
    if not (pub / "index.html").is_file():
        raise SystemExit(f"{dst.name} has no index.html at its top level, so there is no website to publish.")
    return pub


def project_name(spec: dict, dst: Path, given: str) -> str:
    raw = (given or "").strip() or str(spec.get("name") or "").strip() or dst.name
    slug = builder.slugify(raw).strip("-")[:58].rstrip("-")
    return slug or dst.name


def setup_guidance(project: str, pub: Path) -> str:
    return "\n".join([
        "Not published yet: this PC has no Cloudflare connection set up. It takes a few minutes, once:",
        "1. Create a free account at cloudflare.com (or sign in).",
        "2. In the Cloudflare dashboard open My Profile, then API Tokens, then Create Token, and use the template or a custom token with Account, Cloudflare Pages, Edit permission.",
        "3. Find your Account ID on any domain's overview page in the dashboard (right-hand column).",
        "4. Put both in Windows user variables (the token never goes in a file):",
        '     setx CLOUDFLARE_API_TOKEN "your token"',
        '     setx CLOUDFLARE_ACCOUNT_ID "your account id"',
        "5. Restart the HQ runner (so it can see the new variables), then run Publish again.",
        f"Manual route, no setup at all: in the Cloudflare dashboard choose Workers & Pages, Create, Pages, Upload assets, name the project {project}, and drag in the contents of this folder:",
        f"  {pub}",
        "Either way the site gets a free address like https://" + project + ".pages.dev, and a custom domain can be attached later in the same dashboard.",
    ])


def deploy(pub: Path, project: str, env: dict, run=subprocess.run) -> tuple[str | None, str]:
    """Deploy with Wrangler. Returns (live url or None, the tail of Wrangler's output)."""
    exe = shutil.which("npx")
    if not exe:
        return None, "Node.js (npx) was not found on this PC. Install Node.js LTS from nodejs.org, restart the runner, and run Publish again."
    cmd = [exe, "--yes", "wrangler@3", "pages", "deploy", str(pub), "--project-name", project]
    try:
        r = run(cmd, capture_output=True, text=True, timeout=600, env=env)
    except subprocess.TimeoutExpired:
        return None, "The upload took longer than 10 minutes and was stopped. Check the connection and run Publish again."
    text = (r.stdout or "") + (r.stderr or "")
    urls = URL_RE.findall(text)
    if r.returncode == 0 and urls:
        live = f"https://{project}.pages.dev"
        return (live if live in urls else urls[0]), text
    return None, text


def main(argv=None, env=None, run=subprocess.run) -> int:
    ap = argparse.ArgumentParser(prog="publish")
    ap.add_argument("build")
    ap.add_argument("--project", default="")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)
    env = dict(os.environ) if env is None else env

    dst = find_build(a.build)
    spec = read_spec(dst)
    if spec.get("kind") != "website":
        raise SystemExit(f"{dst.name} is a {spec.get('kind') or 'unknown'} build. Only website builds publish to Cloudflare Pages; apps are published through their own stores and tooling.")
    project = project_name(spec, dst, a.project)
    pub = stage(dst)
    count = len([f for f in pub.iterdir() if f.is_file()])
    print(f"Staged {count} site files from {dst.name} into {pub} (the site exactly as it stands; if you edited the words in My builds, Render there first).")
    if a.dry:
        print("Dry run: nothing was uploaded.")
        return 0
    if not env.get("CLOUDFLARE_API_TOKEN") or not env.get("CLOUDFLARE_ACCOUNT_ID"):
        print(setup_guidance(project, pub))
        return 0
    url, tail = deploy(pub, project, env, run)
    if url:
        print("\n".join(tail.strip().splitlines()[-6:]))
        print(f"PUBLISHED {url}")
        print("The site is live. Later changes: edit in My builds, Render, then run Publish again; the same address is updated.")
        return 0
    print("The upload did not finish. Wrangler said:")
    print("\n".join(tail.strip().splitlines()[-12:]))
    print(f"Nothing is live yet. You can also publish by hand: drag the contents of {pub} into a new Pages project in the Cloudflare dashboard (Workers & Pages, Create, Pages, Upload assets).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
