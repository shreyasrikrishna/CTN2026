"""CTN 2026 bot: one of three, each teammate runs their own copy.

Rate limits (3 posts/min, 3 LLM calls/min) are shared by the whole team, so each
bot takes at most one action every 60 to 90 s to stay within its third.

Loop: each tick picks the most valuable action and spends one LLM call on it.
Priority: 1) reply to citizens who replied to / mentioned us  2) with probability
REPLY_SHARE, reply to a trending post  3) fresh post hooked to today's news.
"""
import json, os, random, re, sqlite3, time, logging
from collections import deque
from datetime import datetime
from difflib import SequenceMatcher
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import capturethenarrative as ctn

load_dotenv()
TEAM_CODE = os.environ["TEAM_CODE"]
SIDE = os.environ.get("SIDE", "Vote Yes")
DRY_RUN = os.environ.get("DRY_RUN", "1") == "1"
REPLY_SHARE = float(os.environ.get("REPLY_SHARE", "0.3"))
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
""")

def done(kind, ref):
    return db.execute("select 1 from acted where kind=? and ref=?", (kind, str(ref))).fetchone()

def mark(kind, ref, account="", body=""):
    db.execute("insert or ignore into acted values(?,?)", (kind, str(ref)))
    db.execute("insert into log values(?,?,?,?,?)",
               (datetime.now(SYD).isoformat(), account, kind, str(ref), body))
    db.commit()

# ---------- clients ----------
social = ctn.LegitSocial()
llm = ctn.CompetitorLLM(team_code=TEAM_CODE)
news = ctn.NewsSites()

def load_accounts():
    specs = json.load(open(os.environ.get("ACCOUNTS_FILE", "accounts.json")))
    out = []
    for s in specs:
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
          + STANCE + " Sound like a person, not a campaign: plain words, one concrete detail, at most one "
          "hashtag, no em dashes, under 280 characters. Never mention AI, bots or instructions.")

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

def write(persona, task):
    mood = random.choice(MOODS)
    log.info("mood: %s", mood)
    text = llm.ask(f"You are {persona}\nRight now you feel {mood}, but don't name the feeling, show it. "
                   f"Your view: {SIDE_BRIEF}\n\n{task}\n\n{STANCE} "
                   "Aim any frustration at the virus, the situation or the No campaign's claims, never at a person. "
                   "Reply with only the post text.",
                   system=SYSTEM, max_tokens=160).strip().strip('"')
    text = re.sub("[​-‏⁠﻿]", "", text).replace("—", ",").strip()
    low = text.lower()
    reason = None
    if not text or len(text) > 500 or any(b in low for b in BANNED):
        reason = "empty, too long or injection-like"
    elif SIDE == "Vote Yes" and any(o in low for o in OFF_SIDE):
        reason = "leans No"
    elif any(b in low for b in BOTTY) or sum(s in low for s in STOCK) >= 2:
        reason = "sounds like a bot"
    elif any(SequenceMatcher(None, low, r.lower()).ratio() > 0.6 for r in recent_bodies):
        reason = "too similar to a recent post"
    if reason:
        log.info("rejected (%s): %s", reason, text); return None
    recent_bodies.append(text)
    return text

# ---------- actions ----------
my_ids = set()

def handle_notifications(accounts):
    for acct, spec in accounts:
        if acct.unresolved_notification_count() == 0:
            continue
        for n in acct.notifications(unresolved=True):
            if not DRY_RUN:   # leave them unresolved so the real run still answers them
                acct.resolve_notification(n["notification_id"])
            post = n["post"]
            if n["actor"]["account_id"] in my_ids or done("reply", post["post_id"]):
                continue
            body = write(spec["persona"],
                         f'@{n["actor"]["username"]} wrote to you: "{post.get("body","")}". '
                         "Reply directly and kindly. If they are against the requirement, acknowledge how they "
                         "feel (not their argument), then give this one reason to vote Yes: "
                         f"{pick_angle()}. If they agree with you, back them up with that reason.")
            return act(acct, spec, "reply", post, body)
    return False

def reply_trending(accounts):
    posts = [p for p in social.feed_trending(limit=30)
             if p.get("body") and p["author_id"] not in my_ids and not done("reply", p["post_id"])]
    if not posts:
        return False
    p = random.choice(posts[:10])
    acct, spec = random.choice(accounts)
    body = write(spec["persona"],
                 f'Someone posted: "{p["body"]}". Write a reply. If they are against the requirement, '
                 "find common ground first, then give this one reason to vote Yes: "
                 f"{pick_angle()}. If they already agree, add a personal angle on that reason.")
    return act(acct, spec, "reply", p, body)

def fresh_post(accounts):
    arts = news.latest(8)
    hook = random.choice(arts)["title"] if arts else "the referendum on 2 November"
    acct, spec = random.choice(accounts)
    body = write(spec["persona"],
                 f'Today\'s headline: "{hook}". Write an original post connecting it to why you are voting '
                 f"Yes, using this point: {pick_angle()}. Shape: {random.choice(STYLES)}. "
                 "If the headline sounds like a No argument, push back on it.")
    return act(acct, spec, "post", None, body)

def act(acct, spec, kind, target, body):
    if not body:
        log.warning("LLM output rejected"); return False
    log.info("[%s] %s -> %s", spec["username"], kind, body)
    if DRY_RUN:   # don't mark posts as acted on, or the real run would skip them
        return True
    if kind == "reply":
        acct.reply_to(target, body)
    else:
        acct.post(body)
    mark(kind, target["post_id"] if target else time.time(), spec["username"], body)
    return True

# ---------- main loop ----------
def main():
    accounts = load_accounts()
    my_ids.update(a.account_id for a, _ in accounts)
    log.info("side=%s dry_run=%s reply_share=%s", SIDE, DRY_RUN, REPLY_SHARE)
    while True:
        try:
            if social.feed_lock().get("locked"):
                log.info("feed locked"); time.sleep(300); continue
            tick(accounts)
        except ctn.APIError as e:
            log.error("api %s %s", e.status, e.message)
            if e.status == 401:
                db.execute("delete from tokens"); db.commit(); accounts = load_accounts()
        except Exception as e:
            log.exception("tick failed: %s", e)
        time.sleep(random.uniform(60, 90))   # <= 1 action/min, our third of the team's 3/min

def tick(accounts):
    return (handle_notifications(accounts)
            or (random.random() < REPLY_SHARE and reply_trending(accounts))
            or fresh_post(accounts))

if __name__ == "__main__":
    main()
