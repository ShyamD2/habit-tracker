# HabitFlow — Advanced Habit Tracker

A self-contained, full-featured habit tracker built with **Python (Flask)**
and **SQLite** — no external database or account required. Runs entirely on
your machine.

## Features

- **Flexible scheduling** — track a habit every day, on specific weekdays
  (e.g. Mon/Wed/Fri), or as a flexible "X times per week" target.
- **Streak engine** — current streak and best-ever streak, calculated
  correctly against each habit's actual schedule (a Mon/Wed/Fri habit isn't
  penalized for Tuesdays).
- **GitHub-style consistency heatmap** — an 18-week calendar heatmap per
  habit, color-coded to the habit's own accent color.
- **Achievements / badges** — automatically unlocked at streak milestones
  (3, 7, 14, 30, 60, 100, 365 days) and total check-in milestones (10, 50,
  100, 365).
- **Analytics dashboard** — weekly completion trend chart, category
  breakdown donut chart, and a per-habit performance table.
- **Quantity + notes tracking** — log a quantity (e.g. "8 glasses of
  water") and a free-text note per check-in.
- **CSV export** — download your entire history as a spreadsheet-ready CSV.
- **Dark, modern UI** — custom-built responsive interface, no bloated
  framework required.
- **Zero external services** — SQLite file storage, nothing to configure.

## Requirements

- Python 3.9+
- pip

## Setup

```bash
# 1. Unzip and enter the project folder
cd habit_tracker

# 2. (Recommended) create a virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install the one dependency
pip install -r requirements.txt

# 4. Run the app
python app.py
```

Then open **http://127.0.0.1:5050** in your browser.

The first time it runs, the app creates `data/habits.db` (SQLite) and seeds
four example habits so the UI isn't empty — feel free to edit or delete
them.

## Project Structure

```
habit_tracker/
├── app.py                 # Flask routes / app entry point
├── db.py                  # SQLite schema + connection helper
├── analytics.py           # Streak calculation, stats, achievements
├── requirements.txt
├── templates/              # Jinja2 HTML templates
│   ├── base.html
│   ├── dashboard.html
│   ├── habit_detail.html
│   ├── habit_form.html
│   └── analytics.html
├── static/
│   ├── css/style.css
│   └── js/app.js
└── data/
    └── habits.db           # created automatically on first run
```

## How Streaks Work

- **Daily habits**: streak breaks the first day it isn't checked in.
- **Specific-days habits** (e.g. Mon/Wed/Fri): only scheduled days count —
  skipping a Tuesday doesn't break a Mon/Wed/Fri streak.
- **X times/week habits**: a "streak" is consecutive weeks where the target
  count was met; the current, in-progress week doesn't break the streak
  early.

## Resetting Your Data

Delete `data/habits.db` and restart the app — a fresh database (with the
example seed habits) will be created automatically.

## Notes

- Chart.js is loaded from a CDN for the analytics charts; everything else
  runs fully offline once the page is loaded.
- This app is intended for local/personal use (`app.run(debug=True)`). If
  you want to deploy it beyond your own machine, disable debug mode and put
  it behind a production WSGI server (e.g. gunicorn) — and add proper auth,
  since there is currently no login system.
