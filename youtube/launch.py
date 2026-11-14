"""YouTube Launchpad: build a YouTube channel from zero, and keep improving it until it can earn.

    python youtube/launch.py plan   --niche ai-tools --faceless yes --goal leads --hours 6 [--topic "..."] [--name "..."]
    python youtube/launch.py ideas  --channel <slug> [--count 10] [--angle "..."]
    python youtube/launch.py script --channel <slug> --title "..." [--minutes 8] [--ai]
    python youtube/launch.py track  --channel <slug> --subs 120 --watch-hours 85 --shorts-views 4000 [--views 900] [--ctr 4.2] [--avd 38]
    python youtube/launch.py check  --title "..." [--keyword "..."] [--description "..."] [--thumb "..."]
    python youtube/launch.py niches

Each channel lives in youtube/channels/<slug>/: CHANNEL-PLAN.md (the 90-day plan), ideas.csv (30 video ideas
with title, hook, thumbnail and Short), scripts/, tracker.csv and PROGRESS.md (where you stand against the
Partner Program numbers). Free, stdlib only; --ai adds a first draft from your local Ollama model.
It teaches the method and the odds honestly. It cannot promise income, and nothing here uploads, posts or pays.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import knowledge as K  # noqa: E402

HERE = Path(__file__).resolve().parent
CH = HERE / "channels"
ORDER = ["how", "explain", "mistakes", "story", "wish", "checklist", "truth"]
YEAR = dt.date.today().year


# ------------------------------------------------------------------ helpers

def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40].strip("-") or "channel"


def clean(s: str, n: int = 200) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[\"\\<>`{}$]", "", s or "")).strip()[:n]


def write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


def load_channel(slug: str) -> dict:
    f = CH / slug / "channel.json"
    if not f.exists():
        sys.exit(f"No channel '{slug}'. Make one first: python youtube/launch.py plan ...")
    return json.loads(f.read_text(encoding="utf-8"))


def ollama(prompt: str, timeout: int = 240) -> str | None:
    model = os.environ.get("OLLAMA_MODEL", "gemma3:1b")
    body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    try:
        req = urllib.request.Request("http://localhost:11434/api/generate", body, {"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())["response"].strip()
    except Exception:
        return None


def seeds_for(niche: str, topic: str) -> list[tuple[str, str]]:
    if niche in K.NICHES:
        out = []
        for s in K.NICHES[niche]["seeds"]:
            t, n = [x.strip() for x in s.split("|")]
            out.append((t, n))
        if topic:
            out.insert(0, (topic, topic))
        return out
    return [(topic, topic)]


def formats_for(niche: str, faceless: bool) -> list[str]:
    pool = K.NICHES.get(niche, {}).get("formats", ["slides", "screen", "talking"])
    ok = [f for f in pool if (K.FORMATS[f][1] or not faceless)]
    return ok or (["slides", "screen"] if faceless else ["talking", "slides"])


def make_ideas(niche: str, topic: str, faceless: bool, start: int, count: int, have: set[str]) -> list[dict]:
    seeds = seeds_for(niche, topic)
    fmts = formats_for(niche, faceless)
    pool = []
    rounds = len(ORDER) if len(seeds) > 1 else len(ORDER)
    for r in range(rounds):
        for si, (t, n) in enumerate(seeds):
            pid = ORDER[(si + r) % len(ORDER)]
            pool.append((si, r, pid, t, n))
    rows = []
    for si, r, pid, t, n in pool:
        tpls, intent, hooks, thumb, short = K.TITLE_PATTERNS[pid]
        cap = n if re.match(r"[a-z]\d", n) else n[:1].upper() + n[1:]
        fmt_all = lambda x: x.format(t=t, n=n, N=cap, year=YEAR)  # noqa: E731
        title = next((fmt_all(x) for x in tpls if len(fmt_all(x)) <= 62), "")
        if not title or title.lower() in have:
            continue
        k = start + len(rows)
        fmt = fmts[k % len(fmts)]
        rows.append({
            "n": k + 1, "title": title, "intent": intent, "format": K.FORMATS[fmt][0],
            "hook": hooks[k % 3].format(t=t, n=n, N=cap, n3="3", year=YEAR),
            "thumbnail": thumb + (". Show the object or screen, no face needed." if faceless else ". Your face with one clear emotion works well."),
            "short_cutdown": short, "length_hint": "6-9 min" if intent in ("how-to", "checklist", "explainer") else "5-8 min",
            "status": "idea"})
        have.add(title.lower())
        if len(rows) >= count:
            break
    return rows


IDEA_COLS = ["n", "title", "intent", "format", "hook", "thumbnail", "short_cutdown", "length_hint", "status"]


def read_ideas(slug: str) -> list[dict]:
    f = CH / slug / "ideas.csv"
    if not f.exists():
        return []
    with f.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_ideas(slug: str, rows: list[dict]) -> None:
    f = CH / slug / "ideas.csv"
    with f.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=IDEA_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# ------------------------------------------------------------------ plan

def cadence(hours: int) -> tuple[str, int, int]:
    """(plain words, long videos in 13 weeks, shorts in 13 weeks). A beginner needs about 4-6 hours per 6-9 minute video."""
    if hours <= 3:
        return "1 long video every 2 weeks and 1 Short a week", 7, 13
    if hours <= 6:
        return "1 long video a week and 1 Short a week (cut from the long video)", 13, 13
    if hours <= 12:
        return "1 long video a week and 3 Shorts a week", 13, 39
    return "2 long videos a week and 4 Shorts a week", 26, 52


def channel_names(niche: str, topic: str, name: str, name_given: bool = False) -> list[tuple[str, str]]:
    base_words = re.findall(r"[A-Za-z]+", (K.NICHES.get(niche, {}).get("name") or topic))
    stop = {"and", "the", "for", "with", "of", "to", "in", "on", "a", "an", "online", "your", "basics", "everyday", "working"}
    words = [w for w in base_words if w.lower() not in stop][:2] or ["Creator"]
    base = " ".join(w.upper() if w.lower() in {"ai", "seo", "crm"} else w.capitalize() for w in words)
    me = clean(name, 24) if name else ""
    forms = [f"{base} Made Simple", f"The {base} Desk", f"{base} Lab", f"Simply {base}", f"{base} Daily", f"{base} Playbook", f"Learn {base}", f"{base} Step by Step"]
    if me and not name_given:
        forms = [f"{base} with {me}"] + forms
    out = []
    for f in forms[:10]:
        handle = "@" + re.sub(r"[^a-z0-9]", "", f.lower())[:28]
        out.append((f, handle))
    return out


def cmd_plan(a) -> None:
    niche = a.niche
    topic = clean(a.topic, 80)
    if niche != "other" and niche not in K.NICHES:
        sys.exit("Unknown niche. Run: python youtube/launch.py niches")
    if niche == "other" and not topic:
        sys.exit("For 'other' write your topic, for example: --topic \"repair phones\" (a verb phrase works best).")
    faceless = str(a.faceless).lower() in ("yes", "true", "1", "y")
    goal = a.goal if a.goal in K.GOALS else "leads"
    hours = max(1, min(40, int(a.hours)))
    nd = K.NICHES.get(niche, {"name": topic.capitalize(), "audience": "People searching for help with " + topic, "formats": ["slides", "screen", "talking"],
                              "advertiser_demand": "unknown", "policy": "Share only what you know or have tested. Do not make claims you cannot back up.",
                              "income": ["A service or product of your own (leads from the video)", "Affiliate links (disclose)", "Sponsorships"], "seeds": []})
    names = channel_names(niche, topic, a.name or "", bool(a.name))
    chosen = clean(a.name, 40) if a.name else names[0][0]
    chosen_handle = "@" + re.sub(r"[^a-z0-9]", "", chosen.lower())[:28]
    slug = slugify(chosen)
    d = CH / slug
    if d.exists():
        slug = f"{slug}-{dt.date.today():%m%d}"
        d = CH / slug
    cad, longs, shorts = cadence(hours)
    pillar_note = {"ads": "Make videos people search for (how-to, explainers): they keep earning views for years.",
                   "leads": "Every video must lead to one next step you offer. Your future clients are the audience.",
                   "affiliate": "Make comparison and 'how I do it' videos for tools you genuinely use, and disclose every link.",
                   "authority": "Pick one big question in your field and answer it better than anyone else, week after week."}[goal]
    ideas = make_ideas(niche, topic, faceless, 0, 30, set())
    d.mkdir(parents=True, exist_ok=True)
    (d / "scripts").mkdir(exist_ok=True)
    cfg = {"slug": slug, "name": chosen, "niche": niche, "topic": topic, "faceless": faceless, "goal": goal, "hours": hours,
           "created": dt.date.today().isoformat(), "audience": clean(a.audience, 120) or nd["audience"]}
    write(d / "channel.json", json.dumps(cfg, indent=2) + "\n")
    write_ideas(slug, ideas)
    write(d / "tracker.csv", "date,subs,watch_hours_12m,shorts_views_90d,views_28d,uploads,ctr_pct,avg_pct_viewed\n")
    fmt_lines = "\n".join(f"- **{K.FORMATS[f][0]}** (effort {K.FORMATS[f][2]}/3): {K.FORMATS[f][4]} You need: {K.FORMATS[f][3]}." for f in formats_for(niche, faceless))
    lf, sh = K.YPP["long_form"], K.YPP["shorts"]
    mins = lambda m: f"{math.ceil(lf['watch_hours'] * 60 / m):,}"  # noqa: E731
    faceless_block = ""
    if faceless:
        faceless_block = "\n## Faceless: how to stay safe and still monetise\n" + "\n".join(f"- {x}" for x in K.POLICY_FACELESS) + "\n"
    plan = f"""# {chosen}: your 90-day YouTube plan

Made {dt.date.today():%d %b %Y} by the YouTube Launchpad. Topic: **{nd['name']}**{' (' + topic + ')' if topic else ''}. Style: **{'faceless' if faceless else 'on camera'}**. Goal: **{K.GOALS[goal]}**. Time you have: **{hours} hours a week**.

## 1. Your channel in one paragraph
For **{cfg['audience'][:1].lower() + cfg['audience'][1:]}**, **{chosen}** shows how to {topic or 'get real results'} with clear {'screen, slide or voice-led' if faceless else 'on-camera'} videos, so they can act on it the same day. {pillar_note}

## 2. The honest odds (read this once)
- Most new channels take many months to reach the Partner Program numbers, and many never do. The first 90 days are for learning what your audience watches, not for earning.
- The channels that make it publish steadily, improve every video and stay with one topic. Nothing here is a shortcut.
- {'The most reliable income for a new creator is clients, affiliate links or sponsors found through the channel, not ads.' if goal != 'ads' else 'Ads are the slowest income to start. Plan a second route (clients, affiliates, sponsors) from day one so the effort pays while you grow.'}

## 3. What YouTube needs before it pays you (checked {K.CHECKED})
Official source: {K.YPP['sources'][0]}
- **Long-form route:** {lf['subs']:,} subscribers **and** {lf['watch_hours']:,} public watch hours in the last {lf['window_days']} days. Shorts-feed hours do not count.
- **Shorts route:** {sh['subs']:,} subscribers **and** {sh['shorts_views']:,} Shorts views in the last {sh['window_days']} days. A very high bar: treat it as a bonus.
- {K.YPP['review']}
- Also required:
{chr(10).join('  - ' + r for r in K.YPP['requirements'])}
- {K.YPP['note']}
- Policy pages (re-read them every few months, they change): {K.YPP['sources'][1]}

**What 4,000 watch hours means in views.** 4,000 hours is 240,000 minutes. If the average viewer watches **2 minutes**, you need about **{mins(2)}** views. At **4 minutes**: about **{mins(4)}**. At **6 minutes**: about **{mins(6)}**. That is why watch time per view matters more than a long video nobody finishes.

## 4. Other ways this channel earns (usually before ads do)
{chr(10).join('- ' + x for x in nd['income'])}
- Advertiser demand for this topic: **{nd['advertiser_demand']}** (a general pattern, not a promise: what you earn depends on your audience and country).
{('- **Leads plan:** end every video with ONE next step (a free checklist, a call, a message). Put that link first in the description and pin a comment with it. Write down how many leads came from the channel each week.' + chr(10)) if goal == 'leads' else ''}
## 5. Set up the channel (week 1, about 3 hours)
{chr(10).join(f'{i}. {x}' for i, x in enumerate(K.SETUP_CHECKLIST, 1))}

Your name: **{chosen}** (handle to try: {chosen_handle}). {'Other name ideas if it is taken' if a.name else 'Name ideas'}: check each handle in YouTube Studio, because availability is only visible there.
{chr(10).join(f'- {n}  ({h})' for n, h in names)}

## 6. How you will make the videos
{fmt_lines}

Free tools:
{chr(10).join(f'- **{k}:** {v}' for k, v in K.TOOLS_FREE)}
{faceless_block}
## 7. Content mix
- **60% answer videos** (how-to, checklist, explainer): people search for them and they keep earning views.
- **25% proof videos** (you did it, here is what happened): build trust and clients.
- **15% opinion or insight** (what nobody tells beginners): build a following.
- **Shorts:** one idea from each long video, cut to under 60 seconds, ending with "full video on my channel".
- Your first 30 ideas, with titles, hooks, thumbnails and Short cut-downs, are in **ideas.csv**.

## 8. The 90-day roadmap
Your rhythm: **{cad}**. A beginner needs about 4-6 hours for a 6-9 minute video (script, record, edit, thumbnail). That is why this rhythm fits {hours} hours a week. Aim for about {longs} long videos and {shorts} Shorts in 13 weeks.

| Weeks | Focus | You finish |
|---|---|---|
| 1-2 | Set up, then script and record 5 videos before publishing | Channel ready, 5 videos in the bank |
| 3-6 | Publish on schedule. 48 hours after each upload read the click-through rate and where viewers leave | 4-6 videos out, a note on each |
| 7-10 | Find your 3 best videos. Make a new angle on each. Test two thumbnail styles | Top 3 identified, 2 follow-ups out |
| 11-13 | Add your next step for the goal ({goal}). Review the 90 days with the tracker | A decision: keep, sharpen or change angle |

**Weekly routine**
- Monday: pick the next idea from ideas.csv, write the script (`script` tool).
- Tuesday-Wednesday: record and edit.
- Thursday: thumbnail and title (run the `check` tool), schedule the upload.
- Friday: publish, post the Short, reply to every comment in the first hour.
- Sunday (20 minutes): update the tracker (`track` tool) and read PROGRESS.md.

## 9. How to read your numbers
{chr(10).join(f'- **{k}:** {v}' for k, v in K.ANALYTICS_GUIDE)}

## 10. Mistakes to avoid
{chr(10).join('- ' + x for x in K.PITFALLS)}

## 11. Day-90 review (answer in writing)
1. Which 3 videos beat my average, and what do they have in common?
2. What is my average click-through rate and average percentage viewed, compared with day 30?
3. Am I still enjoying the topic enough to make 50 more videos?
4. Which income route has produced a real conversation (a lead, a sponsor enquiry, an affiliate sale)?
5. What will I change in the next 90 days, and what will I keep?

---
Sources and dates are in `knowledge.py` (checked {K.CHECKED}). Policies change: the official pages above always win over this document.
"""
    write(d / "CHANNEL-PLAN.md", plan)
    print(f"Channel '{chosen}' planned in {d}")
    print("Files: CHANNEL-PLAN.md (read this first), ideas.csv (30 video ideas), tracker.csv, scripts/")
    print(f"Next: python youtube/launch.py script --channel {slug} --title \"{ideas[0]['title']}\"")
    print("Reminder: the Partner Program numbers and rules were checked on", K.CHECKED, "- confirm on", K.YPP["sources"][0])


# ------------------------------------------------------------------ ideas

def cmd_ideas(a) -> None:
    cfg = load_channel(a.channel)
    rows = read_ideas(a.channel)
    have = {r["title"].lower() for r in rows}
    angle = clean(a.angle, 80)
    new = []
    if angle:
        tpl = K.TITLE_PATTERNS["how"]
        title = tpl[0][0].format(t=angle, n=angle, N=angle[:1].upper() + angle[1:], year=YEAR)
        if title.lower() not in have:
            have.add(title.lower())
            new.append({"n": len(rows) + 1, "title": title, "intent": tpl[1], "format": K.FORMATS[formats_for(cfg["niche"], cfg["faceless"])[0]][0],
                        "hook": tpl[2][0].format(t=angle, n=angle, N=angle, n3="3", year=YEAR), "thumbnail": tpl[3], "short_cutdown": tpl[4],
                        "length_hint": "6-9 min", "status": "idea"})
    new += make_ideas(cfg["niche"], cfg["topic"], cfg["faceless"], len(rows) + len(new), max(1, min(40, int(a.count))) - len(new), have)
    for i, r in enumerate(new, len(rows) + 1):
        r["n"] = i
    write_ideas(a.channel, rows + new)
    print(f"Added {len(new)} ideas to {CH / a.channel / 'ideas.csv'} (now {len(rows) + len(new)}).")
    for r in new:
        print(f"{r['n']:>3}. {r['title']}")
    if not new:
        print("Every idea from this niche's pool is already in your list. Add your own with --angle \"what you know about\".")


# ------------------------------------------------------------------ script

def cmd_script(a) -> None:
    cfg = load_channel(a.channel)
    title = clean(a.title, 120)
    mins = max(3, min(20, int(a.minutes)))
    idea = next((r for r in read_ideas(a.channel) if r["title"].lower() == title.lower()), None)
    words = mins * 150
    beats = max(3, mins // 2)
    per = int((words - 220) / beats)
    hook = idea["hook"] if idea else "State the result the viewer gets, in one sentence, before anything else."
    fmt = idea["format"] if idea else K.FORMATS[formats_for(cfg["niche"], cfg["faceless"])[0]][0]
    topic_words = [w for w in re.findall(r"[a-z]+", title.lower()) if len(w) > 3][:4]
    ai = ""
    if a.ai:
        draft = ollama(f"Write a spoken YouTube script of about {words} words for the video titled '{title}', for {cfg['audience']}. Start with a 20 second hook. "
                       f"Then {beats} short sections with one practical example each. End with a call to action. Plain words, short sentences, no emojis.")
        ai = ("\n## AI first draft (from your own PC, to rewrite in YOUR voice)\nOriginal content is what YouTube rewards: change every line so it sounds like you and add your own examples.\n\n" + draft + "\n") if draft \
            else "\n(AI draft unavailable: Ollama is not running. The outline above still works.)\n"
    nl = chr(10)
    sections = nl.join(f"""### Section {i}: ______________________ (about {per} words, {per // 150 or 1}:{(per % 150) * 60 // 150:02d} min)
- Point (one sentence the viewer can repeat):
- Example, demo or story that proves it:
- On screen / B-roll: {'screen recording, slide or stock clip' if cfg['faceless'] else 'camera on you, with a cutaway to the thing you are showing'}
- Link line into the next section ("Now that you have X, here is the part most people skip..."):""" for i in range(1, beats + 1))
    text = f"""# Script: {title}

Channel: {cfg['name']} | Format: {fmt} | Target: {mins} min (about {words} words at a natural speaking pace)

## Hook (0:00-0:20, about 50 words)
Pick one and say it in your own words:
- {hook}
- Start with the problem: "You have probably tried to ... and it did not work. Here is why."
- Start with the result: show the finished thing first, then say "I will show you how".
Rules: no greeting, no channel intro, no "before we start". The first sentence must match the title.

## Promise and proof (0:20-0:45)
- What they will be able to do by the end, in one line.
- Why you can say it: one sentence of real experience or evidence.

## Body ({beats} sections)
Change something on screen every 5-10 seconds (cut, zoom, text, new clip). Add a small surprise about every 90 seconds (a mistake, a number, a question) so attention resets.

{sections}

## Recap and next step (last 30 seconds)
- One-line recap of the {beats} points.
- ONE call to action only: {'the free resource or call link in the description (this is how a leads channel earns)' if cfg['goal'] == 'leads' else 'watch the next video (name it)'}.
- Say the title of the next video and show it on an end screen.

## Title options (test the best two)
1. {title}
2. {title.split(':')[0]}: the simple version
3. The truth about {' '.join(topic_words[:2]) or 'this'}: what to do first
4. {' '.join(topic_words[:3]).capitalize() or 'Do this'} in {YEAR}: step by step
5. I tried it so you do not have to: {title}
Check each with the check tool. Keep it under 60 characters if you can, and put the main words first.

## Thumbnail brief
- {idea['thumbnail'] if idea else 'One clear object or screen, 3 words at most, strong contrast.'}
- Test: shrink it to the size of a postage stamp. Can you still read it and tell what it is?

## Description template
Line 1-2 (what shows in search): {topic_words[0] if topic_words else 'main keyword'} - what the viewer will learn, in plain words.
Line 3: {'Your free resource / call link' if cfg['goal'] == 'leads' else 'Your best link'}.
Chapters: 0:00 Intro, 0:45 Section 1, ... (YouTube needs 0:00 and at least three chapters).
Links used: (tools you show; add "Affiliate link" if it is one).
Disclosure: "Some links may be affiliate links. I only recommend what I use."

## Pinned comment
Ask one question the viewer can answer in a sentence, then add your link.

## Short cut-down
{idea['short_cutdown'] if idea else 'The single most useful moment, under 45 seconds, ending with "full video on my channel".'}

## Before you upload
- [ ] Audio is clear (record 10 seconds and listen with earbuds)
- [ ] Captions checked
- [ ] Music/footage rights are clear
- [ ] Altered or synthetic realistic content disclosed in the upload settings, if any
- [ ] Not-made-for-kids set correctly
{ai}
## 48 hours after publishing
Open YouTube Studio > Content > this video > Analytics. Write down the click-through rate and average percentage viewed. Under 2% CTR: change the thumbnail and title. Big drop in the first 30 seconds: shorten the hook. Then add the numbers to the tracker.
"""
    f = CH / a.channel / "scripts" / f"{slugify(title)}.md"
    write(f, text)
    print(f"Script written: {f}")
    if idea:
        rows = read_ideas(a.channel)
        for r in rows:
            if r["title"].lower() == title.lower():
                r["status"] = "scripted"
        write_ideas(a.channel, rows)


# ------------------------------------------------------------------ track

def bar(p: float) -> str:
    p = max(0.0, min(1.0, p))
    n = round(p * 20)
    return "[" + "#" * n + "-" * (20 - n) + f"] {p * 100:.0f}%"


def cmd_track(a) -> None:
    cfg = load_channel(a.channel)
    f = CH / a.channel / "tracker.csv"
    today = dt.date.today().isoformat()
    row = [today, a.subs, a.watch_hours, a.shorts_views, a.views or "", a.uploads or "", a.ctr or "", a.avd or ""]
    with f.open("a", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerow(row)
    with f.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    lf, sh = K.YPP["long_form"], K.YPP["shorts"]
    cur = rows[-1]
    subs, hrs, sv = float(cur["subs"]), float(cur["watch_hours_12m"]), float(cur["shorts_views_90d"])
    prev = next((r for r in reversed(rows[:-1]) if (dt.date.fromisoformat(cur["date"]) - dt.date.fromisoformat(r["date"])).days >= 6), None)
    eta = []
    if prev:
        wk = max(1.0, (dt.date.fromisoformat(cur["date"]) - dt.date.fromisoformat(prev["date"])).days / 7)
        for label, now, before, goal in (("subscribers", subs, float(prev["subs"]), lf["subs"]), ("watch hours", hrs, float(prev["watch_hours_12m"]), lf["watch_hours"])):
            gain = (now - before) / wk
            if now >= goal:
                eta.append(f"- {label}: target reached.")
            elif gain > 0:
                eta.append(f"- {label}: gaining about {gain:,.0f} a week, so about **{math.ceil((goal - now) / gain)} weeks** to go if the pace holds (it rarely stays flat: use this as a rough guide).")
            else:
                eta.append(f"- {label}: not growing yet. That is normal early on: keep publishing and fix the weakest number below.")
    else:
        eta.append("- Two entries at least a week apart are needed to show your pace. Keep updating the tracker every week.")
    ctr = float(cur["ctr_pct"]) if cur["ctr_pct"] else None
    avd = float(cur["avg_pct_viewed"]) if cur["avg_pct_viewed"] else None
    actions = []
    if ctr is not None and ctr < 2:
        actions.append("Click-through is under 2%: the thumbnail and title are the problem. Redesign the thumbnail of your 3 newest videos (bigger shape, 3 words, more contrast) and rewrite the titles to promise one clear result.")
    elif ctr is not None and ctr < 4:
        actions.append("Click-through is ordinary (2-4%). Test a bolder thumbnail on your best-impression video and compare after a week.")
    if avd is not None and avd < 30:
        actions.append("People leave early (under 30% watched). Rewrite the first 30 seconds: say the result first, cut the intro, and change something on screen every 5-10 seconds.")
    elif avd is not None and avd < 45:
        actions.append("Retention is fair. Find the biggest drop in the retention graph of your best video and cut or tighten that part in the next one.")
    if hrs < lf["watch_hours"] * 0.1 and subs < lf["subs"] * 0.1:
        actions.append("You are early. The job now is volume of learning: publish your next 10 videos on schedule before judging the channel.")
    if subs < lf["subs"] * 0.5 and hrs >= lf["watch_hours"] * 0.5:
        actions.append("Watch hours are ahead of subscribers: add a spoken, specific ask ('subscribe if you want part 2 on X') and a pinned comment.")
    if subs >= lf["subs"] * 0.5 and hrs < lf["watch_hours"] * 0.5:
        actions.append("Subscribers are ahead of watch hours: make fewer, longer-lasting answer videos that people watch to the end.")
    actions = (actions or ["Keep the rhythm. Make more of your top 3 videos from new angles (use the ideas tool with --angle)."])[:3]
    uploads = f"{cur['uploads']} uploads so far. " if cur["uploads"] else ""
    md = f"""# Progress: {cfg['name']}

Updated {today}. {uploads}Numbers from YouTube Studio. Partner Program numbers checked {K.CHECKED} at {K.YPP['sources'][0]}

## Distance to the Partner Program (long-form route)
- Subscribers: {subs:,.0f} of {lf['subs']:,}  {bar(subs / lf['subs'])}
- Public watch hours (last 12 months): {hrs:,.0f} of {lf['watch_hours']:,}  {bar(hrs / lf['watch_hours'])}
- Shorts route (bonus): {sv:,.0f} Shorts views in 90 days of {sh['shorts_views']:,}  {bar(sv / sh['shorts_views'])}

Also needed: no active strikes, 2-Step Verification, advanced features, an AdSense account, and a country where the program runs. Reaching the numbers does not guarantee approval.

## Your pace
{chr(10).join(eta)}

## Do these next
{chr(10).join(f'{i}. {x}' for i, x in enumerate(actions, 1))}

{'Do not wait for the Partner Program to earn: ' + {'ads': 'start one more income route now (a service, affiliate links, sponsors).', 'leads': 'count the leads that came from the channel this week.', 'affiliate': 'make sure every link is disclosed and tracked.', 'authority': 'ask your three most engaged viewers what they would pay to learn.'}[cfg['goal']]}
"""
    write(CH / a.channel / "PROGRESS.md", md)
    print(md)


# ------------------------------------------------------------------ check

BAIT = {"shocking", "unbelievable", "insane", "secret", "hack", "won't believe", "you won't", "destroyed", "gone wrong", "exposed", "scam"}


def cmd_check(a) -> None:
    title, kw = clean(a.title, 150), clean(a.keyword, 60).lower()
    desc, thumb = clean(a.description, 600), clean(a.thumb, 80)
    score, fixes, good = 100, [], []
    n = len(title)
    if n > 70:
        score -= 20; fixes.append(f"Title is {n} characters: it will be cut off. Aim for 60 or fewer.")
    elif n > 60:
        score -= 7; fixes.append(f"Title is {n} characters: fine, but the end may be cut on phones. Put the key words first.")
    elif n < 25:
        score -= 10; fixes.append("Title is very short. Add the result or the audience (who it is for).")
    else:
        good.append(f"Title length ({n}) is good.")
    if kw:
        pos = title.lower().find(kw)
        if pos < 0:
            score -= 20; fixes.append(f"The keyword '{kw}' is not in the title. People search with those words.")
        elif pos > 30:
            score -= 8; fixes.append("Move the keyword nearer the start of the title.")
        else:
            good.append("Keyword is in the first part of the title.")
    letters = [c for c in title if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.5:
        score -= 10; fixes.append("Too much CAPITAL LETTERS reads as shouting. Use normal case.")
    if title.count("!") > 1 or title.count("?") > 1:
        score -= 5; fixes.append("Use at most one ! or ?.")
    hit = [b for b in BAIT if b in title.lower()]
    if hit:
        score -= 8; fixes.append(f"Words like '{hit[0]}' make a promise the video must keep. If it does not, viewers leave and YouTube stops showing it.")
    if re.search(r"\d", title):
        good.append("A number in the title makes the payoff concrete.")
    else:
        fixes.append("Optional: a number or a time ('in 10 minutes', '5 mistakes') often lifts clicks.")
    if thumb:
        w = len(thumb.split())
        if w > 4:
            score -= 10; fixes.append(f"Thumbnail text is {w} words. Use 4 at most: it must be readable at stamp size.")
        elif title and thumb.lower() == title.lower():
            score -= 8; fixes.append("The thumbnail repeats the title. Let it add something: the result, a number or a feeling.")
        else:
            good.append("Thumbnail text is short enough to read on a phone.")
    if desc:
        first = desc[:150].lower()
        if kw and kw not in first:
            score -= 10; fixes.append("Put the keyword in the first 150 characters of the description (the part shown in search).")
        if "http" not in desc and "www" not in desc:
            fixes.append("Add your link in the first lines of the description if the video has a next step.")
        if len(desc) < 120:
            score -= 5; fixes.append("The description is thin. Add 2-3 sentences on what the video covers, then chapters.")
    else:
        fixes.append("No description given to check: write 2 keyword-rich sentences, your link, chapters and links used.")
    score = max(0, min(100, score))
    print(f"Packaging check: {score}/100")
    for g in good:
        print("  OK  " + g)
    for f in fixes:
        print("  FIX " + f)
    print("A good title is a promise you can keep. Test two versions, change one thing at a time and judge by click-through after a week.")


def cmd_niches(a) -> None:
    for k, v in K.NICHES.items():
        print(f"{k:26} {v['name']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--niche", required=True)
    p.add_argument("--topic", default="")
    p.add_argument("--faceless", default="yes")
    p.add_argument("--goal", default="leads")
    p.add_argument("--hours", default=6, type=int)
    p.add_argument("--name", default="")
    p.add_argument("--audience", default="")
    i = sub.add_parser("ideas")
    i.add_argument("--channel", required=True)
    i.add_argument("--count", default=10, type=int)
    i.add_argument("--angle", default="")
    s = sub.add_parser("script")
    s.add_argument("--channel", required=True)
    s.add_argument("--title", required=True)
    s.add_argument("--minutes", default=8, type=int)
    s.add_argument("--ai", action="store_true")
    t = sub.add_parser("track")
    t.add_argument("--channel", required=True)
    t.add_argument("--subs", required=True, type=int)
    t.add_argument("--watch-hours", dest="watch_hours", required=True, type=float)
    t.add_argument("--shorts-views", dest="shorts_views", default=0, type=int)
    t.add_argument("--views", default="")
    t.add_argument("--uploads", default="")
    t.add_argument("--ctr", default="")
    t.add_argument("--avd", default="")
    c = sub.add_parser("check")
    c.add_argument("--title", required=True)
    c.add_argument("--keyword", default="")
    c.add_argument("--description", default="")
    c.add_argument("--thumb", default="")
    sub.add_parser("niches")
    a = ap.parse_args()
    {"plan": cmd_plan, "ideas": cmd_ideas, "script": cmd_script, "track": cmd_track, "check": cmd_check, "niches": cmd_niches}[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
