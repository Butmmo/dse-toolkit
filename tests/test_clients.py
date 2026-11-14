"""Tests for the Client Desk: a client's whole life from a won proposal to paid.   python tests/test_clients.py"""
import csv
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dse import cashdesk as CD, clients as C, proposal as PR, review as RV  # noqa: E402

fails = []


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


TODAY = dt.date(2026, 11, 14)
SLUG = "zz-client"
d = ROOT / "engines" / SLUG
shutil.rmtree(d, ignore_errors=True)
(d / "data").mkdir(parents=True)
(d / "engine.json").write_text(json.dumps({"name": "Client test", "path": "smb", "sender_name": "Bolu Ade", "brand_name": "T Co", "postal_address": "1 Main St, Tampa FL", "archived": False}), encoding="utf-8")
try:
    PR.report(SLUG, "Acme Dental", "Dana", "patients cannot book online and call after hours", "Online booking that fills the calendar", 1500, "Booking page; Reminder emails; Staff training", 3, 4000, today=TODAY, start="2026-11-16")
    pj = d / "proposals" / "2026-11-14-acme-dental.json"
    pdata = json.loads(pj.read_text(encoding="utf-8"))
    check("the proposal saves structured data", pdata["price"] == 1500 and pdata["deposit"] == 50 and pdata["items"] == ["Booking page", "Reminder emails", "Staff training"] and pdata["currency"] == "USD")

    # ---- won
    check("unknown proposal is explained with the ones that exist", "2026-11-14-acme-dental" in (raises(C.won, SLUG, "nope", today=TODAY) or ""))
    check("a proposal path outside the engine's proposals folder is refused", raises(C.won, SLUG, str(ROOT / "bridge" / "catalog.json"), today=TODAY) is not None)
    check("bad email refused", "email" in (raises(C.won, SLUG, "2026-11-14-acme-dental", "not-an-email", today=TODAY) or ""))
    t = C.won(SLUG, "2026-11-14-acme-dental", "dana@acme.example", "5 Oak Ave, Tampa FL", today=TODAY)
    folder = d / "clients" / "acme-dental"
    c = json.loads((folder / "client.json").read_text(encoding="utf-8"))
    check("client created from the proposal: price, deposit, start, weeks, items with due dates", c["price"] == 1500 and c["deposit_pct"] == 50 and c["start"] == "2026-11-16" and c["weeks"] == 3
          and [i["due"] for i in c["items"]] == ["2026-11-20", "2026-11-27", "2026-12-04"], str(c["items"]))
    check("deposit invoice INV-2026-001 for 750, due on acceptance", c["invoices"][0]["id"] == "INV-2026-001" and c["invoices"][0]["amount"] == 750 and c["invoices"][0]["due"] == "2026-11-14" and c["invoices"][0]["kind"] == "deposit")
    check("onboarding checklist has dates and tasks", len(c["onboarding"]) == 7 and c["onboarding"][0]["by"] == "2026-11-13")
    ob = (folder / "onboarding.md").read_text(encoding="utf-8")
    check("onboarding.md: checklist, delivery plan, welcome message in the sender's name, agreement outline with the not-legal-advice line",
          "Delivery plan" in ob and "Welcome message" in ob and "Bolu Ade" in ob and "not legal advice" in ob and "Never send passwords by email".lower() in ob.lower() or "never send passwords by email" in ob.lower(), ob[:300])
    inv_html = (folder / "invoices" / "INV-2026-001.html").read_text(encoding="utf-8")
    check("invoice page: from, to, amount, due, and a placeholder for payment details", "1 Main St, Tampa FL" in inv_html and "5 Oak Ave" in inv_html and "$750" in inv_html and "payment-details.txt" in inv_html)
    check("won says nothing was sent and mentions the missing payment details", "Nothing was sent" in t and "payment-details.txt" in t)
    check("the same client twice is refused", "already a client" in (raises(C.won, SLUG, "2026-11-14-acme-dental", today=TODAY) or ""))
    check("status starts as onboarding", C.status(c) == "onboarding")

    # ---- show / list
    s = C.show(f"{SLUG}/acme-dental", TODAY)
    check("show: onboarding, delivery, invoices", "## Onboarding" in s and "Booking page (due 2026-11-20)" in s and "INV-2026-001 deposit: $750" in s and "$750 outstanding" in s and "Not yet invoiced: $750" in s, s)
    check("show by path works too", "Acme Dental: onboarding" in C.show("engines/zz-client/clients/acme-dental/client.json", TODAY))
    check("bad targets are explained", "engine/client-name" in (raises(C.resolve, "just-a-name") or "") and "No client" in (raises(C.resolve, f"{SLUG}/ghost") or "") and raises(C.resolve, "../../x/client.json") is not None)
    check("list shows the client", "Acme Dental" in C.listing(SLUG, TODAY) and "Booking page" in C.listing(SLUG, TODAY))
    (ROOT / "engines" / "zz-client2").mkdir(exist_ok=True)
    (ROOT / "engines" / "zz-client2" / "engine.json").write_text(json.dumps({"name": "c2", "path": "smb"}), encoding="utf-8")
    check("empty list says how to start", "client won zz-client2" in C.listing("zz-client2"))
    shutil.rmtree(ROOT / "engines" / "zz-client2", ignore_errors=True)

    # ---- done
    check("a too-short or unknown item is explained", raises(C.done, f"{SLUG}/acme-dental", "x", "", TODAY) and "No deliverable or task matches" in (raises(C.done, f"{SLUG}/acme-dental", "unicorn", "", TODAY) or ""))
    check("an ambiguous item lists the matches", "more than one" in (raises(C.done, f"{SLUG}/acme-dental", "get ", "", TODAY) or ""))
    r = C.done(f"{SLUG}/acme-dental", "Agreement signed", "2026-11-15", TODAY)
    check("an onboarding task can be ticked", "onboarding task" in r and "2026-11-15" in r)
    r = C.done(f"{SLUG}/acme-dental", "booking page", "2026-11-19", TODAY)
    check("a deliverable can be ticked, case-insensitively, status becomes active", "deliverable" in r and "active" in r, r)
    check("final invoice before delivery is refused, naming what is left", "Reminder emails" in (raises(C.invoice, f"{SLUG}/acme-dental", "final", today=TODAY) or ""))
    C.done(f"{SLUG}/acme-dental", "reminder", "2026-11-26", TODAY)
    r = C.done(f"{SLUG}/acme-dental", "staff training", "2026-12-03", TODAY)
    check("when the last deliverable is ticked it says to issue the final invoice for the balance", "Everything is delivered" in r and "$750" in r and "--kind final" in r, r)

    # ---- invoices
    DEC = dt.date(2026, 12, 4)
    r = C.invoice(f"{SLUG}/acme-dental", "final", today=DEC)
    c = json.loads((folder / "client.json").read_text(encoding="utf-8"))
    check("final invoice = price - already invoiced = 750, next number, due in 7 days", c["invoices"][1]["id"] == "INV-2026-002" and c["invoices"][1]["amount"] == 750 and c["invoices"][1]["due"] == "2026-12-11" and (folder / "invoices" / "INV-2026-002.html").exists(), r)
    check("a second final invoice is refused: nothing left to invoice", "already invoiced" in (raises(C.invoice, f"{SLUG}/acme-dental", "final", today=DEC) or ""))
    check("extra invoice needs an amount and a note", raises(C.invoice, f"{SLUG}/acme-dental", "extra", 0, "", 7, DEC) and raises(C.invoice, f"{SLUG}/acme-dental", "extra", 100, "", 7, DEC))
    check("bad kind and terms refused", raises(C.invoice, f"{SLUG}/acme-dental", "weird", today=DEC) and raises(C.invoice, f"{SLUG}/acme-dental", "extra", 10, "x extra", 400, DEC))
    (d / "payment-details.txt").write_text("Pay by bank transfer to the account shown here\nReference: INV", encoding="utf-8")
    C.invoice(f"{SLUG}/acme-dental", "extra", 200, "An extra <b>page</b>", 7, DEC)
    ih = (folder / "invoices" / "INV-2026-003.html").read_text(encoding="utf-8")
    check("payment details come from the local file; the note is html-escaped", "Pay by bank transfer" in ih and "&lt;b&gt;page&lt;/b&gt;" in ih and "payment-details.txt" not in ih)
    check("extra invoices do not change the 'invoiced' total used for the price", C.invoiced(json.loads((folder / "client.json").read_text(encoding="utf-8"))) == 1500)

    # ---- attention (Weekly Review feed) before anything is paid
    JAN = dt.date(2027, 1, 5)
    att = C.attention(SLUG, JAN)
    check("overdue invoices are listed with amounts: 750 + 750 + 200", sorted(i["owed"] for i in att["overdue_invoices"]) == [200, 750, 750], str(att))
    check("nothing late when everything is delivered", att["late_items"] == [])

    # ---- paid, and the Cash Desk
    r = C.paid(f"{SLUG}/acme-dental", "INV-2026-001", 400, "2026-11-18", DEC)
    check("partial payment recorded, 350 left", "$350 is still outstanding" in r, r)
    cash = CD.read_cash(SLUG)
    check("the Cash Desk got the payment: 400, project, with the invoice number", len(cash) == 1 and cash[0]["amount"] == "400.00" and cash[0]["kind"] == "project" and "INV-2026-001" in cash[0]["note"] and cash[0]["date"] == "2026-11-18", str(cash))
    check("overpaying is refused", "at most what is outstanding" in (raises(C.paid, f"{SLUG}/acme-dental", "INV-2026-001", 500, "", DEC) or ""))
    check("unknown invoice is explained", "INV-2026-001" in (raises(C.paid, f"{SLUG}/acme-dental", "INV-9", 0, "", DEC) or ""))
    C.paid(f"{SLUG}/acme-dental", "INV-2026-001", 0, "2026-11-20", DEC)          # the rest: amount defaults to what is left
    check("paying with no amount pays what is left (350)", [p["amount"] for p in json.loads((folder / "client.json").read_text(encoding="utf-8"))["invoices"][0]["payments"]] == [400, 350])
    check("a paid invoice cannot be paid again", "already paid" in (raises(C.paid, f"{SLUG}/acme-dental", "INV-2026-001", 10, "", DEC) or ""))
    C.paid(f"{SLUG}/acme-dental", "INV-2026-002", 0, "2026-12-08", DEC)
    check("delivered but not closed while the extra invoice is unpaid", C.status(json.loads((folder / "client.json").read_text(encoding="utf-8"))) == "delivered")
    C.paid(f"{SLUG}/acme-dental", "INV-2026-003", 0, "2026-12-09", DEC)
    check("all paid and delivered: closed", C.status(json.loads((folder / "client.json").read_text(encoding="utf-8"))) == "closed")
    a = CD.month_data(SLUG, dt.date(2026, 12, 1), dt.date(2026, 12, 31))
    check("Cash Desk December received = 750 + 200 = 950", a["received"] == 950.0, str(a["received"]))
    check("a closed client no longer needs attention", C.attention(SLUG, JAN) == {"overdue_invoices": [], "late_items": []})

    # ---- a second client: late work, an overdue invoice, GBP, and the Weekly Review
    PR.report(SLUG, "Beta <Bakery>", "Ben", "no website for the shop", "A simple website", 900, "Home page; Contact page", 2, 0, today=TODAY, start="2026-11-16", currency="GBP", deposit=100)
    C.won(SLUG, "2026-11-14-beta-bakery", today=TODAY)
    bc = json.loads((d / "clients" / "beta-bakery" / "client.json").read_text(encoding="utf-8"))
    check("100% deposit: one invoice 'full' for the whole price, in pounds", bc["invoices"][0]["kind"] == "full" and bc["invoices"][0]["amount"] == 900 and bc["sym"] == "£")
    check("the invoice page escapes the client's name and has the next number", bc["invoices"][0]["id"] == "INV-2026-004" and "&lt;Bakery&gt;" in (d / "clients" / "beta-bakery" / "invoices" / "INV-2026-004.html").read_text(encoding="utf-8"))
    r_gbp = C.paid(f"{SLUG}/beta-bakery", bc["invoices"][0]["id"], 100, "2026-11-20", TODAY)
    check("GBP: the payment is recorded in GBP and the note says it does not count toward the dollar target until a rate is given, with the command", "recorded in GBP" in r_gbp and "until you give a rate" in r_gbp and "fx add" in r_gbp, r_gbp)
    check("the cash row carries the currency", CD.read_cash(SLUG)[-1]["currency"] == "GBP")
    late = C.attention(SLUG, dt.date(2026, 12, 1))
    check("late deliverables are found by their dates (Home page due Nov 20 and Contact page due Nov 27)", [x["item"] for x in late["late_items"]] == ["Home page", "Contact page"], str(late))
    g = RV.gather(SLUG, dt.date(2026, 12, 1))
    mv = RV.moves(g)
    ranks = [m["rank"] for m in mv]
    check("Weekly Review: a late deliverable move, in order", 3.5 in ranks and ranks == sorted(ranks), str(ranks))
    check("the review names the client and the next step for late work", any("Beta" in m["do"] and "client done" in m["how"] for m in mv if m["rank"] == 3.5), str([m["do"] for m in mv]))
    bi = bc["invoices"][0]["id"]
    g2 = RV.gather(SLUG, dt.date(2027, 3, 1))
    check("an overdue invoice appears too, with the amount still owed (900 - 100 = 800)", any(m["rank"] == 2.5 and "£800" in m["do"] and "client paid" in m["how"] for m in RV.moves(g2)), str([m["do"] for m in RV.moves(g2)]))
    check("no em dash in the onboarding, invoice or review text", all(chr(0x2014) not in x for x in (ob, inv_html, RV.build(SLUG, today=dt.date(2026, 12, 1)))))
finally:
    shutil.rmtree(d, ignore_errors=True)

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
