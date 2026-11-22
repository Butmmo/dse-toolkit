# Stage 40: Versioned path enrichment profiles

## What changed

Added a previewable, versioned enrichment profile for each current Engine path (general, SMB Optimisation, Search & AI Visibility, AI Voice Receptionist, AI Automation Engineering, Revenue Recovery, Go-to-Market Engineering, Authority Engine, Broadcast Engine and The Ascent). Profiles reuse each path's existing buyer roles, signal priorities, pain hypothesis, commercial checks and next human step, then add explicit field priorities, lane/source order, acceptance guidance, freshness target and budget defaults.

Profiles default to zero optional provider calls and a $0 spend cap. The current defaults allow up to 12 Herald and 3 Presence queries per lead, following the current research waterfall defaults. Expected enrichment coverage is explicitly `not measured yet`; profile previews do not imply expected results.

## Commands

List profiles:

```powershell
python dse.py enrichment-profile list
```

Preview one path:

```powershell
python dse.py enrichment-profile preview automation
```

Adjust preview-only budgets and export a versioned JSON copy for review:

```powershell
python dse.py enrichment-profile export automation --herald-queries 8 --presence-queries 2 --provider-calls 0 --max-spend 0 --freshness-days 90 --out enrichment-profiles\automation.v1.json
```

Use `show <path> --json` for the full structured profile. The defaults and exported copy are recommendations only; they do not yet alter a CSV or Ledger enrichment run.

## Scope and limits

- `dse/enrichment_profiles.py` holds the profile schema/version, path-specific field and business-segment priorities, defaults, validation and CLI.
- Profiles expose acceptance guidance for person identity, company identity, signals, email and legal-form claims. These notes do not replace the field/provider acceptance code.
- Monetary spend and freshness values are preview settings only. Actual execution will require a follow-up integration with runner options and provider pricing metadata.
- User-authored profile files can be exported for review, but loading edited profiles into runs is not implemented yet.
- No database migration is needed. No enrichment or provider request is triggered by profile commands.

## Next slice

Connect the profile to actual lead and Ledger-grid run configuration: allow users to choose a saved profile, preview the selected segment and source/budget plan, and enforce the supported limits during execution. Then use the Stage 39 evaluator to compare profile versions on reviewed data.

No automated test suite was added or run in this slice.
