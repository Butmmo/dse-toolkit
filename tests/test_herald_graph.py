"""Sending and reading through Microsoft Graph for a mailbox signed in from Citadel (dse/herald_graph.py). Nothing real is contacted.   python tests/test_herald_graph.py"""
import base64
import datetime as dt
import json
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import herald as H  # noqa: E402
from dse import herald_graph as G  # noqa: E402
from dse import herald_send as S  # noqa: E402

fails = []
DASH = chr(0x2014)
MB = "11111111-1111-4111-8111-111111111111"


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


class Api:
    url, key, token = "https://x.supabase.co", "anon-key", "t" * 40

    def __init__(self, signed=None, boom=False):
        self.signed, self.boom, self.calls = signed if signed is not None else [MB], boom, []

    def rpc(self, name, body, tries=3):
        self.calls.append(name)
        if self.boom:
            raise RuntimeError("no such function")
        return self.signed if name == "hq_herald_signed_in" else None


class Http:
    """Answers like Citadel's token function and Microsoft Graph, and remembers every request."""

    def __init__(self, token_code=200, send_code=202, send_body=b"", inbox=None, token_body=None):
        self.token_code, self.send_code, self.send_body, self.inbox = token_code, send_code, send_body, inbox or []
        self.token_body = token_body if token_body is not None else {"access_token": "AT123", "expires_in": 3600}
        self.log = []

    def __call__(self, method, url, headers, data=None, timeout=30):
        self.log.append((method, url, headers, data))
        if url.endswith("/herald-oauth-token"):
            return self.token_code, json.dumps(self.token_body).encode()
        if url.endswith("/me/sendMail"):
            return self.send_code, self.send_body
        if "/me/mailFolders/inbox?" in url:
            return 200, b"{}"
        if "/me/mailFolders/inbox/messages" in url:
            return 200, json.dumps({"value": [{"id": m["id"], "internetMessageId": m.get("mid")} for m in self.inbox]}).encode()
        if "/me/messages/" in url and url.endswith("/$value"):
            import urllib.parse as _u
            mid = _u.unquote(url.split("/me/messages/")[1].split("/")[0])
            return 200, next(m["raw"] for m in self.inbox if m["id"] == mid)
        return 404, b"{}"


def fresh(api=None):
    G._state["api"], G._state["tokens"], G._state["signed"] = api or Api(), {}, None


def msg():
    m = EmailMessage()
    m["From"], m["To"], m["Subject"], m["Message-ID"] = "ada@outlook.com", "lead@x.co", "Hello", "<abc@herald>"
    m.set_content("Hi there")
    return m


# ---- the marker
check("a signed-in mailbox's marker is recognised, a real password and nothing are not", G.is_cloud(G.cloud_secret(MB)) and not G.is_cloud("hunter2") and not G.is_cloud(None) and G.cloud_secret(MB).startswith("citadel-ms:"))
fresh()
secrets = G.with_signed_in(Api(), {"other": "pw", MB: ""})
check("a signed-in mailbox with no password here gets the marker; one that has a password keeps it; the PC's own dict is not changed", secrets[MB] == G.cloud_secret(MB) and secrets["other"] == "pw" and G.with_signed_in(Api(), {MB: "mine"})[MB] == "mine")
orig = {"a": "1"}
G.with_signed_in(Api(), orig)
check("the original secrets are left as they were", orig == {"a": "1"})
check("if Citadel does not have the sign-in update yet, or the PC is not connected, nothing breaks: no mailbox is signed in", G.signed_in_ids(Api(boom=True)) == set() and G.with_signed_in(Api(boom=True), {"x": "y"}) == {"x": "y"})

# ---- the token
fresh()
h = Http()
t1 = G.access_token(MB, now=1000, http=h)
t2 = G.access_token(MB, now=1500, http=h)
check("the PC gets an access token from Citadel with its runner token and keeps it for its life (one request, not two)", t1 == "AT123" and t2 == "AT123" and len([x for x in h.log if x[1].endswith("/herald-oauth-token")]) == 1 and json.loads(h.log[0][3])["token"] == "t" * 40 and json.loads(h.log[0][3])["mailbox_id"] == MB)
G.access_token(MB, now=1000 + 3600, http=h)
check("a token that is about to expire is asked for again", len([x for x in h.log if x[1].endswith("/herald-oauth-token")]) == 2)
fresh()
needed = False
try:
    G.access_token(MB, http=Http(token_code=409, token_body={"error": "signin_needed"}))
except G.SignInNeeded as e:
    needed = "Sign in with Microsoft" in str(e)
check("when Citadel says the sign-in no longer works, the member is told to sign in again from Citadel", needed)
fresh()
said = ""
try:
    G.access_token(MB, http=Http(token_code=401, token_body={"error": "That PC is not connected."}))
except ConnectionError as e:
    said = str(e)
check("any other refusal names Citadel's own reason, the code, and does not call a Google mailbox a Microsoft one", "401" in said and "That PC is not connected." in said and "Microsoft" not in said, said)

# ---- sending
fresh()
h = Http()
G.send_mime(MB, msg(), http=h)
sent = [x for x in h.log if x[1].endswith("/me/sendMail")][0]
check("a message is sent as MIME through Graph sendMail with the bearer token, the mail itself unchanged", sent[0] == "POST" and sent[2]["Authorization"] == "Bearer AT123" and sent[2]["Content-Type"] == "text/plain" and b"Subject: Hello" in base64.b64decode(sent[3]) and b"Message-ID: <abc@herald>" in base64.b64decode(sent[3]))


def raised(code, body=b"{}"):
    fresh()
    try:
        G.send_mime(MB, msg(), http=Http(send_code=code, send_body=body))
    except Exception as e:
        return e
    return None


check("a refused sign-in becomes the login error the sender already retries", isinstance(raised(401), smtplib.SMTPAuthenticationError) and isinstance(raised(403), smtplib.SMTPAuthenticationError))
check("a refused address becomes the recipient error (so it can count as a bounce)", isinstance(raised(400, json.dumps({"error": {"code": "ErrorInvalidRecipients", "message": "bad"}}).encode()), smtplib.SMTPRecipientsRefused))
e429, e503 = raised(429), raised(503)
check("being throttled or a server error is a temporary error (tried again), other refusals are a permanent rejection that is never a bounce", isinstance(e429, smtplib.SMTPResponseException) and e429.smtp_code == 451 and e503.smtp_code == 451 and raised(413, json.dumps({"error": {"code": "ErrorMessageSizeExceeded", "message": "big"}}).encode()).smtp_code == 554)
fresh()
class Down(Http):
    def __call__(self, method, url, headers, data=None, timeout=30):
        if "herald-oauth-token" in url:
            return super().__call__(method, url, headers, data, timeout)
        raise ConnectionError("offline")
try:
    G.send_mime(MB, msg(), http=Down())
    net = False
except ConnectionError:
    net = True
check("no network is a connection error (the sender retries without counting an attempt)", net)
fresh()
try:
    G.send_mime(MB, msg(), http=Http(token_code=404, token_body={"error": "signin_needed"}))
    login = False
except smtplib.SMTPAuthenticationError as e:
    login = b"Sign in with Microsoft" in e.smtp_error
check("a missing sign-in is reported like a bad login, with what to do", login)

# ---- the sender uses it
fresh()
h2 = Http()
G._http = h2   # the module's default transport is replaced only for this check
orig_send = G.send_mime
G.send_mime = lambda mid, m, http=h2: orig_send(mid, m, http=h2)
S._smtp_send({"id": MB, "email": "ada@outlook.com"}, G.cloud_secret(MB), msg())
G.send_mime = orig_send
check("the Herald sender uses Graph (not SMTP) for a signed-in mailbox", any(x[1].endswith("/me/sendMail") for x in h2.log))
d = S.deliver({"id": "q1", "mailbox": {"id": MB, "email": "ada@outlook.com", "display_name": "Ada", "provider": "outlook", "smtp_host": "x", "smtp_port": 465}, "to_email": "lead@x.co", "subject": "Hi", "body": "Hello", "unsub_token": "u" * 24, "step": 1},
              G.cloud_secret(MB), dt.datetime(2026, 11, 17, 9, 0, tzinfo=dt.timezone.utc), send=lambda m, pw, ms: (_ for _ in ()).throw(smtplib.SMTPAuthenticationError(535, b"sign in again")))
check("a failed Graph login comes back as a retry that does not count as an attempt and says so without any token in it", d["status"] == "retry" and d.get("auth") is True and "AT123" not in json.dumps(d))

# ---- reading replies
fresh()
raw1 = b"From: lead@x.co\r\nSubject: Re: Hello\r\nMessage-ID: <r1@x>\r\n\r\nYes please"
raw2 = b"From: other@x.co\r\nSubject: Hi\r\n\r\n" + b"x" * 50000
h3 = Http(inbox=[{"id": "AAA=", "mid": "<r1@x>", "raw": raw1}, {"id": "BBB=", "mid": "<r2@x>", "raw": raw2}, {"id": "CCC=", "mid": "<seen@x>", "raw": raw1}])
got = G.fetch_new({"id": MB, "email": "ada@outlook.com"}, dt.date(2026, 11, 15), {"<seen@x>"}, http=h3)
check("new inbox messages are read as raw mail, ones already seen are skipped, and a long message is cut to the start only", [k for k, _ in got] == ["<r1@x>", "<r2@x>"] and got[0][1] == raw1 and len(got[1][1]) == G.MAX_RAW)
lst = [x for x in h3.log if "/me/mailFolders/inbox/messages" in x[1]][0]
check("the inbox is asked only for messages since the date, newest first, and nothing is changed (only GET requests)", "receivedDateTime+ge+2026-11-15" in lst[1] and all(x[0] in ("GET", "POST") and (x[0] == "GET" or x[1].endswith(("/herald-oauth-token",))) for x in h3.log))
ev = S.classify(raw1, {"lead@x.co"})
check("a reply read this way is understood by the same reader as one read over IMAP", ev is not None and ev.get("kind") == "reply")
fresh()
try:
    G.fetch_new({"id": MB}, dt.date(2026, 11, 15), set(), http=Http(inbox=[]) if False else type("H", (Http,), {"__call__": lambda self, m, u, h, d=None, t=30: (401, b"{}") if "inbox" in u else Http.__call__(self, m, u, h, d, t)})())
    again = False
except G.SignInNeeded:
    again = True
check("a refused inbox read asks for a new sign-in", again)

# ---- testing and reporting
fresh()
r = G.test(MB, http=Http())
check("the test says ready when Citadel gives a token and Graph answers, without sending or changing anything", r["status"] == "ready" and r["secret_set"] is True and r["smtp"] and r["imap"])
fresh()
check("the test says what to do when the sign-in is gone", G.test(MB, http=Http(token_code=409, token_body={"error": "signin_needed"}))["status"] == "error")
pay = H.status_payload([{"id": MB, "email": "ada@outlook.com"}, {"id": "other", "email": "o@x.co"}], signed={MB})
check("Citadel is told a signed-in mailbox has a login (so it shows as set up) and one that is not signed in does not", pay[MB]["secret_set"] is True and "Signed in with Microsoft" in pay[MB]["note"] and pay["other"]["secret_set"] is False)

# ---- Google: sending through the Gmail API (sending only)
class GHttp(Http):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.token_body = {"access_token": "GAT", "expires_in": 3600, "provider": "google"}
        self.gmail_code, self.gmail_body = 200, b"{}"

    def __call__(self, method, url, headers, data=None, timeout=30):
        if url.startswith(G.GMAIL_SEND):
            self.log.append((method, url, headers, data))
            return self.gmail_code, self.gmail_body
        return super().__call__(method, url, headers, data, timeout)


fresh()
gh = GHttp()
G.send_mime(MB, msg(), http=gh)
gsent = [x for x in gh.log if x[1] == G.GMAIL_SEND][0]
raw64 = json.loads(gsent[3])["raw"]
check("for a Google mailbox the message goes to the Gmail API as url-safe base64 MIME (the mail itself unchanged) with the bearer token, not to Microsoft Graph", gsent[0] == "POST" and gsent[2]["Authorization"] == "Bearer GAT" and gsent[2]["Content-Type"] == "application/json" and b"Subject: Hello" in base64.urlsafe_b64decode(raw64 + "=" * (-len(raw64) % 4)) and not any(x[1].endswith("/me/sendMail") for x in gh.log) and G.provider_of(MB) == "google")


def graised(code, body=b"{}"):
    fresh()
    h = GHttp()
    h.gmail_code, h.gmail_body = code, body
    try:
        G.send_mime(MB, msg(), http=h)
    except Exception as e:
        return e
    return None


check("Gmail refusals become the same errors as for Microsoft: a refused sign-in is a login error, a bad address is a recipient error, throttling is temporary, the rest is a permanent rejection", isinstance(graised(401), smtplib.SMTPAuthenticationError) and isinstance(graised(400, json.dumps({"error": {"code": 400, "message": "Invalid To header", "status": "INVALID_ARGUMENT"}}).encode()), smtplib.SMTPRecipientsRefused) and graised(429).smtp_code == 451 and graised(503).smtp_code == 451 and graised(400, json.dumps({"error": {"message": "Bad thing"}}).encode()).smtp_code == 554)
fresh()
gh2 = GHttp()
check("a Google mailbox reads no replies here (the permission to read is restricted): the read is empty and changes nothing", G.fetch_new({"id": MB}, dt.date(2026, 11, 20), set(), http=gh2) == [] and not any("/messages" in x[1] and "gmail" in x[1] for x in gh2.log))
fresh()
tg = G.test(MB, http=GHttp())
check("the test of a Google sign-in says ready for sending, and says plainly that replies are read in Gmail itself", tg["status"] == "ready" and tg["smtp"] is True and tg["imap"] is None and "Replies are read in Gmail" in tg["note"])
fresh()
check("a Microsoft sign-in is still tested through Graph (the provider decides, not a setting)", G.test(MB, http=Http())["imap"] is True)
check("the marker is never written to disk and no token appears in the module", "write_text" not in (ROOT / "dse" / "herald_graph.py").read_text(encoding="utf-8") and "print(" not in (ROOT / "dse" / "herald_graph.py").read_text(encoding="utf-8"))
check("no em dash", DASH not in (ROOT / "dse" / "herald_graph.py").read_text(encoding="utf-8") + Path(__file__).read_text(encoding="utf-8"))
print("\nALL PASS" if not fails else f"\n{len(fails)} FAILED: " + ", ".join(fails))
sys.exit(1 if fails else 0)
