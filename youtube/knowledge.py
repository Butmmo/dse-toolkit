"""YouTube Launchpad knowledge base: what the tool knows. Plain data, edit it freely.

Everything with a number or a rule carries its source and the date it was checked, because YouTube changes
its rules. The tool prints those dates, and `launch.py plan` tells the student to re-check the official page
before acting on them. Nothing here promises income: it teaches the method and the odds honestly.
"""

CHECKED = "2026-11-14"

YPP = {
    "sources": [
        "https://support.google.com/youtube/answer/72851",      # YouTube Partner Program eligibility
        "https://support.google.com/youtube/answer/1311392",    # YouTube channel monetization policies
    ],
    "long_form": {"subs": 1000, "watch_hours": 4000, "window_days": 365},
    "shorts": {"subs": 1000, "shorts_views": 10_000_000, "window_days": 90},
    "requirements": [
        "Follow the YouTube channel monetization policies.",
        "Live in a country or region where the Partner Program is available (check the list on YouTube's own page: it changes).",
        "Have no active Community Guidelines strikes.",
        "Turn on 2-Step Verification for the Google Account that owns the channel.",
        "Have access to advanced features on YouTube (verify your phone number in YouTube Studio).",
        "Have one active AdSense account linked to the channel (you can set it up inside YouTube Studio).",
    ],
    "review": "Reaching the numbers does not guarantee approval. Channels go through a review that typically takes about a month.",
    "note": "YouTube also offers earlier access to some fan-funding features at lower numbers in some regions: look in YouTube Studio > Earn to see what your channel can use today.",
}

# format id -> (label, faceless, effort 1-3, what you need, note)
FORMATS = {
    "screen": ("Screen recording tutorial", True, 2, "OBS Studio (free), a microphone or phone earbuds", "Show the screen, explain what you do and why. Best for software, websites, AI tools, spreadsheets."),
    "slides": ("Voiceover over slides", True, 1, "Canva or PowerPoint, a microphone", "A clear slide for every point, big words, your voice explaining. Fastest to make."),
    "broll": ("Voiceover with stock video", True, 3, "Free stock video (Pexels, Pixabay), editor (DaVinci Resolve or CapCut)", "Needs real thought on every shot or it looks like filler. Your script and your voice are what make it original."),
    "whiteboard": ("Whiteboard or drawn explainer", True, 3, "A drawing app or paper and a phone camera pointed down", "Draw while you explain. Memorable, hard to copy."),
    "textstory": ("Text and image story", True, 2, "Slides, a calm voice or clear captions", "Case studies and stories told with your own research and photos."),
    "talking": ("Talking to camera", False, 1, "Phone, window light, earbuds", "Fastest way to build trust. Look at the lens, short sentences, cut the pauses."),
    "demo": ("Hands-on demonstration", False, 2, "Phone on a stand, good light", "Show the real thing being done (cooking, repairing, designing a room, preparing a CV)."),
    "walkthrough": ("Place or process walkthrough", False, 2, "Phone with a gimbal or steady hands", "Walk the viewer through a place, a product or a process, with narration."),
}

TITLE_PATTERNS = {
    # id: (title template, intent, hook templates, thumbnail idea, short cut-down)
    "how": (["How to {t} (step by step for beginners)", "How to {t} (for beginners)", "How to {t}", "{N}: a beginner's guide"], "how-to",
            ["If you want to {t}, there are only {n3} steps that matter. Here they are, in order.",
             "Most people make this harder than it is. In the next few minutes I will show you the simple way to {t}.",
             "By the end of this video you will know exactly how to {t}, even if you are starting from zero."],
            "3 words max on the thumbnail (the result, not the topic), one clear object, strong contrast", "The first step only, in 30 seconds, with 'part 2 on my channel'"),
    "mistakes": (["7 mistakes beginners make when they {t}", "7 {n} mistakes beginners make", "7 {n} mistakes to avoid"], "mistakes",
                 ["I made most of these mistakes myself. Number 4 cost me the most.",
                  "If you {t} the way most people do, you will waste weeks. Avoid these 7 mistakes.",
                  "Here are the 7 mistakes I see over and over when people {t}."],
                 "A big red cross or the number 7, one frustrated or surprised element", "The worst mistake only, with the fix"),
    "story": (["I tried to {t}: honest results", "I tried {n}: honest results", "I tested {n}: what happened"], "case study",
              ["I tried to {t} and I am going to show you everything, including what went wrong.",
               "No hype: this is exactly what happened when I tried to {t}.",
               "Everyone says you can {t}. I tested it so you do not have to."],
              "Before and after, or a number from the result, with a plain honest face or object", "The single most surprising moment"),
    "explain": (["{N} explained in 5 minutes", "{N} explained simply"], "explainer",
                ["{N}: what it is, why it matters and what to do about it, in five minutes.",
                 "Confused by {n}? By the end of this video it will make sense.",
                 "You hear about {n} everywhere. Here is the plain explanation nobody gave you."],
                "The one word the viewer is confused by, large, with a question mark", "The one-sentence definition, then a simple example"),
    "checklist": (["The complete checklist to {t} in {year}", "The {n} checklist for {year}", "The {n} checklist"], "checklist",
                  ["Pause the video and tick along: this is the full checklist to {t}.",
                   "Before you {t}, check these things. Skipping any one of them costs time and money.",
                   "Save this checklist. It is everything you need to {t} in {year}."],
                  "A checklist graphic with 2 ticked boxes and one empty box", "Three items from the list, then 'full checklist on my channel'"),
    "truth": (["{N}: what nobody tells beginners", "{N}: the truth for beginners"], "insight",
              ["Nobody tells beginners the truth about {n}. I will.",
               "Before you spend any money on {n}, watch this.",
               "Here is what I wish someone had told me about {n} on day one."],
              "A bold claim in 3 words, with a visual that shows the tension", "The one thing you wish you knew, in one breath"),
    "wish": (["5 things I wish I knew before I tried to {t}", "5 things I wish I knew about {n}", "5 lessons about {n}"], "list",
             ["I wish someone had told me these 5 things before I tried to {t}.",
              "Five lessons, each one learned the hard way, about trying to {t}.",
              "If I could go back, I would tell myself these 5 things before I tried to {t}."],
             "The number 5 large, a simple photo or icon that shows the topic", "Lesson number one, delivered in 25 seconds"),
}

# Seeds per niche: "verb phrase | noun phrase". Titles are built from these, so keep them natural.
NICHES = {
    "ai-tools": {
        "name": "AI tools and automation for work",
        "audience": "Employees, freelancers and small business owners who want to save time with AI",
        "formats": ["screen", "slides", "talking"], "advertiser_demand": "high",
        "policy": "Show real results from real use. Do not make up demonstrations or claim tools do things they do not. Say clearly when something is a paid tool.",
        "income": ["Affiliate links to tools you really use (disclose them)", "Sponsorships from software companies", "Your own automation or training service (leads from the video)"],
        "seeds": ["automate customer emails with AI | AI email automation", "write a month of social posts with AI in one hour | AI content planning",
                  "build a simple chatbot for a small business | business chatbots", "summarise long documents with AI | AI document summaries",
                  "use AI to prepare for a job interview | AI interview practice", "clean and analyse a spreadsheet with AI | AI spreadsheet analysis",
                  "set up a free automation with n8n | n8n", "turn meeting notes into action lists with AI | AI meeting notes"]},
    "no-code-building": {
        "name": "Build websites and apps without code",
        "audience": "Beginners and small business owners who want a website or app without hiring a developer",
        "formats": ["screen", "slides", "talking"], "advertiser_demand": "high",
        "policy": "Be honest about limits and costs. Show the finished result working.",
        "income": ["Done-for-you website and app services (leads from the video)", "Affiliate links to hosting and builder tools (disclose)", "Templates you make and sell"],
        "seeds": ["build a business website for free | free business websites", "put a website online with a free host | free website hosting",
                  "make a booking page for a small business | online booking pages", "build a mobile app without writing code | no-code mobile apps",
                  "add a contact form that emails you | website contact forms", "get a custom domain name and connect it | custom domains",
                  "build a simple online store | starting an online store", "make your website show up on Google | beginner website SEO"]},
    "small-business-marketing": {
        "name": "Marketing for local and small businesses",
        "audience": "Owners of small local businesses and the people who work for them",
        "formats": ["screen", "slides", "talking", "demo"], "advertiser_demand": "high",
        "policy": "Do not promise specific revenue results. Use real examples with permission, or clearly label examples as examples.",
        "income": ["Your own service for local businesses (the best income route: the channel is your proof)", "Affiliate links to CRM and review tools (disclose)", "Consulting calls"],
        "seeds": ["get more Google reviews for a local business | getting Google reviews", "fix a Google Business Profile in 20 minutes | Google Business Profile",
                  "get customers from Instagram as a local business | Instagram for local business", "follow up with leads so they do not go cold | lead follow-up",
                  "answer every missed call with a text-back | missed call text-back", "write an offer a customer cannot ignore | writing offers",
                  "check why a competitor ranks above you on Google | local SEO", "send a simple email newsletter that gets read | small business email"]},
    "careers-recruiting": {
        "name": "Careers, jobs and recruiting",
        "audience": "Job seekers, graduates, and recruiters who want to work smarter",
        "formats": ["slides", "talking", "screen", "textstory"], "advertiser_demand": "high",
        "policy": "Give general guidance, not guaranteed outcomes. Do not share anyone's private details.",
        "income": ["CV review and coaching services", "Recruiting services (leads from the video)", "Affiliate links to resume and learning tools (disclose)"],
        "seeds": ["write a CV that gets interviews | CV writing", "answer 'tell me about yourself' in an interview | interview answers",
                  "find remote jobs that really pay | remote job search", "negotiate a higher salary offer | salary negotiation",
                  "start a recruiting agency from home | starting a recruitment agency", "write a LinkedIn profile recruiters find | LinkedIn profiles",
                  "follow up after an interview without being annoying | interview follow-up", "spot a fake job offer before it costs you | job scams"]},
    "freelancing": {
        "name": "Freelancing and selling your skills online",
        "audience": "People who want to earn from a skill: writing, design, development, virtual assistance, editing",
        "formats": ["screen", "slides", "talking", "textstory"], "advertiser_demand": "medium",
        "policy": "Never promise income. Show real process and real limits. Income screenshots must be real and not misleading.",
        "income": ["Your own freelance clients (the channel is your portfolio)", "Courses or templates", "Affiliate links to freelancing tools (disclose)"],
        "seeds": ["write an Upwork proposal that gets replies | Upwork proposals", "set your first freelance price | freelance pricing",
                  "build a portfolio with no clients | freelance portfolios", "find your first paying client in 30 days | first freelance client",
                  "handle a client who keeps changing the brief | difficult clients", "get paid safely from international clients | getting paid internationally",
                  "choose a freelance skill that sells | choosing a freelance skill", "write a contract a small client will sign | freelance contracts"]},
    "personal-finance": {
        "name": "Personal money basics",
        "audience": "Young adults and families learning to budget, save and avoid money traps",
        "formats": ["slides", "talking", "textstory"], "advertiser_demand": "high",
        "policy": "Teach general principles only. Do not give personal investment advice or promise returns. Be careful with finance topics: YouTube applies extra scrutiny to finance content, so use real sources and a real voice.",
        "income": ["Affiliate links to budgeting tools (disclose)", "Sponsorships from financial education products", "Your own templates"],
        "seeds": ["make a monthly budget that you keep | monthly budgets", "build an emergency fund on a small income | emergency funds",
                  "get out of debt without a big salary | paying off debt", "save money on a low income | saving money",
                  "spot a money scam before you lose your savings | money scams", "track every naira or dollar with a free spreadsheet | expense tracking",
                  "understand interest without a finance degree | how interest works", "plan for irregular freelance income | irregular income"]},
    "productivity-study": {
        "name": "Productivity and study skills",
        "audience": "Students and busy workers who want to get more done with less stress",
        "formats": ["slides", "talking", "screen", "whiteboard"], "advertiser_demand": "medium",
        "policy": "Share methods you actually use. Do not make health claims.",
        "income": ["Affiliate links to apps and stationery (disclose)", "Sponsorships from study and productivity apps", "Your own planners and templates"],
        "seeds": ["plan your week in 15 minutes | weekly planning", "study for an exam in one week | last-week studying",
                  "stop procrastinating on big tasks | procrastination", "take notes you can actually use later | note-taking",
                  "build a morning routine that survives a busy life | morning routines", "use a free app to organise all your tasks | task management",
                  "focus for two hours without your phone | deep focus", "remember what you read | remembering what you read"]},
    "faith-reflections": {
        "name": "Faith reflections and parish life",
        "audience": "Catholic and Christian viewers who want short, sincere reflections and practical parish help",
        "formats": ["talking", "slides", "textstory", "broll"], "advertiser_demand": "medium",
        "policy": "Quote scripture and Church documents accurately and say where they come from. Use only music and images you have the right to use. Do not claim miracles or healing.",
        "income": ["Donations from viewers (clearly explained)", "Parish and ministry technology services (leads from the video)", "Books and resources you create"],
        "seeds": ["pray the rosary when you are tired | praying the rosary", "prepare your heart before Mass | preparing for Mass",
                  "read the Bible without feeling lost | reading the Bible", "make confession less scary | going to confession",
                  "start a parish social media page that people follow | parish social media", "stream Mass online with just a phone | streaming Mass",
                  "pray the Liturgy of the Hours as a beginner | Liturgy of the Hours", "live a simple Lent that changes you | keeping Lent"]},
    "caregiving-info": {
        "name": "Home care and caregiving guidance",
        "audience": "Families caring for elderly parents and people who work in home care",
        "formats": ["talking", "slides", "demo", "textstory"], "advertiser_demand": "medium",
        "policy": "General information only, never medical advice or diagnosis: say 'ask a qualified professional' where needed. Health content is sensitive: cite reputable sources. Never show a real person's private health details without written consent.",
        "income": ["Home care agency services (leads from the video)", "Affiliate links to care products (disclose)", "Printable care checklists"],
        "seeds": ["choose a home care agency for a parent | choosing a home care agency", "prepare a home for an elderly parent | elder-safe homes",
                  "talk to a parent about needing help | talking to a parent about care", "plan a daily care routine | daily care routines",
                  "spot signs that a parent needs more help | signs a parent needs help", "pay for care without panic | paying for care",
                  "avoid caregiver burnout | caregiver burnout", "check that a caregiver is trustworthy | vetting caregivers"]},
    "ecommerce": {
        "name": "Online stores and email marketing",
        "audience": "Small online shop owners who want more repeat customers",
        "formats": ["screen", "slides", "talking"], "advertiser_demand": "high",
        "policy": "No fake income claims. Show real dashboards only with permission or from your own store.",
        "income": ["Your own email and store services (leads from the video)", "Affiliate links to email tools (disclose)", "Templates for flows and emails"],
        "seeds": ["set up an abandoned cart email in 20 minutes | abandoned cart emails", "get more repeat customers for your shop | repeat customers",
                  "write a welcome email that sells | welcome emails", "grow an email list from zero | email list building",
                  "add product reviews that build trust | product reviews", "set up a simple win-back email | win-back emails",
                  "read your store numbers without a degree | store analytics", "price a product without losing money | product pricing"]},
    "creators-podcasting": {
        "name": "Podcasting and growing as a creator",
        "audience": "New podcasters and creators who want to publish steadily and grow",
        "formats": ["screen", "talking", "slides", "demo"], "advertiser_demand": "medium",
        "policy": "Use only audio, clips and music you have the right to use. Never repost other people's shows.",
        "income": ["Sponsorships", "Production services for other podcasters (leads from the video)", "Affiliate links to gear and hosting (disclose)"],
        "seeds": ["start a podcast with only a phone | starting a podcast", "get your first 100 listeners | podcast growth",
                  "record good audio in a noisy room | recording audio", "turn a podcast into a YouTube channel | podcast to YouTube",
                  "cut a podcast into short clips that get views | podcast clips", "write show notes that bring in listeners | show notes",
                  "get a guest to say yes | booking podcast guests", "plan 12 episodes before you record one | episode planning"]},
    "tech-how-to": {
        "name": "Everyday tech how-tos",
        "audience": "Everyday computer and phone users who want clear help",
        "formats": ["screen", "slides", "demo"], "advertiser_demand": "medium",
        "policy": "Test every step before you publish it. Do not show or ask for anyone's passwords.",
        "income": ["Affiliate links to software and gadgets (disclose)", "Local tech support or training (leads from the video)", "Sponsorships"],
        "seeds": ["speed up a slow Windows laptop | speeding up a laptop", "recover a file you deleted by mistake | file recovery",
                  "make Excel do the boring work for you | Excel basics", "protect your accounts from being hacked | account security",
                  "back up your phone and computer for free | free backups", "set up a printer that refuses to connect | printer problems",
                  "connect two screens to one laptop | dual monitors", "clean up your phone storage safely | phone storage"]},
    "history-explainers": {
        "name": "History and clear explainers",
        "audience": "Curious viewers who like a story told well",
        "formats": ["broll", "slides", "whiteboard", "textstory"], "advertiser_demand": "medium",
        "policy": "Write every script yourself from reliable sources and list the sources. Do not reuse other creators' videos or scripts. Use only images and clips you have the right to use.",
        "income": ["AdSense (the main route here)", "Sponsorships", "Books or courses on your subject"],
        "seeds": ["understand how an empire fell | the fall of an empire", "explain a war in ten minutes | a short history of a war",
                  "tell the real story behind a famous event | the story behind an event", "trace how a city grew | the history of a city",
                  "show how a famous invention really happened | the history of an invention", "explain why a famous mystery is still unsolved | an unsolved mystery",
                  "compare two historical leaders fairly | two historical leaders", "follow one ordinary person through a big moment in history | ordinary people in history"]},
    "food-cooking": {
        "name": "Cooking and food",
        "audience": "Home cooks who want reliable recipes and techniques",
        "formats": ["demo", "talking", "broll"], "advertiser_demand": "medium",
        "policy": "Only share recipes you have cooked. Credit recipes you adapt. Do not make health claims.",
        "income": ["AdSense and sponsorships", "Affiliate links to kitchen tools (disclose)", "A recipe book or catering service"],
        "seeds": ["cook a perfect pot of jollof rice | jollof rice", "make soup that tastes like a restaurant's | restaurant-style soup",
                  "meal prep a week of food for little money | cheap meal prep", "cook with one pot and no stress | one-pot meals",
                  "fix a recipe that went wrong | rescuing a recipe", "bake without an oven | baking without an oven",
                  "stretch one chicken into five meals | stretching a chicken", "cook for a crowd without panic | cooking for a crowd"]},
    "interior-home": {
        "name": "Interior design and home improvement",
        "audience": "Home owners and renters who want better-looking rooms on a budget",
        "formats": ["demo", "walkthrough", "talking", "slides"], "advertiser_demand": "high",
        "policy": "Show real projects with permission from the owners. Credit anyone whose work you show.",
        "income": ["Design services (leads from the video)", "Affiliate links to furniture and decor (disclose)", "Sponsorships from brands"],
        "seeds": ["make a small room look bigger | small room design", "pick a paint colour you will not regret | choosing paint colours",
                  "decorate a rented flat without damaging walls | renting and decorating", "arrange furniture so a room feels right | furniture layout",
                  "light a living room properly | living room lighting", "redo a room for under a small budget | budget room makeover",
                  "avoid the mistakes that make a home look cheap | common design mistakes", "plan a kitchen before you spend anything | kitchen planning"]},
}

GOALS = {
    "ads": "Earn from YouTube ads (the Partner Program) as the main income",
    "leads": "Use the channel to bring clients to a service I sell (the most reliable route for new creators)",
    "affiliate": "Earn from affiliate links and sponsors, with ads as a bonus",
    "authority": "Build authority and a following first, income later",
}

TOOLS_FREE = [
    ("Planning and research", "YouTube search autocomplete, Google Trends, and your competitors' most-viewed videos (sort their channel by Popular). The free versions of vidIQ or TubeBuddy add keyword hints."),
    ("Recording", "OBS Studio (free) for screen and voice. A phone camera in front of a window for talking videos. Wired earbuds with a mic beat a laptop microphone."),
    ("Editing", "DaVinci Resolve (free) or CapCut (free tier). Learn three things first: cut, captions, and normalising audio."),
    ("Audio", "Audacity (free) to remove background noise. Record in a small room with soft things around you, such as a wardrobe full of clothes."),
    ("Thumbnails and graphics", "Canva (free tier). Use big simple shapes, 3 words at most and a strong contrast between text and background."),
    ("Music and sound", "YouTube Audio Library inside YouTube Studio. Check the licence for anything else. Never use a song just because it is popular."),
    ("Stock footage", "Pexels and Pixabay (free licences: read each licence and credit where asked). Never use clips from other creators."),
    ("Voice", "Your own voice is best. If you use a synthetic voice, YouTube asks you to disclose realistic altered or synthetic content and treats mass-produced, repetitive videos as a risk: add your own script, research and commentary."),
]

POLICY_FACELESS = [
    "A faceless channel is allowed. What YouTube checks for is original, valuable content, not whether you show your face.",
    "Write your own script and add real value: research, experience, a point of view, a demonstration. A channel of near-identical videos made from a template, with little of you in them, is at risk of being judged mass-produced or repetitive.",
    "Do not re-upload other people's videos, clips or audio, even with edits and credit, unless you have the right to. A reaction or review only works when your commentary is the point.",
    "If you use AI to help with research, outlines or editing, check every fact yourself and put your own judgement in. If a video contains realistic altered or synthetic content that could mislead, use YouTube's disclosure setting in the upload form.",
    "Never buy subscribers, views or comments. It breaks the rules and ruins the numbers you need to learn from.",
    "Use music, images and footage you have the right to use. A copyright claim can take away a video's earnings.",
    "Answer 'made for kids' honestly in the upload settings. Wrong answers can lose you features and comments.",
    "Re-read the official monetization policies page every few months. Policies change and the official text beats any summary, including this one.",
]

SETUP_CHECKLIST = [
    "Create the channel from a Google account only you control. Turn on 2-Step Verification on that account now: it is required for monetization.",
    "Verify your phone number in YouTube Studio (Settings > Channel > Feature eligibility) to unlock longer videos and custom thumbnails.",
    "Choose a name that says what the channel is about or who it is for, not just your own name. Pick a handle that is short, easy to say and easy to spell.",
    "Write the About text: who it helps, the promise, how often you publish, where to get in touch. The first two lines matter most.",
    "Make a profile picture that is readable when tiny: one letter, one simple mark, or your face. Make a banner with the promise in one line.",
    "Set the channel country, a business contact email, and your links (website, your service page, a free resource).",
    "Set upload defaults: category, language, a standard description footer with your links, and 'not made for kids' if that is true.",
    "Record 5 videos before you publish the first, so you can publish steadily for the first month without panic.",
    "Make a channel trailer later, not now. Your first job is to publish and learn what people watch.",
    "Create a simple tracker (this tool keeps one) and write down your numbers every week.",
]

ANALYTICS_GUIDE = [
    ("Impressions click-through rate (CTR)", "How many people who saw your thumbnail and title clicked. Rule of thumb: under 2% means the packaging is weak, 2-4% is ordinary for a small channel, 4-10% is good. Fix the thumbnail and title first, before you change the video."),
    ("Average percentage viewed and retention curve", "Where people leave. A big drop in the first 30 seconds means the hook does not match the title or takes too long. Cut the intro, state the promise in the first sentence."),
    ("Average view duration", "Multiply by views to see watch time. A longer video only helps if people actually watch it. Make the video as long as it needs to be, and no longer."),
    ("Traffic sources", "Browse and Suggested mean YouTube is recommending you: make more like that video. Search means people look for it: make more of that topic and use the words they type. External is you sharing it: useful for the first views, not a plan."),
    ("Returning viewers", "A rising share of returning viewers means people like you enough to come back. That is what builds a channel."),
    ("Which videos beat your average", "Your best three videos show you what the audience wants. Make a version of each every month, from a new angle."),
]

PITFALLS = [
    "Chasing a niche only because ads pay more there. If you hate the topic you will quit by month three. Choose a topic you can make 50 videos on, and where you have real experience or can learn publicly.",
    "Changing niche every month. You need about 20 videos in one niche before the numbers teach you anything.",
    "Spending weeks on the first video. Publish, learn, improve. Your tenth video will be better than your first, and nobody saw the first.",
    "Titles that promise what the video does not deliver. It raises clicks once and kills retention, which is what YouTube watches.",
    "Ignoring the first 30 seconds. Most viewers decide there.",
    "Looking at subscribers only. Watch time, retention and click-through tell you what to fix.",
    "Waiting for approval to start earning. For most new creators the real income in the first year comes from clients, affiliates or sponsors found through the channel, not from ads.",
    "Believing income stories. Most new channels take many months to reach the Partner Program thresholds, and many do not reach them. Treat the first 90 days as learning.",
]
