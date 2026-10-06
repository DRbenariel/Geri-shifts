# Geri-shifts: deploying the new UI

Status: proposal (2026-10-06). The mockup in this folder uses fictional data. Nothing here touches the live Streamlit app or the Google Sheet.

## Recommendation

**Run everything on Vercel, as one project with two parts:**
- the Next.js frontend from this folder;
- a small Python API (FastAPI) that reuses the existing scheduling logic.

Google Sheets stays the database, accessed with the same service account. Streamlit Cloud keeps running in parallel until the new site has proven itself.

Why Vercel can host the Python part (limits checked against Vercel docs on 2026-10-06):

| Need | Geri-shifts | Vercel limit | Fits? |
|---|---|---|---|
| Python bundle size (ortools, pandas, numpy, gspread, openpyxl) | about 200 MB unpacked | 500 MB for Python functions | Yes |
| Longest call: CP-SAT auto-schedule | up to 38 s (28 s + 10 s phases) | 300 s on every plan | Yes |
| Memory | under 1 GB | 2 GB (Hobby), 4 GB (Pro) | Yes |
| CPU for CP-SAT (`num_workers=4` today) | 4 threads preferred | 1 vCPU (Hobby), up to 2 vCPU (Pro) | Works, slower. Set `num_workers` to the vCPU count and keep the 28 s / 10 s time limits. |
| Background save thread (`_save_async`, `appy.py:3059`) | fire-and-forget | Work can't continue after the response is sent | Change needed: make writes synchronous. |

**Plan choice.**
- Vercel Hobby (free) is limited to personal, non-commercial use, which a hospital department tool may not qualify as.
- Use **Pro, at $20 per developer seat per month** (one seat). Viewers and site users don't need seats.
- A short pilot on a Pro trial is fine.

**Fallback: Google Cloud Run in `me-west1` (Tel Aviv, Tier 1 pricing).** Move the Python API there, and leave the frontend on Vercel, if any of these happen:
- cold starts of the Python bundle feel slow to users (likely a few seconds after idle);
- CP-SAT on 1 to 2 vCPU gives noticeably worse schedules;
- hospital IT requires compute hosted in Israel.

Cloud Run scales to zero, so cost stays near zero, but the GCP project needs billing enabled even for the free tier. The API code is identical either way: the same FastAPI app, in a Docker image instead of a Vercel function.

## Architecture

```
browser ──HTTPS──> Vercel
                    ├─ Next.js (static UI, this folder)
                    └─ /api/*  FastAPI (Python)
                          ├─ auth: login → signed httpOnly session cookie
                          ├─ role check on every route (server side)
                          ├─ scheduling_core/ (logic lifted from appy.py)
                          └─ gspread ──> Google Sheets (unchanged schema)
GitHub Actions ── daily_report.py ──> Sheets   (unchanged)
Gmail SMTP <── API (absence notifications)      (unchanged)
```

- **Region:** the default function region is `iad1` (US East). Pick the Vercel region with the lowest latency from Israel, likely a European one such as `fra1` (Frankfurt); check this from the hospital network before launch.
- **Secrets:** Vercel environment variables (encrypted) hold:
  - `GSHEETS_CREDENTIALS`: the service-account JSON, the same variable `daily_report.py` already reads;
  - `SPREADSHEET_URL`;
  - `SMTP_USER` / `SMTP_PASSWORD`;
  - `SESSION_SECRET`.
- Nothing secret goes in the repo. The JSON key file stays gitignored.

## Backend port (phase 2, before any real user sees the new UI)

The logic lives in `appy.py` and reads Streamlit's session state 534 times. Port it in this order. `daily_report.py` is already Streamlit-free and is the template.

1. **Data layer.**
   - A `DataContext` loads all sheets once per request: staff, schedule, requests, special_days, dept_rotation, absence_requests, work_schedule_daily, konenut, swap_requests, settings.
   - Writes go through one `save(sheet, df)`, based on `save_to_db`. Retry on 429, 500, 502, 503 and 504, not only 429; that gap caused a login crash before.
   - Pin every version in the API's `requirements.txt`. Unpinned installs caused two production crashes in August.
2. **Pure functions, lifted as-is:**
   - `check_assignment_validity` (`appy.py:3460`);
   - day-type helpers (`3432`);
   - `_absence_conflicts` (`1616`);
   - dept-name normalizers (`61-116`).
3. **Refactor to take a `DataContext`:**
   - `_derive_auto_status` (`1831`). This is the single source of truth for daily status; the mockup's `lib/logic.ts` mirrors its priority order.
   - `find_swap_candidates` (`3544`).
   - `run_smart_scheduling_cp` (`4502`) plus the greedy fallback (`3978`).
   - The absence workflow (`221-380`).
   - `_generate_work_schedule` (`382`).
4. **Exports return file bytes:** the Excel builders (`587-1340`) become download endpoints. "Open in Sheets" keeps creating the `WSD_` tab. Decide whether the "anyone with the link" sharing (`_export_dept_to_new_gsheet`, `911`) should stay.
5. **Auth, which today exists only in the UI:**
   - Login checks the unsalted SHA-256 hash, then re-hashes with bcrypt on success. Old hashes upgrade silently.
   - Every API route checks the role from the session, not from the client.
   - Add a login rate limit with a Vercel WAF rule.
6. **Analytics and email** move from background threads to inline calls. Same sheet columns, same SMTP.

Each endpoint gets a parity test: same input sheet → same output as the Streamlit function.

The mockup already defines the data shapes (`lib/mock.ts` mirrors `init_db`) and every screen. Wiring a screen means swapping `useStore()` mock calls for `fetch('/api/...')`.

## Rollout

| Step | What | Who | Exit criterion |
|---|---|---|---|
| 0 | Approve UI direction (this mockup + video) | Ben | Go / changes |
| 1 | Backend port + parity tests; preview deploys on every push (Vercel gives each push a private preview URL) | dev | All parity tests green |
| 2 | Superadmin screens on live data (read-only first, then writes), Streamlit still primary | Ben | Ben runs a full month cycle (open month, auto-schedule, approvals) in the new UI |
| 3 | Other roles: מתמחה, תורן חוץ, רופא בכיר, מנהל מחלקה, מנהל/ת (each gets the tabs from `ui_components.render_navbar`) | dev | Role screens pass the parity checklist |
| 4 | Pilot: 2 to 3 people per role use the new link for one month; both apps share the same Sheet | pilot group | No blocking bugs, feedback addressed |
| 5 | Switch: send everyone the new link; Streamlit stays up as fallback for one month, then is retired | Ben | One quiet month |

Both apps write the same sheets, so during steps 2 to 4 don't edit the same month from both at the same time. Streamlit's 10-minute read cache can show stale data.

## Cost (monthly, at current usage of about 20 users)

| Item | Cost |
|---|---|
| Vercel Pro, 1 seat (functions, bandwidth and previews well inside included usage) | $20 |
| Google Sheets API, Gmail SMTP, GitHub Actions | $0 |
| Domain (optional, e.g. a `.co.il`) | about $1 to 2 |
| Fallback Cloud Run, only if used | about $0 to 5 |

## What Ben needs to do

1. Create or choose a Vercel account and connect the `DRbenariel/Geri-shifts` GitHub repo. Set the project root to `ui-v2/`.
2. Decide: Pro seat now, or Pro trial for the pilot.
3. Add the environment variables listed above in the Vercel dashboard.
4. Decide the address: the free `*.vercel.app` URL or a custom domain.
5. Confirm with hospital IT whether staff-scheduling data may be processed outside Israel. If not, use the Cloud Run `me-west1` fallback for the API.

## Previewing the mockup now

```bash
cd ui-v2
npm install
npm run build                                  # static export to ./out
python -m http.server 3100 --directory out     # open http://localhost:3100
node scripts/record.mjs                        # re-record review/version-b.mp4
```

The same `out/` folder can be deployed to Vercel as-is to share a private preview link.

Before connecting Vercel, move the recording tools (`playwright-core`, `ffmpeg-static`) out of `ui-v2/package.json` into a separate `scripts/` package. Vercel installs devDependencies on every build, and `ffmpeg-static` downloads an 80 MB binary.
