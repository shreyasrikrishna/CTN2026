"""Guess whether an account is a citizen (NPC, scores points) or a competitor bot (scores nothing).

The API doesn't say, and account age doesn't help (citizens keep being added during the
competition). What does separate them, from a sample of 45 accounts that engaged with us
on 21 Oct:
- competitor bots (small LLMs, like ours) put hashtags and emojis in most posts;
  citizens almost never do
- citizens' writing uses em dashes; competitor bots are usually told to strip them
- bot farms register in batches: several hashtag-heavy accounts created in the same hour

score() adds these up; label is 1 likely citizen, 0 likely bot, None not enough evidence.
Results are cached in SQLite for a day.
"""
import re, time
from datetime import datetime, timedelta, timezone

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
REFERENDUM = re.compile(r"h2d2|vaccin|vax|jab|mandate|referendum|\bvote|proof|certificate|dolphin flu", re.I)
FRESH = timedelta(days=1)
GAP = 0.4   # s between reads: "other reads" is 300/min for the whole team

def setup(db):
    db.execute("""create table if not exists citizen_scores(account_id integer primary key,
      username text, created_at text, posts int, tag_rate real, emoji_rate real, dash_rate real,
      off_topic real, score real, label int, checked_at text)""")
    db.commit()

def features(posts):
    bodies = [p.get("body") or "" for p in posts]
    n = len(bodies) or 1
    return dict(posts=len(bodies),
                tag_rate=sum("#" in b for b in bodies) / n,
                emoji_rate=sum(bool(EMOJI.search(b)) for b in bodies) / n,
                dash_rate=sum("—" in b for b in bodies) / n,
                off_topic=sum(not REFERENDUM.search(b) for b in bodies) / n)

def score(f):
    if f["posts"] < 3:
        return 0.0, None
    s = 0.0
    s += 1 if f["tag_rate"] < 0.1 else -1 if f["tag_rate"] < 0.3 else -2
    s -= 1 if f["emoji_rate"] >= 0.15 else 0
    s += 1 if f["dash_rate"] >= 0.05 else 0
    s += 0.5 if f["off_topic"] >= 0.3 else 0
    return s, 1 if s >= 1 else 0 if s <= -1 else None

def label(db, social, account_id, mine=()):
    """1 / 0 / None, from cache when it's under a day old."""
    if account_id in mine:
        return 0
    row = db.execute("select label, checked_at from citizen_scores where account_id=?", (account_id,)).fetchone()
    now = datetime.now(timezone.utc)
    if row and now - datetime.fromisoformat(row[1]) < FRESH:
        return row[0]
    try:
        time.sleep(GAP); acc = social.get_account(account_id)
        time.sleep(GAP); posts = list(social.account_posts(account_id, limit=50))
    except Exception:
        return row[0] if row else None
    f = features(posts)
    s, lab = score(f)
    db.execute("insert or replace into citizen_scores values(?,?,?,?,?,?,?,?,?,?,?)",
               (account_id, acc.get("username"), acc.get("created_at"), f["posts"], f["tag_rate"],
                f["emoji_rate"], f["dash_rate"], f["off_topic"], s, lab, now.isoformat()))
    db.commit()
    return lab

def farm_hours(db, min_size=3):
    """Hours (UTC) in which min_size+ hashtag-heavy accounts were registered: likely bot farms."""
    return [r[0] for r in db.execute(
        "select substr(created_at,1,13) h from citizen_scores where tag_rate >= 0.3 "
        "group by h having count(*) >= ?", (min_size,))]
