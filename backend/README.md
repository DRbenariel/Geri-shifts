# backend — `geri_core`

The business logic of `appy.py`, extracted so it runs **without Streamlit**. This is phase 2 of `ui-v2/DEPLOY_PLAN.md` ("Backend port"). The live Streamlit app is unchanged and does not import this package yet.

```bash
cd backend
pip install -r requirements.txt
python -m pytest tests -q      # 49 tests, about 2 minutes
```

## How it works

- `appy.py` kept all state in `st.session_state`. Here that state lives in a **`DataContext`**, which is built once per API request.
  - Build it with `DataContext.load(store)`. It reads every sheet and applies the same clean-up steps `appy.py` ran at session start.
  - Every logic function takes `ctx` as its first argument.
- All sheet access goes through a **`SheetStore`**. There are two:
  - `GSheetStore` uses gspread with the same service-account JSON.
  - `MemoryStore` keeps everything in memory, for tests and local previews.
- Writes call `ctx.save(sheet, df)`. The write is **synchronous** and follows the old `save_to_db` order: write first, then trim, never clear.
- Lookup indexes (`wsd_index`, `approved_map`) are rebuilt automatically when their source sheet changes. That replaces the manual `_rebuild_wsd_index()` and `_build_approved_map()` calls.
- Nothing in the package renders UI:
  - Functions that drove a Streamlit widget now return data. For example, `daily.dept_grid()` returns the department × month grid model, and the schedulers return a `SchedulingResult` with their messages.
  - Functions that changed data raise `ValueError` / `PermissionError` with the same Hebrew message the Streamlit version showed.

| Module | What's in it | From appy.py |
|---|---|---|
| `context` / `store` | Data loading, clean-up, indexes, sheet I/O with retries | 61-187, 3123-3257, 3704-3790 |
| `days` | Functional Friday / Saturday / weekend | 947-964, 3432-3458 |
| `people` | Gantt-first dept resolution, managers, role order, Gantt options | 753, 1542-1613, 1787-1815, 6132-6212 |
| `daily` | `derive_auto_status`, cell click/popover, temporary transfers, grid model | 1359-1538, 1758-1993, data side of 2046-2754 |
| `absences` | Day-absence submit / approve / reject / delete, migration, conflicts, absence Gantt | 221-380, 1616-1715, 2771-3006, inline 8008-9197 |
| `night` | `check_assignment_validity`, employee + admin swap search, swap requests, manual tool, cleanup | 3460-3701, inline 5215-5980, 6347-6849 |
| `scheduling` | Greedy and CP-SAT schedulers, Friday post-pass | 3978-4945 |
| `constraints` | Night constraint/wish rules + save | 3943-3976, 7145-7175, 8228-8406 |
| `staff` | Login, password change, staff table | 3260-3325, 6309-6345, 6849-7094 |
| `admin` | Settings, special days, on-call (כוננויות), monthly Gantt | 4948-5206, 6215-6276, 6493-6549, 7697-7955 |
| `exports` | Excel bytes, `Schedule_Export`, `WSD_` sheets | 587-945, 972-1356 |
| `reports` | Dashboard, fairness, problem scan, analytics A–I | 3007-3045, 7244-7694 |

## API (`api/`)

A thin FastAPI layer over `geri_core` (SCREENS_PLAN §3). Status 2026-10-19: login, session, the read endpoints and the write endpoints (`api/writes.py`), all behind the read-only switch.

- **Session:** `POST /api/auth/login` sets an httpOnly cookie signed with `SESSION_SECRET`. It holds only the user name; the role is read from the staff sheet on every request, so permissions can't be claimed by the client.
- **Permissions** are checked per route from that role (tabs per role as in `constants.tabs_for_role`; department managers only their `manage_depts`; interns and seniors only their own department; night-shift rows of others and who blocked/wished stay admin-only).
- **Read-only by default.** With `API_READ_ONLY=1` every POST/PUT/DELETE (except login/logout) is refused up front, and the store refuses writes as a second line of defence. Turn it off only after the write phase is signed off (DEPLOY_PLAN rollout step 2).
- **Passwords stay SHA-256 while Streamlit runs** (`STREAMLIT_PARALLEL=1`, default): no bcrypt upgrade on login, and changed or new passwords are SHA-256, because Streamlit can only read that format. Set `STREAMLIT_PARALLEL=0` when Streamlit is retired.
- **Write rules enforced on the server:** employees submit constraints only for the open night month and absences only for the daily active month; department managers approve, reject, delete and edit only within their departments; approving or adding an absence that overlaps returns `409` with the Streamlit question until it is sent again with `force`; a swap request is accepted only if the server's own search finds that option.
- **Email:** `SMTP_USER` / `SMTP_PASSWORD` (Gmail, as in Streamlit) send the absence notifications synchronously inside the request; without them mail is skipped.
- Env vars: see `api/config.py`. Local run: `uvicorn api.main:app --reload` from `backend/` with `COOKIE_SECURE=0`.
- Deploy: `Dockerfile` (Cloud Run, me-west1). The Cloudflare Worker proxies `/api/*` to it so the cookie stays first-party.
- Tests: `tests/test_api.py` (login, tabs per role, 403s, privacy of the night calendar, read-only guard, JSON for every read route) and `tests/test_api_writes.py` (read-only gate, SHA-256 kept, month and department scope, conflict confirmation, swap validation).
- Known cost: each request loads all 10 sheets. Fine for the pilot; add a short per-instance cache before the whole department uses it (Sheets API read quota).

## Tests

- **`tests/test_parity.py`** (17 tests) runs the original `appy.py` functions next to `geri_core` on the same data and requires identical output.
  - `tests/legacy.py` loads `appy.py` without Streamlit: it parses the file and keeps only the imports, constants and function definitions, backed by a stub `streamlit` module.
  - Covered:
    - every cell of `derive_auto_status` for every employee, day and department (3,900 cells);
    - 600 random validity checks;
    - both greedy-scheduler modes, plus a stressed month with empty slots and swap suggestions;
    - the employee swap search;
    - absence approve, reject, delete and migrate;
    - WSD edits;
    - every Excel export, compared cell by cell including fills and page breaks;
    - the `WSD_` and `Schedule_Export` sheets.
- **`tests/test_core.py`** (32 tests) covers logic that existed only inline in the UI code, so there is no legacy function to compare against. That includes login and the hash upgrade, the Gantt save and migration, swap approval, absence submission rules, CP-SAT hard constraints, on-call, settings, reports and tabs per role.
- `tests/fixtures.py` is a fictional dataset that includes the known data problems: a name with a trailing space, a geresh in `manage_depts`, `"True"`/`"False"` strings, legacy `dept_at_request` values, Friday-like and Saturday-like special days, transfers with sides, and managers planting themselves.
- `.github/workflows/backend_tests.yml` runs both files on every PR that touches `backend/` or `appy.py`. A change to `appy.py` that isn't mirrored here fails the parity tests.

## Intentional differences from appy.py

1. **Synchronous writes.** The background save queue (`_save_async`) is gone, because a serverless request (Cloud Run with request-based billing) loses its CPU once it responds. An approved absence that spans several days is now written in one batch instead of one write per day; the final sheet is the same.
2. **Retries.** Writes retry on 429 and on 500/502/503/504. Previously only reads retried on 5xx.
3. **Passwords.**
   - New hashes use bcrypt. Existing unsalted SHA-256 hashes still log in and are upgraded to bcrypt on the first successful login.
   - The default password for new staff (`1234`) is unchanged.
4. **Staff table save** keeps each password by employee name. A renamed row sends `_original_name` to keep its password. The Streamlit version matched passwords by row index, which could give one person another person's hash after rows were deleted or reordered.
5. **"Open in Sheets" export** no longer shares the whole spreadsheet as "anyone with the link can view" unless you pass `share_anyone=True`. Whether to keep that is still Ben's decision (DEPLOY_PLAN step 4).
6. **Schedulers return their messages** (balancing report, CP-SAT summary, fallback warnings) instead of calling `st.info`. CP-SAT time limits and worker count are parameters; the defaults are the old 28 s / 10 s / 4 workers.
7. **All years of `work_schedule_daily` are loaded.** See the data-loss bug below. Pass `wsd_year_prefix='2026'` only to reproduce the old behaviour.
8. **Role checks are not in the core.** The API layer must check the role on every route (DEPLOY_PLAN step 5). The core functions trust their caller, as the Streamlit tabs did.

## Legacy bugs found during the port

- **Data loss in `work_schedule_daily` (fixed).** `appy.py` loaded only rows whose date starts with `2026` (line 3783), but `_wsd_upsert` and the other write paths save the entire session table back over the sheet. The סידור עבודה month selector already reaches 2027. A 2027 edit (a manual cell, a transfer, an approved absence written to the grid) is saved once, then erased by the next write from any session that loaded after it. The port loads all years by default (difference 7). Fixed in the live app by PR #3 (merged).

The rest are kept as-is in the port, not fixed:


- **The 3-way chain swap (🔗 החלפה משולשת) never returns a result.** `find_swap_candidates` validates the intern for פנימית against a schedule that still contains their own שיקום shift that day, so the check always fails with "Already working this day". `test_find_swap_candidates_all_pnim` pins this behaviour. Fix: drop the intern's שיקום row before validating.
- **The auto-approve path for מנהל מחלקה absences can't be reached.** The code in the `הגשת בקשות` tab exists, but the navbar never shows that tab to this role. The port keeps the logic (`submit_day_absences(role='מנהל מחלקה')`) so the new UI can decide whether to expose it.
- `_generate_work_schedule` and `_export_dept_grid_excel` are never called. The first was not ported (statuses are derived live). The second was ported and tested in case the new UI wants the colour grid.
