# DSE Toolkit

Lead finders and website problem checks for DBI's DSE paths. It runs on **your own PC**, and you can start it from your phone through **DBI Citadel → HQ Tools**. Every result is a CSV list with:
- the business and how to reach it
- **what its website is missing** for your path
- **a ready first message** for you to send yourself

Nothing here sends, posts or pays. You do every send.

| Your path | What the toolkit does for you |
|---|---|
| **SMB Optimization** | Finds independent local businesses (22 types: dentists, HVAC, plumbers, salons, law offices and more) and checks whether they ask for Google reviews, show reviews, take bookings online, and offer text/chat. |
| **AI Automation** | Same lead finder, plus a check for back-office work still done by hand: hiring for admin roles, paper or PDF intake forms, no online scheduling, enquiries by plain email, no FAQ, no chat, no online payment, no email follow-up. It also warns you when a business already shows automation tools. Each gap is a workflow you can build in n8n. |
| **AI Voice Receptionist** | Same lead finder for phone-heavy service businesses. Checks after-hours answering, online booking and text/chat, and warns you if they already use an AI receptionist. |
| **CareBridge** | Finds home care agencies, assisted living, nursing homes and senior services. Checks their enquiry form and reply-time promise, then the **mystery-shop tracker** scores Hot/Warm/Cold by how fast they really answer. |
| **Digital Ministry Systems** | Checks your own parish or a warm-network church's website: online giving, event sign-up, newsletter, services online, Mass times. No cold lists, by design. |
| **Revenue Recovery Engine** | Checks an online shop you found in the Meta Ad Library: email tool installed, sign-up offer, SMS sign-up, product reviews. |
| **The Broadcast Engine** | Finds active business podcasts on Apple Podcasts. Shows missed episodes, irregular schedule, no video version, thin show notes, and the host's public email. |
| **The Ascent** | You scout companies that sell high-ticket offers by hand (search, YouTube, people who already close for them) and paste their websites. The check looks for a price of $3,000+, an application page, closers being hired and income-promise red flags, then drafts your commission-only pitch. **Score a sales call** (HQ Tools) rates each call in eight areas, names your two weakest with a 10-minute drill, and tracks show rate, close rate, cash per call and your score trend. |
| **Authority Engine** | You look at experts by hand and paste their headline, audience, last post dates and a few posts into a CSV (`name, profile_url, headline, connections, post_dates, post_1, post_2`). The audit scores who posts little and finds what to lead with: the silence, announcement-style openers, walls of text, no question or ask, talking about "we" instead of "you". Nothing is read from LinkedIn. |
| **Go-to-Market Engineering** | You export a list from your **own** Clay, Apollo or HubSpot account and save the CSV in `engines/<engine>/imports/`. Columns are matched by meaning. Each account is scored (sales or growth lead, funding in the last 12 months, 10-500 people), its website is read for GTM signals (hiring SDR, AE or RevOps, a CRM, no instant demo path) and the best are drafted. |

## Build and grow tools (for every path)
| Tool (in HQ Tools) | What it does |
|---|---|
| **App Builder** (`python builder/build.py new ...`) | Builds a real, working **website, web app, phone app (iPhone + Android), desktop app or TV app** from a starting point (landing page, dashboard, store, booking). You get the project, a README with the exact commands to run and publish it, a BUILD-BRIEF of what to build next, and `AGENTS.md` so an AI coding agent can carry on safely. Needs Node.js LTS (nodejs.org) except for the plain website. Tick "Install and test the build" to prove it builds. Results go in `builds/`. |
| **YouTube Launchpad** (`python youtube/launch.py plan ...`) | Plans a YouTube channel from zero, faceless or on camera: niche and promise, setup checklist, the current Partner Program (monetisation) numbers with their source and date, a faceless-safe policy guide, a 13-week roadmap matched to your hours, and 30 video ideas. Then `ideas` (more ideas), `script` (a ready-to-record script plan, optional Ollama first draft), `track` (weekly numbers, distance to monetisation, what to fix next) and `check` (title and thumbnail check). Results go in `youtube/channels/<name>/`. It teaches the method and the honest odds and cannot promise income. |

## Follow-ups and results for your engines
Once you send from the **Send Desk** (More, or the Send Desk tab) and tap **Sent** on each message, your PC keeps the log and does the rest.

| Tool (HQ Tools, My engines) | What it does |
|---|---|
| **Plan follow-ups** (`python dse.py followups <engine>`) | Finds everyone you messaged who has not answered, drafts touch 2 and touch 3 and saves them as a list in the Send Desk. Email and Instagram: 3 and 7 days after the first message. Facebook: 4 and 9. Website form: 5 and 12. Sundays skipped. Never a second Instagram DM: a public comment, then a note by email or form. It stops when they reply, book, are lost or you skip. Only rows you marked **Sent** count; it lists any you forgot to mark. |
| **Results** (`python dse.py outcomes <engine>`) | Sent, replies, calls booked, clients won and the monthly value, by channel, by the gap you led with, by wording and by touch. It only calls a difference when both sides have **30 or more sends in the same channel**, and says "too early to call" otherwise. |

Your log is `engines/<engine>/data/log.csv`. You can also mark a row from the keyboard: `python dse.py log <engine> 2026-11-16 3 sent`.
Test everything with `python tests/test_member_desk.py`.

---

## Where to type the commands
Every command below goes into **PowerShell opened inside the `dse-toolkit` folder**:
1. Open File Explorer and go into the `dse-toolkit` folder.
2. Click the address bar at the top, type `powershell` and press **Enter**. A window opens, already in that folder.
3. Paste a command there (right-click pastes) and press **Enter**.

## Install (once, about 15 minutes)
1. Install **Python 3.11 or newer** from python.org. During setup, **tick "Add python.exe to PATH"**.
2. Install **Git** from git-scm.com, keeping all the default options.
3. **Microsoft Edge** is already on Windows. The website checks open pages in it, hidden.
4. Only if your path needs them: **ffmpeg** (`winget install ffmpeg`), for video and reels; **Node.js LTS** from nodejs.org, then **n8n** (`npm install -g n8n`), for workflow tools.
5. Get the toolkit and its Python packages (HQ Tools → Connect a PC has these lines with Copy buttons):
   ```bash
   cd $HOME/Documents; git clone https://github.com/Butmmo/dse-toolkit dse-toolkit
   ```
   ```bash
   cd dse-toolkit
   ```
   ```bash
   pip install -r requirements.txt
   ```

## One-time: business data (SMB, AI Voice, CareBridge)
The lead finder uses **Foursquare's free open business data**. It doesn't scrape Google Maps.
1. Make a free account at huggingface.co.
2. Open huggingface.co/datasets/foursquare/fsq-os-places and accept the terms.
3. In your account settings, make a **Read** access token.
4. Save the token on your PC. Run this once in PowerShell, with your own token, then close and reopen PowerShell. Never share the token or paste it into a chat.
   ```bash
   setx HF_TOKEN "hf_your_token_here"
   ```
5. Download the business types you sell to. Each takes a few minutes, and you should repeat it monthly.
   ```bash
   python dse.py build dentist,plumber
   ```
   `python dse.py kinds` lists all the types for each path.

## Connect it to DBI Citadel (so you can run it from your phone)
1. In Citadel, open **More → HQ Tools → Connect a PC**. The panel shows each command with a **Copy** button.
2. Run its `setup` line here. It prints your **PC code**.
3. Paste the code into Citadel, name your PC and press **Connect**.
4. Check the connection. It should say "Connected":
   ```bash
   python bridge/runner.py check
   ```
5. Make it start by itself with Windows:
   ```bash
   powershell -ExecutionPolicy Bypass -File bridge/install.ps1
   ```

Keep the PC switched on and online while jobs run. Jobs you start while it's off wait until it's back.

## Your engines (the main way to use the toolkit)
An **engine** is one outreach business of yours: for example "Tampa dentists" on SMB, or "Business podcasts" on Broadcast. It records:
- who you target and where
- your brand and name
- which channels to use, and how many a day
- your first-message wording

1. In Citadel, open **HQ Tools → My engines → New engine**. Pick your path, and its template fills most of it in. Choose cities (or topics, or websites) and save.
2. Your PC picks it up within a minute, as `engines/<name>/engine.json`. You never edit that file: change the engine in Citadel.
3. Press **Build next list** in Citadel, or run this here:
   ```bash
   python dse.py daily <engine>
   ```
   It finds new leads (or checks your seed websites), checks what each one is missing, and skips anyone already on your lists. It then picks each lead's channel in your order, within your daily caps, drafts your message, and writes `engines/<engine>/send-lists/<date>.csv`.
4. Send from the **Send Desk** on your phone. Tap Sent, Got a reply and so on. Follow-ups and outcomes per engine come in the next update.

`python dse.py engines` lists your engines and how many lists each has.

## Daily use (without an engine)
From HQ Tools on your phone, or here in PowerShell:

**SMB / AI Voice / CareBridge:** find leads and check them in one go.
```bash
python dse.py list smb dentist "Tampa FL; Orlando FL"
```

**Ministry / Revenue Recovery:** check one website.
```bash
python dse.py check ministry https://yourparish.org
```

**Broadcast Engine:** find podcasts.
```bash
python dse.py podcasts "marketing; startup; sales"
```

**CareBridge:** start a mystery-shop tracker from a home-care list, then score it after filling in the times.
```bash
python dse.py mystery new my-lists/<your home-care list>.csv
```
```bash
python dse.py mystery score my-lists/<the tracker>.csv
```

Then, in HQ Tools:
1. Open the finished job.
2. **Preview** the list and spot-check a few rows.
3. Press **Add to my CRM**. The leads land in **BPS → CRM** as "Not Contacted", with:
   - the channel, where to message and the drafted first message, with a **Copy first message** button
   - the gaps found
   - your path's own details (for example a podcast's episode gap, or an agency's mystery-shop reply time)

## The rules this toolkit follows (DSE Constitution)
- **No free work for cold prospects.** The openers offer to *send what you found*, never to do the job free.
- **Read the gap before you send.** The checker leans towards "has it", so a gap it reports is real, but open the site and confirm. "Check by hand" means the site blocked the script: look yourself.
- **SMB is manual-first.** Scout your first leads by hand, as the playbook says, before using the finder.
- **Ministry is warm-network only.** Check your own parish and churches you're introduced to.
- **No scraping** of LinkedIn, Instagram, Facebook or Google Maps. It breaks their terms and gets accounts banned.

Data: Foursquare Open Source Places (Apache 2.0), Apple Podcasts Search API and public podcast RSS feeds, and OpenStreetMap Nominatim for city locations.
