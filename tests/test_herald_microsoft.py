"""Tests for Herald's sign in with Microsoft (Outlook.com, Hotmail, Microsoft 365): dse/herald_oauth.py and dse/herald.py.   python tests/test_herald_microsoft.py
Nothing real is contacted: Microsoft, the browser and the mail servers are replaced by fakes (the only real thing is a tiny web page on this computer).
HONEST LIMIT: this proves our side of the protocol (the right address, scopes, PKCE, no secret, the right login line). It does not prove Microsoft accepts it: that needs a real Outlook mailbox."""
import base64
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

CID = "8f2c1a3e-4b5d-4e6f-9a7b-1c2d3e4f5a6b"
CLIENT = {"cid": CID, "cs": ""}
EMAIL = "ada@outlook.com"
RT = "0.AAAA-refresh-token-SECRET"
M = {"id": "m9", "email": EMAIL, "provider": "microsoft", "username": EMAIL, "smtp_host": "smtp.office365.com", "smtp_port": 587, "smtp_security": "starttls", "imap_host": "outlook.office365.com", "imap_port": 993}


def idtoken(**claims):
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"x.{body}.y"


try:
    # ---- what is stored, and that Google's format did not change
    b = O.pack(CID, "", RT, "ADA@outlook.com", "microsoft")
    g = O.pack("123-abc.apps.googleusercontent.com", "GOCSPX-secretvalue", "1//rt", "bob@gmail.com")
    check("a Microsoft sign-in is labelled, reads back with the address in lower case, and is told apart from Google's", O.is_oauth(b) and O.provider_of(b) == "microsoft" and O.unpack(b)["email"] == EMAIL and O.unpack(b)["rt"] == RT)
    check("a Google sign-in keeps the exact old format (no label), and one saved before Microsoft existed still counts as Google's", '"p"' not in g and O.provider_of(g) == "google" and O.provider_of(O.PREFIX + '{"cid":"a","cs":"b","rt":"c","email":"d@e.f"}') == "google" and O.provider_of("not-a-sign-in") == "google")
    check("the Application (client) ID is checked before it is saved, and no secret is required", O.ms_client_ok(CID) == "" and "looks like" in O.ms_client_ok("12345") and "looks like" in O.ms_client_ok("123.apps.googleusercontent.com") and O.ms_client_ok(CID, "") == "" and "Leave the secret empty" in O.ms_client_ok(CID, "abc"))
    check("Microsoft client details are accepted without a secret, Google's still need one", O.unpack_client(O.pack_client(CID, ""), "microsoft") == {"cid": CID, "cs": ""} and O.unpack_client(O.pack_client(CID, ""), "google") is None and O.unpack_client("nonsense", "microsoft") is None)
    try:
        O.unpack(O.PREFIX + "{not json")
        dmg = None
    except Exception as e:
        dmg = e
    check("a damaged Microsoft sign-in says to sign in again, as Google's does", isinstance(dmg, O.OAuthRevoked) and "damaged" in str(dmg))

    # ---- the address Herald sends the browser to
    url = O.build_auth_url(CID, "http://localhost:5555", "STATE", "CHAL", EMAIL, "microsoft")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    scopes = q["scope"][0].split()
    check("the Microsoft address: the right endpoint, PKCE, state, the mailbox as a hint, both Outlook permissions and a long-lasting token, no Google-only option", url.startswith("https://login.microsoftonline.com/common/oauth2/v2.0/authorize?") and q["code_challenge_method"] == ["S256"] and q["state"] == ["STATE"] and q["login_hint"] == [EMAIL] and "https://outlook.office.com/IMAP.AccessAsUser.All" in scopes and "https://outlook.office.com/SMTP.Send" in scopes and "offline_access" in scopes and "access_type" not in q and q["redirect_uri"] == ["http://localhost:5555"])
    check("Google's address is unchanged", O.build_auth_url("x.apps.googleusercontent.com", "http://127.0.0.1:1", "S", "C", "a@gmail.com").startswith("https://accounts.google.com/o/oauth2/v2/auth?") and "access_type=offline" in O.build_auth_url("x", "http://127.0.0.1:1", "S", "C", "a@gmail.com"))

    # ---- the one-time sign-in, with a fake browser and a fake Microsoft
    class FakeLoop:
        redirect_uri = "http://localhost:5555"

        def __init__(self, mutate=None):
            self.mutate, self.url = mutate, None

        def wait(self, timeout=0):
            st = urllib.parse.parse_qs(urllib.parse.urlparse(self.url).query)["state"][0]
            p = {"code": "AUTHCODE", "state": st}
            return self.mutate(p) if self.mutate else p

    def run(mutate=None, token=None, claims=None):
        loop = FakeLoop(mutate)
        posts = []

        def post(url, data):
            posts.append((url, data))
            return token if token is not None else {"access_token": "AT", "refresh_token": RT, "id_token": idtoken(**(claims or {"email": EMAIL})), "expires_in": 3600}
        try:
            r = O.run_flow(EMAIL, CLIENT, loop=loop, opener=lambda u: setattr(loop, "url", u), post=post, out=lambda *a: None, provider="microsoft")
        except O.OAuthSetupError as e:
            return str(e), posts
        return r, posts

    r, posts = run()
    check("a good sign-in returns a Microsoft bundle for that address", O.is_oauth(r) and O.provider_of(r) == "microsoft" and O.unpack(r)["rt"] == RT and O.unpack(r)["email"] == EMAIL)
    check("the code goes to Microsoft's token address with the PKCE verifier and the app ID, and no secret", posts[0][0] == "https://login.microsoftonline.com/common/oauth2/v2.0/token" and posts[0][1]["grant_type"] == "authorization_code" and posts[0][1]["client_id"] == CID and len(posts[0][1]["code_verifier"]) >= 43 and posts[0][1]["client_secret"] == "")
    check("an address given as preferred_username (what a work account sends) is read too", O.is_oauth(run(claims={"preferred_username": "ADA@outlook.com"})[0]))
    check("an answer with the wrong state is refused before anything is asked of Microsoft", "did not match" in run(lambda p: {**p, "state": "forged"})[0] and run(lambda p: {**p, "state": "forged"})[1] == [])
    check("a different Microsoft account than the mailbox is refused and both addresses are named", "bola@outlook.com" in run(claims={"email": "bola@outlook.com"})[0] and "ada@outlook.com" in run(claims={"email": "bola@outlook.com"})[0])
    check("Microsoft saying no, or nothing coming back, names Microsoft", "Microsoft did not allow it" in run(lambda p: {"error": "access_denied"})[0] and "Nothing came back from Microsoft" in run(lambda p: {})[0])
    check("no long-lasting token tells you to accept every permission", "accept every permission" in run(token={"access_token": "AT", "id_token": idtoken(email=EMAIL)})[0])
    check("a wrong app ID points to the Entra Overview page, not to Google Cloud", "Overview" in run(token={"error": "invalid_client"})[0] and "Google" not in run(token={"error": "invalid_client"})[0])

    # ---- the answer page, and keeping the access token fresh
    loop = O.Loopback("localhost")
    check("the answer page uses the word localhost (what Microsoft accepts) but still listens on this computer only", loop.redirect_uri.startswith("http://localhost:") and loop._srv.server_address[0] == "127.0.0.1")
    urllib.request.urlopen("http://127.0.0.1:" + loop.redirect_uri.rsplit(":", 1)[1] + "/?code=C&state=S", timeout=5).read()
    check("it catches the code and the state, and stops", loop.wait(5) == {"code": "C", "state": "S"})

    O._CACHE.clear()
    calls = []

    def okpost(url, data):
        calls.append((url, data))
        return {"access_token": "MS-TOKEN", "expires_in": 3600}
    check("a Microsoft token is refreshed at Microsoft's address, with the Outlook scopes, and kept for the hour", O.access_token(b, now=1000.0, post=okpost) == "MS-TOKEN" and O.access_token(b, now=1500.0, post=okpost) == "MS-TOKEN" and len(calls) == 1 and calls[0][0].startswith("https://login.microsoftonline.com/") and "outlook.office.com/SMTP.Send" in calls[0][1]["scope"])
    O._CACHE.clear()
    gcalls = []
    O.access_token(g, now=1.0, post=lambda u, d: (gcalls.append((u, d)) or {"access_token": "G", "expires_in": 3600}))
    check("a Google token is refreshed exactly as before (Google's address, no scope)", gcalls[0][0] == O.TOKEN_URL and "scope" not in gcalls[0][1])

    def revoked(err):
        O._CACHE.clear()
        try:
            O.access_token(b, now=5.0, post=lambda u, d: {"error": err})
        except O.OAuthRevoked as e:
            return e
        except O.OAuthNetwork:
            return None
        return None
    e1, e2, e3 = revoked("invalid_grant"), revoked("interaction_required"), revoked("consent_required")
    check("a Microsoft refusal (expired, password changed, needs consent) says to sign in again with Microsoft's own marker; the Google Testing hint is not shown", all(e is not None and O.PROVIDERS["microsoft"]["marker"] in str(e) and "Testing mode" not in str(e) for e in (e1, e2, e3)))
    check("a temporary Microsoft problem is retried later, not treated as a revoked sign-in", revoked("temporarily_unavailable") is None)
    check("the plain-words reason for a Microsoft refusal names Microsoft and the button", "Sign in with Microsoft" in H.explain(e1, "microsoft") and "Microsoft no longer accepts" in H.explain(e1, "microsoft"))

    # ---- logging in: the same XOAUTH2 line Outlook expects
    class FakeSmtp:
        def __init__(self):
            self.log = []

        def auth(self, mech, cb, initial_response_ok=True):
            self.log.append((mech, cb()))

        def login(self, *a):
            self.log.append(("login",) + a)
    O._CACHE.clear()
    s = FakeSmtp()
    import dse.herald_oauth as OO
    OO.access_token = lambda secret, now=None, post=None: "LIVE-TOKEN"
    O.smtp_auth(s, M, b)
    check("a Microsoft sign-in logs SMTP in with XOAUTH2 for the mailbox's own address", s.log == [("XOAUTH2", O.xoauth2(EMAIL, "LIVE-TOKEN"))])
    s2 = FakeSmtp()
    O.smtp_auth(s2, M, "plain-app-password")
    check("a normal password still logs in the normal way", s2.log == [("login", EMAIL, "plain-app-password")])

    # ---- the commands on the PC
    out = []
    rows = [M]
    H.MAILBOXES.parent.mkdir(parents=True, exist_ok=True)
    H.MAILBOXES.write_text(json.dumps(rows), encoding="utf-8")
    asked = []

    def ask(prompt):
        asked.append(prompt)
        return CID

    def good_flow(email, client, out=print, provider="google"):
        return O.pack(client["cid"], client.get("cs", ""), RT, email, provider)
    code = H.microsoft_sign_in(M, ask=ask, out=out.append, flow=good_flow)
    saved = H._read_secrets()
    check("the first time it asks only for the Application (client) ID (no secret), saves it, and saves the mailbox's Microsoft sign-in", code == 0 and len(asked) == 1 and "secret" not in asked[0].lower() and O.unpack_client(saved[O.PROVIDERS["microsoft"]["client_key"]], "microsoft") == CLIENT and O.provider_of(saved["m9"]) == "microsoft")
    asked.clear()
    code2 = H.microsoft_sign_in(M, ask=ask, out=out.append, flow=good_flow)
    check("the next mailbox does not ask again", code2 == 0 and asked == [])
    d = H._read_secrets()
    d.pop(O.PROVIDERS["microsoft"]["client_key"], None)
    H._write_secrets(d)
    bad = []
    code3 = H.microsoft_sign_in(M, ask=lambda p: "not-a-guid", out=bad.append, flow=good_flow)
    check("a wrong client ID is refused with what to copy, and nothing is saved", code3 == 1 and any("looks like" in x for x in bad) and O.PROVIDERS["microsoft"]["client_key"] not in H._read_secrets())
    d = H._read_secrets()
    d["_microsoft_client"] = O.pack_client(CID, "")
    H._write_secrets(d)

    def failing_flow(email, client, out=print, provider="google"):
        raise O.OAuthSetupError("You signed in as bola@outlook.com, but this mailbox is ada@outlook.com.")
    errs = []
    check("a flow error is shown in plain words and returns failure", H.microsoft_sign_in(M, ask=ask, out=errs.append, flow=failing_flow) == 1 and any("bola@outlook.com" in x for x in errs))
    popped = []
    msg = H.open_microsoft_window(M, popen=lambda argv, **kw: popped.append((argv, kw)))
    import os
    if os.name == "nt":
        check("the window runs the toolkit with the mailbox id as ONE argument (no shell), and tells you where to look", popped and popped[0][0][-3:] == ["microsoft", "m9", "--wait"] and "taskbar" in msg and "shell" not in popped[0][1])
    else:
        check("off Windows it says to run the command in a terminal instead of opening a window", "python dse.py herald microsoft" in msg and not popped)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ---- wiring
cat = json.loads((ROOT / "bridge" / "catalog.json").read_text(encoding="utf-8"))
t = cat["tools"]["dse.herald_microsoft"]
check("the Microsoft tool asks for an address only, never a secret, runs the window command, and says it stays on this PC", [f["name"] for f in t["fields"]] == ["mailbox"] and "never goes through Citadel" in t["help"] and t["args"][1] == {"lit": "microsoftwin"} and "no secret to copy" in t["help"])
src = {n: (ROOT / "dse" / n).read_text(encoding="utf-8") for n in ("herald.py", "herald_oauth.py")}
check("nothing in the module prints a token, a secret or the client details", "print(" not in src["herald_oauth.py"].replace("out=print", "") and "log(" not in src["herald_oauth.py"])
check("the Microsoft commands exist (microsoft, microsoftwin, microsoftclient)", all(c in src["herald.py"] for c in ('cmd == "microsoftclient"', 'cmd in ("microsoft", "microsoftwin")')))
check("no em dash", DASH not in src["herald_oauth.py"] + src["herald.py"] + Path(__file__).read_text(encoding="utf-8"))
print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
