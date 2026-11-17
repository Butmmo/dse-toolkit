"""Tests for Herald's sign in with Google (dse/herald_oauth.py and how the rest of Herald uses it).   python tests/test_herald_oauth.py
Nothing real is contacted: Google, the browser and the mail servers are replaced by fakes (the only real thing is a tiny web page on 127.0.0.1)."""
import base64
import hashlib
import imaplib
import json
import shutil
import smtplib
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import herald as H  # noqa: E402
from dse import herald_oauth as O  # noqa: E402

fails = []
DASH = chr(0x2014)


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


tmp = Path(tempfile.mkdtemp())
H.DATA = tmp / "herald"
H.MAILBOXES = H.DATA / "mailboxes.json"
H.SECRETS = H.DATA / "secrets.dat"
H.STATUS = H.DATA / "status.json"

CLIENT = {"cid": "123-abc.apps.googleusercontent.com", "cs": "GOCSPX-supersecretvalue"}
EMAIL = "ada@gmail.com"
RT = "1//refresh-token-SECRET"
M = {"id": "m1", "email": EMAIL, "provider": "google", "username": EMAIL, "smtp_host": "smtp.gmail.com", "smtp_port": 465, "smtp_security": "ssl", "imap_host": "imap.gmail.com", "imap_port": 993}


def idtoken(email):
    body = base64.urlsafe_b64encode(json.dumps({"email": email, "email_verified": True}).encode()).decode().rstrip("=")
    return f"x.{body}.y"


try:
    # ---- what is stored
    b = O.pack(CLIENT["cid"], CLIENT["cs"], RT, "ADA@gmail.com")
    check("a Google sign-in is stored with its own prefix and reads back, with the address in lower case", O.is_oauth(b) and O.unpack(b)["email"] == EMAIL and O.unpack(b)["rt"] == RT and not O.is_oauth("a-normal-app-password") and not O.is_oauth(None))
    try:
        O.unpack(O.PREFIX + "{not json")
        dmg = None
    except Exception as e:
        dmg = e
    check("a damaged stored sign-in says to sign in again instead of crashing", isinstance(dmg, O.OAuthRevoked) and "damaged" in str(dmg))
    check("client details are checked before they are saved", O.client_ok(CLIENT["cid"], CLIENT["cs"]) == "" and "apps.googleusercontent.com" in O.client_ok("12345", CLIENT["cs"]) and "GOCSPX" in O.client_ok(CLIENT["cid"], "short"))
    check("client details pack and unpack", O.unpack_client(O.pack_client(CLIENT["cid"], CLIENT["cs"])) == CLIENT and O.unpack_client("nonsense") is None and O.unpack_client(None) is None)

    # ---- PKCE and the address
    v, c = O.pkce()
    check("the PKCE challenge is the SHA-256 of the verifier, so only this PC can finish the sign-in", c == base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("=") and len(v) >= 43)
    u = urllib.parse.urlparse(O.build_auth_url(CLIENT["cid"], "http://127.0.0.1:5555", "st", "ch", EMAIL))
    q = {k: x[0] for k, x in urllib.parse.parse_qs(u.query).items()}
    check("the address asks for offline access, one mail scope, S256, the right account and a state", u.netloc == "accounts.google.com" and q["access_type"] == "offline" and q["prompt"] == "consent" and q["code_challenge_method"] == "S256" and q["login_hint"] == EMAIL and q["state"] == "st"
          and q["scope"] == "openid email https://mail.google.com/" and q["redirect_uri"] == "http://127.0.0.1:5555" and q["response_type"] == "code")

    # ---- the one-time sign-in, with a fake browser, Loopback and Google
    class FakeLoop:
        redirect_uri = "http://127.0.0.1:5555"

        def __init__(self, mutate=None):
            self.mutate, self.url = mutate, None

        def wait(self, timeout=0):
            st = urllib.parse.parse_qs(urllib.parse.urlparse(self.url).query)["state"][0]
            p = {"code": "AUTHCODE", "state": st}
            return self.mutate(p) if self.mutate else p

    def run(mutate=None, token=None, email=EMAIL):
        loop = FakeLoop(mutate)
        posts = []

        def post(url, data):
            posts.append(data)
            return token if token is not None else {"access_token": "AT", "refresh_token": RT, "id_token": idtoken(email), "expires_in": 3600}
        try:
            r = O.run_flow(EMAIL, CLIENT, loop=loop, opener=lambda url: setattr(loop, "url", url), post=post, out=lambda *a: None)
        except O.OAuthSetupError as e:
            return str(e), posts
        return r, posts

    r, posts = run()
    check("a good sign-in returns the stored bundle for that address", O.is_oauth(r) and O.unpack(r)["rt"] == RT and O.unpack(r)["email"] == EMAIL)
    check("the code is exchanged with the PKCE verifier and the client details, nothing else", posts[0]["grant_type"] == "authorization_code" and posts[0]["code"] == "AUTHCODE" and posts[0]["client_id"] == CLIENT["cid"] and len(posts[0]["code_verifier"]) >= 43)
    check("an answer with the wrong state is refused before anything is asked of Google", "did not match" in run(lambda p: {**p, "state": "forged"})[0] and run(lambda p: {**p, "state": "forged"})[1] == [])
    check("a different Google account than the mailbox is refused and named", "bola@gmail.com" in run(email="bola@gmail.com")[0] and "ada@gmail.com" in run(email="bola@gmail.com")[0])
    check("Google saying no, or nothing coming back, is explained", "press Allow" in run(lambda p: {"error": "access_denied"})[0] and "Nothing came back" in run(lambda p: {})[0])
    check("no long-lasting token tells you how to remove Herald and try again", "myaccount.google.com/permissions" in run(token={"access_token": "AT", "id_token": idtoken(EMAIL)})[0])
    check("wrong client details are named as such", "client ID and secret" in run(token={"error": "invalid_client"})[0])

    # ---- tokens
    secret = O.pack(CLIENT["cid"], CLIENT["cs"], RT, EMAIL)
    calls = []

    def refresh(url, data):
        calls.append(data)
        return {"access_token": "ACCESS-1", "expires_in": 3600}
    O._CACHE.clear()
    t1 = O.access_token(secret, now=1000.0, post=refresh)
    t2 = O.access_token(secret, now=1500.0, post=refresh)
    t3 = O.access_token(secret, now=1000.0 + 3600 - 30, post=refresh)
    check("a token is fetched once and reused until shortly before it expires, then fetched again", t1 == t2 == "ACCESS-1" and len(calls) == 2 and calls[0]["grant_type"] == "refresh_token" and calls[0]["refresh_token"] == RT)

    def revoked(url, data):
        return {"error": "invalid_grant"}
    O._CACHE.clear()
    try:
        O.access_token(secret, now=5000.0, post=revoked)
        got = None
    except Exception as e:
        got = e
    check("a revoked or expired sign-in is an authentication failure that mentions the 7-day Testing limit", isinstance(got, smtplib.SMTPAuthenticationError) and isinstance(got, O.OAuthRevoked) and "Testing" in str(got))

    def busy(url, data):
        return {"error": "temporarily_unavailable"}
    O._CACHE.clear()
    try:
        O.access_token(secret, now=9000.0, post=busy)
        got = None
    except Exception as e:
        got = e
    check("Google being busy is a temporary network-style problem, not a revoked sign-in", isinstance(got, O.OAuthNetwork) and isinstance(got, OSError) and not isinstance(got, smtplib.SMTPAuthenticationError))
    check("the XOAUTH2 line is exactly what Gmail expects", O.xoauth2(EMAIL, "TOK") == "user=ada@gmail.com\x01auth=Bearer TOK\x01\x01")

    # ---- logging in: password or Google, one place
    class Smtp:
        def __init__(self, fail=False):
            self.log, self.fail = [], fail

        def login(self, u, p):
            self.log.append(("login", u, p))

        def auth(self, mech, obj, initial_response_ok=True):
            self.log.append(("auth", mech, obj(None), obj("challenge")))
            if self.fail:
                raise smtplib.SMTPAuthenticationError(535, b"bad token")

    class Imap:
        def __init__(self, fail=False):
            self.log, self.fail = [], fail

        def login(self, u, p):
            self.log.append(("login", u, p))

        def authenticate(self, mech, cb):
            self.log.append(("auth", mech, cb(b"")))
            if self.fail:
                raise imaplib.IMAP4.error("AUTHENTICATE failed")
    O._CACHE.clear()
    s1 = Smtp()
    O.smtp_auth(s1, M, "plain-app-password")
    check("an app password still logs in the ordinary way", s1.log == [("login", EMAIL, "plain-app-password")])
    s2 = Smtp()
    real = O.access_token
    O.access_token = lambda sec, now=None, post=None: "LIVE-TOKEN"
    O.smtp_auth(s2, M, secret)
    check("a Google sign-in logs SMTP in with XOAUTH2, and answers a server challenge with nothing", s2.log[0][1] == "XOAUTH2" and s2.log[0][2] == O.xoauth2(EMAIL, "LIVE-TOKEN") and s2.log[0][3] == "")
    i2 = Imap()
    O.imap_auth(i2, M, secret)
    check("a Google sign-in logs IMAP in with XOAUTH2", i2.log == [("auth", "XOAUTH2", O.xoauth2(EMAIL, "LIVE-TOKEN").encode())])
    try:
        O.smtp_auth(Smtp(fail=True), M, secret)
        e1 = None
    except Exception as e:
        e1 = e
    try:
        O.imap_auth(Imap(fail=True), M, secret)
        e2 = None
    except Exception as e:
        e2 = e
    O.access_token = real
    check("Gmail refusing the token is reported as a Google sign-in failure on both servers", isinstance(e1, O.OAuthRevoked) and isinstance(e2, O.OAuthRevoked))
    ex = H.explain(e1, "google")
    check("the explanation tells you to sign in with Google again, not to make an app password", "Sign in with Google" in ex and "App Password" not in ex)
    check("a temporary Google outage is explained as such", "tried again by itself" in H.explain(O.OAuthNetwork("x"), "google"))

    # ---- storing, and what Citadel is told
    H.DATA.mkdir(parents=True, exist_ok=True)
    H.set_secret_raw("m1", secret)
    H.set_secret_raw(O.CLIENT_KEY, O.pack_client(CLIENT["cid"], CLIENT["cs"]))
    H.MAILBOXES.write_text(json.dumps([M]), encoding="utf-8")
    pay = H.status_payload()
    check("a mailbox signed in with Google counts as having a login, and nothing secret is in what Citadel is told", pay["m1"]["secret_set"] is True and RT not in json.dumps(pay) and CLIENT["cs"] not in json.dumps(pay) and "oauth1" not in json.dumps(pay))
    check("the Google client details are found again and are not a mailbox", H.get_google_client() == CLIENT and "_google_client" not in [x["id"] for x in H.load_mailboxes()])
    raw_file = H.SECRETS.read_bytes()
    check("the stored file does not contain the token or the client secret in the clear", RT.encode() not in raw_file and CLIENT["cs"].encode() not in raw_file or sys.platform != "win32")

    # ---- the command that runs in the window
    out = []
    H.forget_secret("m1")
    code = H.google_sign_in(M, ask=lambda p: "x", ask_secret=lambda p: "y", out=out.append, flow=lambda email, client, out=None: secret)
    check("with the client already saved it goes straight to the sign-in and saves the result, saying only what to do next", code == 0 and H.get_secret("m1") == secret and any("Test connection" in x for x in out) and not any(RT in x or CLIENT["cs"] in x for x in out))
    H.forget_secret("m1")
    H.forget_secret(O.CLIENT_KEY)
    out = []
    code = H.google_sign_in(M, ask=lambda p: "not-a-client-id", ask_secret=lambda p: "tiny", out=out.append, flow=lambda *a, **k: secret)
    check("the first time it asks for the client details and refuses ones that cannot be right", code == 1 and H.get_secret("m1") is None and H.get_google_client() is None)
    out = []
    code = H.google_sign_in(M, ask=lambda p: CLIENT["cid"], ask_secret=lambda p: CLIENT["cs"], out=out.append, flow=lambda *a, **k: secret)
    check("good client details are saved for the next mailbox, then the sign-in runs", code == 0 and H.get_google_client() == CLIENT and H.get_secret("m1") == secret)

    def refuse(email, client, out=None):
        raise O.OAuthSetupError("You signed in as bola@gmail.com, but this mailbox is ada@gmail.com.")
    H.forget_secret("m1")
    out = []
    check("a refused sign-in saves nothing and says why", H.google_sign_in(M, out=out.append, flow=refuse) == 1 and H.get_secret("m1") is None and "bola@gmail.com" in " ".join(out))

    calls = []
    msg = H.open_google_window({"id": "m-1", "email": EMAIL}, popen=lambda cmd, **kw: calls.append(cmd)) if H.os.name == "nt" else ""
    check("the Citadel button opens the window with the mailbox id as one argument, never a shell string", H.os.name != "nt" or (calls and calls[0][-3:] == ["google", "m-1", "--wait"] and isinstance(calls[0], list) and "Allow" in msg))

    # ---- the real tiny web page on this computer
    loop = O.Loopback()
    check("the answer page listens on this computer only", loop.redirect_uri.startswith("http://127.0.0.1:"))
    urllib.request.urlopen(loop.redirect_uri + "/?code=C&state=S", timeout=5).read()
    p = loop.wait(5)
    check("it catches the code and the state Google sends back, and stops", p == {"code": "C", "state": "S"})
    loop2 = O.Loopback()
    urllib.request.urlopen(loop2.redirect_uri + "/favicon.ico", timeout=5).read()
    urllib.request.urlopen(loop2.redirect_uri + "/?error=access_denied", timeout=5).read()
    check("a stray request is ignored and an error answer is passed on", loop2.wait(5) == {"error": "access_denied"})
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ---- wiring
cat = json.loads((ROOT / "bridge" / "catalog.json").read_text(encoding="utf-8"))
t = cat["tools"]["dse.herald_google"]
check("the Google tool asks for an address only, never a secret, and says it stays on this PC", [f["name"] for f in t["fields"]] == ["mailbox"] and "never goes through Citadel" in t["help"] and t["args"][1]["lit"] == "googlewin")
src = {n: (ROOT / "dse" / n).read_text(encoding="utf-8") for n in ("herald.py", "herald_send.py", "herald_warm.py", "herald_oauth.py")}
check("every place that logs in goes through the one helper (no direct login left)", ".login(" not in src["herald.py"].replace("O.smtp_auth", "") and src["herald_send.py"].count("O.smtp_auth") == 2 and "O.imap_auth" in src["herald_send.py"] and "O.imap_auth" in src["herald_warm.py"] and "O.imap_auth" in src["herald.py"], [k for k, v in src.items() if ".login(" in v])
check("nothing in the module prints a token, a secret or the client details", "print(" not in src["herald_oauth.py"].replace("out=print", "") and "log(" not in src["herald_oauth.py"])
check("no em dash", DASH not in src["herald_oauth.py"] + Path(__file__).read_text(encoding="utf-8"))
print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
