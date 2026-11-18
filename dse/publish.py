"""Presence phase 4: post YOUR OWN content to YOUR OWN account through the platform's official programme, from this PC, only after you approve it.

    python dse.py presence publish connect <linkedin|discord> <account>      a small window asks for the token (LinkedIn) or the webhook address (Discord), hidden; it stays ON THIS PC
    python dse.py presence publish accounts                                   which accounts are connected (names only, never a secret)
    python dse.py presence publish remove <linkedin|discord> <account>        forget one on this PC (revoke it at the platform too if it leaked)
    python dse.py presence publish post <my-posts/file.json> [--approve POST] a PREVIEW of exactly what would go out; with --approve POST it is posted

What this is and is not:
  * It only ever creates ONE new post on an account you connected. There is no code here for direct messages, comments, follows, likes or reading anyone else's account, and there never will be.
  * Nothing is posted without the word POST typed by you, here, for that file. Without it you get a preview.
  * The post file comes from Presence > Studio ("Post file (for your PC)"), which only offers it for a piece with no [bracket] left. It is checked again here.
  * Limits kept here: at most 3 posts a day per account, at least 30 minutes apart, never the same text twice.
  * The token or webhook address is kept in your Windows user settings, NEVER typed into Citadel, never sent to Citadel, never printed or put in a log or a job. It is sent only to the platform it belongs to.
Platforms: LinkedIn (a text post on your own profile, through the Posts API with a token that has the w_member_social permission, from your own LinkedIn developer app) and Discord (a message in a channel
of a server you manage, through that channel's webhook; no app or token needed). Standard library only.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from .claudekey import WindowsStore
from .common import DATA, ROOT, slug

POSTS = ROOT / "my-posts"
STATE = DATA / "presence"
ACCOUNTS = STATE / "accounts.json"
LOG = STATE / "posted.jsonl"
PLATFORMS = ("linkedin", "discord")
ACCOUNT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")
MAX_PER_DAY = 3
MIN_GAP_MINUTES = 30
LIMITS = {"linkedin": 3000, "discord": 2000}
LINKEDIN_VERSION = os.environ.get("PRESENCE_LINKEDIN_VERSION", "202610")   # LinkedIn's API versions are monthly (YYYYMM); change it here if LinkedIn retires this one
WEBHOOK_RE = re.compile(r"^https://(?:discord|discordapp)\.com/api/webhooks/\d{5,25}/[A-Za-z0-9_-]{20,120}\Z")
TOKEN_RE = re.compile(r"^[A-Za-z0-9._~+/=-]{20,2000}\Z")
PERSON_RE = re.compile(r"^[A-Za-z0-9_-]{4,60}\Z")


# ------------------------------------------------------------------ where secrets live (this PC only)

def secret_name(platform: str, account: str) -> str:
    return f"PRESENCE_{platform.upper()}_{account.upper().replace('-', '_')}"


def get_secret(platform: str, account: str, store=None) -> str:
    n = secret_name(platform, account)
    return (os.environ.get(n, "").strip() or (store or WindowsStore()).get(n)).strip()


def mask(s: str) -> str:
    return "..." + s[-4:] if len(s) >= 8 else "..."


def read_accounts() -> list[dict]:
    try:
        a = json.loads(ACCOUNTS.read_text(encoding="utf-8")).get("accounts", [])
        return [x for x in a if isinstance(x, dict) and x.get("platform") in PLATFORMS and ACCOUNT_RE.match(str(x.get("account", "")))]
    except (OSError, ValueError):
        return []


def write_accounts(accts: list[dict]) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    ACCOUNTS.write_text(json.dumps({"v": 1, "accounts": accts}, indent=2), encoding="utf-8")


# ------------------------------------------------------------------ the checks (pure)

def check_post(p: object, platform: str | None = None) -> list[str]:
    """Plain-words problems with a post file. An empty list means it may be previewed and, with POST typed, posted."""
    if not isinstance(p, dict):
        return ["This is not a Presence post file."]
    out: list[str] = []
    pf = platform or p.get("platform")
    text = str(p.get("text") or "")
    if pf not in PLATFORMS:
        out.append(f"I can post to {' and '.join(PLATFORMS)} only, not {pf!r}.")
    if not ACCOUNT_RE.match(str(p.get("account") or "")):
        out.append("The post file has no account name (letters, digits and dashes, for example orlando-linkedin).")
    if not text.strip():
        out.append("The post has no words in it.")
    if re.search(r"\[[^\]]{1,120}\]", text):
        out.append("There is still a [bracket] in the text: fill it with your real detail in the Studio first.")
    if pf in LIMITS and len(text) > LIMITS[pf]:
        out.append(f"The text is {len(text)} characters; {pf} allows {LIMITS[pf]}.")
    if p.get("ready") is not True:
        out.append("The Studio did not mark this piece ready (no [bracket] left and its checks passed).")
    return out


def text_sha(platform: str, account: str, text: str) -> str:
    return hashlib.sha256(f"{platform}\n{account}\n{text.strip()}".encode("utf-8")).hexdigest()[:16]


def read_log() -> list[dict]:
    out = []
    try:
        for line in LOG.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    except OSError:
        pass
    return out


def rate_problem(platform: str, account: str, sha: str, now: dt.datetime, log: list[dict]) -> str:
    """The reason this post must wait or not go at all, or an empty string. Counts what really went out."""
    mine = [e for e in log if e.get("platform") == platform and e.get("account") == account]
    if any(e.get("sha") == sha for e in mine):
        return "This exact post was already posted from this account. Change it, or post something new."
    times = []
    for e in mine:
        try:
            times.append(dt.datetime.fromisoformat(e["at"]))
        except (KeyError, ValueError):
            pass
    today = [t for t in times if t.date() == now.date()]
    if len(today) >= MAX_PER_DAY:
        return f"{len(today)} posts already went out today from this account (the limit is {MAX_PER_DAY} a day). Try tomorrow."
    if times and (now - max(times)).total_seconds() < MIN_GAP_MINUTES * 60:
        wait = MIN_GAP_MINUTES - int((now - max(times)).total_seconds() // 60)
        return f"The last post from this account was under {MIN_GAP_MINUTES} minutes ago. Wait about {wait} more minutes."
    return ""


# ------------------------------------------------------------------ the two official programmes

_LITTLE = re.compile(r"([\\|{}@\[\]()<>*_~])")


def linkedin_text(text: str) -> str:
    """LinkedIn's post text format reserves a few characters: they are escaped so the post is not cut short or turned into a mention. A hashtag (#word) stays a hashtag."""
    t = _LITTLE.sub(r"\\\1", text.strip())
    return re.sub(r"#(?!\w)", r"\\#", t)


def _http(method: str, url: str, headers: dict, body: bytes | None = None, timeout: int = 30) -> tuple[int, dict, str]:
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read(4000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read(2000).decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, {}, ""


def post_linkedin(text: str, token: str, person: str, http=_http) -> tuple[bool, str, str]:
    """(posted, post id or the platform's own words about what went wrong, public address)."""
    body = {"author": f"urn:li:person:{person}", "commentary": linkedin_text(text), "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []}, "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False}
    code, hdr, resp = http("POST", "https://api.linkedin.com/rest/posts", {"Authorization": f"Bearer {token}", "X-Restli-Protocol-Version": "2.0.0", "Linkedin-Version": LINKEDIN_VERSION,
                                                                          "Content-Type": "application/json"}, json.dumps(body).encode("utf-8"))
    if code == 201:
        urn = hdr.get("x-restli-id", "")
        return True, urn, f"https://www.linkedin.com/feed/update/{urn}/" if urn else ""
    why = {0: "Could not reach LinkedIn: check your internet.", 401: "LinkedIn did not accept the token (it may have expired): connect the account again.",
           403: "LinkedIn refused: the token needs the w_member_social permission (add the 'Share on LinkedIn' product to your LinkedIn app, then get a new token).",
           429: "LinkedIn says too many requests: wait and try later."}.get(code, f"LinkedIn answered {code}.")
    return False, f"{why} {resp[:200]}".strip(), ""


def post_discord(text: str, webhook: str, http=_http) -> tuple[bool, str, str]:
    body = {"content": text.strip()[:2000], "allowed_mentions": {"parse": []}}       # no @everyone, no @role, no @user can fire from this message
    code, _h, resp = http("POST", webhook + "?wait=true", {"Content-Type": "application/json", "User-Agent": "DSEToolkit-Presence/1.0"}, json.dumps(body).encode("utf-8"))
    if code in (200, 204):
        try:
            return True, str(json.loads(resp).get("id", "")), ""
        except ValueError:
            return True, "", ""
    why = {0: "Could not reach Discord: check your internet.", 401: "Discord did not accept this webhook (it may have been deleted): connect it again.", 404: "That webhook no longer exists: make a new one in the channel's settings.",
           429: "Discord says too many requests: wait and try later."}.get(code, f"Discord answered {code}.")
    return False, why, ""


# ------------------------------------------------------------------ the commands

def preview(p: dict, account_ok: bool) -> str:
    text = str(p.get("text") or "").strip()
    pf, acc = p.get("platform"), p.get("account")
    return "\n".join(["PREVIEW: nothing has been posted.", f"Platform: {pf}   Account: {acc}" + ("" if account_ok else "   (NOT connected on this PC: run 'Presence: connect an account' first)"),
                      f"Characters: {len(text)} of {LIMITS.get(pf, '?')}", "---", text, "---", "To post exactly this, run again with the word POST typed in the approve box."])


def post_file(path: str | Path, approve: str = "", now: dt.datetime | None = None, store=None, http=_http, out=print) -> int:
    f = Path(path)
    if not f.exists():
        cand = POSTS / Path(path).name
        f = cand if cand.exists() else f
    try:
        p = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        out("I could not read that post file. Download it again from Presence > Studio.")
        return 1
    problems = check_post(p)
    if problems:
        out("Not posted. Fix this first:")
        for x in problems:
            out(f"  - {x}")
        return 1
    pf, acc, text = p["platform"], p["account"], str(p["text"]).strip()
    secret = get_secret(pf, acc, store)
    if approve.strip() != "POST":
        out(preview(p, bool(secret)))
        return 0
    if not secret:
        out(f"No {pf} account called {acc} is connected on this PC. Run 'Presence: connect an account' (python dse.py presence publish connect {pf} {acc}) first.")
        return 1
    now = now or dt.datetime.now()
    sha = text_sha(pf, acc, text)
    why = rate_problem(pf, acc, sha, now, read_log())
    if why:
        out("Not posted. " + why)
        return 1
    if pf == "linkedin":
        person = next((a.get("person", "") for a in read_accounts() if a["platform"] == pf and a["account"] == acc), "")
        if not PERSON_RE.match(person or ""):
            out("This LinkedIn account has no member id saved: connect it again.")
            return 1
        ok, ident, url = post_linkedin(text, secret, person, http)
    else:
        ok, ident, url = post_discord(text, secret, http)
    if not ok:
        out("Not posted. " + ident)
        return 1
    STATE.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": now.isoformat(timespec="seconds"), "platform": pf, "account": acc, "sha": sha, "id": ident}) + "\n")
    POSTS.mkdir(exist_ok=True)
    rec = POSTS / f"{slug(f.stem)}.posted.json"
    rec.write_text(json.dumps({"v": 1, "platform": pf, "account": acc, "at": now.isoformat(timespec="seconds"), "id": ident, "url": url, "title": str(p.get("title") or "")[:120], "sha": sha}, indent=2), encoding="utf-8")
    out(f"Posted to {pf} ({acc})." + (f" {url}" if url else "") + f" Record: {rec.name}")
    return 0


def ask_secret(prompt: str, window: bool = True) -> str:
    """The secret, typed hidden. A small window when tkinter exists, else the terminal."""
    if window:
        try:
            import tkinter
            from tkinter import simpledialog
            root = tkinter.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            v = simpledialog.askstring("Presence: connect an account", prompt + " (it stays on this PC):", show="*", parent=root)
            root.destroy()
            return (v or "").strip()
        except Exception:
            pass
    import getpass
    return getpass.getpass(prompt + " (hidden as you type, it stays on this PC): ").strip()


def connect(platform: str, account: str, secret: str, person: str = "", store=None, http=_http) -> str:
    account = (account or "").strip().lower()
    if platform not in PLATFORMS:
        return f"Choose {' or '.join(PLATFORMS)}.\n"
    if not ACCOUNT_RE.match(account):
        return "Give the account a short name: letters, digits and dashes, for example orlando-linkedin.\n"
    secret = (secret or "").strip()
    if platform == "discord":
        if not WEBHOOK_RE.match(secret):
            return "Not saved: that does not look like a Discord webhook address (it starts with https://discord.com/api/webhooks/). In Discord: channel settings, Integrations, Webhooks, New Webhook, Copy Webhook URL.\n"
    else:
        if not TOKEN_RE.match(secret):
            return "Not saved: that does not look like a LinkedIn access token (a long line of letters and digits with no spaces).\n"
        if not PERSON_RE.match(person or ""):
            code, _h, body = http("GET", "https://api.linkedin.com/v2/userinfo", {"Authorization": f"Bearer {secret}"})
            try:
                person = str(json.loads(body).get("sub", "")) if code == 200 else ""
            except ValueError:
                person = ""
        if not PERSON_RE.match(person or ""):
            return "Not saved: I could not read your LinkedIn member id with this token (it needs the openid and profile permissions as well). Use a token with both, or give the member id yourself.\n"
    store = store or WindowsStore()
    try:
        store.set(secret_name(platform, account), secret)
    except RuntimeError as e:
        return f"Not saved. {e}\n"
    os.environ[secret_name(platform, account)] = secret
    accts = [a for a in read_accounts() if not (a["platform"] == platform and a["account"] == account)]
    accts.append({"platform": platform, "account": account, **({"person": person} if platform == "linkedin" else {}), "added": dt.date.today().isoformat()})
    write_accounts(accts)
    return f"Connected {platform} account {account} ({mask(secret)}). It stays on this PC and is sent only to {platform}. Nothing was posted.\n"


def remove(platform: str, account: str, store=None) -> str:
    account = (account or "").strip().lower()
    (store or WindowsStore()).delete(secret_name(platform, account))
    os.environ.pop(secret_name(platform, account), None)
    write_accounts([a for a in read_accounts() if not (a["platform"] == platform and a["account"] == account)])
    return f"Removed {platform} account {account} from this PC. If it ever leaked, also revoke it at {platform}.\n"


def accounts_report(store=None) -> str:
    rows = read_accounts()
    if not rows:
        return "No account is connected yet. Run 'Presence: connect an account'.\n"
    lines = ["# Accounts connected on this PC (names only)", ""]
    for a in rows:
        has = bool(get_secret(a["platform"], a["account"], store))
        lines.append(f"- {a['platform']}: {a['account']}  ({'ready' if has else 'secret missing: connect again'})")
    return "\n".join(lines) + "\n"


def run_cli(args: list[str]) -> int:
    x = args[0] if args else ""
    rest = args[1:]
    if x == "connect" and len(rest) >= 2:
        pf = rest[0]
        secret = ask_secret("Paste your LinkedIn access token" if pf == "linkedin" else "Paste the Discord webhook address", window="--terminal" not in rest)
        if not secret:
            print("Nothing entered: nothing saved.")
            return 1
        out = connect(pf, rest[1], secret)
        print(out)
        return 0 if out.startswith("Connected") else 1
    if x == "accounts":
        print(accounts_report())
        return 0
    if x == "remove" and len(rest) >= 2:
        print(remove(rest[0], rest[1]))
        return 0
    if x == "post" and rest:
        approve = rest[rest.index("--approve") + 1] if "--approve" in rest and rest.index("--approve") + 1 < len(rest) else ""
        return post_file(rest[0], approve)
    print(__doc__)
    return 0 if x in ("", "-h", "--help") else 2


if __name__ == "__main__":
    sys.exit(run_cli(sys.argv[1:]))
