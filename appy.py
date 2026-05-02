import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import calendar
import random
import io
import os
import streamlit_shadcn_ui as ui
import streamlit_antd_components as sac  # Added for Chips/Menu
import hashlib
import gspread
from streamlit_gsheets import GSheetsConnection
import time

calendar.setfirstweekday(calendar.SUNDAY)

import ui_components # Modular UI components

# --- 1. עיצוב ו-CSS ---
st.set_page_config(page_title="מערכת שיבוץ", layout="wide")
ui_components.setup_style()

import hashlib
from streamlit_gsheets import GSheetsConnection

# --- 2. ניהול מסד נתונים (Google Sheets) ---

@st.cache_data(ttl=600, show_spinner=False)
def _fetch_sheet_data_silently(worksheet_name):
    # הפונקציה הזו רצה מאחורי הקלעים ומביאה את הנתונים ללא הודעות קופצות
    gc = get_gspread_client()
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    sh = gc.open_by_url(url)
    try:
        ws = sh.worksheet(worksheet_name)
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except gspread.exceptions.WorksheetNotFound:
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

def save_to_db(worksheet_name, df, is_rtl=False):
    # שימוש ב-gspread ישירות כדי למנוע בעיות עם st-gsheets-connection
    try:
        gc = get_gspread_client()
        url = st.secrets["connections"]["gsheets"]["spreadsheet"]
        sh = gc.open_by_url(url)
        
        try:
            ws = sh.worksheet(worksheet_name)
        except:
            # הגיליון לא קיים - נוסיף אותו
            ws = sh.add_worksheet(title=worksheet_name, rows=100, cols=20)
            
        # עדכון הנתונים
        # gspread update expects list of lists including header
        # המרה של ה-DF לרשימה ועדכון
        # הערה: update של gspread דורס תאים קיימים, זה מה שאנחנו רוצים.
        
        # המרה בטוחה של נתונים כך שיהיו serializable (למשל תאריכים ל-str)
        df_str = df.astype(str)
        # החלפת nan ב-String ריק
        df_str = df_str.replace('nan', '', regex=True).replace('None', '', regex=True)
        
        data = [df_str.columns.tolist()] + df_str.values.tolist()
        
        # ניקוי הגיליון לפני כתיבה כדי למנוע שאריות במידה והטבלה החדשה קצרה יותר
        ws.clear()
        
        ws.update(range_name='A1', values=data)
        
        # טיפול ביישור מימין לשמאל (RTL) במידת הצורך
        if is_rtl:
            try:
                # שליחת בקשת batch_update לשינוי הגדרות הגיליון
                requests = [{
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": ws.id,
                            "rightToLeft": True,
                            "gridProperties": {"columnCount": 8}
                        },
                        "fields": "rightToLeft,gridProperties.columnCount"
                    }
                }]
                sh.batch_update({"requests": requests})
                
                # עיצוב בסיסי
                ws.format('A1:H1', {'textFormat': {'bold': True}, 'horizontalAlignment': 'CENTER'})
                ws.format('A2:H100', {'horizontalAlignment': 'CENTER', 'verticalAlignment': 'MIDDLE'})
            except Exception as e:
                print(f"RTL/Format warning: {e}")
                
    except Exception as e:
         st.error(f"שגיאה קריטית בשמירה לגיליון '{worksheet_name}': {e}")

def init_db():
    # בדיקה האם יש נתונים בטבלת staff, אם לא - נאתחל
    try:
        current_staff = get_db_data("staff")
        
        # אם חזר DataFrame ריק, ייתכן שהגיליון לא קיים או ריק לחלוטין
        if current_staff.empty or 'name' not in current_staff.columns:
            st.info("מאתחל נתונים ראשוניים ב-Google Sheets (פעולה חד פעמית)...")
            
            # יצירת טבלת עובדים ריקה בסיסית, ההזנה תתבצע מהמערכת
            staff_df = pd.DataFrame(columns=['name', 'type', 'dept', 'monthly_quota', 'weekend_quota', 'password', 'only_home_dept'])
            save_to_db("staff", staff_df)
            
            # אתחול שאר הטבלאות
            schedule_df = pd.DataFrame(columns=['date', 'dept', 'employee', 'is_manual', 'empty_reason'])
            save_to_db("schedule", schedule_df)
            
            requests_df = pd.DataFrame(columns=['employee', 'date', 'status'])
            save_to_db("requests", requests_df)
            
            # טבלת הגדרות (Settings) - חודש פעיל
            next_month_init = (date.today().replace(day=1) + timedelta(days=32)).month
            settings_df = pd.DataFrame([{'key': 'active_month', 'value': str(next_month_init)}])
            save_to_db("settings", settings_df)
            
            # טבלת ימים מיוחדים (Special Days) עם סוג היום
            special_days_df = pd.DataFrame(columns=['date', 'description', 'day_type'])
            save_to_db("special_days", special_days_df)
            
            st.success("הנתונים אותחלו בהצלחה! אנא רענן את העמוד.")

    except Exception as e:
        # הודעה מרוכזת אחת למשתמש
        if "Worksheet" in str(e) and "not found" in str(e):
             st.warning("שים לב: המערכת לא מצאה את הגיליונות הנדרשים (staff/schedule). אנא וודא שהם קיימים ב-Google Sheet שלך.")
        elif "Public Spreadsheet" in str(e) or "403" in str(e):
             st.error("שגיאת הרשאות: לא ניתן לכתוב לגיליון (Public Spreadsheet). \nאם אתה מריץ מקומית: וודא שקובץ הסודות קיים. \nאם בענן: וודא שהגדרת Secrets בהגדרות האפליקציה.")
        else:
             st.error(f"שגיאה באתחול: {e}")

# אתחול מסד הנתונים (רק פעם אחת)
if 'db_initialized' not in st.session_state:
    init_db()
    st.session_state.db_initialized = True

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

    st.markdown("<h1 style='text-align: center; color: #1e293b; margin-bottom: 24px; font-size: 1.8rem;'>מערכת שיבוץ תורנויות המערך הגריאטרי</h1>", unsafe_allow_html=True)
    
    username = st.text_input("שם משתמש:").strip()
    password = st.text_input("סיסמה:", type="password")
    
    st.markdown("<br>", unsafe_allow_html=True) # Spacing before button
    
    if st.button("כניסה", use_container_width=True):
        staff_df = get_db_data("staff")
        hashed_pass = hashlib.sha256(password.encode()).hexdigest()
        
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
        else:
            st.error("שם המשתמש לא נמצא במערכת")

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    login_screen()
    st.stop()
else:
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

    month_prefix = f"{year}-{sel_month:02d}"
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

        their_shifts = schedule_df[
            (schedule_df['employee'].astype(str).str.strip() == cand_name) &
            (schedule_df['date'].astype(str).str.startswith(month_prefix))
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
    return {'full': full, 'partial': partial}

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
        # Check User Agent and Width
        ua_string = st_javascript("window.navigator.userAgent", key="ua_check_1")
        ui_width = st_javascript("window.innerWidth", key="width_check_1")
        
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
        # --- List View Implementation ---
        days_names = ["א'", "ב'", "ג'", "ד'", "ה'", "ו'", "ש'"]
        
        # Collect all assignments first
        month_sched = st.session_state.schedule
        
        # Collect special days
        month_special_days = {}
        if 'special_days' in st.session_state and not st.session_state.special_days.empty:
            for _, row in st.session_state.special_days.iterrows():
                month_special_days[row['date']] = row['description']
        
        # Iterate through days linearly
        for week in cal:
             for i, day in enumerate(week):
                if day == 0: continue

                
                date_str = f"{year}-{month:02d}-{day:02d}"
                day_name = days_names[i]
                
                # Check if user has shift this day (or if admin)
                day_rows = month_sched[month_sched['date'] == date_str]
                
                # Filter for non-admin visibility
                if role != "מנהל/ת":
                    day_rows = day_rows[(day_rows['employee'] == user_name) | (day_rows['employee'] == "---")]
                
                if day_rows.empty and role != "מנהל/ת":
                    continue
                
                # Render Day Card
                with st.container():
                    formatted_date = f"{day:02d}/{month:02d}/{year}"
                    
                    # Display Special Day Header Info
                    sd_text = ""
                    if date_str in month_special_days:
                        sd_text = f" &mdash; <span style='color:#b91c1c; font-weight:bold;'>{month_special_days[date_str]}</span>"
                    
                    st.markdown(f"**{formatted_date} ({day_name})**{sd_text}", unsafe_allow_html=True)
                    
                    if day_rows.empty:
                        st.caption("אין שיבוצים")
                    else:
                        for _, row in day_rows.iterrows():
                             emp = row['employee']
                             # Clean employee name from common icons if present
                             emp_clean = emp.replace("👤", "").replace("🛡️", "").replace("🍼", "").strip()

                             dept = row['dept']

                             style = "color:#1e3a8a;" if "שיקום" in dept else "color:#ea580c;" # Indigo/Orange hints
                             # Removed icon as requested
                             st.markdown(f"<div style='margin-right:10px; {style}'>{dept}: <b>{emp_clean}</b></div>", unsafe_allow_html=True)

                    # Availability panel for list view (admin only, after all submitted)
                    if show_availability:
                        wished_here = date_wished.get(date_str, [])
                        avail       = date_availability.get(date_str, [])
                        if wished_here:
                            st.markdown(
                                f"<div style='font-size:11px; color:#854d0e;'>⭐ ביקשו: {', '.join(wished_here)}</div>",
                                unsafe_allow_html=True
                            )
                        if avail:
                            st.markdown(
                                f"<div style='font-size:11px; color:#166534;'>✅ זמינים: {', '.join(avail)}</div>",
                                unsafe_allow_html=True
                            )
                        if not wished_here and not avail:
                            st.markdown(
                                "<div style='font-size:11px; color:#991b1b;'>⚠️ אין זמינים</div>",
                                unsafe_allow_html=True
                            )
                    st.divider()

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
</style>
""", unsafe_allow_html=True)
st.title("מערכת תורנויות")

# Logout button centered under title for mobile robustness
if st.button("התנתק", key="logout_top", use_container_width=False):
    st.session_state.logged_in = False
    st.rerun()
st.markdown('</div>', unsafe_allow_html=True)

role = st.session_state.user_role
user_name = st.session_state.user_name

# שליפת החודש הפעיל — נטען מחדש בכל רינדור כדי שעדכון מנהל יגיע לכל המשתמשים מיד
try:
    st.session_state.settings = get_db_data("settings")
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

# Render Navigation Bar
selected_nav = ui_components.render_navbar(role)

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
            month_prefix = f"2026-{sel_month:02d}"
            user_shifts = sched_df[
                (sched_df['employee'].astype(str).str.strip() == str(user_name).strip()) &
                (sched_df['date'].astype(str).str.startswith(month_prefix))
            ].sort_values('date').reset_index(drop=True)

            if user_shifts.empty:
                st.info(f"אין לך משמרות משובצות בחודש {sel_month}/2026.")
            else:
                DAY_NAMES_HE = {0: 'שני', 1: 'שלישי', 2: 'רביעי', 3: 'חמישי', 4: 'שישי', 5: 'שבת', 6: 'ראשון'}

                shift_options = []
                for _, s in user_shifts.iterrows():
                    d_obj = datetime.strptime(str(s['date']), '%Y-%m-%d').date()
                    label = f"{d_obj.strftime('%d/%m')} ({DAY_NAMES_HE[d_obj.weekday()]}) — {s['dept']}"
                    shift_options.append((label, str(s['date']), s['dept']))

                labels = ["— בחר/י משמרת —"] + [opt[0] for opt in shift_options]
                sel_label = st.selectbox("המשמרות שלי החודש:", labels, key=f"swap_search_select_{sel_month}")

                if sel_label != "— בחר/י משמרת —":
                    chosen = next(o for o in shift_options if o[0] == sel_label)
                    swap_date, swap_dept = chosen[1], chosen[2]

                    with st.spinner("מחפש החלפות..."):
                        results = find_swap_candidates(
                            st.session_state.schedule,
                            st.session_state.requests,
                            st.session_state.staff,
                            user_name, swap_date, swap_dept, sel_month
                        )

                    full = results['full']
                    partial = results['partial']

                    if not full and not partial:
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
                                        existing = get_db_data("swap_requests")
                                        if existing.empty:
                                            combined = new_req
                                        else:
                                            combined = pd.concat([existing, new_req], ignore_index=True)
                                        save_to_db("swap_requests", combined)
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
                                        existing = get_db_data("swap_requests")
                                        if existing.empty:
                                            combined = new_req
                                        else:
                                            combined = pd.concat([existing, new_req], ignore_index=True)
                                        save_to_db("swap_requests", combined)
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
    if selected_nav == 'לוח שיבוץ':
        
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

        _swap_reqs = get_db_data("swap_requests")
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

                    with st.container(border=True):
                        _ca, _cb = st.columns([4, 2])
                        with _ca:
                            if _stype == 'full':
                                st.markdown(f"**✅ החלפה מלאה** | נשלח: {_created}")
                                st.write(f"**{_requester}** מוותר/ת על: **{_r_date}** ({_r_dept})")
                                st.write(f"← **{_candidate}** ייקח/תיקח אותה ויעביר/ת: **{_c_date}** ({_c_dept})")
                            else:
                                st.markdown(f"**⚠️ כיסוי חד-צדדי** | נשלח: {_created}")
                                st.write(f"**{_requester}** מבקש/ת כיסוי: **{_r_date}** ({_r_dept})")
                                st.write(f"← **{_candidate}** מוצע/ת כמחליף/ה (ללא משמרת הדדית)")

                        with _cb:
                            _col_a, _col_r = st.columns(2)
                            if _col_a.button("✅ אשר", key=f"approve_swap_{_idx}", use_container_width=True):
                                _sched = st.session_state.schedule
                                _mask_req = (_sched['date'].astype(str) == _r_date) & (_sched['dept'] == _r_dept)
                                st.session_state.schedule.loc[_mask_req, 'employee'] = _candidate
                                st.session_state.schedule.loc[_mask_req, 'is_manual'] = True
                                if _stype == 'full' and _c_date:
                                    _mask_cand = (_sched['date'].astype(str) == _c_date) & (_sched['dept'] == _c_dept)
                                    st.session_state.schedule.loc[_mask_cand, 'employee'] = _requester
                                    st.session_state.schedule.loc[_mask_cand, 'is_manual'] = True
                                save_to_db("schedule", st.session_state.schedule)
                                _swap_reqs.loc[_idx, 'status'] = 'approved'
                                save_to_db("swap_requests", _swap_reqs)
                                st.session_state['show_swap_approved'] = True
                                st.rerun()
                            if _col_r.button("❌ דחה", key=f"reject_swap_{_idx}", use_container_width=True):
                                _swap_reqs.loc[_idx, 'status'] = 'rejected'
                                save_to_db("swap_requests", _swap_reqs)
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
                    new_type = st.selectbox("תפקיד:", ["מתמחה", "תורן חוץ", "מנהל/ת"])
                with col_new2:
                    new_dept = st.selectbox("מחלקה:", ["שיקום", "פנימית גריאטרית", "כללי", "הנהלה"])
                    new_quota = st.number_input("מכסה חודשית:", min_value=0, value=6)
                    new_weekend_quota = st.number_input("מכסת סופ\"ש:", min_value=0, value=1)
                    new_only_home = st.checkbox("מוגבל למחלקה זו בלבד?", value=False)
                
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
                                'password': def_pass_hash
                            }])
                            
                            st.session_state.staff = pd.concat([st.session_state.staff, new_emp_row], ignore_index=True)
                            save_to_db("staff", st.session_state.staff)
                            st.success(f"העובד/ת {new_name} נוספ/ה בהצלחה! (סיסמה: 1234)")
                            st.rerun()
        
        st.divider()
        st.caption("שינויים בטבלה נשמרים רק בלחיצה על כפתור השמירה")
        
        # עטיפה בטופס (Form) כדי למנוע טעינה מחדש בכל שינוי תא
        # הגדרות ווטסאפ בתוך הטופס כדי ששינויי תאריך לא יגרמו לאיפוס הטבלה
        with st.form(key="staff_batch_edit_form"):
            # --- הגדרות לתזכורות ווטסאפ ---
            import urllib.parse
            st.markdown("**הגדרות תזכורת ווטסאפ (יופיעו כקישורים בטבלה למטה):**")
            col_wa1, col_wa2 = st.columns(2)
            with col_wa1:
                hebrew_months = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני", "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"]
                default_month_idx = (date.today().replace(day=1) + timedelta(days=32)).month - 1
                wa_target_month = st.selectbox("חודש רלוונטי:", hebrew_months, index=default_month_idx)
            with col_wa2:
                default_deadline = date.today().replace(day=20) if date.today().day < 20 else (date.today().replace(day=1) + timedelta(days=32)).replace(day=20)
                wa_deadline = st.date_input("תאריך יעד למילוי בקשות:", value=default_deadline)
            # -----------------------------------------
            # Prepare view without password
            # Explicitly select columns to show, excluding password
            # Also ensure only_home_dept is present
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

            # We want to edit: name, type, dept, monthly_quota, weekend_quota
            # We remove 'password' and 'only_home_dept' from the editable table
            cols_to_show = [c for c in st.session_state.staff.columns if c not in ['password', 'only_home_dept']]
            staff_view = st.session_state.staff[cols_to_show].copy()
            
            # --- הוספת עמודת תזכורת ווטסאפ ---
            whatsapp_links = []
            for idx, row in staff_view.iterrows():
                emp_name = str(row['name'])
                if emp_name.strip() and emp_name != '---':
                    wa_msg = f"היי {emp_name},\nתזכורת למלא בקשות לחודש {wa_target_month} עד לתאריך {wa_deadline.strftime('%d/%m/%Y')}.\nלמערכת השיבוצים: https://geri-shifts-scheduler.streamlit.app"
                    encoded_msg = urllib.parse.quote(wa_msg)
                    link = f"https://wa.me/?text={encoded_msg}"
                else:
                    link = None
                whatsapp_links.append(link)
            
            staff_view['whatsapp_link'] = whatsapp_links
            cols_to_show.append('whatsapp_link')
            # -----------------------------------------
            
            # Reorder for RTL or just keep consistent? 
            # Original code did: reversed_staff_view = st.session_state.staff[st.session_state.staff.columns[::-1]]
            # Let's respect RTL by reversing, but ensuring password is gone first.
            
            reversed_cols = cols_to_show[::-1]
            reversed_staff_view = staff_view[reversed_cols]

            staff_editor = st.data_editor(
                reversed_staff_view, 
                use_container_width=True, 
                num_rows="dynamic",
                column_config={
                    "whatsapp_link": st.column_config.LinkColumn(
                        "ווטסאפ",
                        help="לחץ לפתיחת ווטסאפ",
                        display_text="📱",
                        width="small"
                    )
                }
            )
            submit_changes = st.form_submit_button("💾 שמור שינויים בצוות")
        
        if submit_changes:
            # Merge logic:
            # 1. Take the editor result (staff_editor)
            # 2. Get the original passwords from st.session_state.staff
            # WE MUST BE CAREFUL: "dynamic" rows means users can add/delete rows.
            # If a row is added here, it won't have a password. We should assign default.
            
            # Because we reversed columns for display, we reverse back to normal for processing
            edited_df = staff_editor[staff_editor.columns[::-1]]
            
            # Remove the whatsapp column so it doesn't get saved to DB!
            if 'whatsapp_link' in edited_df.columns:
                edited_df = edited_df.drop(columns=['whatsapp_link'])
            
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
                    # משיכת נתונים עדכניים מהגיליון
                    latest_requests = get_db_data("requests")
                    if not latest_requests.empty:
                        st.session_state.requests = latest_requests
                        
                    # 1. מחיקת הישן לחודש זה
                    mask_keep = ~((st.session_state.requests['employee'] == selected_emp_mgr) & 
                                  (st.session_state.requests['date'].astype(str).str.startswith(current_month_prefix)))
                    st.session_state.requests = st.session_state.requests[mask_keep]
                    
                    # 2. הוספת החדש
                    new_records = []
                    for d in new_constraints:
                        new_records.append({'employee': selected_emp_mgr, 'date': d, 'status': 'אילוץ'})
                    for d in new_wishes:
                        new_records.append({'employee': selected_emp_mgr, 'date': d, 'status': 'בקשה'})
                    
                    if new_records:
                        st.session_state.requests = pd.concat([st.session_state.requests, pd.DataFrame(new_records)], ignore_index=True)
                    
                    save_to_db("requests", st.session_state.requests)
                    st.success(f"האילוצים של {selected_emp_mgr} עודכנו בהצלחה!")
                    st.session_state.pop(f"{mgr_key_prefix}_init_{sel_month}", None)
                    st.rerun()
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

        st.divider()

        # --- ייצוא נתונים ---
        st.markdown("### ייצוא נתונים")
        st.caption("לחיצה על הכפתור תשמור את הנתונים בגיליון בשם 'Schedule_Export' בקובץ המרכזי.")
        
        if st.button("עדכן את הגיליון 'Schedule_Export' (פורמט רחב)", key="export_google_top"):
            try:
                # 1. יצירת טווח תאריכים מלא לחודש הנבחר
                days_in_month = calendar.monthrange(2026, sel_month)[1]
                dates_list = [date(2026, sel_month, d) for d in range(1, days_in_month + 1)]
                
                export_rows = []
                schedule_data = st.session_state.schedule
                
                for d_obj in dates_list:
                    d_str = str(d_obj)
                    day_name = ["ב'", "ג'", "ד'", "ה'", "ו'", "ש'", "א'"][d_obj.weekday()]
                    
                    # ברירת מחדל לשורת התאריך
                    row_data = {
                        'תאריך': d_str,
                        'יום': day_name,
                        'פנימית גריאטרית': '',
                        'שיקום': '',
                        'שישי בוקר - פנימית (1)': '',
                        'שישי בוקר - פנימית (2)': '',
                        'שישי בוקר - שיקום (1)': '',
                        'שישי בוקר - שיקום (2)': ''
                    }
                    
                    # שליפת משמרות לאותו יום
                    daily_shifts = schedule_data[schedule_data['date'] == d_str]
                    
                    if not daily_shifts.empty:
                        for _, shift in daily_shifts.iterrows():
                            dept = shift['dept']
                            emp = shift['employee']
                            if emp == '---': continue # דילוג על ריקים
                            
                            # מיפוי מחלקות לעמודות
                            if dept == 'פנימית גריאטרית':
                                row_data['פנימית גריאטרית'] = emp
                            elif dept == 'שיקום':
                                row_data['שיקום'] = emp
                            elif dept == 'שישי בוקר - פנימית (1)':
                                row_data['שישי בוקר - פנימית (1)'] = emp
                            elif dept == 'שישי בוקר - פנימית (2)':
                                row_data['שישי בוקר - פנימית (2)'] = emp
                            elif dept == 'שישי בוקר - שיקום (1)':
                                row_data['שישי בוקר - שיקום (1)'] = emp
                            elif dept == 'שישי בוקר - שיקום (2)':
                                row_data['שישי בוקר - שיקום (2)'] = emp
                    
                    export_rows.append(row_data)
                
                # יצירת DataFrame סופי
                df_export = pd.DataFrame(export_rows)
                
                # סדר עמודות A-H
                col_order = [
                    'תאריך', 'יום', 
                    'פנימית גריאטרית', 'שיקום', 
                    'שישי בוקר - פנימית (1)', 'שישי בוקר - פנימית (2)', 
                    'שישי בוקר - שיקום (1)', 'שישי בוקר - שיקום (2)'
                ]
                
                # השלמת עמודות חסרות
                for col in col_order:
                    if col not in df_export.columns:
                        df_export[col] = ''
                        
                df_export = df_export[col_order]
                
                # שמירה לגיליון חדש (עם פורמט RTL)
                save_to_db("Schedule_Export", df_export, is_rtl=True)
                st.success("הנתונים ייוצאו בהצלחה לגיליון 'Schedule_Export'!")
                
            except Exception as e:
                st.error(f"שגיאה בייצוא הנתונים: {e}")


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


else:
    user_name = st.session_state.user_name
    
    if selected_nav == 'הגשת אילוצים':
        # Display the active month name clearly
        hebrew_months = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני", "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"]
        month_name = hebrew_months[sel_month - 1]
        st.subheader(f"הגשת אילוצים לחודש: {month_name}")
        
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
                    # משיכת נתונים עדכניים מהגיליון כדי למנוע דריסת נתונים
                    latest_requests = get_db_data("requests")
                    if not latest_requests.empty:
                        st.session_state.requests = latest_requests

                    # הסרת כל האילוצים והבקשות הקודמים של המשתמש לחודש זה
                    current_month_prefix = f"2026-{sel_month:02d}"
                    mask_keep = ~((st.session_state.requests['employee'] == user_name) & 
                                  (st.session_state.requests['date'].astype(str).str.startswith(current_month_prefix)))
                    st.session_state.requests = st.session_state.requests[mask_keep]
                    
                    # הוספת הרשימה החדשה והמעודכנת
                    if selected:
                        new_reqs = pd.DataFrame([{'employee': user_name, 'date': str(d), 'status': "אילוץ"} for d in selected])
                        st.session_state.requests = pd.concat([st.session_state.requests, new_reqs], ignore_index=True)
                    if wishes:
                        new_wishes = pd.DataFrame([{'employee': user_name, 'date': str(d), 'status': "בקשה"} for d in wishes])
                        st.session_state.requests = pd.concat([st.session_state.requests, new_wishes], ignore_index=True)
                    
                    save_to_db("requests", st.session_state.requests)
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

    if selected_nav == 'לוח שיבוץ':
        draw_calendar_view(2026, sel_month, "עובד/ת", user_name)