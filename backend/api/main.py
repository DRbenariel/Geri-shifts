"""FastAPI layer over geri_core (SCREENS_PLAN §3, build step A + read-only step C).

Every request builds a fresh DataContext from the store and runs one core
function. Permissions are checked here, on the server, from the role in the
staff sheet, never from anything the client sends.

Run locally:  uvicorn api.main:app --reload   (from backend/, env vars per api/config.py)
"""
from __future__ import annotations

import math
import re
import threading
import time
from datetime import date
from urllib.parse import quote

import gspread
import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from geri_core import DataContext, GSheetStore
from geri_core import absences, admin, daily, exports, night, people, reports, staff
from geri_core.constants import DAILY_DEPTS_ALL, default_tab_for_role, tabs_for_role

from . import session
from .config import Settings
from .mailer import SmtpMailer
from .store import READ_ONLY_MSG, CacheClearingStore, ReadOnlyError, ReadOnlyStore

QUOTA_BACKOFF = 15
SHEETS_BUSY_MSG = "המערכת עמוסה כרגע. נסה/י שוב בעוד דקה."

# Hebrew tab names (geri_core.constants) → keys the ui-v2 frontend routes by (ui-v2/lib/roles.ts).
TAB_KEYS = {'הגדרות': 'settings', 'סידור תורנויות': 'night', 'הגשת בקשות': 'submit', 'צוות': 'staff',
            'דוחות וניהול': 'reports', 'סידור כוננויות': 'oncall', 'גאנט חודשי': 'gantt',
            'סידור עבודה': 'work', 'ניהול בקשות': 'requests'}
ADMINS = ('מנהל על', 'מנהל/ת')
YM = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def _plain(v):
    """pandas / numpy values → JSON-safe Python."""
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_plain(x) for x in v]
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, float) and math.isnan(v):
        return None
    if v is pd.NaT:
        return None
    if isinstance(v, (pd.Timestamp, date)):
        return v.isoformat()[:10]
    return v


class Plain(JSONResponse):
    def render(self, content) -> bytes:
        return super().render(_plain(content))


class Me(BaseModel):
    name: str
    role: str


class LoginBody(BaseModel):
    username: str
    password: str


def _day_note(ctx, emp: str, ds: str) -> str:
    """The note behind an absent day: a manual WSD note, else the approved request's note (e.g. "מילואים")."""
    note = daily.wsd_get_note(ctx, ds, emp)
    if note:
        return note
    ar = ctx.absence_requests
    if ar.empty or 'employee' not in ar.columns:
        return ''
    m = ar[(ar['employee'].astype(str).str.strip() == emp) & (ar['status'].astype(str).str.lower() == 'approved')
           & (ar['start_date'].astype(str) <= ds) & (ar['end_date'].astype(str) >= ds)]
    return '' if m.empty else str(m.iloc[0].get('notes', '') or '').strip()


def _gantt_json(g: dict, ctx=None, y: int = 0, m: int = 0) -> dict:
    """absence_gantt keys conflicts by (dept, day) tuples, which JSON can't hold; also attach each day's note."""
    notes = {}
    if ctx is not None:
        for emps in g['by_dept'].values():
            for emp, items in emps.items():
                for day, _st in items:
                    n = _day_note(ctx, emp, f"{y}-{m:02d}-{day:02d}")
                    if n:
                        notes.setdefault(emp, {})[str(day)] = n
    return {'by_dept': g['by_dept'], 'notes': notes,
            'conflicts': [{'dept': d, 'day': day, 'employees': es} for (d, day), es in g['conflicts'].items()]}


def _shift_split(ctx, y: int, m: int) -> list:
    """Per employee: שיקום nights, פנימית nights, שישי בוקר (any dept); busiest first."""
    s = ctx.schedule
    if s.empty:
        return []
    mon = s[s['date'].astype(str).str.startswith(f"{y}-{m:02d}") & (s['employee'].astype(str).str.strip() != '---')]
    out = {}
    for _, r in mon.iterrows():
        e = str(r['employee']).strip()
        dept = str(r['dept'])
        k = 'fri' if 'שישי בוקר' in dept else 'sh' if dept == 'שיקום' else 'pn'
        out.setdefault(e, {'employee': e, 'sh': 0, 'pn': 0, 'fri': 0})[k] += 1
    return sorted(out.values(), key=lambda d: -(d['sh'] + d['pn'] + d['fri']))


def _ym(ym: str) -> tuple[int, int]:
    m = YM.match(ym)
    if not m:
        raise HTTPException(400, "חודש לא תקין (YYYY-MM)")
    return int(m.group(1)), int(m.group(2))


def _manager_dept(ctx, me, dept: str):
    """404 for an unknown dept; a מנהל מחלקה only for the depts they manage."""
    if dept not in DAILY_DEPTS_ALL:
        raise HTTPException(404, "מחלקה לא קיימת")
    if me.role not in ADMINS and dept not in people.managed_depts(ctx, me.name):
        raise HTTPException(403, "אין הרשאה למחלקה זו")


def create_app(settings: Settings | None = None, store_factory=None) -> FastAPI:
    settings = settings or Settings.from_env()
    if store_factory is None:
        # One store for the app's lifetime: gspread auth + open_by_url cost ~3 s, so not per request.
        shared = GSheetStore(settings.credentials, settings.spreadsheet_url)

        def store_factory():
            return shared
    app = FastAPI(title="Geri-shifts API", default_response_class=Plain, docs_url=None, redoc_url=None)
    staff.use_legacy_hashes(settings.streamlit_parallel)
    mailer = SmtpMailer(settings.smtp_user, settings.smtp_password) if settings.smtp_user else None

    # The Sheets quota is 60 reads/min for the service account, shared with Streamlit, and one screen
    # fires several /api calls at once. So one load is shared for cache_seconds; the lock makes
    # concurrent requests wait for that load instead of each starting its own. Writes clear it; `gen`
    # stops a load that started before a write from caching pre-write data. After a 429 nothing calls
    # Sheets for QUOTA_BACKOFF s (stale frames are served if any), so queued requests can't each
    # retry and keep the shared quota exhausted.
    cache = {'frames': None, 'at': 0.0, 'gen': 0, 'failed_at': None}
    cache_lock = threading.Lock()

    def clear_cache():
        cache['gen'] += 1
        cache['frames'] = None

    def load_frames(store) -> dict:
        now = time.monotonic()
        if cache['frames'] is not None and now - cache['at'] < settings.cache_seconds:
            return cache['frames']
        if cache['failed_at'] is not None and now - cache['failed_at'] < QUOTA_BACKOFF:
            if cache['frames'] is not None:
                return cache['frames']
            raise HTTPException(503, SHEETS_BUSY_MSG)
        gen = cache['gen']
        try:
            read_many = getattr(store, 'read_many', None)
            frames = read_many(DataContext.FRAMES) if read_many else {n: store.read(n) for n in DataContext.FRAMES}
        except gspread.exceptions.APIError as e:
            if e.response.status_code != 429:
                raise
            cache['failed_at'] = time.monotonic()
            if cache['frames'] is not None:
                return cache['frames']
            raise HTTPException(503, SHEETS_BUSY_MSG)
        cache['failed_at'] = None
        if cache['gen'] == gen:
            cache['frames'], cache['at'] = frames, time.monotonic()
        return frames

    def get_ctx() -> DataContext:
        store = store_factory()
        store = CacheClearingStore(ReadOnlyStore(store) if settings.read_only else store, clear_cache)
        with cache_lock:
            frames = {n: df.copy() for n, df in load_frames(store).items()}
        return DataContext.from_frames(frames, store=store, mailer=mailer)

    def session_name(request: Request) -> str:
        name = session.verify(settings.session_secret, request.cookies.get(session.COOKIE))
        if not name:
            raise HTTPException(401, "יש להתחבר מחדש")
        return name

    # session_name is listed before ctx so a missing/bad cookie is refused before any Sheets read.
    def current_user(name: str = Depends(session_name), ctx: DataContext = Depends(get_ctx)) -> Me:
        row = people.staff_row(ctx, name)
        if row is None:                       # removed from the staff sheet since login
            raise HTTPException(401, "יש להתחבר מחדש")
        return Me(name=name, role=str(row.get('type', '')))

    def require(*roles):
        def dep(me: Me = Depends(current_user)) -> Me:
            if me.role not in roles:
                raise HTTPException(403, "אין הרשאה")
            return me
        return dep

    # Read-only phase: refuse writes up front (the ReadOnlyStore below is the second line of defence),
    # so e.g. a 38-second auto-schedule doesn't run only to fail at the save.
    @app.middleware("http")
    async def _read_only_gate(request: Request, call_next):
        if (settings.read_only and request.method in ("POST", "PUT", "DELETE")
                and request.url.path not in ("/api/auth/login", "/api/auth/logout")):
            return Plain({"detail": READ_ONLY_MSG}, status_code=403)
        return await call_next(request)

    @app.exception_handler(gspread.exceptions.APIError)
    async def _sheets(_, exc):
        if exc.response.status_code == 429:     # a write still over quota after the store's retries
            return Plain({"detail": SHEETS_BUSY_MSG}, status_code=503)
        raise exc

    @app.exception_handler(ReadOnlyError)
    async def _ro(_, exc):
        return Plain({"detail": str(exc)}, status_code=403)

    @app.exception_handler(PermissionError)
    async def _perm(_, exc):
        return Plain({"detail": str(exc) or "אין הרשאה"}, status_code=403)

    @app.exception_handler(ValueError)
    async def _val(_, exc):
        return Plain({"detail": str(exc)}, status_code=400)

    # ── auth ───────────────────────────────────────────────────────────
    @app.post("/api/auth/login")
    def login(body: LoginBody, response: Response, ctx: DataContext = Depends(get_ctx)):
        try:
            # No SHA-256 → bcrypt upgrade while Streamlit runs in parallel: it can only read SHA-256.
            who = staff.login(ctx, body.username, body.password, upgrade_hash=not settings.streamlit_parallel)
        except staff.AuthError as e:
            raise HTTPException(401, str(e))
        response.set_cookie(session.COOKIE, session.sign(settings.session_secret, who['name']),
                            max_age=session.MAX_AGE, httponly=True, secure=settings.cookie_secure,
                            samesite="lax", path="/")
        return _me_payload(ctx, Me(**who))

    @app.post("/api/auth/logout")
    def logout(response: Response):
        response.delete_cookie(session.COOKIE, path="/")
        return {"ok": True}

    def _me_payload(ctx, me: Me) -> dict:
        tabs = tabs_for_role(me.role)
        row = people.staff_row(ctx, me.name)
        return {"name": me.name, "role": me.role,
                "tabs": [TAB_KEYS[t] for t in tabs], "home": TAB_KEYS[default_tab_for_role(me.role)],
                "manage_depts": people.managed_depts(ctx, me.name) if me.role == 'מנהל מחלקה' else [],
                "monthly_quota": row.get('monthly_quota', '') if row is not None else '',
                "weekend_quota": row.get('weekend_quota', '') if row is not None else '',
                "settings": admin.active_months(ctx), "read_only": settings.read_only}

    @app.get("/api/me")
    def me(me: Me = Depends(current_user), ctx: DataContext = Depends(get_ctx)):
        return _me_payload(ctx, me)

    # ── night shifts ───────────────────────────────────────────────────
    @app.get("/api/night/{ym}")
    def night_month(ym: str, me: Me = Depends(require('מנהל על', 'מתמחה', 'תורן חוץ')),
                    ctx: DataContext = Depends(get_ctx)):
        y, m = _ym(ym)
        # Non-admins get only their own rows and unfilled slots; blockers/wishers stay admin-only.
        return night.night_calendar(ctx, y, m, me.name, is_admin=me.role == 'מנהל על')

    @app.get("/api/swaps/pending")
    def swaps_pending(_: Me = Depends(require('מנהל על')), ctx: DataContext = Depends(get_ctx)):
        return night.pending_swap_requests(ctx)

    # ── daily work schedule ────────────────────────────────────────────
    # Declared before /api/work/{dept}/{ym}, which would otherwise capture "me" as a dept.
    @app.get("/api/work/me/{ym}")
    def my_dept(ym: str, me: Me = Depends(require('מתמחה', 'רופא בכיר')), ctx: DataContext = Depends(get_ctx)):
        _ym(ym)
        return {"dept": people.employee_dept_for_month(ctx, me.name, ym)}

    @app.get("/api/work/{dept}/{ym}")
    def work_grid(dept: str, ym: str, me: Me = Depends(current_user), ctx: DataContext = Depends(get_ctx)):
        y, m = _ym(ym)
        if dept not in DAILY_DEPTS_ALL:
            raise HTTPException(404, "מחלקה לא קיימת")
        if me.role in ADMINS:
            pass
        elif me.role == 'מנהל מחלקה':
            if dept not in people.managed_depts(ctx, me.name):
                raise HTTPException(403, "אין הרשאה למחלקה זו")
        elif me.role in ('מתמחה', 'רופא בכיר'):
            if people.employee_dept_for_month(ctx, me.name, ym) != dept:
                raise HTTPException(403, "אפשר לצפות רק במחלקה שלך")
        else:
            raise HTTPException(403, "אין הרשאה")
        include = me.name if me.role == 'מנהל מחלקה' else None
        emps = people.grid_employees(ctx, dept, ym, include_user=include)
        grid = daily.dept_grid(ctx, dept, ym, m, emps, year=y)
        can_edit = me.role in ADMINS + ('מנהל מחלקה',)
        grid['editable'] = can_edit and not settings.read_only
        # The "העברה זמנית" form (Streamlit: allow_temp_add on the admin and manager grids) shows by role, also
        # while read-only, so it can be reviewed; adding then gets the read-only notice like every other write.
        grid['transfer_candidates'] = daily.transfer_candidates(ctx, dept, ym) if can_edit else None
        return grid

    # ── Excel exports (reads only, so they work in read-only mode) ─────
    def _xlsx(data, fname):
        if not data:
            raise HTTPException(404, "אין שיבוצים לייצוא לחודש זה")
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f"attachment; filename=\"export.xlsx\"; filename*=UTF-8''{quote(fname)}"})

    @app.get("/api/export/work/{dept}/{ym}")
    def export_dept(dept: str, ym: str, me: Me = Depends(require(*ADMINS, 'מנהל מחלקה')), ctx: DataContext = Depends(get_ctx)):
        y, m = _ym(ym)
        _manager_dept(ctx, me, dept)
        return _xlsx(*exports.dept_batched_excel(ctx, dept, ym, m, year=y))

    @app.get("/api/export/work-all/{ym}")
    def export_all(ym: str, _: Me = Depends(require(*ADMINS)), ctx: DataContext = Depends(get_ctx)):
        y, m = _ym(ym)
        return _xlsx(*exports.all_depts_batched_excel(ctx, ym, m, year=y))

    @app.get("/api/export/me/{ym}")
    def export_mine(ym: str, me: Me = Depends(require('מתמחה', 'רופא בכיר')), ctx: DataContext = Depends(get_ctx)):
        y, m = _ym(ym)
        return _xlsx(*exports.personal_excel(ctx, me.name, m, daily_dept=people.employee_dept_for_month(ctx, me.name, ym) or None, year=y))

    # ── absences ───────────────────────────────────────────────────────
    @app.get("/api/absences/pending")
    def absences_pending(dept: str | None = None, me: Me = Depends(require(*ADMINS, 'מנהל מחלקה')),
                         ctx: DataContext = Depends(get_ctx)):
        if me.role == 'מנהל מחלקה':
            return absences.pending_requests(ctx, manager=me.name)
        return absences.pending_requests(ctx, dept_filter=dept)

    @app.get("/api/absences/gantt/{ym}")
    def absences_gantt(ym: str, dept: str | None = None, me: Me = Depends(require(*ADMINS, 'מנהל מחלקה')),
                       ctx: DataContext = Depends(get_ctx)):
        y, m = _ym(ym)
        if me.role == 'מנהל מחלקה':
            mine = people.managed_depts(ctx, me.name)
            if dept and dept not in mine:
                raise HTTPException(403, "אין הרשאה למחלקה זו")
            return {d: _gantt_json(absences.absence_gantt(ctx, y, m, dept_filter=d), ctx, y, m) for d in ([dept] if dept else mine)}
        return _gantt_json(absences.absence_gantt(ctx, y, m, dept_filter=dept), ctx, y, m)

    @app.get("/api/absences/me/{ym}")
    def my_absences(ym: str, me: Me = Depends(require('מתמחה', 'רופא בכיר')), ctx: DataContext = Depends(get_ctx)):
        y, m = _ym(ym)
        return {"calendar": absences.my_absence_calendar(ctx, me.name, y, m),
                "history": absences.my_absence_history(ctx, me.name)}

    # ── admin screens ──────────────────────────────────────────────────
    @app.get("/api/gantt/{ym}")
    def gantt(ym: str, _: Me = Depends(require(*ADMINS)), ctx: DataContext = Depends(get_ctx)):
        _ym(ym)
        return {"rows": admin.gantt_rows(ctx, ym), "summary": admin.gantt_summary(ctx, ym)}

    @app.get("/api/oncall/{ym}")
    def oncall(ym: str, _: Me = Depends(require(*ADMINS)), ctx: DataContext = Depends(get_ctx)):
        y, m = _ym(ym)
        return {"days": admin.konenut_month(ctx, y, m), "doctors": admin.konenut_doctors(ctx)}

    @app.get("/api/staff")
    def staff_table(_: Me = Depends(require('מנהל על')), ctx: DataContext = Depends(get_ctx)):
        return staff.staff_view(ctx)

    @app.get("/api/special-days")
    def special_days(_: Me = Depends(current_user), ctx: DataContext = Depends(get_ctx)):
        sd = ctx.special_days
        return [] if sd.empty else sd.to_dict('records')

    @app.get("/api/reports/{ym}")
    def report(ym: str, _: Me = Depends(require('מנהל על')), ctx: DataContext = Depends(get_ctx)):
        y, m = _ym(ym)
        return {"submissions": reports.submission_status(ctx, y, m),
                "shift_counts": _shift_split(ctx, y, m),
                "problems": reports.problem_report(ctx),
                "fairness": reports.fairness(ctx)}          # all history, not this month (as in Streamlit)

    @app.get("/api/swaps/mine")
    def my_upcoming(me: Me = Depends(current_user), ctx: DataContext = Depends(get_ctx)):
        return night.upcoming_shifts(ctx, me.name)

    @app.get("/api/people")
    def people_list(me: Me = Depends(require(*ADMINS, 'מנהל מחלקה')), ctx: DataContext = Depends(get_ctx)):
        """Names and roles for pickers (no emails or passwords). Department managers get their own staff."""
        sf = ctx.staff
        rows = [{'name': str(r['name']).strip(), 'type': str(r.get('type', '')).strip()} for _, r in sf.iterrows()
                if str(r.get('name', '')).strip() and str(r['name']).strip() != '---']
        if me.role == 'מנהל מחלקה':
            _, _, emps = absences.manager_scope(ctx, me.name)
            rows = [r for r in rows if r['name'] in emps or r['name'] == me.name]
        return rows

    from .writes import register_writes
    register_writes(app, settings, get_ctx, current_user, require)

    @app.get("/api/health")
    def health():
        return {"ok": True, "read_only": settings.read_only}

    return app


def _lazy_app():
    # Uvicorn entry point; built on import only when env vars are present.
    try:
        return create_app()
    except RuntimeError:
        return None


app = _lazy_app()
