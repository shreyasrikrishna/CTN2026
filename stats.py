"""Per-bot performance report: engagement on our posts, split into likely citizens vs bots.

Only citizen actions score, and the API doesn't say who is a citizen, so citizens.py
guesses from how each account writes. Mind-change points (the big 160s) aren't visible
here, so "est pts" is engagement only; the team's real score is in the activity CSV.

Run anytime, read-only: .venv/bin/python stats.py
Each run is saved to the stats table so the next run can show what changed.
"""
import os, sqlite3, time
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import capturethenarrative as ctn
import citizens

load_dotenv()
DB = os.environ.get("DB_PATH", "ctn_state.db")
GAP = 0.4                        # s between reads: "other reads" is 300/min for the whole team
SYD = ZoneInfo("Australia/Sydney")

db = sqlite3.connect(DB)
citizens.setup(db)
db.executescript("""
create table if not exists stats(ts text, account text, posts int, replies int, views int,
  likes int, citizen_likes int, replies_in int, citizen_replies int, reposts int,
  followers int, citizen_followers int, est_points int);
""")
social = ctn.LegitSocial()

def call(fn, *args, **kw):
    time.sleep(GAP)
    return fn(*args, **kw)

def pages(fn, *args):
    cursor = None
    while True:
        page = call(fn, *args, limit=50, cursor=cursor)
        yield from page
        cursor = page.next_cursor
        if not cursor:
            return

def citizen(account_id, mine):
    return citizens.label(db, social, account_id, mine)

def our_accounts():
    out = {}
    for username, token in db.execute("select username, token from tokens"):
        out[username] = social.account_from_token(token).account_id
    if not out:
        raise SystemExit("No bot accounts in the database yet. Run bot.py once first.")
    return out

def measure(username, account_id, mine, top, by_kind):
    t = dict(posts=0, replies=0, views=0, likes=0, citizen_likes=0, replies_in=0,
             citizen_replies=0, reposts=0, followers=0, citizen_followers=0)
    for p in pages(social.account_posts, account_id):
        c = call(social.counters, p["post_id"])
        kind = "posts" if p["kind"] == "post" else "replies"
        t[kind] += 1
        t["views"] += c["view_count"]; t["likes"] += c["like_count"]
        t["replies_in"] += c["reply_count"]; t["reposts"] += c["repost_count"]
        cl = sum(citizen(l["account_id"], mine) == 1 for l in pages(social.likers, p["post_id"])) \
            if c["like_count"] else 0
        cr = sum(r["author_id"] not in mine and citizen(r["author_id"], mine) == 1
                 for r in pages(social.replies, p["post_id"])) if c["reply_count"] else 0
        t["citizen_likes"] += cl; t["citizen_replies"] += cr
        pts = 5 * cl + 15 * cr + 10 * c["repost_count"]
        by_kind[kind][0] += 1; by_kind[kind][1] += pts
        per_post[p["post_id"]] = pts
        if pts:
            top.append((pts, username, p["kind"], cl, cr, c["repost_count"], p["body"]))
    for f in pages(social.followers, account_id):
        t["followers"] += 1
        t["citizen_followers"] += citizen(f["account_id"], mine) == 1
    # reposts have no "who" endpoint, so they're counted as if all were citizens
    t["est_points"] = (5 * t["citizen_likes"] + 15 * t["citizen_replies"] + 10 * t["reposts"]
                       + 20 * t["citizen_followers"] + t["views"])
    return t

per_post = {}   # post_id -> citizen engagement points, filled by measure()

def what_works(min_n=3):
    """Average citizen points per post, grouped by what bot.py recorded about each post in meta."""
    if not db.execute("select name from sqlite_master where name='meta'").fetchone():
        return
    rows = db.execute("select post_id, source, angle, style, mood, model, target_stance from meta").fetchall()
    rows = [r for r in rows if r[0] in per_post]
    print(f"\nWhat works ({len(rows)} tracked posts; groups with fewer than {min_n} posts hidden):")
    if not rows:
        print("  nothing tracked yet: bot.py records this for posts made from now on")
        return
    for col, label in enumerate(["post type", "argument", "shape", "mood", "model", "target stance"], start=1):
        groups = {}
        for r in rows:
            if r[col]:
                groups.setdefault(r[col], []).append(per_post[r[0]])
        shown = sorted(((sum(v) / len(v), k, len(v)) for k, v in groups.items() if len(v) >= min_n), reverse=True)
        if shown:
            print(f"  by {label}:")
            for avg, k, n in shown:
                print(f"    {avg:5.1f} pts avg  ({n:>3} posts)  {k[:70]}")

def main():
    accounts = our_accounts()
    mine = set(accounts.values())
    prev = {r[0]: (r[1], r[2]) for r in db.execute(
        "select account, est_points, ts from stats where ts = (select max(ts) from stats)")}
    now = datetime.now(SYD).isoformat(timespec="seconds")
    top, by_kind, rows = [], {"posts": [0, 0], "replies": [0, 0]}, {}
    for username, account_id in accounts.items():
        print(f"reading {username}...", flush=True)
        rows[username] = t = measure(username, account_id, mine, top, by_kind)
        db.execute("insert into stats values(?,?,?,?,?,?,?,?,?,?,?,?,?)", (now, username, *t.values()))
    db.commit()

    print(f"\nCtN bot report, {now[:16].replace('T', ' ')} Sydney")
    print("likes/replies/followers shown as citizens/total; est pts = engagement points from citizens\n")
    head = f"{'bot':<20}{'posts':>6}{'replies':>8}{'views':>7}{'likes':>9}{'replies in':>11}" \
           f"{'reposts':>8}{'followers':>10}{'est pts':>8}{'change':>8}"
    print(head); print("-" * len(head))
    total = {}
    for username, t in rows.items():
        for k, v in t.items():
            total[k] = total.get(k, 0) + v
        change = f"+{t['est_points'] - prev[username][0]}" if username in prev else ""
        print(f"{username:<20}{t['posts']:>6}{t['replies']:>8}{t['views']:>7}"
              f"{t['citizen_likes']:>4}/{t['likes']:<4}{t['citizen_replies']:>5}/{t['replies_in']:<5}"
              f"{t['reposts']:>8}{t['citizen_followers']:>5}/{t['followers']:<4}{t['est_points']:>8}{change:>8}")
    print("-" * len(head))
    print(f"{'TOTAL':<20}{total['posts']:>6}{total['replies']:>8}{total['views']:>7}"
          f"{total['citizen_likes']:>4}/{total['likes']:<4}{total['citizen_replies']:>5}/{total['replies_in']:<5}"
          f"{total['reposts']:>8}{total['citizen_followers']:>5}/{total['followers']:<4}{total['est_points']:>8}")
    if prev:
        print(f"(change is since the last run, {next(iter(prev.values()))[1][:16].replace('T', ' ')})")

    print("\nPoints per item (citizen likes, replies and reposts only):")
    for kind, (n, pts) in by_kind.items():
        print(f"  fresh {kind:<8}" if kind == "posts" else f"  {kind:<14}", f"{n:>4} made, {pts / n if n else 0:.1f} pts each")

    unknown = db.execute("select count(*) from citizen_scores where label is null").fetchone()[0]
    if unknown:
        print(f"  ({unknown} accounts were too unclear to call and aren't counted as citizens)")

    print("\nTop 5 by citizen engagement:")
    for pts, username, kind, cl, cr, rp, body in sorted(top, reverse=True)[:5]:
        print(f"  {pts:>3} pts  {username} {kind}  ({cl} likes, {cr} replies, {rp} reposts)")
        print(f"           {body[:150]}")

    what_works()

if __name__ == "__main__":
    main()
