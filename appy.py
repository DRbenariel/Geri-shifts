import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import calendar
import random
import io

calendar.setfirstweekday(calendar.SUNDAY)

# --- 1. עיצוב ו-CSS ---
st.set_page_config(page_title="מערכת שיבוץ - כולל אבחון שגיאות", layout="wide")
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Rubik:wght@300;400;500;700&display=swap');
    
    html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"], .main { 
        direction: rtl; 
        text-align: right; 
        font-family: 'Rubik', sans-serif;
        background-color: #f0f2f6; 
    }
    .stTabs [data-baseweb="tab-list"] { direction: rtl; justify-content: flex-start; flex-direction: row-reverse; }
    
    /* Calendar Card Styling */
    .calendar-day { 
        border: none; 
        border-radius: 16px; 
        padding: 12px; 
        min-height: 220px; 
        background: #ffffff; 
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        transition: transform 0.2s;
        margin-bottom: 16px;
    }
    .calendar-day:hover { transform: translateY(-3px); box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1); }
    
    .weekend-day { background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%); border: 1px solid #e2e8f0; }
    
    .day-number { 
        font-weight: 700; 
        font-size: 1.4em; 
        color: #334155; 
        border-bottom: 2px solid #f1f5f9; 
        margin-bottom: 12px; 
        padding-bottom: 4px;
        display: flex;
        justify-content: space-between;
    }
    
    /* Slot Styling */
    .slot { 
        padding: 8px 10px; 
        border-radius: 8px; 
        font-size: 13px; 
        font-weight: 500; 
        margin-top: 6px; 
        display: flex;
        align-items: center;
        justify-content: space-between;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }
    .shikum-slot { background-color: #e0f2fe; border-right: 4px solid #0ea5e9; color: #0284c7; }
    .pnimia-slot { background-color: #ffedd5; border-right: 4px solid #f97316; color: #c2410c; }
    .empty-slot { background-color: #fee2e2; border: 1px dashed #ef4444; color: #991b1b; justify-content: center;}
    
    .dept-label { font-weight: 600; font-size: 0.9em; opacity: 0.8; }
    .error-hint { font-size: 11px; color: #ef4444; margin-top: 4px; display: block; background: #fef2f2; padding: 2px 4px; border-radius: 4px;}
    
    /* Enlarged Date Input & Checkboxes */
    div[data-testid="stDateInput"] input {
        font-size: 1.2rem;
        padding: 10px;
    }
    div[data-testid="stCheckbox"] label {
        font-size: 1.2rem !important;
    }
    div[data-testid="stCheckbox"] div[role="checkbox"] {
        transform: scale(1.3);
    }
    </style>
    """, unsafe_allow_html=True)

import hashlib
from streamlit_gsheets import GSheetsConnection

# --- 2. ניהול מסד נתונים (Google Sheets) ---

def get_db_data(worksheet_name):
    # קריאה מהירה ללא מטמון כדי לקבל עדכונים בזמן אמת
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df = conn.read(worksheet=worksheet_name, ttl=0)
        return df
    except Exception as e:
        # במקרה שהגיליון לא קיים או שגיאה אחרת (כמו Worksheet not found), נחזיר DataFrame ריק אך עם העמודות הנדרשות כדי למנוע קריסה
        return pd.DataFrame(columns=['name', 'password', 'type', 'dept', 'monthly_quota', 'weekend_quota'])

def save_to_db(worksheet_name, df):
    conn = st.connection("gsheets", type=GSheetsConnection)
    # שינוי: זריקת שגיאה למעלה כדי ש-init_db יטפל בה בצורה מרוכזת
    conn.update(worksheet=worksheet_name, data=df)

def init_db():
    # בדיקה האם יש נתונים בטבלת staff, אם לא - נאתחל
    try:
        current_staff = get_db_data("staff")
        
        # אם חזר DataFrame ריק, ייתכן שהגיליון לא קיים או ריק לחלוטין
        if current_staff.empty or 'name' not in current_staff.columns:
            st.info("מאתחל נתונים ראשוניים ב-Google Sheets (פעולה חד פעמית)...")
            
            interns = [
                ('בוריס גורביץ', 'שיקום'), ('סלאמה קאסם', 'שיקום'), ('נטעלי בלייכמן', 'שיקום'), ('שאדי חאג יחיא', 'שיקום'),
                ('בן אריאל', 'פנימית גריאטרית'), ('נטע פרל', 'פנימית גריאטרית'), ('יובל קירשנבוים', 'פנימית גריאטרית'),
                ('שירה בנימיני', 'פנימית גריאטרית'), ('רוני מינר', 'פנימית גריאטרית'), ('בלודאן אבו גבאל', 'פנימית גריאטרית'),
                ('חוסיין אבו דיה', 'פנימית גריאטרית'), ('סאגד מסארווה', 'פנימית גריאטרית'), ('אופיר קופל', 'פנימית גריאטרית')
            ]
            # סיסמת ברירת מחדל: 1234
            def_pass = hashlib.sha256("1234".encode()).hexdigest()
            
            data = []
            for n, d in interns:
                data.append({'name': n, 'type': 'מתמחה', 'dept': d, 'monthly_quota': 6, 'weekend_quota': 1, 'password': def_pass})
            
            # תורני חוץ
            externals = ['אחמד אלעמור', 'סגא עסלי', 'הייתם חגיר']
            for n in externals:
                data.append({'name': n, 'type': 'תורן חוץ', 'dept': 'שיקום', 'monthly_quota': 8, 'weekend_quota': 4, 'password': def_pass})
            
            # מנהל
            data.append({'name': 'admin', 'type': 'מנהל/ת', 'dept': 'הנהלה', 'monthly_quota': 0, 'weekend_quota': 0, 'password': def_pass})
            
            staff_df = pd.DataFrame(data)
            save_to_db("staff", staff_df)
            
            # אתחול שאר הטבלאות
            schedule_df = pd.DataFrame(columns=['date', 'dept', 'employee', 'is_manual', 'empty_reason'])
            save_to_db("schedule", schedule_df)
            
            requests_df = pd.DataFrame(columns=['employee', 'date', 'status'])
            save_to_db("requests", requests_df)
            
            st.success("הנתונים אותחלו בהצלחה! אנא רענן את העמוד.")

    except Exception as e:
        # הודעה מרוכזת אחת למשתמש
        if "Worksheet" in str(e) and "not found" in str(e):
             st.warning("שים לב: המערכת לא מצאה את הגיליונות הנדרשים (staff/schedule). אנא וודא שהם קיימים ב-Google Sheet שלך.")
        elif "Public Spreadsheet" in str(e) or "403" in str(e):
             st.error("שגיאת הרשאות: לא ניתן לכתוב לגיליון (Public Spreadsheet). \nאם אתה מריץ מקומית: וודא שקובץ הסודות קיים. \nאם בענן: וודא שהגדרת Secrets בהגדרות האפליקציה.")
        else:
             st.error(f"שגיאה באתחול: {e}")

# אתחול מסד הנתונים
init_db()

# --- 3. ניהול התחברות (Login) ---
def login_screen():
    st.markdown("""
        <div style='max-width: 400px; margin: 100px auto; padding: 2rem; background: white; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.1);'>
            <h1 style='text-align: center; color: #1e293b; margin-bottom: 2rem;'>🔐 כניסה למערכת</h1>
        </div>
        <style>
            div[data-testid="stTextInput"] input {
                border: 2px solid #e2e8f0 !important;
                background-color: #f8fafc;
                border-radius: 8px;
                padding: 10px;
                transition: all 0.3s;
            }
            div[data-testid="stTextInput"] input:focus {
                border-color: #3b82f6 !important;
                background-color: #ffffff;
                box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
            }
        </style>
    """, unsafe_allow_html=True)
    
    with st.container():
        cols = st.columns([1, 2, 1])
        with cols[1]:
            username = st.text_input("שם משתמש (לדוגמה: שם מלא או admin):").strip()
            password = st.text_input("סיסמה:", type="password")
            
            if st.button("כניסה", use_container_width=True):
                staff_df = get_db_data("staff")
                hashed_pass = hashlib.sha256(password.encode()).hexdigest()
                
                # בדיקה אם המשתמש קיים
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

# טעינת נתונים ממסד הנתונים ל-Session State
if 'staff' not in st.session_state:
    st.session_state.staff = get_db_data("staff")
if 'schedule' not in st.session_state:
    st.session_state.schedule = get_db_data("schedule")
if 'requests' not in st.session_state:
    st.session_state.requests = get_db_data("requests")

# כלי שיבוץ ידני
if 'manual_date' not in st.session_state:
    st.session_state.manual_date = date(2026, 1, 1)
if 'manual_dept' not in st.session_state:
    st.session_state.manual_dept = "שיקום"
if 'manual_emp' not in st.session_state:
    st.session_state.manual_emp = st.session_state.staff['name'].iloc[0] if not st.session_state.staff.empty else ""

# --- 3. לוגיקת שיבוץ עם אבחון ---
def run_smart_scheduling(year, month, only_weekends=False):
    num_days = calendar.monthrange(year, month)[1]
    staff_df = st.session_state.staff.copy()
    manual_entries = st.session_state.schedule[st.session_state.schedule['is_manual'] == True].to_dict('records')
    new_schedule = manual_entries
    
    work_load = {row['name']: 0 for _, row in staff_df.iterrows()}
    weekends_worked = {row['name']: set() for _, row in staff_df.iterrows()}
    last_assignment = {row['name']: -999 for _, row in staff_df.iterrows()}
    wed_counts = {row['name']: 0 for _, row in staff_df.iterrows()}
    thu_counts = {row['name']: 0 for _, row in staff_df.iterrows()}
    
    # עדכון מונים לפי שיבוצים ידניים קיימים
    for s in manual_entries:
        if s['employee'] in work_load:
            work_load[s['employee']] += 1
            dt = datetime.strptime(s['date'], '%Y-%m-%d')
            last_assignment[s['employee']] = dt.toordinal()
            if dt.weekday() == 2: wed_counts[s['employee']] += 1
            if dt.weekday() == 3: thu_counts[s['employee']] += 1
            # תיקון: החרגת שישי בוקר ממכסת הסופ"ש
            if dt.weekday() in [4, 5] and "שישי בוקר" not in s.get('dept', ''): 
                weekends_worked[s['employee']].add(dt.isocalendar()[1])

    all_dates = [date(year, month, d) for d in range(1, num_days + 1)]
    
    # סינון תאריכים לפי דרישה
    if only_weekends:
        # אם ביקשו רק סופ"שים, ניקח רק שישי-שבת
        sorted_dates = [d for d in all_dates if d.weekday() in [4, 5]]
    else:
        # תעדוף סופי שבוע ואז אמצע שבוע (שישי-שבת הם סופ"ש, ראשון-חמישי הם חול)
        sorted_dates = [d for d in all_dates if d.weekday() in [4, 5]] + [d for d in all_dates if d.weekday() not in [4, 5]]
    
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
                
                # בדיקת מכסה קשיחה (חודשית)
                monthly_quota = safe_int(person['monthly_quota'], 0)
                if work_load[name] >= monthly_quota:
                    failure_reasons.append(f"{name}: מכסה מלאה ({monthly_quota})")
                    continue
                
                # בדיקת סופ"ש
                weekend_quota = safe_int(person['weekend_quota'], 0)
                if d.weekday() in [4, 5] and len(weekends_worked[name]) >= weekend_quota and week_num not in weekends_worked[name]:
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
                    
                    # פקטור סופ"ש לתורני חוץ בשיקום
                    if dept == "שיקום" and cand['type'] == 'תורן חוץ':
                        # ימי חמישי (3), שישי (4), שבת (5)
                        if d.weekday() in [3, 4, 5]:
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
                    if cand_dept == dept or cand_dept == 'כללי':
                        score += 500
                    else:
                        score -= 500  # קנס משמעותי לשיבוץ במחלקה לא תואמת

                    return score

                final_choice = max(final_pool, key=calculate_score)['name']
                
                new_schedule.append({'date': d_str, 'dept': dept, 'employee': final_choice, 'is_manual': False, 'empty_reason': ''})
                work_load[final_choice] += 1
                last_assignment[final_choice] = d.toordinal()
                if d.weekday() == 2: wed_counts[final_choice] += 1
                if d.weekday() == 3: thu_counts[final_choice] += 1
                if d.weekday() in [4, 5]: weekends_worked[final_choice].add(week_num)
            else:
                # --- לוגיקת הצעת החלפות ועזרה (Swap & Suggest) ---
                suggestions = []
                # אתחול מילון הצעות מובנה אם לא קיים (נמחק בתחילת הריצה)
                if 'swap_suggestions' not in st.session_state: st.session_state.swap_suggestions = {}
                
                # כלי עזר לבדיקת תקינות מלאה (כולל מנוחה, רצף, וכו') להחלפה
                def is_valid_assignment_for_swap(person_name, check_date, target_dept):
                    # בדיקת מנוחה (יומיים רווח) רק סביב התאריך הנבדק
                    check_d_obj = datetime.strptime(check_date, '%Y-%m-%d').date()
                    for offset in [-2, -1, 1, 2]:
                        if any(s for s in new_schedule if s['date'] == str(check_d_obj + timedelta(days=offset)) and s['employee'] == person_name):
                             return False
                    
                    # בדיקת כפילות באותו יום
                    if any(s for s in new_schedule if s['date'] == check_date and s['employee'] == person_name): return False
                    
                    # בדיקת רצף חמישי-שישי בוקר (אם רלוונטי) - כאן זה בדיקה גנרית
                    
                    # בדיקת אילוצי משתמש (רק חסמים קשיחים)
                    if not st.session_state.requests[(st.session_state.requests['employee'] == person_name) & (st.session_state.requests['date'] == check_date) & (st.session_state.requests['status'] == "אילוץ")].empty: return False
                    
                    # בדיקת סוג עובד: תורן חוץ לא יכול לבצע משמרת בפנימית
                    p_row = staff_df[staff_df['name'] == person_name]
                    if not p_row.empty:
                        p_type = p_row['type'].iloc[0]
                        if p_type == 'תורן חוץ' and 'פנימית' in target_dept:
                            return False

                    return True

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
                                suggestions.append(f"💡 הסטה: העבר את **{name_a}** מה-{conf_date} לפה, ושבץ שם את **{name_b}**.")
                                
                                core_key = f"{d_str}_{dept}"
                                if core_key not in st.session_state.swap_suggestions: st.session_state.swap_suggestions[core_key] = []
                                st.session_state.swap_suggestions[core_key].append({
                                    'type': 'move_shift',
                                    'conflict_date': conf_date,
                                    'conflicted_emp': name_a,
                                    'conflict_dept': conf_dept,
                                    'replacement_emp': name_b,
                                    'desc': f"הסטה: {name_a} (מ-{conf_date}) ⬅️ {name_b}"
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
                    final_msg = f"{name}: לא נמצא שיבוץ ישיר.\n" + "\n".join(suggestions[:3])
                else:
                    final_msg = "לא נמצא פתרון אוטומטי (" + ", ".join(failure_reasons[:2]) + ")"
                
                new_schedule.append({'date': d_str, 'dept': dept, 'employee': '---', 'is_manual': False, 'empty_reason': final_msg})

    # --- לוגיקה חדשה: שיבוץ שישי בוקר (4 עובדים) ---
    # רצים על כל ימי השישי בחודש
    fridays = [d for d in all_dates if d.weekday() == 4]
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
                # קריטריונים: מחלקת שיקום, פנוי בשישי, לא עבד ברביעי/חמישי האחרונים
                
                # בדיקת עבודה ברביעי/חמישי
                wed_date = fri_date - timedelta(days=2)
                thu_date = fri_date - timedelta(days=1)
                
                candidates = []
                for _, row in staff_df.iterrows():
                    if row['type'] == 'מתמחה' and row['dept'] == 'שיקום' and row['name'] != worker_name:
                        emp = row['name']
                        
                        # האם פנוי ביום שישי (אילוץ - חסם)
                        is_blocked = not st.session_state.requests[(st.session_state.requests['employee'] == emp) & (st.session_state.requests['date'] == fri_str) & (st.session_state.requests['status'] == "אילוץ")].empty
                        if is_blocked: continue
                        
                        # האם עובד ברביעי או חמישי?
                        worked_wed = any(s['employee'] == emp and s['date'] == wed_date.strftime('%Y-%m-%d') for s in new_schedule)
                        worked_thu = any(s['employee'] == emp and s['date'] == thu_date.strftime('%Y-%m-%d') for s in new_schedule)
                        if worked_wed or worked_thu: continue
                        
                        # האם כבר משובץ בשישי במקום אחר (למשל תורנות רגילה במחלקת שיקום בצד השני?)
                        if any(s['employee'] == emp and s['date'] == fri_str for s in new_schedule): continue

                        # חישוב ציון הוגנות: כמה שישי בוקר כבר יש לו?
                        fri_morning_count = len([s for s in new_schedule if s['employee'] == emp and 'שישי בוקר' in s['dept']])
                        candidates.append((emp, fri_morning_count))
                
                # מיון לפי הכמות הכי קטנה של שישי בוקר (איזון)
                if candidates:
                    candidates.sort(key=lambda x: x[1]) # מהקטן לגדול
                    best_candidate = candidates[0][0]
                    new_schedule.append({'date': fri_str, 'dept': target_dept, 'employee': best_candidate, 'is_manual': False, 'empty_reason': f'השלמה במקום {worker_name}'})
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
# --- 4. פונקציית ציור הלוח ---
def draw_calendar_view(year, month, role, user_name=None):
    cal = calendar.monthcalendar(year, month)
    days_names = ["א'", "ב'", "ג'", "ד'", "ה'", "ו'", "ש'"]
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
                        if "שישי בוקר" in dept: label = "🔊 בוקר (" + ("שיקום" if "שיקום" in dept else "פנימית") + ")"
                        
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
                
                st.markdown(html + "</div>", unsafe_allow_html=True)

# --- 5. ממשק המנהל והעובד ---
with st.sidebar:
    st.title("🏥 מערכת תורנויות")
    st.write(f"👋 שלום, **{st.session_state.user_name}**")
    role = st.session_state.user_role
    sel_month = st.selectbox("חודש", range(1, 13), index=date.today().month - 1)
    
    if st.button("🚪 התנתק"):
        st.session_state.logged_in = False
        st.rerun()
    
    st.divider()
    with st.expander("🔑 שינוי סיסמה"):
        old_p = st.text_input("סיסמה נוכחית:", type="password")
        new_p = st.text_input("סיסמה חדשה:", type="password")
        conf_p = st.text_input("אימות סיסמה חדשה:", type="password")
        
        if st.button("עדכן סיסמה"):
            staff_df = st.session_state.staff
            current_user = st.session_state.user_name
            actual_pass = staff_df[staff_df['name'] == current_user].iloc[0]['password']
            
            if hashlib.sha256(old_p.encode()).hexdigest() != actual_pass:
                st.error("הסיסמה הנוכחית שגויה")
            elif new_p != conf_p:
                st.error("הסיסמה החדשה והאימות אינם תואמים")
            elif len(new_p) < 4:
                st.error("הסיסמה חייבת להכיל לפחות 4 תווים")
            else:
                new_hashed = hashlib.sha256(new_p.encode()).hexdigest()
                # עדכון ב-DataFrame
                st.session_state.staff.loc[st.session_state.staff['name'] == current_user, 'password'] = new_hashed
                # שמירה למסד הנתונים
                save_to_db("staff", st.session_state.staff)
                st.success("הסיסמה עודכנה בהצלחה!")

if role == "מנהל/ת":
    t1, t2, t3, t4 = st.tabs(["📅 לוח שיבוץ", "👥 ניהול צוות", "📊 דוח", "⚖️ טבלת צדק"])
    with t1:
        # --- הוספת כלי שיבוץ ידני ---
        # --- הוספת כלי שיבוץ ידני ---
        with st.expander("🛠️ כלי שיבוץ ידני (דריסה)", expanded=True):
            c_date, c_dept, c_emp, c_btn_add, c_btn_del = st.columns([1, 1, 1, 0.7, 0.7])
            
            # עדכון ערך ברירת מחדל לתאריך רק אם החודש השתנה בסרגל הצד
            # זה מאפשר לשמור על בחירת המשתמש בתוך אותו חודש
            default_date = date(2026, sel_month, 1)
            if 'manual_date' in st.session_state:
                if st.session_state.manual_date.month != sel_month:
                     st.session_state.manual_date = default_date

            d_man = c_date.date_input("תאריך:", key="manual_date")
            dept_man = c_dept.selectbox("מחלקה:", ["שיקום", "פנימית גריאטרית", "שישי בוקר - שיקום (1)", "שישי בוקר - שיקום (2)", "שישי בוקר - פנימית (1)", "שישי בוקר - פנימית (2)"], key="manual_dept")
            
            # סינון רשימת העובדים - הצגת מי שמשובץ כרגע למעלה או סימון מיוחד? לא קריטי כרגע.
            emp_man = c_emp.selectbox("עובד:", st.session_state.staff['name'].tolist(), key="manual_emp")
            
            # כפתור שיבוץ
            if c_btn_add.button("✅ שבוץ"):
                # הסרת שיבוץ קיים לתאריך ולמחלקה הזו (אם יש)
                st.session_state.schedule = st.session_state.schedule[
                    ~((st.session_state.schedule['date'] == str(d_man)) & 
                      (st.session_state.schedule['dept'] == dept_man))
                ]
                # הוספת השיבוץ הידני עם סימון ידני=True
                new_entry = pd.DataFrame([{
                    'date': str(d_man), 
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
        if c3.button("🗑️ נקה לוח"): 
            # איפוס מלא של הלוח - שומר רק על מבנה העמודות
            st.session_state.schedule = pd.DataFrame(columns=st.session_state.schedule.columns)
            save_to_db("schedule", st.session_state.schedule)
            st.rerun()
        
        # --- התראה על משמרות שלא שובצו ---
        if not st.session_state.schedule.empty:
            failures = st.session_state.schedule[st.session_state.schedule['employee'] == '---']
            if not failures.empty:
                st.error(f"⚠️ שימו לב: נמצאו {len(failures)} משמרות שלא ניתן היה לשבץ!")
                with st.expander("🔻 לחץ כאן לפירוט השגיאות והסיבות", expanded=False):
                    for _, row in failures.iterrows():
                        st.markdown(f"❌ **{row['date']}** ({row['dept']}): {row['empty_reason']}")
                        
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
    with t2:
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
                                'password': def_pass_hash
                            }])
                            
                            st.session_state.staff = pd.concat([st.session_state.staff, new_emp_row], ignore_index=True)
                            save_to_db("staff", st.session_state.staff)
                            st.success(f"העובד/ת {new_name} נוספ/ה בהצלחה! (סיסמה: 1234)")
                            st.rerun()
                        else:
                            st.error("שגיאה: שם העובד כבר קיים במערכת.")
                    else:
                        st.error("חובה להזין שם עובד.")
        # -----------------------

        st.caption("שינויים בטבלה נשמרים רק בלחיצה על כפתור השמירה")
        
        # עטיפה בטופס (Form) כדי למנוע טעינה מחדש בכל שינוי תא
        with st.form(key="staff_batch_edit_form"):
            staff_editor = st.data_editor(st.session_state.staff, use_container_width=True, num_rows="dynamic")
            submit_changes = st.form_submit_button("💾 שמור שינויים בצוות")
        
        if submit_changes:
            st.session_state.staff = staff_editor
            save_to_db("staff", st.session_state.staff)
            st.success("הנתונים נשמרו בהצלחה!")
            st.rerun()
            
        st.divider()
        st.subheader("ניהול אילוצים ומשמרות")
        
        # בחירת עובד לניהול אילוצים
        selected_emp_mgr = st.selectbox("בחר עובד לניהול אילוצים:", st.session_state.staff['name'].tolist())
        
        if selected_emp_mgr:
            st.write(f"עריכת אילוצים עבור: **{selected_emp_mgr}**")
            
            # טעינת אילוצים קיימים
            existing_mgr = st.session_state.requests[st.session_state.requests['employee'] == selected_emp_mgr]
            default_dates_mgr = []
            if not existing_mgr.empty:
                for d_str in existing_mgr['date']:
                    try:
                        d_obj = datetime.strptime(d_str, '%Y-%m-%d').date()
                        if d_obj.month == sel_month and d_obj.year == 2026:
                            default_dates_mgr.append(d_obj)
                    except: pass
            
            # לוח שנה (Data Editor) לניהול
            # יצירת DataFrame לעריכה
            days_in_month = calendar.monthrange(2026, sel_month)[1]
            month_dates = [date(2026, sel_month, d) for d in range(1, days_in_month + 1)]
            
            # יצירת טבלה זמנית
            edit_data = []
            for d_obj in month_dates:
                is_blocked = d_obj in default_dates_mgr
                day_name = ["ב'", "ג'", "ד'", "ה'", "ו'", "ש'", "א'"][d_obj.weekday()] # 0=Monday
                edit_data.append({
                    "תאריך": d_obj,
                    "יום": day_name,
                    "חסום?": is_blocked
                })
            
            df_edit = pd.DataFrame(edit_data)
            
            st.caption("סמן V בימים בהם העובד **לא יכול** לעבוד:")
            with st.form(key=f"mgr_form_{selected_emp_mgr}"):
                edited_df = st.data_editor(
                    df_edit, 
                    column_config={
                        "תאריך": st.column_config.DateColumn("תאריך", format="DD/MM/YYYY", disabled=True),
                        "יום": st.column_config.TextColumn("יום", disabled=True),
                        "חסום?": st.column_config.CheckboxColumn("חסום?", default=False)
                    },
                    hide_index=True,
                    use_container_width=True,
                    height=400
                )
                
                submitted = st.form_submit_button("💾 שמור אילוצים לחודש זה")

            if submitted:
                # סינון ימים שנבחרו כחסומים
                blocked_dates = edited_df[edited_df["חסום?"] == True]["תאריך"].tolist()
                
                # המרה למחרוזות לשמירה אחידה
                blocked_dates_str = [str(d) for d in blocked_dates]
                
                # ניקוי אילוצים קיימים לחודש זה עבור העובד
                # המרה בטוחה למחרוזת לפני הפעולה כדי למנוע את השגיאה AttributeError
                st.session_state.requests['date'] = st.session_state.requests['date'].astype(str)
                
                current_month_prefix = f"2026-{sel_month:02d}"
                
                # מחיקת אילוצים ישנים של העובד לחודש זה
                # משמרים: (לא העובד הנוכחי) או (העובד הנוכחי אבל לא בחודש הזה)
                mask_keep = ~((st.session_state.requests['employee'] == selected_emp_mgr) & 
                              (st.session_state.requests['date'].str.startswith(current_month_prefix)))
                
                st.session_state.requests = st.session_state.requests[mask_keep]
                
                # הוספת האילוצים החדשים
                if blocked_dates_str:
                    new_reqs = pd.DataFrame([
                        {'employee': selected_emp_mgr, 'date': d_str, 'status': "אילוץ"} 
                        for d_str in blocked_dates_str
                    ])
                    st.session_state.requests = pd.concat([st.session_state.requests, new_reqs], ignore_index=True)
                
                # וידוא שוב שהכל מחרוזות
                st.session_state.requests['date'] = st.session_state.requests['date'].astype(str)
                
                save_to_db("requests", st.session_state.requests)
                st.success(f"האילוצים של {selected_emp_mgr} לחודש {sel_month}/2026 עודכנו בהצלחה!")
                st.rerun()
    with t3:
        if not st.session_state.schedule.empty: 
            st.subheader("ספירת משמרות")
            
            # הכנת נתונים לגרף משולב
            sched = st.session_state.schedule
            
            # ספירה רגילה (ללא שישי בוקר)
            reg_counts = sched[~sched['dept'].str.contains("שישי בוקר", na=False)]['employee'].value_counts()
            
            # ספירת שישי בוקר בלבד
            morn_counts = sched[sched['dept'].str.contains("שישי בוקר", na=False)]['employee'].value_counts()
            
            # איחוד לטבלה אחת
            combined_df = pd.DataFrame({'תורנויות רגילות': reg_counts, 'שישי בוקר': morn_counts}).fillna(0)
            
            st.bar_chart(combined_df)
            st.caption("הגרף מציג בחלוקה לצבעים: תורנויות רגילות לעומת שישי בוקר")
            
            st.divider()
            st.subheader("ייצוא נתונים")
            
            # הכנת קובץ אקסל בזיכרון
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                # עיבוד הנתונים לפורמט הרצוי: תאריך | תורן פנימית | תורן שיקום
                if not st.session_state.schedule.empty:
                    export_df = st.session_state.schedule.copy()
                    # הסרת כפילויות אם יש
                    export_df = export_df.drop_duplicates(subset=['date', 'dept'])
                    
                    # Pivot Table
                    pivot_df = export_df.pivot(index='date', columns='dept', values='employee')
                    
                    # השלמת עמודות חסרות
                    if 'פנימית גריאטרית' not in pivot_df.columns: pivot_df['פנימית גריאטרית'] = ""
                    if 'שיקום' not in pivot_df.columns: pivot_df['שיקום'] = ""
                    
                    # בחירת עמודות וסידורן
                    final_df = pivot_df[['פנימית גריאטרית', 'שיקום']].reset_index()
                    final_df.columns = ['תאריך', 'תורן פנימית גריאטרית', 'תורן שיקום']
                    
                    final_df.to_excel(writer, index=False, sheet_name='Schedule')
                    
                    # כיוון מימין לשמאל
                    writer.sheets['Schedule'].sheet_view.rightToLeft = True
                    
                    # התאמת רוחב עמודות (אופציונלי)
                    ws = writer.sheets['Schedule']
                    ws.column_dimensions['A'].width = 15
                    ws.column_dimensions['B'].width = 20
                    ws.column_dimensions['C'].width = 20
                    
                # גליון צוות
                st.session_state.staff.to_excel(writer, index=False, sheet_name='Staff')
                writer.sheets['Staff'].sheet_view.rightToLeft = True
                
            download_data = buffer.getvalue()
            
            st.download_button(
                label="📥 הורד סידור עבודה (Excel)",
                data=download_data,
                file_name=f"schedule_{sel_month}_2026.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    with t4:
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
                    'ציון הוגנות (נטו)': wed_count - thu_count # חיובי = קיבל יותר טובים, שלילי = קיבל יותר קשים
                })
            
            df_fairness = pd.DataFrame(tracker).sort_values('ציון הוגנות (נטו)', ascending=False)
            
            # עיצוב הטבלה
            st.dataframe(
                df_fairness.style.background_gradient(subset=['ציון הוגנות (נטו)'], cmap="RdYlGn"),
                use_container_width=True
            )
            
            st.divider()
            st.caption("פירוט לפי חודשים:")
            
            # פירוט לפי חודשים (Pivot Table)
            # אנו רוצים לראות לכל עובד, בחלוקה לחודשים, כמה ד' וכמה ה' עשה
            monthly_breakdown = intern_schedule[intern_schedule['weekday'].isin([2, 3])].copy()
            if not monthly_breakdown.empty:
                monthly_breakdown['day_type'] = monthly_breakdown['weekday'].map({2: "יום ד'", 3: "יום ה'"})
                
                pivot = pd.pivot_table(
                    monthly_breakdown, 
                    values='date', 
                    index=['employee'], 
                    columns=['month_year', 'day_type'], 
                    aggfunc='count', 
                    fill_value=0
                )
                st.dataframe(pivot, use_container_width=True)
            else:
                st.info("אין נתונים להצגה בחיתוך חודשי")
        else:
            st.info("הלוח עדיין ריק.")
else:
    user_name = st.session_state.user_name
    tab1, tab2 = st.tabs(["✍️ הגשת אילוצים", "📅 סידור עבודה"])

    with tab1:
        st.subheader(f"הגשת אילוצים עבור: {user_name}")
        
        # --- הצגת אילוצים קיימים ---
        existing = st.session_state.requests[st.session_state.requests['employee'] == user_name]
        if not existing.empty:
            st.info(f"📅 **תאריכים שכבר חסמת ({len(existing)}):**\n" + ", ".join([r['date'] for _, r in existing.iterrows()]))
        else:
            st.info("עדיין לא הגשת אילוצים לחודש זה.")
        # ----------------------------

        st.divider()
        st.write("### שלב 1: סימון ימים בהם **אינך** יכול/ה לעבוד")
        st.caption("חובה להשאיר לפחות 2 ימי חמישי ו-4 ימי סופ\"ש פנויים.")

        # חישוב תאריכים שכבר נבחרו (לצורך אתחול)
        default_dates = []
        if not existing.empty:
            for d_str in existing['date']:
                try:
                    d_obj = datetime.strptime(d_str, '%Y-%m-%d').date()
                    # יש להוסיף רק תאריכים שרלוונטיים לחודש הנבחר
                    if d_obj.month == sel_month and d_obj.year == 2026:
                        default_dates.append(d_obj)
                except: pass
        
        # --- יצירת לוח שנה עם Checkboxes ---
        # פונקציה עזר לציור
        if 'temp_selected_dates' not in st.session_state:
            st.session_state.temp_selected_dates = set(default_dates)
            
        # עדכון ה-session state במקרה של שינוי חודש או טעינה מחדש
        # אבל נרצה לשמר בחירות זמניות שטרם נשמרו? 
        # לצורך הפשטות, תמיד נאתחל עם הקיים ב-DB בתוספת מה שהמשתמש שיחק איתו כרגע, 
        # אבל ה-State של ה-Checkbox הוא טריקי. 
        # נשתמש ב-Callback או פשוט נקרא את הערכים מהממשק.
        
        cal = calendar.monthcalendar(2026, sel_month)
        days_cols = st.columns(7)
        headers = ["א'", "ב'", "ג'", "ד'", "ה'", "ו'", "ש'"]
        for i, h in enumerate(headers):
            days_cols[i].markdown(f"<div style='text-align:center; font-weight:bold'>{h}</div>", unsafe_allow_html=True)
        
        selected_from_grid = []
        
        for week in cal:
            wk_cols = st.columns(7)
            for i, day_num in enumerate(week):
                with wk_cols[i]:
                    if day_num == 0:
                        st.write("")
                    else:
                        d_obj = date(2026, sel_month, day_num)
                        is_checked = d_obj in default_dates
                        # מפתח ייחודי לכל צ'קבוקס
                        chk = st.checkbox(f"{day_num}", value=is_checked, key=f"date_chk_{sel_month}_{day_num}")
                        if chk:
                            selected_from_grid.append(d_obj)
        
        st.divider()
        st.write("### שלב 2: בקשות למשמרות (Wishes) - אופציונלי")
        st.caption("ניתן לבחור עד **2 תאריכים** בחודש בהם היית רוצה לעבוד. המערכת תשתדל להתחשב, אך לא מבטיחה שיבוץ.")
        
        # בחירת בקשות חיוביות
        existing_wishes = st.session_state.requests[(st.session_state.requests['employee'] == user_name) & (st.session_state.requests['status'] == "בקשה")]
        default_wishes = []
        if not existing_wishes.empty:
            for d_str in existing_wishes['date']:
                try:
                    d_obj = datetime.strptime(d_str, '%Y-%m-%d').date()
                    if d_obj.month == sel_month and d_obj.year == 2026:
                        default_wishes.append(d_obj)
                except: pass

        selected_wishes = []
        wish_cols = st.columns(7)
        for week in cal:
            w_wk_cols = st.columns(7)
            for i, day_num in enumerate(week):
                with w_wk_cols[i]:
                    if day_num != 0:
                        d_obj = date(2026, sel_month, day_num)
                        is_wished = d_obj in default_wishes
                        # במקום Chkbox, נשתמש ב-Toggle או משהו שונה ויזואלית
                        win_chk = st.checkbox(f"⭐ {day_num}", value=is_wished, key=f"wish_chk_{sel_month}_{day_num}")
                        if win_chk:
                            selected_wishes.append(d_obj)

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
                
                errors = []
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

                c_yes, c_no = st.columns(2)
                if c_yes.button("✅ כן, עדכן"):
                    # הסרת כל האילוצים והבקשות הקודמים של המשתמש לחודש זה
                    current_month_prefix = f"2026-{sel_month:02d}"
                    mask_keep = ~((st.session_state.requests['employee'] == user_name) & 
                                  (st.session_state.requests['date'].str.startswith(current_month_prefix)))
                    st.session_state.requests = st.session_state.requests[mask_keep]
                    
                    # הוספת הרשימה החדשה והמעודכנת
                    if selected:
                        new_reqs = pd.DataFrame([{'employee': user_name, 'date': str(d), 'status': "אילוץ"} for d in selected])
                        st.session_state.requests = pd.concat([st.session_state.requests, new_reqs], ignore_index=True)
                    if wishes:
                        new_wishes = pd.DataFrame([{'employee': user_name, 'date': str(d), 'status': "בקשה"} for d in wishes])
                        st.session_state.requests = pd.concat([st.session_state.requests, new_wishes], ignore_index=True)
                    
                    save_to_db("requests", st.session_state.requests)
                    st.success("האילוצים עודכנו בהצלחה!")
                    st.session_state['confirm_request_save'] = False
                    st.rerun()
                
                if c_no.button("❌ בטל"):
                    st.session_state['confirm_request_save'] = False
                    st.rerun()
    with tab2:
        draw_calendar_view(2026, sel_month, "עובד/ת", user_name)