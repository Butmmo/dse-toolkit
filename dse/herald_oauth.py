"""Herald: sign in with Google or Microsoft instead of an app password (OAuth 2.0, on your PC).

Why: Google hides app passwords for many accounts (no 2-Step Verification, passkeys only, Workspace). Signing in with Google needs no app password: you approve Herald once in your browser,
and Google gives this PC a long-lasting token that can send and read this one mailbox.

How it stays private (the same promise as the password):
  * The sign-in runs on THIS PC. A small web page listens on 127.0.0.1 (this computer only) for Google's answer; nothing passes through Citadel or the runner.
  * The token and your Google client details are stored in data/herald/secrets.dat under Windows' own protection, like a password. Citadel only ever learns "a login is set" and the test result.
  * The token is checked to belong to the SAME address as the mailbox before it is saved.
  * It uses PKCE and a random "state", the standard protections for a desktop sign-in.

You set Google up once (about ten minutes, free): a Google Cloud project with an OAuth "Desktop app" client. Microsoft (Outlook.com, Hotmail, Microsoft 365) is the same idea: a free Microsoft Entra
"app registration" for a public client (no client secret needed). The Herald page walks through both. Stdlib only.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import re
import secrets as _secrets
import smtplib
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "openid email https://mail.google.com/"      # mail.google.com is what Gmail's IMAP and SMTP accept for OAuth
PREFIX = "oauth1:"
CLIENT_KEY = "_google_client"
MARKER = "[google-sign-in]"                          # lets herald.explain() tell a Google sign-in failure from a wrong password
SKEW_S = 90

# Each way of signing in. "common" lets both personal accounts (Outlook.com, Hotmail) and work or school accounts (Microsoft 365) sign in. The Outlook scopes are what Microsoft's own IMAP and SMTP accept.
PROVIDERS = {
    "google": {"name": "Google", "auth": AUTH_URL, "token": TOKEN_URL, "scope": SCOPE, "client_key": CLIENT_KEY, "marker": MARKER, "redirect_host": "127.0.0.1", "secret_needed": True},
    "microsoft": {"name": "Microsoft", "auth": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize", "token": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                  "scope": "offline_access openid email https://outlook.office.com/IMAP.AccessAsUser.All https://outlook.office.com/SMTP.Send", "client_key": "_microsoft_client",
                  "marker": "[microsoft-sign-in]", "redirect_host": "localhost", "secret_needed": False},
}
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def provider_of(secret: str) -> str:
    """Which way a saved sign-in was made. Sign-ins saved before Microsoft existed have no label and are Google's."""
    try:
        p = json.loads(secret[len(PREFIX):]).get("p", "google")
    except (ValueError, AttributeError):
        return "google"
    return p if p in PROVIDERS else "google"


class OAuthRevoked(smtplib.SMTPAuthenticationError):
    """Google or Microsoft no longer accepts the saved sign-in (removed in the account, expired, or the client was deleted): sign in again."""
    def __init__(self, why: str = "", provider: str = "google"):
        self.provider = provider
        super().__init__(535, f"{PROVIDERS.get(provider, PROVIDERS['google'])['marker']} {why}".encode("utf-8"))


class OAuthNetwork(OSError):
    """The sign-in service could not be reached to refresh the token: a temporary problem, the email is retried later."""


class OAuthSetupError(ValueError):
    """Something in the one-time sign-in is wrong (client details, wrong account, no long-lasting token). The message says what to do."""


# ------------------------------------------------------------------ what is stored

def is_oauth(secret: str | None) -> bool:
    return bool(secret) and str(secret).startswith(PREFIX)


def pack(client_id: str, client_secret: str, refresh_token: str, email: str, provider: str = "google") -> str:
    d = {"cid": client_id, "cs": client_secret, "rt": refresh_token, "email": email.lower()}
    if provider != "google":
        d["p"] = provider                    # Google sign-ins keep the exact old format
    return PREFIX + json.dumps(d, separators=(",", ":"))


def unpack(secret: str) -> dict:
    try:
        d = json.loads(secret[len(PREFIX):])
        if not (isinstance(d, dict) and d.get("cid") and d.get("rt") and d.get("email")):
            raise ValueError
        return d
    except ValueError:
        raise OAuthRevoked("the saved sign-in is damaged", provider_of(secret)) from None


def pack_client(client_id: str, client_secret: str) -> str:
    return json.dumps({"cid": client_id.strip(), "cs": client_secret.strip()}, separators=(",", ":"))


def unpack_client(raw: str | None, provider: str = "google") -> dict | None:
    try:
        d = json.loads(raw or "")
    except ValueError:
        return None
    if not (isinstance(d, dict) and d.get("cid")):
        return None
    if PROVIDERS[provider]["secret_needed"] and not d.get("cs"):
        return None
    d.setdefault("cs", "")
    return d


def ms_client_ok(client_id: str, client_secret: str = "") -> str:
    """The problem with Microsoft app details, or '' when they look right. The Application (client) ID is a GUID; a public client has no secret, so none is needed."""
    if not GUID.match(client_id.strip()):
        return "The Application (client) ID looks like 8f2c1a3e-4b5d-4e6f-9a7b-1c2d3e4f5a6b: copy it from the app's Overview page in Microsoft Entra."
    if client_secret.strip() and len(client_secret.strip()) < 10:
        return "Leave the secret empty (a public client needs none), or paste the whole secret value."
    return ""


def client_ok(client_id: str, client_secret: str) -> str:
    """The problem with Google client details, or '' when they look right. (Google's client ids end in .apps.googleusercontent.com.)"""
    if not client_id.strip().endswith(".apps.googleusercontent.com"):
        return "A client ID ends in .apps.googleusercontent.com: copy it from Google Cloud, Credentials."
    if len(client_secret.strip()) < 10:
        return "The client secret is the other value on the same Google Cloud screen (it starts with GOCSPX-)."
    return ""


# ------------------------------------------------------------------ talking to Google

def _post_form(url: str, data: dict, timeout: int = 20) -> dict:
    data = {k: v for k, v in data.items() if v != ""}          # a public Microsoft client sends no secret
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode("ascii"), headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
        except ValueError:
            body = {}
        body.setdefault("error", f"http_{e.code}")
        return body
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise OAuthNetwork(f"Could not reach the sign-in service: {e}") from e


_CACHE: dict[str, tuple[str, float]] = {}


def access_token(secret: str, now: float | None = None, post=_post_form) -> str:
    """A fresh access token for the saved sign-in (kept in memory for about an hour). Raises OAuthRevoked when Google says the sign-in is no longer valid, OAuthNetwork when Google cannot be reached."""
    d = unpack(secret)
    now = time.time() if now is None else now
    key = hashlib.sha256(d["rt"].encode("utf-8")).hexdigest()
    hit = _CACHE.get(key)
    if hit and hit[1] - SKEW_S > now:
        return hit[0]
    prov = provider_of(secret)
    P = PROVIDERS[prov]
    form = {"client_id": d["cid"], "client_secret": d.get("cs", ""), "refresh_token": d["rt"], "grant_type": "refresh_token"}
    if prov == "microsoft":
        form["scope"] = P["scope"]
    r = post(P["token"], form)
    if r.get("access_token"):
        _CACHE[key] = (r["access_token"], now + float(r.get("expires_in", 3600)))
        return r["access_token"]
    err = str(r.get("error", ""))
    if err in ("invalid_grant", "invalid_client", "unauthorized_client", "access_denied", "interaction_required", "consent_required"):
        hint = ""
        if err == "invalid_grant" and prov == "google":
            hint = " (if the Google Cloud app is still in Testing mode, its sign-ins expire after 7 days: publish it)"
        elif prov == "microsoft":
            hint = " (the password may have changed, or an administrator may need to allow the app: sign in again)"
        raise OAuthRevoked(f"{P['name']} says this sign-in is no longer valid" + hint, prov)
    raise OAuthNetwork(f"{P['name']} did not give a token ({err or 'no answer'}).")


def xoauth2(email: str, token: str) -> str:
    return f"user={email}\x01auth=Bearer {token}\x01\x01"


# ------------------------------------------------------------------ logging in: password or Google, one place

_HOSTS = {"google": (".gmail.com", ".googlemail.com", ".google.com"), "microsoft": (".office365.com", ".outlook.com", ".office.com", ".hotmail.com", ".live.com")}


def _own_server(secret: str, host: str) -> None:
    """A Google or Microsoft sign-in token is only ever handed to that provider's own mail servers, whatever host Citadel says (so a changed host setting cannot collect it)."""
    prov = provider_of(secret)
    h = ("." + str(host or "").lower().strip().rstrip("."))
    if not any(h.endswith(suffix) for suffix in _HOSTS[prov]):
        raise OAuthRevoked(f"the mail server {host!r} is not {PROVIDERS[prov]['name']}'s, so the sign-in was not sent to it. Check the server in the mailbox settings", prov)


def smtp_auth(s, m: dict, secret: str) -> None:
    """Logs an open SMTP connection in: with Google's token when the secret is a Google sign-in, otherwise with the password."""
    if not is_oauth(secret):
        s.login(m.get("username") or m["email"], secret)
        return
    _own_server(secret, m.get("smtp_host", ""))
    getattr(s, "ehlo_or_helo_if_needed", lambda: None)()          # smtplib's auth() does not say hello first, and an SSL connection has not yet
    d = unpack(secret)
    line = xoauth2(d["email"], access_token(secret))
    try:
        s.auth("XOAUTH2", lambda challenge=None: line if challenge is None else "", initial_response_ok=True)
    except smtplib.SMTPAuthenticationError as e:
        _CACHE.clear()
        raise OAuthRevoked(f"{PROVIDERS[provider_of(secret)]['name']} refused the sign-in token", provider_of(secret)) from e


def imap_auth(box, m: dict, secret: str) -> None:
    if not is_oauth(secret):
        box.login(m.get("username") or m["email"], secret)
        return
    _own_server(secret, m.get("imap_host", ""))
    d = unpack(secret)
    line = xoauth2(d["email"], access_token(secret)).encode("utf-8")
    try:
        box.authenticate("XOAUTH2", lambda _x: line)
    except Exception as e:                  # imaplib.IMAP4.error and friends
        if e.__class__.__name__ in ("error", "abort", "readonly"):
            _CACHE.clear()
            raise OAuthRevoked(f"{PROVIDERS[provider_of(secret)]['name']} refused the sign-in token", provider_of(secret)) from e
        raise


# ------------------------------------------------------------------ the one-time sign-in

def pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(_secrets.token_bytes(48)).decode("ascii").rstrip("=")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    return verifier, challenge


def build_auth_url(client_id: str, redirect_uri: str, state: str, challenge: str, login_hint: str, provider: str = "google") -> str:
    P = PROVIDERS[provider]
    q = {"client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": P["scope"], "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
         "prompt": "consent", "login_hint": login_hint}
    if provider == "google":
        q["access_type"] = "offline"
    return P["auth"] + "?" + urllib.parse.urlencode(q)


class Loopback:
    """A one-time web page on THIS computer only (127.0.0.1) that catches Google's answer after you approve in the browser."""
    PAGE = b"<!doctype html><meta charset=utf-8><title>Herald</title><body style='font-family:sans-serif;max-width:32rem;margin:4rem auto'><h2>You can close this tab.</h2><p>Herald received the answer. Go back to the window on your PC.</p></body>"

    def __init__(self, host: str = "127.0.0.1"):
        outer = self
        self.params: dict = {}
        self._done = threading.Event()

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):               # noqa: N802
                q = urllib.parse.urlparse(self.path)
                if q.path == "/" and ("code" in q.query or "error" in q.query):
                    outer.params = {k: v[0] for k, v in urllib.parse.parse_qs(q.query).items()}
                    outer._done.set()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(Loopback.PAGE)

            def log_message(self, *a):      # silent
                pass

        self._srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        self.redirect_uri = f"http://{host}:{self._srv.server_address[1]}"      # Microsoft wants the word localhost; the page still listens on this computer only
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()

    def wait(self, timeout: float = 300) -> dict:
        self._done.wait(timeout)
        self.close()
        return self.params

    def close(self) -> None:
        try:
            self._srv.shutdown()
            self._srv.server_close()
        except Exception:
            pass


def _id_token_claims(id_token: str) -> dict:
    try:
        body = id_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode("utf-8"))
    except (IndexError, ValueError):
        return {}


def run_flow(email: str, client: dict, loop=None, opener=webbrowser.open, post=_post_form, out=print, timeout: float = 300, provider: str = "google") -> str:
    """Opens Google or Microsoft in the browser, waits for the approval, checks the account is the mailbox's own, and returns the secret to store. Raises OAuthSetupError with what to do when it cannot."""
    P = PROVIDERS[provider]
    name = P["name"]
    loop = loop or Loopback(P["redirect_host"])
    verifier, challenge = pkce()
    state = _secrets.token_urlsafe(24)
    url = build_auth_url(client["cid"], loop.redirect_uri, state, challenge, email, provider)
    out(f"Opening {name} in your browser. Choose the account " + email + " and press Allow.")
    out("If nothing opens, copy this address into your browser:\n" + url)
    try:
        opener(url)
    except Exception:
        pass
    params = loop.wait(timeout)
    if not params:
        raise OAuthSetupError(f"Nothing came back from {name} in time. Run it again and press Allow in the browser.")
    if params.get("error"):
        raise OAuthSetupError(f"{name} did not allow it (" + params["error"] + "). Run it again and press Allow.")
    if params.get("state") != state:
        raise OAuthSetupError("The answer did not match this sign-in, so it was refused. Run it again.")
    form = {"code": params.get("code", ""), "client_id": client["cid"], "client_secret": client.get("cs", ""), "redirect_uri": loop.redirect_uri, "grant_type": "authorization_code", "code_verifier": verifier}
    if provider == "microsoft":
        form["scope"] = P["scope"]
    r = post(P["token"], form)
    if not r.get("access_token"):
        err = str(r.get("error", "no answer"))
        where = "Google Cloud, Credentials" if provider == "google" else "Microsoft Entra, the app's Overview page"
        hint = f" Check the client ID{' and secret' if provider == 'google' else ''} ({where})." if err in ("invalid_client", "unauthorized_client") else ""
        raise OAuthSetupError(f"{name} would not finish the sign-in ({err}).{hint}")
    claims = _id_token_claims(str(r.get("id_token", "")))
    got = str(claims.get("email") or (claims.get("preferred_username") if provider == "microsoft" else "") or "").lower()
    if not got:
        raise OAuthSetupError(f"{name} did not say which account signed in. Run it again.")
    if got != email.lower():
        raise OAuthSetupError(f"You signed in as {got}, but this mailbox is {email.lower()}. Run it again and choose {email.lower()}.")
    if not r.get("refresh_token"):
        raise OAuthSetupError("Google did not give a long-lasting sign-in. Remove Herald at myaccount.google.com/permissions, then run it again." if provider == "google" else "Microsoft did not give a long-lasting sign-in. Run it again and accept every permission it lists.")
    return pack(client["cid"], client.get("cs", ""), r["refresh_token"], email, provider)
