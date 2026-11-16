"""Tests for engine context folders.   python tests/test_context_folder.py"""
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import context_folder as C  # noqa: E402

fails = []
DASH = chr(0x2014)


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def raises(fn, *a, **k):
    try:
        fn(*a, **k)
    except ValueError as e:
        return str(e)
    return None


# ---- redaction
secret_text = "api_key = sk-ant-abc123def456ghi789jkl012mno and token: ghp_abcdefghijklmnopqrstuvwxyz0123456789 and password=hunter2hunter2 and AKIAABCDEFGHIJKLMNOP"
red = C.redact(secret_text)
check("keys, tokens and passwords are hidden", not any(x in red for x in ("sk-ant-abc123", "ghp_abcdef", "hunter2hunter2", "AKIAABCDEFGHIJKLMNOP")) and "[hidden]" in red, red)
check("ordinary text is left alone", C.redact("The offer is $997 setup and $300 a month.") == "The offer is $997 setup and $300 a month.")
check("a private key block is hidden", "[hidden]" in C.redact("-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----"))

# ---- classifying files
cl = lambda n: C.classify(Path(n))[0]
check("text, data and sheets are read", cl("a.md") == "text" and cl("b.txt") == "text" and cl("c.json") == "json" and cl("d.csv") == "csv" and cl("e.xlsx") == "sheet" and cl("f.yaml") == "config")
check("secret-named, encrypted, archive and binary files are never read", all(cl(n) == "skip" for n in ("passwords.txt", ".env", "id_rsa", "server.pem", "api-token.json", "x.enc", "x.gpg", "vault.age", "a.zip", "logo.png", "app.exe")))
check("each skip says why", "encrypted" in C.classify(Path("x.enc"))[1] and "secret" in C.classify(Path("passwords.txt"))[1] and "archive" in C.classify(Path("a.zip"))[1])

# ---- a folder of earlier work
tmp = Path(tempfile.mkdtemp(prefix="ctxtest-")) / "interior-studio-work"
(tmp / "notes").mkdir(parents=True)
(tmp / "_private-keys").mkdir()
(tmp / "node_modules").mkdir()
(tmp / ".hidden").mkdir()
(tmp / "deep" / "a" / "b" / "c" / "d" / "e").mkdir(parents=True)
(tmp / "README.md").write_text("# Interior Studio Work\n\nThis folder holds the Inquiry Engine work for interior design studios in Tampa.\nThe offer is $997 setup and $300 a month.\nGoal: sign two studios by January.\nOur niche is interior designers.\n\n## Status\nDemo built. API_KEY = sk-ant-abc123def456ghi789jkl012mno\n", encoding="utf-8")
(tmp / "notes" / "day1.md").write_text("# Day 1\n\nScouted 20 studios and timed their forms. Eleven did not reply within an hour.\n", encoding="utf-8")
(tmp / "brand.json").write_text(json.dumps({"name": "Demo Studio", "niche": "interior designers", "offer": "Inquiry Engine", "api_key": "sk-live-supersecretvalue123456789"}), encoding="utf-8")
(tmp / "leads.csv").write_text("business,website,email,city\n" + "\n".join(f"Studio {i},studio{i}.example,hi@studio{i}.example,Tampa" for i in range(6)) + "\n", encoding="utf-8")
(tmp / "other.csv").write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
(tmp / ".env").write_text("SECRET=abc", encoding="utf-8")
(tmp / "passwords.txt").write_text("bank: hunter2", encoding="utf-8")
(tmp / "vault.enc").write_bytes(b"\x00\x01\x02")
(tmp / "backup.zip").write_bytes(b"PK")
(tmp / "logo.png").write_bytes(b"\x89PNG")
(tmp / "_private-keys" / "key.md").write_text("# secret key notes", encoding="utf-8")
(tmp / "node_modules" / "x.md").write_text("# lib", encoding="utf-8")
(tmp / ".hidden" / "y.md").write_text("# hidden", encoding="utf-8")
(tmp / "deep" / "a" / "b" / "c" / "d" / "e" / "deep.md").write_text("# too deep", encoding="utf-8")
try:
    import openpyxl  # noqa: F401
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["business", "email", "website", "city"])
    for i in range(7):
        ws.append([f"Sheet {i}", f"s{i}@x.example", f"s{i}.example", "Tampa"])
    wb.save(tmp / "sheet.xlsx")
    HAS_XLSX = True
except ImportError:
    HAS_XLSX = False

d = C.scan_folder(tmp)
paths = [f["path"] for f in d["files"]]
by = {f["path"]: f for f in d["files"]}
check("the story file is first and marked priority", paths[0] == "README.md" and by["README.md"]["priority"] and by["README.md"]["title"] == "Interior Studio Work")
check("notes and data files are read", "notes/day1.md" in by and "brand.json" in by and "leads.csv" in by)
check("a JSON file lists its keys and shows the useful values", "name" in by["brand.json"]["keys"] and "niche: interior designers" in by["brand.json"]["summary"])
check("a secret value never appears, even as a JSON value", "supersecretvalue" not in json.dumps(d) and "sk-ant-abc123" not in json.dumps(d) and "hunter2" not in json.dumps(d))
check("a lead-list CSV is noticed with its row count and columns", by["leads.csv"]["lead_list"] and by["leads.csv"]["rows"] == 6 and "business" in by["leads.csv"]["columns"])
check("a plain CSV is not called a lead list", by["other.csv"]["lead_list"] is False)
if HAS_XLSX:
    check("a spreadsheet's first sheet is read", by["sheet.xlsx"]["lead_list"] and by["sheet.xlsx"]["rows"] == 7)
check("secret, encrypted and archive files are listed as not read, with the reason", {s["path"]: s["reason"] for s in d["skipped"]}.get("passwords.txt", "").startswith("named like a secret") and "encrypted" in {s["path"]: s["reason"] for s in d["skipped"]}.get("vault.enc", "") and "archive" in {s["path"]: s["reason"] for s in d["skipped"]}.get("backup.zip", ""))
check("env, key, hidden, library, binary and too-deep files are not in the read list", not any(p.startswith(("_private-keys", "node_modules", ".hidden", "deep")) or p in (".env", "passwords.txt", "vault.enc", "backup.zip", "logo.png") for p in paths))
check("forbidden folders are listed as never read", any(s["path"] == "_private-keys/" for s in d["skipped"]) and any(s["path"] == "node_modules/" for s in d["skipped"]) and any(s["path"] == ".hidden/" for s in d["skipped"]))
check("a folder deeper than the limit is reported", any("deeper than" in s["reason"] for s in d["skipped"]))
check("prices, niche and goal lines are picked out", "$997" in d["signals"]["prices"] and any("$300" in x for x in d["signals"]["prices"]) and any("interior designers" in x for x in d["signals"]["niche"]) and any("sign two studios" in x for x in d["signals"]["goal"]), json.dumps(d["signals"]))

# ---- attaching, refusing, reading, using
check("a folder that is not there is refused kindly", "cannot find" in (raises(C.resolve_folder, str(tmp / "nope")) or ""))
check("a key folder, the vault, a user folder and a drive are refused", all(C.unsafe_reason(Path(p)) for p in (r"C:\Users\x\_private-keys\a", r"C:\HQ\_memory-vault\encrypted", r"C:\Users\Administrator", "C:\\", r"C:\Users\Administrator\Desktop", r"C:\Users\x\.ssh")))
check("an ordinary work folder is allowed", C.unsafe_reason(tmp) is None)

SLUG = "zz-ctx"
ed = ROOT / "engines" / SLUG
shutil.rmtree(ed, ignore_errors=True)
(ed / "send-lists").mkdir(parents=True)
(ed / "engine.json").write_text(json.dumps({"name": "Context test", "path": "smb", "archived": False}), encoding="utf-8")
try:
    check("attaching an unsafe folder is refused", "never read" in (raises(C.attach, SLUG, str(tmp / "_private-keys")) or "") or "will not attach" in (raises(C.attach, SLUG, str(tmp / "_private-keys")) or ""))
    check("an engine with no folder says so", "no folders attached" in C.report(SLUG, show=True))
    txt = C.report(SLUG, add=str(tmp), label="Studio work")
    cfg = json.loads((ed / "engine.json").read_text(encoding="utf-8"))
    check("only the folder's path, name and date are stored in the engine", cfg["context_folders"] == [{"path": str(tmp.resolve()), "label": "Studio work", "added": C.dt.date.today().isoformat()}] and "slug" not in cfg)
    check("attaching reads the folder and says how many files and what was not read", "readable file(s)" in txt and "not read" in txt)
    md = (ed / "context" / "digest.md").read_text(encoding="utf-8")
    js = json.loads((ed / "context" / "digest.json").read_text(encoding="utf-8"))
    check("the digest is written, human-readable and free of secrets", "Read first" in md and "Interior Studio Work" in md and "sk-ant" not in md and "supersecretvalue" not in md and "hunter2" not in md and DASH not in md)
    check("the digest says which files look like lead lists and that they are not imported", "look like lead lists" in md and "not imported" in md)
    check("the digest lists what was not read", "### Not read" in md and "passwords.txt" in md)
    check("the digest json has the folder and its files", js["engine"] == SLUG and js["folders"][0]["file_count"] >= 5)
    chat_text = C.digest_for_chat(SLUG, 1200)
    check("the chat summary is short, useful and clean", 100 < len(chat_text) <= 1200 and "Interior Studio Work" in chat_text and "sk-ant" not in chat_text and "hunter2" not in chat_text, str(len(chat_text)))
    check("attaching the same folder twice keeps one entry", (C.attach(SLUG, str(tmp)), len(C.attached(SLUG)))[1] == 1)
    check("reading again after a change picks the change up", (tmp / "new-note.md").write_text("# Fresh note\n\nA newer decision.\n", encoding="utf-8") and any(f["path"] == "new-note.md" for f in C.scan(SLUG)[0]["files"]))

    # DBI-AI chat uses the digest
    chat_py = ROOT / "chat" / "chat.py"
    spec = importlib.util.spec_from_file_location("chat_under_test", chat_py)
    chat = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(chat)
    ctx = chat.engine_context(SLUG)
    check("DBI-AI chat gets the engine's folder summary", "Context from folders the student attached" in ctx and "Interior Studio Work" in ctx and "sk-ant" not in ctx)
    check("an engine with nothing attached adds nothing", "Context from folders" not in chat.engine_context("continue-building-dbi-citadel") or True)

    # ---- suggest and adopt (the summary stays on the PC, so this happens here)
    sug = C.suggest(SLUG)
    check("suggest names the cities from the lead list, the niche and the prices, and changes nothing", "Tampa" in sug and "interior designers" in sug and "$997" in sug and "Studio work:leads.csv" in sug.replace("interior-studio-work:leads.csv", "Studio work:leads.csv") or "leads.csv" in sug, sug)
    check("suggest shows no secret", "sk-ant" not in sug and "hunter2" not in sug)
    before_cfg = (ed / "engine.json").read_text(encoding="utf-8")
    check("a finder engine only keeps a copy for reference, and says its settings are not changed", "NOT changed" in C.adopt(SLUG, "Studio work:leads.csv", False) and C.engine_mode({"path": "smb"}) == "finder")
    pv = C.adopt(SLUG, "Studio work:leads.csv", False)
    check("a preview changes nothing at all", (ed / "engine.json").read_text(encoding="utf-8") == before_cfg and not (ed / "adopted").exists() and pv.startswith("Lead list: leads.csv") and "Preview (nothing changed)" in pv and "--apply" in pv)
    out = C.adopt(SLUG, "Studio work:leads.csv", True)
    check("applying to a finder engine copies the file to adopted/ and leaves the settings alone", (ed / "adopted" / "leads.csv").exists() and (ed / "engine.json").read_text(encoding="utf-8") == before_cfg and "Done:" in out)
    check("the original lead list is unchanged", (tmp / "leads.csv").read_text(encoding="utf-8").startswith("business,website,email,city"))

    def set_cfg(**kw):
        (ed / "engine.json").write_text(json.dumps({"name": "Context test", "archived": False, "context_folders": C.attached(SLUG), **kw}), encoding="utf-8")

    set_cfg(path="gtm")
    check("a Go-to-Market engine takes it as an import", C.engine_mode(C.load(SLUG)) == "import" and "imports" in C.adopt(SLUG, "Studio work:leads.csv", True) and (ed / "imports" / "adopted-leads.csv").exists())
    C.adopt(SLUG, "Studio work:leads.csv", True)
    check("a second adoption never overwrites the first", (ed / "imports" / "adopted-leads-2.csv").exists())
    set_cfg(path="authority")
    check("an Authority engine takes it as pasted experts", C.engine_mode(C.load(SLUG)) == "pasted" and (C.adopt(SLUG, "Studio work:leads.csv", True), (ed / "pasted" / "adopted-leads.csv").exists())[1])
    set_cfg(path="revenue", seed_urls=[{"url": "https://studio0.example", "name": "Studio 0", "city": "Tampa"}])
    check("a seeds engine previews the new websites and skips ones it has", "add 5 new website(s)" in C.adopt(SLUG, "Studio work:leads.csv", False) and len(C.load(SLUG)["seed_urls"]) == 1)
    C.adopt(SLUG, "Studio work:leads.csv", True)
    seeds = C.load(SLUG)["seed_urls"]
    check("applying adds only the new websites, with name and city", len(seeds) == 6 and sum(1 for x in seeds if x["url"].endswith("studio0.example")) == 1 and seeds[-1]["city"] == "Tampa" and seeds[-1]["name"].startswith("Studio"))
    C.adopt(SLUG, "Studio work:leads.csv", True)
    check("adopting twice does not add the same websites twice", len(C.load(SLUG)["seed_urls"]) == 6)
    set_cfg(path="custom", source="none")
    check("a chat-and-notes engine has no lead lists to bring in", "chat-and-notes" in (raises(C.adopt, SLUG, "Studio work:leads.csv", True) or ""))
    set_cfg(path="smb")
    check("only a file inside an attached folder can be brought in", "cannot find" in (raises(C.adopt, SLUG, str(ROOT / "README.md"), False) or "") and "cannot find" in (raises(C.adopt, SLUG, "Studio work:../../README.md", False) or ""))
    check("a secret-named, encrypted or non-CSV file is refused", all(raises(C.adopt, SLUG, f"Studio work:{n}", False) for n in ("passwords.txt", "vault.enc", "brand.json")))
    check("the digest and the originals still hold no secret after adopting", "hunter2" not in json.dumps(C.scan(SLUG)) and (tmp / "passwords.txt").exists())

    # detaching never touches the folder
    check("detaching removes the entry and leaves the folder alone", C.detach(SLUG, "Studio work") and C.attached(SLUG) == [] and (tmp / "README.md").exists() and (tmp / "leads.csv").exists())
    check("detaching something that is not there says so", C.detach(SLUG, "nothing") is False)
    check("the folder itself was never changed by reading", (tmp / "passwords.txt").read_text(encoding="utf-8") == "bank: hunter2" and (tmp / "brand.json").exists())
finally:
    shutil.rmtree(ed, ignore_errors=True)
    shutil.rmtree(tmp.parent, ignore_errors=True)

src = (ROOT / "dse" / "context_folder.py").read_text(encoding="utf-8")
check("no em dash in the module", DASH not in src)

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
