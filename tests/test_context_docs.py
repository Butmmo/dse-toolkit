"""Tests for reading Word and PDF files in engine context folders.   python tests/test_context_docs.py"""
import sys
import tempfile
import zipfile
import zlib
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


def make_docx(path: Path, paragraphs):
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = f'<?xml version="1.0"?><w:document xmlns:w="x"><w:body>{body}</w:body></w:document>'
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", xml)


def make_pdf(path: Path, lines):
    ops = "BT /F1 12 Tf " + " ".join(f"({l}) Tj T*" for l in lines) + " ET"
    stream = zlib.compress(ops.encode("latin-1"))
    head = b"%PDF-1.4\n1 0 obj\n<< /Length " + str(len(stream)).encode() + b" /Filter /FlateDecode >>\nstream\n"
    path.write_bytes(head + stream + b"\nendstream\nendobj\n%%EOF\n")


tmp = Path(tempfile.mkdtemp())
try:
    check("Word and PDF files are now read, not skipped", C.classify(Path("offer.docx"))[0] == "doc" and C.classify(Path("plan.PDF"))[0] == "doc")
    check("old binary Word files are still not opened", C.classify(Path("old.doc"))[0] == "skip")

    make_docx(tmp / "offer.docx", ["Our niche is interior designers in Austin.", "The offer is a $997 setup and $300 a month.", "Ben &amp; Co is our best client."])
    t = C.read_doc(tmp / "offer.docx")
    check("Word text is read, paragraph by paragraph, with entities decoded", "interior designers in Austin" in t and "\n" in t and "Ben & Co" in t, t)

    make_pdf(tmp / "plan.pdf", ["The goal is ten new retainer clients this quarter.", "We focus on kitchen and bath designers across Texas.", "Pricing starts with a setup fee and a monthly plan.", "Every message is written by hand and sent by the owner."])
    p = C.read_doc(tmp / "plan.pdf")
    check("a simple PDF gives its text", "ten new retainer clients" in p and "kitchen and bath designers" in p, p)

    (tmp / "scan.pdf").write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Page >>\nendobj\n%%EOF\n")
    check("a PDF with no text (a scan) gives nothing, without crashing", C.read_doc(tmp / "scan.pdf") == "")
    (tmp / "broken.docx").write_bytes(b"this is not a zip")
    check("a damaged Word file gives nothing, without crashing", C.read_doc(tmp / "broken.docx") == "")
    with zipfile.ZipFile(tmp / "empty.docx", "w") as z:
        z.writestr("other.txt", "x")
    check("a zip that is not a Word file gives nothing", C.read_doc(tmp / "empty.docx") == "")

    big = tmp / "big.docx"
    with zipfile.ZipFile(big, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", "<w:p>" + "a" * (C.MAX_XML_BYTES + 10) + "</w:p>")
    check("a zip bomb inside a Word file is not unpacked", C.read_doc(big) == "")

    make_docx(tmp / "keys.docx", ["Notes: api_key = sk-ant-abc123def456ghi789jkl012mno stays private.", "The niche is plumbers in Dallas and the goal is five clients."])
    scan = C.scan_folder(tmp)
    recs = {r["path"]: r for r in scan["files"]}
    check("the scan lists Word and PDF files with a summary", "offer.docx" in recs and "plan.pdf" in recs and recs["offer.docx"]["summary"], str(recs.get("offer.docx")))
    check("a PDF with no text is listed with an honest note", "No readable text" in recs["scan.pdf"]["summary"])
    check("secrets inside a Word file are hidden in what is kept", "sk-ant-abc123" not in str(scan) and "[hidden]" in str(scan))
    check("niche and goal lines are picked up from Word and PDF text", any("plumbers in Dallas" in x for x in scan["signals"].get("niche", [])) or any("five clients" in x for x in scan["signals"].get("goal", [])) or bool(scan["signals"]), str(scan["signals"]))
finally:
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

src = (ROOT / "dse" / "context_folder.py").read_text(encoding="utf-8") + Path(__file__).read_text(encoding="utf-8")
check("no em dash", DASH not in src)
print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
