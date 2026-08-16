"""
Advanced Habit Tracker
A self-contained Flask app: SQLite storage, streak engine, calendar
heatmaps, analytics dashboard, and an achievement/badge system.

Run with:  python app.py
Then open: http://127.0.0.1:5050
"""
import csv
import io
import json
from datetime import date, datetime, timedelta

from flask import (
    Flask, render_template, request, redirect, url_for, jsonify,
    flash, Response, send_file
)

import db
import analytics as an

app = Flask(__name__)
app.secret_key = "habit-tracker-dev-secret"  # only used for flash messages

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
COLOR_PALETTE = ["#00d4ff", "#8b5cf6", "#22c55e", "#eab308", "#ef4444",
                  "#ec4899", "#3b82f6", "#14b8a6", "#f97316", "#a3e635"]
ICON_CHOICES = ["\U0001F3AF", "\U0001F4A7", "\U0001F4DA", "\U0001F3CB", "\U0001F4CB",
                 "\U0001F3C3", "\U0001F9D8", "\U0001F4DD", "\U0001F3A8", "\U0001F634",
                 "\U0001F957", "\U0001F6B0", "\U0001F4B0", "\U0001F9EA", "\U0001F4F5",
                 "\U0001F3B8", "\U0001F6CF", "\U0001F9F9", "\U0001F415", "\u2615"]


def dict_habit(row):
    h = dict(row)
    h["custom_days_list"] = json.loads(h["custom_days"] or "[]")
    return h


@app.route("/")
def dashboard():
    conn = db.get_db()
    today = date.today()
    habits = [dict_habit(r) for r in
               conn.execute("SELECT * FROM habits WHERE archived = 0 ORDER BY sort_order, id").fetchall()]

    today_iso = today.isoformat()
    for h in habits:
        entry = conn.execute(
            "SELECT * FROM entries WHERE habit_id = ? AND date = ?", (h["id"], today_iso)
        ).fetchone()
        h["today_entry"] = dict(entry) if entry else None
        h["scheduled_today"] = an.is_scheduled(h, today)
        h["streak"] = an.calculate_streak(conn, h)
        h["stats30"] = an.completion_stats(conn, h, days=30)

    stats = an.overall_dashboard_stats(conn)
    recent_achievements = conn.execute(
        """SELECT a.*, h.name as habit_name FROM achievements a
           JOIN habits h ON h.id = a.habit_id
           ORDER BY a.earned_at DESC LIMIT 5"""
    ).fetchall()

    conn.close()
    return render_template(
        "dashboard.html", habits=habits, stats=stats,
        recent_achievements=recent_achievements, today=today_iso,
        weekday_names=WEEKDAY_NAMES,
    )


@app.route("/habit/<int:habit_id>")
def habit_detail(habit_id):
    conn = db.get_db()
    row = conn.execute("SELECT * FROM habits WHERE id = ?", (habit_id,)).fetchone()
    if not row:
        conn.close()
        return redirect(url_for("dashboard"))
    habit = dict_habit(row)

    heatmap = an.heatmap_data(conn, habit, weeks=18)
    streak = an.calculate_streak(conn, habit)
    stats30 = an.completion_stats(conn, habit, days=30)
    stats7 = an.completion_stats(conn, habit, days=7)

    recent_entries = conn.execute(
        "SELECT * FROM entries WHERE habit_id = ? ORDER BY date DESC LIMIT 15", (habit_id,)
    ).fetchall()

    badges = conn.execute(
        "SELECT * FROM achievements WHERE habit_id = ? ORDER BY earned_at DESC", (habit_id,)
    ).fetchall()

    # group heatmap days into weeks (columns) for the template
    weeks_grid = [heatmap[i:i + 7] for i in range(0, len(heatmap), 7)]

    conn.close()
    return render_template(
        "habit_detail.html", habit=habit, heatmap_weeks=weeks_grid,
        streak=streak, stats30=stats30, stats7=stats7,
        recent_entries=recent_entries, badges=badges,
        weekday_names=WEEKDAY_NAMES,
    )


@app.route("/habit/new", methods=["GET", "POST"])
def habit_new():
    if request.method == "POST":
        conn = db.get_db()
        _save_habit(conn, None)
        conn.close()
        flash("Habit created!", "success")
        return redirect(url_for("dashboard"))
    return render_template(
        "habit_form.html", habit=None, colors=COLOR_PALETTE, icons=ICON_CHOICES,
        weekday_names=WEEKDAY_NAMES,
    )


@app.route("/habit/<int:habit_id>/edit", methods=["GET", "POST"])
def habit_edit(habit_id):
    conn = db.get_db()
    row = conn.execute("SELECT * FROM habits WHERE id = ?", (habit_id,)).fetchone()
    if not row:
        conn.close()
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        _save_habit(conn, habit_id)
        conn.close()
        flash("Habit updated.", "success")
        return redirect(url_for("habit_detail", habit_id=habit_id))

    habit = dict_habit(row)
    conn.close()
    return render_template(
        "habit_form.html", habit=habit, colors=COLOR_PALETTE, icons=ICON_CHOICES,
        weekday_names=WEEKDAY_NAMES,
    )


def _save_habit(conn, habit_id):
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    category = request.form.get("category", "General").strip() or "General"
    color = request.form.get("color", "#00d4ff")
    icon = request.form.get("icon", "\U0001F3AF")
    frequency_type = request.form.get("frequency_type", "daily")
    custom_days = json.dumps([int(d) for d in request.form.getlist("custom_days")])
    weekly_target = int(request.form.get("weekly_target") or 7)
    target_quantity = int(request.form.get("target_quantity") or 1)
    unit = request.form.get("unit", "").strip()

    if habit_id is None:
        now = datetime.now().isoformat()
        max_order = conn.execute("SELECT COALESCE(MAX(sort_order),0) AS m FROM habits").fetchone()["m"]
        conn.execute(
            """INSERT INTO habits (name, description, category, color, icon, frequency_type,
               custom_days, weekly_target, target_quantity, unit, sort_order, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (name, description, category, color, icon, frequency_type, custom_days,
             weekly_target, target_quantity, unit, max_order + 1, now),
        )
    else:
        conn.execute(
            """UPDATE habits SET name=?, description=?, category=?, color=?, icon=?,
               frequency_type=?, custom_days=?, weekly_target=?, target_quantity=?, unit=?
               WHERE id=?""",
            (name, description, category, color, icon, frequency_type, custom_days,
             weekly_target, target_quantity, unit, habit_id),
        )
    conn.commit()


@app.route("/habit/<int:habit_id>/archive", methods=["POST"])
def habit_archive(habit_id):
    conn = db.get_db()
    conn.execute("UPDATE habits SET archived = 1 WHERE id = ?", (habit_id,))
    conn.commit()
    conn.close()
    flash("Habit archived.", "info")
    return redirect(url_for("dashboard"))


@app.route("/habit/<int:habit_id>/delete", methods=["POST"])
def habit_delete(habit_id):
    conn = db.get_db()
    conn.execute("DELETE FROM habits WHERE id = ?", (habit_id,))
    conn.commit()
    conn.close()
    flash("Habit deleted.", "info")
    return redirect(url_for("dashboard"))


@app.route("/api/checkin", methods=["POST"])
def api_checkin():
    """Toggle / set a habit's completion for a given date. Returns JSON for AJAX use."""
    data = request.get_json(force=True)
    habit_id = data["habit_id"]
    entry_date = data.get("date", date.today().isoformat())
    quantity = int(data.get("quantity", 0))
    note = data.get("note", "")

    conn = db.get_db()
    existing = conn.execute(
        "SELECT * FROM entries WHERE habit_id = ? AND date = ?", (habit_id, entry_date)
    ).fetchone()

    if existing:
        new_completed = 0 if existing["completed"] else 1
        conn.execute(
            "UPDATE entries SET completed = ?, quantity = ?, note = ? WHERE id = ?",
            (new_completed, quantity or existing["quantity"], note or existing["note"], existing["id"]),
        )
    else:
        now = datetime.now().isoformat()
        conn.execute(
            """INSERT INTO entries (habit_id, date, completed, quantity, note, created_at)
               VALUES (?,?,1,?,?,?)""",
            (habit_id, entry_date, quantity, note, now),
        )
        new_completed = 1

    conn.commit()

    habit = conn.execute("SELECT * FROM habits WHERE id = ?", (habit_id,)).fetchone()
    newly_earned = an.check_and_award_achievements(conn, habit) if new_completed else []
    streak = an.calculate_streak(conn, habit)
    conn.close()

    return jsonify({
        "completed": bool(new_completed),
        "streak": streak,
        "newly_earned": newly_earned,
    })


@app.route("/analytics")
def analytics_page():
    conn = db.get_db()
    habits = [dict_habit(r) for r in
               conn.execute("SELECT * FROM habits WHERE archived = 0 ORDER BY sort_order").fetchall()]

    per_habit = []
    for h in habits:
        streak = an.calculate_streak(conn, h)
        stats30 = an.completion_stats(conn, h, days=30)
        per_habit.append({"habit": h, "streak": streak, "stats30": stats30})

    trend = an.weekly_trend(conn, weeks=10)
    breakdown = an.category_breakdown(conn)
    all_badges = conn.execute(
        """SELECT a.*, h.name as habit_name, h.color as habit_color FROM achievements a
           JOIN habits h ON h.id = a.habit_id ORDER BY a.earned_at DESC"""
    ).fetchall()

    conn.close()
    return render_template(
        "analytics.html", per_habit=per_habit, trend=trend,
        breakdown=breakdown, all_badges=all_badges,
    )


@app.route("/export/csv")
def export_csv():
    conn = db.get_db()
    rows = conn.execute(
        """SELECT h.name as habit, h.category, e.date, e.completed, e.quantity, e.note
           FROM entries e JOIN habits h ON h.id = e.habit_id
           ORDER BY e.date DESC"""
    ).fetchall()
    conn.close()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Habit", "Category", "Date", "Completed", "Quantity", "Note"])
    for r in rows:
        writer.writerow([r["habit"], r["category"], r["date"], bool(r["completed"]), r["quantity"], r["note"]])

    mem = io.BytesIO(buf.getvalue().encode("utf-8"))
    return send_file(
        mem, mimetype="text/csv", as_attachment=True,
        download_name=f"habit_tracker_export_{date.today().isoformat()}.csv",
    )


@app.route("/api/habit/<int:habit_id>/reorder", methods=["POST"])
def api_reorder(habit_id):
    data = request.get_json(force=True)
    new_order = int(data.get("order", 0))
    conn = db.get_db()
    conn.execute("UPDATE habits SET sort_order = ? WHERE id = ?", (new_order, habit_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.context_processor
def inject_globals():
    return {"current_year": date.today().year}


if __name__ == "__main__":
    db.init_db()
    print("\n" + "=" * 52)
    print("  Habit Tracker running at http://127.0.0.1:5050")
    print("=" * 52 + "\n")
    app.run(debug=True, port=5050)
