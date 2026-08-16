"""
Analytics engine: streak calculation, completion rates, weekly/monthly
trends, and the achievement/badge system.
"""
import json
from datetime import date, timedelta, datetime
from collections import defaultdict

ACHIEVEMENT_DEFS = [
    # (code, threshold, title, description, icon)
    ("streak_3", 3, "Getting Started", "3-day streak", "\U0001F331"),
    ("streak_7", 7, "One Week Strong", "7-day streak", "\U0001F525"),
    ("streak_14", 14, "Two Weeks In", "14-day streak", "\u26A1"),
    ("streak_30", 30, "Habit Formed", "30-day streak", "\U0001F3C6"),
    ("streak_60", 60, "Unstoppable", "60-day streak", "\U0001F48E"),
    ("streak_100", 100, "Centurion", "100-day streak", "\U0001F451"),
    ("streak_365", 365, "Full Year", "365-day streak", "\U0001F30D"),
]

TOTAL_ACHIEVEMENT_DEFS = [
    ("total_10", 10, "First Ten", "10 total check-ins", "\u2728"),
    ("total_50", 50, "Half Century", "50 total check-ins", "\U0001F3AF"),
    ("total_100", 100, "Triple Digits", "100 total check-ins", "\U0001F4AF"),
    ("total_365", 365, "Year of Effort", "365 total check-ins", "\U0001F3C5"),
]


def is_scheduled(habit, d: date) -> bool:
    """Return True if `habit` is scheduled to happen on date `d`."""
    ftype = habit["frequency_type"]
    if ftype == "daily":
        return True
    if ftype == "custom_days":
        days = json.loads(habit["custom_days"] or "[]")
        return d.weekday() in days
    if ftype == "weekly_target":
        # Flexible: scheduled every day, target is "N times this week"
        return True
    return True


def _entries_map(conn, habit_id):
    rows = conn.execute(
        "SELECT date, completed, quantity FROM entries WHERE habit_id = ? AND completed = 1",
        (habit_id,),
    ).fetchall()
    return {r["date"]: r for r in rows}


def calculate_streak(conn, habit):
    """Current streak + best streak, respecting the habit's schedule."""
    entries = _entries_map(conn, habit["id"])
    if not entries:
        return {"current": 0, "best": 0}

    if habit["frequency_type"] == "weekly_target":
        return _weekly_target_streak(conn, habit, entries)

    today = date.today()
    # Current streak: walk backward from today (allow today to be "pending")
    current = 0
    cursor = today
    # If today is scheduled but not yet completed, start checking from yesterday
    if is_scheduled(habit, cursor) and cursor.isoformat() not in entries:
        cursor = cursor - timedelta(days=1)

    while True:
        if is_scheduled(habit, cursor):
            if cursor.isoformat() in entries:
                current += 1
                cursor -= timedelta(days=1)
            else:
                break
        else:
            cursor -= timedelta(days=1)
        # safety bound
        if (today - cursor).days > 3650:
            break

    # Best streak: scan full history
    all_dates = sorted(entries.keys())
    if not all_dates:
        return {"current": current, "best": current}

    start = datetime.strptime(all_dates[0], "%Y-%m-%d").date()
    end = today
    best = 0
    run = 0
    d = start
    while d <= end:
        if is_scheduled(habit, d):
            if d.isoformat() in entries:
                run += 1
                best = max(best, run)
            else:
                run = 0
        d += timedelta(days=1)

    return {"current": current, "best": max(best, current)}


def _weekly_target_streak(conn, habit, entries):
    """For weekly_target habits: a 'streak' is consecutive weeks meeting target."""
    target = habit["weekly_target"] or 1
    if not entries:
        return {"current": 0, "best": 0}

    dates = sorted(datetime.strptime(d, "%Y-%m-%d").date() for d in entries.keys())
    start_monday = dates[0] - timedelta(days=dates[0].weekday())
    today = date.today()
    this_monday = today - timedelta(days=today.weekday())

    week_counts = defaultdict(int)
    for d in dates:
        wk = d - timedelta(days=d.weekday())
        week_counts[wk] += 1

    weeks = []
    wk = start_monday
    while wk <= this_monday:
        weeks.append(wk)
        wk += timedelta(days=7)

    current = 0
    best = 0
    run = 0
    for i, wk in enumerate(weeks):
        met = week_counts.get(wk, 0) >= target
        is_last = wk == this_monday
        if met:
            run += 1
            best = max(best, run)
        elif not is_last:
            run = 0
        # if it's the current (incomplete) week and not yet met, don't break the streak
    # current streak = trailing run counting back from most recent *complete* week
    run = 0
    for wk in reversed(weeks):
        met = week_counts.get(wk, 0) >= target
        if wk == this_monday and not met:
            continue  # current week still in progress, skip
        if met:
            run += 1
        else:
            break
    current = run

    return {"current": current, "best": max(best, current)}


def completion_stats(conn, habit, days=30):
    """Completion rate over the trailing `days` days, respecting schedule."""
    today = date.today()
    entries = _entries_map(conn, habit["id"])
    scheduled = 0
    done = 0
    for i in range(days):
        d = today - timedelta(days=i)
        if is_scheduled(habit, d):
            scheduled += 1
            if d.isoformat() in entries:
                done += 1
    rate = round((done / scheduled) * 100) if scheduled else 0
    return {"done": done, "scheduled": scheduled, "rate": rate}


def heatmap_data(conn, habit, weeks=18):
    """Return a list of {date, completed, quantity} for a GitHub-style heatmap."""
    today = date.today()
    start = today - timedelta(days=weeks * 7 - 1)
    # align start to a Monday for clean grid columns
    start = start - timedelta(days=start.weekday())

    entries = {
        r["date"]: r
        for r in conn.execute(
            "SELECT date, completed, quantity FROM entries WHERE habit_id = ? AND date >= ?",
            (habit["id"], start.isoformat()),
        ).fetchall()
    }

    days = []
    d = start
    while d <= today:
        iso = d.isoformat()
        row = entries.get(iso)
        days.append({
            "date": iso,
            "completed": bool(row["completed"]) if row else False,
            "quantity": row["quantity"] if row else 0,
            "scheduled": is_scheduled(habit, d),
            "future": d > today,
        })
        d += timedelta(days=1)
    return days


def check_and_award_achievements(conn, habit):
    """Check streak + total-count thresholds and insert any newly earned badges."""
    streak = calculate_streak(conn, habit)
    total = conn.execute(
        "SELECT COUNT(*) AS c FROM entries WHERE habit_id = ? AND completed = 1",
        (habit["id"],),
    ).fetchone()["c"]

    newly_earned = []
    now = datetime.now().isoformat()

    for code, threshold, title, desc, icon in ACHIEVEMENT_DEFS:
        if streak["best"] >= threshold or streak["current"] >= threshold:
            existing = conn.execute(
                "SELECT id FROM achievements WHERE habit_id = ? AND code = ?",
                (habit["id"], code),
            ).fetchone()
            if not existing:
                conn.execute(
                    """INSERT INTO achievements (habit_id, code, title, description, icon, earned_at)
                       VALUES (?,?,?,?,?,?)""",
                    (habit["id"], code, title, f"{desc} — {habit['name']}", icon, now),
                )
                newly_earned.append(title)

    for code, threshold, title, desc, icon in TOTAL_ACHIEVEMENT_DEFS:
        if total >= threshold:
            existing = conn.execute(
                "SELECT id FROM achievements WHERE habit_id = ? AND code = ?",
                (habit["id"], code),
            ).fetchone()
            if not existing:
                conn.execute(
                    """INSERT INTO achievements (habit_id, code, title, description, icon, earned_at)
                       VALUES (?,?,?,?,?,?)""",
                    (habit["id"], code, title, f"{desc} — {habit['name']}", icon, now),
                )
                newly_earned.append(title)

    conn.commit()
    return newly_earned


def overall_dashboard_stats(conn):
    """Aggregate stats across all active habits, for the dashboard header cards."""
    habits = conn.execute("SELECT * FROM habits WHERE archived = 0").fetchall()
    today = date.today().isoformat()

    total_habits = len(habits)
    scheduled_today = [h for h in habits if is_scheduled(h, date.today())]
    completed_today = conn.execute(
        "SELECT COUNT(*) AS c FROM entries WHERE date = ? AND completed = 1", (today,)
    ).fetchone()["c"]

    streak_sum = 0
    best_overall = 0
    total_rate = []
    for h in habits:
        s = calculate_streak(conn, h)
        streak_sum += s["current"]
        best_overall = max(best_overall, s["best"])
        stats = completion_stats(conn, h, days=30)
        if stats["scheduled"] > 0:
            total_rate.append(stats["rate"])

    avg_rate = round(sum(total_rate) / len(total_rate)) if total_rate else 0

    return {
        "total_habits": total_habits,
        "scheduled_today": len(scheduled_today),
        "completed_today": completed_today,
        "current_streak_sum": streak_sum,
        "best_overall_streak": best_overall,
        "avg_completion_rate": avg_rate,
    }


def weekly_trend(conn, weeks=8):
    """Overall completion count per week across all habits, for the trend chart."""
    today = date.today()
    this_monday = today - timedelta(days=today.weekday())
    result = []
    for i in range(weeks - 1, -1, -1):
        wk_start = this_monday - timedelta(days=7 * i)
        wk_end = wk_start + timedelta(days=6)
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM entries WHERE completed = 1 AND date BETWEEN ? AND ?",
            (wk_start.isoformat(), wk_end.isoformat()),
        ).fetchone()["c"]
        result.append({"week": wk_start.strftime("%b %d"), "count": count})
    return result


def category_breakdown(conn):
    habits = conn.execute("SELECT * FROM habits WHERE archived = 0").fetchall()
    counts = defaultdict(int)
    for h in habits:
        counts[h["category"]] += 1
    return [{"category": k, "count": v} for k, v in counts.items()]
