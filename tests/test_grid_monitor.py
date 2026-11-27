"""Scheduled re-enrichment with change diffs, for the website lane of grid enrichment.

Scheduling itself already exists (dse/schedules.py, pulled by the runner every minute);
what was missing is the diff: a re-run overwrote or kept cells quietly. Now the website
lane stamps each row with a comparison status, a change summary naming old and new
values, the previous check date, and a rolling monitor history. These tests drive the
real persist step against an in-memory grid, three runs in a row, and prove that a
weekly schedule of the enrich tool validates against the real catalog.
Run: python tests/test_grid_monitor.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dse import grid_enrich as ge
from dse import schedules

FAILED = []


def check(label, fn):
    try:
        fn()
        print("PASS ", label)
    except Exception as e:  # noqa: BLE001
        FAILED.append(label)
        print("FAIL ", label, "-", e)


HEADERS = ["best_email", "phone_found", "lead_score", "enriched_on",
           "website_comparison_status", "website_change_summary", "website_previous_checked_at", "website_monitor_history"]
KEYS = {h: f"c_{h}" for h in HEADERS}


class FakeApi:
    """hq_grid_set_cells applied to an in-memory row store."""

    def __init__(self):
        self.store = {}

    def rpc(self, name, params, tries=1):
        assert name == "hq_grid_set_cells", name
        for update in params["p_updates"]:
            self.store.setdefault(update["id"], {}).update(update["cells"])
        return len(params["p_updates"])


def run_once(api: FakeApi, result: dict):
    source = [{"id": "r1", "data": dict(api.store.get("r1", {}))}]
    written, skipped, oversized, stats = ge._persist_batch(api, "g1", "website", source, [result], HEADERS, KEYS, True)
    assert written == 1 and oversized == 0
    return api.store["r1"], stats


RUN1 = {"best_email": "ada@brightcare.co.uk", "phone_found": "020 111", "lead_score": "40", "enriched_on": "2026-11-20"}
RUN2 = {"best_email": "hello@brightcare.co.uk", "phone_found": "020 111", "lead_score": "55", "enriched_on": "2026-11-27"}
RUN3 = dict(RUN2, enriched_on="2026-12-04")


def t_three_runs():
    api = FakeApi()
    row, stats = run_once(api, RUN1)
    assert row[KEYS["website_comparison_status"]] == "first check", row
    assert stats == {"first check": 1}
    history = json.loads(row[KEYS["website_monitor_history"]])
    assert len(history) == 1 and history[0]["status"] == "first check"

    row, stats = run_once(api, RUN2)
    assert row[KEYS["website_comparison_status"]] == "changed"
    summary = row[KEYS["website_change_summary"]]
    assert "best_email: ada@brightcare.co.uk is now hello@brightcare.co.uk" in summary, summary
    assert "lead_score: 40 is now 55" in summary
    assert "phone_found" not in summary, "an unchanged fact is not listed"
    assert row[KEYS["website_previous_checked_at"]] == "2026-11-20"
    assert row[KEYS["enriched_on"]] == "2026-11-27", "the run stamp itself refreshes"
    history = json.loads(row[KEYS["website_monitor_history"]])
    assert len(history) == 2 and history[1]["changes"] == ["best_email", "lead_score"]

    row, stats = run_once(api, RUN3)
    assert row[KEYS["website_comparison_status"]] == "no change"
    assert row[KEYS["website_change_summary"]] == "Nothing changed since the last check."
    assert row[KEYS["website_previous_checked_at"]] == "2026-11-27"
    assert len(json.loads(row[KEYS["website_monitor_history"]])) == 3


def t_columns_and_history_cap():
    assert {"website_comparison_status", "website_change_summary", "website_previous_checked_at"} <= set(ge.OUTPUTS["website"])
    status, summary, changes = ge._website_changes({"best_email": "a@x.co.uk"}, {}, KEYS)
    assert status == "first check" and summary == "" and changes == []
    previous = json.dumps([{"checked_at": "2026-01-01", "status": "changed", "changes": []}] * 12)
    capped = json.loads(ge._website_monitor_history({"enriched_on": "2026-12-04"}, previous, "no change", []))
    assert len(capped) == 12 and capped[-1]["checked_at"] == "2026-12-04", "history keeps the last 12 checks"


def t_a_weekly_schedule_validates():
    catalog = json.loads((Path(__file__).resolve().parents[1] / "bridge" / "catalog.json").read_text(encoding="utf-8"))
    tools = catalog["tools"]
    assert schedules.schedulable("dse.grid_enrich", tools["dse.grid_enrich"]) == ""
    schedule = {"frequency": "weekly", "weekday": 0, "at_time": "07:30", "tool": "dse.grid_enrich",
                "params": {"grid": "Leads", "lane": "website", "limit": 25, "output_detail": "essentials", "overwrite": True}}
    problems = schedules.validate(schedule, tools)
    assert problems == [], problems
    assert "schedule this tool from the Schedules page" in tools["dse.grid_enrich"]["help"]


check("three runs: first check, then a named diff, then no change", t_three_runs)
check("the comparison columns ship with the website lane and history caps at 12", t_columns_and_history_cap)
check("a weekly re-enrichment schedule validates against the real catalog", t_a_weekly_schedule_validates)

print("\n%d FAILED" % len(FAILED) if FAILED else "\nALL PASS")
sys.exit(1 if FAILED else 0)
