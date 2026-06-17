# Deploying the new Flask app to Render

This replaces the Streamlit app. The Flask app (`frontend/`) serves the HTML UI
and a JSON API backed by the **same Google Sheet** the Streamlit app uses.

## 1. Local run (build + manual test before deploying)

```bash
pip install -r requirements-web.txt
export GSHEETS_CREDENTIALS="$(cat gerishifts-7ccae6b773f7.json)"   # service-account JSON
export FLASK_SECRET_KEY="$(python -c 'import secrets;print(secrets.token_hex(32))')"
# optional email:
export SMTP_SENDER="you@gmail.com" SMTP_PASSWORD="app-password"
python frontend/server.py        # → http://127.0.0.1:5000
```

Without credentials it boots in **DESIGN MODE** (reads → [], writes → no-op) so the
UI can be previewed, but login requires the real `staff` sheet.

### Manual test checklist (the M6 gate)
- [ ] Log in as one user of each of the 6 roles; wrong password rejected.
- [ ] Each role sees exactly its tabs and lands on its default tab.
- [ ] A low-privilege session calling an admin endpoint by hand → 403.
- [ ] Change password → re-login with the new password.
- [ ] Employee submits blocks+wishes → `requests` rows (אילוץ/בקשה); re-submit overwrites only that month.
- [ ] Employee submits absence → `pending` row + manager email; admin approve → `approved` + reflected in סידור עבודה generation.
- [ ] **Smart schedule** run writes `schedule` and **matches Streamlit** for the same month snapshot (parity test — see below).
- [ ] Swap search returns full/partial/chain; request → approve → schedule updated.
- [ ] `Schedule_Export` + `WSD_*` sheets written; daily_report GitHub Action still green.

### Parity test (schedule)
Snapshot `staff/requests/schedule/special_days/settings` for a real month, then run
both the Streamlit `run_smart_scheduling` and the Flask `/api/smart_schedule` on that
exact snapshot and diff the `(date, dept, employee)` tuples. They should match
(the Flask port drops only the UI swap-suggestion text, not any assignment).

## 2. Render setup

1. Push this branch and merge to `main` (or set `branch:` in `render.yaml`).
2. Render dashboard → **New → Blueprint** → select this repo (`render.yaml` is picked up).
3. Fill the `sync:false` env vars in the dashboard:
   - `GSHEETS_CREDENTIALS` — paste the full service-account JSON (the **same** value the
     `daily_report` GitHub Action secret uses).
   - `FLASK_SECRET_KEY` — `python -c "import secrets;print(secrets.token_hex(32))"`.
   - `SMTP_SENDER` / `SMTP_PASSWORD` — Gmail address + app password (optional; email
     silently disabled if unset).
4. Deploy. The start command is
   `gunicorn 'frontend.app:create_app()' --bind 0.0.0.0:$PORT --workers 1 --timeout 120`.

### Custom domain + HTTPS
Render dashboard → service → **Settings → Custom Domains** → add the domain → create the
CNAME at your DNS provider → Render auto-provisions a Let's Encrypt cert (HTTPS automatic).
`SESSION_COOKIE_SECURE=1` is already set so cookies are HTTPS-only in production.

## 3. Cutover from Streamlit
- Keep Streamlit Cloud running (read-only-ish) for a few days as rollback.
- Point users / the custom domain at the Render URL.
- The `daily_report` GitHub Action is **unchanged** and keeps writing the `daily_report`
  sheet on its cron.
- Once stable, retire the Streamlit Cloud app.

## Notes / not-yet-ported
- Admin **swap-approval UI** (endpoints exist: `/api/swaps`, `/api/swaps/approve|reject`).
- `WSD_*` export uses a simple employees×days grid (not appy's 3-section batched layout).
- Analytics dashboard (the `analytics_log` is written via `/api/log_event`; the admin
  charts view is not rebuilt).
