import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import calendar
import random
import io
import os
import uuid
import streamlit_shadcn_ui as ui
import streamlit_antd_components as sac  # Added for Chips/Menu
import hashlib
import gspread
from streamlit_gsheets import GSheetsConnection
import time

calendar.setfirstweekday(calendar.SUNDAY)

# ── Daily-schedule departments (Phase 1+, single source of truth) ──
DAILY_DEPTS_ALL = ["שיקום גריאטרי א'", "שיקום גריאטרי ב'", "פנימית גריאטרית", "זה״ב"]

import ui_components # Modular UI components

# --- 1. עיצוב ו-CSS ---
st.set_page_config(page_title="מערכת סידור עבודה", layout="wide")
ui_components.setup_style()

import hashlib
from streamlit_gsheets import GSheetsConnection

# --- 2. ניהול מסד נתונים (Google Sheets) ---

def _strip_cell(s):
    """
    Strip only MATCHING surrounding quote pairs from a cell value.
    '...'  →  ...    (removes surrounding single quotes)
    "..."  →  ...    (removes surrounding double quotes)
    שיקום גריאטרי א'  →  unchanged  (trailing apostrophe is part of the name)
    """
    s = str(s).strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s

def _clean_sheet_values(vals):
    """
    Convert raw get_all_values() output to a clean DataFrame.
    Strips matching surrounding quote pairs from headers and cell values —
    these are baked in when data was imported via CSV or written with
    USER_ENTERED mode that serialised Python string reprs into cells.
    """
    if not vals:
        return pd.DataFrame()
    headers = [_strip_cell(h) for h in vals[0]]
    rows = []
    for row in vals[1:]:
        cleaned = [_strip_cell(c) for c in row]
        # Pad short rows to match header length
        while len(cleaned) < len(headers):
            cleaned.append('')
        rows.append(cleaned[:len(headers)])
    return pd.DataFrame(rows, columns=headers)

@st.cache_data(ttl=600, show_spinner=False)
def _fetch_sheet_data_silently(worksheet_name):
    """
    Cached sheet read. Uses get_all_values() so a sheet with a header row but
    no data rows still returns a DataFrame with correct column names.
    Strips surrounding quotes from all headers and cell values.
    """
    gc = get_gspread_client()
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    sh = gc.open_by_url(url)
    try:
        ws = sh.worksheet(worksheet_name)
        vals = ws.get_all_values()
        return _clean_sheet_values(vals)
    except gspread.exceptions.WorksheetNotFound:
        return pd.DataFrame()

def _fetch_live(worksheet_name):
    """
    Direct Sheets read that bypasses the cache — use only immediately before a write.
    Uses get_all_values() + _clean_sheet_values() to preserve column names even on
    header-only sheets and to strip surrounding quotes baked in by CSV imports.
    """
    for attempt in range(3):
        try:
            gc = get_gspread_client()
            url = st.secrets["connections"]["gsheets"]["spreadsheet"]
            sh = gc.open_by_url(url)
            ws = sh.worksheet(worksheet_name)
            return _clean_sheet_values(ws.get_all_values())
        except gspread.exceptions.WorksheetNotFound:
            return pd.DataFrame()
        except gspread.exceptions.APIError as e:
            if e.response.status_code == 429:
                time.sleep(2 ** attempt)
            else:
                raise
    return pd.DataFrame()

def get_db_data(worksheet_name):
    try:
        df = _fetch_sheet_data_silently(worksheet_name)
        return df
    except Exception as e:
        err_msg = str(e).lower()
        if "worksheet" in err_msg and "not found" in err_msg:
             return pd.DataFrame()
        raise e

def get_gspread_client():
    # יצירת קליינט gspread מתוך ה-secrets הקיימים
    # נניח שהם במבנה סטנדרטי תחת connections.gsheets
    creds = st.secrets["connections"]["gsheets"]
    
    # gspread מצפה למילון או קובץ, st.secrets מחזיר מילון-כמו-אובייקט, נמיר למילון רגיל
    creds_dict = dict(creds)
    
    # במידה ויש צורך ב-scopes ספציפיים, gspread מטפל בזה לרוב אוטומטית עם service_account_from_dict
    gc = gspread.service_account_from_dict(creds_dict)
    return gc

def send_notification_email(to_address, subject, body_html):
    """
    Send an HTML email via Gmail SMTP.
    Credentials from [email] section in .streamlit/secrets.toml.
    Entire body wrapped in except — NEVER crashes the app.
    """
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        cfg = st.secrets.get("email", {})
        smtp_server = str(cfg.get("smtp_server", "smtp.gmail.com"))
        smtp_port = int(cfg.get("smtp_port", 587))
        sender = str(cfg.get("sender_address", ""))
        password = str(cfg.get("sender_password", ""))
        if not sender or not password or not to_address:
            return  # not configured — silently skip

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = to_address
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, to_address, msg.as_string())
    except Exception:
        pass  # Email failure must never affect the main app

def _update_absence_status(req_id, new_status, responder_name):
    """Update an absence_requests row's status + responded_at + approved_by, persist + email user."""
    df = st.session_state.absence_requests.copy()
    if df.empty or 'id' not in df.columns:
        return False
    mask = df['id'].astype(str) == str(req_id)
    if not mask.any():
        return False
    df.loc[mask, 'status']       = new_status
    df.loc[mask, 'approved_by']  = responder_name
    df.loc[mask, 'responded_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    st.session_state.absence_requests = df
    save_to_db("absence_requests", df)

    # Notify the requester by email if we have one
    try:
        row = df[mask].iloc[0]
        emp_name = str(row.get('employee', '')).strip()
        # Look up requester's email
        staff_df = st.session_state.staff
        emp_match = staff_df[staff_df['name'].astype(str).str.strip() == emp_name]
        emp_email = str(emp_match.iloc[0].get('email', '')).strip() if not emp_match.empty else ''
        if emp_email:
            verb = "אושרה" if new_status == 'approved' else "נדחתה"
            send_notification_email(
                emp_email,
                f"בקשת היעדרות {verb}",
                f"<div dir='rtl'><p>שלום {emp_name},</p>"
                f"<p>בקשת ההיעדרות שלך לתאריכים "
                f"<b>{row.get('start_date','')} – {row.get('end_date','')}</b> "
                f"({row.get('type','')}) <b>{verb}</b> על ידי {responder_name}.</p></div>"
            )
    except Exception:
        pass
    return True

def _approve_request(req_id, responder_name):
    return _update_absence_status(req_id, 'approved', responder_name)

def _reject_request(req_id, responder_name):
    return _update_absence_status(req_id, 'rejected', responder_name)

def _generate_work_schedule(year_month, view_month):
    """
    Generate work_schedule_daily for one month.
    Reads dept_rotation, absence_requests (approved), and schedule (night shifts) from session_state.
    Preserves rows with is_manual=True.
    Returns: {'written': N, 'kept_manual': K, 'employees': E, 'absences_applied': A, 'post_shifts': P, 'error': err}
    """
    try:
        year = 2026
        # Inputs
        dr = st.session_state.dept_rotation.copy()
        ar = st.session_state.absence_requests.copy()
        sched = st.session_state.schedule.copy()
        wsd  = st.session_state.work_schedule_daily.copy()

        if dr.empty or 'employee' not in dr.columns:
            return {'error': "אין נתוני dept_rotation. אנא הגדר תחילה את השיבוץ החודשי."}

        dr['employee']   = dr['employee'].astype(str).str.strip()
        dr['year_month'] = dr['year_month'].astype(str)
        dr['daily_dept'] = dr['daily_dept'].astype(str)
        month_rotation = dr[dr['year_month'] == year_month]
        if month_rotation.empty:
            return {'error': f"אין שיבוצים לחודש {year_month}. אנא שבץ עובדים תחילה."}

        # Recurring weekly absences map: employee → set of Hebrew weekday indexes (Sun=0..Sat=6)
        HEB_DAY_TO_IDX = {"א": 0, "ב": 1, "ג": 2, "ד": 3, "ה": 4, "ו": 5, "ש": 6}
        recurring_map = {}
        staff_for_rec = st.session_state.staff
        if not staff_for_rec.empty and 'name' in staff_for_rec.columns:
            for _, sr in staff_for_rec.iterrows():
                rec_raw = str(sr.get('recurring_absent_days', '') or '').strip()
                if not rec_raw:
                    continue
                idxs = set()
                for tok in rec_raw.split(','):
                    t = tok.strip()
                    if t in HEB_DAY_TO_IDX:
                        idxs.add(HEB_DAY_TO_IDX[t])
                if idxs:
                    recurring_map[str(sr['name']).strip()] = idxs

        # Approved absences map: employee → list of (start_d, end_d, type)
        approved_map = {}
        if not ar.empty and 'status' in ar.columns:
            ar['status']     = ar['status'].astype(str).str.lower()
            ar['employee']   = ar['employee'].astype(str).str.strip()
            ar['start_date'] = ar['start_date'].astype(str)
            ar['end_date']   = ar['end_date'].astype(str)
            ar['type']       = ar['type'].astype(str)
            for _, r in ar[ar['status'] == 'approved'].iterrows():
                try:
                    sd = datetime.strptime(r['start_date'], '%Y-%m-%d').date()
                    ed = datetime.strptime(r['end_date'],   '%Y-%m-%d').date()
                except Exception:
                    continue
                approved_map.setdefault(r['employee'], []).append((sd, ed, r['type']))

        # Night shifts map: (employee, date_str) → True (for D+1 lookup)
        night_map = set()
        if not sched.empty and 'employee' in sched.columns and 'date' in sched.columns:
            sched['employee'] = sched['employee'].astype(str).str.strip()
            sched['date']     = sched['date'].astype(str)
            sched['dept']     = sched['dept'].astype(str)
            # Only main dept shifts count as "night shift" for אחרי תורנות (not שישי בוקר)
            real_shifts = sched[~sched['dept'].str.contains('שישי בוקר', na=False)]
            real_shifts = real_shifts[real_shifts['employee'].str.len() > 0]
            real_shifts = real_shifts[~real_shifts['employee'].isin(['', '---'])]
            for _, r in real_shifts.iterrows():
                night_map.add((r['employee'], r['date']))

        # Existing manual rows for this month (preserve untouched)
        if wsd.empty or 'date' not in wsd.columns:
            wsd = pd.DataFrame(columns=['date','employee','daily_dept','status','note','is_manual'])
        wsd['date']     = wsd['date'].astype(str)
        wsd['employee'] = wsd['employee'].astype(str).str.strip()
        wsd['is_manual'] = wsd['is_manual'].apply(
            lambda v: v if isinstance(v, bool) else str(v).strip().lower() == 'true'
        )
        in_month = wsd['date'].str.startswith(year_month)
        manual_rows  = wsd[in_month & wsd['is_manual']].copy()
        # Preserved manual rows (we keep these as-is)
        manual_keys  = set(zip(manual_rows['date'], manual_rows['employee']))

        # Other-month rows (untouched)
        other_rows = wsd[~in_month].copy()

        # Build new rows for this month
        new_rows = []
        absences_applied = 0
        post_shifts = 0
        num_days = calendar.monthrange(year, view_month)[1]

        for _, rot in month_rotation.iterrows():
            emp_n = rot['employee']
            dept_n = rot['daily_dept']
            if dept_n == "— לא שובץ —" or not dept_n:
                continue
            for d in range(1, num_days + 1):
                date_obj = date(year, view_month, d)
                date_str = date_obj.strftime('%Y-%m-%d')

                # Skip: manual override exists for this (date, employee) → keep manual_rows version
                if (date_str, emp_n) in manual_keys:
                    continue

                status = "עובד"  # default
                note   = ""

                wd_idx_gen = (date_obj.weekday() + 1) % 7  # Sun=0, Fri=5, Sat=6

                # Priority 0a: Saturday — department closed
                if wd_idx_gen == 6:
                    status = "חופש"
                    note   = "שבת"

                # Priority 0b: Friday — working employees from שישי בוקר schedule
                elif wd_idx_gen == 5:
                    fri_shifts = _DAILY_DEPT_TO_FRIDAY_SHIFTS.get(str(dept_n), [])
                    if fri_shifts:
                        # Check if this employee is assigned to the mapped שישי בוקר shift
                        fri_assigned = {
                            str(r['employee']).strip()
                            for _, r in sched.iterrows()
                            if str(r['date']) == date_str and str(r['dept']) in fri_shifts
                        }
                        if emp_n not in fri_assigned:
                            status = "חופש"
                            note   = "שישי — לא משובץ"

                # Priority 1: approved absence covers this day?
                if status == "עובד":
                    for sd, ed, atype in approved_map.get(emp_n, []):
                        if sd <= date_obj <= ed:
                            status = atype if atype else "חופש"
                            break

                # Priority 2: recurring weekly absence? (weekdays only — Fri/Sat handled above)
                if status == "עובד":
                    wd_heb_idx = wd_idx_gen
                    if wd_heb_idx in recurring_map.get(emp_n, set()):
                        status = "חופש"
                        note = "היעדרות קבועה"

                # Priority 3: night shift the day before?
                if status == "עובד":
                    prev_str = (date_obj - timedelta(days=1)).strftime('%Y-%m-%d')
                    if (emp_n, prev_str) in night_map:
                        status = "אחרי תורנות"
                        post_shifts += 1
                else:
                    absences_applied += 1

                new_rows.append({
                    'date': date_str,
                    'employee': emp_n,
                    'daily_dept': dept_n,
                    'status': status,
                    'note': note,
                    'is_manual': False,
                })

        # Merge: other_rows + manual_rows (this month) + new_rows (auto for this month)
        new_df = pd.concat(
            [other_rows, manual_rows, pd.DataFrame(new_rows)],
            ignore_index=True
        )
        st.session_state.work_schedule_daily = new_df
        save_to_db("work_schedule_daily", new_df)

        return {
            'written': len(new_rows),
            'kept_manual': len(manual_rows),
            'employees': len(month_rotation),
            'absences_applied': absences_applied,
            'post_shifts': post_shifts,
            'error': None,
        }
    except Exception as e:
        return {'error': f"שגיאה ביצירת הסידור: {e}"}

def _export_schedule_wide(view_month):
    """
    Export the schedule sheet (night shifts) to 'Schedule_Export' in wide format.
    One row per date, columns: תאריך, יום, פנימית גריאטרית, שיקום, שישי בוקר *4.
    Returns (ok, error_msg).
    """
    try:
        days_in_month = calendar.monthrange(2026, view_month)[1]
        dates_list = [date(2026, view_month, d) for d in range(1, days_in_month + 1)]
        export_rows = []
        schedule_data = st.session_state.schedule

        for d_obj in dates_list:
            d_str = str(d_obj)
            day_name = ["ב'", "ג'", "ד'", "ה'", "ו'", "ש'", "א'"][d_obj.weekday()]
            row_data = {
                'תאריך': d_str, 'יום': day_name,
                'פנימית גריאטרית': '', 'שיקום': '',
                'שישי בוקר - פנימית (1)': '', 'שישי בוקר - פנימית (2)': '',
                'שישי בוקר - שיקום (1)':   '', 'שישי בוקר - שיקום (2)':   '',
            }
            daily_shifts = schedule_data[schedule_data['date'] == d_str]
            if not daily_shifts.empty:
                for _, shift in daily_shifts.iterrows():
                    dept = shift['dept']; emp = shift['employee']
                    if emp == '---': continue
                    if dept in row_data:
                        row_data[dept] = emp
            export_rows.append(row_data)

        df_export = pd.DataFrame(export_rows)
        col_order = [
            'תאריך', 'יום',
            'פנימית גריאטרית', 'שיקום',
            'שישי בוקר - פנימית (1)', 'שישי בוקר - פנימית (2)',
            'שישי בוקר - שיקום (1)',   'שישי בוקר - שיקום (2)',
        ]
        for col in col_order:
            if col not in df_export.columns:
                df_export[col] = ''
        df_export = df_export[col_order]
        save_to_db("Schedule_Export", df_export, is_rtl=True)
        return True, None
    except Exception as e:
        return False, str(e)

def _export_dept_grid(dept_name, year_month, view_month):
    """
    Export the dept grid for a given month — PIVOTED format.

    Status resolution: same logic as the board display —
      manual override → use stored status
      non-manual "עובד" (or no entry) → re-derive (recurring days, תורנות, אחרי תורנות)

    Section נמצאים: עובד (with note if any) + תורנות
    Section נעדרים: חופש / 202 / אחרי תורנות / אחר — each cell "name (reason)"

    Worksheet is set to RTL after writing.
    Worksheet name: 'WSD_<dept>_<year_month>'. Returns True on success.
    """
    try:
        year = 2026
        num_days = calendar.monthrange(year, view_month)[1]
        days = list(range(1, num_days + 1))

        # Employees from dept_rotation
        dr = st.session_state.dept_rotation
        if dr.empty or 'employee' not in dr.columns:
            return False
        mask = ((dr['year_month'].astype(str) == year_month) &
                (dr['daily_dept'].astype(str) == dept_name))
        employees = dr[mask]['employee'].astype(str).str.strip().tolist()
        if not employees:
            return False

        _ABSENT_STATUSES = {"חופש", "202", "אחרי תורנות", "אחר"}

        WD = ["א", "ב", "ג", "ד", "ה", "ו", "ש"]
        per_day_working = {}   # day → list[str]  — נמצאים
        per_day_absent  = {}   # day → list[str]  — נעדרים

        for d in days:
            date_str = f"{year}-{view_month:02d}-{d:02d}"
            working, absent = [], []
            for emp in employees:
                raw    = _wsd_get_status(date_str, emp, default=None)
                manual = _wsd_is_manual(date_str, emp)
                # Same live-derive logic as the board
                if raw is None or (raw == "עובד" and not manual):
                    status = _derive_auto_status(date_str, emp, daily_dept=dept_name)
                else:
                    status = raw
                note = _wsd_get_note(date_str, emp)

                if status in _ABSENT_STATUSES:
                    # נעדרים: "name (reason)" or "name (reason — note)"
                    reason = f"{status} — {note}" if note else status
                    absent.append(f"{emp} ({reason})")
                else:
                    # נמצאים: עובד or תורנות — show note or status tag if not plain עובד
                    if status == "תורנות":
                        working.append(f"{emp} (תורנות)")
                    elif note:
                        working.append(f"{emp} ({note})")
                    else:
                        working.append(emp)

            per_day_working[d] = working
            per_day_absent[d]  = absent

        max_work_rows = max((len(v) for v in per_day_working.values()), default=0)
        max_abs_rows  = max((len(v) for v in per_day_absent.values()),  default=0)

        col_names = ['#'] + [str(d) for d in days]
        rows = []

        # Weekday-letter header row
        rows.append({'#': 'יום', **{str(d): WD[(date(year, view_month, d).weekday() + 1) % 7] for d in days}})

        # Section נמצאים
        rows.append({'#': '— נמצאים —', **{str(d): '' for d in days}})
        for i in range(max_work_rows):
            row = {'#': ''}
            for d in days:
                lst = per_day_working.get(d, [])
                row[str(d)] = lst[i] if i < len(lst) else ''
            rows.append(row)

        # Section נעדרים
        rows.append({'#': '— נעדרים —', **{str(d): '' for d in days}})
        for i in range(max_abs_rows):
            row = {'#': ''}
            for d in days:
                lst = per_day_absent.get(d, [])
                row[str(d)] = lst[i] if i < len(lst) else ''
            rows.append(row)

        export_df = pd.DataFrame(rows, columns=col_names)

        safe = dept_name.replace("'", "").replace('"', '').replace('/', '_')[:25]
        sheet_name = f"WSD_{safe}_{year_month}"
        save_to_db(sheet_name, export_df)

        # Set worksheet to RTL
        try:
            gc  = get_gspread_client()
            url = st.secrets["connections"]["gsheets"]["spreadsheet"]
            sh  = gc.open_by_url(url)
            ws  = sh.worksheet(sheet_name)
            sh.batch_update({"requests": [{
                "updateSheetProperties": {
                    "properties": {"sheetId": ws.id, "rightToLeft": True},
                    "fields": "rightToLeft"
                }
            }]})
        except Exception:
            pass  # RTL is cosmetic — don't fail the export if it errors

        return True
    except Exception:
        return False

# ── Excel colour map (PatternFill hex) ──────────────────────────────────────
_XL_STATUS_FILL = {
    "עובד":         "DCFCE7",
    "חופש":         "DBEAFE",
    "202":          "FEF9C3",
    "אחרי תורנות":  "FFEDD5",
    "תורנות":       "EDE9FE",
    "אחר":          "F1F5F9",
}

def _get_user_email(user_name):
    """Return email for user_name from staff sheet, or '' if missing."""
    try:
        sf = st.session_state.staff
        if sf.empty or 'email' not in sf.columns:
            return ""
        row = sf[sf['name'].astype(str).str.strip() == str(user_name).strip()]
        if row.empty:
            return ""
        return str(row.iloc[0].get('email', '') or '').strip()
    except Exception:
        return ""

def _export_dept_grid_excel(dept_name, year_month, view_month):
    """
    Build an in-memory Excel workbook for the dept grid and return (bytes, filename).
    Returns (None, None) on failure.
    """
    try:
        import openpyxl
        from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
        year = 2026
        num_days = calendar.monthrange(year, view_month)[1]
        days = list(range(1, num_days + 1))
        WD = ["א", "ב", "ג", "ד", "ה", "ו", "ש"]

        dr = st.session_state.dept_rotation
        if dr.empty or 'employee' not in dr.columns:
            return None, None
        mask = ((dr['year_month'].astype(str) == year_month) &
                (dr['daily_dept'].astype(str) == dept_name))
        employees = dr[mask]['employee'].astype(str).str.strip().tolist()
        if not employees:
            return None, None

        wb = openpyxl.Workbook()
        ws_xl = wb.active
        ws_xl.title = dept_name[:31]
        ws_xl.sheet_view.rightToLeft = True

        thin = Side(style='thin', color='CBD5E1')
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        # Row 1: dept + month title
        ws_xl.cell(1, 1, f"{dept_name} — {year_month}").font = Font(bold=True, size=12)
        ws_xl.merge_cells(start_row=1, start_column=1,
                          end_row=1, end_column=num_days + 1)

        # Row 2: header — col A = "עובד", then day numbers
        ws_xl.cell(2, 1, "עובד/ת").font = Font(bold=True)
        for i, d in enumerate(days):
            wd_letter = WD[(date(year, view_month, d).weekday() + 1) % 7]
            cell = ws_xl.cell(2, i + 2, f"{d}\n{wd_letter}")
            cell.font = Font(bold=True, size=9)
            cell.alignment = Alignment(horizontal='center', vertical='center',
                                       wrap_text=True)
            cell.border = border
        ws_xl.row_dimensions[2].height = 28
        ws_xl.column_dimensions['A'].width = 16

        # Data rows
        for ri, emp in enumerate(employees):
            row_num = ri + 3
            ws_xl.cell(row_num, 1, emp).font = Font(bold=False, size=10)
            ws_xl.cell(row_num, 1).alignment = Alignment(horizontal='right')
            for i, d in enumerate(days):
                date_str = f"{year}-{view_month:02d}-{d:02d}"
                raw = _wsd_get_status(date_str, emp, default=None)
                status = raw if raw is not None else _derive_auto_status(date_str, emp, daily_dept=dept_name)
                note   = _wsd_get_note(date_str, emp)
                col_num = i + 2
                cell = ws_xl.cell(row_num, col_num)
                lbl = _GRID_STATUS_LABEL_SHORT.get(status, status)
                cell.value = lbl + (f"\n{note}" if note else "")
                cell.alignment = Alignment(horizontal='center', vertical='center',
                                           wrap_text=True, shrink_to_fit=False)
                fill_hex = _XL_STATUS_FILL.get(status, "F8FAFC")
                cell.fill = PatternFill("solid", fgColor=fill_hex)
                cell.border = border
                cell.font   = Font(size=9)
            ws_xl.column_dimensions[
                openpyxl.utils.get_column_letter(i + 2)].width = 6

        # Freeze header rows
        ws_xl.freeze_panes = "B3"

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        safe = dept_name.replace("'", "").replace('"', '').replace('/', '_')[:25]
        return buf.getvalue(), f"WSD_{safe}_{year_month}.xlsx"
    except Exception:
        return None, None

def _export_personal_schedule_excel(user_name, view_month, daily_dept=None):
    """
    Build an Excel file with the personal day schedule for one employee.
    Returns (bytes, filename) or (None, None).
    """
    try:
        import openpyxl
        from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
        year = 2026
        num_days = calendar.monthrange(year, view_month)[1]
        WD_FULL = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]

        wb = openpyxl.Workbook()
        ws_xl = wb.active
        ws_xl.title = "לוח עבודה אישי"
        ws_xl.sheet_view.rightToLeft = True

        thin = Side(style='thin', color='CBD5E1')
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        # Header
        headers = ["תאריך", "יום", "סטטוס", "הערה"]
        header_fills = ["334155"] * 4
        for ci, h in enumerate(headers):
            cell = ws_xl.cell(1, ci + 1, h)
            cell.font = Font(bold=True, color="FFFFFF", size=10)
            cell.fill = PatternFill("solid", fgColor="334155")
            cell.alignment = Alignment(horizontal='center')
            cell.border = border

        ws_xl.column_dimensions['A'].width = 12
        ws_xl.column_dimensions['B'].width = 10
        ws_xl.column_dimensions['C'].width = 14
        ws_xl.column_dimensions['D'].width = 22

        for d in range(1, num_days + 1):
            date_str = f"{year}-{view_month:02d}-{d:02d}"
            wd_name  = WD_FULL[(date(year, view_month, d).weekday() + 1) % 7]
            raw = _wsd_get_status(date_str, user_name, default=None)
            manual = _wsd_is_manual(date_str, user_name)
            if raw is None or (raw == "עובד" and not manual):
                status = _derive_auto_status(date_str, user_name,
                                             daily_dept=daily_dept)
            else:
                status = raw
            note   = _wsd_get_note(date_str, user_name)
            row_num = d + 1
            ws_xl.cell(row_num, 1, date_str).border = border
            ws_xl.cell(row_num, 2, wd_name).border = border
            status_cell = ws_xl.cell(row_num, 3, status)
            status_cell.fill = PatternFill("solid", fgColor=_XL_STATUS_FILL.get(status, "F8FAFC"))
            status_cell.alignment = Alignment(horizontal='center')
            status_cell.border = border
            ws_xl.cell(row_num, 4, note).border = border

        ws_xl.freeze_panes = "A2"
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        safe_name = str(user_name).replace(' ', '_')[:20]
        return buf.getvalue(), f"סידור_{safe_name}_{year}-{view_month:02d}.xlsx"
    except Exception:
        return None, None

def _export_dept_to_new_gsheet(dept_name, year_month, view_month):
    """
    Export the dept grid into the EXISTING Shifts_scheduler spreadsheet
    (same as _export_dept_grid) and return a direct URL to that specific
    worksheet tab so it can be opened immediately in the browser.
    Returns (True, tab_url, '') or (False, '', error_message).
    No new files are created — avoids Drive quota issues.
    """
    try:
        # Run the standard export into the main spreadsheet
        ok = _export_dept_grid(dept_name, year_month, view_month)
        if not ok:
            return False, '', "שגיאה בייצוא — וודא שיש שיבוצים למחלקה זו"

        # Build the worksheet name (same logic as _export_dept_grid)
        safe = dept_name.replace("'", "").replace('"', '').replace('/', '_')[:25]
        sheet_name = f"WSD_{safe}_{year_month}"

        # Open the spreadsheet and get the worksheet's gid for a direct tab URL
        gc  = get_gspread_client()
        url = st.secrets["connections"]["gsheets"]["spreadsheet"]
        sh  = gc.open_by_url(url)
        ws  = sh.worksheet(sheet_name)
        tab_url = f"{sh.url}#gid={ws.id}"

        # Make the spreadsheet viewable by anyone with the link (read-only)
        try:
            sh.share('', perm_type='anyone', role='reader')
        except Exception:
            pass  # non-critical — link still works for existing editors

        return True, tab_url, ''
    except Exception as e:
        return False, '', str(e)

def _get_fri_shift_workers(date_str, daily_dept):
    """
    Return list of employee names assigned to the department's Friday-morning
    shifts on date_str (Fridays only). Returns [] for any other weekday.
    For פנימית גריאטרית returns both slot-1 and slot-2 names;
    for each שיקום dept returns the single matching slot name.
    """
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        if (date_obj.weekday() + 1) % 7 != 5:   # not Friday
            return []
        fri_shifts = _DAILY_DEPT_TO_FRIDAY_SHIFTS.get(str(daily_dept), [])
        if not fri_shifts:
            return []
        sch = st.session_state.schedule
        if sch.empty or 'date' not in sch.columns:
            return []
        mask = (
            (sch['date'].astype(str) == date_str) &
            (sch['dept'].astype(str).isin(fri_shifts))
        )
        workers = sch[mask]['employee'].astype(str).str.strip().tolist()
        return [w for w in workers if w and w != '---']
    except Exception:
        return []


def _rebuild_wsd_index():
    """Build a (date_str, employee) → dict index from work_schedule_daily.
    Called at session init and after every _wsd_upsert write.
    """
    idx = {}
    wsd = st.session_state.get('work_schedule_daily', pd.DataFrame())
    if not wsd.empty and 'date' in wsd.columns:
        for _, r in wsd.iterrows():
            key = (str(r['date']), str(r.get('employee', '')).strip())
            raw_manual = r.get('is_manual', False)
            idx[key] = {
                'status':    str(r.get('status', 'עובד')),
                'note':      str(r.get('note', '') or ''),
                'is_manual': raw_manual if isinstance(raw_manual, bool)
                             else str(raw_manual).strip().lower() == 'true',
            }
    st.session_state.wsd_index = idx


def _wsd_get_status(date_str, employee, default="עובד"):
    """O(1) status lookup via pre-built wsd_index."""
    idx = st.session_state.get('wsd_index')
    if idx is None:
        _rebuild_wsd_index()
        idx = st.session_state.wsd_index
    return idx.get((str(date_str), str(employee).strip()), {}).get('status', default)

def _wsd_is_manual(date_str, employee):
    """O(1) is_manual lookup via pre-built wsd_index."""
    idx = st.session_state.get('wsd_index')
    if idx is None:
        _rebuild_wsd_index()
        idx = st.session_state.wsd_index
    return idx.get((str(date_str), str(employee).strip()), {}).get('is_manual', False)

def _wsd_upsert(date_str, employee, daily_dept, status, is_manual=True, note=""):
    """Insert/update one row in work_schedule_daily; persist to sheet."""
    wsd = st.session_state.work_schedule_daily.copy()
    if wsd.empty or 'date' not in wsd.columns:
        wsd = pd.DataFrame(columns=['date','employee','daily_dept','status','note','is_manual'])
    emp_n = str(employee).strip()
    m = (wsd['date'].astype(str) == date_str) & (wsd['employee'].astype(str).str.strip() == emp_n)
    if m.any():
        wsd.loc[m, 'status']     = status
        wsd.loc[m, 'is_manual']  = is_manual
        wsd.loc[m, 'daily_dept'] = daily_dept
        wsd.loc[m, 'note']       = note  # always update — empty string clears the note
    else:
        wsd = pd.concat([wsd, pd.DataFrame([{
            'date': date_str, 'employee': emp_n, 'daily_dept': daily_dept,
            'status': status, 'note': note, 'is_manual': is_manual,
        }])], ignore_index=True)
    st.session_state.work_schedule_daily = wsd
    _rebuild_wsd_index()   # keep O(1) index in sync
    save_to_db("work_schedule_daily", wsd)

# Status cycle for in-grid editing (clicks rotate through these)
_GRID_STATUS_CYCLE = {
    "עובד":         "חופש",
    "חופש":         "202",
    "202":          "אחרי תורנות",
    "אחרי תורנות":  "אחר",
    "אחר":          "עובד",
    "תורנות":       "חופש",   # clicking overrides auto-derived night-shift status
}
_GRID_STATUS_LABEL_SHORT = {
    "עובד":         "עובד/ת",
    "חופש":         "חופש",
    "202":          "202",
    "אחרי תורנות":  "אחרי",
    "אחר":          "אחר",
    "תורנות":       "תורנות",
}
_GRID_STATUS_PFX = {
    "עובד":         "wsdcell_w",
    "חופש":         "wsdcell_h",
    "202":          "wsdcell_2",
    "אחרי תורנות":  "wsdcell_p",
    "אחר":          "wsdcell_a",
    "תורנות":       "wsdcell_t",
}

def _wsd_get_note(date_str, employee):
    """O(1) note lookup via pre-built wsd_index."""
    idx = st.session_state.get('wsd_index')
    if idx is None:
        _rebuild_wsd_index()
        idx = st.session_state.wsd_index
    return idx.get((str(date_str), str(employee).strip()), {}).get('note', '')

_FRIDAY_SHIFT_DEPTS = {
    "שישי בוקר - שיקום (1)", "שישי בוקר - שיקום (2)",
    "שישי בוקר - פנימית (1)", "שישי בוקר - פנימית (2)",
}

_HEB_DAY_TO_IDX = {"א": 0, "ב": 1, "ג": 2, "ד": 3, "ה": 4, "ו": 5, "ש": 6}

# Friday shift → daily dept mapping (for deriving who works which daily dept on Fridays)
_DAILY_DEPT_TO_FRIDAY_SHIFTS = {
    "פנימית גריאטרית":    ["שישי בוקר - פנימית (1)", "שישי בוקר - פנימית (2)"],
    "שיקום גריאטרי א'":   ["שישי בוקר - שיקום (1)"],
    "שיקום גריאטרי ב'":   ["שישי בוקר - שיקום (2)"],
}

# Daily dept → night-shift dept name (for תורנ/ית display row)
_DAILY_DEPT_TO_NIGHT_DEPT = {
    "פנימית גריאטרית":    "פנימית גריאטרית",
    "שיקום גריאטרי א'":   "שיקום",
    "שיקום גריאטרי ב'":   "שיקום",
}

def _derive_auto_status(date_str, employee, daily_dept=None):
    """
    Derive the day-schedule status for (date, employee) without reading work_schedule_daily.
    Priority order:
      0. Saturday (wd=6) → "חופש" (department closed)
      0. Friday (wd=5) + daily_dept known → check שישי בוקר assignment;
         עובד if assigned to mapped shift, חופש otherwise
      1. Recurring weekly absence (recurring_absent_days in staff sheet) → "חופש"
      2. Night shift today (schedule sheet) → "תורנות"
      3. Night shift yesterday → "אחרי תורנות"
      4. Default → "עובד"
    """
    try:
        emp = str(employee).strip()
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        wd_idx = (date_obj.weekday() + 1) % 7  # Sun=0 … Sat=6

        # 0a. Saturday: department closed
        if wd_idx == 6:
            return "חופש"

        # 0b. Friday: working employees come from שישי בוקר assignments
        if wd_idx == 5 and daily_dept:
            fri_shifts = _DAILY_DEPT_TO_FRIDAY_SHIFTS.get(str(daily_dept), [])
            if fri_shifts:
                try:
                    sch = st.session_state.schedule
                    if not sch.empty and 'date' in sch.columns:
                        fri_mask = (
                            (sch['date'].astype(str) == date_str) &
                            (sch['dept'].astype(str).isin(fri_shifts))
                        )
                        fri_emps = sch[fri_mask]['employee'].astype(str).str.strip().tolist()
                        fri_emps = [e for e in fri_emps if e and e != '---']
                        return "עובד" if emp in fri_emps else "חופש"
                except Exception:
                    pass

        # 1. Recurring weekly absence
        try:
            sf = st.session_state.staff
            if not sf.empty and 'recurring_absent_days' in sf.columns:
                emp_row = sf[sf['name'].astype(str).str.strip() == emp]
                if not emp_row.empty:
                    rec_raw = str(emp_row.iloc[0].get('recurring_absent_days', '') or '').strip()
                    if rec_raw:
                        wd_heb_idx = wd_idx
                        for tok in rec_raw.split(','):
                            if _HEB_DAY_TO_IDX.get(tok.strip()) == wd_heb_idx:
                                return "חופש"
        except Exception:
            pass

        # 2 & 3. Night shift schedule
        sch = st.session_state.schedule
        if not sch.empty and 'date' in sch.columns:
            night_sch = sch[~sch['dept'].astype(str).isin(_FRIDAY_SHIFT_DEPTS)]
            names = night_sch['employee'].astype(str).str.strip()
            dates = night_sch['date'].astype(str)
            if ((dates == date_str) & (names == emp)).any():
                return "תורנות"
            prev = (date_obj - timedelta(days=1)).strftime("%Y-%m-%d")
            if ((dates == prev) & (names == emp)).any():
                return "אחרי תורנות"
    except Exception:
        pass
    return "עובד"


def _get_night_duty(date_str, daily_dept):
    """Return the name of the on-call (night-shift) employee for a given date and daily dept."""
    night_dept = _DAILY_DEPT_TO_NIGHT_DEPT.get(str(daily_dept))
    if not night_dept:
        return None
    try:
        sch = st.session_state.schedule
        if sch.empty or 'date' not in sch.columns:
            return None
        mask = (sch['date'].astype(str) == date_str) & (sch['dept'].astype(str) == night_dept)
        rows = sch[mask]
        if rows.empty:
            return None
        emp = str(rows.iloc[0]['employee']).strip()
        return emp if emp and emp != '---' else None
    except Exception:
        return None

_MANUAL_STATUSES = ["עובד", "חופש", "202", "אחרי תורנות", "אחר"]
# ── Inclusive display labels for role types (stored values unchanged) ─────────
_TYPE_DISPLAY = {
    'מתמחה':      'מתמחה',
    'תורן חוץ':   'תורנ/ית חוץ',
    'מנהל/ת':     'מנהל/ת',
    'רופא בכיר':  'רופא/ה בכירה',
    'מנהל מחלקה': 'מנהל/ת מחלקה',
}


def _render_export_buttons(dept_name, year_month, view_month, key_ns, user_name=""):
    """
    Render three export buttons for a dept:
      1. 📥 Excel — download_button
      2. 📤 ייצא לקובץ הראשי — write worksheet to same Shifts_scheduler spreadsheet
      3. 🔗 פתח ב-Sheets — create standalone GSheet, open in new tab
    """
    import streamlit.components.v1 as _components
    c1, c2, c3 = st.columns(3)

    # 1. Excel download
    with c1:
        xl_bytes, xl_fname = _export_dept_grid_excel(dept_name, year_month, view_month)
        if xl_bytes:
            st.download_button(
                "📥 הורד Excel",
                data=xl_bytes,
                file_name=xl_fname,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"xl_dl_{key_ns}",
                use_container_width=True,
            )
        else:
            st.button("📥 Excel", key=f"xl_dl_{key_ns}_na", disabled=True,
                      use_container_width=True)

    # 2. Export to main Shifts_scheduler spreadsheet
    with c2:
        if st.button("📤 ייצא לקובץ הראשי", key=f"exp_main_{key_ns}",
                     use_container_width=True):
            if _export_dept_grid(dept_name, year_month, view_month):
                st.success(f"✅ {dept_name} יוצא לגיליון הראשי!")
            else:
                st.error("שגיאה בייצוא")

    # 3. New standalone Google Sheet — auto-open in browser
    with c3:
        if st.button("🔗 פתח ב-Sheets", key=f"exp_new_{key_ns}",
                     use_container_width=True):
            ok, url, err = _export_dept_to_new_gsheet(dept_name, year_month, view_month)
            if ok:
                # Auto-open in new browser tab
                _components.html(
                    f'<script>window.open("{url}", "_blank");</script>',
                    height=0)
                st.success(f"✅ גיליון נוצר!")
                st.markdown(f"[🔗 פתח גיליון]({url})")
            else:
                st.error(f"שגיאה: {err}")

def _render_dept_grid(dept_name, year_month, view_month, key_ns, employees=None, max_days=None):
    """
    Render an editable grid for a single dept and month.

    Each cell has:
      - A **status button** (left-click cycles through statuses; CSS-coloured).
        If a note exists it is shown as a tooltip on this button.
      - A tiny **💬 note button** (right of each cell) that opens a popover
        for typing / clearing the note.  No checkbox or edit-mode toggle.

    The month is shown in three segments: 1-10, 11-20, 21-end.
    """
    year = 2026
    num_days = calendar.monthrange(year, view_month)[1]
    seg1 = list(range(1, 11))
    seg2 = list(range(11, 21))
    seg3 = list(range(21, num_days + 1))
    halves = [s for s in [seg1, seg2, seg3] if s]

    # Derive employees from dept_rotation if not provided
    if employees is None:
        dr = st.session_state.dept_rotation
        if dr.empty or 'employee' not in dr.columns:
            employees = []
        else:
            mask = ((dr['year_month'].astype(str) == year_month) &
                    (dr['daily_dept'].astype(str) == dept_name))
            employees = dr[mask]['employee'].astype(str).str.strip().tolist()

    if not employees:
        st.info(f"אין עובדים משובצים ל-{dept_name} בחודש זה.")
        return

    # ── Mobile toggle — auto-enable when phone detected ─────────────────────
    _mob_key = f"wsd_mob_{key_ns}"
    if _mob_key not in st.session_state:
        st.session_state[_mob_key] = bool(
            st.session_state.get('mobile_detected_persistent', False))
    is_mobile = st.toggle("📱 תצוגת מובייל", value=st.session_state[_mob_key],
                          key=_mob_key)

    if is_mobile:
        # ── Mobile: date-centric cards — נמצאים / נעדרים per day ────────────
        WD_FULL  = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]
        _ABSENT_SET = {"חופש", "202", "אחרי תורנות", "אחר"}
        all_days = list(range(1, num_days + 1))

        for d in all_days:
            date_str = f"{year}-{view_month:02d}-{d:02d}"
            wd_idx   = (date(year, view_month, d).weekday() + 1) % 7
            wd_name  = WD_FULL[wd_idx]
            is_wknd  = wd_idx in (5, 6)

            # Compute status for every employee this day
            day_working, day_absent = [], []
            for emp in employees:
                raw    = _wsd_get_status(date_str, emp, default=None)
                manual = _wsd_is_manual(date_str, emp)
                if raw is None or (raw == "עובד" and not manual):
                    status = _derive_auto_status(date_str, emp, daily_dept=dept_name)
                else:
                    status = raw
                note = _wsd_get_note(date_str, emp)
                # Fri/Sat auto-חופש → show nothing (not working, not absent listed)
                if is_wknd and status == "חופש" and not manual:
                    continue
                if status in _ABSENT_SET:
                    day_absent.append((emp, status, note))
                else:
                    day_working.append((emp, status, note))

            hdr_color = "#b91c1c" if is_wknd else "#1e3a8a"
            with st.expander(
                f"📅 {d}/{view_month} {wd_name}  "
                f"✅ {len(day_working)}  ❌ {len(day_absent)}",
                expanded=False,
            ):
                # ── נמצאים ──────────────────────────────────────────────────
                if day_working:
                    st.markdown(
                        "<div style='font-weight:700;color:#166534;"
                        "font-size:0.85rem;margin-bottom:4px'>✅ נמצאים</div>",
                        unsafe_allow_html=True)
                    for emp, status, note in day_working:
                        tag = ""
                        if status == "תורנות":
                            tag = " (תורנות)"
                        elif note:
                            tag = f" ({note})"
                        pfx      = _GRID_STATUS_PFX.get(status, "wsdcell_w")
                        cell_key = f"{pfx}_{key_ns}_md_{emp}_{d}"
                        c1, c2 = st.columns([5, 1])
                        with c1:
                            if st.button(f"{emp}{tag}", key=cell_key,
                                         use_container_width=True):
                                nxt = _GRID_STATUS_CYCLE.get(status, "חופש")
                                _wsd_upsert(date_str, emp, dept_name, nxt,
                                            is_manual=True, note=note)
                                st.rerun()
                        with c2:
                            try:
                                with st.popover("💬" if note else "+",
                                               key=f"notepop_md_{key_ns}_{emp}_{d}",
                                               use_container_width=True):
                                    st.markdown(f"<b>{emp}</b> — {d}/{view_month}",
                                                unsafe_allow_html=True)
                                    ps = st.selectbox("סטטוס:", _MANUAL_STATUSES,
                                        index=_MANUAL_STATUSES.index(status)
                                               if status in _MANUAL_STATUSES else 0,
                                        key=f"popst_md_{key_ns}_{emp}_{d}")
                                    nn = st.text_input("הערה:", value=note,
                                        key=f"popnote_md_{key_ns}_{emp}_{d}")
                                    if st.button("💾 שמור",
                                                 key=f"popsave_md_{key_ns}_{emp}_{d}",
                                                 use_container_width=True):
                                        _wsd_upsert(date_str, emp, dept_name, ps,
                                                    is_manual=True, note=nn.strip())
                                        st.rerun()
                            except Exception:
                                pass

                # ── נעדרים ──────────────────────────────────────────────────
                if day_absent:
                    st.markdown(
                        "<div style='font-weight:700;color:#991b1b;"
                        "font-size:0.85rem;margin:6px 0 4px'>❌ נעדרים</div>",
                        unsafe_allow_html=True)
                    for emp, status, note in day_absent:
                        reason = f"{status} — {note}" if note else status
                        pfx      = _GRID_STATUS_PFX.get(status, "wsdcell_h")
                        cell_key = f"{pfx}_{key_ns}_md_{emp}_{d}"
                        c1, c2 = st.columns([5, 1])
                        with c1:
                            if st.button(f"{emp} ({reason})", key=cell_key,
                                         use_container_width=True):
                                nxt = _GRID_STATUS_CYCLE.get(status, "עובד")
                                _wsd_upsert(date_str, emp, dept_name, nxt,
                                            is_manual=True, note=note)
                                st.rerun()
                        with c2:
                            try:
                                with st.popover("💬" if note else "+",
                                               key=f"notepop_md_{key_ns}_{emp}_{d}_a",
                                               use_container_width=True):
                                    st.markdown(f"<b>{emp}</b> — {d}/{view_month}",
                                                unsafe_allow_html=True)
                                    ps = st.selectbox("סטטוס:", _MANUAL_STATUSES,
                                        index=_MANUAL_STATUSES.index(status)
                                               if status in _MANUAL_STATUSES else 0,
                                        key=f"popst_md_{key_ns}_{emp}_{d}_a")
                                    nn = st.text_input("הערה:", value=note,
                                        key=f"popnote_md_{key_ns}_{emp}_{d}_a")
                                    if st.button("💾 שמור",
                                                 key=f"popsave_md_{key_ns}_{emp}_{d}_a",
                                                 use_container_width=True):
                                        _wsd_upsert(date_str, emp, dept_name, ps,
                                                    is_manual=True, note=nn.strip())
                                        st.rerun()
                            except Exception:
                                pass

                if not day_working and not day_absent:
                    st.caption("אין נתונים ליום זה")

                # ── תורנ/ית (night duty) ─────────────────────────────────
                night_worker = _get_night_duty(date_str, dept_name)
                if night_worker:
                    st.markdown(
                        f"<div style='font-size:0.82rem;color:#5b21b6;"
                        f"margin-top:6px'>🌙 תורנ/ית: <b>{night_worker}</b></div>",
                        unsafe_allow_html=True)

                # ── שישי בוקר (Friday shifts) ─────────────────────────────
                if wd_idx == 5:   # Friday
                    fri_workers = _get_fri_shift_workers(date_str, dept_name)
                    if fri_workers:
                        st.markdown(
                            f"<div style='font-size:0.82rem;color:#854d0e;"
                            f"margin-top:4px'>☀️ שישי בוקר: <b>{'  /  '.join(fri_workers)}</b></div>",
                            unsafe_allow_html=True)

        return  # skip desktop grid below

    for half_idx, days in enumerate(halves):
        if half_idx > 0:
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        n = len(days)
        # Header row — each day takes two tiny sub-cols [status, note-icon]
        cols = st.columns([3] + [2] * n)
        cols[0].markdown(
            "<div style='background:#f1f5f9;font-weight:700;text-align:center;"
            "padding:6px 2px;border-radius:6px;font-size:0.75rem;color:#334155'>עובד/ת</div>",
            unsafe_allow_html=True)
        _WD_LETTERS = ["א", "ב", "ג", "ד", "ה", "ו'", "ש'"]
        for i, d in enumerate(days):
            wd = (date(year, view_month, d).weekday() + 1) % 7
            wd_letter = _WD_LETTERS[wd]
            is_wknd_col = wd in (5, 6)
            hdr_bg = "#fef2f2" if is_wknd_col else "#f1f5f9"
            hdr_col = "#b91c1c" if is_wknd_col else "#334155"
            cols[i+1].markdown(
                f"<div style='background:{hdr_bg};font-weight:700;text-align:center;"
                f"padding:6px 2px;border-radius:6px;font-size:0.75rem;color:{hdr_col}'>{d} {wd_letter}</div>",
                unsafe_allow_html=True)

        # Data rows
        for emp in employees:
            cols = st.columns([3] + [2] * n)
            cols[0].markdown(
                f"<div style='font-weight:600;font-size:0.82rem;color:#0f172a;"
                f"padding:4px 8px;background:white;border-radius:6px;"
                f"border:1px solid #e2e8f0'>{emp}</div>",
                unsafe_allow_html=True)
            for i, d in enumerate(days):
                date_str = f"{year}-{view_month:02d}-{d:02d}"
                _wsd_raw   = _wsd_get_status(date_str, emp, default=None)
                # Re-derive when no entry or when non-manual "עובד" (picks up recurring days live)
                if _wsd_raw is None or (_wsd_raw == "עובד" and not _wsd_is_manual(date_str, emp)):
                    cur_status = _derive_auto_status(date_str, emp, daily_dept=dept_name)
                else:
                    cur_status = _wsd_raw
                cur_note   = _wsd_get_note(date_str, emp)
                label_short = _GRID_STATUS_LABEL_SHORT.get(cur_status, cur_status[:4])
                pfx = _GRID_STATUS_PFX.get(cur_status, "wsdcell_w")
                cell_key = f"{pfx}_{key_ns}_{emp}_{d}"

                _wd_cell = (date(year, view_month, d).weekday() + 1) % 7
                _is_wknd_cell = _wd_cell in (5, 6)
                _is_empty_cell = _is_wknd_cell and cur_status == "חופש" and not _wsd_is_manual(date_str, emp)
                with cols[i+1]:
                    # Fri/Sat auto-חופש → empty grey cell (no button, no note icon)
                    if _is_empty_cell:
                        st.markdown(
                            "<div style='height:32px;background:#f8fafc;"
                            "border-radius:6px;border:1px solid #e2e8f0'></div>",
                            unsafe_allow_html=True)
                        continue
                    # Split each day cell: [status button | 💬 note icon]
                    sc = st.columns([3, 1])
                    with sc[0]:
                        # Status button — click cycles status
                        if st.button(
                            label_short, key=cell_key,
                            use_container_width=True,
                            help=cur_note if cur_note else None,
                        ):
                            nxt = _GRID_STATUS_CYCLE.get(cur_status, "חופש")
                            _wsd_upsert(date_str, emp, dept_name, nxt,
                                        is_manual=True, note=cur_note)
                            st.rerun()
                    with sc[1]:
                        # Note popover — opens a small panel for editing the note
                        note_icon = "💬" if cur_note else "+"
                        note_pop_key = f"notepop_{key_ns}_{emp}_{d}"
                        try:
                            with st.popover(note_icon, key=note_pop_key,
                                            use_container_width=True):
                                st.markdown(
                                    f"<b>{emp}</b> — {d}/{view_month}",
                                    unsafe_allow_html=True)
                                # Quick status change inside the popover too
                                ps = st.selectbox(
                                    "סטטוס:", _MANUAL_STATUSES,
                                    index=_MANUAL_STATUSES.index(cur_status)
                                           if cur_status in _MANUAL_STATUSES else 0,
                                    key=f"popst_{key_ns}_{emp}_{d}",
                                )
                                new_note = st.text_input(
                                    "הערה:", value=cur_note,
                                    placeholder="הוסף הערה (לדוגמה: עוזב/ת מוקדם)",
                                    key=f"popnote_{key_ns}_{emp}_{d}",
                                )
                                if st.button("💾 שמור",
                                             key=f"popsave_{key_ns}_{emp}_{d}",
                                             use_container_width=True):
                                    _wsd_upsert(date_str, emp, dept_name, ps,
                                                is_manual=True, note=new_note.strip())
                                    st.rerun()
                        except Exception:
                            pass  # older Streamlit without popover — note editing unavailable

        # ── תורנ/ית row (one per half) ─────────────────────────────────────
        cols = st.columns([3] + [2] * n)
        cols[0].markdown(
            "<div style='background:#ede9fe;font-weight:700;text-align:center;"
            "padding:6px 2px;border-radius:6px;font-size:0.75rem;color:#5b21b6'>🌙 תורנ/ית</div>",
            unsafe_allow_html=True)
        for i, d in enumerate(days):
            date_str_nd = f"{year}-{view_month:02d}-{d:02d}"
            nd = _get_night_duty(date_str_nd, dept_name)
            _wd_nd = (date(year, view_month, d).weekday() + 1) % 7
            _cell_bg_nd = "#fef2f2" if _wd_nd in (5, 6) else "#f5f3ff"
            cols[i+1].markdown(
                f"<div style='background:{_cell_bg_nd};text-align:center;padding:4px 2px;"
                f"border-radius:6px;font-size:0.7rem;color:#6d28d9;"
                f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>"
                f"{nd or '—'}</div>",
                unsafe_allow_html=True)

        # ── שישי בוקר row (one per half) ────────────────────────────────────
        cols = st.columns([3] + [2] * n)
        cols[0].markdown(
            "<div style='background:#fef9c3;font-weight:700;text-align:center;"
            "padding:6px 2px;border-radius:6px;font-size:0.75rem;color:#854d0e'>☀️ שישי בוקר</div>",
            unsafe_allow_html=True)
        for i, d in enumerate(days):
            date_str_fri = f"{year}-{view_month:02d}-{d:02d}"
            _wd_fri = (date(year, view_month, d).weekday() + 1) % 7
            if _wd_fri == 5:   # Friday only
                fw = _get_fri_shift_workers(date_str_fri, dept_name)
                cell_txt = " / ".join(fw) if fw else "—"
                cell_bg_fri = "#fef3c7"
            else:
                cell_txt = ""
                cell_bg_fri = "#f8fafc"
            cols[i+1].markdown(
                f"<div style='background:{cell_bg_fri};text-align:center;padding:4px 2px;"
                f"border-radius:6px;font-size:0.68rem;color:#92400e;"
                f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>"
                f"{cell_txt}</div>",
                unsafe_allow_html=True)

def log_event(event_type, detail_1='', detail_2=''):
    """
    Append a single analytics event row to the 'analytics_log' Google Sheet.
    Never clears the sheet — append-only. Entire body wrapped in bare except so it
    NEVER crashes the main app. Dropped events are acceptable.
    """
    try:
        now = datetime.now()
        row = [
            str(uuid.uuid4()),                                          # event_id
            str(st.session_state.get('analytics_session_id', '')),     # session_id
            now.strftime('%Y-%m-%d %H:%M:%S'),                         # timestamp
            str(st.session_state.get('user_name', '')),                # user_name
            str(st.session_state.get('user_role', '')),                # user_role
            event_type,                                                 # event_type
            str(detail_1),                                             # detail_1
            str(detail_2),                                             # detail_2
            str(st.session_state.get('analytics_device_type', 'unknown')),  # device_type
            str(st.session_state.get('analytics_ua', ''))[:200],      # ua_string
            str(st.session_state.get('analytics_vp_width', '')),      # viewport_width
            str(st.session_state.get('active_month_int', '')),        # active_month
            str(now.day),                                              # day_of_month
        ]
        gc = get_gspread_client()
        url = st.secrets["connections"]["gsheets"]["spreadsheet"]
        sh = gc.open_by_url(url)
        # Create sheet with header on first call if missing
        try:
            ws = sh.worksheet('analytics_log')
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet('analytics_log', rows=5000, cols=13)
            ws.append_row([
                'event_id', 'session_id', 'timestamp', 'user_name', 'user_role',
                'event_type', 'detail_1', 'detail_2', 'device_type', 'ua_string',
                'viewport_width', 'active_month', 'day_of_month'
            ], value_input_option='USER_ENTERED')
        ws.append_row(row, value_input_option='USER_ENTERED')
    except Exception:
        pass  # Analytics failure must never affect the main app


import threading as _threading

def _log_async(event_type, detail_1='', detail_2=''):
    """Fire-and-forget wrapper for log_event — never blocks the UI."""
    _threading.Thread(
        target=log_event,
        args=(event_type, detail_1, detail_2),
        daemon=True,
    ).start()


def save_to_db(worksheet_name, df, is_rtl=False):
    """
    Write df to a Google Sheets worksheet. Retries up to 4 times on 429 rate-limit errors.

    SAFE write order — prevents data loss on transient API failures:
      1. ws.update()  ← write new data first (old data still present in stale rows below)
      2. ws.resize()  ← trim stale rows/cols after a successful write (soft failure OK)
    Never calls ws.clear() before writing, so a mid-write failure never leaves the sheet empty.
    """
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    df_str = df.astype(str).replace('nan', '', regex=True).replace('None', '', regex=True)
    data = [df_str.columns.tolist()] + df_str.values.tolist()
    n_rows = len(data)
    n_cols = max((len(r) for r in data), default=1)

    last_err = None
    for attempt in range(4):
        try:
            gc = get_gspread_client()
            sh = gc.open_by_url(url)
            try:
                ws = sh.worksheet(worksheet_name)
            except gspread.exceptions.WorksheetNotFound:
                ws = sh.add_worksheet(title=worksheet_name,
                                      rows=max(n_rows, 1), cols=max(n_cols, 1))

            # Write first — data is safe even if the trim below fails
            ws.update(range_name='A1', values=data, value_input_option='RAW')

            # Trim stale rows/cols that exceed the new data (soft failure is OK)
            try:
                ws.resize(rows=max(n_rows, 1), cols=max(n_cols, 1))
            except Exception:
                pass

            if is_rtl:
                try:
                    sh.batch_update({"requests": [{
                        "updateSheetProperties": {
                            "properties": {"sheetId": ws.id, "rightToLeft": True,
                                           "gridProperties": {"columnCount": 8}},
                            "fields": "rightToLeft,gridProperties.columnCount"
                        }
                    }]})
                    ws.format('A1:H1', {'textFormat': {'bold': True}, 'horizontalAlignment': 'CENTER'})
                    ws.format('A2:H100', {'horizontalAlignment': 'CENTER', 'verticalAlignment': 'MIDDLE'})
                except Exception as e:
                    print(f"RTL/Format warning: {e}")
            return  # success

        except gspread.exceptions.APIError as e:
            last_err = e
            if e.response.status_code == 429:
                wait = 2 ** attempt  # 1s, 2s, 4s, 8s
                time.sleep(wait)
                continue
            break  # non-429 API error — don't retry
        except Exception as e:
            last_err = e
            break

    st.error(f"שגיאה קריטית בשמירה לגיליון '{worksheet_name}': {last_err}")

def init_db():
    """
    Safe, additive initialisation.
    ONLY creates worksheets that do not yet exist — NEVER overwrites or clears
    any worksheet that is already present (even if it has zero data rows).
    This prevents accidental data loss on API hiccups or cold-start empty reads.
    """
    # Required sheets and their header columns
    REQUIRED_SHEETS = {
        "staff": ['name', 'type', 'dept', 'monthly_quota', 'weekend_quota',
                  'password', 'only_home_dept', 'email', 'manage_depts',
                  'recurring_absent_days'],
        "schedule":     ['date', 'dept', 'employee', 'is_manual', 'empty_reason'],
        "requests":     ['employee', 'date', 'status'],
        "special_days": ['date', 'description', 'day_type'],
        "dept_rotation":        ['employee', 'year_month', 'daily_dept'],
        "absence_requests":     ['id', 'employee', 'start_date', 'end_date', 'type',
                                 'status', 'dept_at_request', 'manager_email',
                                 'approved_by', 'notes', 'created_at', 'responded_at'],
        "work_schedule_daily":  ['date', 'employee', 'daily_dept', 'status', 'note', 'is_manual'],
    }
    SETTINGS_DEFAULTS = [
        ('active_month',        str((date.today().replace(day=1) + timedelta(days=32)).month)),
        ('daily_active_month',  str((date.today().replace(day=1) + timedelta(days=32)).month)),
        ('daily_requests_open', 'True'),
    ]

    try:
        gc  = get_gspread_client()
        url = st.secrets["connections"]["gsheets"]["spreadsheet"]
        sh  = gc.open_by_url(url)

        existing_titles = {ws.title for ws in sh.worksheets()}
        created_any = False

        for sheet_name, columns in REQUIRED_SHEETS.items():
            if sheet_name not in existing_titles:
                # Create the worksheet with just the header row — no data rows
                empty_df = pd.DataFrame(columns=columns)
                save_to_db(sheet_name, empty_df)
                created_any = True

        # settings sheet: create if missing, else only ADD missing keys (never overwrite)
        if "settings" not in existing_titles:
            next_m = (date.today().replace(day=1) + timedelta(days=32)).month
            settings_df = pd.DataFrame(
                [{'key': k, 'value': v} for k, v in SETTINGS_DEFAULTS])
            save_to_db("settings", settings_df)
            created_any = True
        else:
            # Add any settings keys that do not yet exist
            cur = get_db_data("settings")
            existing_keys = set(cur['key'].astype(str)) if not cur.empty and 'key' in cur.columns else set()
            for key, val in SETTINGS_DEFAULTS:
                if key not in existing_keys:
                    cur = pd.concat([cur, pd.DataFrame([{'key': key, 'value': val}])],
                                    ignore_index=True)
            if set(cur['key'].astype(str)) != existing_keys:
                save_to_db("settings", cur)

        if created_any:
            pass  # silent — no st.info/success shown to the user

    except Exception as e:
        if "403" in str(e) or "Public Spreadsheet" in str(e):
            st.error("שגיאת הרשאות Google Sheets — וודא ש-Secrets הוגדרו נכון.")
        # All other errors: silent — don't block the app from loading

# --- 3. ניהול התחברות (Login) ---
def login_screen():
    st.markdown("""
        <style>
            /* Center the entire screen content for login */
            .main .block-container {
                max-width: 450px !important;
                padding-top: 5rem !important;
                background-color: white;
                border-radius: 20px;
                box-shadow: 0 10px 25px rgba(0,0,0,0.05);
                margin-top: 40px;
                padding-bottom: 2rem !important;
            }
            
            div[data-testid="stTextInput"] input {
                border: 2px solid #e2e8f0 !important;
                background-color: #f8fafc;
                border-radius: 8px;
                padding: 10px;
                transition: all 0.3s;
                color: #1e293b !important; /* Ensure input text is dark */
            }
            div[data-testid="stTextInput"] input:focus {
                border-color: #3b82f6 !important;
                background-color: #ffffff;
                box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
            }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<h1 style='text-align: center; color: #1e293b; margin-bottom: 24px; font-size: 1.8rem;'>מערכת סידור עבודה המערך הגריאטרי</h1>", unsafe_allow_html=True)
    
    username = st.text_input("שם משתמש:").strip()
    password = st.text_input("סיסמה:", type="password")
    
    st.markdown("<br>", unsafe_allow_html=True) # Spacing before button
    
    if st.button("כניסה", use_container_width=True):
        # Use _fetch_live so login always reads fresh data, bypassing the cache
        # (a stale cached empty-DataFrame would otherwise block every login attempt)
        staff_df = _fetch_live("staff")
        hashed_pass = hashlib.sha256(password.encode()).hexdigest()

        # Guard: 'name' column missing means the sheet could not be read at all
        # (staff_df.empty is valid — sheet may have headers but no employees yet)
        if 'name' not in staff_df.columns:
            st.error("לא ניתן לטעון את רשימת הצוות — נסה שוב")
            st.stop()

        # בדיקה אם המשתמש קיים (strip whitespace from sheet names to avoid invisible-character mismatches)
        staff_df['name'] = staff_df['name'].astype(str).str.strip()
        user_match = staff_df[staff_df['name'] == username]
        
        if not user_match.empty:
            user = user_match[user_match['password'] == hashed_pass]
            if not user.empty:
                st.session_state.logged_in = True
                st.session_state.user_name = username
                st.session_state.user_role = user.iloc[0]['type']
                st.rerun()
            else:
                st.error("סיסמה שגויה")
                log_event('login_fail', username, 'סיסמה שגויה')
        else:
            st.error("שם המשתמש לא נמצא במערכת")
            log_event('login_fail', username, 'משתמש לא קיים')

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    login_screen()
    st.stop()
else:
    # אתחול מסד הנתונים (רק פעם אחת, אחרי כניסה — לא מוצג על מסך הכניסה)
    if 'db_initialized' not in st.session_state:
        init_db()
        st.session_state.db_initialized = True

    # --- אתחול סשן אנליטיקה (פעם אחת לכל כניסה) ---
    if 'analytics_session_id' not in st.session_state:
        st.session_state.analytics_session_id = str(uuid.uuid4())
        st.session_state.analytics_login_time = datetime.now()
        st.session_state.analytics_last_tab = None
        st.session_state.analytics_tab_enter = datetime.now()
        st.session_state.analytics_device_captured = False
        st.session_state.analytics_device_type = 'unknown'
        st.session_state.analytics_ua = ''
        st.session_state.analytics_vp_width = ''

    # --- זיהוי מכשיר ב-JS (frame 2: ה-JS מחזיר None בפריים 1, ערך בפריים 2) ---
    try:
        from streamlit_javascript import st_javascript
        _ua_cap  = st_javascript("window.navigator.userAgent", key="analytics_ua_cap")
        _vp_cap  = st_javascript("window.innerWidth",          key="analytics_vp_cap")
        if _ua_cap and isinstance(_ua_cap, str) and not st.session_state.analytics_device_captured:
            st.session_state.analytics_ua = _ua_cap
            st.session_state.analytics_vp_width = str(_vp_cap) if _vp_cap else ''
            _is_mobile = any(x in _ua_cap for x in ["Android", "iPhone", "iPad", "Mobile", "webOS"])
            _is_mobile = _is_mobile or (isinstance(_vp_cap, (int, float)) and 0 < _vp_cap < 768)
            st.session_state.analytics_device_type = 'mobile' if _is_mobile else 'desktop'
            st.session_state.analytics_device_captured = True
            _log_async('login_success', st.session_state.analytics_device_type, str(_vp_cap))
    except Exception:
        pass

    # --- הזרקת CSS ייעודי למובייל (רק למשתמש מחובר) ---
    # מונע את עיוות מסך הכניסה
    st.markdown("""
        <style>
        /* 1. Aggressive Sidebar Hiding on Mobile */
        @media (max-width: 768px) {
            section[data-testid="stSidebar"][aria-expanded="false"], 
            section[data-testid="stSidebar"][aria-hidden="true"] {
                display: none !important;
                width: 0 !important;
                flex: 0 !important;
            }
            div[data-testid="stSidebarCollapsedControl"] {
                display: none !important;
            }
            
            /* 2. Mini-Calendar Grid for Mobile (Target specific classes instead of all columns) */
            /* Wrap the calendar in a container and target that, or target the specific 7-column child count if possible */
            /* To avoid breaking Manager UI (Team/Settings/Swap), we only apply this 7-column grid to the specific Calendar container */
            div.calendar-grid-container > div[data-testid="stHorizontalBlock"],
            div[data-testid="stHorizontalBlock"]:has(> div:nth-child(7):last-child) {
                display: grid !important;
                grid-template-columns: repeat(7, 1fr) !important;
                gap: 1px !important;
                padding: 0 !important;
                width: 100% !important;
            }
            div.calendar-grid-container div[data-testid="column"],
            div[data-testid="stHorizontalBlock"]:has(> div:nth-child(7):last-child) > div[data-testid="column"] {
                width: auto !important;
                min-width: 0 !important;
                flex: 1 1 0 !important;
                padding: 1px !important;
            }
            div.calendar-grid-container div[data-testid="column"] > div,
            div[data-testid="stHorizontalBlock"]:has(> div:nth-child(7):last-child) > div[data-testid="column"] > div {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
            }
            div.calendar-grid-container div[data-testid="column"] div[data-testid="stMarkdownContainer"] p,
            div[data-testid="stHorizontalBlock"]:has(> div:nth-child(7):last-child) div[data-testid="column"] div[data-testid="stMarkdownContainer"] p {
                 font-size: 11px !important;
                 text-align: center !important;
                 margin: 0 !important;
                 line-height: 1.2 !important;
            }
            div[data-testid="stCheckbox"] {
                margin-top: -2px !important;
                justify-content: center !important;
            } 
            /* Label hiding is removed as it hides the checkbox itself in some structures. 
               We rely on label_visibility="collapsed" in Python. */
            
            div[data-testid="stCheckbox"] div[role="checkbox"] {
                transform: scale(0.75) !important;
            }

        }
        </style>
    """, unsafe_allow_html=True)

# --- Helper Function for Validity Checks (Shared by Auto-Scheduler and Swap Tool) ---
# --- Helper Function for Validity Checks (Shared by Auto-Scheduler and Swap Tool) ---
# --- Helper Function for Validity Checks (Shared by Auto-Scheduler and Swap Tool) ---
def get_functional_day_type(date_obj, special_days_df):
    """Returns the functional day type ('רגיל', 'כמו שישי (ערב חג)', 'כמו שבת (חג)')"""
    date_str = date_obj.strftime('%Y-%m-%d') if isinstance(date_obj, date) else date_obj
    if not special_days_df.empty and 'day_type' in special_days_df.columns:
        match = special_days_df[special_days_df['date'] == str(date_str)]
        if not match.empty:
            return match.iloc[0]['day_type']
    return 'רגיל'

def is_functional_weekend(date_obj, special_days_df):
    """Returns True if the date acts as a weekend, including days functioning as Friday or Saturday."""
    if isinstance(date_obj, str):
        date_obj = datetime.strptime(date_obj, '%Y-%m-%d').date()
    # 4 = Friday, 5 = Saturday
    if date_obj.weekday() in [4, 5]:
        return True
    
    day_type = get_functional_day_type(date_obj, special_days_df)
    if day_type in ['כמו שישי (ערב חג)', 'כמו שבת (חג)']:
        return True
        
    # The user specifically requested that the day BEFORE "Like Friday" behaves like a weekend day too
    tomorrow = date_obj + timedelta(days=1)
    if get_functional_day_type(tomorrow, special_days_df) == 'כמו שישי (ערב חג)':
        return True
        
    return False

def check_assignment_validity(schedule_data, person_name, check_date, target_dept, staff_df, requests_df, ignore_quota=False, ignore_home_restrict=False, ignore_rest=False):
    """
    Checks if assigning person_name to target_dept on check_date is valid.
    schedule_data: List of dicts OR DataFrame
    ignore_quota: If True, skips the max shifts check (useful for Swaps where count doesn't increase)
    ignore_home_restrict: If True, skips "Restricted to Home Dept" check
    ignore_rest: If True, skips "Rest Violation" (nearby days) check
    """
    # Normalize to list of dicts if DataFrame
    if isinstance(schedule_data, pd.DataFrame):
        schedule_data = schedule_data.to_dict('records')
        
    if person_name in ['ADMIN', '---']:
        return False, "Invalid Person"
        
    p_row = staff_df[staff_df['name'] == person_name]
    if p_row.empty: return False, "Unknown Employee"
    person = p_row.iloc[0]
    
    # --- 1. Static Constraints (Critical - Must Fail First) ---
    # Type Check (External vs Internal)
    p_type = str(person.get('type', '')).strip()
    if 'חוץ' in p_type and 'פנימית' in target_dept:
        return False, "External cannot work Internal"

    # Home Dept Check
    if not ignore_home_restrict:
        only_home = person.get('only_home_dept', False)
        if only_home:
             target_context = target_dept
             if "שישי בוקר" in target_dept:
                 target_context = "שיקום" if "שיקום" in target_dept else "פנימית גריאטרית"
             if person['dept'] != 'כללי' and person['dept'] != target_context:
                 return False, f"Restricted to Home Dept ({person['dept']})"

    # --- 2. Hard User Constraints ---
    req_date_str = requests_df['date'].astype(str)
    if not requests_df[(requests_df['employee'] == person_name) & (req_date_str == check_date) & (requests_df['status'] == "אילוץ")].empty:
        return False, "User Restriction (Blocked)"
        
    # --- 3. Quota Check ---
    # Default quota to 6 if missing
    try:
        max_quota = int(person.get('monthly_quota', 6))
    except:
        max_quota = 6

    if max_quota == 0:
        return False, "Quota is 0 (Inactive)"

    if not ignore_quota:
        # Filter for current month only
        # check_date is 'YYYY-MM-DD'
        target_month_prefix = check_date[:7] # 'YYYY-MM'
        
        current_shifts = len([
            s for s in schedule_data 
            if s['employee'] == person_name 
            and str(s['date']).startswith(target_month_prefix)
        ])
        
        if current_shifts >= max_quota:
             return False, f"Quota Exceeded ({current_shifts}/{max_quota})"

    # --- 4. Situational Constraints ---
    check_d_obj = datetime.strptime(check_date, '%Y-%m-%d').date()
    
    # Rest Check (2 days gap)
    if not ignore_rest:
        for offset in [-2, -1, 1, 2]:
            nearby_date = str(check_d_obj + timedelta(days=offset))
            if any(s for s in schedule_data if str(s['date']) == nearby_date and s['employee'] == person_name):
                return False, "Rest Violation (Worked nearby)"
            
    # Duplicate Check (Same Day)
    if any(s for s in schedule_data if str(s['date']) == check_date and s['employee'] == person_name):
        return False, "Already working this day"

    return True, "Valid"

def find_swap_candidates(schedule_df, requests_df, staff_df, user_name, swap_date, swap_dept, sel_month, year=2026):
    """
    For an employee wanting to swap their shift on (swap_date, swap_dept), find:
    - 'full': candidates who can cover the user's shift AND have a shift the user can take in return
    - 'partial': candidates who can cover the user's shift but no mutual shift was found

    Hard constraints enforced via check_assignment_validity (ignore_quota=True, since a swap
    doesn't change anyone's monthly count). The user's own shift is removed from the simulated
    schedule before validating, so the 2-day rest gap recalculates correctly.
    """
    user_name_n = str(user_name).strip()

    sched_minus_user = schedule_df[
        ~((schedule_df['date'].astype(str) == swap_date) &
          (schedule_df['employee'].astype(str).str.strip() == user_name_n) &
          (schedule_df['dept'] == swap_dept))
    ].copy()

    def _safe_q(v):
        try: return int(v)
        except: return 6

    active_staff = staff_df[
        (staff_df['name'].astype(str).str.strip() != user_name_n) &
        (staff_df['type'].astype(str).str.strip() != 'מנהל/ת')
    ].copy()
    active_staff = active_staff[active_staff['monthly_quota'].apply(_safe_q) > 0]

    req_dates = requests_df['date'].astype(str)
    req_emps = requests_df['employee'].astype(str).str.strip()
    wished_set = set(req_emps[(req_dates == swap_date) & (requests_df['status'] == 'בקשה')])

    # Search candidate's mutual shifts in the same month as the swap (derived from swap_date,
    # not the active month — handles swaps in any future month).
    month_prefix = swap_date[:7]
    full, partial = [], []

    for _, cand_row in active_staff.iterrows():
        cand_name = str(cand_row['name']).strip()

        ok, _ = check_assignment_validity(
            sched_minus_user, cand_name, swap_date, swap_dept,
            staff_df, requests_df,
            ignore_quota=True, ignore_home_restrict=False, ignore_rest=False
        )
        if not ok:
            continue

        _today_str = date.today().strftime('%Y-%m-%d')
        their_shifts = schedule_df[
            (schedule_df['employee'].astype(str).str.strip() == cand_name) &
            (schedule_df['date'].astype(str).str.startswith(month_prefix)) &
            (schedule_df['date'].astype(str) >= _today_str)   # exclude past shifts
        ]

        mutual = None
        for _, ts in their_shifts.iterrows():
            ts_date = str(ts['date'])
            ts_dept = ts['dept']

            sched_sim = sched_minus_user[
                ~((sched_minus_user['date'].astype(str) == ts_date) &
                  (sched_minus_user['employee'].astype(str).str.strip() == cand_name) &
                  (sched_minus_user['dept'] == ts_dept))
            ]
            sched_sim = pd.concat([sched_sim, pd.DataFrame([{
                'date': swap_date, 'dept': swap_dept, 'employee': cand_name,
                'is_manual': False, 'empty_reason': ''
            }])], ignore_index=True)

            ok_me, _ = check_assignment_validity(
                sched_sim, user_name_n, ts_date, ts_dept,
                staff_df, requests_df,
                ignore_quota=True, ignore_home_restrict=False, ignore_rest=False
            )
            if ok_me:
                mutual = {'date': ts_date, 'dept': ts_dept}
                break

        info = {
            'name': cand_name,
            'dept': str(cand_row.get('dept', '')),
            'type': str(cand_row.get('type', '')),
            'wished': cand_name in wished_set,
            'their_shift': mutual,
        }
        if mutual:
            full.append(info)
        else:
            partial.append(info)

    full.sort(key=lambda x: (not x['wished'], x['name']))
    partial.sort(key=lambda x: (not x['wished'], x['name']))

    # ── 3-way chain swap (only relevant when user's shift is in פנימית גריאטרית) ─
    # Logic: find a מתמחה currently on שיקום on swap_date who CAN work פנימית,
    # then simulate them moving to פנימית and check if any תורן חוץ can fill the
    # now-vacant שיקום slot. Result is a list of chain dicts.
    chain = []
    if swap_dept == 'פנימית גריאטרית':
        # Candidates for facilitator role: מתמחה assigned to שיקום on swap_date
        _facilitators_sched = sched_minus_user[
            (sched_minus_user['date'].astype(str) == swap_date) &
            (sched_minus_user['dept'] == 'שיקום') &
            (sched_minus_user['employee'].astype(str).str.strip() != user_name_n)
        ]
        _externals = staff_df[
            (staff_df['type'].astype(str).str.strip() == 'תורן חוץ') &
            (staff_df['name'].astype(str).str.strip() != user_name_n)
        ].copy()

        for _, _fac_row in _facilitators_sched.iterrows():
            _fac_name = str(_fac_row['employee']).strip()
            _fac_staff = staff_df[staff_df['name'].astype(str).str.strip() == _fac_name]
            if _fac_staff.empty:
                continue
            if str(_fac_staff.iloc[0].get('type', '')).strip() != 'מתמחה':
                continue  # must be מתמחה to work פנימית

            # Check if facilitator can work פנימית on swap_date
            _ok_fac, _ = check_assignment_validity(
                sched_minus_user, _fac_name, swap_date, 'פנימית גריאטרית',
                staff_df, requests_df, ignore_quota=True
            )
            if not _ok_fac:
                continue

            # Simulate: remove facilitator from שיקום, add them to פנימית
            _sched_sim = sched_minus_user[
                ~((sched_minus_user['date'].astype(str) == swap_date) &
                  (sched_minus_user['employee'].astype(str).str.strip() == _fac_name) &
                  (sched_minus_user['dept'] == 'שיקום'))
            ].copy()
            _sched_sim = pd.concat([_sched_sim, pd.DataFrame([{
                'date': swap_date, 'dept': 'פנימית גריאטרית', 'employee': _fac_name,
                'is_manual': False, 'empty_reason': ''
            }])], ignore_index=True)

            # Find a תורן חוץ who can now cover the vacant שיקום slot
            _fac_wished = _fac_name in wished_set
            for _, _ext_row in _externals.iterrows():
                _ext_name = str(_ext_row['name']).strip()
                _ok_ext, _ = check_assignment_validity(
                    _sched_sim, _ext_name, swap_date, 'שיקום',
                    staff_df, requests_df, ignore_quota=True
                )
                if _ok_ext:
                    chain.append({
                        'facilitator_name': _fac_name,
                        'facilitator_dept': str(_fac_staff.iloc[0].get('dept', '')),
                        'facilitator_wished': _fac_wished,
                        'external_name': _ext_name,
                        'external_wished': _ext_name in wished_set,
                    })
                    break  # one valid external per facilitator is enough

    chain.sort(key=lambda x: (not x['facilitator_wished'], not x['external_wished'], x['facilitator_name']))
    return {'full': full, 'partial': partial, 'chain': chain}

# טעינת נתונים ממסד הנתונים ל-Session State
if 'staff' not in st.session_state:
    st.session_state.staff = get_db_data("staff")
    # Initialize only_home_dept if missing
    if 'only_home_dept' not in st.session_state.staff.columns:
        st.session_state.staff['only_home_dept'] = False
    else:
        # Google Sheets returns booleans as strings "True"/"False".
        # astype(bool) on a non-empty string always returns True, so we parse manually.
        st.session_state.staff['only_home_dept'] = st.session_state.staff['only_home_dept'].apply(
            lambda v: v if isinstance(v, bool) else str(v).strip().lower() == 'true'
        )
    # Daily-schedule feature columns (added after initial DB creation — handle missing gracefully)
    if 'email' not in st.session_state.staff.columns:
        st.session_state.staff['email'] = ''
    if 'manage_depts' not in st.session_state.staff.columns:
        st.session_state.staff['manage_depts'] = ''
    if 'recurring_absent_days' not in st.session_state.staff.columns:
        st.session_state.staff['recurring_absent_days'] = ''

if 'schedule' not in st.session_state:
    st.session_state.schedule = get_db_data("schedule")
if 'requests' not in st.session_state:
    st.session_state.requests = get_db_data("requests")
if 'special_days' not in st.session_state:
    try:
        st.session_state.special_days = get_db_data("special_days")
        if 'day_type' not in st.session_state.special_days.columns:
            st.session_state.special_days['day_type'] = 'רגיל'
    except:
        st.session_state.special_days = pd.DataFrame(columns=['date', 'description', 'day_type'])
        save_to_db("special_days", st.session_state.special_days)

if 'swap_requests' not in st.session_state:
    st.session_state.swap_requests = get_db_data("swap_requests")

# ── Daily schedule feature data (load lazily, create empty if missing) ──
if 'dept_rotation' not in st.session_state:
    df = get_db_data("dept_rotation")
    if df.empty or 'employee' not in df.columns:
        df = pd.DataFrame(columns=['employee', 'year_month', 'daily_dept'])
    st.session_state.dept_rotation = df

if 'absence_requests' not in st.session_state:
    df = get_db_data("absence_requests")
    if df.empty or 'employee' not in df.columns:
        df = pd.DataFrame(columns=[
            'id', 'employee', 'start_date', 'end_date', 'type', 'status',
            'dept_at_request', 'manager_email', 'approved_by', 'notes',
            'created_at', 'responded_at'])
    st.session_state.absence_requests = df

if 'work_schedule_daily' not in st.session_state:
    df = get_db_data("work_schedule_daily")
    if df.empty or 'date' not in df.columns:
        df = pd.DataFrame(columns=[
            'date', 'employee', 'daily_dept', 'status', 'note', 'is_manual'])
    else:
        # Scope to 2026 only — prevents multi-year data from bloating session state
        df = df[df['date'].astype(str).str.startswith('2026')]
    st.session_state.work_schedule_daily = df
    _rebuild_wsd_index()   # build O(1) lookup index at session start
elif 'wsd_index' not in st.session_state:
    _rebuild_wsd_index()   # rebuild if session restored without index

# כלי שיבוץ ידני
if 'manual_date' not in st.session_state:
    st.session_state.manual_date = date(2026, 1, 1)
if 'manual_dept' not in st.session_state:
    st.session_state.manual_dept = "שיקום"
if 'manual_emp' not in st.session_state:
    st.session_state.manual_emp = st.session_state.staff['name'].iloc[0] if not st.session_state.staff.empty else ""

# --- 3. לוגיקת שיבוץ עם אבחון ---
def toggle_state(key):
    """Callback to toggle boolean state for calendar buttons"""
    if key in st.session_state:
        st.session_state[key] = not st.session_state[key]
        # st.toast(f"עודכן: {st.session_state[key]}") # Optional Debug

def render_modern_calendar(year, month, default_constraint_days, default_wish_days,
                           special_days_df=None, key_prefix='cal', show_validation=True):
    """
    Renders a unified modern calendar for constraint/wish selection using colored buttons.
    Returns (constraint_day_nums, wish_day_nums) as lists of int day numbers.
    """
    const_key = f"{key_prefix}_c_{month}"
    wish_key  = f"{key_prefix}_w_{month}"
    mode_key  = f"{key_prefix}_m_{month}"
    init_key  = f"{key_prefix}_init_{month}"
    hash_key  = f"{key_prefix}_hash_{month}"

    # Fingerprint the DB-derived defaults. If they differ from what was loaded last time
    # (e.g. employee switched, or DB updated after save), reinitialize the calendar.
    # If defaults haven't changed, session state is preserved so unsaved edits survive reruns.
    defaults_hash = (
        tuple(sorted(int(d) for d in default_constraint_days)),
        tuple(sorted(int(d) for d in default_wish_days)),
    )
    if init_key not in st.session_state or st.session_state.get(hash_key) != defaults_hash:
        st.session_state[const_key] = sorted(list(set(int(d) for d in default_constraint_days)))
        st.session_state[wish_key]  = sorted(list(set(int(d) for d in default_wish_days)))
        st.session_state[init_key]  = True
        st.session_state[hash_key]  = defaults_hash

    sel_c    = st.session_state[const_key]
    sel_w    = st.session_state[wish_key]
    pfx      = key_prefix

    # ── Legend ────────────────────────────────────────────────────
    st.markdown(
        "<div style='display:flex;gap:12px;justify-content:center;margin-bottom:8px;flex-wrap:wrap;direction:rtl;'>"
        "<span style='background:linear-gradient(135deg,#6366f1,#4f46e5);color:white;border-radius:8px;padding:4px 12px;font-size:0.8rem;font-weight:600;'>רגיל</span>"
        "<span style='background:linear-gradient(135deg,#fecaca,#f87171);color:white;border-radius:8px;padding:4px 12px;font-size:0.8rem;font-weight:600;'>🔒 חסימה</span>"
        "<span style='background:linear-gradient(135deg,#86efac,#22c55e);color:white;border-radius:8px;padding:4px 12px;font-size:0.8rem;font-weight:600;'>⭐ בקשה</span>"
        "<span style='color:#64748b;font-size:0.8rem;padding-top:4px;'>לחץ יום כדי לעבור בין המצבים</span>"
        "</div>",
        unsafe_allow_html=True
    )

    # ── Dynamic CSS: color each day cell based on its state ────────
    css_parts = [f"""
    div[class*="st-key-{pfx}_d{month}_"] button {{
        min-height: 42px !important; font-size: 0.95rem !important;
        font-weight: 600 !important; border-radius: 10px !important;
        padding: 4px 2px !important;
        background: linear-gradient(135deg, #6366f1, #4f46e5) !important;
        color: white !important; border: none !important;
        box-shadow: 0 1px 3px rgba(79,70,229,0.3) !important; transform: none !important; letter-spacing: 0 !important;
    }}
    div[class*="st-key-{pfx}_d{month}_"] button:hover {{
        background: linear-gradient(135deg, #4f46e5, #4338ca) !important;
        transform: none !important; box-shadow: 0 2px 6px rgba(79,70,229,0.4) !important;
    }}"""]
    for d in sel_c:
        css_parts.append(f"""
    div[class*="st-key-{pfx}_d{month}_{d}x"] button {{
        background: linear-gradient(135deg,#fecaca,#f87171) !important;
        color: white !important; border-color: #f87171 !important;
    }}
    div[class*="st-key-{pfx}_d{month}_{d}x"] button:hover {{
        background: linear-gradient(135deg,#f87171,#ef4444) !important;
    }}""")
    for d in sel_w:
        css_parts.append(f"""
    div[class*="st-key-{pfx}_d{month}_{d}x"] button {{
        background: linear-gradient(135deg,#86efac,#22c55e) !important;
        color: white !important; border-color: #16a34a !important;
    }}
    div[class*="st-key-{pfx}_d{month}_{d}x"] button:hover {{
        background: linear-gradient(135deg,#22c55e,#16a34a) !important;
    }}""")
    st.markdown(f"<style>{''.join(css_parts)}</style>", unsafe_allow_html=True)

    # ── Special days lookup ────────────────────────────────────────
    special_map = {}
    if special_days_df is not None and not special_days_df.empty:
        for _, row in special_days_df.iterrows():
            try:
                d_obj = datetime.strptime(row['date'], '%Y-%m-%d').date()
                if d_obj.month == month and d_obj.year == year:
                    special_map[d_obj.day] = row['description']
            except:
                pass

    # ── Day headers ────────────────────────────────────────────────
    day_headers = ["א'", "ב'", "ג'", "ד'", "ה'", "ו'", "ש'"]
    hcols = st.columns(7)
    for idx, h in enumerate(day_headers):
        is_wk_col = idx in [5, 6]
        hcols[idx].markdown(
            f"<div style='text-align:center;font-weight:700;"
            f"color:{'#7c3aed' if is_wk_col else '#64748b'};"
            f"font-size:0.8rem;padding:4px 0 2px;'>{h}</div>",
            unsafe_allow_html=True
        )

    # ── Calendar grid ──────────────────────────────────────────────
    cal_weeks = calendar.monthcalendar(year, month)
    for week in cal_weeks:
        wcols = st.columns(7)
        for col_idx, day_num in enumerate(week):
            with wcols[col_idx]:
                if day_num == 0:
                    st.write("")
                else:
                    is_c       = day_num in sel_c
                    is_w       = day_num in sel_w
                    is_special = day_num in special_map
                    icon  = "🔒" if is_c else ("⭐" if is_w else ("📌" if is_special else ""))
                    label = f"{icon}{day_num}" if icon else str(day_num)

                    if st.button(label, key=f"{pfx}_d{month}_{day_num}x", use_container_width=True):
                        # Cycle: regular → חסימה → בקשה → regular
                        if day_num in st.session_state[const_key]:
                            # חסימה → בקשה
                            st.session_state[const_key].remove(day_num)
                            st.session_state[wish_key].append(day_num)
                        elif day_num in st.session_state[wish_key]:
                            # בקשה → regular
                            st.session_state[wish_key].remove(day_num)
                        else:
                            # regular → חסימה
                            st.session_state[const_key].append(day_num)
                        st.rerun()

                    if is_special:
                        desc = special_map[day_num]
                        st.markdown(
                            f"<div title='{desc}' style='font-size:9px;color:#b91c1c;"
                            f"text-align:center;margin-top:-6px;line-height:1.2;"
                            f"white-space:normal;word-break:break-word;overflow:visible;'>"
                            f"{desc}</div>",
                            unsafe_allow_html=True
                        )

    # ── Real-time status counter ───────────────────────────────────
    days_in_month = calendar.monthrange(year, month)[1]
    if show_validation:
        all_dates_m = [date(year, month, d) for d in range(1, days_in_month + 1)]
        total_thu = sum(1 for d in all_dates_m if d.weekday() == 3)
        total_wk  = sum(1 for d in all_dates_m if d.weekday() in [4, 5])
        blocked   = [date(year, month, d) for d in sel_c]
        av_thu = total_thu - sum(1 for d in blocked if d.weekday() == 3)
        av_wk  = total_wk  - sum(1 for d in blocked if d.weekday() in [4, 5])
        thu_ok = av_thu >= 2
        wk_ok  = av_wk  >= 4

        def _chip(label, ok=None):
            if ok is None:
                bg, bc, tc = "#f1f5f9", "#e2e8f0", "#334155"
            elif ok:
                bg, bc, tc = "#dcfce7", "#22c55e", "#166534"
            else:
                bg, bc, tc = "#fee2e2", "#ef4444", "#991b1b"
            icon = (" ✅" if ok else " ⚠️") if ok is not None else ""
            return (f"<span style='background:{bg};border:1px solid {bc};border-radius:8px;"
                    f"padding:5px 12px;font-weight:600;color:{tc};"
                    f"font-size:0.85rem;white-space:nowrap;'>{label}{icon}</span>")

        st.markdown(
            f"<div style='display:flex;gap:8px;justify-content:center;margin-top:14px;"
            f"flex-wrap:wrap;direction:rtl;'>"
            f"{_chip(f'🔒 חסימות: {len(sel_c)}')}"
            f"{_chip(f'⭐ בקשות: {len(sel_w)}')}"
            f"{_chip(f'ימי ה׳ פנויים: {av_thu}/{total_thu}', thu_ok)}"
            f"{_chip(f'סופ״ש פנויים: {av_wk}/{total_wk}', wk_ok)}"
            f"</div>",
            unsafe_allow_html=True
        )

    return list(st.session_state[const_key]), list(st.session_state[wish_key])

def run_smart_scheduling(year, month, only_weekends=False):
    num_days = calendar.monthrange(year, month)[1]
    staff_df = st.session_state.staff.copy()
    
    # טעינת כל השיבוצים הקיימים (לא רק ידניים) כדי לשמר מצב קיים
    all_current_records = st.session_state.schedule.to_dict('records')
    
    # סינון מקדים:
    # 1. שומרים את כל השיבוצים של חודשים אחרים.
    # 2. בחודש הנוכחי: שומרים כל שיבוץ שיש בו עובד אמיתי (לא '---').
    #    נמחקים רק שיבוצים של '---' בחודש הנוכחי כדי לאפשר למערכת לנסות לשבץ אותם מחדש.
    new_schedule = []
    current_month_prefix = f"{year}-{month:02d}"
    
    for r in all_current_records:
        # אם התאריך לא בחודש הנוכחי - שומרים
        if not str(r['date']).startswith(current_month_prefix):
            new_schedule.append(r)
        else:
            # אם בחודש הנוכחי - שומרים רק אם זה לא כישלון ('---') 
            # (כך שאם היה כישלון, המשבצת "מתפנה" לניסיון חוזר)
            if r['employee'] != '---':
                new_schedule.append(r)
    
    work_load = {row['name']: 0 for _, row in staff_df.iterrows()}
    weekends_worked = {row['name']: set() for _, row in staff_df.iterrows()}
    last_assignment = {row['name']: -999 for _, row in staff_df.iterrows()}
    wed_counts = {row['name']: 0 for _, row in staff_df.iterrows()}
    thu_counts = {row['name']: 0 for _, row in staff_df.iterrows()}

    # איסוף נתונים לדיווח הוגנות
    initial_wed_stats = {}
    initial_thu_stats = {}

    # עדכון מונים: הפרדה בין מונים גלובליים (הוגנות) למונים חודשיים (מכסות)
    for s in new_schedule:
        if s['employee'] not in work_load or s['employee'] == '---': continue

        dt = datetime.strptime(s['date'], '%Y-%m-%d')

        # 1. מונים גלובליים (היסטוריה מלאה) - לאיזון ימי כוח
        if dt.weekday() == 2: wed_counts[s['employee']] += 1
        if dt.weekday() == 3: thu_counts[s['employee']] += 1

        # 2. last_assignment מעודכן מכל ההיסטוריה (כולל חודשים קודמים)
        # כדי שמי שעבד ב-31 למרץ לא יקבל בונוס ריווח מקסימלי ב-1 לאפריל
        if dt.toordinal() > last_assignment[s['employee']]:
            last_assignment[s['employee']] = dt.toordinal()

        # 3. מונים חודשיים בלבד - לבדיקת מכסות
        if str(s['date']).startswith(current_month_prefix):
            work_load[s['employee']] += 1

            # תיקון: החרגת שישי בוקר ממכסת הסופ"ש + שילוב "סופ"שים פונקציונליים"
            if is_functional_weekend(dt, st.session_state.special_days) and "שישי בוקר" not in s.get('dept', ''):
                weekends_worked[s['employee']].add(dt.isocalendar()[1])

    # חישוב סטטיסטיקה לפני השיבוץ הנוכחי
    avg_wed = sum(wed_counts.values()) / len(wed_counts) if wed_counts else 0
    avg_thu = sum(thu_counts.values()) / len(thu_counts) if thu_counts else 0
    
    # זיהוי עובדים שזקוקים לאיזון (מתחת לממוצע)
    priority_wed = [k for k, v in wed_counts.items() if v < avg_wed]
    priority_thu = [k for k, v in thu_counts.items() if v < avg_thu]
    
    balancing_msg = f"**דוח איזון הוגנות (רב-חודשי):**\n"
    balancing_msg += f"- **רביעי:** ממוצע {avg_wed:.1f}. תועדפו: {len(priority_wed)} עובדים.\n"
    balancing_msg += f"- **חמישי:** ממוצע {avg_thu:.1f}. תועדפו: {len(priority_thu)} עובדים.\n"
    balancing_msg += f"- **שישי בוקר:** האיזון מבוצע אוטומטית על סמך כל ההיסטוריה."

    all_dates = [date(year, month, d) for d in range(1, num_days + 1)]
    
    # סינון תאריכים לפי דרישה
    if only_weekends:
        # אם ביקשו רק סופ"שים, ניקח רק שישי-שבת או ימים מיוחדים שמוגדרים סופ"ש
        sorted_dates = [d for d in all_dates if is_functional_weekend(d, st.session_state.special_days)]
    else:
        # תעדוף סופי שבוע פונקציונליים ואז אמצע שבוע
        sorted_dates = [d for d in all_dates if is_functional_weekend(d, st.session_state.special_days)] + [d for d in all_dates if not is_functional_weekend(d, st.session_state.special_days)]
    
    # פונקציית עזר להמרה בטוחה למספר
    def safe_int(val, default=0):
        try:
            if pd.isna(val) or val == "":
                return default
            return int(float(val))
        except (ValueError, TypeError):
            return default

    for d in sorted_dates:
        d_str = str(d)
        week_num = d.isocalendar()[1]
        
        # תעדוף פנימית גריאטרית (כי רק מתמחים יכולים) ואז שיקום (שיש בו תורני חוץ)
        for dept in ["פנימית גריאטרית", "שיקום"]:
            if any(s for s in new_schedule if s['date'] == d_str and s['dept'] == dept): continue
            
            candidates = []
            failure_reasons = []
            
            for _, person in staff_df.iterrows():
                name = person['name']
                if person['type'] == 'תורן חוץ' and dept == 'פנימית גריאטרית': continue
                
                # BUG FIX: Ensure employee is not already assigned to another department on the same day
                if any(s for s in new_schedule if s['date'] == d_str and s['employee'] == name):
                    continue

                # --- Department Restriction Check ---
                only_home = person.get('only_home_dept', False)
                if only_home:
                     # Determine target shift's "Real" Department context
                     target_context = dept
                     if "שישי בוקר" in dept:
                         target_context = "שיקום" if "שיקום" in dept else "פנימית גריאטרית"
                     
                     # Enforce restriction (General staff usually exempt unless we want otherwise)
                     if person['dept'] != 'כללי' and person['dept'] != target_context:
                         # failure_reasons.append(f"{name}: מוגבל למחלקת אם")
                         continue
                # ------------------------------------

                # בדיקת מכסה קשיחה (חודשית)
                monthly_quota = safe_int(person['monthly_quota'], 0)
                if work_load[name] >= monthly_quota:
                    failure_reasons.append(f"{name}: מכסה מלאה ({monthly_quota})")
                    continue

                # שמירת מכסה רכה (Soft Quota Reservation)
                # אם אנחנו בחצי הראשון של החודש (לפני יום 15) ועובד כבר ניצל 50%+ מהמכסה שלו —
                # נדחה אותו מהמאגר הראשי כדי לשמור לו משמרות לחצי השני.
                # ה-Fallback עדיין יוכל לשלוף אותו כמוצא אחרון אם אין אף אחד אחר.
                if d.day < 15 and monthly_quota > 0 and work_load[name] >= monthly_quota * 0.5:
                    failure_reasons.append(f"{name}: שמירת מכסה (חצי ראשון)")
                    continue

                # בדיקת סופ"ש (כולל סופ"ש פונקציונלי)
                weekend_quota = safe_int(person['weekend_quota'], 0)
                if is_functional_weekend(d, st.session_state.special_days) and len(weekends_worked[name]) >= weekend_quota and week_num not in weekends_worked[name]:
                    failure_reasons.append(f"{name}: מכסת סופ\"ש")
                    continue
                
                # מנוחה - מרווח של שנתיים (2 ימים)
                # בדיקה של יומיים אחורה ויומיים קדימה
                gap_days = [-2, -1, 1, 2]
                has_rest_conflict = False
                for offset in gap_days:
                    if any(s for s in new_schedule if s['date'] == str(d + timedelta(days=offset)) and s['employee'] == name):
                        has_rest_conflict = True
                        break
                
                if has_rest_conflict:
                    failure_reasons.append(f"{name}: מרווח מנוחה")
                    continue

                # כלל שבת-רביעי למתמחים
                if person['type'] == 'מתמחה':
                    # אם היום שבת, בדוק אם שובץ ברביעי הקודם
                    if d.weekday() == 5: # שבת
                        if any(s for s in new_schedule if s['date'] == str(d - timedelta(days=3)) and s['employee'] == name):
                            failure_reasons.append(f"{name}: שובץ ברביעי")
                            continue
                    # אם היום רביעי, בדוק אם שובץ בשבת הבאה
                    if d.weekday() == 2: # רביעי
                        # בדיקה אם משובץ לשבת הבאה
                        if any(s for s in new_schedule if s['date'] == str(d + timedelta(days=3)) and s['employee'] == name):
                            failure_reasons.append(f"{name}: משובץ בשבת")
                            continue
                        # בדיקה אם משובץ לשישי הבא (כולל שישי בוקר) - לוגיקה הפוכה חדשה
                        fri_check = str(d + timedelta(days=2))
                        if any(s for s in new_schedule if s['date'] == fri_check and s['employee'] == name):
                            failure_reasons.append(f"{name}: משובץ בשישי הקרוב")
                            continue
                
                # אילוצים (חסמים)
                if not st.session_state.requests[(st.session_state.requests['employee'] == name) & (st.session_state.requests['date'] == d_str) & (st.session_state.requests['status'] == "אילוץ")].empty:
                    failure_reasons.append(f"{name}: אילוץ")
                    continue

                candidates.append(person)

            if candidates:
                # --- לוגיקה חדשה: תעדוף בקשות (Wishes - Option 3) ---
                # נבדוק אם יש מועמדים שביקשו במיוחד את המשמרת הזו (וברור שהם עומדים בכל שאר הכללים כי הם עברו את הסינון למעלה)
                requesters = st.session_state.requests[(st.session_state.requests['date'] == d_str) & (st.session_state.requests['status'] == "בקשה")]['employee'].tolist()
                
                wish_candidates = [c for c in candidates if c['name'] in requesters]
                
                # אם יש כאלו שביקשו, נצמצם את הרשימה רק אליהם
                final_pool = wish_candidates if wish_candidates else candidates
                
                # לוגיקת תיעדוף משופרת:
                # שימוש בשיטת ניקוד כדי:
                # 1. לפזר את התורנויות (מי שמילא אחוז נמוך יותר מהמכסה מקבל עדיפות)
                # 2. לתת עדיפות ברורה לתורני חוץ בימי חמישי, שישי ושבת במחלקת שיקום
                
                def calculate_score(cand):
                    name = cand['name']
                    # חישוב אחוז ניצול מכסה (נרצה לתת עדיפות למי שניצל פחות)
                    quota = safe_int(cand['monthly_quota'], 1)
                    usage_ratio = work_load[name] / quota if quota > 0 else 1.0
                    
                    # ציון בסיס: אחוז ניצול מכסה (שלילי, כי אנו רוצים יחס נמוך)
                    # מכפילים ב-100 כדי שיהיה משקל משמעותי
                    score = -usage_ratio * 100
                    
                    # פקטור פיזור: כמה ימים עברו מאז המשמרת האחרונה?
                    last_day = last_assignment.get(name, -999)
                    days_diff = d.toordinal() - last_day
                    score += days_diff * 2  # בונוס על כל יום שעבר
                    
                    # --- פקטור ריווח (Spacing/Pacing) ---
                    # המטרה: לפזר את המשמרות לאורך החודש ולמנוע דחיסה בהתחלה
                    # נחשב "קצב צפוי": באיזה יום בחודש אנו נמצאים, וכמה משמרות היה אמור לעשות עד עכשיו באופן לינארי.
                    current_day_in_month = d.day
                    month_progress = current_day_in_month / num_days # 0.0 to 1.0
                    expected_shifts = quota * month_progress
                    actual_shifts = work_load[name]
                    
                    # הציון הוא ההפרש:
                    # אם expected (2.5) > actual (1) -> נקבל 1.5 חיובי (דחוף לשבץ)
                    # אם expected (1.0) < actual (3) -> נקבל -2.0 שלילי (כבר עשה יותר מדי, להרגיע)
                    pacing_score = (expected_shifts - actual_shifts) * 500 
                    score += pacing_score
                    # ------------------------------------

                    # פקטור סופ"ש לתורני חוץ בשיקום
                    if dept == "שיקום" and cand['type'] == 'תורן חוץ':
                        # ימי חמישי (3), שישי (4), שבת (5) או סופ"ש פונקציונלי
                        if d.weekday() in [3, 4, 5] or is_functional_weekend(d, st.session_state.special_days):
                            score += 2000 # בונוס ענק שמבטיח בחירה
                    
                    # פקטור איזון ימי רביעי/חמישי למתמחים (שלא תורני חוץ)
                    if cand['type'] == 'מתמחה':
                        # יום רביעי (2) - מבוקש, ננסה לתת למי שעשה הכי מעט
                        if d.weekday() == 2:
                            score -= wed_counts[name] * 200
                        # יום חמישי (3) - לא מבוקש/קשה, ננסה לתת למי שעשה הכי מעט
                        if d.weekday() == 3:
                            score -= thu_counts[name] * 200
                            
                    # פקטור מחלקה - העדפה למחלקת האם!
                    # אם המועמד שייך למחלקה הנוכחית או ל'כללי' - מקבל בונוס
                    # אם המועמד ממחלקה אחרת - נמצא רק בעדיפות אחרונה (ענישה)
                    cand_dept = cand['dept']
                    
                    # בדיקת התאמה מלאה - אם מוגבל למחלקת אם, הציון לא רלוונטי כי הוא נפסל למעלה,
                    # אבל כאן זה נותן בונוס למי שנמצא במחלקה הנכונה
                    if cand_dept == dept or cand_dept == 'כללי':
                         score += 500
                    else:
                         score -= 5000  # קנס משמעותי מאוד (היה 500, הגברנו ל-5000 ליתר ביטחון)

                    return score

                final_choice = max(final_pool, key=calculate_score)['name']
                
                new_schedule.append({'date': d_str, 'dept': dept, 'employee': final_choice, 'is_manual': False, 'empty_reason': ''})
                work_load[final_choice] += 1
                last_assignment[final_choice] = d.toordinal()
                if d.weekday() == 2: wed_counts[final_choice] += 1
                if d.weekday() == 3: thu_counts[final_choice] += 1
                if is_functional_weekend(d, st.session_state.special_days): weekends_worked[final_choice].add(week_num)
            else:
                # --- NEW STARVATION FALLBACK ---
                fallback_pool = []
                for _, cand in staff_df.iterrows():
                    c_name = cand['name']
                    if c_name == '---' or str(c_name).upper() == 'ADMIN': continue
                    if cand['type'] == 'תורן חוץ' and dept == 'פנימית גריאטרית': continue
                    if any(s for s in new_schedule if s['date'] == d_str and s['employee'] == c_name): continue
                    req = st.session_state.requests[(st.session_state.requests['employee'] == c_name) & (st.session_state.requests['date'] == d_str) & (st.session_state.requests['status'] == 'אילוץ')]
                    if not req.empty: continue
                    
                    # HARD QUOTA CHECK: Do not bypass quotas even in fallback
                    monthly_quota = safe_int(cand['monthly_quota'], 0)
                    if work_load.get(c_name, 0) >= monthly_quota: continue
                    
                    # Weekend quota
                    weekend_quota = safe_int(cand['weekend_quota'], 0)
                    if is_functional_weekend(d, st.session_state.special_days) and len(weekends_worked.get(c_name, set())) >= weekend_quota and week_num not in weekends_worked.get(c_name, set()):
                        continue
                        
                    fallback_pool.append(c_name)
                
                if fallback_pool:
                    fallback_choice = min(fallback_pool, key=lambda x: work_load.get(x, 0))
                    new_schedule.append({'date': d_str, 'dept': dept, 'employee': fallback_choice, 'is_manual': False, 'empty_reason': 'הושלם מחוסר ברירה (הגמשת חוקים)'})
                    work_load[fallback_choice] += 1
                    last_assignment[fallback_choice] = d.toordinal()
                    if d.weekday() == 2: wed_counts[fallback_choice] += 1
                    if d.weekday() == 3: thu_counts[fallback_choice] += 1
                    if is_functional_weekend(d, st.session_state.special_days): weekends_worked[fallback_choice].add(week_num)
                    continue
                # --- END FALLBACK ---
                
                # --- לוגיקת הצעת החלפות ועזרה (Swap & Suggest) ---
                suggestions = []
                # אתחול מילון הצעות מובנה אם לא קיים (נמחק בתחילת הריצה)
                if 'swap_suggestions' not in st.session_state: st.session_state.swap_suggestions = {}
                
                # כלי עזר לבדיקת תקינות מלאה (כולל מנוחה, רצף, וכו') להחלפה
                def is_valid_assignment_for_swap(person_name, check_date, target_dept):
                    # Use the shared global validation function
                    # check_assignment_validity returns (bool, reason)
                    is_valid, _ = check_assignment_validity(new_schedule, person_name, check_date, target_dept, staff_df, st.session_state.requests)
                    return is_valid
                # נרוץ על המתמודדים שנפסלו (Candidate A) וננסה למצוא פתרון שיאפשר לשבץ אותם
                for _, person_a in staff_df.iterrows():
                    name_a = person_a['name']
                    # אם הסיבה לפסילה היא "מכסה", אין טעם להציע החלפה (אלא אם כן מגדילים ראש, אבל נתמקד באילוצי לו"ז)
                    # אבל אם הוא תפוס במקום אחר, ננסה לשחרר אותו
                    
                    # תרחיש 1: החלפה ישירה (Direct Swap)
                    # A נמצא במקום אחר באותו יום. האם אפשר למצוא מישהו (B) שיחליף את A שם?
                    parallel_shift = next((s for s in new_schedule if s['date'] == d_str and s['employee'] == name_a), None)
                    if parallel_shift:
                        other_dept = parallel_shift['dept']
                        # מחפשים מחליף (B) לתפקיד השני
                        for _, person_b in staff_df.iterrows():
                            name_b = person_b['name']
                            if name_b == name_a: continue
                            
                            # בדיקה קפדנית: האם B יכול חוקית להיכנס ל-other_dept בתאריך d_str?
                            if is_valid_assignment_for_swap(name_b, d_str, other_dept):
                                suggestions.append(f"💡 החלפה: העבר את **{name_a}** מ-{other_dept} לפה, ושבץ את **{name_b}** שם.")
                                
                                # שמירת הצעה מובנית לביצוע בלחיצה
                                core_key = f"{d_str}_{dept}" # מפתח למשבצת הריקה הנוכחית
                                if core_key not in st.session_state.swap_suggestions: st.session_state.swap_suggestions[core_key] = []
                                st.session_state.swap_suggestions[core_key].append({
                                    'type': 'direct_swap',
                                    'target_date': d_str,
                                    'conflicted_emp': name_a, # מי שאנחנו רוצים לפה
                                    'source_dept': other_dept, # מאיפה הוא בא
                                    'replacement_emp': name_b, # מי יחליף אותו שם
                                    'desc': f"{name_a} ⬅️ {name_b} ({other_dept})"
                                })
                                break 

                    # תרחיש 2: הסטה (Shift/Move)
                    # A לא יכול לעבוד היום כי עבד אתמול (מנוחה). האם אפשר להזיז את המשמרת של אתמול למישהו אחר (B)?
                    prev_conflict = next((s for s in new_schedule if s['employee'] == name_a and s['date'] in [str(d - timedelta(days=i)) for i in [1, 2]]), None)
                    if prev_conflict:
                        conf_date = prev_conflict['date']
                        conf_dept = prev_conflict['dept']
                        
                        # מחפשים מחליף (B) לתאריך ההוא
                        for _, person_b in staff_df.iterrows():
                            name_b = person_b['name']
                            if name_b == name_a: continue
                            
                            # בדיקה קפדנית: האם B יכול להיכנס ל-conf_date?
                            if is_valid_assignment_for_swap(name_b, conf_date, conf_dept):
                                # Format conf_date for display
                                conf_date_obj = datetime.strptime(conf_date, '%Y-%m-%d')
                                conf_date_fmt = conf_date_obj.strftime('%d/%m/%Y')

                                suggestions.append(f"💡 הסטה: העבר את **{name_a}** מה-{conf_date_fmt} לפה, ושבץ שם את **{name_b}**.")
                                
                                core_key = f"{d_str}_{dept}"
                                if core_key not in st.session_state.swap_suggestions: st.session_state.swap_suggestions[core_key] = []
                                st.session_state.swap_suggestions[core_key].append({
                                    'type': 'move_shift',
                                    'conflict_date': conf_date,
                                    'conflicted_emp': name_a,
                                    'conflict_dept': conf_dept,
                                    'replacement_emp': name_b,
                                    'desc': f"הסטה: {name_a} (מ-{conf_date_fmt}) ⬅️ {name_b}"
                                })
                                break

                    # תרחיש 3: שרשור משולש (Triple Swap) - בקשת המשתמש
                    # אם תרחיש 1 נכשל (לא נמצא B פנוי), אולי B תפוס במקום אחר (C) אבל C פנוי?
                    # כלומר: A בא לפה -> B מחליף את A -> C מחליף את B
                    if parallel_shift: # A תפוס ב-other_dept
                         other_dept = parallel_shift['dept']
                         # רצים שוב על B פוטנציאליים (שאולי לא פנויים)
                         for _, person_b in staff_df.iterrows():
                            name_b = person_b['name']
                            if name_b == name_a: continue
                            
                            # אם B תפוס ב-other_dept_2 בתאריך d_str
                            parallel_shift_b = next((s for s in new_schedule if s['date'] == d_str and s['employee'] == name_b), None)
                            if parallel_shift_b:
                                other_dept_b = parallel_shift_b['dept']
                                # מחפשים C שיחליף את B
                                for _, person_c in staff_df.iterrows():
                                    name_c = person_c['name']
                                    if name_c in [name_a, name_b]: continue
                                    
                                    # האם C יכול להחליף את B ב-other_dept_b?
                                    if is_valid_assignment_for_swap(name_c, d_str, other_dept_b):
                                        # האם B (אחרי שהשתחרר) יכול להחליף את A ב-other_dept?
                                        # כאן ההנחה היא ש-B עובר מ-other_dept_b ל-other_dept באותו יום. האם זה חוקי?
                                        # בדרך כלל כן, כי זה אותו יום.
                                        
                                        suggestions.append(f"💡 שרשור: {name_a} לפה, {name_b} ל-{other_dept}, {name_c} ל-{other_dept_b}.")
                                        
                                        core_key = f"{d_str}_{dept}"
                                        if core_key not in st.session_state.swap_suggestions: st.session_state.swap_suggestions[core_key] = []
                                        st.session_state.swap_suggestions[core_key].append({
                                            'type': 'triple_swap',
                                            'target_date': d_str,
                                            'emp_a': name_a, 'dept_a_origin': other_dept,
                                            'emp_b': name_b, 'dept_b_origin': other_dept_b,
                                            'emp_c': name_c,
                                            'desc': f"שרשור: {name_a} ⬅️ {name_b} ⬅️ {name_c}"
                                        })
                                        break
                                if len(suggestions) > 3: break # הגבלה שלא נתפוצץ

                # סינון כפילויות בהצגה
                unique_suggestions = list(set([s.split(":")[0] + "..." for s in suggestions])) # תקציר
                if suggestions:
                    final_msg = "לא נמצא שיבוץ מתאים עבור אף עובד.\n" + "\n".join(suggestions[:3])
                else:
                    final_msg = "לא נמצא פתרון אוטומטי (סיבות לדוגמה: " + ", ".join(list(set(failure_reasons))[:3]) + ")"
                
                new_schedule.append({'date': d_str, 'dept': dept, 'employee': '---', 'is_manual': False, 'empty_reason': final_msg})

    # --- לוגיקה חדשה: שיבוץ משמרות כמו "שישי בוקר" (4 עובדים) ---
    # רצים על כל ימי השישי האמיתיים + ימי "כמו שישי" האקסטרה
    fridays = [d for d in all_dates if d.weekday() == 4 or get_functional_day_type(d, st.session_state.special_days) == 'כמו שישי (ערב חג)']
    for fri_date in fridays:
        fri_str = str(fri_date)
        sat_date = fri_date + timedelta(days=1)
        sat_str = str(sat_date)
        
        # 1. פנימית גריאטרית (2 עובדים) - מי שעושה שישי ושבת
        fri_worker_pnimia = next((s['employee'] for s in new_schedule if s['date'] == fri_str and s['dept'] == 'פנימית גריאטרית'), None)
        sat_worker_pnimia = next((s['employee'] for s in new_schedule if s['date'] == sat_str and s['dept'] == 'פנימית גריאטרית'), None)
        
        # בדיקה אם כבר יש שיבוץ (למשל ידני)
        has_pnimia_1 = any(s for s in new_schedule if s['date'] == fri_str and s['dept'] == 'שישי בוקר - פנימית (1)')
        has_pnimia_2 = any(s for s in new_schedule if s['date'] == fri_str and s['dept'] == 'שישי בוקר - פנימית (2)')

        if not has_pnimia_1 and fri_worker_pnimia and fri_worker_pnimia != '---':
                new_schedule.append({'date': fri_str, 'dept': 'שישי בוקר - פנימית (1)', 'employee': fri_worker_pnimia, 'is_manual': False, 'empty_reason': 'נגזר אוטומטית משישי'})
        if not has_pnimia_2 and sat_worker_pnimia and sat_worker_pnimia != '---':
                new_schedule.append({'date': fri_str, 'dept': 'שישי בוקר - פנימית (2)', 'employee': sat_worker_pnimia, 'is_manual': False, 'empty_reason': 'נגזר אוטומטית משבת'})

        # 2. שיקום (2 עובדים)
        fri_worker_rehab = next((s['employee'] for s in new_schedule if s['date'] == fri_str and s['dept'] == 'שיקום'), None)
        sat_worker_rehab = next((s['employee'] for s in new_schedule if s['date'] == sat_str and s['dept'] == 'שיקום'), None)
        
        def handle_rehab_morning(worker_name, source_day, slot_num):
            target_dept = f'שישי בוקר - שיקום ({slot_num})'
            # בדיקה למניעת כפילות עם שיבוץ ידני
            if any(s for s in new_schedule if s['date'] == fri_str and s['dept'] == target_dept): return

            if not worker_name or worker_name == '---': return

            # בדיקת סוג העובד
            w_type = None
            if worker_name in staff_df['name'].values:
                w_type = staff_df[staff_df['name'] == worker_name]['type'].iloc[0]
            
            if w_type == 'מתמחה':
                # אם זה מתמחה - הוא עושה את הבוקר
                new_schedule.append({'date': fri_str, 'dept': target_dept, 'employee': worker_name, 'is_manual': False, 'empty_reason': f'נגזר אוטומטית מ{source_day}'})
            else:
                # אם זה תורן חוץ - מחפשים מחליף (מתמחה משיקום)
                # קריטריונים: מחלקת שיקום, פנוי בשישי, עומד בבדיקת מנוחה ±2 ימים
                candidates = []
                for _, row in staff_df.iterrows():
                    if row['type'] == 'מתמחה' and row['dept'] == 'שיקום' and row['name'] != worker_name:
                        emp = row['name']
                        
                        # האם פנוי ביום שישי (אילוץ - חסם)
                        is_blocked = not st.session_state.requests[(st.session_state.requests['employee'] == emp) & (st.session_state.requests['date'] == fri_str) & (st.session_state.requests['status'] == "אילוץ")].empty
                        if is_blocked: continue
                        
                        # בדיקת מנוחה: ±2 ימים מסביב ליום שישי
                        has_rest_conflict = any(
                            s['employee'] == emp and s['date'] == str(fri_date + timedelta(days=offset))
                            for s in new_schedule for offset in [-2, -1, 1, 2]
                        )
                        if has_rest_conflict: continue

                        # האם כבר משובץ בשישי במקום אחר (למשל תורנות רגילה במחלקת שיקום בצד השני?)
                        if any(s['employee'] == emp and s['date'] == fri_str for s in new_schedule): continue
                        
                        # HARD QUOTA CHECK: האם המכסה החודשית שלו חוסמת אותו?
                        monthly_quota = safe_int(row['monthly_quota'], 0)
                        if work_load.get(emp, 0) >= monthly_quota: continue

                        # חישוב ציון הוגנות: כמה שישי בוקר כבר יש לו?
                        fri_morning_count = len([s for s in new_schedule if s['employee'] == emp and 'שישי בוקר' in s['dept']])
                        candidates.append((emp, fri_morning_count))
                
                # מיון לפי הכמות הכי קטנה של שישי בוקר (איזון)
                if candidates:
                    candidates.sort(key=lambda x: x[1]) # מהקטן לגדול
                    best_candidate = candidates[0][0]
                    new_schedule.append({'date': fri_str, 'dept': target_dept, 'employee': best_candidate, 'is_manual': False, 'empty_reason': f'השלמה במקום {worker_name}'})
                    work_load[best_candidate] += 1 # עדכון מכסה כדי למנוע חריגה בחיפושים הבאים באותה ריצה
                else:
                    new_schedule.append({'date': fri_str, 'dept': target_dept, 'employee': '---', 'is_manual': False, 'empty_reason': 'לא נמצא מחליף לבוקר'})

        handle_rehab_morning(fri_worker_rehab, "שישי", "1")
        handle_rehab_morning(sat_worker_rehab, "שבת", "2")

    # יצירת DataFrame סופי וניקוי כפילויות (הגנה הרמטית)
    final_df = pd.DataFrame(new_schedule)
    if not final_df.empty:
        # אם יש כפילות של תאריך+מחלקה, משאירים את הראשון (שהוא הידני כי הוא הוסף ראשון)
        final_df = final_df.drop_duplicates(subset=['date', 'dept'], keep='first')

    st.session_state.schedule = final_df
    save_to_db("schedule", st.session_state.schedule)
    
    # הצגת דוח האיזון למשתמש
    st.info(balancing_msg)
# --- 4. פונקציית ציור הלוח ---
def draw_calendar_view(year, month, role, user_name=None):
    # --- Pre-compute availability (admin only, only when ALL employees submitted) ---
    show_availability = False
    date_availability = {}  # {date_str: [available_names]}

    if role == "מנהל/ת":
        month_prefix = f"{year}-{month:02d}"
        active_staff = st.session_state.staff[
            st.session_state.staff['type'].isin(['מתמחה', 'תורן חוץ']) &
            ~st.session_state.staff['name'].isin(['---', 'ADMIN'])
        ]
        reqs_month = st.session_state.requests[
            st.session_state.requests['date'].astype(str).str.startswith(month_prefix)
        ] if not st.session_state.requests.empty else pd.DataFrame()

        submitted_names  = set(reqs_month['employee'].astype(str).str.strip().unique()) if not reqs_month.empty else set()
        all_active_names = set(active_staff['name'].dropna().astype(str).str.strip().tolist())
        show_availability = bool(all_active_names) and all_active_names.issubset(submitted_names)

        if show_availability:
            # Build per-employee blocked/wished sets for this month
            blocked_dates = {}   # emp -> set of date strings
            wished_dates  = {}   # emp -> set of date strings
            if not reqs_month.empty:
                for _, r in reqs_month.iterrows():
                    emp = str(r['employee']).strip()
                    d   = str(r['date'])[:10]
                    if r['status'] == 'אילוץ':
                        blocked_dates.setdefault(emp, set()).add(d)
                    elif r['status'] == 'בקשה':
                        wished_dates.setdefault(emp, set()).add(d)

            num_days = calendar.monthrange(year, month)[1]
            sched_records = st.session_state.schedule.to_dict('records') if not st.session_state.schedule.empty else []

            date_wished = {}  # {date_str: [wished_names]}
            for day in range(1, num_days + 1):
                d_str = f"{year}-{month:02d}-{day:02d}"
                assigned_today = {s['employee'] for s in sched_records if str(s['date']) == d_str and s['employee'] != '---'}
                wished   = []
                available = []
                for _, emp in active_staff.iterrows():
                    name = str(emp['name']).strip()
                    if d_str in blocked_dates.get(name, set()):  continue  # blocked
                    if name in assigned_today:                    continue  # already scheduled
                    if d_str in wished_dates.get(name, set()):
                        wished.append(name)
                    else:
                        available.append(name)
                date_wished[d_str]       = wished
                date_availability[d_str] = available

    # Toggle for Mobile View (List vs Grid)
    # Mobile Detection
    # Mobile Detection
    if 'mobile_detected_persistent' not in st.session_state:
        st.session_state.mobile_detected_persistent = False
        
    try:
        from streamlit_javascript import st_javascript
        # Check User Agent and Width — run once per session, not every rerun
        if not st.session_state.get('analytics_device_captured'):
            ua_string = st_javascript("window.navigator.userAgent", key="ua_check_1")
            ui_width  = st_javascript("window.innerWidth",          key="width_check_1")
        else:
            ua_string = st.session_state.get('analytics_ua', '')
            ui_width  = st.session_state.get('analytics_vp_width', 0) or 0
        
        # 1. User Agent Check
        if ua_string and isinstance(ua_string, str):
             if any(x in ua_string for x in ["Android", "iPhone", "iPad", "Mobile", "webOS"]):
                 st.session_state.mobile_detected_persistent = True
                 
        # 2. Width Check (Backup)
        if ui_width and isinstance(ui_width, int) and 300 < ui_width < 768:
             st.session_state.mobile_detected_persistent = True
             
    except:
        pass

    is_mobile_view = st.toggle("📱 תצוגת רשימה", value=st.session_state.mobile_detected_persistent, key="mobile_list_view")

    cal = calendar.monthcalendar(year, month)
    
    if is_mobile_view:
        # ── Night-shift mobile: one collapsible card per day ────────────────
        WD_FULL_N = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]

        # Collect special days
        month_special_days = {}
        if "special_days" in st.session_state and not st.session_state.special_days.empty:
            for _, row in st.session_state.special_days.iterrows():
                month_special_days[str(row["date"])[:10]] = row["description"]

        month_sched = st.session_state.schedule
        num_days_m  = calendar.monthrange(year, month)[1]

        for day in range(1, num_days_m + 1):
            date_str = f"{year}-{month:02d}-{day:02d}"
            wd_idx   = (date(year, month, day).weekday() + 1) % 7
            wd_name  = WD_FULL_N[wd_idx]
            is_wknd  = wd_idx in (5, 6)

            day_rows = month_sched[month_sched["date"].astype(str) == date_str].copy()
            if role != "מנהל/ת":
                day_rows = day_rows[
                    (day_rows["employee"].astype(str).str.strip() == str(user_name).strip()) |
                    (day_rows["employee"] == "---")
                ]
            if day_rows.empty and role != "מנהל/ת":
                continue

            # Build display groups: main depts / friday morning / empty slots
            mains, friday_m, empty_slots = [], [], []
            for _, row in day_rows.iterrows():
                emp  = str(row["employee"]).replace("👤", "").replace("🛡️", "").replace("🍼", "").strip()
                dept = str(row["dept"])
                if emp == "---" or emp == "":
                    empty_slots.append(dept)
                elif "שישי בוקר" in dept:
                    friday_m.append((dept, emp))
                else:
                    mains.append((dept, emp))

            sd_suffix = f" — {month_special_days[date_str]}" if date_str in month_special_days else ""
            n_assigned = len(mains) + len(friday_m)
            n_empty    = len(empty_slots)

            with st.expander(
                f"📅 {day}/{month} {wd_name}{sd_suffix}  ✅ {n_assigned}  ⚠️ {n_empty}",
                expanded=False,
            ):
                if mains:
                    st.markdown(
                        "<div style='font-weight:700;font-size:0.85rem;margin-bottom:4px'>✅ משמרות לילה</div>",
                        unsafe_allow_html=True)
                    for dept, emp in mains:
                        dept_color = "#1e3a8a" if "שיקום" in dept else "#9a3412"
                        st.markdown(
                            f"<div style='margin-right:6px;font-size:0.92rem;padding:2px 0'>"
                            f"<span style='color:{dept_color};font-weight:600'>{dept}:</span> {emp}</div>",
                            unsafe_allow_html=True)
                if friday_m:
                    st.markdown(
                        "<div style='font-weight:700;font-size:0.85rem;margin:6px 0 4px'>☀️ שישי בוקר</div>",
                        unsafe_allow_html=True)
                    for dept, emp in friday_m:
                        st.markdown(
                            f"<div style='margin-right:6px;font-size:0.92rem;padding:2px 0'>"
                            f"<span style='color:#854d0e;font-weight:600'>{dept}:</span> {emp}</div>",
                            unsafe_allow_html=True)
                if empty_slots:
                    st.markdown(
                        "<div style='font-weight:700;color:#991b1b;font-size:0.85rem;margin:6px 0 4px'>"
                        "⚠️ ריקים</div>",
                        unsafe_allow_html=True)
                    for dept in empty_slots:
                        st.markdown(
                            f"<div style='color:#991b1b;font-size:0.85rem;margin-right:6px'>{dept}</div>",
                            unsafe_allow_html=True)
                if not mains and not friday_m and not empty_slots:
                    st.caption("אין שיבוצים")

                # Availability panel (admin only, after all submitted)
                if show_availability:
                    wished_here = date_wished.get(date_str, [])
                    avail       = date_availability.get(date_str, [])
                    if wished_here:
                        st.markdown(
                            f"<div style='font-size:11px;color:#854d0e;margin-top:4px'>⭐ ביקשו: {', '.join(wished_here)}</div>",
                            unsafe_allow_html=True)
                    if avail:
                        st.markdown(
                            f"<div style='font-size:11px;color:#166534'>✅ זמינים: {', '.join(avail)}</div>",
                            unsafe_allow_html=True)
                    if not wished_here and not avail:
                        st.markdown(
                            "<div style='font-size:11px;color:#991b1b'>⚠️ אין זמינים</div>",
                            unsafe_allow_html=True)
    else:
        # --- Standard Grid View ---
        days_names = ["א'", "ב'", "ג'", "ד'", "ה'", "ו'", "ש'"]
        st.markdown('<div class="calendar-grid-container">', unsafe_allow_html=True)
        header_cols = st.columns(7)
        for i, name in enumerate(days_names):
            header_cols[i].markdown(f"<div style='text-align: center; font-weight: bold;'>{name}</div>", unsafe_allow_html=True)
    
        for week in cal:
            cols = st.columns(7)
            for i, day in enumerate(week):
                if day == 0: continue
                with cols[i]:
                    date_str = f"{year}-{month:02d}-{day:02d}"
                    is_weekend = "weekend-day" if i >= 5 else ""
                    day_sched = st.session_state.schedule[st.session_state.schedule['date'] == date_str]
                    
                    html = f'<div class="calendar-day {is_weekend}"><div class="day-number">{day}</div>'
                    
                    # Add special day note in grid
                    if 'special_days' in st.session_state and not st.session_state.special_days.empty:
                        sd_match = st.session_state.special_days[st.session_state.special_days['date'] == date_str]
                        if not sd_match.empty:
                            sd_desc = sd_match.iloc[0]['description']
                            html += f'<div style="font-size:10px; color:#b91c1c; font-weight:bold; text-align:center; padding-bottom:5px;">{sd_desc}</div>'
                            
                    for dept in ["שיקום", "פנימית גריאטרית", "שישי בוקר - שיקום (1)", "שישי בוקר - שיקום (2)", "שישי בוקר - פנימית (1)", "שישי בוקר - פנימית (2)"]:
                        rows = day_sched[day_sched['dept'] == dept]
                        # אם מדובר בשישי בוקר ואין שורה כזו (כי זה לא יום שישי), דלג
                        if "שישי בוקר" in dept and rows.empty: continue
                        
                        # שינוי: ריצה על כל השורות שנמצאו (כדי לתמוך בכפילויות, למשל 2 תורני בוקר)
                        for _, row in rows.iterrows():
                            val = row['employee']
                            reason = row['empty_reason'] if val == "---" else ""
                            
                            # פילטור עבור מתמחים - רואים רק את השיבוצים של עצמם
                            if role != "מנהל/ת" and val != user_name and val != "---":
                                continue
                                
                            css = "shikum-slot" if "שיקום" in dept else "pnimia-slot"
                            if val == "---": css = "empty-slot"
                            
                            label = "שיקום" if dept == "שיקום" else "פנימית"
                            if "שישי בוקר" in dept: label = "בוקר (" + ("שיקום" if "שיקום" in dept else "פנימית") + ")"
                            
                            html += f'<div class="slot {css}"><span class="dept-label">{label}</span> <span>{val}</span>'
                            if role == "מנהל/ת" and reason:
                                html += f'<span class="error-hint">❓ {reason}</span>'
                            html += '</div>'
                    
                    # הצגת אילוצים ובקשות (למנהל בלבד או לעובד על עצמו)
                    if role == "מנהל/ת":
                        reqs = st.session_state.requests[st.session_state.requests['date'] == date_str]
                        for _, r in reqs.iterrows():
                            icon = "❌" if r['status'] == "אילוץ" else "⭐"
                            html += f'<div style="font-size:10px; color:{"#991b1b" if r["status"] == "אילוץ" else "#eab308"};">{icon} {r["employee"]}</div>'

                    # Availability panel — shown only after all employees submitted
                    if show_availability:
                        wished_here = date_wished.get(date_str, [])
                        avail       = date_availability.get(date_str, [])
                        avail_html  = ''
                        if wished_here:
                            avail_html += (
                                f'<div style="font-size:9px; color:#854d0e; margin-top:4px;'
                                f' border-top:1px dashed #fde68a; padding-top:3px; line-height:1.5;">'
                                f'⭐ ביקשו:<br>{"<br>".join(wished_here)}</div>'
                            )
                        if avail:
                            avail_html += (
                                f'<div style="font-size:9px; color:#166534; margin-top:2px;'
                                f' line-height:1.5;">'
                                f'✅ זמינים:<br>{"<br>".join(avail)}</div>'
                            )
                        if not wished_here and not avail:
                            avail_html = '<div style="font-size:9px; color:#991b1b; margin-top:4px; border-top:1px dashed #fca5a5; padding-top:3px;">⚠️ אין זמינים</div>'
                        html += avail_html

                    st.markdown(html + "</div>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # --- Smart Swap Assistant (Manager Only) ---
    if role == "מנהל/ת":
        st.divider()
        st.subheader("🤖 עוזר החלפות חכם")
        st.caption("כלי זה מציע החלפות משמרת לפי חוקיות: פנויים, החלפות הדדיות, והחלפות משולשות.")
        
        # On mobile, we avoid tight column wrapping by using stack layout logic (handled natively if grid block removed above)
        c1, c2 = st.columns(2)
        # Safe Date Input
        try:
            default_d = date(year, month, 1)
            max_d = date(year, month, calendar.monthrange(year, month)[1])
        except:
             default_d = date(2026, 1, 1)
             max_d = date(2026, 12, 31)

        target_date_swap = c1.date_input("תאריך לבדיקה", value=default_d, min_value=default_d, max_value=max_d)
        target_dept_swap = c2.selectbox("מחלקה/משמרת", ["שיקום", "פנימית גריאטרית", "שישי בוקר - שיקום (1)", "שישי בוקר - שיקום (2)", "שישי בוקר - פנימית (1)", "שישי בוקר - פנימית (2)"])
        
        # Analyze Current Slot
        t_date_str = str(target_date_swap)
        sche_df = st.session_state.schedule
        
        # Robust filtering with strip() to avoid whitespace mismatches
        current_assignment = sche_df[
            (sche_df['date'] == t_date_str) & 
            (sche_df['dept'].astype(str).str.strip() == target_dept_swap.strip())
        ]
        
        current_emp = "---"
        if not current_assignment.empty:
            current_emp = current_assignment.iloc[0]['employee']
        
        st.info(f"**מצב נוכחי:** {target_dept_swap} ב-{target_date_swap.strftime('%d/%m')}: **{current_emp}**")
        
        if st.button("🔍 מצא החלפות אפשריות"):
            candidates_direct = []
            candidates_exchange = []
            candidates_triple = []
            
            # Debug counters
            failure_reasons = {}
            debug_log = []
            
            # Pre-fetch data
            staff_df = st.session_state.staff
            requests_df = st.session_state.requests
            
            # CRITICAL FIX: Limit schedule analysis STRICTLY to the target month to prevent March swaps in February
            t_month_prefix = t_date_str[:7]
            schedule_records = [s for s in sche_df.to_dict('records') if str(s['date']).startswith(t_month_prefix)]
            
            debug_log.append(f"Target: {target_dept_swap} on {t_date_str}, Current: {current_emp}")
            
            # Count how many people work on the target date
            workers_on_date = [s for s in schedule_records if str(s['date']) == t_date_str]
            debug_log.append(f"Workers on {t_date_str}: {len(workers_on_date)}")
            for w in workers_on_date:
                debug_log.append(f"  - {w['employee']} @ {w['dept']}")
            
            # 1. Direct Replacements (Free & Valid)
            # 2. Exchanges (Busy but can swap)
            
            for _, person in staff_df.iterrows():
                p_name = person['name']
                # Filter out ADMIN (Case Insensitive), placeholder, and current employee
                if str(p_name).upper() == 'ADMIN' or p_name == '---' or p_name == current_emp: continue
                
                # Check validity for TARGET spot
                # Relaxed constraints for Manager Swap: Quota, Home Dept, Rest - but keep External/Internal check
                is_valid, reason = check_assignment_validity(
                    schedule_records, p_name, t_date_str, target_dept_swap, staff_df, requests_df,
                    ignore_quota=True, ignore_home_restrict=True, ignore_rest=True
                )

                if is_valid:
                    candidates_direct.append(p_name)
                else:
                    # Log failure reason
                    failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
                    
                    # Logic: If failed due to a constraint we can relax for Swaps (because they are busy and we keep invariant)
                    ignorable_for_swap = ["Quota Exceeded", "Restricted to Home Dept", "Rest Violation", "Already working"]
                    is_ignorable = any(ign in reason for ign in ignorable_for_swap)
                    
                    if is_ignorable:
                        # Check if they are actually working today (Condition for Exchange)
                        other_spot = next((s for s in schedule_records if str(s['date']) == t_date_str and s['employee'] == p_name), None)
                        
                        if other_spot:
                            other_dept = other_spot['dept']
                            
                            # Re-validate B for Target with relaxed rules
                            is_valid_relaxed, reason_relaxed = check_assignment_validity(
                                schedule_records, p_name, t_date_str, target_dept_swap, staff_df, requests_df,
                                ignore_quota=True, ignore_home_restrict=True, ignore_rest=True
                            )
                            
                            # If valid (or blocked only by "Already working" which is expected)
                            if is_valid_relaxed or reason_relaxed == "Already working this day":
                                
                                # --- Exchange Check (A <-> B) ---
                                # Can Current Emp (A) take Other Spot (B's spot)?
                                if current_emp != "---":
                                    valid_for_a, reason_a = check_assignment_validity(
                                        schedule_records, current_emp, t_date_str, other_dept, staff_df, requests_df, 
                                        ignore_quota=True, ignore_home_restrict=True, ignore_rest=True
                                    )
                                    
                                    if valid_for_a or reason_a == "Already working this day": 
                                        # --- Strict Constraints Check ---
                                        # 1. Morning <-> Morning
                                        is_target_morning = 'שישי בוקר' in target_dept_swap or 'שיקום (1)' in target_dept_swap or 'שיקום (2)' in target_dept_swap
                                        is_other_morning = 'שישי בוקר' in other_dept or 'שיקום (1)' in other_dept or 'שיקום (2)' in other_dept
                                        
                                        # 2. Weekday <-> Weekday
                                        t_date_obj = datetime.strptime(t_date_str, '%Y-%m-%d')
                                        is_target_weekend = t_date_obj.weekday() in [4, 5]
                                        # Since exchange is same day, date is same. So this check is always passed logic-wise.
                                        
                                        if is_target_morning == is_other_morning:
                                             candidates_exchange.append({'name': p_name, 'dept': other_dept})

                            # --- Triple Swap Skipped (User Request) ---
            
            # Store results in Session State
            st.session_state['swap_results'] = {
                'direct': candidates_direct,
                'exchange': candidates_exchange,
                'triple': candidates_triple,
                'date': t_date_str,
                'dept': target_dept_swap,
                'fail_reasons': failure_reasons
            }

            # --- Advanced Swaps (Cross-Date) ---
            # Added as per user request for "Mutual Cross-Date" and "Circular Cross-Date"
            
            advanced_log = []
            
            # Helper for strict constraints
            def check_advanced_constraints(date1, dept1, date2, dept2):
                # 1. Morning Swap Rule: Morning only with Morning
                is_m1 = 'שישי בוקר' in dept1 or 'שיקום (1)' in dept1 or 'שיקום (2)' in dept1
                is_m2 = 'שישי בוקר' in dept2 or 'שיקום (1)' in dept2 or 'שיקום (2)' in dept2
                if is_m1 != is_m2: return False
                
                # 2. Weekend Swap Rule: Weekend only with Weekend
                # Weekday: Sun(6), Mon(0)-Thu(3). Weekend: Fri(4), Sat(5).
                d1 = datetime.strptime(date1, '%Y-%m-%d')
                d2 = datetime.strptime(date2, '%Y-%m-%d')
                is_w1 = d1.weekday() in [4, 5]
                is_w2 = d2.weekday() in [4, 5]
                if is_w1 != is_w2: return False
                
                return True

            # Helper for consecutive check (Zero Gap)
            def is_creating_consecutive_violation(emp, new_date, schedule_data):
                # Check if emp works on new_date +/- 1 day
                d_obj = datetime.strptime(new_date, '%Y-%m-%d').date()
                for offset in [-1, 1]:
                    check_s = str(d_obj + timedelta(days=offset))
                    # Ignore if the conflict is the slot we are moving OUT of? 
                    # No, we assume we move TO new_date.
                    if any(s for s in schedule_data if s['date'] == check_s and s['employee'] == emp):
                        return True
                return False
            
            # 4. Mutual Cross-Date Swaps
            # Scenario: A is on Date 1 (Target). B is on Date 2.
            # Proposal: A goes to Date 2 (replacing B), B goes to Date 1 (replacing A).
            
            candidates_mutual_cross = []
            
            # We iterate over all OTHER assignments in the schedule (same month)
            # To optimize, we focus on the displayed month or the relevant range
            
            if current_emp != "---":
                for s_rec in schedule_records:
                    # Skip same date (already covered by Exchange)
                    if s_rec['date'] == t_date_str: continue
                    
                    # Skip empty slots or Admin
                    other_emp = s_rec['employee']
                    if other_emp == "---" or other_emp == 'ADMIN': continue
                    if other_emp == current_emp: continue # Can't swap with self
                    
                    other_date = s_rec['date']
                    other_dept = s_rec['dept']
                    
                    # Check 1: Can 'Other Emp' (B) move to 'Target Date' (Date 1) in 'Target Dept'?
                    # We use relaxed constraints because B is technically busy on Date 2, but we are moving them.
                    # We must ensure B is NOT busy on Date 1 (unless they are, which blocks them).
                    
                    valid_b_to_target, reason_b = check_assignment_validity(
                        schedule_records, other_emp, t_date_str, target_dept_swap, staff_df, requests_df,
                        ignore_quota=True, ignore_home_restrict=True, ignore_rest=True
                    )
                    
                    # If B is working on target date, they can't move here (unless we do complex 3-way, but let's keep simple)
                    if not valid_b_to_target:
                         # unique constraint: invalid because "Already working" is acceptable IF we were swapping same day, 
                         # but here we are swapping CROSS date. So if B is working on Date 1, they can't take A's spot on Date 1.
                         continue
                         
                    # Check 2: Can 'Current Emp' (A) move to 'Other Date' (Date 2) in 'Other Dept'?
                    # We need to verify A is not busy on Date 2 (unless they are, which blocks them).
                    
                    valid_a_to_other, reason_a = check_assignment_validity(
                        schedule_records, current_emp, other_date, other_dept, staff_df, requests_df,
                        ignore_quota=True, ignore_home_restrict=True, ignore_rest=True
                    )
                    
                    if not valid_a_to_other:
                        continue
                        
                    # --- NEW STRICT CHECKS ---
                    if not check_advanced_constraints(t_date_str, target_dept_swap, other_date, other_dept):
                         continue
                    
                    if is_creating_consecutive_violation(current_emp, other_date, schedule_records):
                         continue
                    if is_creating_consecutive_violation(other_emp, t_date_str, schedule_records):
                         continue
                    # -------------------------

                    # If both valid, we have a match!
                    candidates_mutual_cross.append({
                        'b_name': other_emp,
                        'b_date': other_date,
                        'b_dept': other_dept
                    })
            
            st.session_state['swap_results']['mutual_cross'] = candidates_mutual_cross


            # 5. Circular Cross-Date Swaps (A -> B, B -> C, C -> A)
            # Date 1 (Target): A is here. We want C here.
            # Date 2: B is here. We want A here.
            # Date 3: C is here. We want B here.
            
            candidates_circular = []
            
            # This is O(N^2) or O(N^3) search space. We must limit it.
            # We already know who can accept A (from Mutual search step 2).
            # Let's refine:
            
            # Step 1: Find potential "Date 2" slots where A can go.
            # list of (Date 2, Dept 2, Person B) where A -> (Date 2, Dept 2) is valid.
            
            potential_destinations_for_a = []
            if current_emp != "---":
                for s_rec in schedule_records:
                    if s_rec['date'] == t_date_str: continue # distinct dates
                    person_b = s_rec['employee']
                    if person_b == "---" or person_b == 'ADMIN' or person_b == current_emp: continue
                    
                    valid_a, _ = check_assignment_validity(
                        schedule_records, current_emp, s_rec['date'], s_rec['dept'], staff_df, requests_df,
                        ignore_quota=True, ignore_home_restrict=True, ignore_rest=True
                    )
                    if valid_a:
                        potential_destinations_for_a.append(s_rec)
            
            # Step 2: For each such slot, Person B needs to go somewhere (Date 3).
            # We look for a "Date 3" slot where Person C exists, and B can go there.
            # AND matching that C can go to "Date 1" (Target).
            
            # Optimization: Pre-calculate who can go to Target (Date 1).
            # list of Person C who can Validly work at (Target Date, Target Dept)
            potential_replacements_for_a = []
            for _, person in staff_df.iterrows():
                c_name = person['name']
                if c_name == current_emp or c_name == 'ADMIN' or c_name == '---': continue
                
                # C must not be working on Date 1
                is_busy_on_target = any(s['date'] == t_date_str and s['employee'] == c_name for s in schedule_records)
                if is_busy_on_target: continue
                
                val_c, _ = check_assignment_validity(
                    schedule_records, c_name, t_date_str, target_dept_swap, staff_df, requests_df,
                    ignore_quota=True, ignore_home_restrict=True, ignore_rest=True
                )
                if val_c:
                    potential_replacements_for_a.append(c_name)
                    
            # Now Step 2 loop
            import random
            # Limit loop if too huge
            for b_rec in potential_destinations_for_a[:50]: 
                person_b = b_rec['employee']
                date_2 = b_rec['date']
                dept_2 = b_rec['dept']
                
                # Find where B can go (Date 3) where Person C is one of 'potential_replacements_for_a'
                # We iterate over slots occupied by potential C's
                
                for c_name in potential_replacements_for_a:
                    if c_name == person_b: continue 
                    
                    # Find slots occupied by C (Date 3)
                    c_slots = [s for s in schedule_records if s['employee'] == c_name and s['date'] != t_date_str and s['date'] != date_2]
                    
                    for c_rec in c_slots:
                        date_3 = c_rec['date']
                        dept_3 = c_rec['dept']
                        
                        # Check: Can B go to (Date 3, Dept 3)?
                        valid_b, _ = check_assignment_validity(
                            schedule_records, person_b, date_3, dept_3, staff_df, requests_df,
                            ignore_quota=True, ignore_home_restrict=True, ignore_rest=True
                        )
                        
                        if valid_b:
                            # --- NEW STRICT CHECKS for Circular Swap ---
                            # A -> (Date 2, Dept 2)
                            # B -> (Date 3, Dept 3)
                            # C -> (Target Date, Target Dept)

                            # Check A's move
                            if not check_advanced_constraints(t_date_str, target_dept_swap, date_2, dept_2): continue
                            if is_creating_consecutive_violation(current_emp, date_2, schedule_records): continue
                            
                            # Check B's move
                            if not check_advanced_constraints(date_2, dept_2, date_3, dept_3): continue
                            if is_creating_consecutive_violation(person_b, date_3, schedule_records): continue

                            # Check C's move
                            if not check_advanced_constraints(date_3, dept_3, t_date_str, target_dept_swap): continue
                            if is_creating_consecutive_violation(c_name, t_date_str, schedule_records): continue
                            # -------------------------------------------

                            # Found a chain!
                            # A -> (Date 2, Dept 2) [Replacing B]
                            # B -> (Date 3, Dept 3) [Replacing C]
                            # C -> (Target Date, Target Dept) [Replacing A]
                            
                            candidates_circular.append({
                                'b_name': person_b, 'b_date': date_2, 'b_dept': dept_2,
                                'c_name': c_name, 'c_date': date_3, 'c_dept': dept_3
                            })
                            if len(candidates_circular) > 10: break # Limit results
                    if len(candidates_circular) > 10: break
                if len(candidates_circular) > 10: break
                
            st.session_state['swap_results']['circular'] = candidates_circular


        # --- Display Results from Session State ---
        if 'swap_results' in st.session_state and \
           st.session_state['swap_results']['date'] == t_date_str and \
           st.session_state['swap_results']['dept'] == target_dept_swap:
            
            res = st.session_state['swap_results']
            
            st.write("---")
            
            # 1. Direct - Available Replacements (main swap suggestions)
            st.markdown("##### ✅ מחליפים זמינים להחלפה")
            if res['direct']:
                st.success(f"נמצאו **{len(res['direct'])}** מחליפים זמינים עבור {target_dept_swap} ב-{t_date_str}:")
                
                # Selectbox to pick a replacement
                selected_replacement = st.selectbox(
                    "בחר מחליף/ה:", 
                    res['direct'], 
                    key="swap_select_direct"
                )
                
                if st.button("✅ בצע החלפה", key="do_selected_swap"):
                    # Remove old assignment
                    st.session_state.schedule = st.session_state.schedule[
                        ~((st.session_state.schedule['date'] == t_date_str) & (st.session_state.schedule['dept'] == target_dept_swap))
                    ]
                    # Add new assignment
                    new_row = {'date': t_date_str, 'dept': target_dept_swap, 'employee': selected_replacement, 'is_manual': True, 'empty_reason': ''}
                    st.session_state.schedule = pd.concat([st.session_state.schedule, pd.DataFrame([new_row])], ignore_index=True)
                    save_to_db("schedule", st.session_state.schedule)
                    
                    del st.session_state['swap_results']
                    st.success(f"בוצע! {selected_replacement} שובץ/ה במקום {current_emp}")
                    st.rerun()
            else:
                st.caption("לא נמצאו מחליפים זמינים.")

            # 2. Exchanges
            if current_emp != "---":
                st.markdown("##### 🔄 החלפות הדדיות (ראש בראש)")
                if res['exchange']:
                    for item in res['exchange']:
                        b = item['name']
                        b_dept = item['dept']
                        # Format date for display
                        d_disp = datetime.strptime(t_date_str, '%Y-%m-%d').strftime('%d/%m')
                        
                        c1, c2 = st.columns([3, 1])
                        c1.write(f"**{b}** ({b_dept} ב-**{d_disp}**) ↔️ **{current_emp}** ({target_dept_swap} ב-**{d_disp}**)")
                        if c2.button("החלף", key=f"do_swap_{b}"):
                            # Update DB - Swap Depts
                            mask_a = (st.session_state.schedule['date'] == t_date_str) & (st.session_state.schedule['dept'] == target_dept_swap)
                            mask_b = (st.session_state.schedule['date'] == t_date_str) & (st.session_state.schedule['dept'] == b_dept)
                            
                            st.session_state.schedule.loc[mask_a, 'employee'] = b
                            st.session_state.schedule.loc[mask_b, 'employee'] = current_emp
                            st.session_state.schedule.loc[mask_a | mask_b, 'is_manual'] = True # Mark as manual
                            
                            save_to_db("schedule", st.session_state.schedule)
                            
                            del st.session_state['swap_results']
                            st.success("ההחלפה בוצעה בהצלחה!")
                            st.rerun()
                else:
                    st.caption("לא נמצאו החלפות הדדיות מתאימות.")
            
            # 4. Mutual Cross-Date (New)
            st.markdown("##### 📅⚡ החלפות הדדיות בין תאריכים")
            st.caption(f"תרחיש: {current_emp} מחליף עם B בתאריך אחר.")
            
            candidates_mutual_cross = res.get('mutual_cross', [])
            if candidates_mutual_cross:
                for i, item in enumerate(candidates_mutual_cross[:5]):
                     b_name = item['b_name']
                     b_date = item['b_date']
                     b_dept = item['b_dept']
                     
                     # Displays
                     d_disp_current = datetime.strptime(t_date_str, '%Y-%m-%d').strftime('%d/%m')
                     d_disp_b = datetime.strptime(b_date, '%Y-%m-%d').strftime('%d/%m')
                     
                     c1, c2 = st.columns([3, 1])
                     c1.write(f"**{b_name}** ({b_dept} ב-**{d_disp_b}**) ↔️ **{current_emp}** ({target_dept_swap} ב-**{d_disp_current}**)")
                     
                     if c2.button("החלף", key=f"do_cross_mutual_{i}"):
                         # A goes to B's spot (Date 2)
                         # B goes to A's spot (Date 1)
                         
                         sched = st.session_state.schedule
                         
                         # Mask for A's spot (Date 1)
                         mask_a = (sched['date'] == t_date_str) & (sched['dept'] == target_dept_swap)
                         # Mask for B's spot (Date 2)
                         mask_b = (sched['date'] == b_date) & (sched['dept'] == b_dept)
                         
                         st.session_state.schedule.loc[mask_a, 'employee'] = b_name
                         st.session_state.schedule.loc[mask_a, 'is_manual'] = True
                         
                         st.session_state.schedule.loc[mask_b, 'employee'] = current_emp
                         st.session_state.schedule.loc[mask_b, 'is_manual'] = True
                         
                         save_to_db("schedule", st.session_state.schedule)
                         del st.session_state['swap_results']
                         st.success("החלפה הדדית בין תאריכים בוצעה!")
                         st.rerun()
            else:
                st.caption("לא נמצאו החלפות הדדיות בין תאריכים.")

            # 5. Circular Cross-Date (New)
            st.markdown("##### 📅🔄 מעגל החלפות (3 תאריכים)")
            st.caption(f"תרחיש: A (פה) ⬅️ B (תאריך 2) ⬅️ C (תאריך 3) ⬅️ A.")
            
            candidates_circular = res.get('circular', [])
            if candidates_circular:
                for i, item in enumerate(candidates_circular[:5]):
                    b_name = item['b_name']
                    b_date = item['b_date']
                    b_dept = item['b_dept']
                    
                    c_name = item['c_name']
                    c_date = item['c_date']
                    c_dept = item['c_dept']
                    
                    d_disp_1 = datetime.strptime(t_date_str, '%Y-%m-%d').strftime('%d/%m') # Target (A is here)
                    d_disp_2 = datetime.strptime(b_date, '%Y-%m-%d').strftime('%d/%m') # B is here
                    d_disp_3 = datetime.strptime(c_date, '%Y-%m-%d').strftime('%d/%m') # C is here
                    
                    c1, c2 = st.columns([3, 1])
                    c1.markdown(f"""
                    1. **{current_emp}** עובר אל {b_dept} (**{d_disp_2}**)
                    2. **{b_name}** עובר אל {c_dept} (**{d_disp_3}**)
                    3. **{c_name}** עובר אל {target_dept_swap} (**{d_disp_1}**)
                    """)
                    
                    if c2.button("בצע מעגל", key=f"do_circular_{i}"):
                        sched = st.session_state.schedule
                        
                        # A's Spot (Date 1)
                        mask_1 = (sched['date'] == t_date_str) & (sched['dept'] == target_dept_swap)
                        # B's Spot (Date 2)
                        mask_2 = (sched['date'] == b_date) & (sched['dept'] == b_dept)
                        # C's Spot (Date 3)
                        mask_3 = (sched['date'] == c_date) & (sched['dept'] == c_dept)
                        
                        # Apply Changes
                        # 1. C -> Spot 1
                        st.session_state.schedule.loc[mask_1, 'employee'] = c_name
                        st.session_state.schedule.loc[mask_1, 'is_manual'] = True
                        
                        # 2. A -> Spot 2
                        st.session_state.schedule.loc[mask_2, 'employee'] = current_emp
                        st.session_state.schedule.loc[mask_2, 'is_manual'] = True
                        
                        # 3. B -> Spot 3
                        st.session_state.schedule.loc[mask_3, 'employee'] = b_name
                        st.session_state.schedule.loc[mask_3, 'is_manual'] = True
                        
                        save_to_db("schedule", st.session_state.schedule)
                        del st.session_state['swap_results']
                        st.success("מעגל החלפות בוצע בהצלחה!")
                        st.rerun()
            else:
                 st.caption("לא נמצאו מעגלי החלפות.")


            # Debug Info Removed


# --- 5. ממשק המנהל והעובד ---
# Header Area
st.markdown('<div class="main-header">', unsafe_allow_html=True)

# FORCE INDIGO CHECKBOX CSS (Hardcoded Fix for Streamlit Cloud)
st.markdown("""
<style>
    /* Force Indigo Checkbox Color - Broad Selector */
    div[data-testid="stCheckbox"] *[aria-checked="true"] {
        background-color: #6366f1 !important;
        border-color: #6366f1 !important;
    }
    
    /* Force SVG Color */
    div[data-testid="stCheckbox"] *[aria-checked="true"] svg {
        fill: white !important;
        stroke: white !important;
    }
    
    /* Fallback for specific structure if broad fails */
    span[data-baseweb="checkbox"] div[aria-checked="true"] {
         background-color: #6366f1 !important;
    }

    /* ── Day-absence calendar (Phase 3) ── */
    div[class*="st-key-dayabs_free_"] > div[data-testid="stButton"] > button {
        background: white !important; color: #334155 !important;
        border: 1px solid #e2e8f0 !important;
        font-size: 0.78rem !important; min-height: 34px !important;
    }
    div[class*="st-key-dayabs_free_"] > div[data-testid="stButton"] > button:hover {
        background: #f0fdf4 !important; border-color: #86efac !important;
        color: #166534 !important; transform: none !important;
    }
    div[class*="st-key-dayabs_start_"] > div[data-testid="stButton"] > button {
        background: #16a34a !important; color: white !important;
        border: 2px solid #15803d !important;
        font-size: 0.78rem !important; min-height: 34px !important;
    }
    div[class*="st-key-dayabs_range_"] > div[data-testid="stButton"] > button {
        background: #bbf7d0 !important; color: #166534 !important;
        border: 1px solid #86efac !important;
        font-size: 0.78rem !important; min-height: 34px !important;
    }
    .dayabs-vac  { background:#2563eb; color:white; border-radius:8px; padding:5px 2px;
                   text-align:center; font-size:0.78rem; min-height:34px;
                   display:flex; align-items:center; justify-content:center; }
    .dayabs-202  { background:#ca8a04; color:white; border-radius:8px; padding:5px 2px;
                   text-align:center; font-size:0.78rem; min-height:34px;
                   display:flex; align-items:center; justify-content:center; }
    .dayabs-pend { background:#94a3b8; color:white; border-radius:8px; padding:5px 2px;
                   text-align:center; font-size:0.78rem; min-height:34px;
                   display:flex; align-items:center; justify-content:center; }
    .dayabs-night{ background:#1e3a5f; color:white; border-radius:8px; padding:5px 2px;
                   text-align:center; font-size:0.78rem; min-height:34px;
                   display:flex; align-items:center; justify-content:center; }
    .dayabs-post { background:#f97316; color:white; border-radius:8px; padding:5px 2px;
                   text-align:center; font-size:0.78rem; min-height:34px;
                   display:flex; align-items:center; justify-content:center; }
    .dayabs-empty{ padding:5px 2px; min-height:34px; }
    .dayabs-hdr  { text-align:center; font-weight:700; color:#475569;
                   font-size:0.82rem; padding-bottom:4px; }

    /* ── WSD dept-grid cell coloring (Phase 6) ── */
    div[class*="st-key-wsdcell_"] > div[data-testid="stButton"] > button {
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        font-size:0.7rem !important; min-height:30px !important; padding:2px 1px !important;
    }
    div[class*="st-key-wsdcell_w_"] > div[data-testid="stButton"] > button {
        background:#16a34a !important; color:white !important;
    }
    div[class*="st-key-wsdcell_h_"] > div[data-testid="stButton"] > button {
        background:#2563eb !important; color:white !important;
    }
    div[class*="st-key-wsdcell_2_"] > div[data-testid="stButton"] > button {
        background:#ca8a04 !important; color:white !important;
    }
    div[class*="st-key-wsdcell_p_"] > div[data-testid="stButton"] > button {
        background:#f97316 !important; color:white !important;
    }
    div[class*="st-key-wsdcell_a_"] > div[data-testid="stButton"] > button {
        background:#94a3b8 !important; color:white !important;
    }
    div[class*="st-key-wsdcell_t_"] > div[data-testid="stButton"] > button {
        background:#7c3aed !important; color:white !important;
    }
    /* Note icon buttons — minimal appearance */
    div[class*="st-key-notepop_"] button {
        background:transparent !important; color:#94a3b8 !important;
        border:1px solid #e2e8f0 !important;
        font-size:0.65rem !important; min-height:30px !important; padding:1px !important;
        border-radius:4px !important;
    }
    div[class*="st-key-notepop_"] button:hover {
        color:#4f46e5 !important; border-color:#4f46e5 !important;
    }
</style>
""", unsafe_allow_html=True)
st.title("מערכת סידור עבודה המערך הגריאטרי")

# Logout button centered under title for mobile robustness
if st.button("התנתק", key="logout_top", use_container_width=False):
    _login_time = st.session_state.get('analytics_login_time', datetime.now())
    _session_dur = int((datetime.now() - _login_time).total_seconds())
    _log_async('logout', str(_session_dur), 'explicit')
    st.session_state.logged_in = False
    st.rerun()
st.markdown('</div>', unsafe_allow_html=True)

role = st.session_state.user_role
user_name = st.session_state.user_name

# שליפת החודש הפעיל — cached with 30 s TTL so admin changes propagate quickly
# but don't trigger a new API call on every widget interaction.
try:
    if (time.time() - st.session_state.get('_settings_fetched_at', 0) > 30):
        st.session_state.settings = get_db_data("settings")
        st.session_state['_settings_fetched_at'] = time.time()
except:
    st.session_state.settings = pd.DataFrame([{'key': 'active_month', 'value': str(date.today().month + 1)}])

if 'key' not in st.session_state.settings.columns:
    st.session_state.settings = pd.DataFrame([{'key': 'active_month', 'value': str(date.today().month + 1)}])
    save_to_db("settings", st.session_state.settings)

try:
    active_month_setting = st.session_state.settings[st.session_state.settings['key'] == 'active_month']['value'].iloc[0]
    active_month_int = int(active_month_setting)
except:
    active_month_int = date.today().month

# ── Daily-schedule settings (Phase 2+) ──
def _parse_manage_depts(raw):
    """
    Split a comma-separated manage_depts string into a clean list of dept names.
    Normalises Hebrew Geresh ׳ (U+05F3) → ASCII apostrophe ' so manually-typed
    values like 'שיקום גריאטרי א׳' match DAILY_DEPTS_ALL entries exactly.
    """
    normalised = str(raw).strip().replace('׳', "'").replace('״', '״')
    return [d.strip() for d in normalised.split(',') if d.strip()]

_ROLE_ORDER = {'מנהל מחלקה': 0, 'רופא בכיר': 1, 'מתמחה': 2}

def _sort_employees_by_role(emp_list: list[str]) -> list[str]:
    """
    Sort a list of employee names by role:
      מנהל/ת מחלקה → רופא/ה בכיר/ה → מתמחה → everything else.
    Looks up each name in st.session_state.staff; unknown names go last.
    Preserves original order within the same role (stable sort).
    """
    try:
        sf = st.session_state.staff
        if sf.empty or 'name' not in sf.columns:
            return emp_list
        _name_to_role: dict[str, str] = {}
        for _, r in sf.iterrows():
            _name_to_role[str(r.get('name', '')).strip()] = str(r.get('type', '')).strip()
        return sorted(
            emp_list,
            key=lambda n: _ROLE_ORDER.get(_name_to_role.get(str(n).strip(), ''), 99)
        )
    except Exception:
        return emp_list


def _get_setting(key, default):
    try:
        rows = st.session_state.settings[st.session_state.settings['key'] == key]
        if not rows.empty:
            return rows['value'].iloc[0]
    except Exception:
        pass
    return default

def _set_setting(key, value):
    """Upsert a setting key+value, persist to sheet."""
    s = st.session_state.settings
    if (s['key'] == key).any():
        s.loc[s['key'] == key, 'value'] = str(value)
    else:
        s = pd.concat([s, pd.DataFrame([{'key': key, 'value': str(value)}])], ignore_index=True)
    st.session_state.settings = s
    save_to_db("settings", s)

try:
    daily_active_month_int = int(_get_setting('daily_active_month', active_month_int))
except Exception:
    daily_active_month_int = active_month_int

daily_requests_open = str(_get_setting('daily_requests_open', 'True')).strip().lower() == 'true'

# Render Navigation Bar
selected_nav = ui_components.render_navbar(role)

# --- אנליטיקת טאב: רישום כניסה ויציאה מטאבים ---
_prev_tab = st.session_state.get('analytics_last_tab', None)
if selected_nav != _prev_tab:
    _now_tab = datetime.now()
    if _prev_tab is not None:
        _secs_on_prev = int((_now_tab - st.session_state.get('analytics_tab_enter', _now_tab)).total_seconds())
        _log_async('tab_view', _prev_tab, str(_secs_on_prev))
    _log_async('tab_view', selected_nav, 'enter')
    st.session_state.analytics_last_tab = selected_nav
    st.session_state.analytics_tab_enter = _now_tab

# Month Selection Logic - MOVED TO SCHEDULE TAB ONLY (as requested)
# sel_month defaults to active month, but admins can override it LOCALLY in the schedule tab
sel_month = active_month_int 

# Admin Global control (Hidden here, moved logic down)
# We keep the "active_month_setter" logic but it needs to be where the selector is.
# So we skip the global expander here.



if selected_nav == 'הגדרות':
    st.subheader("⚙️ הגדרות משתמש")
    
    # --- Change Password Section ---
    with st.expander("🔑 שינוי סיסמה", expanded=True):
        with st.form("change_password_form"):
            st.caption("כאן ניתן לשנות את סיסמת ההתחברות למערכת.")
            
            curr_pass = st.text_input("סיסמה נוכחית", type="password")
            new_pass = st.text_input("סיסמה חדשה", type="password")
            conf_pass = st.text_input("אימות סיסמה חדשה", type="password")
            
            if st.form_submit_button("עדכן סיסמה"):
                # 1. Verify Current Password
                # Get user record
                user_record = st.session_state.staff[st.session_state.staff['name'] == user_name]
                if user_record.empty:
                    st.error("שגיאה: משתמש לא נמצא.")
                else:
                    stored_hash = user_record.iloc[0]['password']
                    input_hash = hashlib.sha256(curr_pass.encode()).hexdigest()
                    
                    if input_hash != stored_hash:
                        st.error("סיסמה נוכחית שגויה.")
                    elif not new_pass:
                        st.error("לא ניתן להגדיר סיסמה ריקה.")
                    elif new_pass != conf_pass:
                        st.error("הסיסמאות החדשות אינן תואמות.")
                    else:
                        # 2. Update Password
                        new_hash = hashlib.sha256(new_pass.encode()).hexdigest()
                        st.session_state.staff.loc[st.session_state.staff['name'] == user_name, 'password'] = new_hash
                        
                        # 3. Save to DB
                        save_to_db("staff", st.session_state.staff)
                        
                        # 4. Clear Cache to force reload on next login
                        st.cache_data.clear()
                        
                        st.success("הסיסמה עודכנה בהצלחה!")

    # --- Swap Search Section ---
    if role != "מנהל/ת":
        with st.expander("🔄 חיפוש החלפות", expanded=False):


            sched_df = st.session_state.schedule
            today_str = date.today().strftime('%Y-%m-%d')
            user_shifts = sched_df[
                (sched_df['employee'].astype(str).str.strip() == str(user_name).strip()) &
                (sched_df['date'].astype(str) >= today_str)
            ].sort_values('date').reset_index(drop=True)

            if user_shifts.empty:
                st.info("אין לך משמרות עתידיות משובצות.")
            else:
                DAY_NAMES_HE = {0: 'שני', 1: 'שלישי', 2: 'רביעי', 3: 'חמישי', 4: 'שישי', 5: 'שבת', 6: 'ראשון'}

                shift_options = []
                for _, s in user_shifts.iterrows():
                    d_obj = datetime.strptime(str(s['date']), '%Y-%m-%d').date()
                    label = f"{d_obj.strftime('%d/%m/%Y')} ({DAY_NAMES_HE[d_obj.weekday()]}) — {s['dept']}"
                    shift_options.append((label, str(s['date']), s['dept']))

                labels = ["— בחר/י משמרת —"] + [opt[0] for opt in shift_options]
                sel_label = st.selectbox("המשמרות הקרובות שלי:", labels, key=f"swap_search_select_upcoming")

                if sel_label != "— בחר/י משמרת —":
                    chosen = next(o for o in shift_options if o[0] == sel_label)
                    swap_date, swap_dept = chosen[1], chosen[2]
                    swap_month_int = int(swap_date.split('-')[1])
                    _log_async('swap_search', swap_date, swap_dept)

                    with st.spinner("מחפש החלפות..."):
                        results = find_swap_candidates(
                            st.session_state.schedule,
                            st.session_state.requests,
                            st.session_state.staff,
                            user_name, swap_date, swap_dept, swap_month_int
                        )

                    full = results['full']
                    partial = results['partial']
                    chain = results.get('chain', [])

                    if not full and not partial and not chain:
                        st.warning("לא נמצאו אפשרויות החלפה תקפות למשמרת זו.")
                    else:
                        if full:
                            st.markdown("##### ✅ החלפה מלאה")
                            st.caption("יכולים לכסות את המשמרת שלך, ויש להם משמרת שתוכל/י לקחת בתמורה")
                            for cand in full:
                                ts_d_obj = datetime.strptime(cand['their_shift']['date'], '%Y-%m-%d').date()
                                their_label = f"{ts_d_obj.strftime('%d/%m')} ({DAY_NAMES_HE[ts_d_obj.weekday()]}) — {cand['their_shift']['dept']}"
                                wish_pill = " ⭐" if cand['wished'] else ""

                                c1, c2 = st.columns([3, 1])
                                with c1:
                                    st.markdown(f"**{cand['name']}**{wish_pill}  \n_{cand['type']} · {cand['dept']}_  \n⇄ מציע/ה: **{their_label}**")
                                with c2:
                                    btn_key = f"swap_send_full_{cand['name']}_{swap_date}"
                                    if st.button("🔄 בקש החלפה", key=btn_key, use_container_width=True):
                                        new_req = pd.DataFrame([{
                                            'requester': user_name,
                                            'requester_date': swap_date,
                                            'requester_dept': swap_dept,
                                            'candidate': cand['name'],
                                            'candidate_date': cand['their_shift']['date'],
                                            'candidate_dept': cand['their_shift']['dept'],
                                            'swap_type': 'full',
                                            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                                            'status': 'pending',
                                        }])
                                        existing = st.session_state.swap_requests
                                        combined = new_req if existing.empty else pd.concat([existing, new_req], ignore_index=True)
                                        save_to_db("swap_requests", combined)
                                        _log_async('swap_request_sent', swap_date, 'full')
                                        st.session_state.swap_requests = combined
                                        st.success("הבקשה נשלחה למנהל/ת לאישור.")
                                st.divider()

                        if partial:
                            st.markdown("##### ⚠️ כיסוי חד-צדדי")
                            st.caption("יכולים לכסות את המשמרת שלך, אך לא נמצאה משמרת הדדית מתאימה")
                            for cand in partial:
                                wish_pill = " ⭐" if cand['wished'] else ""
                                c1, c2 = st.columns([3, 1])
                                with c1:
                                    st.markdown(f"**{cand['name']}**{wish_pill}  \n_{cand['type']} · {cand['dept']}_")
                                with c2:
                                    btn_key = f"swap_send_partial_{cand['name']}_{swap_date}"
                                    if st.button("🔄 בקש החלפה", key=btn_key, use_container_width=True):
                                        new_req = pd.DataFrame([{
                                            'requester': user_name,
                                            'requester_date': swap_date,
                                            'requester_dept': swap_dept,
                                            'candidate': cand['name'],
                                            'candidate_date': '',
                                            'candidate_dept': '',
                                            'swap_type': 'partial',
                                            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                                            'status': 'pending',
                                        }])
                                        existing = st.session_state.swap_requests
                                        combined = new_req if existing.empty else pd.concat([existing, new_req], ignore_index=True)
                                        save_to_db("swap_requests", combined)
                                        _log_async('swap_request_sent', swap_date, 'partial')
                                        st.session_state.swap_requests = combined
                                        st.success("הבקשה נשלחה למנהל/ת לאישור.")
                                st.divider()

                        if chain:
                            st.markdown("##### 🔗 החלפה משולשת")
                            st.caption("מתמחה עובר/ת מ-שיקום ל-פנימית, תורן חוץ מכסה שיקום")
                            for ch in chain:
                                fac_pill = " ⭐" if ch['facilitator_wished'] else ""
                                ext_pill = " ⭐" if ch['external_wished'] else ""
                                c1, c2 = st.columns([3, 1])
                                with c1:
                                    st.markdown(
                                        f"**{ch['facilitator_name']}**{fac_pill} ⇄ פנימית  +  "
                                        f"**{ch['external_name']}**{ext_pill} → שיקום"
                                    )
                                with c2:
                                    btn_key = f"swap_send_chain_{ch['facilitator_name']}_{ch['external_name']}_{swap_date}"
                                    if st.button("🔄 בקש החלפה", key=btn_key, use_container_width=True):
                                        new_req = pd.DataFrame([{
                                            'requester': user_name,
                                            'requester_date': swap_date,
                                            'requester_dept': swap_dept,
                                            'candidate': ch['facilitator_name'],
                                            'candidate_date': swap_date,
                                            'candidate_dept': 'פנימית גריאטרית',
                                            'swap_type': 'chain',
                                            'chain_ext': ch['external_name'],
                                            'chain_ext_dept': 'שיקום',
                                            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                                            'status': 'pending',
                                        }])
                                        existing = st.session_state.swap_requests
                                        combined = new_req if existing.empty else pd.concat([existing, new_req], ignore_index=True)
                                        save_to_db("swap_requests", combined)
                                        _log_async('swap_request_sent', swap_date, 'chain')
                                        st.session_state.swap_requests = combined
                                        st.success("הבקשה נשלחה למנהל/ת לאישור.")
                                st.divider()

    # --- Manage Special Days Section (Admin Only) ---
    if role == "מנהל/ת":
        with st.expander("📅 ניהול ימים מיוחדים וחגים", expanded=False):
            st.caption("הוסף תאריכים מיוחדים כדי שמתמחים יראו אותם לפני הגשת אילוצים.")
            
            c_sd1, c_sd2, c_sd_type, c_sd3 = st.columns([1, 1.5, 1, 1])
            sd_date = c_sd1.date_input("תאריך ליום מיוחד:", format="DD/MM/YYYY")
            sd_desc = c_sd2.text_input("תיאור (למשל: ערב פסח):")
            sd_type = c_sd_type.selectbox("סוג יום:", ["לידיעה בלבד", "כמו שישי (ערב חג)", "כמו שבת (חג)"])
            
            if c_sd3.button("➕ הוסף יום", use_container_width=True):
                if sd_desc:
                    new_sd = pd.DataFrame([{'date': str(sd_date), 'description': sd_desc, 'day_type': sd_type}])
                    st.session_state.special_days = pd.concat([st.session_state.special_days, new_sd], ignore_index=True)
                    save_to_db("special_days", st.session_state.special_days)
                    st.success("היום המיוחד התווסף בהצלחה!")
                    st.rerun()
                else:
                    st.error("חובה להזין תיאור.")
            
            if not st.session_state.special_days.empty:
                st.write("ימים מיוחדים קיימים:")
                for idx, row in st.session_state.special_days.iterrows():
                    colA, colB, colC, colD = st.columns([1, 1.5, 1, 0.5])
                    colA.write(f"**{row['date']}**")
                    colB.write(row['description'])
                    colC.write(row.get('day_type', 'רגיל'))
                    if colD.button("🗑️", key=f"del_sd_{idx}"):
                        st.session_state.special_days = st.session_state.special_days.drop(idx).reset_index(drop=True)
                        save_to_db("special_days", st.session_state.special_days)
                        st.rerun()

elif role == "מנהל/ת":
    if selected_nav == 'סידור תורנויות':
        
        # --- Month Selector for Schedule Tab (Admin Only) ---
        with st.expander("הגדרות תצוגה", expanded=False):
            c_m1, c_m2 = st.columns(2)
            # Use a specialized key to avoid conflicts if previously used
            sel_month = c_m1.selectbox("חודש לצפייה/עריכה", range(1, 13), index=active_month_int - 1, key="sched_month_select")
            
            # Admin Global Control
            new_active_month = c_m2.selectbox(
                "חודש פתוח להגשת אילוצים:", 
                range(1, 13), 
                index=active_month_int - 1,
                key="admin_active_month_setter_sched"
            )
            if new_active_month != active_month_int:
                st.session_state.settings['value'] = st.session_state.settings['value'].astype(object)
                st.session_state.settings.loc[st.session_state.settings['key'] == 'active_month', 'value'] = str(new_active_month)
                save_to_db("settings", st.session_state.settings)
                st.success(f"החודש הפעיל עודכן ל-{new_active_month}")
                st.rerun()
        # ----------------------------------------------------

        # --- ייצוא ל-Schedule_Export (הועבר מטאב "דוחות וניהול") ---
        col_exp, _ = st.columns([1, 3])
        with col_exp:
            if st.button("📤 עדכן את הגיליון Schedule_Export",
                         key="export_schedule_top", use_container_width=True):
                ok, err = _export_schedule_wide(sel_month)
                if ok:
                    st.success("✅ הנתונים יוצאו לגיליון 'Schedule_Export'!")
                else:
                    st.error(f"שגיאה בייצוא: {err}")

        # --- הוספת כלי שיבוץ ידני ---
        with st.expander("כלי שיבוץ ידני (דריסה)", expanded=True):
            c_date, c_dept, c_emp, c_btn_add, c_btn_del = st.columns([1, 1, 1, 0.7, 0.7])
            
            # עדכון ערך ברירת מחדל לתאריך רק אם החודש השתנה בסרגל הצד
            # זה מאפשר לשמור על בחירת המשתמש בתוך אותו חודש
            default_date = date(2026, sel_month, 1)
            if 'manual_date' in st.session_state:
                if st.session_state.manual_date.month != sel_month:
                     st.session_state.manual_date = default_date

            d_man = c_date.date_input("תאריך:", key="manual_date", format="DD/MM/YYYY")
            dept_man = c_dept.selectbox("מחלקה:", ["שיקום", "פנימית גריאטרית", "שישי בוקר - שיקום (1)", "שישי בוקר - שיקום (2)", "שישי בוקר - פנימית (1)", "שישי בוקר - פנימית (2)"], key="manual_dept")
            
            # סינון רשימת העובדים - הצגת מי שמשובץ כרגע למעלה או סימון מיוחד? לא קריטי כרגע.
            emp_man = c_emp.selectbox("עובד:", st.session_state.staff['name'].tolist(), key="manual_emp")
            
            # כפתור שיבוץ
            if c_btn_add.button("✅ שיבוץ"):
                d_man_str = str(d_man)
                # Check for constraints
                is_blocked = False
                if not st.session_state.requests[(st.session_state.requests['employee'] == emp_man) & (st.session_state.requests['date'] == d_man_str) & (st.session_state.requests['status'] == "אילוץ")].empty:
                    is_blocked = True
                
                if is_blocked:
                    st.error(f"לא ניתן לשבץ את {emp_man} ב-{d_man_str}. יש לו אילוץ על יום זה.")
                else:
                    # הסרת שיבוץ קיים לתאריך ולמחלקה הזו (אם יש)
                    st.session_state.schedule = st.session_state.schedule[
                        ~((st.session_state.schedule['date'] == d_man_str) & 
                          (st.session_state.schedule['dept'] == dept_man))
                    ]
                    # הוספת השיבוץ הידני עם סימון ידני=True
                    new_entry = pd.DataFrame([{
                        'date': d_man_str, 
                        'dept': dept_man, 
                        'employee': emp_man, 
                        'is_manual': True, 
                        'empty_reason': ''
                    }])
                    st.session_state.schedule = pd.concat([st.session_state.schedule, new_entry], ignore_index=True)
                    save_to_db("schedule", st.session_state.schedule)
                    st.success(f"שובץ: {emp_man}")
                    st.rerun()
 
            # כפתור ביטול שיבוץ
            if c_btn_del.button("❌ בטל"):
                # מחיקת השיבוץ הספציפי הזה
                st.session_state.schedule = st.session_state.schedule[
                    ~((st.session_state.schedule['date'] == str(d_man)) & 
                      (st.session_state.schedule['dept'] == dept_man))
                ]
                save_to_db("schedule", st.session_state.schedule)
                st.success("השיבוץ בוטל")
                st.rerun()
        # ---------------------------
        c1, c2, c3 = st.columns(3)
        if c1.button("🪄 שיבוץ אוטומטי מלא"): run_smart_scheduling(2026, sel_month, only_weekends=False); st.rerun()
        if c2.button("☕ שיבוץ סופ\"שים בלבד"): run_smart_scheduling(2026, sel_month, only_weekends=True); st.rerun()
        with c3:
            with st.expander("🗑️ ניקוי"):
                if st.button("🧹 נקה אוטומטי (חודש זה)", help="מוחק שיבוצים אוטומטיים בחודש הנוכחי בלבד"):
                    current_prefix = f"2026-{sel_month:02d}"
                    
                    # Ensure is_manual column exists
                    if 'is_manual' not in st.session_state.schedule.columns:
                        st.session_state.schedule['is_manual'] = False
                    
                    # Logic: Delete if (Date matches prefix) AND (is_manual is NOT True)
                    mask_current_month = st.session_state.schedule['date'].astype(str).str.startswith(current_prefix)
                    
                    # Handle both boolean True and string "TRUE" from Google Sheets serialization
                    is_manual_s = st.session_state.schedule['is_manual']
                    mask_manual = (is_manual_s == True) | (is_manual_s.astype(str).str.upper() == 'TRUE')
                    mask_auto = ~mask_manual
                    mask_to_delete = mask_current_month & mask_auto
                    
                    st.session_state.schedule = st.session_state.schedule[~mask_to_delete]
                    
                    save_to_db("schedule", st.session_state.schedule)
                    st.success(f"שיבוצים אוטומטיים לחודש {sel_month}/2026 נמחקו (חודשים אחרים וידניים נשמרו).")
                    st.rerun()
                
                if st.button("💥 נקה הכל (חודש זה)", help="מוחק את כל הלוח לחודש זה"): 
                    current_prefix = f"2026-{sel_month:02d}"
                    
                    # Logic: Delete if Date matches prefix
                    mask_to_delete = st.session_state.schedule['date'].astype(str).str.startswith(current_prefix)
                    
                    st.session_state.schedule = st.session_state.schedule[~mask_to_delete]
                    save_to_db("schedule", st.session_state.schedule)
                    st.success(f"כל השיבוצים לחודש {sel_month}/2026 נמחקו.")
                    st.rerun()
        
        # --- התראה על משמרות שלא שובצו ---
        if not st.session_state.schedule.empty:
            failures = st.session_state.schedule[st.session_state.schedule['employee'] == '---']
            if not failures.empty:
                st.error(f"⚠️ שימו לב: נמצאו {len(failures)} משמרות שלא ניתן היה לשבץ!")
                with st.expander("🔻 לחץ כאן לפירוט השגיאות והסיבות", expanded=False):
                    for _, row in failures.iterrows():
                        # Format date for display
                        d_obj = datetime.strptime(row['date'], '%Y-%m-%d')
                        fmt_date = d_obj.strftime('%d/%m/%Y')
                        st.markdown(f"❌ **{fmt_date}** ({row['dept']}): {row['empty_reason']}")
                        
                        # כפתורי ביצוע החלפה (Swap Actions)
                        actions_found = False
                        if 'swap_suggestions' in st.session_state:
                            core_key = f"{row['date']}_{row['dept']}"
                            if core_key in st.session_state.swap_suggestions:
                                actions_found = True
                                for i, sugg in enumerate(st.session_state.swap_suggestions[core_key]):
                                    btn_label = f"✨ בצע: {sugg['desc']}"
                                    if st.button(btn_label, key=f"swap_btn_{core_key}_{i}"):
                                        # --- בדיקת תקינות נוספת לפני ביצוע (פותר באג של הצעות ישנות/לא תקינות) ---
                                        # וידוא שתורן חוץ לא נכנס לפנימית גריאטרית
                                        current_schedule = st.session_state.schedule
                                        current_staff = st.session_state.staff
                                        
                                        # פונקציה לבדיקת חוקיות עובד-מחלקה
                                        def validate_emp_dept(emp_name, dept_name):
                                            emp_row = current_staff[current_staff['name'] == emp_name]
                                            if not emp_row.empty:
                                                e_type = emp_row['type'].iloc[0]
                                                if e_type == 'תורן חוץ' and 'פנימית' in dept_name:
                                                    return False, f"שגיאה: לא ניתן לשבץ את {emp_name} (תורן חוץ) לפנימית גריאטרית!"
                                            return True, ""

                                        # בדיקה לפי סוג ההחלפה
                                        validation_passed = True
                                        fail_reason = ""
                                        
                                        if sugg['type'] == 'direct_swap':
                                            # נכנס ל-row['dept'] -> conflicted_emp (A)
                                            # נכנס ל-other_dept -> replacement_emp (B)
                                            ok1, msg1 = validate_emp_dept(sugg['conflicted_emp'], row['dept'])
                                            if not ok1: validation_passed, fail_reason = False, msg1
                                            ok2, msg2 = validate_emp_dept(sugg['replacement_emp'], sugg['source_dept'])
                                            if not ok2: validation_passed, fail_reason = False, msg2
                                            
                                        elif sugg['type'] == 'move_shift':
                                            # נכנס ל-row['dept'] -> conflicted_emp (A)
                                            # נכנס ל-conf_dept -> replacement_emp (B)
                                            ok1, msg1 = validate_emp_dept(sugg['conflicted_emp'], row['dept'])
                                            if not ok1: validation_passed, fail_reason = False, msg1
                                            ok2, msg2 = validate_emp_dept(sugg['replacement_emp'], sugg['conflict_dept'])
                                            if not ok2: validation_passed, fail_reason = False, msg2

                                        if not validation_passed:
                                            st.error(f"❌ לא ניתן לבצע את ההחלפה: {fail_reason}")
                                            st.info("ייתכן שהנתונים השתנו מאז ההרצה האחרונה. מומלץ להריץ שיבוץ אוטומטי מחדש.")
                                        else:
                                            # ביצוע ההחלפה בפועל!
                                            sched = st.session_state.schedule
                                            
                                            if sugg['type'] == 'direct_swap':
                                                mask_other = (sched['date'] == sugg['target_date']) & (sched['dept'] == sugg['source_dept'])
                                                st.session_state.schedule.loc[mask_other, 'employee'] = sugg['replacement_emp']
                                                
                                                mask_here = (sched['date'] == sugg['target_date']) & (sched['dept'] == row['dept'])
                                                st.session_state.schedule.loc[mask_here, 'employee'] = sugg['conflicted_emp']
                                                st.session_state.schedule.loc[mask_here, 'empty_reason'] = '' 
                                                
                                            elif sugg['type'] == 'move_shift':
                                                mask_conflict = (sched['date'] == sugg['conflict_date']) & (sched['dept'] == sugg['conflict_dept'])
                                                st.session_state.schedule.loc[mask_conflict, 'employee'] = sugg['replacement_emp']
                                                
                                                mask_here = (sched['date'] == row['date']) & (sched['dept'] == row['dept'])
                                                st.session_state.schedule.loc[mask_here, 'employee'] = sugg['conflicted_emp']
                                                st.session_state.schedule.loc[mask_here, 'empty_reason'] = ''
                                                
                                            elif sugg['type'] == 'triple_swap':
                                                mask_b_origin = (sched['date'] == sugg['target_date']) & (sched['dept'] == sugg['dept_b_origin'])
                                                st.session_state.schedule.loc[mask_b_origin, 'employee'] = sugg['emp_c']
                                                
                                                mask_a_origin = (sched['date'] == sugg['target_date']) & (sched['dept'] == sugg['dept_a_origin'])
                                                st.session_state.schedule.loc[mask_a_origin, 'employee'] = sugg['emp_b']
                                                
                                                mask_here = (sched['date'] == sugg['target_date']) & (sched['dept'] == row['dept'])
                                                st.session_state.schedule.loc[mask_here, 'employee'] = sugg['emp_a']
                                                st.session_state.schedule.loc[mask_here, 'empty_reason'] = ''
                                                
                                            save_to_db("schedule", st.session_state.schedule)
                                            st.success("ההחלפה בוצע בהצלחה! מרענן...")
                                            st.rerun()
                        
                        if not actions_found:
                             st.caption("כדי לראות כפתורי החלפה, יש להריץ 'שיבוץ אוטומטי' מחדש.")
        # ---------------------------------

        draw_calendar_view(2026, sel_month, "מנהל/ת")

        # --- Swap Requests Panel ---
        if st.session_state.pop('show_swap_approved', False):
            st.success("✅ ההחלפה אושרה ובוצעה בלוח השיבוץ!")
        if st.session_state.pop('show_swap_rejected', False):
            st.info("הבקשה נדחתה.")

        _swap_reqs = st.session_state.swap_requests
        if not _swap_reqs.empty and 'status' in _swap_reqs.columns:
            _pending = _swap_reqs[_swap_reqs['status'].astype(str).str.strip() == 'pending']
            if not _pending.empty:
                st.divider()
                st.markdown(f"### 🔄 בקשות החלפה ממתינות לאישור ({len(_pending)})")
                for _idx, _req in _pending.iterrows():
                    _requester  = str(_req.get('requester', ''))
                    _r_date     = str(_req.get('requester_date', ''))
                    _r_dept     = str(_req.get('requester_dept', ''))
                    _candidate  = str(_req.get('candidate', ''))
                    _c_date     = str(_req.get('candidate_date', ''))
                    _c_dept     = str(_req.get('candidate_dept', ''))
                    _stype      = str(_req.get('swap_type', 'partial'))
                    _created    = str(_req.get('created_at', ''))

                    _chain_ext      = str(_req.get('chain_ext', ''))
                    _chain_ext_dept = str(_req.get('chain_ext_dept', ''))

                    with st.container(border=True):
                        _ca, _cb = st.columns([4, 2])
                        with _ca:
                            if _stype == 'full':
                                st.markdown(f"**✅ החלפה מלאה** | נשלח: {_created}")
                                st.write(f"**{_requester}** מוותר/ת על: **{_r_date}** ({_r_dept})")
                                st.write(f"← **{_candidate}** ייקח/תיקח אותה ויעביר/ת: **{_c_date}** ({_c_dept})")
                            elif _stype == 'chain':
                                st.markdown(f"**🔗 החלפה משולשת** | נשלח: {_created}")
                                st.write(f"**{_requester}** מסיר/ה: **{_r_date}** ({_r_dept})")
                                st.write(f"← **{_candidate}** עובר/ת מ-שיקום ל-פנימית")
                                st.write(f"← **{_chain_ext}** מכסה שיקום")
                            else:
                                st.markdown(f"**⚠️ כיסוי חד-צדדי** | נשלח: {_created}")
                                st.write(f"**{_requester}** מבקש/ת כיסוי: **{_r_date}** ({_r_dept})")
                                st.write(f"← **{_candidate}** מוצע/ת כמחליף/ה (ללא משמרת הדדית)")

                        with _cb:
                            _col_a, _col_r = st.columns(2)
                            if _col_a.button("✅ אשר", key=f"approve_swap_{_idx}", use_container_width=True):
                                _sched = st.session_state.schedule
                                # Mutation 1: requester's shift → candidate (or remove requester from פנימית for chain)
                                _mask_req = (_sched['date'].astype(str) == _r_date) & (_sched['dept'] == _r_dept)
                                if _stype == 'chain':
                                    # Remove requester from פנימית
                                    st.session_state.schedule.loc[_mask_req, 'employee'] = '---'
                                    st.session_state.schedule.loc[_mask_req, 'is_manual'] = True
                                    # Mutation 2: move facilitator (מתמחה) from שיקום → פנימית
                                    _mask_fac = (_sched['date'].astype(str) == _r_date) & (_sched['dept'] == 'שיקום') & \
                                                (_sched['employee'].astype(str).str.strip() == _candidate)
                                    st.session_state.schedule.loc[_mask_fac, 'employee'] = '---'
                                    st.session_state.schedule.loc[_mask_fac, 'is_manual'] = True
                                    st.session_state.schedule.loc[_mask_req, 'employee'] = _candidate
                                    # Mutation 3: assign תורן חוץ to שיקום (add new row if needed)
                                    _mask_sha = (_sched['date'].astype(str) == _r_date) & (_sched['dept'] == 'שיקום') & \
                                                (_sched['employee'].astype(str).str.strip().isin(['---', '']))
                                    if _mask_sha.any():
                                        st.session_state.schedule.loc[_mask_sha, 'employee'] = _chain_ext
                                        st.session_state.schedule.loc[_mask_sha, 'is_manual'] = True
                                    else:
                                        _new_row = pd.DataFrame([{
                                            'date': _r_date, 'dept': 'שיקום',
                                            'employee': _chain_ext, 'is_manual': True, 'empty_reason': ''
                                        }])
                                        st.session_state.schedule = pd.concat(
                                            [st.session_state.schedule, _new_row], ignore_index=True
                                        )
                                else:
                                    st.session_state.schedule.loc[_mask_req, 'employee'] = _candidate
                                    st.session_state.schedule.loc[_mask_req, 'is_manual'] = True
                                    if _stype == 'full' and _c_date:
                                        _mask_cand = (_sched['date'].astype(str) == _c_date) & (_sched['dept'] == _c_dept)
                                        st.session_state.schedule.loc[_mask_cand, 'employee'] = _requester
                                        st.session_state.schedule.loc[_mask_cand, 'is_manual'] = True
                                save_to_db("schedule", st.session_state.schedule)
                                _swap_reqs.loc[_idx, 'status'] = 'approved'
                                save_to_db("swap_requests", _swap_reqs)
                                st.session_state.swap_requests = _swap_reqs.copy()
                                st.session_state['show_swap_approved'] = True
                                st.rerun()
                            if _col_r.button("❌ דחה", key=f"reject_swap_{_idx}", use_container_width=True):
                                _swap_reqs.loc[_idx, 'status'] = 'rejected'
                                save_to_db("swap_requests", _swap_reqs)
                                st.session_state.swap_requests = _swap_reqs.copy()
                                st.session_state['show_swap_rejected'] = True
                                st.rerun()

    elif selected_nav == 'צוות':
        st.subheader("ניהול צוות עובדים")
        
        # --- טופס הוספת עובד ---
        with st.expander("➕ הוספת עובד חדש", expanded=False):
            with st.form("add_emp_form"):
                col_new1, col_new2 = st.columns(2)
                with col_new1:
                    new_name = st.text_input("שם מלא:")
                    new_type = st.selectbox(
                        "תפקיד:",
                        ["מתמחה", "תורן חוץ", "מנהל/ת", "רופא בכיר", "מנהל מחלקה"],
                        format_func=lambda x: _TYPE_DISPLAY.get(x, x),
                    )
                    new_email = st.text_input("אימייל (להתראות):", placeholder="optional@example.com")
                with col_new2:
                    new_dept = st.selectbox("מחלקה:", ["שיקום", "פנימית גריאטרית", "כללי", "הנהלה", "זה״ב"])
                    new_quota = st.number_input("מכסה חודשית:", min_value=0, value=6)
                    new_weekend_quota = st.number_input("מכסת סופ\"ש:", min_value=0, value=1)
                    new_only_home = st.checkbox("מוגבל למחלקה זו בלבד?", value=False)

                # שדה manage_depts — רק למנהל מחלקה
                new_manage_depts = ""
                if new_type == "מנהל מחלקה":
                    selected_depts = st.multiselect(
                        "מחלקות בניהולו:",
                        options=DAILY_DEPTS_ALL,
                        default=[],
                        key="new_emp_manage_depts"
                    )
                    new_manage_depts = ",".join(selected_depts)

                if st.form_submit_button("הוסף עובד"):
                    if new_name.strip():
                        if new_name not in st.session_state.staff['name'].values:
                            # סיסמת ברירת מחדל מוצפנת
                            def_pass_hash = hashlib.sha256("1234".encode()).hexdigest()

                            new_emp_row = pd.DataFrame([{
                                'name': new_name,
                                'type': new_type,
                                'dept': new_dept,
                                'monthly_quota': new_quota,
                                'weekend_quota': new_weekend_quota,
                                'only_home_dept': new_only_home,
                                'password': def_pass_hash,
                                'email': new_email.strip(),
                                'manage_depts': new_manage_depts.strip(),
                                'recurring_absent_days': '',
                            }])

                            st.session_state.staff = pd.concat([st.session_state.staff, new_emp_row], ignore_index=True)
                            save_to_db("staff", st.session_state.staff)
                            st.success(f"העובד/ת {new_name} נוספ/ה בהצלחה! (סיסמה: 1234)")
                            st.rerun()
        
        st.divider()
        st.caption("שינויים בטבלה נשמרים רק בלחיצה על כפתור השמירה")
        
        # עטיפה בטופס (Form) כדי למנוע טעינה מחדש בכל שינוי תא
        with st.form(key="staff_batch_edit_form"):
            # Ensure only_home_dept exists
            if 'only_home_dept' not in st.session_state.staff.columns:
                st.session_state.staff['only_home_dept'] = False

            # Fix True/False serialization from Google Sheets
            def _is_true(v):
                if pd.isna(v): return False
                if isinstance(v, bool): return v
                return str(v).strip().lower() == 'true'

            st.session_state.staff['only_home_dept'] = st.session_state.staff['only_home_dept'].apply(_is_true)

            # Multi-select for Home Dept only
            valid_names = [n for n in st.session_state.staff['name'].tolist() if str(n).strip() and n != '---']
            default_homes = st.session_state.staff[st.session_state.staff['only_home_dept']]['name'].dropna().tolist()
            default_homes = [n for n in default_homes if n in valid_names]

            selected_home_depts = st.multiselect(
                "עובדים המוגבלים למחלקת האם בלבד (ללא חציות למחלקות אחרות):",
                options=valid_names,
                default=default_homes
            )
            st.divider()

            # Build editor view: exclude password & only_home_dept from the editable table
            # (only_home_dept handled via the multiselect above)
            preferred_order = ['name', 'type', 'dept', 'monthly_quota', 'weekend_quota',
                               'email', 'manage_depts', 'recurring_absent_days']
            available = [c for c in preferred_order if c in st.session_state.staff.columns]
            # tack on any unexpected extra cols (except hidden)
            extras = [c for c in st.session_state.staff.columns
                      if c not in available and c not in ('password', 'only_home_dept', 'whatsapp_link')]
            cols_to_show = available + extras
            staff_view = st.session_state.staff[cols_to_show].copy()

            # Reverse for RTL display
            reversed_cols = cols_to_show[::-1]
            reversed_staff_view = staff_view[reversed_cols]

            staff_editor = st.data_editor(
                reversed_staff_view,
                use_container_width=True,
                num_rows="dynamic",
                hide_index=True,
                column_config={
                    "name": st.column_config.TextColumn(
                        "👤 שם", help="שם מלא של העובד", width="medium", required=True),
                    "type": st.column_config.SelectboxColumn(
                        "תפקיד",
                        options=["מתמחה", "תורן חוץ", "מנהל/ת", "רופא בכיר", "מנהל מחלקה"],
                        width="small", required=True),
                    "dept": st.column_config.SelectboxColumn(
                        "מחלקה",
                        options=["שיקום", "פנימית גריאטרית", "כללי", "הנהלה"],
                        width="small"),
                    "monthly_quota": st.column_config.NumberColumn(
                        "מכסה חודשית", help="מספר תורנויות חודשיות נדרשות",
                        min_value=0, max_value=20, step=1, width="small"),
                    "weekend_quota": st.column_config.NumberColumn(
                        "מכסת סופ\"ש", help="תורנויות סוף שבוע נדרשות",
                        min_value=0, max_value=10, step=1, width="small"),
                    "email": st.column_config.TextColumn(
                        "📧 אימייל", help="לקבלת התראות (אופציונלי)", width="medium"),
                    "manage_depts": st.column_config.TextColumn(
                        "מחלקות בניהול",
                        help="רק למנהל מחלקה — שמות מופרדים בפסיקים, לדוגמה: שיקום גריאטרי א',שיקום גריאטרי ב'",
                        width="medium"),
                    "recurring_absent_days": st.column_config.TextColumn(
                        "🔁 ימי היעדרות קבועים",
                        help="ימי שבוע שבהם העובד נעדר באופן קבוע (יומי). אותיות עברית מופרדות בפסיקים: א,ב,ג,ד,ה,ו,ש. דוגמה: 'ד,ה' = רביעי וחמישי. ייושם אוטומטית בכל סידור.",
                        width="medium"),
                }
            )
            submit_changes = st.form_submit_button("💾 שמור שינויים בצוות", use_container_width=False)
        
        if submit_changes:
            # Merge logic:
            # 1. Take the editor result (staff_editor)
            # 2. Get the original passwords from st.session_state.staff
            # WE MUST BE CAREFUL: "dynamic" rows means users can add/delete rows.
            # If a row is added here, it won't have a password. We should assign default.
            
            # Because we reversed columns for display, we reverse back to normal for processing
            edited_df = staff_editor[staff_editor.columns[::-1]]

            # Reattach only_home_dept dynamically from the multiselect
            edited_df['only_home_dept'] = edited_df['name'].isin(selected_home_depts)

            # We need to preserve passwords for existing users.
            # Simple approach: Join with original on 'name' IF name is unique and didn't change.
            # But users might change names. 
            # Best effort: 
            # If the index matches, keep the password.
            # If new row (index not in old), set default password.
            
            final_df_list = []
            # משיכת נתונים עדכניים כדי למנוע דריסת נתונים
            latest_staff = get_db_data("staff")
            if not latest_staff.empty:
                old_df = latest_staff
            else:
                old_df = st.session_state.staff
            
            for index, row in edited_df.iterrows():
                # Check if this index existed in old_df
                pass_val = hashlib.sha256("1234".encode()).hexdigest() # Default
                
                if index in old_df.index:
                    # Check if name matched (sanity check, though index usually persists in editor unless sorted)
                     pass_val = old_df.loc[index, 'password']
                
                row['password'] = pass_val
                final_df_list.append(row)
            
            # Reconstruct DataFrame including password
            final_new_staff = pd.DataFrame(final_df_list)
            
            st.session_state.staff = final_new_staff
            save_to_db("staff", st.session_state.staff)
            st.success("הנתונים נשמרו בהצלחה!")
            st.rerun()
        
        st.markdown("---")
        col_sync, col_warn = st.columns([1, 3])
        with col_sync:
            if st.button("🔄 סנכרן נתונים מהענן"):
                 # Force reload of all data
                 st.cache_data.clear()
                 for key in ['staff', 'schedule', 'requests']:
                     if key in st.session_state:
                         del st.session_state[key]
                 st.rerun()
        with col_warn:
             st.warning("⚠️ שים לב: עריכה בטבלה זו דורסת שינויים שנעשו ישירות ב-Google Sheets. אם ערכת שם, לחץ קודם על 'סנכרן נתונים'.")

        st.divider()
        st.subheader("ניהול אילוצים ומשמרות")
        
        # בחירת עובד לניהול אילוצים
        selected_emp_mgr = st.selectbox("בחר עובד לניהול אילוצים:", st.session_state.staff['name'].tolist())
        
        if selected_emp_mgr:
            st.write(f"עריכת אילוצים עבור: **{selected_emp_mgr}**")
            
            # --- טעינת נתונים קיימים ---
            current_month_prefix = f"2026-{sel_month:02d}"
            
            # נרמול עמודת התאריך למחרוזת
            requests_df = st.session_state.requests.copy()
            requests_df['date'] = requests_df['date'].astype(str)
            
            # סינון רשומות רלוונטיות לעובד ולחודש
            emp_reqs = requests_df[
                (requests_df['employee'] == selected_emp_mgr) & 
                (requests_df['date'].str.startswith(current_month_prefix))
            ]
            
            existing_constraints = emp_reqs[emp_reqs['status'] == 'אילוץ']['date'].tolist()
            existing_wishes = emp_reqs[emp_reqs['status'] == 'בקשה']['date'].tolist()
            
            # --- ממשק ויזואלי (מודרני) ---
            # Use employee index for key_prefix — Hebrew names break CSS class selectors
            emp_names_list = st.session_state.staff['name'].tolist()
            emp_idx        = emp_names_list.index(selected_emp_mgr) if selected_emp_mgr in emp_names_list else 0
            mgr_key_prefix = f"mgr_e{emp_idx}"
            mgr_const_days = [int(d.split('-')[2]) for d in existing_constraints]
            mgr_wish_days  = [int(d.split('-')[2]) for d in existing_wishes]
            mgr_cal_sd     = st.session_state.get('special_days')
            if isinstance(mgr_cal_sd, pd.DataFrame) and mgr_cal_sd.empty:
                mgr_cal_sd = None

            st.divider()
            new_const_day_nums, new_wish_day_nums = render_modern_calendar(
                2026, sel_month,
                mgr_const_days, mgr_wish_days,
                special_days_df=mgr_cal_sd,
                key_prefix=mgr_key_prefix,
                show_validation=False
            )
            new_constraints = [f"2026-{sel_month:02d}-{d:02d}" for d in new_const_day_nums]
            new_wishes       = [f"2026-{sel_month:02d}-{d:02d}" for d in new_wish_day_nums]
            
            st.divider()
            
            if st.button("💾 שמור שינויים לעובד זה"):
                # בדיקת חפיפה (סתירה)
                overlap = set(new_constraints).intersection(set(new_wishes))
                if overlap:
                    formatted_overlap = [datetime.strptime(d, '%Y-%m-%d').strftime('%d/%m') for d in overlap]
                    st.error(f"שגיאה: התאריכים הבאים מסומנים גם כחסימה וגם כבקשה: {', '.join(formatted_overlap)}")
                else:
                    # הכל תקין - שמירה
                    # משיכת נתונים חיים מהגיליון (עוקף cache למניעת דריסה הדדית)
                    live = _fetch_live("requests")
                    base = live if not live.empty else st.session_state.requests

                    # 1. מחיקת הישן לחודש זה
                    mask_keep = ~((base['employee'].astype(str).str.strip() == str(selected_emp_mgr).strip()) &
                                  (base['date'].astype(str).str.startswith(current_month_prefix)))
                    base = base[mask_keep]

                    # 2. הוספת החדש
                    new_records = []
                    for d in new_constraints:
                        new_records.append({'employee': selected_emp_mgr, 'date': d, 'status': 'אילוץ'})
                    for d in new_wishes:
                        new_records.append({'employee': selected_emp_mgr, 'date': d, 'status': 'בקשה'})

                    merged = pd.concat([base, pd.DataFrame(new_records)], ignore_index=True) if new_records else base
                    save_to_db("requests", merged)
                    st.session_state.requests = merged
                    _fetch_sheet_data_silently.clear()
                    st.success(f"האילוצים של {selected_emp_mgr} עודכנו בהצלחה!")
                    st.session_state.pop(f"{mgr_key_prefix}_init_{sel_month}", None)
                    st.rerun()

            # ── ☀️ היעדרויות יומיות לעובד הנבחר ──────────────────────
            st.divider()
            st.markdown("### ☀️ היעדרויות יומיות (עבודת בוקר)")
            st.caption("בקשות ההיעדרות של העובד — ניתן לאשר/לדחות בקשות ממתינות.")

            ar_tzevet = st.session_state.absence_requests.copy()
            if ar_tzevet.empty or 'employee' not in ar_tzevet.columns:
                st.info("אין בקשות במערכת.")
            else:
                ar_tzevet['employee'] = ar_tzevet['employee'].astype(str).str.strip()
                ar_tzevet['status']   = ar_tzevet['status'].astype(str).str.lower()
                emp_n = str(selected_emp_mgr).strip()
                emp_reqs_da = ar_tzevet[ar_tzevet['employee'] == emp_n]

                if emp_reqs_da.empty:
                    st.info(f"אין בקשות היעדרות לעובד {selected_emp_mgr}.")
                else:
                    pending_da = emp_reqs_da[emp_reqs_da['status'] == 'pending']
                    if not pending_da.empty:
                        st.markdown(f"**🟡 ממתינות לאישור ({len(pending_da)})**")
                        for idx_da, row_da in pending_da.iterrows():
                            with st.container(border=True):
                                ca, cb, cc, cd, ce = st.columns([2, 2, 2, 1, 1])
                                ca.write(f"{row_da['start_date']} – {row_da['end_date']}")
                                cb.write(row_da.get('type', '—'))
                                cc.write(row_da.get('dept_at_request', '—') or '—')
                                req_id_da = str(row_da.get('id', idx_da))
                                if cd.button("✅ אשר", key=f"tzv_ap_{req_id_da}",
                                             use_container_width=True):
                                    _approve_request(req_id_da, str(user_name).strip())
                                    st.rerun()
                                if ce.button("❌ דחה", key=f"tzv_rj_{req_id_da}",
                                             use_container_width=True):
                                    _reject_request(req_id_da, str(user_name).strip())
                                    st.rerun()
                                if row_da.get('notes'):
                                    st.caption(f"💬 {row_da['notes']}")
                    # All requests (including approved/rejected) as a compact table
                    st.markdown("**📋 היסטוריה מלאה**")
                    show_da = emp_reqs_da[['start_date','end_date','type','status','approved_by','notes']].copy()
                    show_da['status'] = show_da['status'].map({
                        'pending':'⏳ ממתין', 'approved':'✅ אושר', 'rejected':'❌ נדחה'
                    }).fillna(show_da['status'])
                    show_da = show_da.rename(columns={
                        'start_date':'תאריך התחלה', 'end_date':'תאריך סיום',
                        'type':'סוג', 'status':'סטטוס', 'approved_by':'מאשר', 'notes':'הערה',
                    })
                    st.dataframe(show_da, use_container_width=True, hide_index=True)

    elif selected_nav == 'דוחות וניהול':
        # st.header("דוח סטטוס ומסכמים") - Removed by user request
        
        # --- חלק חדש: לוח בקרה מודרני ---
        st.markdown("### 📊 לוח בקרה - סיכום חודשי")
        
        # --- 1. חישוב נתונים למדדים ---
        current_month_prefix = f"2026-{sel_month:02d}"
        relevant_staff = st.session_state.staff[st.session_state.staff['type'].isin(['מתמחה', 'תורן חוץ'])]
        n_total = len(relevant_staff)
        submitted_count = 0
        status_list = []
        
        reqs_df = st.session_state.requests.copy()
        if not reqs_df.empty:
            reqs_df['date'] = reqs_df['date'].astype(str)
            reqs_df['employee'] = reqs_df['employee'].astype(str).str.strip()

        for _, emp in relevant_staff.iterrows():
            name = str(emp['name']).strip()

            n_c, n_w = 0, 0
            if not reqs_df.empty:
                user_reqs = reqs_df[(reqs_df['employee'] == name) & (reqs_df['date'].str.startswith(current_month_prefix))]
                n_c = len(user_reqs[user_reqs['status'] == 'אילוץ'])
                n_w = len(user_reqs[user_reqs['status'] == 'בקשה'])
            
            has_submitted = (n_c + n_w) > 0
            if has_submitted: submitted_count += 1
            
            status_list.append({
                "שם העובד": name.strip(),
                "תפקיד": emp['type'],
                "סטטוס": "✅ הוגש" if has_submitted else "❌ טרם הוגש",
                "חסימות": n_c,
                "בקשות": n_w
            })

        # --- 2. הצגת כרטיסי מדדים מותאמים אישית (Custom Metric Cards) ---
        m_cols = st.columns(3)
        
        # Helper function for generating HTML cards
        def metric_html(title, value, subtitle, icon, color, gradient="from-[#ffffff] to-[#f9fafb]"):
            return f"""
            <div style="
                background: linear-gradient(135deg, {gradient.split('to-')[0].replace('from-[', '').replace(']', '').strip()} 0%, {gradient.split('to-')[1].replace('[', '').replace(']', '').strip()} 100%);
                border-radius: 12px;
                padding: 20px;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
                text-align: right;
                direction: rtl;
                border-top: 4px solid {color};
                transition: transform 0.2s ease-in-out;
                margin-bottom: 20px;
            " onmouseover="this.style.transform='translateY(-5px)'" onmouseout="this.style.transform='translateY(0)'">
                <h4 style="color: #6b7280; font-size: 14px; margin: 0; padding-bottom: 8px;">{title}</h4>
                <div style="display: flex; justify-content: space-between; align-items: baseline;">
                    <h2 style="color: #111827; font-size: 32px; font-weight: 700; margin: 0;">{value}</h2>
                    <span style="font-size: 24px;">{icon}</span>
                </div>
                <p style="color: #10b981; font-size: 12px; margin-top: 8px; margin-bottom:0;">{subtitle}</p>
            </div>
            """

        with m_cols[0]:
            st.markdown(metric_html("סה״כ צוות", f"{n_total}", "מתמחים ותורני חוץ", "👥", "#4f46e5"), unsafe_allow_html=True)
        with m_cols[1]:
            st.markdown(metric_html("הגישו אילוצים", f"{submitted_count}", f"עבור חודש {sel_month}", "✅", "#10b981"), unsafe_allow_html=True)
        with m_cols[2]:
            pending = n_total - submitted_count
            p_color = "#ef4444" if pending > 0 else "#10b981"
            st.markdown(metric_html("ממתינים להגשה", f"{pending}", "נדרש תזכורת", "⚠️", p_color), unsafe_allow_html=True)

        st.divider()

        # --- 3. גרף משמרות וסטטוס הגשה (שני טורים) ---
        col_chart, col_table = st.columns([1.2, 1])

        with col_chart:
            st.markdown("##### 📈 ספירת תורנויות")
            sched = st.session_state.schedule
            
            # סינון ספירת המשמרות לחודש הנוכחי בלבד
            if not sched.empty:
                sched_month = sched[sched['date'].astype(str).str.startswith(current_month_prefix)]
            else:
                sched_month = sched

            if not sched_month.empty:
                # ספירת משמרות לפי עובד וסוג
                reg_counts = sched_month[~sched_month['dept'].astype(str).str.contains("שישי בוקר", na=False)]['employee'].value_counts()
                morn_counts = sched_month[sched_month['dept'].astype(str).str.contains("שישי בוקר", na=False)]['employee'].value_counts()
                combined_df = pd.DataFrame({'תורנויות': reg_counts, 'שישי בוקר': morn_counts}).fillna(0)
                st.bar_chart(combined_df, color=["#4f46e5", "#fb923c"]) # Indigo and Orange
            else:
                st.info("אין נתוני שיבוץ להצגה בגרף")

        with col_table:
            st.markdown("##### 📋 סטטוס הגשות")
            df_status = pd.DataFrame(status_list)
            
            if not df_status.empty:
                df_status = df_status[["שם העובד", "תפקיד", "סטטוס", "חסימות", "בקשות"]] # Ensure order
                # עיצוב טבלה מותאם
                def style_status(val):
                    try:
                        color = '#dcfce7' if '✅' in str(val) else '#fee2e2'
                        return f'background-color: {color}; color: #1e293b; font-weight: 500; border-radius: 4px;'
                    except:
                        return ''

                # rtl support
                reversed_df_status = df_status[df_status.columns[::-1]]
                
                # Make mobile text unbreak using a dedicated mobile-responsive CSS injection inside ui_components.py
                try:
                     styled_df = reversed_df_status.style.applymap(style_status, subset=['סטטוס']).set_properties(**{'text-align': 'right', 'direction': 'rtl'})
                     st.dataframe(styled_df, use_container_width=True, hide_index=True)
                except AttributeError: # For newer pandas without applymap handling
                     styled_df = reversed_df_status.style.map(style_status, subset=['סטטוס']).set_properties(**{'text-align': 'right', 'direction': 'rtl'})
                     st.dataframe(styled_df, use_container_width=True, hide_index=True)
                except Exception as e:
                     st.dataframe(reversed_df_status, use_container_width=True, hide_index=True)
            else:
                 st.info("אין נתונים להצגה.")

        # ── "ייצוא נתונים" הוסר מכאן והועבר לטאב "סידור תורנויות" (ראה כפתור 📤 שם) ──


    if selected_nav == 'דוחות וניהול': # Fairness merged into Reports
        st.subheader("מעקב הוגנות - ימי רביעי, חמישי ושישי (מתמחים בלבד)")
        
        # טעינת כל הנתונים
        full_schedule = st.session_state.schedule.copy()
        if not full_schedule.empty:
            # המרת תאריך ל-datetime
            full_schedule['date_dt'] = pd.to_datetime(full_schedule['date'])
            full_schedule['weekday'] = full_schedule['date_dt'].dt.weekday
            full_schedule['month_year'] = full_schedule['date_dt'].dt.strftime('%m/%Y')
            
            # סינון רק למתמחים
            staff_types = st.session_state.staff.set_index('name')['type'].to_dict()
            full_schedule['staff_type'] = full_schedule['employee'].map(staff_types)
            intern_schedule = full_schedule[full_schedule['staff_type'] == 'מתמחה']
            
            # יצירת טבלת סיכום
            # ימי רביעי = 2, ימי חמישי = 3
            tracker = []
            
            # קבלת רשימת כל המתמחים (כולל אלו שלא שובצו כלל)
            all_interns = st.session_state.staff[st.session_state.staff['type'] == 'מתמחה']['name'].tolist()
            
            for name in all_interns:
                emp_sched = intern_schedule[intern_schedule['employee'] == name]
                wed_count = len(emp_sched[emp_sched['weekday'] == 2])
                thu_count = len(emp_sched[emp_sched['weekday'] == 3])
                fri_morn_count = len(emp_sched[emp_sched['dept'].str.contains('שישי בוקר')])
                
                tracker.append({
                    'שם המתמחה': name,
                    "סה\"כ ימי ד' (מבוקש)": wed_count,
                    "סה\"כ ימי ה' (קשה)": thu_count,
                    "שישי בוקר": fri_morn_count,
                    'ציון הוגנות (נטו)': wed_count - (thu_count + fri_morn_count) # חיובי = קיבל יותר טובים, שלילי = קיבל יותר קשים
                })
            
            df_fairness = pd.DataFrame(tracker).sort_values('ציון הוגנות (נטו)', ascending=False)
            
            # עיצוב הטבלה
            st.dataframe(
                df_fairness[df_fairness.columns[::-1]].style.background_gradient(subset=['ציון הוגנות (נטו)'], cmap="RdYlGn"),
                use_container_width=True
            )
            
            # פירוט לפי חודשים הוסר לבקשת המשתמש.
        else:
            st.info("הלוח עדיין ריק.")

    # --- דוח יומי אוטומטי ---
    if selected_nav == 'דוחות וניהול':
        st.divider()
        st.subheader("🤖 דוח בעיות צפויות")

        # Headline: heavily blocked days from last report
        _report_preview = get_db_data("daily_report")
        if not _report_preview.empty and 'problem_type' in _report_preview.columns:
            _peak_days = _report_preview[_report_preview['problem_type'] == 'ימי שיא חסימה']
            if not _peak_days.empty:
                _critical_peaks = _peak_days[_peak_days['severity'] == 'קריטי']
                _warn_peaks = _peak_days[_peak_days['severity'] == 'אזהרה']
                _headline_parts = []
                if not _critical_peaks.empty:
                    _headline_parts.append(f"🔴 {len(_critical_peaks)} ימים קריטיים (50%+ חסמו)")
                if not _warn_peaks.empty:
                    _headline_parts.append(f"🟡 {len(_warn_peaks)} ימים בסיכון (30%+ חסמו)")
                if _headline_parts:
                    st.info("**ימים קשים לאיוש החודש:** " + " · ".join(_headline_parts) +
                            " — ראה פירוט בדוח למטה")

        col_rep1, col_rep2 = st.columns([3, 1])
        with col_rep2:
            if st.button("🔄 הרץ סריקה עכשיו", use_container_width=True):
                with st.spinner("סורק..."):
                    try:
                        # Import the analysis functions directly from daily_report.py
                        import importlib.util, sys as _sys
                        _spec = importlib.util.spec_from_file_location(
                            "daily_report",
                            os.path.join(os.path.dirname(__file__), "daily_report.py")
                            if hasattr(__file__, '__file__') else "daily_report.py"
                        )
                        _dr = importlib.util.module_from_spec(_spec)
                        _spec.loader.exec_module(_dr)

                        _staff    = st.session_state.staff.copy()
                        _requests = st.session_state.requests.copy()
                        _month    = sel_month

                        _problems = _dr.analyze_month(2026, _month, _staff, _requests)
                        if not _problems:
                            _problems = [{'severity': 'תקין', 'problem_type': 'ללא בעיות',
                                          'description': f'לא נמצאו בעיות צפויות לחודש {_month}/2026', 'day': 0}]

                        # Save to Google Sheets via gspread
                        _now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
                        _month_str = f"2026-{_month:02d}"
                        _gc = get_gspread_client()
                        _sh = _gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
                        _header = [['generated_at', 'month', 'severity', 'problem_type', 'description']]
                        _rows = [[_now_str, _month_str, p['severity'], p['problem_type'], p['description']]
                                 for p in _problems]
                        try:
                            _ws = _sh.worksheet('daily_report')
                            _ws.clear()
                        except Exception:
                            _ws = _sh.add_worksheet('daily_report', rows=500, cols=6)
                        _ws.update('A1', _header + _rows)

                        _fetch_sheet_data_silently.clear()
                        st.toast(f"סריקה הושלמה — {len(_problems)} ממצאים")
                    except Exception as e:
                        st.error(f"שגיאה בהרצת הסריקה: {e}")
                st.rerun()

        report_df = get_db_data("daily_report")

        if report_df.empty:
            st.info("טרם הופק דוח. לחץ 'הרץ סריקה עכשיו' או המתן להרצה האוטומטית היומית.")
        else:
            generated_at = report_df['generated_at'].iloc[0] if 'generated_at' in report_df.columns else "לא ידוע"
            report_month = report_df['month'].iloc[0] if 'month' in report_df.columns else ""
            with col_rep1:
                st.caption(f"עודכן לאחרונה: {generated_at} | חודש: {report_month}")

            severity_icon = {'קריטי': '🔴', 'אזהרה': '🟡', 'מידע': 'ℹ️', 'תקין': '✅'}
            severity_order = {'קריטי': 0, 'אזהרה': 1, 'מידע': 2, 'תקין': 3}

            report_df['_order'] = report_df['severity'].map(severity_order).fillna(9)
            report_df = report_df.sort_values('_order')

            current_type = None
            for _, row in report_df.iterrows():
                ptype = row.get('problem_type', '')
                sev   = row.get('severity', '')
                desc  = row.get('description', '')
                icon  = severity_icon.get(sev, '•')

                if ptype != current_type:
                    current_type = ptype
                    st.markdown(f"**{ptype}**")

                if sev == 'קריטי':
                    st.error(f"{icon} {desc}")
                elif sev == 'אזהרה':
                    st.warning(f"{icon} {desc}")
                elif sev == 'תקין':
                    st.success(f"{icon} {desc}")
                else:
                    st.info(f"{icon} {desc}")

    # --- ניתוח שימוש במערכת ---
    if selected_nav == 'דוחות וניהול':
        st.divider()
        with st.expander("📈 ניתוח שימוש במערכת", expanded=False):
            _alog = get_db_data("analytics_log")
            if _alog.empty or 'event_type' not in _alog.columns:
                st.info("אין נתוני שימוש עדיין. הנתונים יצטברו אוטומטית ככל שמשתמשים נכנסים.")
            else:
                # ─── A. סיכום כללי ───────────────────────────────────────────────
                st.markdown("#### A. סיכום כללי")
                _logins = _alog[_alog['event_type'] == 'login_success']
                _submits = _alog[_alog['event_type'] == 'constraint_submit']
                _unique_users = _alog['user_name'].nunique()
                _mobile_pct = (
                    int((_logins['device_type'] == 'mobile').sum() / len(_logins) * 100)
                    if not _logins.empty else 0
                )
                _avg_submits = (
                    _submits.groupby('active_month').size().mean()
                    if not _submits.empty else 0
                )
                _mc1, _mc2, _mc3, _mc4 = st.columns(4)
                _mc1.metric("סה\"כ התחברויות", len(_logins))
                _mc2.metric("משתמשים ייחודיים", _unique_users)
                _mc3.metric("שיעור מובייל", f"{_mobile_pct}%")
                _mc4.metric("ממוצע הגשות/חודש", f"{_avg_submits:.1f}")

                st.divider()

                # ─── B. פעילות לפי משתמש ─────────────────────────────────────────
                st.markdown("#### B. פעילות לפי משתמש")
                _by_user = pd.DataFrame()
                if not _alog.empty:
                    _grp = _alog.groupby('user_name')
                    _b_logins  = _grp.apply(lambda g: (g['event_type'] == 'login_success').sum())
                    _b_submits = _grp.apply(lambda g: (g['event_type'] == 'constraint_submit').sum())
                    _b_searches= _grp.apply(lambda g: (g['event_type'] == 'swap_search').sum())
                    _b_swaps   = _grp.apply(lambda g: (g['event_type'] == 'swap_request_sent').sum())
                    _b_device  = _alog[_alog['event_type'] == 'login_success'].groupby('user_name')['device_type'].agg(
                        lambda x: x.value_counts().index[0] if len(x) > 0 else 'unknown'
                    )
                    _by_user = pd.DataFrame({
                        'שם': _b_logins.index,
                        'התחברויות': _b_logins.values,
                        'הגשות': _b_submits.reindex(_b_logins.index, fill_value=0).values,
                        'חיפושי החלפה': _b_searches.reindex(_b_logins.index, fill_value=0).values,
                        'בקשות החלפה': _b_swaps.reindex(_b_logins.index, fill_value=0).values,
                        'מכשיר נפוץ': _b_device.reindex(_b_logins.index, fill_value='unknown').values,
                    })
                    st.dataframe(_by_user[_by_user.columns[::-1]], use_container_width=True, hide_index=True)

                st.divider()

                # ─── C. שיעור חסימה לעובד ────────────────────────────────────────
                st.markdown("#### C. שיעור חסימה לעובד (חודש פעיל)")
                _reqs_df = get_db_data("requests")
                if not _reqs_df.empty:
                    _month_prefix_a = f"2026-{sel_month:02d}"
                    _days_in_month = calendar.monthrange(2026, sel_month)[1]
                    _blocks = _reqs_df[
                        (_reqs_df['status'] == 'אילוץ') &
                        (_reqs_df['date'].astype(str).str.startswith(_month_prefix_a))
                    ].groupby('employee').size().reset_index(name='חסימות')
                    _blocks['חסימות'] = _blocks['חסימות'].astype(int)
                    _blocks['% חסימה'] = (_blocks['חסימות'] / _days_in_month * 100).round(1)
                    _blocks = _blocks.sort_values('% חסימה', ascending=False)

                    def _block_color(pct):
                        if pct > 60: return '🔴'
                        if pct > 40: return '🟡'
                        return '🟢'

                    _blocks['סטטוס'] = _blocks['% חסימה'].apply(_block_color)
                    _risk = _blocks[_blocks['% חסימה'] > 60]['employee'].tolist()
                    if _risk:
                        st.warning(f"⚠️ סיכון שיבוץ — חסימה מעל 60%: {', '.join(_risk)}")
                    st.dataframe(_blocks[['employee', 'חסימות', '% חסימה', 'סטטוס']].rename(
                        columns={'employee': 'עובד/ת'}
                    )[['סטטוס', '% חסימה', 'חסימות', 'עובד/ת']], use_container_width=True, hide_index=True)
                else:
                    st.info("אין נתוני בקשות לחודש זה.")

                st.divider()

                # ─── D. שימוש בטאבים ─────────────────────────────────────────────
                st.markdown("#### D. שימוש בטאבים")
                _tab_entries = _alog[(_alog['event_type'] == 'tab_view') & (_alog['detail_2'] == 'enter')]
                if not _tab_entries.empty:
                    _tab_counts = _tab_entries.groupby('detail_1').size().reset_index(name='כניסות')
                    _tab_counts = _tab_counts.rename(columns={'detail_1': 'טאב'})
                    st.bar_chart(_tab_counts.set_index('טאב')['כניסות'])
                else:
                    st.info("אין נתוני טאב עדיין.")

                st.divider()

                # ─── E. זמן ממוצע בטאב ────────────────────────────────────────────
                st.markdown("#### E. זמן ממוצע בטאב (שניות)")
                _tab_exit = _alog[(_alog['event_type'] == 'tab_view') & (_alog['detail_2'] != 'enter')].copy()
                if not _tab_exit.empty:
                    _tab_exit['שניות'] = pd.to_numeric(_tab_exit['detail_2'], errors='coerce')
                    _tab_exit = _tab_exit.dropna(subset=['שניות'])
                    if not _tab_exit.empty:
                        _avg_time = _tab_exit.groupby('detail_1')['שניות'].mean().round(1).reset_index()
                        _avg_time = _avg_time.rename(columns={'detail_1': 'טאב', 'שניות': 'ממוצע שניות'})
                        st.bar_chart(_avg_time.set_index('טאב')['ממוצע שניות'])
                    else:
                        st.info("אין נתוני זמן בטאב עדיין.")
                else:
                    st.info("אין נתוני זמן בטאב עדיין.")

                st.divider()

                # ─── F. התחברויות לפי שעה ─────────────────────────────────────────
                st.markdown("#### F. התחברויות לפי שעה ביום")
                if not _logins.empty:
                    _logins_ts = _logins.copy()
                    _logins_ts['שעה'] = pd.to_datetime(_logins_ts['timestamp'], errors='coerce').dt.hour
                    _hour_counts = _logins_ts.groupby('שעה').size().reindex(range(24), fill_value=0).reset_index(name='כניסות')
                    st.bar_chart(_hour_counts.set_index('שעה')['כניסות'])
                else:
                    st.info("אין נתוני כניסה עדיין.")

                st.divider()

                # ─── G. סוג מכשיר ─────────────────────────────────────────────────
                st.markdown("#### G. סוג מכשיר")
                if not _logins.empty:
                    _dev_counts = _logins['device_type'].value_counts().reset_index()
                    _dev_counts.columns = ['מכשיר', 'כניסות']
                    _gc1, _gc2 = st.columns(2)
                    with _gc1:
                        st.dataframe(_dev_counts[['כניסות', 'מכשיר']], use_container_width=True, hide_index=True)
                    with _gc2:
                        _user_dev = _logins.groupby('user_name')['device_type'].agg(
                            lambda x: x.value_counts().index[0] if len(x) > 0 else 'unknown'
                        ).reset_index().rename(columns={'user_name': 'שם', 'device_type': 'מכשיר נפוץ'})
                        st.dataframe(_user_dev[['מכשיר נפוץ', 'שם']], use_container_width=True, hide_index=True)
                else:
                    st.info("אין נתוני מכשיר עדיין.")

                st.divider()

                # ─── H. זיהוי רענון דף ────────────────────────────────────────────
                st.markdown("#### H. זיהוי רענון דף")
                if not _logins.empty:
                    _logins_ts2 = _logins.copy()
                    _logins_ts2['ts'] = pd.to_datetime(_logins_ts2['timestamp'], errors='coerce')
                    _logins_ts2 = _logins_ts2.sort_values(['user_name', 'ts'])
                    _logins_ts2['prev_ts'] = _logins_ts2.groupby('user_name')['ts'].shift(1)
                    _logins_ts2['gap_min'] = (_logins_ts2['ts'] - _logins_ts2['prev_ts']).dt.total_seconds() / 60
                    _reloads = _logins_ts2[_logins_ts2['gap_min'] < 5]['user_name'].unique().tolist()
                    if _reloads:
                        st.warning(f"⚠️ משתמשים עם כניסות כפולות תוך 5 דקות (ייתכן רענון דף): {', '.join(_reloads)}")
                    else:
                        st.success("לא זוהו רענונים חשודים.")
                else:
                    st.info("אין נתונים.")

                st.divider()

                # ─── I. תזמון הגשות ───────────────────────────────────────────────
                st.markdown("#### I. תזמון הגשות (יום בחודש)")
                if not _submits.empty:
                    _sub_day = _submits['day_of_month'].astype(str).str.extract(r'(\d+)')[0]
                    _sub_day = pd.to_numeric(_sub_day, errors='coerce').dropna().astype(int)
                    _day_counts = _sub_day.value_counts().reindex(range(1, 32), fill_value=0).reset_index()
                    _day_counts.columns = ['יום בחודש', 'הגשות']
                    st.bar_chart(_day_counts.set_index('יום בחודש')['הגשות'])
                else:
                    st.info("אין נתוני הגשות עדיין.")

    # ── סידור חודשי (אדמין) ────────────────────────────────────
    if selected_nav == 'סידור חודשי':
        st.subheader("🗓️ סידור חודשי — ניהול")

        # ── Top: month selector + active-month action ──────────
        hebrew_months = ["ינואר","פברואר","מרץ","אפריל","מאי","יוני","יולי",
                         "אוגוסט","ספטמבר","אוקטובר","נובמבר","דצמבר"]

        # Build options: 6 months back + active + 6 months ahead (wrap around year)
        view_opts = [((daily_active_month_int - 1 + i) % 12) + 1 for i in range(-6, 7)]

        if 'daily_view_month' not in st.session_state:
            st.session_state.daily_view_month = daily_active_month_int

        col_top1, col_top2, col_top3 = st.columns([2, 2, 2])
        with col_top1:
            st.session_state.daily_view_month = st.selectbox(
                "🗓️ חודש לתכנון/עריכה:",
                view_opts,
                format_func=lambda m: f"{hebrew_months[m-1]} ({m})",
                index=view_opts.index(st.session_state.daily_view_month)
                       if st.session_state.daily_view_month in view_opts else 0,
                key="daily_view_month_sel"
            )
        view_month = st.session_state.daily_view_month
        view_year_month = f"2026-{view_month:02d}"

        with col_top2:
            is_active = (view_month == daily_active_month_int)
            if is_active:
                st.markdown(
                    f"<div style='padding:8px;background:#dcfce7;border-radius:8px;"
                    f"text-align:center;color:#166534;font-weight:600'>"
                    f"✅ זהו החודש הפעיל</div>",
                    unsafe_allow_html=True)
            else:
                if st.button(f"⚡ הפוך את {hebrew_months[view_month-1]} לחודש פעיל",
                             key="set_active_month", use_container_width=True):
                    _set_setting('daily_active_month', view_month)
                    _set_setting('daily_requests_open', 'True')
                    st.success(f"חודש פעיל: {hebrew_months[view_month-1]}. הגשות נפתחו.")
                    st.rerun()
        with col_top3:
            req_open_now = daily_requests_open if is_active else None
            if is_active:
                if req_open_now:
                    if st.button(f"🔓 סגור הגשות לחודש {hebrew_months[view_month-1]}",
                                 key="toggle_req_close", use_container_width=True):
                        _set_setting('daily_requests_open', 'False')
                        st.success("הגשות נסגרו"); st.rerun()
                else:
                    if st.button(f"🔒 פתח הגשות לחודש {hebrew_months[view_month-1]}",
                                 key="toggle_req_open", use_container_width=True):
                        _set_setting('daily_requests_open', 'True')
                        st.success("הגשות נפתחו"); st.rerun()
            else:
                st.caption("פתיחה/סגירה זמינה רק לחודש הפעיל")

        st.divider()

        # ── Sub-tabs (Phase 2 implements only the first; rest are stubs) ──
        sub_tabs = st.tabs(["שיבוץ חודשי", "לוח עבודה כללי", "כל הבקשות", "צור סידור", "ייצוא"])

        # ─── Tab 1: שיבוץ חודשי ─────────────────────────────────
        with sub_tabs[0]:
            st.markdown(f"#### שיוך עובדים למחלקות — {hebrew_months[view_month-1]} 2026")
            st.caption("בחר לכל עובד את המחלקה היומית שלו לחודש זה. תורן חוץ ומנהלים אינם בטבלה.")

            DAILY_DEPTS = list(DAILY_DEPTS_ALL) + ["— לא שובץ —"]

            # Filter active staff: only מתמחה + רופא בכיר
            staff = st.session_state.staff.copy()
            staff['name'] = staff['name'].astype(str).str.strip()
            staff['type'] = staff['type'].astype(str).str.strip()
            eligible = staff[staff['type'].isin(['מתמחה', 'רופא בכיר'])]
            eligible = eligible[eligible['name'].str.len() > 0]
            eligible = eligible[eligible['name'] != '---']

            if eligible.empty:
                st.warning("אין עובדים פעילים מסוג מתמחה או רופא/ה בכיר/ה.")
            else:
                # Pre-fill from existing dept_rotation rows for this month
                dr = st.session_state.dept_rotation.copy()
                if 'employee' in dr.columns:
                    dr['employee']   = dr['employee'].astype(str).str.strip()
                    dr['year_month'] = dr['year_month'].astype(str)
                    dr['daily_dept'] = dr['daily_dept'].astype(str)
                    existing = dr[dr['year_month'] == view_year_month].set_index('employee')['daily_dept'].to_dict()
                else:
                    existing = {}

                with st.form(f"rotation_form_{view_month}"):
                    new_assignments = {}
                    for _, emp_row in eligible.iterrows():
                        emp_name = emp_row['name']
                        emp_type = emp_row['type']
                        current = existing.get(emp_name, "— לא שובץ —")
                        if current not in DAILY_DEPTS:
                            current = "— לא שובץ —"

                        c1, c2 = st.columns([2, 3])
                        c1.markdown(
                            f"<div style='padding:6px 0;font-weight:500'>"
                            f"{emp_name} <span style='color:#64748b;font-size:0.8rem'>({emp_type})</span></div>",
                            unsafe_allow_html=True)
                        new_assignments[emp_name] = c2.selectbox(
                            "", DAILY_DEPTS,
                            index=DAILY_DEPTS.index(current),
                            key=f"rot_{emp_name}_{view_month}",
                            label_visibility="collapsed"
                        )

                    submit = st.form_submit_button(f"💾 שמור שיבוץ לחודש {hebrew_months[view_month-1]}")

                if submit:
                    # Reassignment-warning check (Phase 4 will refine, here we just notify)
                    abs_df = st.session_state.absence_requests.copy()
                    warnings_for = []
                    if not abs_df.empty and 'status' in abs_df.columns:
                        approved_future = abs_df[
                            (abs_df['status'].astype(str) == 'approved') &
                            (abs_df['type'].astype(str) == 'חופש עתידי') &
                            (abs_df['start_date'].astype(str).str.startswith(view_year_month))
                        ]
                        for _, ar in approved_future.iterrows():
                            emp_n = str(ar['employee']).strip()
                            old_dept = existing.get(emp_n, '')
                            new_dept = new_assignments.get(emp_n, '')
                            if old_dept and new_dept and old_dept != new_dept:
                                warnings_for.append((emp_n, old_dept, new_dept))

                    if warnings_for:
                        for emp_n, old_d, new_d in warnings_for:
                            st.warning(f"⚠️ {emp_n}: יש חופש עתידי מאושר. שינוי: {old_d} → {new_d}. "
                                       f"שלח התראה למנהלי המחלקות הרלוונטיים.")

                    # Persist: keep all rows from other months, replace this month
                    other_months = dr[dr['year_month'] != view_year_month] if not dr.empty else pd.DataFrame(
                        columns=['employee','year_month','daily_dept'])
                    new_rows = []
                    for emp_n, dept_n in new_assignments.items():
                        if dept_n != "— לא שובץ —":
                            new_rows.append({
                                'employee': emp_n,
                                'year_month': view_year_month,
                                'daily_dept': dept_n,
                            })
                    new_dr = pd.concat([other_months, pd.DataFrame(new_rows)], ignore_index=True)
                    st.session_state.dept_rotation = new_dr
                    save_to_db("dept_rotation", new_dr)
                    st.success(f"✅ נשמרו {len(new_rows)} שיבוצים לחודש {hebrew_months[view_month-1]}")
                    st.rerun()

                # Summary panel
                st.divider()
                if not dr.empty:
                    cur = dr[dr['year_month'] == view_year_month]
                    if not cur.empty:
                        st.caption(f"📊 שיבוצים נוכחיים בחודש: {len(cur)} עובדים")
                        for d in DAILY_DEPTS[:-1]:
                            cnt = (cur['daily_dept'] == d).sum()
                            if cnt > 0:
                                st.caption(f"   • {d}: {cnt} עובדים")

        # ─── Tabs 2-5 stubs (future phases) ─────────────────────
        with sub_tabs[1]:
            st.markdown(f"#### לוח עבודה כללי — {hebrew_months[view_month-1]} 2026")
            st.caption("לחיצה על תא מחזרת בין: עובד/ת → חופש → 202 → אחרי תורנות → אחר. שינויים נשמרים מיד עם is_manual=True.")
            # Pre-build a map: dept_name → [מנהל מחלקה names] so their rows always appear
            _staff_all = st.session_state.staff
            _dept_mgr_map: dict[str, list[str]] = {d: [] for d in DAILY_DEPTS_ALL}
            if not _staff_all.empty and 'type' in _staff_all.columns:
                for _, _sr in _staff_all.iterrows():
                    if str(_sr.get('type', '')).strip() != 'מנהל מחלקה':
                        continue
                    _mgr_name = str(_sr.get('name', '')).strip()
                    if not _mgr_name:
                        continue
                    for _md in _parse_manage_depts(_sr.get('manage_depts', '')):
                        if _md in _dept_mgr_map:
                            _dept_mgr_map[_md].append(_mgr_name)

            dept_inner = st.tabs(DAILY_DEPTS_ALL)
            _ns_map = {d: f"dept_{i}" for i, d in enumerate(DAILY_DEPTS_ALL)}
            for d_tab, d_name in zip(dept_inner, DAILY_DEPTS_ALL):
                with d_tab:
                    # Build employee list: dept_rotation for this month + managers of this dept
                    _dr = st.session_state.dept_rotation
                    _emps_base = []
                    if not _dr.empty and 'employee' in _dr.columns:
                        _mask = ((_dr['year_month'].astype(str) == view_year_month) &
                                 (_dr['daily_dept'].astype(str) == d_name))
                        _emps_base = _dr[_mask]['employee'].astype(str).str.strip().tolist()
                    # Prepend managers (if not already in list from dept_rotation)
                    for _mn in _dept_mgr_map.get(d_name, []):
                        if _mn not in _emps_base:
                            _emps_base = [_mn] + _emps_base
                    _emps_base = _sort_employees_by_role(_emps_base)
                    _render_dept_grid(d_name, view_year_month, view_month,
                                      _ns_map[d_name], employees=_emps_base or None)
                    st.markdown(
                        "<div style='direction:rtl;font-size:0.75rem;color:#64748b;margin-top:6px'>"
                        "<b>מקרא:</b> <span style='background:#16a34a;color:white;padding:1px 6px;border-radius:4px'>עובד/ת</span> &nbsp;"
                        "<span style='background:#2563eb;color:white;padding:1px 6px;border-radius:4px'>חופש</span> &nbsp;"
                        "<span style='background:#ca8a04;color:white;padding:1px 6px;border-radius:4px'>202</span> &nbsp;"
                        "<span style='background:#f97316;color:white;padding:1px 6px;border-radius:4px'>אחרי תורנות</span> &nbsp;"
                        "<span style='background:#94a3b8;color:white;padding:1px 6px;border-radius:4px'>אחר</span></div>",
                        unsafe_allow_html=True)
                    st.divider()
                    cl, _, cr = st.columns([3, 2, 1])
                    cl.caption(f"ייצוא **{d_name}** — תאריכים בעמודות, עובדים/נעדרים בשורות")
                    with cr:
                        if st.button(f"📤 ייצא", key=f"exp_grid_{_ns_map[d_name]}", use_container_width=True):
                            ok = _export_dept_grid(d_name, view_year_month, view_month)
                            if ok:
                                st.success(f"✅ {d_name} יוצא לגיליון!")
                            else:
                                st.error("שגיאה בייצוא")
        with sub_tabs[2]:
            st.markdown(f"#### כל בקשות ההיעדרות לחודש {hebrew_months[view_month-1]} 2026")
            st.caption("בקשות ממתינות בכל המחלקות. ניתן לאשר או לדחות ישירות.")

            # ── Admin: add absence for any employee (auto-approved) ──────────
            with st.expander("➕ הוסף היעדרות לעובד (מאושר אוטומטית)", expanded=False):
                sf_all = st.session_state.staff
                active_emps = sorted(
                    sf_all[sf_all['type'].isin(['מתמחה', 'רופא בכיר', 'מנהל מחלקה'])]
                    ['name'].astype(str).str.strip().tolist()
                )
                adm_emp = st.selectbox("עובד", active_emps, key="adm_abs_emp")
                adm_col1, adm_col2 = st.columns(2)
                with adm_col1:
                    adm_start = st.date_input("מתאריך", key="adm_abs_start",
                                              value=date(2026, view_month, 1),
                                              min_value=date(2026, 1, 1),
                                              max_value=date(2026, 12, 31))
                with adm_col2:
                    adm_end = st.date_input("עד תאריך", key="adm_abs_end",
                                            value=date(2026, view_month, 1),
                                            min_value=date(2026, 1, 1),
                                            max_value=date(2026, 12, 31))
                adm_type = st.selectbox("סוג היעדרות", ["חופש", "202", "היעדרות אחרת"], key="adm_abs_type")
                adm_note = st.text_input("הערה (אופציונלי)", key="adm_abs_note")

                if st.button("✅ הוסף היעדרות מאושרת", key="adm_abs_submit"):
                    if adm_end < adm_start:
                        st.error("תאריך סיום לפני תאריך התחלה.")
                    else:
                        # Look up employee dept
                        emp_row = sf_all[sf_all['name'].astype(str).str.strip() == adm_emp]
                        emp_dept = str(emp_row.iloc[0].get('dept', '')) if not emp_row.empty else ''

                        new_adm_row = {
                            'id':              str(uuid.uuid4()),
                            'employee':        adm_emp,
                            'start_date':      adm_start.strftime('%Y-%m-%d'),
                            'end_date':        adm_end.strftime('%Y-%m-%d'),
                            'type':            adm_type,
                            'status':          'approved',
                            'dept_at_request': emp_dept,
                            'manager_email':   '',
                            'approved_by':     str(user_name).strip(),
                            'notes':           adm_note.strip(),
                            'created_at':      datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'responded_at':    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        }
                        new_adm_df = pd.concat(
                            [st.session_state.absence_requests, pd.DataFrame([new_adm_row])],
                            ignore_index=True
                        )
                        st.session_state.absence_requests = new_adm_df
                        save_to_db("absence_requests", new_adm_df)

                        # Also stamp work_schedule_daily for each day in range
                        dr_df = st.session_state.dept_rotation
                        emp_dept_wsd = emp_dept
                        if not dr_df.empty and 'employee' in dr_df.columns:
                            dr_match = dr_df[
                                (dr_df['employee'].astype(str).str.strip() == adm_emp) &
                                (dr_df['year_month'].astype(str) == f"2026-{adm_start.month:02d}")
                            ]
                            if not dr_match.empty:
                                emp_dept_wsd = str(dr_match.iloc[0].get('daily_dept', emp_dept))
                        d = adm_start
                        while d <= adm_end:
                            _wsd_upsert(d.strftime('%Y-%m-%d'), adm_emp,
                                        emp_dept_wsd, adm_type, is_manual=True,
                                        note=adm_note.strip())
                            d += timedelta(days=1)

                        st.session_state['show_adm_abs_success'] = True
                        st.rerun()

            if st.session_state.pop('show_adm_abs_success', False):
                st.success("✅ היעדרות נוספה ואושרה בהצלחה!")
            ar_all = st.session_state.absence_requests.copy()
            if ar_all.empty or 'status' not in ar_all.columns:
                st.info("אין בקשות במערכת.")
            else:
                ar_all['start_date'] = ar_all['start_date'].astype(str)
                ar_all['end_date']   = ar_all['end_date'].astype(str)
                ar_all['status']     = ar_all['status'].astype(str).str.lower()
                # Show ALL pending requests regardless of month
                pending = ar_all[ar_all['status'] == 'pending'].sort_values('start_date')
                if pending.empty:
                    st.success("אין בקשות ממתינות ✅")
                else:
                    st.caption(f"📋 {len(pending)} בקשות ממתינות")
                    for idx, row in pending.iterrows():
                        with st.container(border=True):
                            cc1, cc2, cc3, cc4, cc5, cc6 = st.columns([2, 2, 2, 2, 1, 1])
                            cc1.markdown(f"**{row.get('employee', '—')}**")
                            cc2.write(f"{row['start_date']} – {row['end_date']}")
                            cc3.write(row.get('type', '—'))
                            cc4.write(row.get('dept_at_request', '—'))
                            req_id = str(row.get('id', idx))
                            if cc5.button("✅", key=f"adm_ap_{req_id}", use_container_width=True):
                                _approve_request(req_id, str(user_name).strip())
                                st.rerun()
                            if cc6.button("❌", key=f"adm_rj_{req_id}", use_container_width=True):
                                _reject_request(req_id, str(user_name).strip())
                                st.rerun()
                            if row.get('notes'):
                                st.caption(f"💬 {row['notes']}")
        with sub_tabs[3]:
            st.markdown(f"#### יצירת סידור יומי לחודש {hebrew_months[view_month-1]} 2026")
            st.markdown("""
            **לוגיקת יצירה:**
            - לכל עובד ב-`dept_rotation` של החודש → לכל יום בחודש (כולל שישי/שבת)
            - **קדימות 1**: בקשת היעדרות מאושרת מכסה את היום? → status = סוג ההיעדרות
            - **קדימות 2**: עשה תורנות לילה ביום הקודם? → status = "אחרי תורנות"
            - אחרת → status = "עובד"
            - **שורות עם `is_manual=True` לא נדרסות** (עריכות ידניות שמורות)
            """)

            col_g1, col_g2 = st.columns([1, 2])
            with col_g1:
                go = st.button(f"⚡ צור סידור לחודש {hebrew_months[view_month-1]}",
                               key="generate_sched", use_container_width=True)
            with col_g2:
                cur_count = 0
                if not st.session_state.work_schedule_daily.empty:
                    cur_count = st.session_state.work_schedule_daily['date'].astype(str).str.startswith(view_year_month).sum()
                if cur_count:
                    st.caption(f"📊 כרגע: {cur_count} שורות קיימות לחודש זה")

            if go:
                with st.spinner("מייצר סידור..."):
                    result = _generate_work_schedule(view_year_month, view_month)
                if result.get('error'):
                    st.error(result['error'])
                else:
                    st.success(
                        f"✅ סידור נוצר! "
                        f"{result['written']} שורות חדשות/מעודכנות, "
                        f"{result['kept_manual']} שורות ידניות שמורות, "
                        f"{result['employees']} עובדים, "
                        f"{result['absences_applied']} ימי היעדרות הוחלו, "
                        f"{result['post_shifts']} ימי 'אחרי תורנות' חושבו."
                    )
        with sub_tabs[4]:
            st.markdown(f"#### ייצוא סידור יומי — {hebrew_months[view_month-1]} 2026")
            st.caption("📥 Excel — הורדה מקומית | 📤 ייצא לקובץ הראשי — לשונית ב-Shifts_scheduler | 🆕 גיליון חדש — קובץ Google Sheets נפרד")
            st.divider()
            for d_name in DAILY_DEPTS_ALL:
                st.markdown(f"**{d_name}**")
                _render_export_buttons(d_name, view_year_month, view_month,
                                       f"adm_exp_{d_name.replace(' ','_').replace(chr(39),'').replace(chr(34),'')}", user_name)
                st.markdown("")
            st.divider()
            if st.button(f"📤 ייצא את כל {len(DAILY_DEPTS_ALL)} המחלקות לקובץ הראשי",
                         key="exp_main_all", use_container_width=False):
                results = []
                for d_name in DAILY_DEPTS_ALL:
                    ok = _export_dept_grid(d_name, view_year_month, view_month)
                    results.append((d_name, ok))
                ok_count = sum(1 for _, o in results if o)
                if ok_count == len(DAILY_DEPTS_ALL):
                    st.success(f"✅ כל {ok_count} המחלקות יוצאו!")
                elif ok_count == 0:
                    st.error("שגיאה בייצוא")
                else:
                    fail = [n for n, o in results if not o]
                    st.warning(f"יוצאו {ok_count}/{len(DAILY_DEPTS_ALL)}. נכשלו: {', '.join(fail)}")

    # ── סידור יומי (אדמין) — same view as מנהל מחלקה but for any dept of choice ──
    if selected_nav == 'סידור יומי':
        st.subheader("🗓️ סידור יומי — תצוגת מנהל/ת מחלקה (אדמין)")
        st.caption("בחר מחלקה לראות אותה כפי שמנהל המחלקה רואה (לוח מחלקה + בקשות ממתינות).")

        adm_hebrew_months = ["ינואר","פברואר","מרץ","אפריל","מאי","יוני","יולי",
                             "אוגוסט","ספטמבר","אוקטובר","נובמבר","דצמבר"]
        sel_dept_admin = st.selectbox("מחלקה לתצוגה:", DAILY_DEPTS_ALL, key="adm_sy_dept")

        st.caption(f"חודש פעיל: **{adm_hebrew_months[daily_active_month_int-1]} 2026**")
        adm_y_m = f"2026-{daily_active_month_int:02d}"

        adm_mgr_tabs = st.tabs(["לוח מחלקה", "בקשות ממתינות"])
        with adm_mgr_tabs[0]:
            st.markdown(f"#### לוח {sel_dept_admin}")
            _render_dept_grid(sel_dept_admin, adm_y_m, daily_active_month_int,
                              "adm_mgrview")
            st.divider()
            _render_export_buttons(sel_dept_admin, adm_y_m, daily_active_month_int,
                                   "adm_mgrview", user_name)

        with adm_mgr_tabs[1]:
            st.markdown(f"#### בקשות ממתינות — {sel_dept_admin}")
            ar_admgr = st.session_state.absence_requests.copy()
            if ar_admgr.empty or 'status' not in ar_admgr.columns:
                st.info("אין בקשות במערכת.")
            else:
                ar_admgr['status']          = ar_admgr['status'].astype(str).str.lower()
                ar_admgr['dept_at_request'] = ar_admgr['dept_at_request'].astype(str)
                pen = ar_admgr[(ar_admgr['status'] == 'pending') &
                               (ar_admgr['dept_at_request'] == sel_dept_admin)]
                if pen.empty:
                    st.success("אין בקשות ממתינות במחלקה זו ✅")
                else:
                    st.caption(f"📋 {len(pen)} בקשות ממתינות")
                    for idx, row in pen.iterrows():
                        with st.container(border=True):
                            cc1, cc2, cc3, cc4, cc5 = st.columns([2, 2, 2, 1, 1])
                            cc1.markdown(f"**{row.get('employee', '—')}**")
                            cc2.write(f"{row['start_date']} – {row['end_date']}")
                            cc3.write(row.get('type', '—'))
                            req_id = str(row.get('id', idx))
                            if cc4.button("✅ אשר", key=f"admmgr_ap_{req_id}",
                                          use_container_width=True):
                                _approve_request(req_id, str(user_name).strip())
                                st.rerun()
                            if cc5.button("❌ דחה", key=f"admmgr_rj_{req_id}",
                                          use_container_width=True):
                                _reject_request(req_id, str(user_name).strip())
                                st.rerun()
                            if row.get('notes'):
                                st.caption(f"💬 {row['notes']}")


else:
    user_name = st.session_state.user_name

    # ── Night-shift constraints (existing UI) — only for roles that do night shifts ──
    if selected_nav == 'הגשת בקשות' and role in ('מתמחה', 'תורן חוץ'):
        # Display the active month name clearly
        hebrew_months = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני", "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"]
        month_name = hebrew_months[sel_month - 1]
        st.subheader(f"📋 הגשת בקשות לחודש: {month_name}")
        st.markdown("### 🌙 אילוצים לתורנויות לילה")
        
        # --- הצגת ימים מיוחדים / חגים לחודש זה ---
        if 'special_days' in st.session_state and not st.session_state.special_days.empty:
            special_days_month = []
            for _, row in st.session_state.special_days.iterrows():
                try:
                    d_obj = datetime.strptime(row['date'], '%Y-%m-%d').date()
                    if d_obj.month == sel_month and d_obj.year == 2026:
                        special_days_month.append(f"{d_obj.strftime('%d/%m/%Y')} - {row['description']}")
                except: pass
            
            if special_days_month:
                st.warning("⚠️ **שים לב לימים מיוחדים בחודש זה:**\n\n" + "\n".join([f"- {sd}" for sd in special_days_month]))
        
        # --- Pre-initialize Chip States for the entire month ---
        cal = calendar.monthcalendar(2026, sel_month)
        
        # Function to safely parse day from various date formats
        def get_day_nums(df, status_type):
            if df.empty: return []
            # Create a copy to avoid SettingWithCopy warnings
            user_rehab = df[(df['employee'] == user_name) & (df['status'] == status_type)].copy()
            
            if user_rehab.empty: return []
            
            # Robust conversion to datetime
            user_rehab['date_dt'] = pd.to_datetime(user_rehab['date'], errors='coerce')
            
            # Filter for valid dates in the selected month/year
            # sel_month is integer (e.g., 2)
            valid_dates = user_rehab[
                (user_rehab['date_dt'].dt.month == sel_month) & 
                (user_rehab['date_dt'].dt.year == 2026)
            ]
            
            return valid_dates['date_dt'].dt.day.tolist()

        default_day_nums = get_day_nums(st.session_state.requests, "אילוץ")
        default_wish_nums = get_day_nums(st.session_state.requests, "בקשה")
        
        default_dates  = [date(2026, sel_month, d) for d in default_day_nums]
        default_wishes = [date(2026, sel_month, d) for d in default_wish_nums]

        # --- הצגת אילוצים ובקשות קיימים ---
        existing_constraints = st.session_state.requests[(st.session_state.requests['employee'] == user_name) & (st.session_state.requests['status'] == "אילוץ")].copy()
        existing_wishes_all = st.session_state.requests[(st.session_state.requests['employee'] == user_name) & (st.session_state.requests['status'] == "בקשה")].copy()
        
        # סינון להצגה רק של החודש הפעיל הנבחר ב-UI (sel_month)
        if not existing_constraints.empty:
            existing_constraints['date_dt'] = pd.to_datetime(existing_constraints['date'], errors='coerce')
            existing_constraints = existing_constraints[(existing_constraints['date_dt'].dt.month == sel_month) & (existing_constraints['date_dt'].dt.year == 2026)]

        if not existing_wishes_all.empty:
            existing_wishes_all['date_dt'] = pd.to_datetime(existing_wishes_all['date'], errors='coerce')
            existing_wishes_all = existing_wishes_all[(existing_wishes_all['date_dt'].dt.month == sel_month) & (existing_wishes_all['date_dt'].dt.year == 2026)]
        
        if not existing_constraints.empty or not existing_wishes_all.empty:
            msg = ""
            if not existing_constraints.empty:
                msg += f"📅 **חסימות ({len(existing_constraints)}):** " + ", ".join([r['date'] for _, r in existing_constraints.iterrows()]) + "\n\n"
            if not existing_wishes_all.empty:
                msg += f"⭐ **בקשות ({len(existing_wishes_all)}):** " + ", ".join([r['date'] for _, r in existing_wishes_all.iterrows()])
            st.info(msg)
        else:
            st.info("עדיין לא הגשת אילוצים או בקשות לחודש זה.")
        # ----------------------------

        st.divider()
        cal_sd = st.session_state.get('special_days')
        if isinstance(cal_sd, pd.DataFrame) and cal_sd.empty:
            cal_sd = None
        constraint_days, wish_days = render_modern_calendar(
            2026, sel_month,
            default_day_nums, default_wish_nums,
            special_days_df=cal_sd,
            key_prefix='user_cal',
            show_validation=(st.session_state.user_role == 'מתמחה')
        )
        selected_from_grid = [date(2026, sel_month, d) for d in constraint_days]
        selected_wishes    = [date(2026, sel_month, d) for d in wish_days]
        
        # -----------------------------------
        st.divider()
        
        if st.button("עדכן אילוצים ובקשות"):
            # --- ולידציה (חוקים) ---
            validation_passed = True
            errors = []
            
            if len(selected_wishes) > 2:
                errors.append("שגיאה: ניתן לבחור עד 2 בקשות חיוביות (⭐) בלבד.")
            
            # בדיקה שלא בחר באותו יום גם אילוץ וגם בקשה
            overlap = set(selected_from_grid).intersection(set(selected_wishes))
            if overlap:
                errors.append(f"שגיאה: בחרת באותו יום ({list(overlap)[0].strftime('%d/%m')}) גם אילוץ וגם בקשה. נא בחר רק אחד.")

            if st.session_state.user_role == 'מתמחה': # רק למתמחים
                # חישוב ימים פנויים
                num_days = calendar.monthrange(2026, sel_month)[1]
                month_days = [date(2026, sel_month, d) for d in range(1, num_days+1)]
                total_thursdays = len([d for d in month_days if d.weekday() == 3])
                total_weekends = len([d for d in month_days if d.weekday() in [4, 5]]) # שישי ושבת
                
                blocked_thursdays = len([d for d in selected_from_grid if d.weekday() == 3])
                blocked_weekends = len([d for d in selected_from_grid if d.weekday() in [4, 5]])
                
                avail_thursdays = total_thursdays - blocked_thursdays
                avail_weekends = total_weekends - blocked_weekends
                
                # Removed bug: errors = [] was here wiping previous validation errors
                if avail_thursdays < 2:
                    errors.append(f"נותר רק יום חמישי אחד פנוי (או פחות). חובה להשאיר לפחות 2 ימי חמישי פנויים.")
                if avail_weekends < 4:
                    errors.append(f"נותרו רק {avail_weekends} ימי סוף שבוע פנויים. חובה להשאיר לפחות 4 (שישי/שבת).")
                
                if errors:
                    validation_passed = False
                    for e in errors: st.error(e)
            
            if validation_passed or st.session_state.user_role == 'מנהל/ת':           
                st.session_state['selected_dates_for_update'] = selected_from_grid
                st.session_state['selected_wishes_for_update'] = selected_wishes
                st.session_state['confirm_request_save'] = True

        if st.session_state.get('confirm_request_save', False):
            selected = st.session_state.get('selected_dates_for_update', [])
            wishes = st.session_state.get('selected_wishes_for_update', [])
            
             # חישוב אילו ימים נוספו ואילו הוסרו (אילוצים)
            added = set(selected) - set(default_dates)
            removed = set(default_dates) - set(selected)
            
            # חישוב שינויים בבקשות
            added_wishes = set(wishes) - set(default_wishes)
            removed_wishes = set(default_wishes) - set(wishes)
            
            changes_msg = ""
            if added: changes_msg += f"➕ **נוספו לחסימה:** {', '.join([d.strftime('%d/%m/%Y') for d in added])}\n\n"
            if removed: changes_msg += f"➖ **הוסרו מחסימה:** {', '.join([d.strftime('%d/%m/%Y') for d in removed])}\n\n"
            if added_wishes: changes_msg += f"⭐ **נוספו לבקשה:** {', '.join([d.strftime('%d/%m/%Y') for d in added_wishes])}\n\n"
            if removed_wishes: changes_msg += f"⭐❌ **הוסרו מבקשה:** {', '.join([d.strftime('%d/%m/%Y') for d in removed_wishes])}\n\n"
            
            if not changes_msg and not (not default_dates and not selected):
                 st.info("לא ביצעת שינויים.")
                 st.session_state['confirm_request_save'] = False
            else:
                if not selected and default_dates:
                     st.warning("⚠️ **האם אתה בטוח?** אתה עומד להסיר את **כל** החסימות שלך.")
                elif changes_msg:
                     st.info(f"⚠️ **האם אתה בטוח שברצונך לעדכן?**\n\n{changes_msg}")
                else: 
                     # מקרה קצה של שמירה ראשונית ריקה או ללא שינוי
                     pass

                # Vertical Stack Design for Mobile Robustness
                if st.button("✅ כן, עדכן", type="primary", use_container_width=True):
                    # משיכת נתונים חיים מהגיליון (עוקף cache למניעת דריסה הדדית בין משתמשים)
                    live = _fetch_live("requests")
                    base = live if not live.empty else st.session_state.requests

                    # הסרת כל האילוצים והבקשות הקודמים של המשתמש לחודש זה
                    current_month_prefix = f"2026-{sel_month:02d}"
                    mask_keep = ~((base['employee'].astype(str).str.strip() == str(user_name).strip()) &
                                  (base['date'].astype(str).str.startswith(current_month_prefix)))
                    base = base[mask_keep]

                    # הוספת הרשימה החדשה והמעודכנת
                    new_rows = []
                    if selected:
                        new_rows += [{'employee': user_name, 'date': str(d), 'status': "אילוץ"} for d in selected]
                    if wishes:
                        new_rows += [{'employee': user_name, 'date': str(d), 'status': "בקשה"} for d in wishes]

                    merged = pd.concat([base, pd.DataFrame(new_rows)], ignore_index=True) if new_rows else base
                    save_to_db("requests", merged)
                    _log_async('constraint_submit', str(len(selected)), str(len(wishes)))
                    st.session_state.requests = merged
                    _fetch_sheet_data_silently.clear()
                    st.session_state['confirm_request_save'] = False
                    st.session_state.pop(f"user_cal_init_{sel_month}", None)
                    st.session_state['show_update_success'] = True
                    st.rerun()

                if st.button("❌ בטל", use_container_width=True):
                    st.session_state['confirm_request_save'] = False
                    st.rerun()

    if st.session_state.get('show_update_success'):
        st.success("✅ האילוצים עודכנו בהצלחה!")
        st.session_state['show_update_success'] = False

    # ── Day-absence section (Phase 3) — for מתמחה / רופא בכיר ─────────────────────────
    if selected_nav == 'הגשת בקשות' and role in ('מתמחה', 'רופא בכיר', 'מנהל מחלקה'):
        hebrew_months_da = ["ינואר","פברואר","מרץ","אפריל","מאי","יוני","יולי",
                            "אוגוסט","ספטמבר","אוקטובר","נובמבר","דצמבר"]

        # מנהל/ת מחלקה / רופא/ה בכיר/ה — no night UI above, so render page header
        if role in ('רופא בכיר', 'מנהל מחלקה'):
            st.subheader(f"📋 הגשת בקשות לחודש: {hebrew_months_da[daily_active_month_int - 1]}")
            if role == 'מנהל מחלקה':
                st.info("💡 כמנהל/ת מחלקה בקשותיך מאושרות אוטומטית ומשתקפות מיד בלוח.")
        else:
            st.divider()

        st.markdown("### ☀️ היעדרות מעבודה יומית")

        # Status banner: open/closed
        if not daily_requests_open:
            st.warning(f"🔒 הגשות לחודש {hebrew_months_da[daily_active_month_int - 1]} נסגרו על ידי המנהל.")

        # Use the daily_active_month for this section (separate from sel_month/active_month)
        da_year_month = f"2026-{daily_active_month_int:02d}"
        da_num_days = calendar.monthrange(2026, daily_active_month_int)[1]
        da_first_wd = (date(2026, daily_active_month_int, 1).weekday() + 1) % 7  # Sun=0

        # Selection state — namespaced per month
        sel_start_key = f"dayabs_sel_start_{daily_active_month_int}"
        sel_end_key   = f"dayabs_sel_end_{daily_active_month_int}"
        if sel_start_key not in st.session_state: st.session_state[sel_start_key] = None
        if sel_end_key   not in st.session_state: st.session_state[sel_end_key]   = None

        # Pre-color sets from absence_requests for this user × this month
        ar_df = st.session_state.absence_requests.copy()
        approved_vac_days, approved_202_days, pending_days = set(), set(), set()
        if not ar_df.empty and 'employee' in ar_df.columns:
            ar_df['employee'] = ar_df['employee'].astype(str).str.strip()
            user_n = str(user_name).strip()
            mine = ar_df[ar_df['employee'] == user_n]
            for _, r in mine.iterrows():
                try:
                    sd = datetime.strptime(str(r['start_date']), '%Y-%m-%d').date()
                    ed = datetime.strptime(str(r['end_date']),   '%Y-%m-%d').date()
                except Exception:
                    continue
                # Only include days that fall within the displayed month
                d_iter = sd
                while d_iter <= ed:
                    if d_iter.month == daily_active_month_int and d_iter.year == 2026:
                        status = str(r.get('status', '')).strip().lower()
                        atype = str(r.get('type', '')).strip()
                        if status == 'approved':
                            if atype == '202':
                                approved_202_days.add(d_iter.day)
                            else:  # חופש / חופש עתידי / היעדרות אחרת all show as 🔵
                                approved_vac_days.add(d_iter.day)
                        elif status == 'pending':
                            pending_days.add(d_iter.day)
                    d_iter = d_iter + timedelta(days=1)

        # ── Night-shift + post-shift days for this user × this month ──
        night_shift_days, post_shift_days = set(), set()
        sched_df_da = st.session_state.schedule.copy()
        if not sched_df_da.empty and 'employee' in sched_df_da.columns:
            sched_df_da['employee'] = sched_df_da['employee'].astype(str).str.strip()
            sched_df_da['date']     = sched_df_da['date'].astype(str)
            sched_df_da['dept']     = sched_df_da['dept'].astype(str)
            user_shifts = sched_df_da[
                (sched_df_da['employee'] == str(user_name).strip()) &
                (~sched_df_da['dept'].str.contains('שישי בוקר', na=False))
            ]
            for _, sr in user_shifts.iterrows():
                try:
                    sd = datetime.strptime(sr['date'], '%Y-%m-%d').date()
                except Exception:
                    continue
                if sd.month == daily_active_month_int and sd.year == 2026:
                    night_shift_days.add(sd.day)
                # Post-shift = day AFTER the shift
                next_d = sd + timedelta(days=1)
                if next_d.month == daily_active_month_int and next_d.year == 2026:
                    post_shift_days.add(next_d.day)

        # Build calendar grid (Hebrew week: Sun..Sat)
        HEB_WEEK = ["א", "ב", "ג", "ד", "ה", "ו", "ש"]
        with st.container(border=True):
            # Header row
            cols_h = st.columns(7)
            for i, h in enumerate(HEB_WEEK):
                cols_h[i].markdown(f"<div class='dayabs-hdr'>{h}</div>", unsafe_allow_html=True)

            # Build 6 weeks max
            grid = [None] * da_first_wd + list(range(1, da_num_days + 1))
            while len(grid) % 7:
                grid.append(None)

            # Compute current selection range
            ss = st.session_state[sel_start_key]
            se = st.session_state[sel_end_key]
            in_range = set(range(min(ss, se), max(ss, se) + 1)) if ss and se else set()

            for wi in range(0, len(grid), 7):
                week = grid[wi:wi + 7]
                cols = st.columns(7)
                for ci, day in enumerate(week):
                    with cols[ci]:
                        if day is None:
                            st.markdown("<div class='dayabs-empty'></div>", unsafe_allow_html=True)
                            continue
                        # Pre-colored fixed states (non-clickable)
                        # Highest priority: night shifts + post-shift (informational; not clickable)
                        if day in night_shift_days:
                            st.markdown(f"<div class='dayabs-night'>🌙 {day}</div>",
                                        unsafe_allow_html=True)
                        elif day in post_shift_days:
                            st.markdown(f"<div class='dayabs-post'>🔶 {day}</div>",
                                        unsafe_allow_html=True)
                        elif day in approved_vac_days:
                            st.markdown(f"<div class='dayabs-vac'>🔵 {day}</div>",
                                        unsafe_allow_html=True)
                        elif day in approved_202_days:
                            st.markdown(f"<div class='dayabs-202'>🟡 {day}</div>",
                                        unsafe_allow_html=True)
                        elif day in pending_days:
                            st.markdown(f"<div class='dayabs-pend'>🔘 {day}</div>",
                                        unsafe_allow_html=True)
                        # Selecting start
                        elif day == ss and not se:
                            if st.button(f"▶{day}", key=f"dayabs_start_{day}",
                                         use_container_width=True):
                                st.session_state[sel_start_key] = None
                                st.rerun()
                        # In selected range
                        elif day in in_range:
                            if st.button(f"✓{day}", key=f"dayabs_range_{day}",
                                         use_container_width=True):
                                st.session_state[sel_start_key] = day
                                st.session_state[sel_end_key]   = None
                                st.rerun()
                        # Free / clickable
                        else:
                            if st.button(str(day), key=f"dayabs_free_{day}",
                                         use_container_width=True):
                                if st.session_state[sel_start_key] is None:
                                    st.session_state[sel_start_key] = day
                                elif (st.session_state[sel_end_key] is None
                                      and day != st.session_state[sel_start_key]):
                                    st.session_state[sel_end_key] = day
                                else:
                                    st.session_state[sel_start_key] = day
                                    st.session_state[sel_end_key]   = None
                                st.rerun()

            # Legend
            st.markdown(
                "<div style='direction:rtl;font-size:0.77rem;color:#64748b;"
                "margin:8px 0 0 0;line-height:2'>"
                "🌙 תורנות לילה &nbsp;|&nbsp; 🔶 אחרי תורנות &nbsp;|&nbsp; "
                "🔵 חופש מאושר &nbsp;|&nbsp; 🟡 202 מאושר &nbsp;|&nbsp; 🔘 בקשה ממתינה &nbsp;|&nbsp; "
                "<span style='border:1px solid #e2e8f0;padding:1px 8px;border-radius:5px;"
                "background:white;color:#334155'>27</span> פנוי (לחיצה לבחירה)"
                "</div>",
                unsafe_allow_html=True)

            st.divider()

            # Submission row
            ss = st.session_state[sel_start_key]
            se = st.session_state[sel_end_key]
            if ss and se:
                lo, hi = min(ss, se), max(ss, se)
                c1, c2, c3, c4 = st.columns([2, 2, 3, 2])
                with c1:
                    st.markdown(f"**נבחר:** {lo:02d}/{daily_active_month_int:02d} – {hi:02d}/{daily_active_month_int:02d}")
                with c2:
                    abs_type_disp = st.selectbox(
                        "סוג:", ["חופש", "202"],
                        label_visibility="collapsed",
                        key=f"dayabs_type_{daily_active_month_int}"
                    )
                with c3:
                    abs_note = st.text_input(
                        "הערה:", placeholder="הערה (רשות)...",
                        label_visibility="collapsed",
                        key=f"dayabs_note_{daily_active_month_int}"
                    )
                with c4:
                    # מנהל מחלקה bypasses the open/close gate (auto-approved)
                    can_submit = daily_requests_open or role == 'מנהל מחלקה'
                    if st.button("✅ הגש בקשה", use_container_width=True,
                                 key=f"dayabs_submit_{daily_active_month_int}",
                                 disabled=not can_submit):
                        # Lookup user's daily dept for this month
                        dr = st.session_state.dept_rotation
                        dept_at_req = ""
                        manager_email = ""
                        if not dr.empty and 'employee' in dr.columns:
                            my_rot = dr[
                                (dr['employee'].astype(str).str.strip() == str(user_name).strip()) &
                                (dr['year_month'].astype(str) == da_year_month)
                            ]
                            if not my_rot.empty:
                                dept_at_req = str(my_rot.iloc[0].get('daily_dept', '')).strip()
                        # Find manager email by manage_depts
                        if dept_at_req:
                            staff_df_local = st.session_state.staff
                            for _, sr in staff_df_local.iterrows():
                                if str(sr.get('type', '')).strip() != 'מנהל מחלקה':
                                    continue
                                mdepts = _parse_manage_depts(sr.get('manage_depts', ''))
                                if dept_at_req in mdepts:
                                    manager_email = str(sr.get('email', '')).strip()
                                    break

                        # מנהל מחלקה: auto-approved immediately
                        _is_mgr_req   = (role == 'מנהל מחלקה')
                        _req_status   = 'approved' if _is_mgr_req else 'pending'
                        _approved_by  = str(user_name).strip() if _is_mgr_req else ''
                        _responded_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S') if _is_mgr_req else ''

                        # Build new row
                        new_row = {
                            'id': str(uuid.uuid4()),
                            'employee': str(user_name).strip(),
                            'start_date': f"2026-{daily_active_month_int:02d}-{lo:02d}",
                            'end_date':   f"2026-{daily_active_month_int:02d}-{hi:02d}",
                            'type': abs_type_disp,
                            'status': _req_status,
                            'dept_at_request': dept_at_req,
                            'manager_email': manager_email,
                            'approved_by': _approved_by,
                            'notes': abs_note.strip(),
                            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'responded_at': _responded_at,
                        }
                        new_df = pd.concat(
                            [st.session_state.absence_requests, pd.DataFrame([new_row])],
                            ignore_index=True
                        )
                        st.session_state.absence_requests = new_df
                        save_to_db("absence_requests", new_df)

                        if _is_mgr_req:
                            # Auto-approved: write directly to work_schedule_daily
                            _mgr_dept = dept_at_req
                            if not _mgr_dept:
                                _sf  = st.session_state.staff
                                _srf = _sf[_sf['name'].astype(str).str.strip() == str(user_name).strip()]
                                if not _srf.empty:
                                    _mdl = _parse_manage_depts(_srf.iloc[0].get('manage_depts', ''))
                                    _mgr_dept = _mdl[0] if _mdl else ''
                            if _mgr_dept:
                                _di = lo
                                while _di <= hi:
                                    _ds = f"2026-{daily_active_month_int:02d}-{_di:02d}"
                                    _wsd_upsert(_ds, str(user_name).strip(), _mgr_dept,
                                                abs_type_disp, is_manual=True,
                                                note=abs_note.strip())
                                    _di += 1
                            st.success(f"✅ {abs_type_disp} {lo:02d}/{daily_active_month_int:02d}–"
                                       f"{hi:02d}/{daily_active_month_int:02d} אושר אוטומטית ועודכן בלוח!")
                        else:
                            # Regular employee: email the manager
                            if manager_email:
                                send_notification_email(
                                    manager_email,
                                    f"בקשת היעדרות חדשה: {user_name}",
                                    f"<div dir='rtl'><p>שלום,</p>"
                                    f"<p>עובד <b>{user_name}</b> ({dept_at_req}) הגיש/ה בקשת היעדרות:</p>"
                                    f"<ul><li>סוג: {abs_type_disp}</li>"
                                    f"<li>תאריכים: {new_row['start_date']} – {new_row['end_date']}</li>"
                                    f"<li>הערה: {abs_note or '—'}</li></ul>"
                                    f"<p>נא להיכנס למערכת לאישור או דחיה.</p></div>"
                                )
                            st.success(f"✅ בקשת {abs_type_disp} ל-{lo:02d}/{daily_active_month_int:02d}–"
                                       f"{hi:02d}/{daily_active_month_int:02d} נשלחה!")
                        st.session_state[sel_start_key] = None
                        st.session_state[sel_end_key]   = None
                        st.rerun()

                if st.button("✖ בטל בחירה", key=f"dayabs_cancel_{daily_active_month_int}"):
                    st.session_state[sel_start_key] = None
                    st.session_state[sel_end_key]   = None
                    st.rerun()
            elif ss:
                st.info(f"📍 נבחר: {ss:02d}/{daily_active_month_int:02d} — כעת לחץ על יום הסיום")
            else:
                st.caption("💡 לחץ על יום פנוי בלוח לבחירת תאריך התחלה. "
                           "חופש עתידי שאושר מראש מופיע בכחול בלוח.")

        # ── History table ──
        st.divider()
        st.markdown("#### 📋 היסטוריית בקשות")
        if ar_df.empty or 'employee' not in ar_df.columns:
            st.caption("אין בקשות עדיין.")
        else:
            mine = ar_df[ar_df['employee'].astype(str).str.strip() == str(user_name).strip()]
            if mine.empty:
                st.caption("אין בקשות עדיין.")
            else:
                show_cols = ['start_date', 'end_date', 'type', 'status', 'approved_by', 'notes']
                disp = mine[[c for c in show_cols if c in mine.columns]].copy()
                # Translate status for display
                disp['status'] = disp['status'].astype(str).str.lower().map({
                    'pending':  '⏳ ממתין',
                    'approved': '✅ אושר',
                    'rejected': '❌ נדחה',
                }).fillna(disp['status'])
                disp = disp.rename(columns={
                    'start_date': 'תאריך התחלה',
                    'end_date':   'תאריך סיום',
                    'type':       'סוג',
                    'status':     'סטטוס',
                    'approved_by': 'מאשר',
                    'notes':      'הערה',
                })
                st.dataframe(disp, use_container_width=True, hide_index=True)

        # ── הגשת חופש עתידי (תאריך מרוחק) ─────────────────────────
        st.divider()
        with st.expander("📅 הגשת חופש עתידי (לתאריך מרוחק / חודש אחר)", expanded=False):
            st.caption("לבקשת היעדרות בחודש שאינו פתוח להגשה. דורש אישור מנהל מראש. לא תלוי במצב פתח/סגור של החודש הנוכחי.")
            fc1, fc2, fc3 = st.columns([2, 2, 2])
            with fc1:
                fut_start = st.date_input("מתאריך:",
                                          value=date.today() + timedelta(days=30),
                                          min_value=date.today(),
                                          key="fut_abs_start")
            with fc2:
                fut_end = st.date_input("עד תאריך:",
                                        value=date.today() + timedelta(days=30),
                                        min_value=date.today(),
                                        key="fut_abs_end")
            with fc3:
                fut_type = st.selectbox("סוג:",
                                        ["חופש עתידי", "חופש", "202", "היעדרות אחרת"],
                                        key="fut_abs_type")
            fut_note = st.text_input("הערה (רשות):", key="fut_abs_note")

            if st.button("✅ שלח בקשה לחופש עתידי", key="fut_abs_submit"):
                if fut_end < fut_start:
                    st.error("תאריך הסיום חייב להיות שווה או אחרי תאריך ההתחלה.")
                else:
                    fut_year_month = fut_start.strftime("%Y-%m")
                    # Lookup user's daily dept for that future month
                    dr = st.session_state.dept_rotation
                    fut_dept = ""
                    fut_mgr_email = ""
                    if not dr.empty and 'employee' in dr.columns:
                        my_rot = dr[
                            (dr['employee'].astype(str).str.strip() == str(user_name).strip()) &
                            (dr['year_month'].astype(str) == fut_year_month)
                        ]
                        if not my_rot.empty:
                            fut_dept = str(my_rot.iloc[0].get('daily_dept', '')).strip()
                    if fut_dept:
                        for _, sr in st.session_state.staff.iterrows():
                            if str(sr.get('type', '')).strip() != 'מנהל מחלקה':
                                continue
                            mdepts = _parse_manage_depts(sr.get('manage_depts', ''))
                            if fut_dept in mdepts:
                                fut_mgr_email = str(sr.get('email', '')).strip()
                                break
                    new_fut_row = {
                        'id': str(uuid.uuid4()),
                        'employee': str(user_name).strip(),
                        'start_date': fut_start.strftime('%Y-%m-%d'),
                        'end_date':   fut_end.strftime('%Y-%m-%d'),
                        'type': fut_type,
                        'status': 'pending',
                        'dept_at_request': fut_dept,
                        'manager_email': fut_mgr_email,
                        'approved_by': '',
                        'notes': fut_note.strip(),
                        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'responded_at': '',
                    }
                    new_fut_df = pd.concat(
                        [st.session_state.absence_requests, pd.DataFrame([new_fut_row])],
                        ignore_index=True
                    )
                    st.session_state.absence_requests = new_fut_df
                    save_to_db("absence_requests", new_fut_df)

                    if fut_mgr_email:
                        send_notification_email(
                            fut_mgr_email,
                            f"בקשת חופש עתידי: {user_name}",
                            f"<div dir='rtl'><p>שלום,</p>"
                            f"<p>עובד <b>{user_name}</b> ({fut_dept or '—'}) הגיש בקשת חופש עתידי:</p>"
                            f"<ul><li>סוג: {fut_type}</li>"
                            f"<li>תאריכים: {new_fut_row['start_date']} – {new_fut_row['end_date']}</li>"
                            f"<li>הערה: {fut_note or '—'}</li></ul>"
                            f"<p>נא להיכנס למערכת לאישור או דחיה.</p></div>"
                        )
                    if not fut_dept:
                        st.warning("⚠️ לא נמצא שיבוץ מחלקה לחודש זה — הבקשה תועבר לכל מנהלי המחלקות.")
                    st.success(f"✅ בקשת חופש עתידי ל-{fut_start} – {fut_end} נשלחה!")
                    st.rerun()

    if selected_nav == 'סידור תורנויות':
        draw_calendar_view(2026, sel_month, "עובד/ת", user_name)

    # ── סידור יומי (עובדים / מנהלי מחלקה) ────────────────────────
    if selected_nav == 'סידור יומי':
        if role == "מנהל מחלקה":
            st.subheader("🗓️ סידור יומי — מנהל/ת מחלקה")
            # Look up the depts this manager controls
            staff_row = st.session_state.staff[
                st.session_state.staff['name'].astype(str).str.strip() == str(user_name).strip()
            ]
            managed_depts = []
            if not staff_row.empty:
                managed_depts = _parse_manage_depts(staff_row.iloc[0].get('manage_depts', ''))
            if not managed_depts:
                st.warning("⚠️ לא הוגדרו מחלקות בניהולך. אנא פנה למנהל המערכת.")
            else:
                st.caption(f"מחלקות בניהולך: {' | '.join(managed_depts)}")

                mgr_tabs = st.tabs(["לוח מחלקה", "בקשות ממתינות"])
                with mgr_tabs[0]:
                    hebrew_months_da = ["ינואר","פברואר","מרץ","אפריל","מאי","יוני","יולי",
                                        "אוגוסט","ספטמבר","אוקטובר","נובמבר","דצמבר"]
                    da_y_m = f"2026-{daily_active_month_int:02d}"
                    st.markdown(f"#### לוח מחלקה — {hebrew_months_da[daily_active_month_int-1]} 2026")
                    st.caption("עורך/ת מחלקה: לחץ/י על תא לשינוי סטטוס. שורתך מצורפת לכל מחלקה — עריכה ישירה.")
                    if len(managed_depts) > 1:
                        sub_dept_tabs = st.tabs(managed_depts)
                        for di, d_name in enumerate(managed_depts):
                            with sub_dept_tabs[di]:
                                # Compose employees: dept_rotation + the manager themselves
                                dr = st.session_state.dept_rotation
                                emps = []
                                if not dr.empty and 'employee' in dr.columns:
                                    mask = ((dr['year_month'].astype(str) == da_y_m) &
                                            (dr['daily_dept'].astype(str) == d_name))
                                    emps = dr[mask]['employee'].astype(str).str.strip().tolist()
                                if user_name not in emps:
                                    emps = [user_name] + emps
                                emps = _sort_employees_by_role(emps)
                                _render_dept_grid(d_name, da_y_m, daily_active_month_int,
                                                  f"mgr_{di}", employees=emps)
                                st.divider()
                                _render_export_buttons(d_name, da_y_m, daily_active_month_int,
                                                       f"mgr_{di}", user_name)
                    else:
                        d_name = managed_depts[0]
                        dr = st.session_state.dept_rotation
                        emps = []
                        if not dr.empty and 'employee' in dr.columns:
                            mask = ((dr['year_month'].astype(str) == da_y_m) &
                                    (dr['daily_dept'].astype(str) == d_name))
                            emps = dr[mask]['employee'].astype(str).str.strip().tolist()
                        if user_name not in emps:
                            emps = [user_name] + emps
                        emps = _sort_employees_by_role(emps)
                        _render_dept_grid(d_name, da_y_m, daily_active_month_int,
                                          "mgr_solo", employees=emps)
                        st.divider()
                        _render_export_buttons(d_name, da_y_m, daily_active_month_int,
                                               "mgr_solo", user_name)
                with mgr_tabs[1]:
                    st.markdown("#### בקשות היעדרות ממתינות")
                    ar_df_mgr = st.session_state.absence_requests.copy()
                    if ar_df_mgr.empty or 'status' not in ar_df_mgr.columns:
                        st.info("אין בקשות במערכת.")
                    else:
                        ar_df_mgr['status']           = ar_df_mgr['status'].astype(str).str.lower()
                        ar_df_mgr['dept_at_request'] = ar_df_mgr['dept_at_request'].astype(str).str.strip()
                        ar_df_mgr['employee']        = ar_df_mgr['employee'].astype(str).str.strip()

                        # Normalise dept names for comparison (strip + normalise apostrophes)
                        def _norm_dept(s):
                            return str(s).strip().replace('׳', "'").replace('’', "'")
                        norm_managed = [_norm_dept(d) for d in managed_depts]
                        dept_match = ar_df_mgr['dept_at_request'].apply(_norm_dept).isin(norm_managed)

                        # Fallback: also match by employee name — find all employees ever in
                        # managed depts across all dept_rotation rows, regardless of month
                        dr_all = st.session_state.dept_rotation
                        managed_emps = set()
                        if not dr_all.empty and 'daily_dept' in dr_all.columns:
                            for md in norm_managed:
                                emask = dr_all['daily_dept'].apply(_norm_dept) == md
                                managed_emps.update(
                                    dr_all[emask]['employee'].astype(str).str.strip().tolist()
                                )
                        emp_match = ar_df_mgr['employee'].isin(managed_emps)

                        # Combine: dept_at_request match OR employee-in-managed-dept match
                        my_pending = ar_df_mgr[
                            (ar_df_mgr['status'] == 'pending') &
                            (dept_match | emp_match)
                        ]
                        if 'start_date' in my_pending.columns:
                            my_pending = my_pending.sort_values('start_date')
                        if my_pending.empty:
                            st.success("אין בקשות ממתינות במחלקותיך ✅")
                        else:
                            st.caption(f"📋 {len(my_pending)} בקשות ממתינות")
                            for idx, row in my_pending.iterrows():
                                with st.container(border=True):
                                    cc1, cc2, cc3, cc4, cc5 = st.columns([2, 2, 2, 1, 1])
                                    cc1.markdown(f"**{row.get('employee', '—')}**")
                                    cc2.write(f"{row['start_date']} – {row['end_date']}")
                                    cc3.write(row.get('type', '—'))
                                    req_id = str(row.get('id', idx))
                                    if cc4.button("✅ אשר", key=f"mgr_ap_{req_id}",
                                                  use_container_width=True):
                                        _approve_request(req_id, str(user_name).strip())
                                        st.rerun()
                                    if cc5.button("❌ דחה", key=f"mgr_rj_{req_id}",
                                                  use_container_width=True):
                                        _reject_request(req_id, str(user_name).strip())
                                        st.rerun()
                                    if row.get('notes'):
                                        st.caption(f"💬 {row['notes']}")
        else:
            # מתמחה / רופא בכיר — read-only personal calendar
            hebrew_months_es = ["ינואר","פברואר","מרץ","אפריל","מאי","יוני","יולי",
                                "אוגוסט","ספטמבר","אוקטובר","נובמבר","דצמבר"]
            view_m = daily_active_month_int
            es_year_month = f"2026-{view_m:02d}"
            st.subheader(f"🗓️ לוח עבודה שלי — {hebrew_months_es[view_m-1]} 2026")

            # Show dept rotation
            dr = st.session_state.dept_rotation
            my_dept = "—"
            if not dr.empty and 'employee' in dr.columns:
                my_row = dr[(dr['employee'].astype(str).str.strip() == str(user_name).strip()) &
                            (dr['year_month'].astype(str) == es_year_month)]
                if not my_row.empty:
                    my_dept = str(my_row.iloc[0].get('daily_dept', '—'))
            st.caption(f"מחלקה יומית: **{my_dept}**")

            # Render the personal month calendar (read-only colored cells)
            num_days_es = calendar.monthrange(2026, view_m)[1]
            first_wd_es = (date(2026, view_m, 1).weekday() + 1) % 7
            HEB_WEEK_ES = ["א", "ב", "ג", "ד", "ה", "ו", "ש"]

            STATUS_COLOR = {
                "עובד":         ("#dcfce7", "#166534"),
                "עובד/ת":       ("#dcfce7", "#166534"),
                "חופש":         ("#dbeafe", "#1e40af"),
                "202":          ("#fef9c3", "#854d0e"),
                "אחרי תורנות":  ("#ffedd5", "#9a3412"),
                "תורנות":       ("#ede9fe", "#5b21b6"),
                "אחר":          ("#f1f5f9", "#475569"),
            }

            with st.container(border=True):
                # Header
                hdr = st.columns(7)
                for i, h in enumerate(HEB_WEEK_ES):
                    hdr[i].markdown(
                        f"<div style='text-align:center;font-weight:700;color:#475569;"
                        f"font-size:0.82rem;padding-bottom:4px'>{h}</div>",
                        unsafe_allow_html=True)

                grid = [None] * first_wd_es + list(range(1, num_days_es + 1))
                while len(grid) % 7:
                    grid.append(None)

                for wi in range(0, len(grid), 7):
                    week = grid[wi:wi+7]
                    cols = st.columns(7)
                    for ci, day in enumerate(week):
                        with cols[ci]:
                            if day is None:
                                st.markdown("<div style='padding:5px 2px;min-height:42px'></div>",
                                            unsafe_allow_html=True)
                                continue
                            date_str = f"2026-{view_m:02d}-{day:02d}"
                            _wsd_raw_es = _wsd_get_status(date_str, user_name, default=None)
                            # Re-derive non-manual "עובד" so recurring days show live
                            if _wsd_raw_es is None or (_wsd_raw_es == "עובד" and not _wsd_is_manual(date_str, user_name)):
                                status = _derive_auto_status(date_str, user_name,
                                                             daily_dept=my_dept if my_dept != "—" else None)
                            else:
                                status = _wsd_raw_es
                            bg, fg = STATUS_COLOR.get(status, ("#f8fafc", "#334155"))
                            st.markdown(
                                f"<div style='background:{bg};color:{fg};border-radius:8px;"
                                f"padding:4px 2px;text-align:center;font-size:0.72rem;"
                                f"min-height:42px;display:flex;flex-direction:column;"
                                f"align-items:center;justify-content:center;"
                                f"border:1px solid #e2e8f0'>"
                                f"<b>{day}</b><br/>{"עובד/ת" if status == "עובד" else status}</div>",
                                unsafe_allow_html=True)

            st.markdown(
                "<div style='direction:rtl;font-size:0.75rem;color:#64748b;margin-top:10px'>"
                "<span style='background:#dcfce7;color:#166534;padding:2px 8px;border-radius:4px'>עובד/ת</span> &nbsp;"
                "<span style='background:#dbeafe;color:#1e40af;padding:2px 8px;border-radius:4px'>חופש</span> &nbsp;"
                "<span style='background:#fef9c3;color:#854d0e;padding:2px 8px;border-radius:4px'>202</span> &nbsp;"
                "<span style='background:#ffedd5;color:#9a3412;padding:2px 8px;border-radius:4px'>אחרי תורנות</span> &nbsp;"
                "<span style='background:#ede9fe;color:#5b21b6;padding:2px 8px;border-radius:4px'>תורנות</span> &nbsp;"
                "<span style='background:#f1f5f9;color:#475569;padding:2px 8px;border-radius:4px'>אחר</span>"
                "</div>", unsafe_allow_html=True)

            # ── Personal schedule Excel download ────────────────────────────
            st.markdown("---")
            _pers_bytes, _pers_fname = _export_personal_schedule_excel(
                user_name, view_m,
                daily_dept=my_dept if my_dept != "—" else None)
            if _pers_bytes:
                st.download_button(
                    "📥 הורד לוח עבודה שלי (Excel)",
                    data=_pers_bytes,
                    file_name=_pers_fname,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="personal_xl_dl",
                )