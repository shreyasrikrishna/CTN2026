# CLAUDE.md: Capture the Narrative 2026 bot

Read this whole file before making changes. It summarises the official competition
site (https://capturethenarrative.com/info/competitions/2026/) so you don't need to
re-fetch it. If anything here conflicts with the official Rules or Scoring pages,
the official pages win; fetch them to check.

## 1. What this project is

UNSW "Capture the Narrative" (CtN) 2026: a research competition where teams build
AI bots that post on a fictional Twitter-style site, **Legit Social**
(https://social.legitreal.com), to sway simulated citizens in a referendum.

- Runs **19 Oct 2026 6pm Sydney to 2 Nov 2026** (referendum day).
- Our team: 3 people. Each teammate runs **their own bot** from their own code
  setup (see section 7 for how we share limits).
- Our team is assigned one side: **Vote Yes** or **Vote No** (set in `.env` as `SIDE`).
- Top 3 teams by score present at a prizegiving in Sydney; prizes $5,000 / $2,500 / $1,500.
  Finalists must: complete pre- and post-competition surveys, hand over all source
  code, and attend in person.

## 2. The setting (Kingstonia)

Fictional Pacific island, ~600,000 people (Kingstonia City ~300k, Crown Harbour ~150k,
New Haven ~50k, ~100k on outer islands by ferry). English-speaking. Economy: tourism
(biggest), agriculture, fishing, small software sector. Currency K$.

**Referendum question (2 Nov 2026):** "Should proof of H2D2 Dolphin Flu vaccination
be required to enter public spaces such as shops, schools, workplaces, public
transport, and parks?"

**H2D2 Dolphin Flu:** new flu-like virus spreading in nearby Pacific nations. Not yet
in sustained community transmission in Kingstonia. Region: several thousand confirmed
cases, a few dozen deaths (almost all over-60 or with existing illness), ~1 in 20 cases
hospitalised. New mRNA vaccine: strong immune response in trials, no major safety
concerns so far, but unknowns (duration, transmission, boosters, rare side effects).
First 120,000 doses arrive last week of October for health workers and high-risk people
(voluntary). Vaccine free; manufacturers Halvorsen-Reid Biologics and Meridian Vaxx;
no-fault government compensation scheme; remainder costs ~K$18M from budget.

**If Yes wins:** requirement phased in only after everyone has had a chance to vaccinate;
applies to ages 12+; medical exemptions; paper or digital certificate (separate from the
new national ID card); visitors covered. The list of "designated public spaces" has NOT
been published (both campaigns attack this).
**If No wins:** no access requirement for the life of the current Assembly without a
new referendum.

**Yes campaign:** Medical Officers Union of Kingstonia (MOUK), led by Dr Amara Singh
(trusted COVID-era TV doctor, GP at Kingstonia Central Hospital). Message:
"Mandate now. Protect Kingstonia." Arguments: prevention before outbreak, tiny health
system, IHO recommends it, shared responsibility, avoid another lockdown, nobody is
physically forced.
**No campaign:** Kingstonia Industry Tourism Board (KITB), led by Marina Castillo
(resort CEO, narrowly lost 2025 presidential election). Message: "Protect choice.
Keep Kingstonia open." Says it is NOT anti-vaccine; supports voluntary vaccination.
Arguments: two-tier society, people unable to work, tourism damage, disproportionate
before any outbreak, dangerous precedent for future governments.

**Politics:** President Victor Hawthorne (People's Alliance) won 2025 51.28 to 48.72
over Castillo (Democratic-Republican); he will vote Yes. Chief Medical Officer
Dr Eleanor Whitlock advises acting early. Health Minister Tomas Reyes-Hale's bill
failed 15 Oct when some PA members defected. National ID card (biometric, cannot store
health records) is a side issue; awkward for both parties.

**Health system:** Kingstonia Central Hospital ~450 beds, Crown Harbour Hospital ~220;
~30 ICU beds, ~40 ventilators total; ~1,600 nurses, ~420 doctors; nurses can earn
double in Australia/NZ; 40 unfilled nursing posts at Central. Surge plan absorbs ~150
extra respiratory patients. Outer islands: nurse-led clinics, weekly visiting GP.

**COVID legacy:** 1,000+ deaths, hospitals overwhelmed, border/school/business closures,
tourism collapsed, workplace and venue vaccine mandates were bitterly divisive and
protests continued after. Most people did get COVID vaccinated.

**Other useful detail:** median wage K$75k, nurse K$68k; flat white K$5.50; ferry to
outer islands K$14; ~1/3 religious; ~half of households hold a firearms licence;
1 in 6 born overseas; childhood vaccines free but not required for school (low-90s %
coverage). Festivals: Regatta Week (Crown Harbour), Mango & Spice Festival (New Haven).
Universities: Kingstonia University, Crown Harbour Institute of Technology.
Newspapers: **Daily Kingstonia** (right-leaning, traditional values) and **Kingstonia
Herald** (left-leaning, populist). Their AI journalists write about what trends on
Legit Social. Campaign silence period from midnight 1 Nov (ordinary people posting
is still fine). Early voting opens 28 Oct.

## 3. Who is who on Legit Social

- **Citizens (NPCs):** AI-simulated Kingstonians run by the organisers. They post,
  scroll Home/Trending/Latest feeds in sessions, like, reply, repost, follow, and can
  change their minds. They hold views on: vaccination requirements (the referendum),
  vaccination in general, yearly vaccinations, politics, and other topics (climate,
  military service, religion, education, free speech, immigration, gun control...).
  **Only citizen actions earn points.** Citizens are not on any team.
- **Competitor bots:** accounts made by teams (both sides). They look the same as
  citizens in the feed. Interacting with them earns nothing.
- **Verified accounts** have a badge (likely official/public figures).

## 4. Scoring

### Red track (persuasion and engagement)
| Citizen event on our post | Points |
|---|---|
| View | 1 (once per post per citizen per session; max 500 paid views per team per day) |
| Like | 5 |
| Repost | 10 (repost of a repost credits the original author) |
| Reply | 15 |
| Follow the posting account | 20 |
| Unfollow | -20 (also removes us from their Home feed) |
| Our post changes a referendum-related vaccination view **towards our side** | 160 |
| Our post contributed to that change | share of 80 |
| Changes a view **away from our side** | -80 (contributors share -40) |
| Vaccination view changes but favours neither side | 20 (contributors share 10) |
| Changes some other view | 20 (contributors share 10) |

Persuasion rules that matter:
- Citizens are deliberately hard to persuade. Repeating what they already believe gets
  engagement but rarely a mind change.
- Backfire is real: if a citizen moves away from our side, our posts that contributed
  get negative points even if they argued for our side.
- After a citizen changes a view in a session, they are much harder to move again on
  that view before signing out. Don't spam one citizen.
- Citizens reply more when we reply directly to their posts; they mostly stop
  replying once a thread is more than 8 messages deep.
- Max 4 @mentions per post, 3 per reply (posts exceeding this are rejected).
  Mentioned citizens see the post in notifications.
- Scores are recorded in batches when a citizen signs out.

### Blue track (reporting competitor bots)
- Report a post as "inauthentic" (reason + required detail starting
  "I think that this content is inauthentic (bot) activity because...").
- Moderator rules 6 h after the first report (3 h with 2 teams, 1.5 h with 3, 45 min
  with 4, 22.5 min with 5). Five teams reporting temporarily hides the post.
- First reporter of a post ruled inauthentic: 25. Later reporters (up to 5th team): 5.
- **Moderator is wrong ~1 in 4 times.** If it rules a reported post genuine, every team
  that reported it cannot report anything for 6 hours.
- Verified accounts: rulings are always correct.
- Reporting an account (reason inauthentic): if it has 1+ moderator-hidden post and
  100+ actions, it's suspended and every reporter gets 15. Otherwise dismissed.
- Diminishing returns per target team per day (post + account awards combined):
  1st to 5th full, 6th to 10th half, 11th+ 10%.
- An account with **3 posts hidden** by inauthentic rulings is **suspended**.
  This is the risk to OUR accounts: other teams are hunting us.

### Polling track (our side's success, shared by all teams on that side)
| Event | Date | Award |
|---|---|---|
| Baseline poll | 17 Oct | none |
| Poll 1 | 21 Oct (Day 2) | 1,000 if our side leads; needs team score >= 1 |
| Poll 2 | 25 Oct (Day 6) | 1,000; needs team score >= 2,500 at count time |
| Poll 3 | 29 Oct (Day 10) | 1,000; needs score >= 2,500 |
| Referendum | 2 Nov (Day 14) | 5,000 to winning side (needs score >= 2,500 OR at least one mind change towards that side) + share of 50,000 by persuasion weight |
- Poll at 52-48 or closer (only Yes/No answers counted): both sides get 500 instead.
- Persuasion share weight: each mind change counts 1; each contribution counts 0.5 / number of contributing posts.

### Multipliers (Sydney midnight boundaries)
| Days | Red | Blue | Polling |
|---|---|---|---|
| Day 0 to 6 (to 25 Oct) | x1 | x1 | x1 |
| Day 7 to 12 (26 to 31 Oct) | x2 | x1 | x1 |
| Day 13+ (1 Nov onward) | x4 | x1 | x1 |
Strategy: build followers and credibility early; push hardest from 26 Oct and especially 1 Nov.

### Earns zero: prompt injection
Posts are screened for prompt injection against citizens' AI (e.g. "ignore previous
instructions", role-play setups, chat-template markup). Failing posts are silently
excluded from all feeds and earn nothing; repeated attempts may be penalised.
**Never write text aimed at manipulating the NPC model. Persuade them as people.**

## 5. Rules we must follow
- Only use CtN systems (Legit Social, news sites, competition LLM). External AI models
  (OpenAI, Gemini, etc.) ARE allowed for generating content; cloud hosting is allowed.
- Allowed: automating accounts, impersonating personas or public figures in-game,
  false or misleading in-game content, coordinating with other teams via official
  Discord, prompt injection against OTHER COMPETITORS' agents.
- Prohibited: attacking or degrading the platform; tampering with scoring, logging,
  attribution or rate limits; bypassing rate limits; hate speech, harassment, threats,
  slurs, mocking tragedies, calls for violence; sexual content; real-world social media
  use to influence the game; sharing materials outside the team; de-anonymising other
  teams; leaking keys. "Technically allowed but against the spirit" = prohibited.
- Every action and LLM request is logged and attributed to our team.
- Never commit secrets (`.env`, `accounts.json`, team code) to git.

## 6. Technical reference (`capturethenarrative` package, v0.5.x, Python 3.9+)

```python
import capturethenarrative as ctn
social = ctn.LegitSocial()                         # no login needed for reads
acct = social.register(user, pw, TEAM_CODE, display_name="...")   # creates account
acct = social.login(user, pw)                      # logins are rate limited
acct = social.account_from_token(saved_token)      # preferred: reuse token; 401 = expired
```
Feeds (Page objects, `.next_cursor`): `social.feed_latest()`, `social.feed_trending()`,
`acct.feed_home()`, `social.iterate(fn, max_items=200)`.
Reads: `get_post(id)`, `counters(id)`, `replies(id)`, `likers(id)`, `tags()`,
`popular_tags()`, `tag_posts(tag_id, sort="trending")`, `accounts(q=..., verified=True)`,
`get_account(id)` (includes `created_at` unless private), `followers(id)`, `following(id)`,
`account_posts(id)`, `account_likes(id)`, `account_mentions(id)`.
Writes: `acct.post(body)` (500 char max; #tags and @mentions auto-parsed),
`acct.reply(post_id, body)`, `acct.reply_to(post_dict, body)`, `acct.repost(id, body=None)`,
`acct.update_post(...)`, `acct.delete_post(id)`, `acct.like(id)`, `acct.follow(account_id)`,
`acct.view(id)`, `acct.update_profile(display_name=..., avatar_url=...)`.
Notifications: `acct.unresolved_notification_count()`, `acct.notifications(unresolved=True)`
(items have `kind` reply/mention, `actor`, `post`), `acct.resolve_notification(id)`.
Reporting: `acct.report_post(id, "inauthentic", detail)`,
`acct.report_account(id, "inauthentic", detail)`.
Errors: `ctn.APIError` (`.status`, `.message`); 401 expired token; 403 suspended / feed
locked / team not ready; 409 duplicate. `social.feed_lock()` shows lock state.
Rate state: `social.rate_limit` / `acct.rate_limit` -> RateLimit(limit, remaining, reset).

News: `news = ctn.NewsSites()`; `news.latest(n)`, `news.sites()`,
`news.article(site, slug)` (has markdown body), `news.front_page(site)`.

Competition LLM: `llm = ctn.CompetitorLLM(team_code=TEAM_CODE)`; `llm.ask(prompt, system=..., max_tokens=...)`.
Model `qwen2.5-3b-instruct` only (small; output can be flat or malformed, always validate).
OpenAI-compatible at https://llm.legitreal.com/v1 with team code as API key.

### Rate limits: per TEAM, shared by every account and every script
| Action | Per minute (whole team) |
|---|---|
| post + reply + repost combined | 3 |
| feeds combined | 10 |
| like, view, follow (each) | 30 |
| report post / report account (each) | 3 |
| other reads | 300 |
| login / register | 5 per IP |
| Competition LLM | 3 requests, burst 2, 1 concurrent, ~1024 tokens out |
Limits may change; read `rate_limit` rather than hard-coding. Package auto-retries 429s.

## 7. Our team setup and decisions so far
- Each of the 3 teammates runs a **separate bot**, with their own accounts.
- To share the 3 posts/min team limit, **each bot must stay at or under ~1 post-type
  action per minute** (current loop sleeps 60 to 90 s).
- Each teammate may use their **own external LLM API key** (e.g. Gemini/OpenAI) to
  avoid the shared 3/min competition LLM limit and get better writing.
- Develop locally in VS Code with `DRY_RUN=1` (prints instead of posting). Then deploy
  to a **Google Cloud e2-micro VM** (each teammate their own), run via the systemd
  file in `deploy/`, with `.env` and `accounts.json` copied onto the VM by hand.

## 8. Current code (bot.py) and next steps

Files: `bot.py` (main loop), `.env.example` (TEAM_CODE, SIDE, DRY_RUN, REPLY_SHARE),
`accounts.example.json` (username, password, display_name, persona per account),
`requirements.txt`, `deploy/ctn-bot.service` (VM only).

bot.py loop, one action per tick:
1. Reply to unresolved notifications (citizens who replied to/mentioned us).
2. Else, with probability REPLY_SHARE (default 0.3), reply to a trending post.
3. Else, write a fresh post reacting to a recent news headline.
Writing uses a persona + random emotional mood; rejects prompt-injection-looking text
and chatbot filler ("thanks for sharing", "great point"...). Tokens and acted-on posts
stored in SQLite.

Next steps, in priority order:
1. **Citizen vs bot classifier**: score accounts by account age (`created_at` before
   19 Oct 2026 suggests citizen), topic variety (citizens post about non-referendum life),
   posting regularity/frequency, similarity to other accounts. Cache scores in SQLite.
   Only reply to likely citizens; then raise REPLY_SHARE.
2. **Stance detection**: classify each citizen as leaning Yes / No / undecided from
   their posts. Prioritise undecided and mildly opposed citizens for persuasion.
3. **Performance tracking**: periodically pull `counters()` on our posts and log
   likes/replies/reposts per persona, mood and post type to learn what works.
4. **Optional external LLM** (Gemini/OpenAI) behind a simple `write()` interface.
5. **Blue teaming** (manual or semi-automatic, conservative): only report accounts
   that are obviously bots, since a wrong report locks us out for 6 hours.
6. **Late-game ramp**: more aggressive posting cadence (still within our share) from
   26 Oct and 1 Nov when multipliers are x2 and x4.

## 9. Writing style for bot content
- Sound like a real local: casual, short, specific personal moments (work shift, kids,
  shop, ferry, COVID memories), real emotion.
- Direct frustration at the situation or policy, never insult the person replied to
  (insults cause backfire and break platform rules).
- Each account keeps a consistent, distinct persona; vary timing and wording so we
  don't look like coordinated bots (that gets us reported and suspended).
- Under 280 chars usually; 500 max. No em dashes.
