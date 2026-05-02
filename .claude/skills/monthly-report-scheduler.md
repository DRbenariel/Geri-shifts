# Skill: פתיחת חודש — תזמון דוח יומי

## When to use
Invoke this skill (`/monthly-report-scheduler`) whenever the admin opens a new month for
submissions (changes the active_month in the app). It sets up daily automatic runs of the
"דוח בעיות צפויות" scan from today through the 10th of the active month.

## What this skill does

1. Reads the current `active_month` from the Google Sheets `settings` sheet (key=`active_month`).
2. Determines today's date and calculates how many days remain until the 10th of that month.
3. If today is between the 1st and 10th of the active month, schedules a daily Claude agent
   (using the schedule skill) that runs `daily_report.py` each morning and writes results to
   the `daily_report` sheet.
4. If today is past the 10th, notifies the user that the window has passed and offers a
   one-time manual run instead.

## Instructions for Claude

When this skill is invoked:

### Step 1 — Determine the window
```
today = date.today()
active_month = read from Google Sheets settings (key='active_month') OR ask the user
deadline = date(2026, active_month, 10)   # 10th of active month
days_left = (deadline - today).days
```

### Step 2 — If inside window (today <= deadline)
Tell the user:
> "החודש הפעיל הוא {month}/{year}. יש {days_left} ימים עד ה-10 לחודש. מגדיר הרצה יומית של הדוח."

Then invoke the `anthropic-skills:schedule` skill to create a **daily** scheduled agent with
this prompt (run every day at 08:00 until the 10th):

```
Run the Geri-shifts daily scheduling report for the active month.

Steps:
1. cd to D:\Projects\New Folder
2. Run: python daily_report.py
3. Read the output and summarize in Hebrew:
   - How many קריטי / אזהרה / מידע issues were found
   - List all "ימי שיא חסימה" (heavily blocked days) — these are the headline metric
   - Flag any new issues compared to yesterday (if you can compare to the previous daily_report sheet content)
4. If any קריטי issues exist, prepend the summary with 🔴 URGENT.

Stop scheduling after {deadline} (the 10th of the active month).
```

Set the schedule to: **daily at 08:00 Israel time**, ending on `{deadline}`.

### Step 3 — If past the 10th
Tell the user:
> "חלון הדוחות האוטומטיים (1-10 לחודש) כבר עבר. האם להריץ סריקה ידנית עכשיו?"
If they confirm, run `python daily_report.py` from `D:\Projects\New Folder` using Bash.

### Step 4 — Confirm
After scheduling, show a summary:
- Active month
- How many daily runs are scheduled (days_left)
- What the report focuses on: "ימי שיא חסימה" — days where ≥30% of staff blocked the same date

## Key files
- `D:\Projects\New Folder\daily_report.py` — the analysis script
- `D:\Projects\New Folder\.github\workflows\daily_report.yml` — GitHub Actions (runs daily at 10:00 IL independently)
- Google Sheets `daily_report` worksheet — where results are written
- Google Sheets `settings` worksheet — `active_month` key holds current month (int as string)

## Notes
- The GitHub Actions workflow already runs `daily_report.py` daily at 10:00 IL. This skill
  adds a Claude-agent layer that reads the results and produces a Hebrew summary with trend
  detection — it does not replace the GitHub Actions run.
- The "ימי שיא חסימה" check (added to daily_report.py) is the headline metric: days where
  ≥50% of active employees submitted אילוץ (block) → קריטי; ≥30% → אזהרה.
- Always `.str.strip()` employee names before comparing (trailing spaces exist in the sheet).
