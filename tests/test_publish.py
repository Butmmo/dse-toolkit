"""Guided publish for static sites: stage, guidance, and the Wrangler deploy.

No real account and no real upload: the process runner is a fake that records the
command it would have run. Run: python tests/test_publish.py
"""
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "builder"))
spec = importlib.util.spec_from_file_location("publish", ROOT / "builder" / "publish.py")
publish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish)

FAILED = []


def check(label, fn):
    try:
        fn()
        print("PASS ", label)
    except Exception as e:  # noqa: BLE001
        FAILED.append(label)
        print("FAIL ", label, "-", e)


def make_build(base: Path, kind="website") -> Path:
    dst = base / "bright-care"
    dst.mkdir(parents=True)
    (dst / "spec.json").write_text(json.dumps({"kind": kind, "name": "Bright Care", "blueprint": "landing"}), encoding="utf-8")
    for name, body in [("index.html", "<h1>Bright Care</h1>"), ("about.html", "<p>About</p>"), ("styles.css", "body{}"),
                       ("app.js", "console.log(1)"), ("logo.png", "PNG"), ("README.md", "# notes"),
                       ("BUILD-BRIEF.md", "brief"), ("preview.html", "<h1>preview</h1>")]:
        (dst / name).write_text(body, encoding="utf-8")
    (dst / "spec-backups").mkdir()
    (dst / "spec-backups" / "spec-1.json").write_text("{}", encoding="utf-8")
    return dst


def with_build(fn):
    def wrapped():
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "builds"
            base.mkdir()
            dst = make_build(base)
            publish.builder.OUT = base
            fn(dst)
    return wrapped


def run_main(argv, env, run=None):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = publish.main(argv, env=env, run=run or (lambda *a, **k: (_ for _ in ()).throw(AssertionError("no process may run"))))
    return code, out.getvalue()


@with_build
def t_stage(dst):
    pub = publish.stage(dst)
    names = sorted(f.name for f in pub.iterdir())
    assert names == ["about.html", "app.js", "index.html", "logo.png", "styles.css"], names
    assert publish.project_name(publish.read_spec(dst), dst, "") == "bright-care"
    assert publish.project_name(publish.read_spec(dst), dst, "My Clinic") == "my-clinic"


@with_build
def t_guidance(dst):
    code, text = run_main(["bright-care"], env={})
    assert code == 0 and "Not published yet" in text
    assert 'setx CLOUDFLARE_API_TOKEN "your token"' in text and "Upload assets" in text
    assert "PUBLISHED" not in text


class Done:
    def __init__(self, code, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = code, stdout, stderr


@with_build
def t_deploy(dst):
    sent = {}

    def fake_run(cmd, **kw):
        sent["cmd"], sent["env"] = cmd, kw.get("env")
        return Done(0, "Deployment complete! https://abc123.bright-care.pages.dev and https://bright-care.pages.dev")

    env = {"CLOUDFLARE_API_TOKEN": "tok", "CLOUDFLARE_ACCOUNT_ID": "acct"}
    code, text = run_main(["bright-care"], env=env, run=fake_run)
    assert code == 0 and "PUBLISHED https://bright-care.pages.dev" in text, text
    assert "pages" in sent["cmd"] and "deploy" in sent["cmd"] and "bright-care" in sent["cmd"]
    assert sent["env"]["CLOUDFLARE_API_TOKEN"] == "tok", "the member's own variables go to Wrangler, nowhere else"


@with_build
def t_failed_deploy(dst):
    def fake_run(cmd, **kw):
        return Done(1, "", "Authentication error: check your token")

    env = {"CLOUDFLARE_API_TOKEN": "tok", "CLOUDFLARE_ACCOUNT_ID": "acct"}
    code, text = run_main(["bright-care"], env=env, run=fake_run)
    assert code == 0 and "did not finish" in text and "Authentication error" in text and "PUBLISHED" not in text


@with_build
def t_dry_and_refusals(dst):
    code, text = run_main(["bright-care"], env={}, run=None)
    assert "Staged" in text  # the plain run with no credentials stages, then guides
    code, text = run_main(["bright-care", "--dry"], env={"CLOUDFLARE_API_TOKEN": "t", "CLOUDFLARE_ACCOUNT_ID": "a"})
    assert code == 0 and "nothing was uploaded" in text
    spec_path = dst / "spec.json"
    spec_path.write_text(json.dumps({"kind": "mobile", "name": "App"}), encoding="utf-8")
    try:
        run_main(["bright-care"], env={})
        raise AssertionError("a mobile build must be refused")
    except SystemExit as e:
        assert "Only website builds" in str(e)


check("staging keeps only the site files, and the project name comes from the business", t_stage)
check("without Cloudflare variables the tool guides instead of uploading", t_guidance)
check("with the member's variables, Wrangler deploys and the live address is reported", t_deploy)
check("a failed upload says so plainly and claims nothing is live", t_failed_deploy)
check("dry runs stage only, and non-website builds are refused", t_dry_and_refusals)

print("\n%d FAILED" % len(FAILED) if FAILED else "\nALL PASS")
sys.exit(1 if FAILED else 0)
