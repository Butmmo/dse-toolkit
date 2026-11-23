"""Engines: a member's own outreach businesses, each a settings file plus its own folders.

    engines/<slug>/engine.json        made by DBI Citadel (HQ Tools → My engines) and synced here by the runner
    engines/<slug>/send-lists/        dated lists; drafts/ holds new ones to spot-check first
    engines/<slug>/content/           idea seeds, inbox.csv (later phases)
    engines/<slug>/data/              the engine's own log and caches

`python dse.py daily <slug>` builds the next dated send lists for an engine:
find (or the engine's own seed list) → website check with the path's pack → drop anyone the engine already
has on any list → pick each lead's channel (the engine's order, within its daily caps) → draft the opener
from the engine's wording → engines/<slug>/send-lists/drafts/<date>.csv, ready for the cockpit/Send Desk.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

from . import check as chk
from . import authority, importer, places, podcasts
from .common import ROOT, log, read_csv, write_csv

ENGINES = ROOT / "engines"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
CHANNELS = ("Instagram DM", "Facebook message", "Email", "Website form", "LinkedIn message")


def engine_dir(slug: str) -> Path:
    if not SLUG.match(slug or ""):
        sys.exit(f"Not an engine name: {slug!r}")
    return ENGINES / slug


def load(slug: str) -> dict:
    p = engine_dir(slug) / "engine.json"
    if not p.exists():
        have = ", ".join(all_slugs()) or "none yet (create one in Citadel: HQ Tools → My engines)"
        sys.exit(f"No engine '{slug}'. Engines on this PC: {have}")
    cfg = json.loads(p.read_text(encoding="utf-8"))
    cfg["slug"] = slug
    return cfg


def all_slugs(include_archived: bool = False) -> list[str]:
    if not ENGINES.exists():
        return []
    out = []
    for p in sorted(ENGINES.glob("*/engine.json")):
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if include_archived or not cfg.get("archived"):
            out.append(p.parent.name)
    return out


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def domain(url: str) -> str:
    u = (url or "").lower().strip()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.split("/")[0]


def already_listed(slug: str) -> tuple[set, set]:
    """Domains and names already on any of this engine's lists (sent, drafted or skipped): never list twice."""
    doms, names = set(), set()
    for p in (engine_dir(slug) / "send-lists").rglob("*.csv"):
        try:
            rows = read_csv(p)
        except Exception:
            continue
        for r in rows:
            d = domain(r.get("website", ""))
            if d:
                doms.add(d)
            n = norm(r.get("business") or r.get("name") or "")
            if n:
                names.add(n)
    return doms, names


def pick_channel(row: dict, order: list[str], left: dict) -> tuple[str, str]:
    """(channel, where) for a lead: the first channel in the engine's order that this lead has and that still
    has room today. Instagram needs a handle, Facebook a page, Email an address, Website form a website."""
    have = {
        "Instagram DM": row.get("instagram", ""),
        "Facebook message": row.get("facebook", ""),
        "Email": row.get("email", ""),
        "Website form": row.get("website", ""),
        "LinkedIn message": row.get("linkedin", ""),
    }
    for ch in order:
        if have.get(ch) and left.get(ch, 0) > 0:
            return ch, have[ch]
    return "", ""


def fill(template: str, row: dict, cfg: dict) -> str:
    business = re.sub(r"\s*\([^)]*\)\s*$", "", row.get("business") or row.get("name") or "").strip()
    vals = {"business": business or "there", "city": (row.get("city") or "your area").strip(),
            "gap_line": row.get("gap_line") or row.get("gap_used") or "", "sender": cfg.get("sender_name", ""),
            "brand": cfg.get("brand_name", ""), "host": (row.get("host") or "").split(" ")[0] or "there",
            "contact_first": (row.get("contact_first") or (row.get("contact_name") or "").split(" ")[0] or "there"),
            "title": row.get("contact_title", "")}
    try:
        return template.format(**vals).strip()
    except (KeyError, IndexError, ValueError) as e:
        return f"[opener template problem: {e}] " + template


def candidates(cfg: dict, need: int, render: bool) -> list[dict]:
    """New, checked leads for the engine: from the lead finder, Apple Podcasts, or the engine's own seed list."""
    slug, path = cfg["slug"], cfg.get("path", "smb")
    mode = cfg.get("source") if path == "custom" else {"gtm": "import", "authority": "pasted"}.get(path)   # custom engines pick their own lead source
    raw = engine_dir(slug) / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    stamp = dt.date.today().isoformat()
    doms, names = already_listed(slug)

    def fresh(rows):
        out = []
        for r in rows:
            d, n = domain(r.get("website", "")), norm(r.get("business") or r.get("name") or "")
            if (d and d in doms) or (n and n in names):
                continue
            doms.add(d) if d else None
            names.add(n) if n else None
            out.append(r)
        return out

    if mode == "import":
        return import_candidates(cfg, need, render, fresh)
    if mode == "pasted":
        rows = fresh(authority.audit(slug, int(cfg.get("min_score", 4))))
        if not rows:
            log(f"  No expert with a gap to lead with yet. Put your CSV in engines/{slug}/pasted/ (run: python dse.py import {slug}).")
        return rows[:need]

    if path == "broadcast" or mode == "podcasts":
        topics = cfg.get("topics") or ["business"]
        src = podcasts.find("; ".join(topics), cfg.get("genre", "business"), max(need * 3, 30), out=str(raw / f"{stamp}-podcasts.csv"))
        rows = [r for r in fresh(read_csv(src)) if str(r.get("gap_count", "0")) not in ("", "0")]
        for r in rows:
            r["gap_line"] = r.get("gap_used", "")
        return rows[:need]

    seeds = list(cfg.get("seed_urls") or []) + list(cfg.get("local_seed_urls") or [])      # the ones from Citadel, plus the ones brought in from a folder on this PC
    if seeds or path in ("ministry", "revenue", "ascent") or mode == "seeds":
        rows = [{"business": u.get("name") or domain(u.get("url", "")), "website": u.get("url", ""), "city": u.get("city", "")}
                if isinstance(u, dict) else {"business": domain(u), "website": u, "city": ""} for u in seeds]
        rows = fresh(rows)[: need * 2]
        if not rows:
            log("  No unchecked seed websites left: add more in Citadel (My engines → this engine).")
            return []
        seed_csv = raw / f"{stamp}-seeds.csv"
        write_csv(seed_csv, rows)
        checked = chk.check_file(cfg.get("pack", path), str(seed_csv), render=render, out=str(raw / f"{stamp}-seeds-checked.csv"))
        return [r for r in read_csv(checked) if r.get("gap_line")][:need]

    kinds = cfg.get("kinds") or []
    cities = "; ".join(cfg.get("cities") or [])
    if not kinds or not cities:
        sys.exit("This engine needs at least one business type and one city (edit it in Citadel).")
    pool = []
    for kind in kinds:
        if len(pool) >= need:
            break
        src = places.find(kind, cities, float(cfg.get("miles", 25)), max(need * 3, 30), out=str(raw / f"{stamp}-{kind}.csv"))
        new = fresh(read_csv(src))
        if not new:
            continue
        new_csv = raw / f"{stamp}-{kind}-new.csv"
        write_csv(new_csv, new)
        checked = chk.check_file(cfg.get("pack", path), str(new_csv), render=render, out=str(raw / f"{stamp}-{kind}-checked.csv"))
        pool += [r for r in read_csv(checked) if r.get("gap_line")]
    return pool[:need]


def import_candidates(cfg: dict, need: int, render: bool, fresh) -> list[dict]:
    """Go-to-Market: accounts from your own exports (engines/<slug>/imports/*.csv), scored, website-checked, ranked."""
    slug = cfg["slug"]
    rows, _rep = importer.load_all(slug)
    if not rows:
        log(f"  No file in engines/{slug}/imports/. Export a list from your own Clay, Apollo or HubSpot account and save the CSV there (check it with: python dse.py import {slug}).")
        return []
    validate_waterfall_outreach_rows(slug, rows)
    best: dict[str, dict] = {}
    for r in rows:                                          # one account per website: keep the contact with the best score
        if not r["website"]:
            continue
        pts, why = importer.icp(r)
        r["icp"], r["icp_why"] = pts, "; ".join(why)
        if r["website"] not in best or pts > best[r["website"]]["icp"]:
            best[r["website"]] = r
    pool = fresh(sorted(best.values(), key=lambda r: -r["icp"]))[: need * 3]
    if not pool:
        log("  Every account in your files is already on a list. Export more.")
        return []
    raw = engine_dir(slug) / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    stamp = dt.date.today().isoformat()
    src = raw / f"{stamp}-import.csv"
    write_csv(src, pool)
    checked = read_csv(chk.check_file(cfg.get("pack", "gtm"), str(src), render=render, out=str(raw / f"{stamp}-import-checked.csv")))
    checked = [r for r in checked if r.get("gap_line")]
    for r in checked:
        r["check_notes"] = "; ".join(x for x in (r.get("icp_why", ""), r.get("check_notes", "")) if x)
    checked.sort(key=lambda r: -(int(r.get("icp") or 0) + min(int(r.get("gap_count") or 0), 3)))
    return checked[:need]


def validate_waterfall_outreach_rows(slug: str, candidates: list[dict]) -> None:
    """Keep experiment variants, assignment modes, and assignment seeds consistent per Engine cohort."""
    tagged = []
    for row in candidates:
        experiment = (row.get("waterfall_experiment_id") or "").strip()
        variant = (row.get("waterfall_experiment_variant") or "").strip().upper()
        lead_id = (row.get("waterfall_experiment_lead_id") or "").strip()
        field = (row.get("waterfall_experiment_field") or "").strip()
        if not experiment:
            continue
        if not lead_id or variant not in {"A", "B"}:
            raise ValueError("Waterfall experiment rows need a stable lead ID and variant A or B before Engine outreach.")
        assignment_id = (row.get("waterfall_outreach_assignment_experiment_id") or "").strip()
        assignment_variant = (row.get("waterfall_outreach_assignment_variant") or "").strip().upper()
        assignment_seed = (row.get("waterfall_outreach_assignment_seed") or "").strip()
        if assignment_id and (assignment_id != experiment or assignment_variant != variant or not assignment_seed):
            raise ValueError(f"Experiment lead {lead_id!r} has conflicting outreach assignment metadata; regenerate it with `eval-enrichment assign-outreach`.")
        if not assignment_id and (assignment_variant or assignment_seed):
            raise ValueError(f"Experiment lead {lead_id!r} has incomplete outreach assignment metadata; regenerate it with `eval-enrichment assign-outreach`.")
        tagged.append((experiment, field, lead_id, variant, "single_variant_assigned" if assignment_id else "legacy_variant_tag_unassigned", assignment_seed))
    if not tagged:
        return

    exposures: dict[tuple[str, str, str], set[str]] = {}
    modes: dict[tuple[str, str], set[str]] = {}
    seeds: dict[tuple[str, str], set[str]] = {}

    def record(experiment: str, field: str, lead_id: str, variant: str, mode: str, seed: str) -> None:
        exposures.setdefault((experiment, field, lead_id), set()).add(variant)
        cohort = (experiment, field)
        modes.setdefault(cohort, set()).add(mode)
        if mode == "single_variant_assigned":
            if not seed:
                raise ValueError(f"Experiment {experiment!r} has assigned rows without an assignment seed; reassign the complete cohort before outreach.")
            seeds.setdefault(cohort, set()).add(seed)

    for experiment, field, lead_id, variant, mode, seed in tagged:
        record(experiment, field, lead_id, variant, mode, seed)
    for p in (engine_dir(slug) / "send-lists").rglob("*.csv"):
        try:
            existing_rows = read_csv(p)
        except Exception:
            continue
        for row in existing_rows:
            experiment = (row.get("waterfall_experiment_id") or "").strip()
            variant = (row.get("waterfall_experiment_variant") or "").strip().upper()
            lead_id = (row.get("waterfall_experiment_lead_id") or "").strip()
            field = (row.get("waterfall_experiment_field") or "").strip()
            if experiment and lead_id and variant in {"A", "B"}:
                assignment_id = (row.get("waterfall_outreach_assignment_experiment_id") or "").strip()
                assignment_variant = (row.get("waterfall_outreach_assignment_variant") or "").strip().upper()
                assignment_seed = (row.get("waterfall_outreach_assignment_seed") or "").strip()
                if assignment_id and (assignment_id != experiment or assignment_variant != variant):
                    raise ValueError(f"Existing Send Desk list {p.name} has conflicting assignment metadata for experiment {experiment!r}.")
                if not assignment_id and (assignment_variant or assignment_seed):
                    raise ValueError(f"Existing Send Desk list {p.name} has incomplete assignment metadata for experiment {experiment!r}.")
                record(experiment, field, lead_id, variant,
                       "single_variant_assigned" if assignment_id else "legacy_variant_tag_unassigned", assignment_seed)

    mixed = [(key, value) for key, value in modes.items() if len(value) > 1]
    if mixed:
        (experiment, _field), value = mixed[0]
        raise ValueError(f"Blocked Engine list: experiment {experiment!r} mixes assigned and legacy unassigned rows ({', '.join(sorted(value))}). Keep the cohort on one assignment workflow before continuing.")
    inconsistent_seeds = [(key, value) for key, value in seeds.items() if len(value) > 1]
    if inconsistent_seeds:
        (experiment, _field), value = inconsistent_seeds[0]
        raise ValueError(f"Blocked Engine list: experiment {experiment!r} has multiple outreach assignment seeds ({', '.join(sorted(value))}). Use one fixed seed for the whole experiment cohort.")
    conflicts = [(key, variants) for key, variants in exposures.items() if len(variants) > 1]
    if conflicts:
        (experiment, _field, lead_id), variants = conflicts[0]
        raise ValueError(f"Blocked Engine list: experiment {experiment!r} would put lead {lead_id!r} in both variants {', '.join(sorted(variants))}. Keep paired enrichment outputs outside engines/{slug}/imports and import only the `*-outreach-assigned.csv` produced by `python dse.py eval-enrichment assign-outreach <paired.csv> --experiment-id {experiment}`.")


def daily(slug: str, start: str | None = None, days: int = 1, per_day: int | None = None, render: bool = True) -> list[str]:
    cfg = load(slug)
    if cfg.get("archived"):
        sys.exit(f"Engine '{slug}' is archived.")
    if cfg.get("path") == "custom" and cfg.get("source", "none") == "none":
        print(f"'{cfg.get('name', slug)}' is a chat-and-notes engine: there are no lead lists to build. Open DBI-AI and pick it from the menu.")
        return []
    per_day = per_day or int(cfg.get("per_day", 20))
    caps = {ch: int((cfg.get("caps") or {}).get(ch, 999)) for ch in CHANNELS}
    order = [c for c in (cfg.get("channels") or list(CHANNELS)) if c in CHANNELS]
    first = dt.date.fromisoformat(start) if start else dt.date.today() + dt.timedelta(days=1)
    dates = []
    d = first
    while len(dates) < days:
        if d.weekday() != 6 or cfg.get("sundays"):
            dates.append(d)
        d += dt.timedelta(days=1)
    log(f"Engine '{cfg.get('name', slug)}' ({cfg.get('path')}): {per_day} a day for {days} day(s) from {dates[0]}")
    pool = candidates(cfg, per_day * days, render)
    opener_tpl = cfg.get("opener") or chk.load_pack(cfg.get("pack", cfg.get("path", "smb"))).get("opener", "")
    if cfg.get("path") == "broadcast" or (cfg.get("path") == "custom" and cfg.get("source") == "podcasts"):
        opener_tpl = cfg.get("opener") or podcasts.OPENER.replace("{show}", "{business}").replace("{genre}", cfg.get("genre", "business"))
    written = []
    # Straight onto the engine's send lists (the Send Desk shows them; Skip anything that looks wrong), unless the
    # engine asks for drafts to spot-check first.
    out_dir = engine_dir(slug) / "send-lists" / ("drafts" if cfg.get("drafts_first") else "")
    for day in dates:
        left = dict(caps)
        rows = []
        while pool and len(rows) < per_day:
            r = pool.pop(0)
            ch, where = pick_channel(r, order, left)
            if not ch:
                continue
            left[ch] -= 1
            ai_body = (r.get("outreach_body") or "").strip() if ch == "email" else ""
            ai_subject = (r.get("outreach_subject") or "").strip() if ai_body else ""
            drafted_opener = (f"Subject: {ai_subject}\n\n{ai_body}" if ai_subject else ai_body) or fill(opener_tpl, r, cfg)
            lead_list_row = {"row": len(rows) + 1, "business": r.get("business", ""), "city": r.get("city", ""),
                         "channel": ch, "where": where, "gap_used": r.get("gap_line") or r.get("gap_used", ""),
                         "variant": cfg.get("variant") or f"{cfg.get('path')}-opener-v1",
                         "opener": drafted_opener, "website": r.get("website", ""),
                         "herald_sources": r.get("herald_sources", r.get("research_sources", "")),
                         "herald_company_findings": r.get("herald_company_findings", ""),
                         "herald_company_sources": r.get("herald_company_sources", ""),
                         "herald_person_findings": r.get("herald_person_findings", ""),
                         "herald_person_sources": r.get("herald_person_sources", ""),
                         "herald_role_candidates": r.get("herald_role_candidates", ""),
                         "herald_people_candidates": r.get("herald_people_candidates", ""),
                         "herald_business_assessment": r.get("herald_business_assessment", ""),
                         "herald_role_assessment": r.get("herald_role_assessment", ""),
                         "herald_signal_events": r.get("herald_signal_events", ""),
                         "herald_legal_form_assessment": r.get("herald_legal_form_assessment", ""),
                         "herald_assessed_at": r.get("herald_assessed_at", ""),
                         "herald_assessment_note": r.get("herald_assessment_note", ""),
                         "herald_identity_summary": r.get("herald_identity_summary", ""),
                         "herald_ai_review": r.get("herald_ai_review", ""),
                         "herald_ai_reviewed_at": r.get("herald_ai_reviewed_at", ""),
                         "herald_ai_review_model": r.get("herald_ai_review_model", ""),
                         "enrichment_target_profile": r.get("enrichment_target_profile", ""),
                         "enrichment_target_decision_maker": r.get("enrichment_target_decision_maker", ""),
                         "enrichment_target_role": r.get("enrichment_target_role", ""),
                         "enrichment_target_legal_form": r.get("enrichment_target_legal_form", ""),
                         "enrichment_target_path": r.get("enrichment_target_path", ""),
                         "enrichment_search_strategy": r.get("enrichment_search_strategy", ""),
                         "herald_status": r.get("herald_status", r.get("research_status", "")),
                         "presence_signals": r.get("presence_signals", ""), "presence_sources": r.get("presence_sources", ""),
                         "field_results": r.get("field_results", ""),
                         "outreach_subject": ai_subject, "outreach_body": ai_body,
                         "outreach_evidence": r.get("outreach_evidence", ""),
                         "outreach_evidence_detail": r.get("outreach_evidence_detail", ""),
                         "outreach_personalization_basis": r.get("outreach_personalization_basis", ""),
                         "research_sources": r.get("research_sources", ""), "research_status": r.get("research_status", ""),
                         "gaps_found": r.get("gaps_found", ""), "email": r.get("email", ""), "phone": r.get("phone", ""),
                         "instagram": r.get("instagram", ""), "facebook": r.get("facebook", ""),
                         "category": r.get("category", ""), "host": r.get("host", ""),
                         "linkedin": r.get("linkedin", ""), "contact_name": r.get("contact_name", ""), "contact_title": r.get("contact_title", ""),
                         "notes": "; ".join(x for x in (r.get("check_notes", ""), r.get("source", "")) if x)}
            if r.get("waterfall_experiment_id"):
                for field in ("waterfall_experiment_id", "waterfall_experiment_variant", "waterfall_experiment_field",
                              "waterfall_experiment_providers", "waterfall_experiment_lead_id", "waterfall_config_sha256"):
                    lead_list_row[field] = r.get(field, "")
            if r.get("waterfall_outreach_assignment_experiment_id"):
                for field in ("waterfall_outreach_assignment_experiment_id", "waterfall_outreach_assignment_variant",
                              "waterfall_outreach_assignment_seed"):
                    lead_list_row[field] = r.get(field, "")
            rows.append(lead_list_row)
        if not rows:
            log(f"  {day}: no leads left with a usable channel")
            continue
        p = out_dir / f"{day.isoformat()}.csv"
        write_csv(p, rows, first=["row", "business", "city", "channel", "where", "gap_used", "variant", "opener", "outreach_subject", "outreach_body", "herald_sources", "presence_sources"])
        written.append(str(p))
        by = {}
        for x in rows:
            by[x["channel"]] = by.get(x["channel"], 0) + 1
        print(f"{day}: {len(rows)} leads ({', '.join(f'{v} {k}' for k, v in by.items())}) -> {p.relative_to(ROOT).as_posix()}")
    if not written:
        print("No list written: no new leads with a usable channel. Add cities or business types in Citadel.")
    else:
        print("Spot-check the drafts, then move them from drafts/ into send-lists/." if cfg.get("drafts_first")
              else "Open them in the Send Desk (or the cockpit), check each lead, and Skip anything that looks wrong.")
    return written


def list_engines():
    slugs = all_slugs(include_archived=True)
    if not slugs:
        print("No engines on this PC yet. Create one in DBI Citadel: HQ Tools → My engines → New engine.")
        return
    for s in slugs:
        c = json.loads((ENGINES / s / "engine.json").read_text(encoding="utf-8"))
        lists = len(list((ENGINES / s / "send-lists").glob("*.csv"))) if (ENGINES / s / "send-lists").exists() else 0
        print(f"{s:<26} {c.get('name', '')[:30]:<30} {c.get('path', ''):<11} {lists} lists{'  (archived)' if c.get('archived') else ''}")
