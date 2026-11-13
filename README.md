# DSE Toolkit

Lead finders and website problem checks for DBI's DSE paths. It runs on **your own PC**, and you can start it from your phone through **DBI Citadel → HQ Tools**. Every result is a CSV list with:
- the business and how to reach it
- **what its website is missing** for your path
- **a ready first message** for you to send yourself

Nothing here sends, posts or pays. You do every send.

| Your path | What the toolkit does for you |
|---|---|
| **SMB Optimization** | Finds independent local businesses (22 types: dentists, HVAC, plumbers, salons, law offices and more) and checks whether they ask for Google reviews, show reviews, take bookings online, and offer text/chat. |
| **AI Voice Receptionist** | Same lead finder for phone-heavy service businesses. Checks after-hours answering, online booking and text/chat, and warns you if they already use an AI receptionist. |
| **CareBridge** | Finds home care agencies, assisted living, nursing homes and senior services. Checks their enquiry form and reply-time promise, then the **mystery-shop tracker** scores Hot/Warm/Cold by how fast they really answer. |
| **Digital Ministry Systems** | Checks your own parish or a warm-network church's website: online giving, event sign-up, newsletter, services online, Mass times. No cold lists, by design. |
| **Revenue Recovery Engine** | Checks an online shop you found in the Meta Ad Library: email tool installed, sign-up offer, SMS sign-up, product reviews. |
| **The Broadcast Engine** | Finds active business podcasts on Apple Podcasts. Shows missed episodes, irregular schedule, no video version, thin show notes, and the host's public email. |
| The Ascent, Authority Engine, Go-to-Market Engineering | Coming next: these paths prospect through LinkedIn and calls, which the toolkit won't scrape. |

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

## Daily use
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
