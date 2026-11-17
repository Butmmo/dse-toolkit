"""Herald: send and read through Microsoft Graph for a mailbox you signed in with Microsoft from Citadel (17 Nov 2026).

The member presses "Sign in with Microsoft" on the mailbox in Citadel. Citadel keeps an encrypted token; this PC asks Citadel for a short-lived access token each time it needs one (the runner token proves the PC),
and uses Microsoft Graph over HTTPS: no SMTP, no app password, nothing for Microsoft to block as a "less secure app". The refresh token never reaches this PC.

To the rest of Herald a signed-in mailbox looks like a mailbox with a password: its "secret" is the marker  citadel-ms:<mailbox id>  (never stored on disk). Sending and reading notice the marker and use Graph;
everything else (limits, windows, warmup, bounces, replies) is unchanged. Graph errors are turned into the same smtplib errors the sender already understands. Stdlib only.
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import smtplib
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage

SENTINEL = "citadel-ms:"
GRAPH = "https://graph.microsoft.com/v1.0"
TIMEOUT = 30
MAX_NEW = 300                      # at most this many NEW messages per read, oldest first; the rest are read on the next pass
MAX_RAW = 20000                    # the same idea as the IMAP reader: only the start of each message is needed

_state: dict = {"api": None, "tokens": {}, "signed": None}


class Batch(list):
    """New messages found by one read. capped is True when there were more than the cap."""
    capped = False


class SignInNeeded(Exception):
    """Citadel has no working Microsoft sign-in for this mailbox: sign in again from Citadel (Herald > Mailboxes)."""


def is_cloud(secret) -> bool:
    return isinstance(secret, str) and secret.startswith(SENTINEL)


def cloud_secret(mailbox_id: str) -> str:
    return SENTINEL + mailbox_id


def set_api(api) -> None:
    _state["api"] = api
    _state["signed"] = None


def _api():
    if _state["api"] is None:
        from . import crmsync
        _state["api"] = crmsync.connect()
    return _state["api"]


def signed_in_ids(api=None) -> set[str]:
    """The mailboxes of this member that are signed in through Citadel. Empty when this PC is not connected or Citadel does not have the sign-in update yet."""
    api = api or _api()
    if api is None:
        return set()
    try:
        return {str(x).lower() for x in (api.rpc("hq_herald_signed_in", {}) or [])}
    except Exception:
        return set()


def with_signed_in(api, secrets: dict) -> dict:
    """A copy of the PC's secrets with the marker added for every mailbox signed in through Citadel that has no password here."""
    out = dict(secrets)
    for mid in signed_in_ids(api):
        if not out.get(mid):
            out[mid] = cloud_secret(mid)
    return out


def cloud_if_signed(mailbox_id: str) -> str | None:
    return cloud_secret(mailbox_id) if mailbox_id.lower() in signed_in_ids() else None


def _http(method: str, url: str, headers: dict, data: bytes | None = None, timeout: int = TIMEOUT) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ConnectionError(str(e)) from None


def access_token(mailbox_id: str, now: float | None = None, http=_http) -> str:
    """A Graph access token for the mailbox, from Citadel (kept for its lifetime, less two minutes)."""
    now = time.time() if now is None else now
    have = _state["tokens"].get(mailbox_id)
    if have and have[1] - 120 > now:
        return have[0]
    api = _api()
    if api is None:
        raise SignInNeeded("This PC is not connected to Citadel.")
    body = json.dumps({"token": api.token, "mailbox_id": mailbox_id}).encode("utf-8")
    code, raw = http("POST", f"{api.url}/functions/v1/herald-oauth-token", {"Content-Type": "application/json", "apikey": api.key, "Authorization": f"Bearer {api.key}"}, body)
    try:
        data = json.loads(raw.decode("utf-8", "replace")) if raw else {}
    except ValueError:
        data = {}
    if code == 200 and data.get("access_token"):
        _state["tokens"][mailbox_id] = (data["access_token"], now + int(data.get("expires_in", 3600)))
        return data["access_token"]
    if code in (404, 409) or data.get("error") == "signin_needed":
        raise SignInNeeded("The Microsoft sign-in for this mailbox needs doing again: open Herald > Mailboxes in Citadel and press Sign in with Microsoft.")
    raise ConnectionError(f"Citadel could not give a Microsoft token ({code}).")


def _graph_error(raw: bytes) -> tuple[str, str]:
    try:
        e = json.loads(raw.decode("utf-8", "replace")).get("error", {})
        return str(e.get("code", "")), str(e.get("message", ""))[:200]
    except (ValueError, AttributeError):
        return "", ""


def send_mime(mailbox_id: str, msg: EmailMessage, http=_http) -> None:
    """Sends the message from the signed-in mailbox. Problems are raised as the smtplib errors the sender already knows how to handle."""
    try:
        token = access_token(mailbox_id, http=http)
    except SignInNeeded as e:
        raise smtplib.SMTPAuthenticationError(535, str(e).encode("utf-8")) from None
    code, raw = http("POST", f"{GRAPH}/me/sendMail", {"Authorization": f"Bearer {token}", "Content-Type": "text/plain"}, base64.b64encode(msg.as_bytes()))
    if code in (200, 202):
        return
    _state["tokens"].pop(mailbox_id, None)
    ecode, text = _graph_error(raw)
    if code in (401, 403):
        raise smtplib.SMTPAuthenticationError(535, f"Microsoft refused the sign-in ({ecode or code}): sign in again from Citadel.".encode("utf-8"))
    if code == 400 and "Recipient" in ecode:
        raise smtplib.SMTPRecipientsRefused({"recipient": (550, f"Microsoft refused the address: {text}".encode("utf-8"))})
    if code == 429 or code >= 500:
        raise smtplib.SMTPResponseException(451, f"Microsoft is busy ({code}); tried again later.".encode("utf-8"))
    raise smtplib.SMTPResponseException(554, f"Microsoft rejected the email ({ecode or code}): {text}".encode("utf-8"))


def fetch_new(m: dict, since: dt.date, seen: set[str], http=_http, limit: int = MAX_NEW) -> list[tuple[str, bytes]]:
    """New inbox messages since a date, as the start of each raw message, without changing anything in the mailbox."""
    token = access_token(m["id"], http=http)
    h = {"Authorization": f"Bearer {token}"}
    q = urllib.parse.urlencode({"$top": "50", "$orderby": "receivedDateTime asc", "$select": "id,internetMessageId", "$filter": f"receivedDateTime ge {since.isoformat()}T00:00:00Z"})
    url = f"{GRAPH}/me/mailFolders/inbox/messages?{q}"
    out = Batch()
    while url:
        code, raw = http("GET", url, h)
        if code != 200:
            ecode, text = _graph_error(raw)
            if code in (401, 403):
                _state["tokens"].pop(m["id"], None)
                raise SignInNeeded("Microsoft refused the sign-in: sign in again from Citadel.")
            raise ConnectionError(f"Microsoft could not list the inbox ({ecode or code}).")
        data = json.loads(raw.decode("utf-8", "replace"))
        for it in data.get("value", []):
            key = it.get("internetMessageId") or f"{m['id']}:{it.get('id')}"
            if key in seen:
                continue
            if len(out) >= limit:
                out.capped = True
                return out
            c2, body = http("GET", f"{GRAPH}/me/messages/{urllib.parse.quote(it['id'], safe='')}/$value", h)
            if c2 == 200:
                out.append((key, body[:MAX_RAW]))
        url = data.get("@odata.nextLink")
    return out


def test(mailbox_id: str, http=_http) -> dict:
    """Checks the sign-in works: a token from Citadel, and Graph answers for the inbox. Sends and changes nothing."""
    try:
        token = access_token(mailbox_id, http=http)
    except SignInNeeded as e:
        return {"status": "error", "secret_set": True, "smtp": False, "imap": False, "note": str(e)}
    except ConnectionError as e:
        return {"status": "error", "secret_set": True, "smtp": None, "imap": None, "note": str(e)}
    code, raw = http("GET", f"{GRAPH}/me/mailFolders/inbox?$select=id", {"Authorization": f"Bearer {token}"})
    if code == 200:
        return {"status": "ready", "secret_set": True, "smtp": True, "imap": True, "note": "Signed in with Microsoft: this mailbox can send and read through Microsoft."}
    ecode, text = _graph_error(raw)
    return {"status": "error", "secret_set": True, "smtp": False, "imap": False, "note": f"Microsoft did not accept the sign-in ({ecode or code}). Sign in again from Citadel."}
