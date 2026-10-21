"""Write endpoints (SCREENS_PLAN §3). Each route checks role and scope on the server.

While API_READ_ONLY=1 every one of these reaches the store and is refused there
(403 with an explanation), so they can ship before the write phase is approved.
"""
from __future__ import annotations

import os
from datetime import date

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from geri_core import DataContext
from geri_core import absences, admin, daily, exports, night, people, scheduling, staff
from geri_core.constants import (ALL_SHIFT_DEPTS, DAILY_DEPTS_ALL, PNIM_DEPT, PNIM_SIDES, SPECIAL_DAY_TYPES)
from geri_core.constraints import my_requests, save_requests
from geri_core.days import to_date

from .main import ADMINS, Me, _ym

EMPLOYEES = ('מתמחה', 'תורן חוץ')
DAILY_SUBMITTERS = ('מתמחה', 'רופא בכיר')


# ── bodies ───────────────────────────────────────────────────────────────────
class PasswordBody(BaseModel):
    current: str
    new: str
    confirm: str


class ConstraintsBody(BaseModel):
    blocked: list[int] = []
    wishes: list[int] = []
    employee: str | None = None          # מנהל על editing someone else


class DayAbsenceBody(BaseModel):
    vacation: list[int] = []
    days_202: list[int] = []


class FutureBody(BaseModel):
    start: str
    end: str
    note: str = ""


class ApproveBody(BaseModel):
    force: bool = False


class AddAbsenceBody(BaseModel):
    employee: str
    start: str
    end: str
    type: str = Field(pattern="^(חופש|202|היעדרות אחרת)$")
    note: str = ""
    force: bool = False


class CellBody(BaseModel):
    dept: str
    date: str
    employee: str
    status: str | None = None
    note: str = ""


class TransferBody(BaseModel):
    dept: str
    date: str
    employee: str
    side: str = ""


class GanttBody(BaseModel):
    assignments: dict[str, str]
    sides: dict[str, str] = {}


class OpenBody(BaseModel):
    open: bool


class MonthBody(BaseModel):
    month: int = Field(ge=1, le=12)


class OncallDay(BaseModel):
    date: str
    pnim_dr: str = ""
    rehab_dr1: str = ""
    rehab_dr2: str = ""


class OncallMonthBody(BaseModel):
    days: list[OncallDay]


class StaffAddBody(BaseModel):
    name: str
    type: str
    dept: str
    monthly_quota: int = 6
    weekend_quota: int = 1
    only_home: bool = False
    email: str = ""
    manage_depts: list[str] = []


class StaffTableBody(BaseModel):
    rows: list[dict]
    only_home: list[str] = []


class SpecialDayBody(BaseModel):
    date: str
    description: str
    day_type: str


class AutoBody(BaseModel):
    only_weekends: bool = False


class ClearBody(BaseModel):
    mode: str = Field(pattern="^(auto|all)$")


class SlotBody(BaseModel):
    date: str
    dept: str
    employee: str = ""


class SwapBody(BaseModel):
    date: str
    dept: str
    kind: str = Field(pattern="^(full|partial|chain)$")
    candidate: str
    chain_ext: str = ""


# ── helpers ──────────────────────────────────────────────────────────────────
def _date_in(ym: str, ds: str) -> str:
    try:
        d = date.fromisoformat(ds)
    except ValueError:
        raise HTTPException(400, "תאריך לא תקין")
    if ds[:7] != ym:
        raise HTTPException(400, "התאריך מחוץ לחודש")
    return d.isoformat()


def _iso(ds: str) -> str:
    try:
        return date.fromisoformat(ds).isoformat()
    except ValueError:
        raise HTTPException(400, "תאריך לא תקין")


def _night_ym(ctx) -> str:
    am = admin.active_months(ctx)
    return f"{am['active_year']}-{am['active_month']:02d}"


def _daily_ym(ctx) -> str:
    am = admin.active_months(ctx)
    return f"{am['daily_active_year']}-{am['daily_active_month']:02d}"


def _can_edit_dept(ctx, me: Me, dept: str):
    if dept not in DAILY_DEPTS_ALL:
        raise HTTPException(404, "מחלקה לא קיימת")
    if me.role in ADMINS:
        return
    if me.role == 'מנהל מחלקה' and dept in people.managed_depts(ctx, me.name):
        return
    raise HTTPException(403, "אין הרשאה למחלקה זו")


def _absence_row(ctx, req_id):
    df = ctx.absence_requests
    if df.empty or 'id' not in df.columns:
        raise HTTPException(404, "הבקשה לא נמצאה")
    m = df[df['id'].astype(str) == str(req_id)]
    if m.empty:
        raise HTTPException(404, "הבקשה לא נמצאה")
    return m.iloc[0]


def _swap_pending(ctx, idx: int):
    sr = ctx.swap_requests
    if sr.empty or idx not in sr.index or str(sr.loc[idx].get('status', '')).strip() != 'pending':
        raise HTTPException(404, "בקשת ההחלפה לא נמצאה או שכבר טופלה")


def register_writes(app, settings, get_ctx, current_user, require):
    any_user = Depends(current_user)
    ctx_dep = Depends(get_ctx)

    # ── own account ────────────────────────────────────────────────────
    @app.post("/api/me/password")
    def change_password(body: PasswordBody, me: Me = any_user, ctx: DataContext = ctx_dep):
        staff.change_password(ctx, me.name, body.current, body.new, body.confirm)
        return {"ok": True}

    # ── night constraints ──────────────────────────────────────────────
    @app.get("/api/constraints/{ym}")
    def get_constraints(ym: str, employee: str | None = None,
                        me: Me = Depends(require(*EMPLOYEES, 'מנהל על')), ctx: DataContext = ctx_dep):
        y, m = _ym(ym)
        who = employee if (employee and me.role == 'מנהל על') else me.name
        blocked, wishes = my_requests(ctx, who, y, m)
        return {"employee": who, "blocked": blocked, "wishes": wishes}

    @app.put("/api/constraints/{ym}")
    def put_constraints(ym: str, body: ConstraintsBody, me: Me = Depends(require(*EMPLOYEES, 'מנהל על')),
                        ctx: DataContext = ctx_dep):
        y, m = _ym(ym)
        if me.role == 'מנהל על':
            if not body.employee or people.staff_row(ctx, body.employee) is None:
                raise HTTPException(400, "יש לבחור עובד/ת")
            save_requests(ctx, body.employee, y, m, body.blocked, body.wishes, enforce_rules=False)
            return {"ok": True}
        if ym != _night_ym(ctx):
            raise HTTPException(403, "אפשר להגיש אילוצים רק לחודש הפתוח להגשה")
        save_requests(ctx, me.name, y, m, body.blocked, body.wishes, role=me.role)
        return {"ok": True}

    # ── day absences: employee side ────────────────────────────────────
    @app.post("/api/absences/me/{ym}")
    def submit_days(ym: str, body: DayAbsenceBody, me: Me = Depends(require(*DAILY_SUBMITTERS)),
                    ctx: DataContext = ctx_dep):
        y, m = _ym(ym)
        if ym != _daily_ym(ctx):
            raise HTTPException(403, "אפשר להגיש רק לחודש הפעיל")
        rows = absences.submit_day_absences(ctx, me.name, me.role, y, m, body.vacation, body.days_202,
                                            requests_open=admin.active_months(ctx)['daily_requests_open'])
        return {"saved": rows}

    @app.post("/api/absences/future")
    def submit_future(body: FutureBody, me: Me = Depends(require(*DAILY_SUBMITTERS)), ctx: DataContext = ctx_dep):
        return absences.submit_future_absence(ctx, me.name, _iso(body.start), _iso(body.end), 'חופש עתידי', body.note)

    # ── day absences: managers ─────────────────────────────────────────
    def _in_scope(ctx, me: Me, req_id: str, approved=False) -> bool:
        if me.role in ADMINS:
            return True
        if approved:
            ids = {r['id'] for r in absences.deletable_approved(ctx, people.managed_depts(ctx, me.name))}
        else:
            ids = {str(r.get('id')) for r in absences.pending_requests(ctx, manager=me.name)}
        return str(req_id) in ids

    managers = Depends(require(*ADMINS, 'מנהל מחלקה'))

    @app.post("/api/absences/{req_id}/approve")
    def approve(req_id: str, body: ApproveBody, me: Me = managers, ctx: DataContext = ctx_dep):
        row = _absence_row(ctx, req_id)
        if not _in_scope(ctx, me, req_id):
            raise HTTPException(403, "הבקשה אינה בהיקף שלך")
        conf = absences.conflicts_for_request(ctx, row)
        if conf and not body.force:
            # Same flow as Streamlit: show the question, approve again with force=true.
            raise HTTPException(409, absences.format_conflict_question(conf))
        absences.approve_request(ctx, req_id, me.name)
        return {"ok": True}

    @app.post("/api/absences/{req_id}/reject")
    def reject(req_id: str, me: Me = managers, ctx: DataContext = ctx_dep):
        _absence_row(ctx, req_id)
        if not _in_scope(ctx, me, req_id):
            raise HTTPException(403, "הבקשה אינה בהיקף שלך")
        absences.reject_request(ctx, req_id, me.name)
        return {"ok": True}

    @app.delete("/api/absences/{req_id}")
    def delete(req_id: str, me: Me = managers, ctx: DataContext = ctx_dep):
        _absence_row(ctx, req_id)
        if not _in_scope(ctx, me, req_id, approved=True):
            raise HTTPException(403, "הבקשה אינה בהיקף שלך")
        if not absences.delete_absence_request(ctx, req_id):
            raise HTTPException(400, "המחיקה נכשלה")
        return {"ok": True}

    @app.post("/api/absences")
    def add_absence(body: AddAbsenceBody, me: Me = managers, ctx: DataContext = ctx_dep):
        if people.staff_row(ctx, body.employee) is None:
            raise HTTPException(400, "עובד/ת לא נמצא/ה")
        if me.role == 'מנהל מחלקה':
            _, _, emps = absences.manager_scope(ctx, me.name)
            if body.employee.strip() not in emps and body.employee.strip() != me.name:
                raise HTTPException(403, "העובד/ת אינו/ה במחלקות שלך")
        start, end = _iso(body.start), _iso(body.end)
        dept = people.emp_dept_for_date(ctx, body.employee, to_date(start))
        conf = absences.absence_conflicts(ctx, body.employee, dept, to_date(start), to_date(end))
        if conf and not body.force:
            raise HTTPException(409, absences.format_conflict_question(conf))
        return absences.add_preapproved_absence(ctx, body.employee, start, end, body.type, body.note, me.name)

    # ── daily work grid ────────────────────────────────────────────────
    def _cell_target(ctx, me: Me, dept: str, ds: str, employee: str):
        _can_edit_dept(ctx, me, dept)
        ym = _iso(ds)[:7]
        include = me.name if me.role == 'מנהל מחלקה' else None
        rows = set(people.grid_employees(ctx, dept, ym, include_user=include)) | set(daily.incoming_transfers(ctx, dept, ym))
        if employee.strip() not in rows:
            raise HTTPException(400, "העובד/ת אינו/ה בסידור של המחלקה בחודש זה")

    edit_roles = Depends(require(*ADMINS, 'מנהל מחלקה'))

    @app.post("/api/work/cell/cycle")
    def cycle(body: CellBody, me: Me = edit_roles, ctx: DataContext = ctx_dep):
        _cell_target(ctx, me, body.dept, body.date, body.employee)
        return {"status": daily.cycle_cell(ctx, _iso(body.date), body.employee.strip(), body.dept)}

    @app.put("/api/work/cell")
    def set_cell(body: CellBody, me: Me = edit_roles, ctx: DataContext = ctx_dep):
        _cell_target(ctx, me, body.dept, body.date, body.employee)
        daily.set_cell(ctx, _iso(body.date), body.employee.strip(), body.dept, body.status or "", body.note)
        return {"ok": True}

    @app.delete("/api/work/cell")
    def clear_cell(body: CellBody, me: Me = edit_roles, ctx: DataContext = ctx_dep):
        """Undo for a cell edit: drop the manual override so the day returns to its computed status."""
        _cell_target(ctx, me, body.dept, body.date, body.employee)
        daily.wsd_delete(ctx, _iso(body.date), body.employee.strip())
        return {"ok": True}

    @app.post("/api/work/transfer")
    def add_transfer(body: TransferBody, me: Me = edit_roles, ctx: DataContext = ctx_dep):
        _can_edit_dept(ctx, me, body.dept)
        ds = _iso(body.date)
        if body.employee.strip() not in daily.transfer_candidates(ctx, body.dept, ds[:7]):
            raise HTTPException(400, "לא ניתן להעביר עובד/ת זה/ו למחלקה")
        if body.dept == PNIM_DEPT and body.side not in PNIM_SIDES:
            raise HTTPException(400, "בפנימית יש לבחור צד")
        daily.add_temp_transfer(ctx, ds, body.employee.strip(), body.dept, side=body.side if body.dept == PNIM_DEPT else "")
        return {"ok": True}

    @app.delete("/api/work/transfer")
    def remove_transfer(body: TransferBody, me: Me = edit_roles, ctx: DataContext = ctx_dep):
        _can_edit_dept(ctx, me, body.dept)
        ds = _iso(body.date)
        if body.employee.strip() not in daily.incoming_transfers(ctx, body.dept, ds[:7]):
            raise HTTPException(404, "ההעברה לא נמצאה")
        daily.wsd_delete(ctx, ds, body.employee.strip())
        return {"ok": True}

    # ── Gantt, settings, on-call ───────────────────────────────────────
    admins = Depends(require(*ADMINS))
    superadmin = Depends(require('מנהל על'))

    @app.put("/api/gantt/{ym}")
    def save_gantt(ym: str, body: GanttBody, _: Me = admins, ctx: DataContext = ctx_dep):
        _ym(ym)
        return admin.save_gantt(ctx, ym, body.assignments, body.sides)

    @app.post("/api/gantt/{ym}/activate")
    def activate(ym: str, _: Me = admins, ctx: DataContext = ctx_dep):
        _, m = _ym(ym)
        admin.make_daily_month_active(ctx, m)
        return admin.active_months(ctx)

    @app.put("/api/settings/daily_requests_open")
    def requests_open(body: OpenBody, _: Me = admins, ctx: DataContext = ctx_dep):
        admin.set_setting(ctx, 'daily_requests_open', 'True' if body.open else 'False')
        return admin.active_months(ctx)

    @app.put("/api/settings/active_month")
    def active_month(body: MonthBody, _: Me = superadmin, ctx: DataContext = ctx_dep):
        admin.set_setting(ctx, 'active_month', body.month)
        return admin.active_months(ctx)

    @app.put("/api/oncall/{ym}")
    def oncall_month(ym: str, body: OncallMonthBody, _: Me = admins, ctx: DataContext = ctx_dep):
        y, m = _ym(ym)
        days = [d.model_dump() for d in body.days]
        for d in days:
            _date_in(ym, d['date'])
        admin.save_konenut_month(ctx, y, m, days)
        return {"ok": True}

    @app.put("/api/oncall/day/{ds}")
    def oncall_day(ds: str, body: OncallDay, _: Me = admins, ctx: DataContext = ctx_dep):
        admin.save_konenut_day(ctx, _iso(ds), body.pnim_dr, body.rehab_dr1, body.rehab_dr2)
        return {"ok": True}

    # ── staff, special days ────────────────────────────────────────────
    @app.post("/api/staff")
    def add_staff(body: StaffAddBody, _: Me = superadmin, ctx: DataContext = ctx_dep):
        staff.add_employee(ctx, body.name.strip(), body.type, body.dept, body.monthly_quota, body.weekend_quota,
                           body.only_home, body.email, body.manage_depts)
        return {"ok": True}

    @app.put("/api/staff")
    def save_staff(body: StaffTableBody, _: Me = superadmin, ctx: DataContext = ctx_dep):
        staff.save_staff_table(ctx, body.rows, body.only_home)
        return {"ok": True}

    @app.post("/api/special-days")
    def add_special(body: SpecialDayBody, _: Me = superadmin, ctx: DataContext = ctx_dep):
        if body.day_type not in SPECIAL_DAY_TYPES:
            raise HTTPException(400, "סוג יום לא תקין")
        admin.add_special_day(ctx, _iso(body.date), body.description.strip(), body.day_type)
        return {"ok": True}

    @app.delete("/api/special-days/{idx}")
    def delete_special(idx: int, _: Me = superadmin, ctx: DataContext = ctx_dep):
        if idx not in ctx.special_days.index:
            raise HTTPException(404, "היום לא נמצא")
        admin.delete_special_day(ctx, idx)
        return {"ok": True}

    # ── night schedule (מנהל על) ───────────────────────────────────────
    @app.post("/api/night/{ym}/auto")
    def auto(ym: str, body: AutoBody, _: Me = superadmin, ctx: DataContext = ctx_dep):
        y, m = _ym(ym)
        workers = max(1, min(4, os.cpu_count() or 1))     # match the instance's vCPUs (DEPLOY_PLAN)
        r = scheduling.run_smart_scheduling_cp(ctx, y, m, only_weekends=body.only_weekends, num_workers=workers)
        return {"method": r.method, "filled": r.filled, "total": r.total, "fallback": r.fallback,
                "messages": [{"level": lv, "text": t} for lv, t in r.messages],
                "suggestions": [{"key": str(k), "options": v} for k, v in r.swap_suggestions.items()]}

    @app.post("/api/night/{ym}/clear")
    def clear(ym: str, body: ClearBody, _: Me = superadmin, ctx: DataContext = ctx_dep):
        y, m = _ym(ym)
        night.clear_month(ctx, y, m, only_auto=body.mode == 'auto')
        return {"ok": True}

    @app.put("/api/night/slot")
    def assign(body: SlotBody, _: Me = superadmin, ctx: DataContext = ctx_dep):
        if body.dept not in ALL_SHIFT_DEPTS:
            raise HTTPException(400, "משמרת לא קיימת")
        if people.staff_row(ctx, body.employee) is None:
            raise HTTPException(400, "עובד/ת לא נמצא/ה")
        night.manual_assign(ctx, _iso(body.date), body.dept, body.employee.strip())
        return {"ok": True}

    @app.delete("/api/night/slot")
    def unassign(body: SlotBody, _: Me = superadmin, ctx: DataContext = ctx_dep):
        night.manual_unassign(ctx, _iso(body.date), body.dept)
        return {"ok": True}

    @app.post("/api/night/{ym}/export-sheet")
    def export_sheet(ym: str, _: Me = superadmin, ctx: DataContext = ctx_dep):
        y, m = _ym(ym)
        exports.export_schedule_wide(ctx, m, y)
        return {"ok": True}

    # ── swaps ──────────────────────────────────────────────────────────
    def _my_shift(ctx, me: Me, ds: str, dept: str):
        s = ctx.schedule
        mine = s[(s['date'].astype(str) == ds) & (s['dept'] == dept) & (s['employee'].astype(str).str.strip() == me.name)]
        if mine.empty:
            raise HTTPException(403, "זו לא משמרת שלך")

    def _search(ctx, me: Me, ds: str, dept: str):
        return night.find_swap_candidates(ctx, ctx.schedule, ctx.requests, ctx.staff, me.name, ds, dept,
                                          sel_month=int(ds[5:7]))

    @app.get("/api/swaps/search")
    def swap_search(date: str, dept: str, me: Me = any_user, ctx: DataContext = ctx_dep):
        ds = _iso(date)
        _my_shift(ctx, me, ds, dept)
        return _search(ctx, me, ds, dept)

    @app.post("/api/swaps")
    def swap_request(body: SwapBody, me: Me = any_user, ctx: DataContext = ctx_dep):
        ds = _iso(body.date)
        _my_shift(ctx, me, ds, body.dept)
        sr = ctx.swap_requests
        if not sr.empty and ((sr['requester'].astype(str).str.strip() == me.name) & (sr['requester_date'].astype(str) == ds)
                             & (sr['requester_dept'] == body.dept) & (sr['status'].astype(str).str.strip() == 'pending')).any():
            raise HTTPException(409, "כבר נשלחה בקשת החלפה למשמרת הזו")
        # Only an option the server itself found is accepted (not whatever the client sends).
        res = _search(ctx, me, ds, body.dept)
        if body.kind == 'chain':
            ok = any(c['facilitator_name'] == body.candidate and c['external_name'] == body.chain_ext for c in res['chain'])
            their = None
        else:
            match = next((c for c in res[body.kind] if c['name'] == body.candidate), None)
            ok, their = match is not None, (match or {}).get('their_shift')
        if not ok:
            raise HTTPException(400, "האפשרות כבר לא זמינה. חפש/י שוב.")
        return night.create_swap_request(ctx, me.name, ds, body.dept, body.kind, body.candidate,
                                         their_shift=their, chain_ext=body.chain_ext)

    @app.post("/api/swaps/{idx}/approve")
    def swap_approve(idx: int, _: Me = superadmin, ctx: DataContext = ctx_dep):
        _swap_pending(ctx, idx)
        night.approve_swap_request(ctx, idx)
        return {"ok": True}

    @app.post("/api/swaps/{idx}/reject")
    def swap_reject(idx: int, _: Me = superadmin, ctx: DataContext = ctx_dep):
        _swap_pending(ctx, idx)
        night.reject_swap_request(ctx, idx)
        return {"ok": True}
