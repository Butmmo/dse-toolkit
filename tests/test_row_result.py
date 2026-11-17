"""The result line a BPS Table workflow reads (dse enrich --site X --result-line) and the tool entry.   python tests/test_row_result.py"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import enrich  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


s = enrich.blank("smile.co")
s.update({"status": "ok", "emails": [{"email": "hi@smile.co", "kind": "generic", "source": "x"}], "people": [{"name": "Ada Obi", "title": "Owner", "source": "x"}], "phones": ["+44 1"], "socials": {"linkedin": "https://linkedin.com/company/smile"}})
line = enrich.result_json(s, 72)
check("one line starting with RESULT, valid JSON, plain ASCII", line.startswith("RESULT {") and "\n" not in line and line.isascii())
r = json.loads(line[len("RESULT "):])
check("owner, email, phone, score and linkedin are in it", r["owner"] == "Ada Obi" and r["email"] == "hi@smile.co" and r["phone"] == "+44 1" and r["score"] == 72 and r["linkedin"].startswith("https://linkedin"))
g = enrich.blank("x.co")
g.update({"status": "ok", "guesses": ["info@x.co"]})
r2 = json.loads(enrich.result_json(g)[7:])
check("a guessed address is marked as a guess, and nothing found gives empty values, never an error", r2["email"] == "info@x.co" and r2["email_kind"] == "guess" and r2["owner"] == "" and r2["phone"] == "" and r2["score"] == "")
r3 = json.loads(enrich.result_json(enrich.blank("y.co"))[7:])
check("a site that could not be read still gives a line (status empty)", r3["status"] == "" and r3["email"] == "")
cat = json.loads((ROOT / "bridge" / "catalog.json").read_text(encoding="utf-8"))["tools"]["dse.enrich_row"]
check("the tool passes the site, always asks for the result line, and fast is a tick box that starts ticked", cat["args"] == [{"lit": "enrich"}, {"opt": "--site", "field": "site"}, {"lit": "--result-line"}, {"flag": "--fast", "field": "fast"}] and cat["fields"][1]["default"] is True)
src = (ROOT / "dse.py").read_text(encoding="utf-8")
check("dse.py hands the flag on", "a.result_line" in src and "--result-line" in src)
check("no em dash", chr(0x2014) not in (ROOT / "bridge" / "add_row_tools.py").read_text(encoding="utf-8") + Path(__file__).read_text(encoding="utf-8"))
print("\nALL PASS" if not fails else f"\n{len(fails)} FAILED")
sys.exit(1 if fails else 0)
