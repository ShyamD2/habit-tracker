"""
Database layer for the Habit Tracker.
Uses plain sqlite3 (no ORM) so the whole app has zero third-party
dependencies beyond Flask.
"""
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "habits.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS habits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    category        TEXT DEFAULT 'General',
    color           TEXT DEFAULT '#00d4ff',
    icon            TEXT DEFAULT '\U0001F3AF',
    frequency_type  TEXT NOT NULL DEFAULT 'daily',   -- daily | custom_days | weekly_target
    custom_days     TEXT DEFAULT '[]',                -- JSON list of weekday ints (Mon=0..Sun=6)
    weekly_target   INTEGER DEFAULT 7,                -- used when frequency_type = weekly_target
    target_quantity INTEGER DEFAULT 1,                -- e.g. "drink 8 glasses of water"
    unit            TEXT DEFAULT '',                  -- e.g. "glasses", "pages", "minutes"
    archived        INTEGER DEFAULT 0,
    sort_order      INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    habit_id    INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
    date        TEXT NOT NULL,      -- YYYY-MM-DD
    completed   INTEGER NOT NULL DEFAULT 0,
    quantity    INTEGER DEFAULT 0,
    note        TEXT DEFAULT '',
    created_at  TEXT NOT NULL,
    UNIQUE(habit_id, date)
);

CREATE TABLE IF NOT EXISTS achievements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    habit_id    INTEGER REFERENCES habits(id) ON DELETE CASCADE,
    code        TEXT NOT NULL,
    title       TEXT NOT NULL,
    description TEXT DEFAULT '',
    icon        TEXT DEFAULT '\U0001F3C6',
    earned_at   TEXT NOT NULL,
    UNIQUE(habit_id, code)
);

CREATE INDEX IF NOT EXISTS idx_entries_habit_date ON entries(habit_id, date);
CREATE INDEX IF NOT EXISTS idx_entries_date ON entries(date);
"""


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()

    # Seed a couple of example habits on very first run only
    cur = conn.execute("SELECT COUNT(*) AS c FROM habits")
    if cur.fetchone()["c"] == 0:
        now = datetime.now().isoformat()
        seed = [
            ("Drink Water", "Stay hydrated throughout the day", "Health", "#00d4ff", "\U0001F4A7",
             "daily", "[]", 7, 8, "glasses", 0, now),
            ("Read", "Read a book for at least 20 minutes", "Growth", "#8b5cf6", "\U0001F4DA",
             "daily", "[]", 7, 20, "minutes", 1, now),
            ("Gym Workout", "Strength or cardio session", "Fitness", "#22c55e", "\U0001F3CB",
             "custom_days", "[0,2,4]", 3, 1, "session", 2, now),
            ("Weekly Review", "Plan and review the upcoming week", "Productivity", "#eab308", "\U0001F4CB",
             "weekly_target", "[]", 1, 1, "review", 3, now),
        ]
        conn.executemany(
            """INSERT INTO habits
               (name, description, category, color, icon, frequency_type, custom_days,
                weekly_target, target_quantity, unit, sort_order, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            seed,
        )
        conn.commit()
    conn.close()
