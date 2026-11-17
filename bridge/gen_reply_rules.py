"""Generates src/lib/herald-reply-rules.ts for Citadel from dse/replies.py, so the Herald Inbox sorts replies by exactly the Reply Desk's rules.

    python bridge/gen_reply_rules.py > herald-reply-rules.ts      then copy it over src/lib/herald-reply-rules.ts in the Citadel repo
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dse import replies as R  # noqa: E402

out = {cat: [{"p": p.pattern, "i": bool(p.flags & 2)} for p in pats] for cat, pats in R.RX.items()}
print("// GENERATED from dse/replies.py (the toolkit's Reply Desk) so the Herald Inbox sorts replies by exactly the same rules. Do not edit by hand:")
print("// regenerate with: python bridge/gen_reply_rules.py (in the toolkit) and copy the output over this file.")
print("export const REPLY_PRIORITY = " + json.dumps(R.PRIORITY) + " as const;")
print("export const REPLY_RULES: Record<string, { p: string; i: boolean }[]> = " + json.dumps(out, indent=1) + ";")
