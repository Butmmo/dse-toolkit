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
| **Vet an offer** (The Ascent, `python dse.py vet ...`) | Before you give a commission-only offer your time: answer 21 questions (Yes, No, Not asked yet) built from the FTC's job-scam advice and practitioner guidance for commission contracts. Any dealbreaker (a fee to start, no written terms, earnings promises, money handling, a company you cannot verify) is **WALK AWAY**; two serious flags are Red; one is Amber; too many unanswered is Unchecked. You get the reasons, a ready message with the questions to put to them in writing, what to get in the contract, and what one sale and a target month would need from you (using your own close rate once you have 10 logged calls). Every offer is saved to your tracker (`python dse.py offers <engine>`). |
| **Authority Engine** | You look at experts by hand and paste their headline, audience, last post dates and a few posts into a CSV (`name, profile_url, headline, connections, post_dates, post_1, post_2`). The audit scores who posts little and finds what to lead with: the silence, announcement-style openers, walls of text, no question or ask, talking about "we" instead of "you". Nothing is read from LinkedIn. |
| **Go-to-Market Engineering** | You export a list from your **own** Clay, Apollo or HubSpot account and save the CSV in `engines/<engine>/imports/`. Columns are matched by meaning. Each account is scored (sales or growth lead, funding in the last 12 months, 10-500 people), its website is read for GTM signals (hiring SDR, AE or RevOps, a CRM, no instant demo path) and the best are drafted. |

## Build and grow tools (for every path)
| Tool (in HQ Tools) | What it does |
|---|---|
| **App Builder** (`python builder/build.py new ...`) | Builds a real, working **website, web app, phone app (iPhone + Android), desktop app or TV app** from a starting point (landing page, dashboard, store, booking). You get the project, a README with the exact commands to run and publish it, a BUILD-BRIEF of what to build next, and `AGENTS.md` so an AI coding agent can carry on safely. Needs Node.js LTS (nodejs.org) except for the plain website. Tick "Install and test the build" to prove it builds. Results go in `builds/`. |
| **YouTube Launchpad** (`python youtube/launch.py plan ...`) | Plans a YouTube channel from zero, faceless or on camera: niche and promise, setup checklist, the current Partner Program (monetisation) numbers with their source and date, a faceless-safe policy guide, a 13-week roadmap matched to your hours, and 30 video ideas. Then `ideas` (more ideas), `script` (a ready-to-record script plan, optional Ollama first draft), `track` (weekly numbers, distance to monetisation, what to fix next) and `check` (title and thumbnail check). Results go in `youtube/channels/<name>/`. It teaches the method and the honest odds and cannot promise income. |
| **Dev workspace** (`python dse.py dev --help`) | A sandboxed place to **create, read, edit, run and ship code** in 14 starters (JavaScript, TypeScript, Python, Java, Kotlin, C#, C, C++, Dart, Flutter, Go, Rust, PowerShell), with GitHub (clone, read issues, commit, push, pull request), named build/test/lint tasks for each ecosystem, and an AI engineer that edits code on its own branch. See "Dev workspace" below. |

## Dev workspace: what it can do and what it will never do

Everything happens in `workspaces/<name>/` on this PC. From Citadel (HQ Tools, group **Dev**) you can start a project, clone a repository, read and search files, change a line, run install/build/test/lint, see the diff, commit, push, open a pull request and ask the AI engineer for a change. The same commands work at the PC: `python dse.py dev languages`, `dev new "My App" --lang python-cli`, `dev run my-app test`, `dev agent my-app --instruction "..." --verify test`.

**Safety is enforced in code, and the switches live only on this PC** (`dev/dev.config.json`, never in Git, never in Citadel):
- Paths stay inside the workspace; `..`, absolute paths, links out and `.git` are refused. Files that hold secrets (`.env`, keys, tokens) cannot be read, written or committed, so they never reach a job log or an AI provider.
- Commands run as a fixed list of programs (no shell), with a time limit, capped output, and your tokens removed from their environment. Output is scrubbed for token patterns.
- **Pushing is off** until you run `python dse.py dev setup --github-user YOURNAME`. It then pushes only to repositories owned by an account you listed, never forces, and from `main` it pushes a new `dev/...` branch so you review a pull request first.
- **PowerShell is off** until you run `python dse.py dev config --set allow_shell=true`. A deny list blocks the worst commands, but it is not a sandbox: turn it on only if you accept that.
- The AI engineer works through the same sandboxed tools, needs a clean workspace, works on a fresh `dev/agent-...` branch, and never pushes. Brain: Claude when `ANTHROPIC_API_KEY` is set and `pip install anthropic` is done; otherwise your local Ollama model (use gemma3:4b or bigger).
- `npm install` runs with `--ignore-scripts` unless you set `npm_scripts=true`.

A missing toolchain is not an error to decode: `dev run` names the program and the exact `winget install` command. Tested here with real runs: Python, JavaScript (Node) and TypeScript. The other languages' starters are written and checked for structure, but their toolchains (Maven + JDK, Gradle, .NET, CMake + a C compiler, Dart, Flutter, Go, Rust) were not all installed when this was built, so run `dev run <workspace> test` once after installing each.

## Cash Desk: am I on track this month?

`python dse.py cash <engine|all> [--month 2026-11] [--target 3000]` (in HQ Tools: "Cash Desk"). It compares the money you **actually received** with your monthly target, projects the month from your pace so far, lays out the steps (messages sent, replies, calls booked, calls shown, sales) and works out what the gap would take **using your own rates**. It says plainly when there is too little data to trust a rate (under 30 messages sent or 5 shown calls), instead of inventing a number.

Where the numbers come from, all in `engines/<engine>/data/`: `cash.csv` (money you log with `python dse.py cashin <engine> --amount 450 --kind commission --note "Acme sale"`; a refund is logged with `--kind refund`), `calls.csv` (from `callscore`; sale value x your commission % is shown as an **estimate** until you log the money), `log.csv` (Send Desk taps; out-of-office replies are not counted as replies) and `cash.json` (your target). `python dse.py cashlog <engine>` lists what you logged. The report is also saved as `engines/<engine>/cash-desk.md`.

## Call Desk: be ready for the call, and know what to do the minute it ends

`python dse.py call prep <engine> --source 2026-11-09 --row 7` (HQ Tools, "Call Desk") builds `engines/<engine>/calls/<date>-<lead>/prep.md` and `notes.md` from your own records only: your first message, their reply in their exact words, what your website check or `enrich` found (each fact names where it came from), three facts to open with, a question plan under the same five headings as your call scorecard (Situation, Problem, Cost, Result wanted, Next step) with their own gap woven in, your up-front contract script, and what must be in hand before you speak (price, what is and is NOT included, the payment link). **What is not known is listed as not known and where to look: nothing about the lead is invented.**

`python dse.py call after <engine> --source LIST --row N --outcome follow_up|sold|no_sale|no_show --problem "their words" --cost-month 4000 --price 1500 --agreed "what we agreed"` writes `after.md`: the recap to send within 10 minutes (their problem, their number, what you agreed, signed in your name), the scorecard command, and for a follow-up the `proposal` command already filled in. A sold or lost call is written into the send log (with the value) so your results stay true; `--stop` adds them to the do-not-contact list. The Weekly Review flags a call booked in the last week with no prep sheet and gives the exact prep command. Nothing is sent.

## Make it yours: your own business type, your own website check, your own words

The built-in lists and checks are written for one path each. Every one of them now has a way out:
- **Your own business type:** in the lead tools (`python dse.py find "wedding photographers" "Tampa FL"`, or HQ Tools, Business type, "Other: type my own") type any business you sell to. It is found among Foursquare's business categories and saved (`data/custom-kinds.json`); if several categories fit, you are shown them and asked to type the exact one (nothing is guessed). The first time it also builds the data (a few minutes, same free `HF_TOKEN`). `python dse.py categories photo` browses the names.
- **Your own website check:** `python dse.py mypack "Wedding photographers" --sells "fast galleries and a booking page" --checks "online booking, book now => there is no way to book a session online"`. Each check is the words that count as the site having it, then `=>`, then what you would say when none appear. It appears next to the built-in packs in every tool that asks for one (`data/custom-packs/`), and your sentence becomes the gap in the opener. Nothing is invented.
- **Your own words:** `--words "wedding, bride"` (the business's website must use one of them; replaces the built-in words) and `--skip "studio"` (leave out businesses whose name has them) on `find` and `list`.
- **Other values:** a currency of your own (any 3-letter code such as NGN or CAD) in proposals, Books, Cut Desk and exchange rates; a podcast genre of your own. In HQ Tools and in the app these are one box you type in, with the usual answers offered as you type (no "Other" step, and it works on a runner that has not been restarted). What you type is understood the way you would say it: "Interior Designers" is the built-in interior design type; a word that fits several Foursquare categories uses all of them (up to 8; a too-broad word asks for one more word).

## My tools and Tool Studio: make your own tools

**My tools (no code, everyone).** In Citadel, HQ Tools > My tools: name a tool, add up to 8 steps, and for each value the step needs choose *Ask me each time*, *A fixed value*, *The file the step before made* or *Leave empty*. Your PC picks it up within a minute (`bridge/mytools_sync.py`), checks it with its own rules and offers it in HQ Tools as `my.<name>` (group "My tools"), where the planner and DBI-AI can find it. At the PC: `python dse.py mytool list | check [name] | save recipe.json [--shared]`, and `mytool run my.<name> --in-<input> value` is what the runner does. A recipe is **data**: it can only call tools this PC already has, through the same value checks as pressing them by hand; never a Dev, Setup or Studio tool or another recipe; at most 8 steps; it never sends, posts or pays. The super admin can *Publish to everyone*: the recipe (data) goes to `shared_tools` and every PC checks it before offering it as a tool "from DBI", with its steps listed in the help. Needs the one-time database update `20261120090000_my_tools.sql` and a runner restart.

**Tool Studio (administrator).** Real Python tools, written with an AI, on your own PC. Off until you run `python dse.py studio config --enable` (Citadel cannot turn it on). Then: `studio draft <name> "what it does"` (Claude with your own key, else your Ollama model; refused drafts are sent back with the reasons), `studio show <name>` (read the code), `studio test <name>` (one run on its sample values; a pass prints an approval code), `studio enable <name> --approve <code>` (the code is the start of the hash of the exact code you read), `studio revise`, `studio disable`, `studio list`. In Citadel the same steps are on the Tool Studio page (super admin only), as ordinary jobs. **The safety is in code:** a static guard (`dse/studio_guard.py`: only json, csv, re, math, datetime and a few other modules; no open, eval, getattr, underscore attributes; no format-string tricks), a sandbox launcher (`dse/studio_run.py`: short builtin list, import hook, separate process, your keys removed from its environment, time limit, capped output), and `dse_sdk` as the only door to files and the web (reads only engines, my-lists, data and its own work folder, never a file that looks like a secret; writes only csv, json, txt, md into its work folder; web only on the public internet, never LinkedIn, Instagram, Facebook, X, TikTok, Reddit or Google Maps, 30 requests a run). A tool runs only after a passing test AND your approval of its exact code: change one character and it switches itself off. **Code never travels through Citadel.** `studio publish <name>` copies an approved tool to `extras/<name>/` for you to review and commit; students get it with the next toolkit update as `extra.<name>`, under the same guard (it is refused if its files no longer match the hash recorded at publish). This is a guard against mistakes and AI-written code, not a wall against a hostile author: that is why you read the code before approving it.

## Schedules: tools that run by themselves

In Citadel, HQ Tools > Schedules: pick a tool (or one of your My tools), fill its form once, choose every day, every weekday, every week (a day) or every month (a day from 1 to 28) and a time. `bridge/schedule_sync.py` (every minute while the runner is on) pulls your schedules and, when one is due, queues an **ordinary job** in your account: same Jobs list, log, files and Cancel button as pressing Run, so scheduling adds no new power. Rules, all in `dse/schedules.py` and tested: times are this PC's local time; it runs only while the PC is on; a new schedule never runs for a moment that already passed; each moment runs at most once; a run missed because the PC was off still happens if the PC is back within 12 hours, later than that it is skipped (and says so), never stacked; if the previous run is still going the new one is skipped; after 3 failed runs in a row the schedule pauses itself and tells you (Resume in the app clears it); Dev, Setup and Studio tools and tools that need you to pick a file cannot be scheduled (put the tool in a My tools recipe and schedule the recipe); at most 20 schedules; nothing here sends, posts or pays. "Run now" queues the tool straight away without touching the schedule. Needs the one-time database update `20261121090000_schedules.sql` and a runner restart. `python bridge/schedule_sync.py --dry` shows what it would queue.

## CRM sync: your engines' leads, replies and calls in your BPS CRM

`python dse.py crm preview <engine>` shows exactly what your BPS CRM would get; `crm on <engine>` turns it on (it is OFF until you do); `crm sync` sends now, and the runner does it by itself every 5 minutes for engines that are on (`bridge/crm_sync.py`). HQ Tools: "CRM sync"; it is also on the BPS Client CRM page and the Send Desk.

One CRM lead per business (a business on several lists, or with a follow-up, is still one lead), from your own files only: name, city, website, email, phone, the gap the check found, your opener, where you reached out, and "Source: My PC: <engine>". The stage comes from the Send Desk log: Sent = Contacted; interested, a price question, a question or a referral = Replied Positively; not interested, already have someone, not now or unsubscribe = Replied Negatively; Call booked; Won = Closed; Lost = Replied Negatively; a saved proposal = Proposal Sent. An out-of-office or unclear reply is never a stage: it stays Contacted and their words are in the notes.

The CRM stays yours first: a stage only moves FORWARD (what you moved by hand is never pulled back; a lost call may close a lead that is not yet a proposal or a client), an empty field is filled but a field you wrote is never overwritten, your own notes are never touched (the PC keeps one block at the end, under a marker line), and a lead you added yourself is matched by website (else name and city) and adopted, not duplicated. **It works both ways.** A stage you change by hand in the CRM is recorded in the engine's log on the next sync (Contacted = a Sent tap; Replied = a Replied tap with no reply text, never an invented one; Call Booked = a Booked tap; Closed or Retainer = a Won tap), so the Daily Brief and the follow-ups stop asking about what you already handled. It never undoes anything (a lead moved back is ignored) and a change is acknowledged only once recorded. Needs the one-time database update `20261119100000_crm_sync.sql` (run it again if you ran an earlier copy: it is safe to re-run and now includes the two-way part) and a runner restart.

## System check: what is on, what is missing, and the fix

`python dse.py doctor` (HQ Tools, "System check"; also on the Dashboard) answers "why is nothing showing?" in plain words, and changes nothing. It checks: **the runner** (is it running, did it start AFTER the toolkit files last changed, are all the background helpers started, are the newest tools there); **your Citadel database** (it asks, for each update this toolkit depends on, whether the function exists, using a call the database refuses before it can write; a missing one names the exact SQL file to run in Supabase); **the background helpers** (the Send Desk, engines, goals, DFY, Daily Brief, CRM and Voices: when each last ran and what its last message said); and **this PC** (engines, your brief, the Voices library, the business-data token, Python packages, Ollama). Each line is OK, NEEDS A FIX (with what to do), OPTIONAL, or "could not check from here": nothing unknown is called fine. `--offline` skips the database questions. The runner now writes `data/runner-status.json` and `data/helpers.json` for this (restart it once to start the reporting).


**The Setup checklist on the Dashboard.** `bridge/setup_sync.py` (every 5 minutes while the runner is on, or the tool "Setup checklist: check now") runs this same check and sends its lines to your Citadel account, where the Dashboard shows them as a checklist: a progress bar, "Do this next", what needs a fix with the fix, and optional and working lines tucked away. The app itself adds three lines it knows without your PC (HQ Tools open, a PC connected, the PC on), so it helps before anything is installed. Only the check's own lines are sent (area, name, state, short detail, fix): no files, data or keys, and anything key-like is hidden before it leaves the PC. Progress counts OK against NEEDS A FIX only; optional and "could not check" lines never hold it back and are never called done. Needs the one-time database update `20261122090000_setup_checklist.sql` and a runner restart; `python bridge/setup_sync.py --dry` shows what would be sent.
## Daily Brief: what to do first today

`python dse.py brief [--top 3]` (HQ Tools, "Daily Brief") reads what the Weekly Review reads, for ALL your engines, keeps the first few things by the review's fixed rule (closest to money first) and attaches to each the tool that does it with the values it already knows: the engine, the booked call's list and row, the list file to check before sending. Each line says where its number came from; a move with no tool points to the Send Desk. Nothing is guessed, sent or changed. It is saved as `data/brief.md` and `data/brief.json`.

The runner builds it by itself every 15 minutes (`bridge/brief_sync.py`, a background helper) and sends it to your own Citadel account, where the Dashboard shows "Your brief for today" with a button for each thing that opens the right tool, already filled in. It needs the one-time database update `20261119090000_hq_brief.sql` and a restart of the runner.

**Brief notifications.** When something that needs you is NEW in the brief, your phone gets one quiet push (it also lands in the notification bell). The rules are fixed (`dse/briefnotify.py`): only a reply waiting, a booked call to prepare for, overdue invoices or student cuts, late deliverables or a student who needs a check-in (follow-ups due, messages to send, offers and goals never buzz); only what is new since you were last told (2 replies waiting becomes 3: told again; handled and back: told again); the first brief is a baseline so turning it on never floods you; at most one push every 45 minutes with several things in it; quiet hours 21:00 to 07:00 on this PC (what arrived overnight is announced once afterwards, if still waiting). Change the hours or turn it off in `data/brief-notify.json` (`{"enabled": true, "quiet_start": 21, "quiet_end": 7, "min_minutes": 45}`), or switch "Brief notifications" off in your Citadel profile. Needs the one-time database update `20261119120000_brief_notify.sql` and a runner restart.

## Voices: the people worth learning from, with their real words and sources

One library, not a tool per person: `voices/roster.json` holds **10 figures for each of five areas** (wisdom and philosophy, human empowerment and psychology, structure and systems, sales and persuasion, financial development) and **7 for each of the 9 paths**. The roster is my proposal and a plain file you can edit (swap a name, fix a source); `python dse.py voices check` confirms the counts still hold. Entries marked `check` are ones I was not sure of: confirm them before relying on them.

**One step to make it work: `python dse.py voices setup`** (HQ Tools, "Voices: set up the library"). It checks every source, repairs what it can (the right Project Gutenberg book found through gutenberg.org's own search and checked against the book's own author and language line; more places to look for a feed; YouTube channels read the way a browser does; book titles simplified), downloads what is lawful to keep, and reads what the living have published. It can be run again and again (it skips what is up to date, retries failures after 3 days, and stops cleanly when its time is up). The runner also does this by itself every 6 hours (`bridge/voices_sync.py`). `voices verify [figure]` checks each source live and records the result. **Nothing is fetched or used until its source is verified.** `voices fetch <figure>` then downloads and indexes only what is lawful to copy: public-domain books from Project Gutenberg (cited by book and section) and sourced quotations from Wikiquote (credited, CC BY-SA; the misattributed and disputed sections are skipped). Books still in copyright are listed by title and year only, and `voices note <figure> --text ... --source ...` lets you add your own notes, marked as yours (a note without a source is refused).

**The fix-it button: `python dse.py voices repair [any | <figure> | <figure>:<number>]`** (HQ Tools, "Voices: repair a failing source"; the list shows each failing source and why). For a source that still fails after setup it tries what a person would try: a different Project Gutenberg book by the same author (confirmed from the book's own header and said plainly in the report), the right Wikiquote page found by searching the figure's name, another feed address on the site, and dropping book titles Open Library cannot confirm. It checks the result, downloads what became lawful to keep and reports FIXED or STILL FAILING with the reason. Repairs are kept in `data/voices/fixes.json`, never in `voices/roster.json` (delete that file to go back to the shipped roster). The System check lists a failing source as a fix that names this button, and as optional once a repair has been tried.

`voices ask "how do I stay calm under pressure" [--figure marcus-aurelius] [--stratum wisdom] [--path ascent]` returns the best matching passages by plain keyword ranking, each with who and where. **No AI model writes, paraphrases or imitates anyone**, and every answer says so. `voices today [--stratum]` gives one passage per day. `voices show <figure>` lists their sources and what is new.

**Mentor answers in DBI-AI.** DBI-AI can show real passages from this library beside (or instead of) its answer. Choose "Mentors" under the chat box: **Auto** adds passages only when you ask for a mentor, a quote or wisdom, or name someone ("what did Seneca say about anger?"; "give me a quote about courage"); **Mentor passages only** answers from the library with no AI model at all; **Off**. Matching is by words, not by meaning (with a small list of everyday ideas mapped to the words the old texts used: procrastinating finds idleness and habit), so an ordinary question is never padded with whatever shares a word, and when nothing fits it says so. The CLI is the same: `python chat/chat.py --mentors only "I keep procrastinating on my outreach"`. A named figure searches only that figure.

**Living figures:** `voices update [figure]` reads only their own published feeds (blog or newsletter RSS, official YouTube channel feed, podcast feed) and lists what is new since last time: title, date, link and a short description. You follow the link to read or watch. **X, LinkedIn, Facebook, Reddit and Instagram are never fetched** (their terms forbid it, and so does our rule): the roster can hold a profile link and that is all. HQ Tools has the same as "Voices" tools (ask, today, roster, one figure, check sources, fetch, what is new, add your note).

## Referral and Testimonial Desk: ask at the right moment, use only what is approved and true

`python dse.py proof due <engine>` (HQ Tools, group "Proof Desk") shows who is at a good moment to ask: a client whose work is **delivered**, a DFY student at **6** and at **12** qualified months, plus one gentle follow-up after 7 days, closing an ask after 21, and referrals not yet thanked. `proof ask <engine> --who Dana --source client:acme-dental` drafts a kind, optional request in your name (three easy questions for a testimonial, a referral ask, how they would like their name shown, whether numbers may be used; "no pressure"). A DFY student's request says it is separate from their DFY and that a no changes nothing. You send every message yourself and record it with `proof mark`.

**Their words are kept exactly, and a quote is usable only with recorded consent.** `proof quote <engine> --who "Dana Cole" --role "Owner, Acme Dental" --text "their exact words" --consent yes --consent-how "replied yes on WhatsApp, 15 Nov" --name full|first|anonymous --company yes|no --numbers yes|no --scope proposals,website` records what they agreed to: that you may use the text, how their name is shown, whether the company and numbers may be shown, and where it may appear. Without consent the quote is stored but cannot be used anywhere, and you get the exact message to send them showing how it would appear. An excerpt is allowed only if it is a verbatim part of their words (`proof excerpt`). A quote with numbers in it is not usable unless they allowed numbers.

**A number must be true.** `proof claim <engine> Q-001 --number "3 new bookings a week" --source words` verifies a number against their own words, or against your records (`--source record:client/acme-dental:cost_month`, or `record:student/ada-obi:qualified_months`). An unverified number is never used. `proof quotes <engine> --scope proposals` lists only the approved, consented, not-withdrawn quotes word for word with the attribution they chose, and the reason for every quote it leaves out. `proposal ... --quotes` adds a "What clients say" section from exactly those. **Withdrawing** (`proof withdraw`) takes effect at once and Outreach Preflight blocks any message that still contains the quote's words, even with different punctuation. Referrals: `proof refer <engine> --from Dana --referred "Bella Dental"`, `proof referral ... --status won --value 1500`, `proof thanked ...`. The Weekly Review adds a move for asks and thank-yous. Data: `engines/<engine>/data/proof.json`.

## Books Desk: the monthly pack for your accountant

`python dse.py books <engine> [--month 2026-11] [--base USD]` (HQ Tools, "Books Desk") writes `engines/<engine>/books/<month>/`: `summary.md` (received in the month on a cash basis, invoiced on an accrual basis, still owed with ageing, written off, the exchange rates used, the year to date, a list of things to check, and the questions your accountant should decide) and CSV files your accountant can open: `receipts.csv`, `invoices.csv`, `receivables.csv`, `writeoffs.csv`. Every figure traces to a line in your own files. It does **not** work out tax or decide cash or accrual, which rate to use, how fees are treated, or whether anything is VAT, sales tax or withholding: it prepares clean records and lists those questions. The default month is the last complete one.

**Currencies are now kept honestly.** Every payment records its currency (the Client Desk, Cut Desk and Statement Matcher pass it automatically; `cashin` takes it too). An older cash file still works: payments logged before currencies were recorded count as dollars and are flagged. A payment in another currency counts toward the Cash Desk's dollar target, your goals and the books **only at an exchange rate you entered**: `python dse.py fx add <engine> --from GBP --to USD --rate 1.27 --date 2026-11-14 --note "Grey rate"` (use the rate your bank, Grey or Payoneer gave you, or your accountant's). The most recent rate on or before the payment date is used, a rate given the other way round is turned over, and a rate more than 45 days old is used but marked. Money with no rate is never converted: it is listed as NOT converted with the exact command that fixes it. `python dse.py fx list <engine>` shows what you entered. Nothing is looked up.

## Connect your own Claude key

In Citadel, DBI-AI > Connect Claude (a badge shows Connected, Key needed, Package needed or Not connected, read from your PC). It walks a student through four steps: get a key from Anthropic (they pay Anthropic directly, with a limit they set), install the package (one press, or `python -m pip install anthropic`), save the key on the PC with **`python dse.py claude setup`** (a small window, or `--terminal`, asks for it hidden as you type; it is checked with a free Anthropic call, then saved in the Windows user settings as ANTHROPIC_API_KEY, which a running runner reads without a restart), and check it (`python dse.py claude status --test`, also a tool in HQ Tools). `claude remove` forgets it. **The key is never typed into Citadel and never stored there:** there is no box for it in the app, no job or log carries it, and the app only learns two yes/no facts the runner reports (key present, package installed). On the PC it is shown only as `sk-ant-...` and its last four characters. A key of the wrong shape (or with a trailing newline) is refused before anything is written, and one Anthropic rejects is not saved. The runner now re-sends its status within about a minute of a change, so the badge catches up quickly.

## Claude cost control

Claude comes in three sizes, in DBI-AI's "Answering with" menu: **Haiku** (the cheapest and fastest), **Sonnet** (balanced: the default, plain "Claude") and **Opus** (the strongest, the one that costs the most); the PC's own default can be changed with the `HQ_CHAT_CLAUDE_MODEL` setting (a tier name or a model id). Before this, a student with a key got Opus on every answer. Every Claude answer's tokens (in and out) are added to today's tally (`data/claude-usage.json`, on this PC only) and shown in the answer's footer: **`python dse.py claude usage [days]`** shows them by model, **`python dse.py claude limit <tokens>`** sets a daily token limit (0 = none): once today's tally reaches it Claude rests until tomorrow, the local model answers, and the answer says why. The Connect Claude card in DBI-AI shows today's tokens against the limit and has the forms for both. Money is deliberately not worked out (prices change): the footer and the card send you to Anthropic's own usage page for what you spent and for a monthly limit. Answers are capped at 2,000 tokens. The menu offers the sizes only when the PC reports `claude_tiers`, so an older toolkit is never sent a choice it would refuse.

## DBI-AI: which model answers

In DBI-AI an "Answering with" menu lets you choose: **Automatic** (your OLLAMA_MODEL setting, else the best installed model: gemma3:4b before gemma3:1b), **one installed local model** (each shows its size, whether it is fast or slower and better, and whether it reads pictures), **Claude** (enabled once your PC has your own `ANTHROPIC_API_KEY` and `pip install anthropic`; the key never leaves your PC) or **HQ library only** (the researched guides and recipes with sources, no AI model). Your PC re-checks the choice, and a model you later delete falls back to Automatic. The OLLAMA_MODEL and ANTHROPIC_API_KEY you save in Windows are read directly, so no runner restart is needed. On a CPU-only laptop a 4-billion-parameter model takes minutes for a long answer: the answer is streamed, cut down to what a small PC can do, returned as far as it got if time runs out, and says so; a fast model or the library is one tap away.

## Student Success Desk: who needs a check-in, and what your DFY income will be

`python dse.py success <engine> [--view overview|flags|drafts|forecast] [--months 6]` (HQ Tools, "Student Success Desk"). It reads only what the Cut Desk holds, so run `cut sync <engine>` first to bring the students' Citadel filings in. Per student it shows DFY progress (qualified months out of 12, remitted out of the $18,000 cap: the two ways DFY ends) and flags who needs a check-in, **with the facts behind each flag**: has not filed (or never filed), filed 0 repeatedly, under the $2,000 line for months in a row (shown as an opportunity when within 25% of it), a sharp drop against their own recent average, few qualified months among those filed, a remittance overdue (red after 14 days), and nearly through DFY (celebrated, not chased). Paused, ended and completed students get no flags.

Each flag has a short, kind draft message in your name (a question or an offer of help, never an accusation) for you to send yourself. The forecast projects your expected DFY income for the next months from each student's own last three filed months: LIKELY uses their average, LOW their weakest month, both stop at the cap or at 12 qualified months; a student with fewer than two filed months is left out and counted. Money for a month arrives about the month after it is earned. It is a projection from past months, not a promise. The Weekly Review adds a check-in move and shows the expected income next month in its headline; the Cash Desk shows the same projection.

## Statement Matcher: match the money to the invoices

`python dse.py match <engine> <statement.csv> [--apply] [--monthfirst] [--tolerance 5]` (HQ Tools, "Statement Matcher"). Export your Grey, Payoneer or bank statement as CSV, save it in `engines/<engine>/statements/`, and it reads the money that came **in** and looks at every open invoice in the engine: student cuts (`CUT-...`) and client invoices (`INV-...`). Columns are found from the headers (date, amount or separate credit and debit, description, sender, reference, currency, status; semicolons, European decimals and a Type column all work). For each credit it uses the invoice number in the reference (the strongest sign), the amount (exact, or short by a normal transfer fee: 2% of the invoice, between $1 and $20, or the `--tolerance` you pass), the sender's name, and the date.

- **SURE** (the invoice number and a right amount both fit, it did not arrive before the invoice existed, and nothing else fits as well): recorded by `--apply` through exactly the code of `cut paid` / `client paid`, so the Cash Desk, and Citadel for DFY months, update too. **Only SURE matches are ever applied.** A payment short by a fee is recorded as received and the shortfall stays owed, for you to ask for or write off.
- **LIKELY** (name and amount fit, or the number fits with an odd amount, or it came early): shown with the exact command to run if you agree.
- **Could be more than one invoice**, **No invoice fits** (unknown senders, possibly new income needing an invoice), **Already recorded** (same amount within 3 days of a payment you recorded), **Seen before** (a line is never applied twice: a fingerprint is kept in `engines/<engine>/data/matched-lines.csv`).
- Debits, failed and pending lines are ignored; a credit in another currency than the invoice is never matched; dates like 03/04/2026 are read day first unless the file proves otherwise or you pass `--monthfirst`. The report is saved as `statements/<name>-match.md`. It has been tested on several statement shapes, but not yet on a real Grey or Payoneer export: if your first one reads wrong, send me a copy with the names and amounts blanked.

## Cut Desk: the percentage your students owe you

**The D'Famocious Year (DFY) is built in.** Citadel's DFY Tracker already defines it: 20% of the net income a student files, **capped at $18,000 in total, ending at 12 qualified months (net income of $2,000 or more) or the cap, whichever comes first**. Students already file each month on `/dfy` and pay on `/payments`. `python dse.py cut add <engine> --name "Ada Obi" --program dfy` sets those exact terms, and `python dse.py cut sync <engine>` pulls every student's filed months from Citadel into the Cut Desk (turn it on for good with `cut sync <engine> --auto on`: the runner then does it every ten minutes). Each month becomes a statement and an invoice (the last month is cut down to what the cap leaves), a month Citadel already shows as paid is recorded as paid here as history (not added to the Cash Desk twice), a changed figure after money was recorded is flagged rather than rewritten, and a disputed month is listed rather than invoiced. When you record the money (`cut paid`), Citadel is told exactly as the council's "Mark paid" does it: the pending bank-transfer entry succeeds and the student's month shows paid. If Citadel cannot be reached, the payment is still recorded and the push retries at the next sync. This needs your runner to belong to an admin and the SQL file `20261118140000_dfy_bridge_payout_accounts.sql` run in Supabase once.

**Where students pay** now lives in the database instead of the code. `python dse.py cut accounts <engine> --example` copies a template to `engines/<engine>/payout-accounts.json`: fill in your company Grey account (and Payoneer, or a bank) from your own app, then `cut accounts <engine> --publish` replaces what students see on `/payments` and the sign-up page (several accounts are shown side by side, each labelled with its method). Anything left in [brackets] is refused so an unfinished list never goes live. Until you publish, students keep seeing the accounts built into the app.

The rest of this section describes the general revenue-share tool (`--program custom`, the default) for any other arrangement. `python dse.py cut add <engine> --name "Ada Obi" --percent 10 [--basis gross|net] [--currency USD|GBP|EUR] [--method grey|payoneer|other] [--due-days 7]` sets up a student's agreement (HQ Tools, "Cut Desk") and writes an agreement starter (company and RC number, percent and basis, report by the 7th, payment within the invoice's days, the student covers transfer fees, a friendly-question clause, placeholders for late-payment terms and governing law). It is a starting point, **not legal advice: have it checked, and check that the platforms your students earn on allow sharing earnings.**

Each month: `cut report <engine>/<student> --month 2026-11 --earned 3200 [--fees 320] --proof "Nov statement in the proofs folder"` works out the cut (percent of gross, or of net of the platform's fees), makes an invoice in the company name (`CUT-<year>-<n>` as a print-ready page, you send it yourself) and notes missing proof. Zero is a valid report and makes no invoice. A month can be corrected with `--replace` until something is paid on it (its invoice number is kept, so numbers never skip). A drop to under half of the student's own last-three-months average gets a friendly prompt to ask how the month went, never an accusation.

When money arrives: `cut paid <engine>/<student> --invoice CUT-2026-001 [--amount 280] [--writeoff]` records what actually arrived and adds it to the Cash Desk as commission. A payment that comes in short (usually a transfer fee) says so, and `--writeoff` accepts the shortfall on the record. `cut list <engine>` shows invoiced, received and owed per student, and what each needs; `cut show`, `cut status --to paused|ended|active` complete it. The Weekly Review adds two moves: overdue cut invoices and students who have not reported by the 7th of the next month.

Where the money goes: put your account details in `engines/<engine>/payment-details-grey.txt` (or `-payoneer.txt`, or one `payment-details.txt`) on your PC. Invoices read them from there, so they never sync to Citadel or Git. The Cash Desk adds amounts as they are and does not convert currencies. For DFY students the filing already happens in Citadel (see above); for any other arrangement you enter their reports. The company (not a personal) account is the cleaner home for the cut: ask your accountant.

## Client Desk: from "yes" to paid

When a proposal is accepted: `python dse.py client won <engine> --proposal 2026-11-14-acme-dental [--email dana@acme.com] [--address "..."]` (HQ Tools, "Client Desk": this proposal was accepted). The Proposal Builder now also saves its data, so the price, deposit, timeline and deliverables carry over without retyping. You get `engines/<engine>/clients/<client>/onboarding.md` (a dated checklist, a welcome message in your name, a short agreement outline: a starting point, not legal advice), the delivery plan with a due date per deliverable, and the deposit invoice as a print-ready page.

Then: `client done <engine>/<client> --item "booking page"` ticks a deliverable or an onboarding task (a few words of its name; the last deliverable tells you to issue the final invoice), `client invoice <engine>/<client> --kind final` bills the balance of the price after delivery (or `--kind extra --amount 200 --note "..."`), and `client paid <engine>/<client> --invoice INV-2026-001 [--amount 400]` records a payment (partial payments are fine; no amount means what is left) **and adds it to the Cash Desk**, so what you received stays true without typing it twice. `client list <engine>` and `client show <engine>/<client>` show where everyone stands. In Citadel the pickers list your clients, so there is nothing to type.

The Weekly Review picks it up: an overdue invoice (with the amount still owed) and a late deliverable each become a move. Nothing is sent: you send the welcome message, the agreement and the invoices yourself. Put your payment details in `engines/<engine>/payment-details.txt` on your PC (it is read when an invoice is made, and stays off Citadel and Git). The Cash Desk adds amounts as they are and does not convert currencies.

## Proposal Builder: after a good call

`python dse.py proposal <engine> --client "Acme Dental" --contact Dana --problem "patients cannot book online" --offer "Online booking" --price 1500 --deliverables "Booking page; Reminder emails; Staff training" --weeks 3 [--cost-month 4000] [--options "Basic:800:2 pages; Standard:1500:5 pages; Premium:2800:10 pages"] [--deposit 50] [--currency USD|GBP|EUR] [--excludes "..."]` (HQ Tools: "Proposal Builder") writes a one-page proposal, a cover email and a follow-up for 3 days later, in your sender name, and saves them in `engines/<engine>/proposals/` as text and as a print-ready `.html` (open it and Print > Save as PDF). Everything comes from what you type. Given what the problem costs them each month, it shows the yearly cost and the payback as plain arithmetic, labelled as not a promise. It invents no results, testimonials or guarantees, spreads your deliverables over the weeks with dates, marks `[brackets]` for facts only you know and lists them before you send, and warns when your price is more than a year of their problem. It sends nothing.

## Outreach Preflight: check before you send

`python dse.py preflight <engine|list> [--domain yourdomain.com] [--clean]` (HQ Tools: "Outreach Preflight") checks the newest send list, or one you name, row by row before anything goes out. **Blockers:** on your do-not-contact list (from the Reply Desk, by email or whole domain), a missing or invalid address, already contacted (the log says Sent, or the business is on an earlier list), the same business twice, an unfilled placeholder like `{business}` still in the message. **Warnings:** spam trigger words, ALL CAPS, too many exclamation marks or links, a long message, role (info@) or free mailboxes, an Email message with no easy way to say no, no sender name, no postal address in the engine settings (CAN-SPAM), more email than your own engine cap or the common daily ceiling for one mailbox. With `--domain` it also looks up your sending domain's mail servers, SPF, DMARC and the common DKIM names. `--clean` saves a copy without the blocked rows in the engine's `send-lists/drafts/` (the original is never touched). Thresholds are in `dse/preflight_rules.json`. This is deliverability and good-manners guidance, not legal advice.

## Reply Desk: what a reply means and what to say

`python dse.py reply <engine> --text "Thanks but we already have an agency" [--name Dana] [--source 2026-11-09 --row 7 --log]` (HQ Tools: "Reply Desk") reads a reply you received and tells you, by plain rules with no AI model: what kind it is (interested, question, price objection, already has someone, not now, not interested, wrong person, points to someone else, asks to stop, out of office, or unclear), the words that decided it, a short honest draft answer in your sender name (with [brackets] where only you know the facts), and the day to follow up ("in 3 months", "next quarter", "in March", "back on 3 December"). It never sends anything. With `--log` and the list and row it answers, it records the reply in the engine's send log (so follow-ups stop for that thread) and puts unsubscribes and "no thanks" on `engines/<engine>/data/do-not-contact.csv`. No tool removes an entry. `python dse.py dnc <engine>` lists them.

## Lead enrichment (free, with an optional bring-your-own-key upgrade)

`python dse.py enrich leads.csv [--icp "emergency, 24/7"] [--engine my-engine] [--max 100] [--fast]` (HQ Tools, group Grow: "Lead enrichment") turns a list of companies into reachable leads using **only each company's own public website**. The file needs a website or domain column (Clay, Apollo and HubSpot exports already have one); every column you gave is kept and your own emails are never overwritten. `python dse.py enrich --site https://their-site.com` shows one site.

Per lead, a waterfall that stops as soon as it has what it needs (the `steps` column shows what ran): your file's own data, the homepage, the contact/about/team pages, a hidden browser for sites drawn by JavaScript, and, only for a named owner with no email on a domain that receives mail, a few likely addresses marked as **guesses** (never put in the email column). It finds emails, the owner and title, phone, contact form, booking tool, socials, tech and a description, and each finding names the page it came from. The score and the "why" come from the rules in `dse/enrich_rules.json`. With `--engine` it also saves an import-ready copy in the engine's `imports/`, which `python dse.py import <engine>` understands.

It respects `robots.txt`, pauses a second between pages, never logs in anywhere, and never reads Google Maps or social networks. A summary (`my-lists/<date>-enriched-<name>.md`) gives the yield at each step and the best leads first.

**Paid sources are optional and bring-your-own-key.** Nothing paid runs unless you name a provider: `python dse.py enrich --add-provider hunter`, then put your own key in a Windows user variable (`setx HUNTER_API_KEY "..."`, the key is never in a file, in Git or in Citadel), then `--provider hunter --budget 25`. The budget caps paid lookups per run, answers are cached for 30 days so a domain is never paid for twice, and the paid step runs only for leads the free steps could not finish. Any API that answers "which emails does this domain have" can be added by copying `dse/provider_examples/TEMPLATE.json` to `enrich-providers/NAME.json` and filling it from the provider's documentation. `python dse.py enrich --providers` lists what is set up.

## Weekly Review and monthly goals

`python dse.py review <engine|all> [--top 5]` (HQ Tools: "Weekly Review") gives the few things to do first this week, ranked by one fixed rule, closest to money first: replies waiting for you, calls booked, follow-ups due, messages on your lists not yet sent, sold calls whose money is not logged, nothing sent for 7 days, offers still being vetted, a goal to accept or a goal you are behind on. Each move names the exact step and the file the number came from. It sends and changes nothing, and saves `engines/<engine>/weekly-review.md`.

`python dse.py goal <engine> [--month 2026-12] [--stretch 20]` (HQ Tools: "Monthly goal") automates the goal. The suggestion is the average of the money you logged in your last 3 complete months (or your last month if it beat that), plus a stretch you choose (default 20%), rounded up to the next $50, with the working shown, then what each week would need (sales, calls, messages) from your own rates, or a plain "too little data". A month with no goal of its own carries your standing target, so there is always one. The runner also writes `engines/<engine>/next-goal.md` every few hours when the month ahead has no goal. **Nothing changes a goal unless you add `--apply` or `--set 4000`.** The Cash Desk and the review use that month's goal.

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

## Building lists: what helps on each path

| Path | How the list is built now |
|---|---|
| **SMB Optimization, AI Voice Receptionist, AI Automation** | The lead pack (niche or business type, cities; type your own business type), the website problem check, enrichment (owners, emails, phones), then "Add to my CRM" or CRM sync. |
| **The Broadcast Engine** | The podcast finder (Apple Podcasts, by genre), with what each show is missing and the host's public email. |
| **Revenue Recovery, The Ascent, Go-to-Market** | You bring the names (store URLs from the Meta Ad Library, companies from search and YouTube, an export from your own Clay, Apollo or HubSpot account); the tools read each site, enrich it, score it and draft the opener. |
| **The Authority Engine** | You paste each expert's headline, post dates and posts (nothing is read from LinkedIn); the audit finds who posts little. DBI-AI or Claude can arrange what you paste into the columns. |
| **Digital Ministry** | Warm network only, by design. |

Everywhere: no scraping of LinkedIn, Instagram, Facebook or Google Maps pages, and nothing is sent for you.

## The rules this toolkit follows (DSE Constitution)
- **No free work for cold prospects.** The openers offer to *send what you found*, never to do the job free.
- **Read the gap before you send.** The checker leans towards "has it", so a gap it reports is real, but open the site and confirm. "Check by hand" means the site blocked the script: look yourself.
- **Build lists with the tools, then look at every lead.** The old SMB rule (scout 50 leads by hand before using the finder) is retired: use the lead pack, enrichment and the website check from day one, and DBI-AI (or Claude with your own API key) to shortlist, score and draft openers. An AI can invent a business and cannot browse sites or social networks, so open each lead before you contact it.
- **Ministry is warm-network only.** Check your own parish and churches you're introduced to.
- **No scraping** of LinkedIn, Instagram, Facebook or Google Maps. It breaks their terms and gets accounts banned.

Data: Foursquare Open Source Places (Apache 2.0), Apple Podcasts Search API and public podcast RSS feeds, and OpenStreetMap Nominatim for city locations.
