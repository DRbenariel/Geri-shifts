# Geri-shifts: deploying the new UI

Status: proposal, revised 2026-10-18. Route chosen by Ben: **Cloudflare Pages + Google Cloud Run**, aiming for about $0 a month. The mockup in this folder uses fictional data. Nothing here touches the live Streamlit app or the Google Sheet.

Earlier draft (2026-10-06) recommended Vercel Pro at $20/month. Dropped: Vercel Hobby is free but limited to non-commercial personal use, which a hospital department tool may not meet, and it gives the scheduler only 1 vCPU.

## Recommendation

- **Frontend:** the static Next.js export from this folder on **Cloudflare Pages** (free plan, commercial use allowed, no bandwidth cap).
- **API:** a small FastAPI service that reuses the existing scheduling logic, in a Docker image on **Google Cloud Run, region `me-west1` (Tel Aviv)**.
- **Data:** Google Sheets stays the database, same service account, same schema.
- Streamlit Cloud keeps running in parallel until the new site has proven itself.

Figures to verify on the providers' pricing pages before signing up (from memory, not re-checked on 2026-10-18):

| Item | Free allowance | Geri-shifts need |
|---|---|---|
| Cloudflare Pages | 500 builds/month, unlimited static requests and bandwidth | a few builds a week |
| Pages Functions (the `/api` proxy, below) | 100,000 requests/day on Workers free | far below |
| Cloud Run (request-based billing) | about 2M requests, 180,000 vCPU-seconds, 360,000 GiB-seconds per month per billing account; confirm `me-west1` is covered | about 20 users; CP-SAT runs of up to 38 s × 4 vCPU |
| Artifact Registry (the API image) | 0.5 GB storage | ortools + pandas image is likely 0.5 to 1 GB, so a few cents a month |

Expected cost: **about $0 to $1 a month, not exactly $0.** Cloud Run needs a GCP billing account (credit card) even inside the free tier. Add a $1 budget alert on day one.

## Architecture

```
browser ──HTTPS──> Cloudflare Pages  (one origin: <project>.pages.dev or a custom domain)
                    ├─ static UI (ui-v2/out)
                    └─ /api/*  Pages Function ──proxy──> Cloud Run, me-west1
                                                        FastAPI (Python)
                                                         ├─ auth: login → signed httpOnly session cookie
                                                         ├─ role check on every route (server side)
                                                         ├─ scheduling_core/ (logic lifted from appy.py)
                                                         └─ gspread ──> Google Sheets (unchanged schema)
GitHub Actions ── daily_report.py ──> Sheets   (unchanged)
Gmail SMTP <── API (absence notifications)      (unchanged)
```

### Why `/api` goes through a Pages Function

`*.pages.dev` and `*.run.app` are both on the Public Suffix List, so the UI and the API on their default URLs are different sites. A session cookie set by the API would be a third-party cookie, and Safari (every iPhone) blocks those: login would fail for most doctors.

Fix: `ui-v2/functions/api/[[path]].ts`, a Pages Function that forwards every `/api/*` request to the Cloud Run URL (stored in a Pages environment variable) and passes the response, including `Set-Cookie`, back unchanged. The browser only ever talks to one origin.

To verify before building:
- Pages `_redirects` can't proxy to an external host (I believe it only redirects), which is why this needs a Function.
- Cloud Run domain mapping isn't available in every region, and `me-west1` may not have it. The alternative, a global load balancer, costs about $18/month. The proxy avoids both.

### Cloud Run settings

- **CPU for CP-SAT:** set `--cpu=4 --memory=2Gi` and `num_workers` to the same vCPU count (today 4). Keep the 28 s / 10 s time limits; the request timeout (default 300 s, max 60 min) covers them.
- **Background threads must go.** With request-based billing, CPU is throttled once the response is sent. `_save_async` (`appy.py:3059`), the analytics writes and the absence emails become synchronous calls inside the request.
- **Cold start:** with min-instances 0, the first request after idle loads ortools and pandas and takes several seconds. Accept that for the pilot; min-instances 1 removes it but costs money.
- **Credentials:** run the service as the existing `gerishifts` service account and use default credentials, so no JSON key is passed around. Fallback: the `GSHEETS_CREDENTIALS` variable that `daily_report.py` already reads, stored in Secret Manager.
- **Other secrets** (Secret Manager or Cloud Run env vars): `SPREADSHEET_URL`, `SMTP_USER` / `SMTP_PASSWORD`, `SESSION_SECRET`.
- Nothing secret goes in the repo. The JSON key file stays gitignored (checked: not tracked).

### Data residency

Computing in `me-west1` keeps processing in Israel. The data at rest stays in Google Sheets, exactly as today. The hospital IT question becomes narrower ("is the Sheet acceptable, as it already is?"), not gone.

## Backend port (phase 2, before any real user sees the new UI)

**Status (2026-10-14): logic extracted.** `backend/geri_core` holds the Streamlit-free port, with parity tests against the original functions (see `backend/README.md`). Remaining for this phase: the thin FastAPI layer (`backend/api/`), auth/session, and deployment config (Dockerfile for Cloud Run, the Pages `/api` proxy). The screen-by-screen plan, with the endpoint for each action, is in `SCREENS_PLAN.md`.

Unchanged by the hosting choice. The logic lives in `appy.py` and reads Streamlit's session state 534 times. Port it in this order. `daily_report.py` is already Streamlit-free and is the template.

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
   - Login rate limit: a Cloudflare rate-limiting rule on `/api/login` (one rule is included in the free plan), plus a per-user lockout counter in the API.
6. **Analytics and email** move from background threads to inline calls (see Cloud Run settings). Same sheet columns, same SMTP.

Each endpoint gets a parity test: same input sheet → same output as the Streamlit function.

The mockup already defines the data shapes (`lib/mock.ts` mirrors `init_db`) and every screen. Wiring a screen means swapping `useStore()` mock calls for `fetch('/api/...')`.

## Rollout

| Step | What | Who | Exit criterion |
|---|---|---|---|
| 0 | Approve UI direction: mockup on a Pages preview link + the video | Ben | Go / changes |
| 1 | Backend port + parity tests; API deployed to Cloud Run; every push to a branch gets a Pages preview URL | dev | All parity tests green |
| 2 | Superadmin screens on live data (read-only first, then writes), Streamlit still primary | Ben | Ben runs a full month cycle (open month, auto-schedule, approvals) in the new UI |
| 3 | Other roles: מתמחה, תורן חוץ, רופא בכיר, מנהל מחלקה, מנהל/ת (each gets the tabs from `ui_components.render_navbar`) | dev | Role screens pass the parity checklist |
| 4 | Pilot: 2 to 3 people per role use the new link for one month; both apps share the same Sheet | pilot group | No blocking bugs, feedback addressed |
| 5 | Switch: send everyone the new link; Streamlit stays up as fallback for one month, then is retired | Ben | One quiet month |

Both apps write the same sheets, so during steps 2 to 4 don't edit the same month from both at the same time. Streamlit's 10-minute read cache can show stale data.

## What Ben needs to do

### Now: the mockup on Cloudflare Pages (step 0)

1. Create a free Cloudflare account.
2. Workers & Pages → Create → Pages → **Connect to Git** → `DRbenariel/Geri-shifts`. Use Git integration, not Direct Upload; as far as I know a Direct Upload project can't be switched to Git later.
3. Build settings:
   - Production branch: `ui-v2-mockup` (`main` has no `ui-v2/` folder yet, so a build from it would fail).
   - Framework preset: **None** (not "Next.js", which expects a server build).
   - Root directory: `ui-v2`
   - Build command: `npm run build`
   - Build output directory: `out`
   - Build watch paths: include `ui-v2/*`, so commits to `appy.py` don't trigger builds.
4. The `*.pages.dev` link is **public by default**. The mockup holds only fictional data, but to restrict it, put **Cloudflare Access** in front (Zero Trust free plan, up to 50 users, email one-time PIN). Required before any real data goes through it.

### Later: the API on Cloud Run (step 1)

1. In Google Cloud, use the project that owns the `gerishifts` service account, enable billing, add a $1 budget alert.
2. Enable Cloud Run, Artifact Registry and Secret Manager.
3. Decide the address: free `*.pages.dev`, or a custom domain (about $1 to 2 a month for a `.co.il`) added in Pages.
4. Confirm with hospital IT that the current Google Sheets storage is acceptable for the new app too (see Data residency).

## Cost (monthly, at current usage of about 20 users)

| Item | Cost |
|---|---|
| Cloudflare Pages + Pages Functions + Access (≤50 users) | $0 |
| Cloud Run inside the free tier, min-instances 0 | $0 |
| Artifact Registry storage over 0.5 GB | a few cents |
| Google Sheets API, Gmail SMTP, GitHub Actions | $0 |
| Domain (optional) | about $1 to 2 |

## Previewing the mockup locally

```bash
cd ui-v2
npm ci
npm run build                                  # static export to ./out
python -m http.server 3100 --directory out     # open http://localhost:3100
npm install --prefix scripts                   # once: recording tools (playwright-core, ffmpeg-static)
node scripts/record.mjs                        # re-record review/version-b.mp4
```

The recording tools live in `scripts/package.json`, outside the site build, so Pages builds don't download the 80 MB ffmpeg binary.
