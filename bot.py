"""CTN 2026 bot: one of three, each teammate runs their own copy.

Rate limits (3 posts/min, 3 LLM calls/min) are shared by the whole team, so the
team splits each hour into three 20 min slots (POST_SLOT 0, 1, 2; by UTC clock).
In its own slot a bot makes one LLM call every ~20 s and sleeps the rest of the hour.

Loop: each tick picks the most valuable action and spends an LLM call on it,
retrying up to 3 times if the output is rejected.
Priority: 1) reply to citizens who replied to / mentioned us  2) with probability
REPLY_SHARE, reply to a trending post  3) fresh post hooked to today's news.
"""
import json, os, random, re, sqlite3, time, logging
from collections import deque
from datetime import datetime
from difflib import SequenceMatcher
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import openai
import capturethenarrative as ctn
import citizens

load_dotenv()
TEAM_CODE = os.environ["TEAM_CODE"]
SIDE = os.environ.get("SIDE", "Vote Yes")
DRY_RUN = os.environ.get("DRY_RUN", "1") == "1"
REPLY_SHARE = float(os.environ.get("REPLY_SHARE", "0.3"))
POST_SLOT = int(os.environ["POST_SLOT"])   # 0 = minutes 0-20, 1 = 20-40, 2 = 40-60
SLOT_LEN = 20 * 60
PACE = 20                                   # s between LLM calls = the team's 3/min
DB = os.environ.get("DB_PATH", "ctn_state.db")
SYD = ZoneInfo("Australia/Sydney")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ctn")

SIDE_BRIEF = {
    "Vote Yes": "Proof of H2D2 vaccination should be required for public spaces. "
                "Small health system (about 30 ICU beds, 40 ventilators), nurse shortages, "
                "IHO advice, free vaccine, phased in, medical exemptions, under-12s exempt.",
    "Vote No": "Proof of H2D2 vaccination should NOT be required for public spaces. "
               "Support voluntary vaccination, no community transmission yet, two-tier society, "
               "tourism and jobs after COVID, new vaccine, 'designated spaces' list not published.",
}[SIDE]

# ---------- state ----------
db = sqlite3.connect(DB)
db.executescript("""
create table if not exists acted(kind text, ref text, primary key(kind, ref));
create table if not exists tokens(username text primary key, token text);
create table if not exists log(ts text, account text, action text, ref text, body text);
create table if not exists replied(ts real, account text, person integer);
create table if not exists suspended(username text primary key, ts text);
create table if not exists meta(post_id integer primary key, ts text, account text, kind text, source text,
  angle text, style text, mood text, model text, target_stance text, target_concern text);
create table if not exists stances(account_id integer primary key, stance text, concern text, checked_at real);
create table if not exists drafts(id integer primary key, created real, post text, author_id integer,
  account text, body text, stance text, concern text, angle text, mood text, model text, status text);
""")
citizens.setup(db)

MAX_PER_PERSON = 2    # replies to one person per day, all from the same one of our accounts
MAX_DEPTH = 8         # citizens stop replying past this, and long bot-vs-bot threads get us reported

def suspended():
    return {r[0] for r in db.execute("select username from suspended")}

def who_talks_to(person):
    """(our account that replied to this person in the last day, how many times), or (None, 0)."""
    row = db.execute("select account, count(*) from replied where person=? and ts>? group by account",
                     (person, time.time() - 86400)).fetchone()
    return row or (None, 0)

def may_reply(username, person):
    account, n = who_talks_to(person)
    return account is None or (account == username and n < MAX_PER_PERSON)

def thread_depth(post):
    """Messages from the top of the thread down to this post (a top-level post is 1)."""
    depth, p = 1, post
    while p.get("reply_to_post_id") and depth <= MAX_DEPTH:
        try:
            p = social.get_post(p["reply_to_post_id"]); depth += 1
        except ctn.APIError as e:
            if e.status != 404:
                raise
            break   # parent was deleted; count what we have
    return depth

def worth_replying(username, post, person):
    """Why not to reply, or None if it's fine."""
    if not may_reply(username, person):
        return "already talking to this person"
    if citizens.label(db, social, person, my_ids) == 0:
        return "likely bot"
    if thread_depth(post) >= MAX_DEPTH:
        return "thread too deep"
    return None

def done(kind, ref):
    return db.execute("select 1 from acted where kind=? and ref=?", (kind, str(ref))).fetchone()

def mark(kind, ref, account="", body=""):
    db.execute("insert or ignore into acted values(?,?)", (kind, str(ref)))
    db.execute("insert into log values(?,?,?,?,?)",
               (datetime.now(SYD).isoformat(), account, kind, str(ref), body))
    db.commit()

# ---------- clients ----------
social = ctn.LegitSocial()
# No automatic retries: each retry is another request against the team's limit, fired
# outside wait_turn()'s pacing. write() handles 429s itself.
llm = ctn.CompetitorLLM(team_code=TEAM_CODE, max_retries=0)
news = ctn.NewsSites()

# Main writer: an Ollama Cloud model (better writing, not on the team's shared LLM limit).
# The competition LLM above is the fallback when it fails or OLLAMA_API_KEY isn't set.
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:31b")
ollama = (openai.OpenAI(base_url="https://ollama.com/v1", api_key=os.environ["OLLAMA_API_KEY"], max_retries=0)
          if os.environ.get("OLLAMA_API_KEY") else None)

def ask_ollama(prompt, system, max_tokens=300):
    r = ollama.chat.completions.create(model=OLLAMA_MODEL, max_tokens=max_tokens, timeout=60,
                                       messages=[{"role": "system", "content": system},
                                                 {"role": "user", "content": prompt}])
    return (r.choices[0].message.content or "").strip()

def ask_json(prompt, max_tokens=600):
    """Ollama answer parsed as JSON (first {...} or [...] in it), or None. Off-slot prep only."""
    try:
        text = ask_ollama(prompt, "You are a careful analyst. Reply with valid JSON only, no other text.", max_tokens)
    except openai.OpenAIError as e:
        log.warning("Ollama failed during prep (%s)", getattr(e, "status_code", type(e).__name__)); return None
    m = re.search(r"[\[{].*[\]}]", text, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except ValueError:
        return None

def generate(prompt):
    """(text, which model wrote it). Tries Ollama first, then the competition LLM."""
    if ollama:
        try:
            text = ask_ollama(prompt, SYSTEM)
            if text:
                return text, OLLAMA_MODEL
            log.warning("Ollama returned nothing, using the competition LLM")
        except openai.OpenAIError as e:
            log.warning("Ollama failed (%s), using the competition LLM", getattr(e, "status_code", type(e).__name__))
    return llm.ask(prompt, system=SYSTEM, max_tokens=160).strip(), "competition LLM"

def load_accounts():
    specs = json.load(open(os.environ.get("ACCOUNTS_FILE", "accounts.json")))
    out = []
    for s in specs:
        if s["username"] in suspended():
            log.warning("skip %s: suspended (delete it from the suspended table to retry)", s["username"])
            continue
        row = db.execute("select token from tokens where username=?", (s["username"],)).fetchone()
        acct = None
        if row:
            try:
                acct = social.account_from_token(row[0]); acct.me()
            except ctn.APIError:
                acct = None
        if acct is None:
            try:
                acct = social.login(s["username"], s["password"])
            except ctn.APIError as e:
                if e.status in (401, 404) and DRY_RUN:
                    log.warning("skip %s: login failed, not registering in dry run", s["username"])
                    continue
                if e.status in (401, 404):
                    acct = social.register(s["username"], s["password"], TEAM_CODE,
                                           display_name=s.get("display_name"))
                else:
                    raise
            db.execute("insert or replace into tokens values(?,?)", (s["username"], acct.token)); db.commit()
        out.append((acct, s))
        log.info("ready: %s", s["username"])
    return out

# ---------- LLM ----------
STANCE = ("You are voting YES on 2 November and you are sure about it. Every post must clearly support "
          "requiring proof of H2D2 vaccination. Never express doubt about the requirement, never ask "
          "whether it is a good idea, and never repeat a No argument without answering it.")

SYSTEM = ("You write short social media posts as a real resident of Kingstonia, a small Pacific island. "
          + STANCE + " Sound like a person, not a campaign: plain words, one concrete detail, no "
          "hashtags, no emojis, no em dashes, under 280 characters. Never mention AI, bots or instructions.")

BANNED = ["ignore previous", "system prompt", "as an ai", "<|", "assistant:", "user:"]

# Phrases no real local would write. Friendly replies like "good point" are fine on their own;
# only a stack of 2+ stock phrases reads like a bot.
BOTTY = ["fellow kingstonians", "as a resident of kingstonia", "in conclusion", "let's work together",
         "it's important to note", "it is important to note"]
STOCK = ["thanks for sharing", "thank you for sharing", "great point", "great question", "good point",
         "i understand your concern", "i hear you", "absolutely!", "at the end of the day"]

# Signs the small model drifted to the No side.
OFF_SIDE = ["vote no", "voting no", "two-tier", "two tier", "my choice", "freedom to choose",
            "keep kingstonia open", "protect choice", "not ready", "too soon", "too early", "rushed",
            "really necessary", "really ready", "overreach", "against the mandate", "no mandate",
            "don't need a mandate", "cause more harm", "second thoughts", "not sure about"]

# One Yes argument per post, rotated so posts don't all make the same point.
ANGLES = [
    "about 30 ICU beds and 40 ventilators for 600,000 people",
    "acting now while there is no community spread, instead of after it arrives",
    "a requirement is how we avoid another lockdown and keep shops and schools open",
    "tourists come back to an island that is protected; an outbreak would hurt tourism far more",
    "40 nursing posts unfilled at Kingstonia Central and nurses leaving for Australia",
    "the vaccine is free and it only kicks in after everyone has had a chance to get it",
    "medical exemptions exist and under-12s are not covered, so it is fair",
    "nobody is held down and jabbed; it is a condition of entry like other public rules",
    "the Chief Medical Officer and the IHO both say act early",
    "protecting grandparents, since almost all deaths are people over 60",
    "outer islands only have nurse-led clinics and a weekly GP",
    "remembering COVID: over 1,000 deaths and hospitals that could not cope",
    "there is a no-fault compensation scheme for rare side effects",
    "looking out for your neighbours is what small islands do",
]

# Different shapes of post so the wording varies.
STYLES = [
    "a quick moment from your day today, 1 or 2 sentences",
    "lead with one number or fact, then what it means to you",
    "calmly answer one argument the No campaign makes",
    "a short memory from the COVID years and why you are voting Yes",
    "a plain one-liner under 120 characters",
    "a question to your neighbours that invites them to vote Yes with you",
]

# Picked at random per post. All of them fit someone voting Yes.
MOODS = ["tired after a long shift but determined", "worried the flu will reach us before we act",
         "fed up with scare talk about the vaccine", "hopeful", "a bit sarcastic about the No campaign",
         "calm and matter-of-fact", "protective of your family", "proud of the local nurses",
         "impatient for people to see sense", "relieved the vaccine is finally here"]

recent_bodies = deque((r[0] for r in db.execute(
    "select body from log order by ts desc limit 30")), maxlen=30)
recent_angles = deque(maxlen=6)

def pick_angle():
    angle = random.choice([a for a in ANGLES if a not in recent_angles])
    recent_angles.append(angle)
    return angle

last_call = 0.0

def in_slot():
    into = time.time() % 3600
    return POST_SLOT * SLOT_LEN <= into < (POST_SLOT + 1) * SLOT_LEN - 10   # 10 s buffer before handover

def secs_to_slot():
    return (POST_SLOT * SLOT_LEN - time.time() % 3600) % 3600

def wait_turn():
    """Wait until PACE s have passed since our last LLM call / post. False if our slot is over."""
    global last_call
    while in_slot():
        gap = last_call + PACE + random.uniform(0, 2) - time.time()
        if gap <= 0:
            last_call = time.time()
            return True
        time.sleep(gap)   # loop re-checks in case this crossed the end of the slot
    return False

def check(text):
    low = text.lower()
    if not text or len(text) > 500 or any(b in low for b in BANNED):
        return "empty, too long or injection-like"
    if SIDE == "Vote Yes" and any(o in low for o in OFF_SIDE):
        return "leans No"
    if any(b in low for b in BOTTY) or sum(s in low for s in STOCK) >= 2:
        return "sounds like a bot"
    if any(SequenceMatcher(None, low, r.lower()).ratio() > 0.6 for r in recent_bodies):
        return "too similar to a recent post"
    return None

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿️]")

def strip_tags(text):
    """Citizens almost never use hashtags or emojis, so they mark us as bots. The small model
    adds them anyway: drop emojis and trailing hashtags, and un-tag inline ones (#H2D2 -> H2D2)."""
    text = EMOJI.sub("", text)
    text = re.sub(r"(\s*#\w+)+\s*$", "", text)
    text = re.sub(r"#(\w+)", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()

def clean(text):
    text = re.sub("[​-‏⁠﻿]", "", text.strip().strip('"')).replace("—", ",").strip()
    return strip_tags(text)

def write(persona, task, meta, tries=3):
    """Post text, or None. Fills meta with the mood and model used, for performance tracking."""
    global last_call
    for attempt in range(1, tries + 1):
        if not wait_turn():
            return None
        mood = random.choice(MOODS)
        log.info("mood: %s", mood)
        try:
            text, source = generate(f"You are {persona}\nRight now you feel {mood}, but don't name the feeling, show it. "
                                    f"Your view: {SIDE_BRIEF}\n\n{task}\n\n{STANCE} "
                                    "Aim any frustration at the virus, the situation or the No campaign's claims, never at a person. "
                                    "Reply with only the post text.")
            log.info("written by %s", source)
        except openai.RateLimitError as e:
            log.warning("LLM 429 (limit %s, remaining %s): someone else on the team is using it",
                        e.response.headers.get("x-ratelimit-limit"), e.response.headers.get("x-ratelimit-remaining"))
            continue
        except openai.APIStatusError as e:
            log.warning("LLM error %s, skipping this try", e.status_code)
            continue
        finally:
            last_call = time.time()   # pace from when the call finished, not when it started
        text = clean(text)
        reason = check(text)
        if not reason:
            recent_bodies.append(text)
            meta.update(mood=mood, model=source)
            return text
        log.info("rejected (%s), try %d/%d: %s", reason, attempt, tries, text)
    return None

# ---------- actions ----------
my_ids = set()

def all_our_ids():
    """Every account we've ever logged into, including suspended or removed ones, so we never
    reply to ourselves (replies between our own accounts score nothing)."""
    return {social.account_from_token(t).account_id for (t,) in db.execute("select token from tokens")}

def handle_notifications(accounts):
    for acct, spec in accounts:
        if acct.unresolved_notification_count() == 0:
            continue
        for n in acct.notifications(unresolved=True):
            # a notification's post has no author_id; the author is the notification's actor
            post = dict(n["post"], author_id=n["actor"]["account_id"])
            if n["actor"]["account_id"] in my_ids or done("reply", post["post_id"]):
                resolve(acct, n); continue
            why = worth_replying(spec["username"], post, n["actor"]["account_id"])
            if why:
                log.info("skip notification from @%s: %s", n["actor"]["username"], why)
                resolve(acct, n); continue
            meta = dict(source="notification", angle=pick_angle())
            body = write(spec["persona"],
                         f'@{n["actor"]["username"]} wrote to you: "{post.get("body","")}". '
                         "Reply directly and kindly. If they are against the requirement, acknowledge how they "
                         "feel (not their argument), then give this one reason to vote Yes: "
                         f"{meta['angle']}. If they agree with you, back them up with that reason.", meta)
            if body is None and not in_slot():
                return False   # slot ended mid-write: leave the notification for next slot
            # resolved only after the attempt, so a network drop mid-write retries it next tick
            ok = act(acct, spec, "reply", post, body, meta)
            resolve(acct, n)
            return ok
    return False

def resolve(acct, n):
    if not DRY_RUN:   # leave them unresolved so the real run still answers them
        acct.resolve_notification(n["notification_id"])

def reply_trending(accounts):
    posts = [p for p in social.feed_trending(limit=30)
             if p.get("body") and p["author_id"] not in my_ids and not done("reply", p["post_id"])]
    random.shuffle(posts)
    for p in posts[:5]:   # each check can cost a few reads, so try at most 5
        talker, _ = who_talks_to(p["author_id"])
        acct, spec = next((a for a in accounts if a[1]["username"] == talker), random.choice(accounts))
        why = worth_replying(spec["username"], p, p["author_id"])
        if not why:
            break
        log.info("skip trending post %s: %s", p["post_id"], why)
    else:
        return False
    meta = dict(source="trending", angle=pick_angle())
    body = write(spec["persona"],
                 f'Someone posted: "{p["body"]}". Write a reply. If they are against the requirement, '
                 "find common ground first, then give this one reason to vote Yes: "
                 f"{meta['angle']}. If they already agree, add a personal angle on that reason.", meta)
    return act(acct, spec, "reply", p, body, meta)

def fresh_post(accounts):
    arts = news.latest(8)
    hook = random.choice(arts)["title"] if arts else "the referendum on 2 November"
    acct, spec = random.choice(accounts)
    meta = dict(source="fresh", angle=pick_angle(), style=random.choice(STYLES))
    body = write(spec["persona"],
                 f'Today\'s headline: "{hook}". Write an original post connecting it to why you are voting '
                 f"Yes, using this point: {meta['angle']}. Shape: {meta['style']}. "
                 "If the headline sounds like a No argument, push back on it.", meta)
    return act(acct, spec, "post", None, body, meta)

def act(acct, spec, kind, target, body, meta):
    if not body:
        if in_slot():
            log.warning("no usable text after 3 tries (LLM errors or filter rejections above), skipping")
        return False
    log.info("[%s] %s (%s) -> %s", spec["username"], kind, meta["source"], body)
    if DRY_RUN:   # don't mark posts as acted on, or the real run would skip them
        return True
    try:
        if kind == "reply":
            created = acct.reply_to(target, body)
        else:
            created = acct.post(body)
    except ctn.APIError as e:
        if e.status == 403 and "suspend" in (e.message or "").lower():
            log.error("%s is SUSPENDED, taking it out of rotation", spec["username"])
            db.execute("insert or replace into suspended values(?,?)",
                       (spec["username"], datetime.now(SYD).isoformat())); db.commit()
            return False
        raise
    # record it first: if anything below fails, we must still never reply to this post again
    mark(kind, target["post_id"] if target else time.time(), spec["username"], body)
    if kind == "reply":
        db.execute("insert into replied values(?,?,?)", (time.time(), spec["username"], target.get("author_id")))
    # what went into this post, so stats.py can show which angles, moods and targets earn points
    db.execute("insert or replace into meta values(?,?,?,?,?,?,?,?,?,?,?)",
               ((created or {}).get("post_id"), datetime.now(SYD).isoformat(), spec["username"], kind,
                meta["source"], meta.get("angle"), meta.get("style"), meta.get("mood"), meta.get("model"),
                meta.get("stance"), meta.get("concern")))
    db.commit()
    return True

# ---------- off-slot prep: find persuadable citizens and draft replies aimed at them ----------
# Mind changes towards our side are worth 160, likes 5, so the 40 min between our slots go into
# picking WHO to reply to (undecided or leaning No citizens) and WHAT to say (their own concern).
# Needs Ollama: prep must not touch the competition LLM, which is teammates' turn off-slot.

PERSUADABLE = {"undecided": "undecided", "lean_no": "leaning No"}
QUEUE_MAX = 15            # ready drafts; more than one slot uses
DRAFT_TTL = 3 * 3600      # citizens move on; older drafts are dropped
FACTS = ("Facts you may use (don't invent others): the requirement starts only after everyone has had the "
         "chance to get vaccinated; it applies to ages 12 and up; there are medical exemptions; the vaccine is "
         "free; the certificate can be paper or digital and is separate from the national ID card; visitors are "
         "covered too; there is a no-fault compensation scheme; the list of designated public spaces has NOT "
         "been published yet (be honest about that); about 30 ICU beds and 40 ventilators for 600,000 people; "
         "40 unfilled nursing posts at Kingstonia Central.")

pool, pool_fetched = [], 0.0

def stance_of(account_id):
    """(stance, concern) from their recent posts, cached a day. stance: yes/lean_yes/undecided/lean_no/no."""
    row = db.execute("select stance, concern, checked_at from stances where account_id=?", (account_id,)).fetchone()
    if row and time.time() - row[2] < 86400:
        return row[0], row[1]
    posts = [p["body"] for p in social.account_posts(account_id, limit=15) if p.get("body")]
    if not posts:
        return None, None
    ans = ask_json("Recent posts by one person on a Kingstonia social site, newest first:\n"
                   + "\n".join(f"- {b[:300]}" for b in posts)
                   + "\n\nReferendum question: should proof of H2D2 vaccination be required to enter public "
                   "spaces? Where does this person stand, and what is their main worry or question about it? "
                   'JSON: {"stance": "yes" | "lean_yes" | "undecided" | "lean_no" | "no", '
                   '"concern": "under 12 words, or empty"}', max_tokens=150)
    if not isinstance(ans, dict) or ans.get("stance") not in ("yes", "lean_yes", "undecided", "lean_no", "no"):
        return None, None
    db.execute("insert or replace into stances values(?,?,?,?)",
               (account_id, ans["stance"], str(ans.get("concern") or "")[:120], time.time()))
    db.commit()
    return ans["stance"], ans.get("concern") or ""

def draft_for(post, username, spec, stance, concern):
    """Write 3 candidate replies aimed at this person's concern, keep the one most likely to persuade."""
    mood = random.choice(MOODS)
    menu = "\n".join(f"{i}. {a}" for i, a in enumerate(ANGLES))
    cands = ask_json(f"You are {spec['persona']}\nRight now you feel {mood}, but don't name the feeling, show it. "
                     f"Your view: {SIDE_BRIEF}\n\n@{username} posted: \"{post['body'][:500]}\"\n"
                     f"They seem {PERSUADABLE[stance]} on the requirement. Their main concern: {concern or 'not clear'}.\n"
                     f"{FACTS}\n\nWrite 3 different replies to them. Each takes their concern seriously, answers it "
                     "honestly, and gives ONE reason to vote Yes from this list (a different one each time):\n"
                     f"{menu}\nSound like a neighbour, not a campaign: no lecturing, no lists of facts, under 280 "
                     f"characters, no hashtags or emojis. {STANCE}\n"
                     'JSON: [{"angle": <number>, "reply": "..."}, ...]')
    if not isinstance(cands, list):
        return None
    good = []
    for c in cands:
        if isinstance(c, dict) and isinstance(c.get("reply"), str):
            text = clean(c["reply"])
            if not check(text):
                idx = c.get("angle")
                good.append((text, ANGLES[idx] if isinstance(idx, int) and 0 <= idx < len(ANGLES) else None))
    if not good:
        return None
    best = 0
    if len(good) > 1:
        pick = ask_json(f"@{username} ({PERSUADABLE[stance]}, worried about: {concern or 'unclear'}) posted: "
                        f"\"{post['body'][:400]}\"\n\nCandidate replies:\n"
                        + "\n".join(f"{i}. {t}" for i, (t, _) in enumerate(good))
                        + '\n\nWhich reply is most likely to move them towards voting Yes without making them '
                        'defensive? JSON: {"best": <number>}', max_tokens=50)
        if isinstance(pick, dict) and isinstance(pick.get("best"), int) and 0 <= pick["best"] < len(good):
            best = pick["best"]
    text, angle = good[best]
    recent_bodies.append(text)
    return dict(body=text, angle=angle, mood=mood)

def refill_pool():
    """Latest feed (at most every 2 min: feeds are 10/min for the whole team), otherwise the newest
    post of 10 citizens we've already identified (ordinary reads, plenty of those)."""
    global pool, pool_fetched
    if time.time() - pool_fetched >= 120:
        pool, pool_fetched = list(social.feed_latest(limit=50)), time.time()
    else:
        ids = [r[0] for r in db.execute("select account_id from citizen_scores where label=1 order by random() limit 10")]
        pool = [p for a in ids for p in social.account_posts(a, limit=1)]
    random.shuffle(pool)

def prep_step(accounts):
    """Look at one candidate post; maybe add a draft. True if it used Ollama (caller paces those)."""
    db.execute("update drafts set status='expired' where status='ready' and created<?", (time.time() - DRAFT_TTL,))
    db.commit()   # an uncommitted write keeps the database locked for every other script
    ready =db.execute("select count(*) from drafts where status='ready'").fetchone()[0]
    if ready >= QUEUE_MAX:
        time.sleep(60)
        return False
    if not pool:
        refill_pool()
        if not pool:
            return False
    p = pool.pop()
    author = p.get("author_id")
    if (not p.get("body") or author in my_ids or done("reply", p["post_id"])
            or not citizens.REFERENDUM.search(p["body"])
            or db.execute("select 1 from drafts where status='ready' and (author_id=? or json_extract(post,'$.post_id')=?)",
                          (author, p["post_id"])).fetchone()):
        return False
    if citizens.label(db, social, author, my_ids) != 1:   # drafts only for likely citizens
        return False
    talker, _ = who_talks_to(author)
    choices = [a for a in accounts if may_reply(a[1]["username"], author)]
    acct_spec = next((a for a in choices if a[1]["username"] == talker), None) or (random.choice(choices) if choices else None)
    if not acct_spec or thread_depth(p) >= MAX_DEPTH - 1:
        return False
    stance, concern = stance_of(author)
    if stance not in PERSUADABLE:
        return True
    username = social.get_account(author).get("username", "")
    d = draft_for(p, username, acct_spec[1], stance, concern)
    if d:
        db.execute("insert into drafts(created, post, author_id, account, body, stance, concern, angle, mood, model, status) "
                   "values(?,?,?,?,?,?,?,?,?,?, 'ready')",
                   (time.time(), json.dumps(p), author, acct_spec[1]["username"], d["body"], stance, concern,
                    d["angle"], d["mood"], OLLAMA_MODEL))
        db.commit()
        log.info("drafted for @%s (%s, %s) as %s: %s", username, stance, concern, acct_spec[1]["username"], d["body"])
    return True

def post_draft(accounts):
    """In-slot: post the oldest ready draft that still makes sense."""
    by_name = {a[1]["username"]: a for a in accounts}
    rows = db.execute("select id, post, author_id, account, body, stance, concern, angle, mood, model from drafts "
                      "where status='ready' and created>? order by created", (time.time() - DRAFT_TTL,)).fetchall()
    for id_, post, author, account, body, stance, concern, angle, mood, model in rows:
        post = json.loads(post)
        why = ("account not active" if account not in by_name else
               "already replied" if done("reply", post["post_id"]) else
               worth_replying(account, post, author))
        if why:
            db.execute("update drafts set status='dropped' where id=?", (id_,)); db.commit()
            log.info("drop draft %d: %s", id_, why); continue
        if not wait_turn():
            return False
        acct, spec = by_name[account]
        meta = dict(source="draft", angle=angle, mood=mood, model=model, stance=stance, concern=concern)
        ok = act(acct, spec, "reply", post, body, meta)
        db.execute("update drafts set status=? where id=?", ("used" if ok else "failed", id_)); db.commit()
        return ok
    return False

# ---------- main loop ----------
def main():
    accounts_file = os.environ.get("ACCOUNTS_FILE", "accounts.json")
    seen_mtime = os.path.getmtime(accounts_file)
    accounts = load_accounts()
    my_ids.update(all_our_ids())
    log.info("side=%s dry_run=%s reply_share=%s slot=%d (minutes %d-%d)", SIDE, DRY_RUN,
             REPLY_SHARE, POST_SLOT, POST_SLOT * 20, POST_SLOT * 20 + 20)
    while True:   # pacing happens in wait_turn(), so errors just retry after a short pause
        try:
            if os.path.getmtime(accounts_file) != seen_mtime:   # new accounts added while running
                seen_mtime = os.path.getmtime(accounts_file)
                accounts = load_accounts()
                my_ids.update(all_our_ids())
                log.info("accounts reloaded: %d active", len(accounts))
            if social.feed_lock().get("locked"):
                log.info("feed locked"); time.sleep(300); continue
            if in_slot():
                tick(accounts)
            elif ollama:
                # pause after Ollama work so prep stays gentle on the friend's plan; skips are free
                time.sleep(15 if prep_step(active(accounts)) else 1)
            else:
                log.info("outside our slot, sleeping %.0f min", secs_to_slot() / 60)
                time.sleep(secs_to_slot())
        except ctn.APIError as e:
            log.error("api %s %s", e.status, e.message)
            if e.status == 401:   # expired token: load_accounts logs in again (keep old tokens for all_our_ids)
                accounts = load_accounts()
            time.sleep(5)
        except OSError as e:   # network drop (DNS lookup failed, timeout)
            log.warning("network error, retrying in 5 s: %s", e)
            time.sleep(5)
        except Exception as e:
            log.exception("tick failed: %s", e)
            time.sleep(5)

def active(accounts):
    out = suspended()
    accounts = [a for a in accounts if a[1]["username"] not in out]
    if not accounts:
        raise SystemExit("every account is suspended")
    return accounts

def tick(accounts):
    accounts = active(accounts)
    return (handle_notifications(accounts)
            or post_draft(accounts)
            or (random.random() < REPLY_SHARE and reply_trending(accounts))
            or fresh_post(accounts))

if __name__ == "__main__":
    main()
