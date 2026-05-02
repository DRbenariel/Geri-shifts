# Shift Scheduling App — CLAUDE.md

## What this is
Streamlit app for managing shift scheduling at a geriatric hospital (המערך הגריאטרי).
Hebrew/RTL UI throughout. Google Sheets is the database (no local DB).
All reads/writes go through `get_db_data()` / `save_to_db()` — never access Sheets directly.

## Stack
- Python + Streamlit
- `streamlit-antd-components` (`sac`) for navbar/tabs
- `streamlit-shadcn-ui` imported as `ui`
- Google Sheets via `gspread` + service account credentials in `.streamlit/secrets.toml`
- `pandas` for all data manipulation

## File structure
- `appy.py` — entire application (DB layer, algorithms, all UI)
- `ui_components.py` — global CSS injection (`setup_style()`) and navbar (`render_navbar()`)
- `reset_passwords.py` — standalone admin utility, not part of the app
- `daily_report.py` — standalone scheduled agent: scans upcoming month requests and writes problems to `daily_report` sheet. Also importable inline from `appy.py` via `importlib`.
- `.github/workflows/daily_report.yml` — GitHub Actions cron (daily 10:00 IL time) that runs `daily_report.py`
- `.claude/skills/monthly-report-scheduler.md` — invoke with `/monthly-report-scheduler` when opening a new month; sets up daily Claude-agent Hebrew summaries through the 10th
- `.gitignore` — excludes `secrets.toml`, `gerishifts-7ccae6b773f7.json`, `*.db`, `__pycache__`
- `.streamlit/config.toml` — Streamlit theme (indigo primary, slate background)

## Key conventions
- All user-visible strings are Hebrew. Keep `direction: rtl` in any new HTML/CSS.
- Dates are stored as `YYYY-MM-DD` strings in Sheets, parsed with `datetime.strptime`.
- Year is hardcoded to 2026 throughout — do not generalize unless explicitly asked.
- `sel_month` is always an integer (1–12) read from session state.
- Staff roles: `מתמחה` (intern), `תורן חוץ` (external), `מנהל/ת` (admin).
- Request statuses: `אילוץ` (block/can't work), `בקשה` (wish/prefer to work).
- Shift departments: `שיקום`, `פנימית גריאטרית`, `שישי בוקר - שיקום (1/2)`, `שישי בוקר - פנימית (1/2)`.

## Google Sheets structure
| Sheet | Key columns |
|---|---|
| `staff` | name, type, dept, monthly_quota, weekend_quota, password, only_home_dept |
| `schedule` | date, dept, employee, is_manual, empty_reason |
| `requests` | employee, date, status |
| `special_days` | date, description, day_type |
| `settings` | key, value (active_month) |
| `Schedule_Export` | wide-format export (תאריך, יום, פנימית גריאטרית, שיקום, שישי בוקר cols) |
| `daily_report` | generated_at, month, severity, problem_type, description |
| `swap_requests` | requester, requester_date, requester_dept, candidate, candidate_date, candidate_dept, swap_type, created_at, status |

## Algorithm notes
- `run_smart_scheduling()` — greedy, no backtracking. Scores candidates with hardcoded weights.
- `check_assignment_validity()` — single source of truth for constraint checking. Always use it.
- Swap suggestions in `draw_calendar_view()` bypass soft scheduling conditions (pacing, quotas) — only hard constraints apply.
- Friday morning shifts are assigned in a separate post-pass after the main loop.
- `find_swap_candidates()` — employee-facing swap search. Takes `(schedule_df, requests_df, staff_df, user_name, swap_date, swap_dept, sel_month)`. Temporarily removes the user's shift before validating candidates so the 2-day rest gap recalculates correctly. Uses `ignore_quota=True`. Returns `{'full': [...], 'partial': [...]}` — full = mutual swap found, partial = one-sided coverage only. Each item: `{name, dept, type, wished, their_shift}`.

## daily_report.py checks (in order run by `analyze_month`)
1. `check_heavily_blocked_days` — **headline metric**. Days where ≥50% of active staff submitted אילוץ → קריטי ("ימי שיא חסימה"); ≥30% → אזהרה. Run first so it sorts to the top.
2. `check_who_not_submitted` — employees with no requests at all for the month.
3. `check_quota_risk` — employees whose available days can't meet their quota.
4. `check_empty_days` — dates with 0 or 1 eligible employee per dept.
5. `check_weekend_coverage` — Fri/Sat with exactly 2 eligible employees.

## UI notes
- `render_modern_calendar()` is the unified calendar component for constraint/wish selection.
  Used in both the user panel and admin constraint management panel.
  Returns `(constraint_day_nums, wish_day_nums)` as lists of int day numbers.
- Calendar session state keys follow the pattern `{key_prefix}_c_{month}`, `{key_prefix}_w_{month}`.
  Reset `{key_prefix}_init_{month}` from session state before `st.rerun()` to force reload from DB.
- Color theme: Indigo 600 (`#4f46e5`) primary, Slate 50 (`#f8fafc`) background.
- Font: Rubik (Google Fonts).
- `draw_calendar_view()` shows per-date availability (⭐ wished / ✅ available) **only for admin** and **only after all active employees have submitted** requests for the month. Gate: `all_active_names.issubset(submitted_names)` — both sets must be `.str.strip()`-normalized.
- `only_home_dept` is managed via a standalone `st.multiselect` outside the `data_editor` — not as a checkbox column — to avoid the bool/string coercion bug from Google Sheets.

## Feature: חיפוש החלפות (employee swap search)
- Location: `הגדרות` tab, expander "🔄 חיפוש החלפות" — shown to non-admins only.
- Employee selects one of their shifts → `find_swap_candidates()` runs → results in two tiers:
  - **✅ החלפה מלאה** — mutual swap: candidate covers user's shift AND user can cover one of theirs.
  - **⚠️ כיסוי חד-צדדי** — candidate can cover the user's shift but no mutual shift found.
- ⭐ pill shown on candidates who submitted `בקשה` on the selected date.
- "🔄 בקש החלפה" button writes a row to `swap_requests` sheet with `status='pending'`.
- No auto-execution — admin must approve.

## Feature: Admin swap approval panel
- Location: `לוח שיבוץ` tab, below `draw_calendar_view()`.
- Loads `swap_requests` sheet and filters `status == 'pending'`.
- **✅ אשר** — moves the schedule rows (sets `is_manual=True`), updates `swap_requests` status to `approved`, reruns.
- **❌ דחה** — updates status to `rejected`, reruns.
- Success/reject messages use the session-state flag pattern (shown on next render).
- `swap_type='full'` swaps both directions; `swap_type='partial'` only reassigns the requester's shift.

## Feature: דוח בעיות צפויות headline
- Top of `דוחות וניהול` tab shows a live banner counting "ימי שיא חסימה" from the last saved report (קריטי / אזהרה counts) before the manual run button.
- Headline reads from the already-saved `daily_report` sheet — does not re-run analysis on load.

## Known data quality issues
- **Employee names in Google Sheets may have trailing/invisible spaces.** Always `.str.strip()` before any name comparison — in login, submission checks, availability display, and anywhere `staff['name']` is compared to `requests['employee']`. The employee `לין חיר אל דין` has a confirmed trailing space in the staff sheet.
- **`only_home_dept` is stored as string `"True"`/`"False"` in Google Sheets.** Never use `.astype(bool)` — a non-empty string `"False"` evaluates to `True`. Always parse with the `_is_true()` helper: `lambda v: v if isinstance(v, bool) else str(v).strip().lower() == 'true'`. Applied at startup load and in the admin form.

## Success message pattern
After `save_to_db()` + `st.rerun()`, success messages must use session state flag — `st.success()` called immediately before `st.rerun()` is invisible. Pattern:
```python
st.session_state['show_xyz_success'] = True
st.rerun()
# On next render (outside any conditional block that gets skipped):
if st.session_state.pop('show_xyz_success', False):
    st.success("...")
```

## Git / GitHub
- Remote: `https://github.com/DRbenariel/Geri-shifts.git` (branch: `main`)
- GitHub Actions: `.github/workflows/daily_report.yml` — runs `daily_report.py` daily at 10:00 IL via `GSHEETS_CREDENTIALS` secret (service account JSON stored as repo secret).

## Do not touch
- `.streamlit/secrets.toml` — credential layout is fixed by the deployment environment.
- `reset_passwords.py` — run manually only when resetting admin passwords.
- `gerishifts-7ccae6b773f7.json` — service account private key. Never commit to git. Already in `.gitignore`. For GitHub Actions use the `GSHEETS_CREDENTIALS` secret.

## Running locally
```
streamlit run "d:/Projects/New Folder/appy.py"
```
