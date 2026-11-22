"""Run the existing enrichment lanes against live Ledger rows and write their fields back to the grid."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
import tempfile
from pathlib import Path

from . import gridpush, gridrun
from .common import LISTS, ROOT

LANES = {"website", "herald", "presence"}
OUTPUTS = {
    "website": ["best_email", "best_email_source", "email_kind", "decision_maker", "decision_maker_title", "decision_maker_source", "phone_found", "contact_form_url", "booking_tool", "linkedin_found", "instagram_found", "facebook_found", "x_found", "youtube_found", "tech_stack", "site_description", "site_active", "mx_ok", "icp_hits", "lead_score", "lead_why", "enriched_on", "waterfall_metrics", "firmographics", "field_waterfall_metrics"],
    "herald": ["herald_company_findings", "herald_person_findings", "herald_signal_events", "herald_identity_summary", "herald_business_assessment", "herald_role_assessment", "herald_legal_form_assessment", "herald_checked_at", "herald_status", "herald_comparison_status", "herald_change_summary", "herald_new_source_urls", "herald_changed_source_urls", "herald_not_returned_urls", "herald_previous_checked_at", "herald_ai_review", "outreach_subject", "outreach_body", "outreach_evidence_detail"],
    "presence": ["presence_sources", "presence_checked_at", "presence_status", "presence_comparison_status", "presence_change_summary", "presence_new_source_urls", "presence_changed_source_urls", "presence_not_returned_urls"],
}
FULL_OUTPUTS = {
    "website": ["found_email", "email_source", "other_emails", "email_guesses", "email_check", "contact_page_url", "field_results", "enrichment_audit"],
    "herald": ["herald_findings", "herald_sources", "herald_company_sources", "herald_person_sources", "herald_role_candidates", "herald_people_candidates", "research_findings", "research_sources", "research_searched_at", "research_status", "enrichment_search_strategy", "field_results"],
    "presence": ["presence_signals", "field_results", "presence_search_waterfall"],
}


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _read_result(path: Path) -> tuple[list[str], list[dict]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader.fieldnames or []), list(reader)


def _run_lane(source: Path, lane: str, engine: str, limit: int, output_detail: str,
              icp: str = "", waterfall_config: str = "", dry_run: bool = False,
              path: str = "any", profile: str = "any", decision_maker: str = "any", legal_form: str = "any",
              decision_role: str = "signal_based", custom_role: str = "", search_provider: str = "duckduckgo",
              search_budget: int = 12, minimum_identity_score: float = 0.0, use_ai: bool = True):
    if lane == "website":
        from . import enrich
        report = enrich.enrich_file(str(source), icp=icp, engine=engine, max_rows=limit, render=False,
                                    waterfall_config_path=waterfall_config, dry_run=dry_run)
        m = re.search(r"Saved: (\S+\.csv)", report)
    elif lane == "herald":
        from . import signal_enrichment
        report = signal_enrichment.enrich_file(str(source), engine=engine, max_rows=limit, use_ai=use_ai,
            business_profile=profile, decision_maker=decision_maker, legal_form=legal_form, decision_role=decision_role,
            custom_role=custom_role, search_provider=search_provider, path_key=path, search_budget=search_budget,
            minimum_identity_score=minimum_identity_score)
        m = re.search(r"Saved: (\S+\.csv)", report)
    else:
        from . import signal_enrichment
        report = signal_enrichment.enrich_presence_file(str(source), engine=engine, max_rows=limit,
            search_budget=min(search_budget, 10), minimum_identity_score=minimum_identity_score)
        m = re.search(r"Saved: (\S+\.csv)", report)
    if not m:
        raise RuntimeError("The enrichment finished but did not report its result CSV path.")
    result_path = ROOT / m.group(1)
    if not result_path.is_file():
        raise RuntimeError("The enrichment result CSV is missing from this PC.")
    headers, rows = _read_result(result_path)
    selected = list(OUTPUTS[lane])
    if output_detail == "full":
        selected.extend(FULL_OUTPUTS[lane])
    selected = [h for h in selected if h in headers]
    return result_path, selected, rows


def run(grid_ref: str, lane: str, engine: str = "", limit: int = 25, output_detail: str = "essentials",
        overwrite: bool = False, api=None, say=lambda *_: None, **options) -> str:
    if lane not in LANES:
        raise ValueError("Choose website, herald or presence.")
    lane_limit = 50 if lane in ("herald", "presence") else 500
    if not 1 <= limit <= lane_limit:
        raise ValueError(f"Process 1 to {lane_limit} {lane} grid rows per run.")
    if output_detail not in ("essentials", "full"):
        raise ValueError("output detail must be essentials or full.")
    api = api or gridpush.connect()
    if api is None:
        raise RuntimeError("This PC is not connected to Citadel yet (run the HQ Tools setup first).")
    grid = gridpush.resolve_grid(gridpush._grids(api), grid_ref)
    columns = gridpush.columns_of(grid.get("doc"))
    rows = gridrun.read_rows(api, grid["id"])
    if not rows:
        return f"{grid.get('workbook', '')}/{grid['name']}: this grid has no rows.\n"
    source_rows = rows[:limit]
    headers = [c["label"] for c in columns]
    with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", suffix=".csv", prefix="grid-enrich-", dir=LISTS, delete=False) as file:
        input_path = Path(file.name)
        writer = csv.DictWriter(file, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        key_by_label = {gridpush.norm(c["label"]): c["key"] for c in columns}
        for row in source_rows:
            data = row.get("data") or {}
            writer.writerow({c["label"]: _cell(data.get(c["key"])) for c in columns})
    say(f"{grid.get('workbook', '')}/{grid['name']}: running {lane} enrichment on {len(source_rows)} live grid rows.")
    try:
        result_path, output_headers, enriched_rows = _run_lane(input_path, lane, engine, len(source_rows), output_detail, **options)
    finally:
        input_path.unlink(missing_ok=True)
    if len(enriched_rows) != len(source_rows):
        raise RuntimeError(f"The enrichment returned {len(enriched_rows)} rows for {len(source_rows)} inputs; nothing was written to the grid.")
    existing = {gridpush.norm(c["label"]): c for c in columns}
    new_headers = [h for h in output_headers if gridpush.norm(h) not in existing]
    remaining = max(0, 60 - len(columns))
    omitted_columns = new_headers[remaining:]
    new_headers = new_headers[:remaining]
    added = api.rpc("hq_grid_add_columns", {"p_grid": grid["id"], "p_cols": [{"label": h, "type": gridpush.infer_type([r.get(h, "") for r in enriched_rows])} for h in new_headers]}, tries=2) if new_headers else []
    by_label = {gridpush.norm(c["label"]): c for c in columns}
    for column in added or []:
        by_label[gridpush.norm(column["label"])] = column
    output_to_key = {h: by_label[gridpush.norm(h)]["key"] for h in output_headers if gridpush.norm(h) in by_label}
    updates, skipped, oversized = [], 0, 0
    for source_row, result_row in zip(source_rows, enriched_rows):
        cells = {}
        data = source_row.get("data") or {}
        for header, key in output_to_key.items():
            value = _cell(result_row.get(header))
            if not value:
                continue
            if not overwrite and data.get(key) not in (None, ""):
                continue
            if len(value) > 5000:
                oversized += 1
                continue
            cells[key] = value
        if cells:
            updates.append({"id": source_row["id"], "cells": cells})
        else:
            skipped += 1
    written = 0
    for offset in range(0, len(updates), 100):
        written += gridrun.save_cells(api, grid["id"], updates[offset:offset + 100])
        say(f"PROGRESS {min(offset + 100, len(updates))}/{len(updates)} failed 0 skipped {skipped}")
    omitted_note = f" {len(omitted_columns)} output columns could not be added because this grid is at its 60-column limit." if omitted_columns else ""
    return (f"FINISHED {lane} enrichment: {written} rows updated, {skipped} rows had no new values, {oversized} oversized values omitted. "
            f"Created or reused {len(output_to_key)} output columns; report saved at {result_path.relative_to(ROOT).as_posix()}.{omitted_note}\n")


def cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="dse.py grid enrich")
    parser.add_argument("grid")
    parser.add_argument("--lane", choices=sorted(LANES), default="website")
    parser.add_argument("--engine", default="")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--output-detail", choices=["essentials", "full"], default="essentials")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--icp", default="")
    parser.add_argument("--waterfall-config", default="")
    parser.add_argument("--dry-run-providers", action="store_true")
    parser.add_argument("--path", default="any")
    parser.add_argument("--profile", default="any")
    parser.add_argument("--decision-maker", default="any")
    parser.add_argument("--legal-form", default="any")
    parser.add_argument("--decision-role", default="signal_based")
    parser.add_argument("--custom-role", default="")
    parser.add_argument("--search-provider", default="duckduckgo")
    parser.add_argument("--search-budget", type=int, default=12)
    parser.add_argument("--minimum-identity-score", type=float, default=0.0)
    parser.add_argument("--no-ai", action="store_true")
    args = parser.parse_args(argv)
    options = vars(args).copy()
    grid = options.pop("grid")
    lane = options.pop("lane")
    options["dry_run"] = options.pop("dry_run_providers")
    options["use_ai"] = not options.pop("no_ai")
    try:
        print(run(grid, lane, say=lambda m: print(m, flush=True), **options), end="")
        return 0
    except (ValueError, RuntimeError) as error:
        print("grid enrich: " + (str(error)[:300]))
        return 1


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
