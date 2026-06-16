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
- `frontend/` — **new standalone admin UI** (separate from the Streamlit app), built with the `/design-taste-frontend` + `ui-ux-pro-max` skills. OLED-dark "instrument panel" Hebrew/RTL design.
  - `frontend/admin/index.html` — single-page superadmin UI (7 tabs). Data-heavy grids (calendar/gantt/work-status) render from JS; falls back to sample fixtures when the API is unreachable ("design mode").
  - `frontend/server.py` — **Flask backend** bridging the HTML to the same Google Sheets DB. Auth mirrors `daily_report.py:get_client()` (env `GSHEETS_CREDENTIALS` or local JSON). JSON API under `/api/*`; serves `frontend/` as web root. Run: `python frontend/server.py` → http://127.0.0.1:5000. Boots in DESIGN MODE (reads→[], writes→`{ok:false,design_mode:true}`) when no creds.
  - `frontend/design-system/` — `tokens.css` (single source of truth) + `MASTER.md` design rules. Hard constraints: no rounded corners, status never colour-only (dot/code+label), Fira Code numerals `dir=ltr`, scanline ≤12%.
  - `frontend/font-samples.html` — side-by-side font-pairing comparison page.
- `.claude/skills/monthly-report-scheduler.md` — invoke with `/monthly-report-scheduler` when opening a new month; sets up daily Claude-agent Hebrew summaries through the 10th
- `.gitignore` — excludes `secrets.toml`, `gerishifts-7ccae6b773f7.json`, `*.db`, `__pycache__`
- `.streamlit/config.toml` — Streamlit theme (indigo primary, slate background)

## Key conventions
- All user-visible strings are Hebrew. Keep `direction: rtl` in any new HTML/CSS.
- Dates are stored as `YYYY-MM-DD` strings in Sheets, parsed with `datetime.strptime`.
- Year is hardcoded to 2026 throughout — do not generalize unless explicitly asked.
- `sel_month` is always an integer (1–12) read from session state.
- Staff roles: `מתמחה` (intern), `תורן חוץ` (external), `מנהל/ת` (admin), **`רופא בכיר`** (senior doctor — daily schedule only), **`מנהל מחלקה`** (department head — manages day-schedule for own dept(s)).
- Request statuses: `אילוץ` (block/can't work), `בקשה` (wish/prefer to work).
- Shift departments: `שיקום`, `פנימית גריאטרית`, plus four Friday morning half-shifts: `שישי בוקר - שיקום (1)`, `שישי בוקר - שיקום (2)`, `שישי בוקר - פנימית (1)`, `שישי בוקר - פנימית (2)`. Each Friday has all 4 → 4 Fridays/month = **16 שישי בוקר shifts**.
- Daily-schedule departments (separate from night shifts): `שיקום גריאטרי א'`, `שיקום גריאטרי ב'`, `פנימית גריאטרית`.
- Day status values (in `work_schedule_daily.status`): `עובד` / `חופש` / `202` / `אחרי תורנות` / `אחר`. **Always use "אחרי תורנות"** (not "מחרת תורנות").

## Google Sheets structure
| Sheet | Key columns |
|---|---|
| `staff` | name, type, dept, monthly_quota, weekend_quota, password, only_home_dept, **email**, **manage_depts** |
| `schedule` | date, dept, employee, is_manual, empty_reason |
| `requests` | employee, date, status |
| `special_days` | date, description, day_type |
| `settings` | key, value (`active_month`, **`daily_active_month`**, **`daily_requests_open`**) |
| `Schedule_Export` | wide-format export of night shifts (תאריך, יום, פנימית גריאטרית, שיקום, שישי בוקר cols) — **export button moved to "לוח שיבוץ" tab** (no longer in דוחות וניהול) |
| `daily_report` | generated_at, month, severity, problem_type, description |
| `swap_requests` | requester, requester_date, requester_dept, candidate, candidate_date, candidate_dept, swap_type, chain_ext, chain_ext_dept, created_at, status |
| `analytics_log` | event_id, session_id, timestamp, user_name, user_role, event_type, detail_1, detail_2, device_type, ua_string, viewport_width, active_month, day_of_month |
| **`dept_rotation`** | employee, year_month (YYYY-MM), daily_dept |
| **`absence_requests`** | id (uuid), employee, start_date, end_date, type (חופש/202/חופש עתידי/היעדרות אחרת), status (pending/approved/rejected), dept_at_request, manager_email, approved_by, notes, created_at, responded_at |
| **`work_schedule_daily`** | date, employee, daily_dept, status, note, is_manual |
| **`WSD_<dept>_<year_month>`** | per-dept wide-format export — rows=employees, cols=days 1..N, cells=status emoji. Created on demand by the "ייצוא" sub-tab in סידור חודשי. |

## Algorithm notes
- `run_smart_scheduling()` — greedy, no backtracking. Scores candidates with hardcoded weights.
- `check_assignment_validity()` — single source of truth for constraint checking. Always use it.
- Swap suggestions in `draw_calendar_view()` bypass soft scheduling conditions (pacing, quotas) — only hard constraints apply.
- Friday morning shifts are assigned in a separate post-pass after the main loop.
- `find_swap_candidates()` — employee-facing swap search. Takes `(schedule_df, requests_df, staff_df, user_name, swap_date, swap_dept, sel_month)`. Temporarily removes the user's shift before validating candidates so the 2-day rest gap recalculates correctly. Uses `ignore_quota=True`. Returns `{'full': [...], 'partial': [...], 'chain': [...]}`:
  - `full` — mutual swap found. Each item: `{name, dept, type, wished, their_shift}`.
  - `partial` — one-sided coverage only. Same shape, `their_shift=None`.
  - `chain` — 3-way: מתמחה moves שיקום→פנימית, תורן חוץ covers שיקום. Only populated when `swap_dept=='פנימית גריאטרית'`. Each item: `{facilitator_name, facilitator_dept, facilitator_wished, external_name, external_wished}`.
  - `their_shifts` filter excludes dates < today (past shifts cannot be offered as mutual exchange).

## daily_report.py checks (in order run by `analyze_month`)
1. `check_heavily_blocked_days` — **headline metric**. Days where ≥50% of active staff submitted אילוץ → קריטי ("ימי שיא חסימה"); ≥30% → אזהרה. Run first so it sorts to the top.
2. `check_who_not_submitted` — employees with no requests at all for the month.
3. `check_quota_risk` — employees whose available days can't meet their quota.
4. `check_empty_days` — dates with 0 or 1 eligible employee per dept.
5. `check_weekend_coverage` — Fri/Sat with exactly 2 eligible employees.
6. `check_scheduling_feasibility` — **scheduling simulation agent** (runs only on days 3–8 of month). Runs 3 strategies, picks best by score, runs Friday morning post-pass, then emits a tight set of rows:
   - `[שיבוץ] סיכום עובד` — one row per active employee: `שם: N משמרות (מתוכן M סופ"ש) | שישי בוקר: K` → מידע. Sums of `N`/`K` across all employees match the totals in the summary row.
   - `[שיבוץ] יום ריק` — slot the simulation could not fill even with the relaxed fallback rules → קריטי
   - `[שיבוץ] שיבוץ בקושי` — slot filled only by relaxing rest-gap or soft-quota rules (fallback pool) → אזהרה
   - `[שיבוץ] סיכום שיבוץ` — **always-present** single summary row at the end. Format: `אסטרטגיה הטובה ביותר: <strat> | משמרות רגילות: X/<num_days × 2> שובצו | שישי בוקר: A/<Fridays × 4> שובצו | ימים ריקים: E | שיבוצי גיבוי: F | ימים קריטיים: K (d1/m, d2/m, ...)` → מידע. Critical days are the union of all distinct days flagged קריטי anywhere in the report.

## Scheduling simulation — 3 strategies
- **tier** — critical slots (≤1 eligible) first, then weekends, then weekdays; within each tier sorted by fewest eligible ascending.
- **weekend_first** — weekends first then weekdays (mirrors current app `run_smart_scheduling`).
- **constraint_first** — all slots sorted purely by fewest eligible ascending.
Score = `empty_slots * 100 + fallback_slots * 10`. Lowest score wins.

## Scheduling simulation — 4 improvements vs `run_smart_scheduling()`
1. Three-tier day ordering (critical → weekend → weekday) instead of weekend-first only.
2. Constraint-first within each tier (fewest eligible first).
3. Multiple runs (3 strategies) — picks best by score.
4. Wish priority = +1000 score bonus instead of pool restriction (non-wishers still fill slot if wisher blocked).

## Scheduling simulation — standalone helpers in `daily_report.py`
- `load_all_data(sh)` — loads all 5 sheets into a dict.
- `is_functional_weekend_standalone(date_obj, special_days_df)` — pure-Python replica of `is_functional_weekend()`.
- `count_eligible_for_slot(date_str, dept, staff_df, requests_df, schedule_df)` — counts candidates by type+block+assigned (no quota/rest-gap). Treats any dept containing `'פנימית'` as off-limits to תורן חוץ.
- `build_ordering(year, month, data, strategy)` — returns `[(date_obj, dept), ...]` for a given strategy. Only ordering for the 2 main depts (`פנימית גריאטרית`, `שיקום`); Friday morning shifts are not in the ordering.
- `run_scheduling_simulation(year, month, data, day_ordering)` — greedy main loop + **Friday morning post-pass** (mirrors `appy.py` lines 1280–1360). Returns `{schedule, empty_slots, fallback_slots, score}`.
- `check_scheduling_feasibility(year, month, data)` — orchestrates 3 runs, returns problem list including the always-present summary row.

## Friday morning post-pass (inside `run_scheduling_simulation`)
After the main greedy loop fills the 2 main depts for every day, derive the 4 Friday morning slots per Friday:
- `שישי בוקר - פנימית (1)` = whoever was assigned `פנימית גריאטרית` on **Friday** (auto-derived).
- `שישי בוקר - פנימית (2)` = whoever was assigned `פנימית גריאטרית` on **Saturday** (auto-derived).
- `שישי בוקר - שיקום (1)` = if that Friday's שיקום worker is מתמחה → they do it themselves; if תורן חוץ → search for a replacement מתמחה from שיקום dept (must pass block/quota/±2-day rest checks; tie-broken by fewest existing שישי בוקר for fairness).
- `שישי בוקר - שיקום (2)` = same logic but sourced from **Saturday's** שיקום worker.

Implementation rules:
- All names extracted from `sim_schedule` rows go through `.strip()` before use, because `schedule_df` may contain trailing-space names (see Known data quality issues). Without stripping, the `staff_df['name'].str.strip() == rehab_worker` lookup misses, `worker_type` becomes `''`, and a real מתמחה is wrongly treated as תורן חוץ.
- Each post-pass insertion checks `_already_has(date, dept)` first to avoid duplicating any existing manual שישי בוקר row from `schedule_df`.
- Empty Friday morning slots are appended to `empty_slots` (so they appear as `[שיבוץ] יום ריק` and are counted in the summary's `שישי בוקר: A/16`).

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
- Employee selects one of their shifts → `find_swap_candidates()` runs → results in three tiers:
  - **✅ החלפה מלאה** — mutual swap: candidate covers user's shift AND user can cover one of theirs.
  - **⚠️ כיסוי חד-צדדי** — candidate can cover the user's shift but no mutual shift found.
  - **🔗 החלפה משולשת** — 3-way chain (only for פנימית shifts): מתמחה moves שיקום→פנימית, תורן חוץ covers שיקום. Writes `swap_type='chain'` with `chain_ext` + `chain_ext_dept` columns.
- ⭐ pill shown on candidates/facilitators who submitted `בקשה` on the selected date.
- "🔄 בקש החלפה" button writes a row to `swap_requests` sheet with `status='pending'`.
- No auto-execution — admin must approve.

## Feature: Admin swap approval panel
- Location: `לוח שיבוץ` tab, below `draw_calendar_view()`.
- Loads `swap_requests` sheet and filters `status == 'pending'`.
- **✅ אשר** — moves the schedule rows (sets `is_manual=True`), updates `swap_requests` status to `approved`, reruns.
- **❌ דחה** — updates status to `rejected`, reruns.
- Success/reject messages use the session-state flag pattern (shown on next render).
- `swap_type='full'` swaps both directions; `swap_type='partial'` only reassigns the requester's shift.
- `swap_type='chain'` does 3 mutations: (1) remove requester from פנימית, (2) move מתמחה (candidate) from שיקום→פנימית, (3) assign תורן חוץ (chain_ext) to שיקום.

## Feature: ניתוח שימוש (user analytics)
- `analytics_log` sheet — append-only event log (never cleared). Written via `log_event()` using `ws.append_row()`.
- `log_event(event_type, detail_1, detail_2)` — defined right after `get_gspread_client()`. Entire body in `except Exception: pass` — never crashes the app.
- Session init on first render after login: `analytics_session_id` (uuid4), `analytics_login_time`, `analytics_tab_enter`, `analytics_device_captured=False`.
- Device capture: `st_javascript` keys `analytics_ua_cap` / `analytics_vp_cap` (frame 2 pattern). `login_success` fired only once per session when UA resolves.
- Events tracked: `login_success`, `login_fail`, `logout`, `tab_view` (enter + seconds on exit), `constraint_submit` (block count / wish count), `swap_search`, `swap_request_sent` (full/partial/chain).
- Admin analytics display: expander "📈 ניתוח שימוש במערכת" at bottom of `דוחות וניהול` tab. Sections A–I: KPI cards, per-user activity table, over-blocking bar chart (red >60%), tab usage, avg time-on-tab, login-by-hour heatmap, device breakdown, reload detection, submission timing.

## Feature: דוח בעיות צפויות headline
- Top of `דוחות וניהול` tab shows a live banner counting "ימי שיא חסימה" from the last saved report (קריטי / אזהרה counts) before the manual run button.
- Headline reads from the already-saved `daily_report` sheet — does not re-run analysis on load.

## Feature: סידור עבודה / גאנט חודשי (Daily Work Schedule)
A second module on top of the night-shift scheduler — covers daytime staffing for 3 depts (`שיקום גריאטרי א'`, `שיקום גריאטרי ב'`, `פנימית גריאטרית`).

### Tab structure (per role)
| Role | Tabs |
|---|---|
| מנהל על | הגדרות \| סידור תורנויות \| צוות \| דוחות וניהול \| **גאנט חודשי** \| **סידור עבודה** \| **ניהול בקשות** |
| מנהל/ת | הגדרות \| **גאנט חודשי** \| **סידור עבודה** |
| מנהל מחלקה | הגדרות \| **סידור עבודה** \| **ניהול בקשות** |
| מתמחה / רופא בכיר | הגדרות \| (סידור תורנויות) \| הגשת בקשות \| **סידור עבודה** |
| תורן חוץ | הגדרות \| סידור תורנויות \| הגשת בקשות |

### Tab access details
- **"הגשת בקשות"** — UNIFIED tab (night constraints + day absences, role-gated):
  - מתמחה: 🌙 night constraints + ☀️ day absences (both sections)
  - תורן חוץ: 🌙 night constraints only
  - רופא בכיר: ☀️ day absences only
  - מנהל מחלקה / מנהל/ת / מנהל על: **not shown** (managers handle absences via ניהול בקשות)
- **"גאנט חודשי"** (was "סידור חודשי") — מנהל/ת + מנהל על only:
  - 5 sub-tabs: שיבוץ חודשי / לוח עבודה כללי / כל הבקשות / צור סידור / ייצוא
  - Top-level month selector (`view_month`) + "הפוך לחודש פעיל" button
- **"סידור עבודה"** (was "סידור יומי") — all roles except תורן חוץ:
  - מנהל על / מנהל/ת: dept selector + editable grid + export buttons (no sub-tabs)
  - מנהל מחלקה: editable grid for own dept(s) + export buttons (no sub-tabs)
  - מתמחה / רופא בכיר: read-only personal calendar (לוח עבודה שלי)
- **"ניהול בקשות"** — מנהל על + מנהל מחלקה only (single page, no sub-tabs):
  - Section 1: pending absence requests (with dept filter for admin)
  - Section 2: all future approved requests (end_date ≥ today), sorted by dept + date
  - Section 3: add pre-approved absence for any employee (status=approved immediately)

### Day-absence calendar UI ("הגשת בקשות" → ☀️ section)
Calendar shows ONLY absence-related states — **no night shifts, no אחרי תורנות**:
- 🔵 חופש מאושר (includes pre-approved חופש עתידי)
- 🟡 202 מאושר
- 🔘 בקשה ממתינה
- ⬜ פנוי (clickable for new request)
- ▶ / ✓ — current range being selected
Submission dropdown has only **two types**: "חופש" / "202". Range select via 1st-click=start, 2nd-click=end.
Submission writes to `absence_requests` (status=pending) + emails the matching מנהל מחלקה via `send_notification_email()`.
Gate: `daily_requests_open` setting. Admin opens/closes via 🔓/🔒 button in שיבוץ חודשי sub-tab.

### Department-grid editing (לוח מחלקה / לוח עבודה כללי)
- One row per employee × one column per day. Cell shows status (עובד/חופש/202/אחרי/אחר), clicking cycles through statuses.
- Any manual edit writes `is_manual=True` to `work_schedule_daily` — these rows are **never overwritten** by the schedule generator.
- מנהל מחלקה appears as a row in the grid even without a `dept_rotation` row (their dept is read from `manage_depts`). They can "plant" themselves directly without going through the absence-request workflow.

### Schedule generation (`_generate_work_schedule`)
- Triggered by admin via "צור סידור" button.
- For each (employee, day) in the month based on `dept_rotation`:
  - **Priority 1**: approved absence covers this day → status = type
  - **Priority 2**: night shift on day-1 (in `schedule` sheet, excluding שישי בוקר) → status = "אחרי תורנות"
  - Else → status = "עובד"
- Preserves all rows where `is_manual=True`.

### Settings keys
- `daily_active_month` — int 1..12, the live month employees are submitting for.
- `daily_requests_open` — "True"/"False" string, gate for חופש/202 submissions. Auto-reset to "True" when admin changes `daily_active_month` via the "הפוך לחודש פעיל" button. חופש עתידי bypasses the gate (always submittable).
- Read with `_get_setting(key, default)` helper, write with `_set_setting(key, value)`.

### Email notifications
- `send_notification_email(to_address, subject, body_html)` — defined right after `get_gspread_client()`. Uses stdlib `smtplib`+`email.mime`. Wrapped in `except Exception: pass` — never crashes the app.
- Reads SMTP creds from `[email]` section in `secrets.toml` (`smtp_server`, `smtp_port`, `sender_address`, `sender_password`). Silently skips if not configured.
- Triggers: (1) employee submits absence → manager email, (2) approve/reject → requester email.

### Helpers
- `_get_setting(key, default)` / `_set_setting(key, value)` — settings sheet read/write
- `_approve_request(req_id, responder)` / `_reject_request(req_id, responder)` — wrap `_update_absence_status()` which updates row + emails requester
- `_generate_work_schedule(year_month, view_month)` — main scheduler
- `_wsd_get_status(date_str, employee, default)` / `_wsd_upsert(date, emp, dept, status, is_manual, note)` — work_schedule_daily I/O
- `_render_dept_grid(dept_name, year_month, view_month, key_ns, employees, max_days, allow_temp_add=False)` — shared editable grid (admin + manager use it). Pass `allow_temp_add=True` to show the "העברה זמנית" form at the bottom — lets admin/manager add any staff member to the grid for the current session (stored in `st.session_state[f"temp_emps_{key_ns}"]`).
- `_export_dept_grid(dept_name, year_month, view_month)` — writes wide-format `WSD_<dept>_<year_month>` sheet
- `_export_schedule_wide(view_month)` — old Schedule_Export wide-format export, **moved to "לוח שיבוץ" tab** (was previously in "דוחות וניהול → ייצוא נתונים")

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
