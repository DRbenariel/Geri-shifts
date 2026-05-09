# mock_requests.py  —  UI prototype
# Run: streamlit run "D:/Projects/New Folder/mock_requests.py"

import streamlit as st
import pandas as pd
import calendar as cal_mod
from datetime import date

st.set_page_config(page_title="מוק - סידור יומי", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Rubik:wght@400;500;700&display=swap');
html, body, [data-testid="stAppViewContainer"], .main {
    direction: rtl; text-align: right;
    font-family: 'Rubik', sans-serif; background: #f8fafc; color: #1e293b;
}
#MainMenu, footer, header { visibility: hidden; }
.main .block-container { padding-top: 1rem !important; padding-bottom: 60px; }
h1,h2,h3,h4 { color: #0f172a !important; }

/* Default button → indigo */
div[data-testid="stButton"] > button {
    background: linear-gradient(135deg,#4f46e5,#4338ca) !important;
    color: white !important; border: none !important;
    border-radius: 8px !important; font-family: 'Rubik',sans-serif !important;
    padding: 4px 2px !important; font-size: 0.8rem !important;
    width: 100% !important; min-height: 34px !important;
}
div[data-testid="stButton"] > button:hover {
    background: linear-gradient(135deg,#4338ca,#3730a3) !important;
    transform: translateY(-1px) !important;
}

/* ── Night calendar variants ── */
div[class*="st-key-nf_"] > div[data-testid="stButton"] > button {
    background: white !important; color: #334155 !important;
    border: 1px solid #e2e8f0 !important;
}
div[class*="st-key-nf_"] > div[data-testid="stButton"] > button:hover {
    background: #fef2f2 !important; border-color: #fca5a5 !important; transform: none !important;
}
div[class*="st-key-nb_"] > div[data-testid="stButton"] > button { background: #dc2626 !important; }
div[class*="st-key-nw_"] > div[data-testid="stButton"] > button { background: #7c3aed !important; }

/* ── Day calendar (free/select/range) ── */
div[class*="st-key-df_"] > div[data-testid="stButton"] > button {
    background: white !important; color: #334155 !important; border: 1px solid #e2e8f0 !important;
}
div[class*="st-key-df_"] > div[data-testid="stButton"] > button:hover {
    background: #f0fdf4 !important; border-color: #86efac !important;
    color: #166534 !important; transform: none !important;
}
div[class*="st-key-ds_"] > div[data-testid="stButton"] > button {
    background: #16a34a !important; border: 2px solid #15803d !important;
}
div[class*="st-key-dr_"] > div[data-testid="stButton"] > button {
    background: #bbf7d0 !important; color: #166534 !important; border: 1px solid #86efac !important;
}

/* ── Dept-grid cell buttons ── */
div[class*="st-key-cell_w_"] > div[data-testid="stButton"] > button  { background: #16a34a !important; font-size:0.72rem !important; }
div[class*="st-key-cell_h_"] > div[data-testid="stButton"] > button  { background: #2563eb !important; font-size:0.72rem !important; }
div[class*="st-key-cell_2_"] > div[data-testid="stButton"] > button  { background: #ca8a04 !important; font-size:0.72rem !important; }
div[class*="st-key-cell_p_"] > div[data-testid="stButton"] > button  { background: #f97316 !important; font-size:0.72rem !important; }
div[class*="st-key-cell_a_"] > div[data-testid="stButton"] > button  { background: #94a3b8 !important; font-size:0.72rem !important; }
div[class*="st-key-cell_e_"] > div[data-testid="stButton"] > button  {
    background: white !important; color: #334155 !important;
    border: 1px dashed #cbd5e1 !important; font-size:0.72rem !important;
}

/* ── Non-clickable day cells ── */
.dc-night { background:#1e3a5f; color:white; border-radius:8px; padding:5px 2px;
            text-align:center; font-size:0.78rem; min-height:34px;
            display:flex; align-items:center; justify-content:center; }
.dc-post  { background:#f97316; color:white; border-radius:8px; padding:5px 2px;
            text-align:center; font-size:0.78rem; min-height:34px;
            display:flex; align-items:center; justify-content:center; }
.dc-vac   { background:#2563eb; color:white; border-radius:8px; padding:5px 2px;
            text-align:center; font-size:0.78rem; min-height:34px;
            display:flex; align-items:center; justify-content:center; }
.dc-202   { background:#ca8a04; color:white; border-radius:8px; padding:5px 2px;
            text-align:center; font-size:0.78rem; min-height:34px;
            display:flex; align-items:center; justify-content:center; }
.dc-pend  { background:#94a3b8; color:white; border-radius:8px; padding:5px 2px;
            text-align:center; font-size:0.78rem; min-height:34px;
            display:flex; align-items:center; justify-content:center; }
.dc-empty { padding:5px 2px; min-height:34px; }
.cal-hdr  { text-align:center; font-weight:700; color:#475569; font-size:0.82rem; padding-bottom:4px; }

/* Grid table */
.grid-hdr { background:#f1f5f9; font-weight:700; text-align:center;
            padding:6px 2px; border-radius:6px; font-size:0.75rem; color:#334155; }
.grid-name { font-weight:600; font-size:0.82rem; color:#0f172a;
             padding:4px 8px; background:white; border-radius:6px;
             border:1px solid #e2e8f0; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# Mock data
# ─────────────────────────────────────────────────────────────
YEAR, MONTH, NUM_DAYS = 2026, 6, 30
HEB_DAYS  = ["א","ב","ג","ד","ה","ו","ש"]
JUNE1_IDX = 1   # June 1 2026 = Monday → Hebrew Sun=0,Mon=1

NIGHT_SHIFTS = {4,10,20}
POST_SHIFTS  = {5,11,21}
APPROVED_VAC = {6,7}
APPROVED_202 = {15,16}
PENDING      = {23}

EMPLOYEES_A  = ["יובל קירשנבוים","לין חיר אל דין","נועה כהן"]
EMPLOYEES_B  = ["בוריס גורוביץ","מיכל לוי"]
EMPLOYEES_PN = ["אורלי שמש","דנה ברק","עמית רוז"]

# per-employee per-day status for dept grid mock
# w=עובד h=חופש 2=202 p=אחרי תורנות a=אחר e=עובד(default)
GRID_A = {
    "יובל קירשנבוים": {1:"w",2:"w",3:"h",4:"h",5:"p",6:"w",7:"w",8:"w",9:"w",10:"w",
                        11:"p",12:"w",13:"w",14:"w",15:"2",16:"2",17:"w",18:"w",19:"w",
                        20:"w",21:"p",22:"w",23:"a",24:"w",25:"w",26:"w",27:"w",28:"w",29:"w",30:"w"},
    "לין חיר אל דין": {**{d:"w" for d in range(1,31)}, 6:"h",7:"h",10:"h"},
    "נועה כהן":        {**{d:"w" for d in range(1,31)}, 15:"2",16:"2",20:"h"},
}

ALL_REQUESTS = pd.DataFrame([
    {"עובד":"יובל קירשנבוים","תאריכים":"03–04/06","סוג":"חופש רגיל",  "מחלקה":"שיקום א'","סטטוס":"⏳ ממתין"},
    {"עובד":"לין חיר אל דין","תאריכים":"06–07/06","סוג":"חופש רגיל",  "מחלקה":"שיקום א'","סטטוס":"⏳ ממתין"},
    {"עובד":"נועה כהן",      "תאריכים":"15–16/06","סוג":"202",         "מחלקה":"שיקום א'","סטטוס":"⏳ ממתין"},
    {"עובד":"אורלי שמש",     "תאריכים":"10/06",   "סוג":"היעדרות אחרת","מחלקה":"פנימית",  "סטטוס":"⏳ ממתין"},
    {"עובד":"דנה ברק",       "תאריכים":"20–22/08","סוג":"חופש עתידי",  "מחלקה":"פנימית",  "סטטוס":"⏳ ממתין"},
    {"עובד":"בוריס גורוביץ", "תאריכים":"01–03/06","סוג":"חופש רגיל",  "מחלקה":"שיקום ב'","סטטוס":"✅ אושר"},
])

MY_HISTORY = pd.DataFrame([
    {"תאריכים":"06–07/06","סוג":"חופש רגיל",   "סטטוס":"✅ אושר",  "מאשר":"רתם"},
    {"תאריכים":"15–16/06","סוג":"202",          "סטטוס":"✅ אושר",  "מאשר":"רתם"},
    {"תאריכים":"23/06",   "סוג":"היעדרות אחרת","סטטוס":"⏳ ממתין", "מאשר":"—"},
    {"תאריכים":"10–12/08","סוג":"חופש עתידי",  "סטטוס":"✅ אושר",  "מאשר":"רון"},
])

ROTATION_DATA = {
    "יובל קירשנבוים":  "שיקום גריאטרי א'",
    "לין חיר אל דין":  "שיקום גריאטרי א'",
    "נועה כהן":         "שיקום גריאטרי א'",
    "בוריס גורוביץ":   "שיקום גריאטרי ב'",
    "מיכל לוי":         "שיקום גריאטרי ב'",
    "אורלי שמש":        "פנימית גריאטרית",
    "דנה ברק":          "פנימית גריאטרית",
    "עמית רוז":         "פנימית גריאטרית",
    "שירה מנחם":        "— לא שובץ —",
}
DAILY_DEPTS = ["שיקום גריאטרי א'","שיקום גריאטרי ב'","פנימית גריאטרית","— לא שובץ —"]

# ─────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────
if "n_state"    not in st.session_state: st.session_state.n_state    = {3:"b",10:"b",20:"w"}
if "sel_start"  not in st.session_state: st.session_state.sel_start  = None
if "sel_end"    not in st.session_state: st.session_state.sel_end    = None
if "rotation"   not in st.session_state: st.session_state.rotation   = dict(ROTATION_DATA)
if "req_open"   not in st.session_state: st.session_state.req_open   = True
if "cell_edit"  not in st.session_state: st.session_state.cell_edit  = {}  # (emp,day)->status

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _grid():
    raw = [None]*JUNE1_IDX + list(range(1, NUM_DAYS+1))
    while len(raw)%7: raw.append(None)
    return [raw[i:i+7] for i in range(0,len(raw),7)]

def _sel_range():
    s,e = st.session_state.sel_start, st.session_state.sel_end
    return set(range(min(s,e), max(s,e)+1)) if s and e else set()

def _day_header():
    cols = st.columns(7)
    for i,h in enumerate(HEB_DAYS):
        cols[i].markdown(f"<div class='cal-hdr'>{h}</div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# Night constraint calendar
# ─────────────────────────────────────────────────────────────
def render_night_cal(key_suffix=""):
    _day_header()
    for week in _grid():
        cols = st.columns(7)
        for ci,day in enumerate(week):
            with cols[ci]:
                if day is None:
                    st.markdown("<div class='dc-empty'></div>", unsafe_allow_html=True); continue
                s = st.session_state.n_state.get(day,"f")
                lbl = f"🔴 {day}" if s=="b" else (f"⭐ {day}" if s=="w" else str(day))
                pfx = "nb" if s=="b" else ("nw" if s=="w" else "nf")
                if st.button(lbl, key=f"{pfx}_{day}{key_suffix}", use_container_width=True):
                    cycle = {"f":"b","b":"w","w":"f"}
                    st.session_state.n_state[day] = cycle[s]; st.rerun()

# ─────────────────────────────────────────────────────────────
# Day absence calendar
# ─────────────────────────────────────────────────────────────
def render_day_cal():
    _day_header()
    rng = _sel_range(); s0 = st.session_state.sel_start
    for week in _grid():
        cols = st.columns(7)
        for ci,day in enumerate(week):
            with cols[ci]:
                if day is None:
                    st.markdown("<div class='dc-empty'></div>", unsafe_allow_html=True); continue
                # Day absence calendar shows ONLY absence-related states.
                # Night shifts + אחרי תורנות are NOT displayed here (they live in night calendar above + לוח עבודה שלי).
                if   day in APPROVED_VAC: st.markdown(f"<div class='dc-vac'>🔵 {day}</div>",  unsafe_allow_html=True)
                elif day in APPROVED_202: st.markdown(f"<div class='dc-202'>🟡 {day}</div>",  unsafe_allow_html=True)
                elif day in PENDING:      st.markdown(f"<div class='dc-pend'>🔘 {day}</div>", unsafe_allow_html=True)
                elif day==s0 and not st.session_state.sel_end:
                    if st.button(f"▶{day}", key=f"ds_{day}", use_container_width=True):
                        st.session_state.sel_start=None; st.rerun()
                elif day in rng:
                    if st.button(f"✓{day}", key=f"dr_{day}", use_container_width=True):
                        st.session_state.sel_start=day; st.session_state.sel_end=None; st.rerun()
                else:
                    if st.button(str(day), key=f"df_{day}", use_container_width=True):
                        if   st.session_state.sel_start is None: st.session_state.sel_start=day
                        elif st.session_state.sel_end   is None and day!=st.session_state.sel_start:
                            st.session_state.sel_end=day
                        else:
                            st.session_state.sel_start=day; st.session_state.sel_end=None
                        st.rerun()

def render_day_legend():
    st.markdown("""<div style='direction:rtl;font-size:0.77rem;color:#64748b;margin:8px 0 0 0;line-height:2'>
    🔵 חופש מאושר &nbsp;|&nbsp; 🟡 202 מאושר &nbsp;|&nbsp; 🔘 בקשה ממתינה &nbsp;|&nbsp;
    <span style='border:1px solid #e2e8f0;padding:1px 8px;border-radius:5px;
    background:white;color:#334155'>27</span> פנוי (לחיצה לבחירה)</div>""", unsafe_allow_html=True)

def render_submission_form():
    s,e = st.session_state.sel_start, st.session_state.sel_end
    st.divider()
    if s and e:
        lo,hi = min(s,e),max(s,e)
        c1,c2,c3,c4 = st.columns([2,2,3,2])
        with c1: st.markdown(f"**נבחר:** {lo}/06 – {hi}/06")
        with c2: atype = st.selectbox("סוג:", ["חופש", "202"], label_visibility="collapsed")
        with c3: st.text_input("הערה:", placeholder="הערה (רשות)...", label_visibility="collapsed")
        with c4:
            if st.button("✅ הגש בקשה", use_container_width=True, key="submit_btn"):
                st.success(f"בקשת {atype} ל-{lo}–{hi}/06 נשלחה!"); st.session_state.sel_start=st.session_state.sel_end=None; st.rerun()
        if st.button("✖ בטל בחירה", key="cancel_sel"):
            st.session_state.sel_start=st.session_state.sel_end=None; st.rerun()
    elif s: st.info(f"📍 נבחר: {s}/06 — כעת לחץ על יום הסיום")
    else:   st.caption("💡 לחץ על יום פנוי בלוח לבחירת תאריך התחלה. חופש עתידי שאושר מראש מופיע בכחול בלוח.")

# ─────────────────────────────────────────────────────────────
# Department grid (manager / admin)
# ─────────────────────────────────────────────────────────────
STATUS_CYCLE = {"w":"h","h":"2","2":"p","p":"a","a":"w","e":"h"}
STATUS_LABEL = {"w":"עובד","h":"חופש","2":"202","p":"🔶 אחרי","a":"אחר","e":"עובד"}
STATUS_PFX   = {"w":"cell_w","h":"cell_h","2":"cell_2","p":"cell_p","a":"cell_a","e":"cell_e"}

def _get_status(emp, day, grid_data, key_ns=""):
    ck = f"{emp}_{day}_{key_ns}"
    if ck in st.session_state.cell_edit:
        return st.session_state.cell_edit[ck]
    return grid_data.get(emp, {}).get(day, "w")

def render_dept_grid(employees, grid_data, dept_label, key_ns=""):
    NUM_SHOW = 14   # first 14 days; real app would scroll
    days = list(range(1, NUM_SHOW + 1))

    # Header row
    cols = st.columns([2] + [1]*NUM_SHOW)
    cols[0].markdown("<div class='grid-hdr'>עובד</div>", unsafe_allow_html=True)
    for i, d in enumerate(days):
        wd = (JUNE1_IDX + d - 1) % 7   # 0=Sun … 5=Fri 6=Sat
        marker = " ו'" if wd == 5 else (" ש'" if wd == 6 else "")
        cols[i+1].markdown(f"<div class='grid-hdr'>{d}{marker}</div>", unsafe_allow_html=True)

    # Data rows
    for emp in employees:
        cols = st.columns([2] + [1]*NUM_SHOW)
        cols[0].markdown(f"<div class='grid-name'>{emp}</div>", unsafe_allow_html=True)
        for i, d in enumerate(days):
            cell_key = f"{emp}_{d}_{key_ns}"
            cell_status = _get_status(emp, d, grid_data, key_ns)
            pfx   = STATUS_PFX.get(cell_status, "cell_e")
            short = STATUS_LABEL.get(cell_status, "עובד")[:4]
            with cols[i+1]:
                if st.button(short, key=f"{pfx}_{cell_key}", use_container_width=True):
                    nxt = STATUS_CYCLE.get(cell_status, "w")
                    st.session_state.cell_edit[cell_key] = nxt
                    st.rerun()

def render_dept_with_export(employees, grid_data, dept_name, key_ns):
    render_dept_grid(employees, grid_data, dept_name, key_ns)
    st.markdown("""<div style='direction:rtl;font-size:0.77rem;color:#64748b;margin-top:6px'>
    <b>מקרא:</b> עובד &nbsp;|&nbsp; 🔵 חופש &nbsp;|&nbsp; 🟡 202 &nbsp;|&nbsp;
    🔶 אחרי תורנות &nbsp;|&nbsp; אחר</div>""", unsafe_allow_html=True)
    st.divider()
    cl, _, cr = st.columns([3, 2, 1])
    cl.caption(f"ייצוא לוח **{dept_name}** — שורות=עובדים, עמודות=ימים, ערכים=סטטוס")
    with cr:
        if st.button(f"📤 ייצא {dept_name[:8]}", key=f"exp_{key_ns}", use_container_width=True):
            with st.spinner("מייצא..."):
                import time; time.sleep(0.8)
            st.success(f"✅ {dept_name} יוצא לגיליון!")

# ─────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────
def view_hagashat_bakshot(role):
    st.markdown("## 📋 הגשת בקשות — יוני 2026")
    show_night = role in ("מתמחה","תורן חוץ")
    show_day   = role in ("מתמחה","רופא בכיר")

    if show_night:
        st.markdown("### 🌙 אילוצים לתורנויות לילה")
        with st.container(border=True):
            render_night_cal()
            cl,_,cr = st.columns([3,1,1])
            cl.caption("לחץ על יום: פנוי → 🔴 חסימה → ⭐ בקשה → פנוי")
            with cr:
                if st.button("💾 שמור אילוצים", use_container_width=True, key="save_night"):
                    st.success("אילוצי לילה נשמרו!")
    if show_night and show_day: st.divider()
    if show_day:
        st.markdown("### ☀️ היעדרות מעבודה יומית")
        if not st.session_state.req_open:
            st.warning("🔒 הגשות לחודש יוני נסגרו. ניתן להגיש חופש עתידי בלבד.")
        with st.container(border=True):
            render_day_cal()
            render_day_legend()
            render_submission_form()
        st.divider()
        st.markdown("#### 📋 היסטוריית בקשות")
        st.dataframe(MY_HISTORY, use_container_width=True, hide_index=True)


def view_tzevet_admin():
    """Admin צוות tab — only day absences per employee (no night shift view)"""
    st.markdown("## 👥 ניהול צוות — היעדרויות יומיות")
    st.caption("כאן מנהל/ת רואה ומאשר/ת היעדרויות יומיות לכל עובד. אילוצי תורנויות לילה מנוהלים בלוח השיבוץ.")

    emp = st.selectbox("בחר עובד:", [
        "יובל קירשנבוים (מתמחה — שיקום א')",
        "לין חיר אל דין (מתמחה — שיקום א')",
        "אורלי שמש (רופא בכיר — פנימית)",
        "בוריס גורוביץ (מתמחה — שיקום ב')",
    ])

    st.divider()
    st.markdown(f"#### בקשות היעדרות — {emp.split('(')[0].strip()}")

    req_for_emp = ALL_REQUESTS[ALL_REQUESTS["עובד"].str.contains(emp.split("(")[0].strip())]

    if req_for_emp.empty:
        st.info("אין בקשות היעדרות לעובד זה")
    else:
        for i,row in req_for_emp.iterrows():
            with st.container(border=True):
                c1,c2,c3,c4,c5 = st.columns([2,2,2,1,1])
                c1.markdown(f"**{row['תאריכים']}**")
                c2.write(row["סוג"])
                c3.write(row["סטטוס"])
                if "ממתין" in row["סטטוס"]:
                    if c4.button("✅ אשר", key=f"adm_ap_{i}", use_container_width=True):
                        st.success(f"אושרה בקשת {row['סוג']} ל-{row['תאריכים']}")
                    if c5.button("❌ דחה", key=f"adm_rj_{i}", use_container_width=True):
                        st.error(f"נדחתה בקשת {row['סוג']}")
                else:
                    c4.markdown(f"<span style='color:#16a34a'>✅ אושר</span>", unsafe_allow_html=True)


def view_sidur_yomi_admin():
    st.markdown("## 🗓️ סידור יומי — ניהול")
    OPEN_LABEL  = "🔓 סגור הגשות לחודש יוני"
    CLOSED_LABEL= "🔒 פתח הגשות לחודש יוני"

    tabs = st.tabs(["שיבוץ חודשי","לוח עבודה כללי","כל הבקשות","צור סידור","ייצוא"])

    # ── Tab 1: שיבוץ חודשי ──────────────────────────────────
    with tabs[0]:
        st.markdown("#### שיוך עובדים למחלקות — יוני 2026")
        status_lbl = "פתוח" if st.session_state.req_open else "סגור"
        status_col = "#16a34a" if st.session_state.req_open else "#dc2626"
        st.markdown(f"סטטוס הגשות: <span style='color:{status_col};font-weight:700'>{status_lbl}</span>",
                    unsafe_allow_html=True)

        btn_lbl = OPEN_LABEL if st.session_state.req_open else CLOSED_LABEL
        if st.button(btn_lbl, key="toggle_req"):
            st.session_state.req_open = not st.session_state.req_open; st.rerun()

        st.divider()
        updated = dict(st.session_state.rotation)
        for emp, current_dept in st.session_state.rotation.items():
            c1,c2 = st.columns([2,3])
            c1.markdown(f"<div style='padding:6px 0;font-weight:500'>{emp}</div>", unsafe_allow_html=True)
            new_dept = c2.selectbox("", DAILY_DEPTS,
                                    index=DAILY_DEPTS.index(current_dept) if current_dept in DAILY_DEPTS else 3,
                                    key=f"rot_{emp}", label_visibility="collapsed")
            updated[emp] = new_dept

        if st.button("💾 שמור שיבוץ חודשי", key="save_rotation"):
            st.session_state.rotation = updated
            st.success("שיבוץ חודשי נשמר!"); st.rerun()

    # ── Tab 2: לוח עבודה כללי ───────────────────────────────
    with tabs[1]:
        st.markdown("#### לוח עבודה כללי — יוני 2026")
        st.caption("לחץ על תא לשינוי סטטוס (מציג 14 ימים ראשונים). כפתור ייצוא לכל מחלקה בנפרד.")
        dept_tabs = st.tabs(["שיקום גריאטרי א'","שיקום גריאטרי ב'","פנימית גריאטרית"])
        with dept_tabs[0]:
            render_dept_with_export(EMPLOYEES_A, GRID_A, "שיקום גריאטרי א'", "A")
        with dept_tabs[1]:
            render_dept_with_export(EMPLOYEES_B, {}, "שיקום גריאטרי ב'", "B")
        with dept_tabs[2]:
            render_dept_with_export(EMPLOYEES_PN, {}, "פנימית גריאטרית", "PN")

    # ── Tab 3: כל הבקשות ────────────────────────────────────
    with tabs[2]:
        st.markdown("#### כל בקשות ההיעדרות הממתינות — יוני 2026")
        pending_df = ALL_REQUESTS[ALL_REQUESTS["סטטוס"].str.contains("ממתין")]
        if pending_df.empty:
            st.success("אין בקשות ממתינות ✅")
        else:
            for i,row in pending_df.iterrows():
                with st.container(border=True):
                    c1,c2,c3,c4,c5,c6 = st.columns([2,2,2,2,1,1])
                    c1.markdown(f"**{row['עובד']}**")
                    c2.write(row["תאריכים"])
                    c3.write(row["סוג"])
                    c4.write(row["מחלקה"])
                    if c5.button("✅", key=f"all_ap_{i}", use_container_width=True): st.success("אושר!")
                    if c6.button("❌", key=f"all_rj_{i}", use_container_width=True): st.error("נדחה!")

    # ── Tab 4: צור סידור ────────────────────────────────────
    with tabs[3]:
        st.markdown("#### יצירת סידור יומי — יוני 2026")
        st.info("לחיצה תייצר/תחדש את `work_schedule_daily` לחודש יוני. שורות עם `is_manual=True` לא ידרסו.")
        col1, col2 = st.columns([1,2])
        with col1:
            if st.button("⚡ צור סידור לחודש יוני", key="gen_sched", use_container_width=True):
                with st.spinner("מייצר סידור..."):
                    import time; time.sleep(1.5)
                st.success("✅ סידור יוני נוצר! 52 שורות נכתבו, 8 שורות ידניות שמורות.")
        with col2:
            st.markdown("""
            **לוגיקת יצירה:**
            - לכל עובד ב-`dept_rotation` ← כל יום בחודש
            - אם יש היעדרות מאושרת → status = סוג ההיעדרות
            - אחרת, אם עשה תורנות ביום הקודם → status = "אחרי תורנות"
            - אחרת → status = "עובד"
            """)

    # ── Tab 5: ייצוא ────────────────────────────────────────
    with tabs[4]:
        st.markdown("#### ייצוא סידור יומי — יוני 2026")
        st.caption("מייצא לגיליון Google Sheets ייעודי — לשונית נפרדת לכל מחלקה. עמודות=ימים, שורות=עובדים.")
        st.divider()
        for dept_name, exp_key in [
            ("שיקום גריאטרי א'", "exp_tab_A"),
            ("שיקום גריאטרי ב'", "exp_tab_B"),
            ("פנימית גריאטרית",  "exp_tab_PN"),
        ]:
            c1, c2 = st.columns([3, 1])
            c1.markdown(f"**{dept_name}** — לשונית נפרדת בגיליון הייצוא")
            with c2:
                if st.button(f"📤 ייצא", key=exp_key, use_container_width=True):
                    with st.spinner(f"מייצא {dept_name}..."):
                        import time; time.sleep(0.7)
                    st.success(f"✅ {dept_name} יוצא!")
        st.divider()
        if st.button("📤 ייצא את כל 3 המחלקות יחד", key="exp_all"):
            with st.spinner("מייצא הכל..."):
                import time; time.sleep(1.2)
            st.success("✅ 3 לשוניות עודכנו ב-Google Sheets!")


def view_sidur_yomi_manager():
    st.markdown("## 🗓️ סידור יומי — מנהל מחלקה")
    tabs = st.tabs(["לוח מחלקה","בקשות ממתינות"])

    with tabs[0]:
        st.markdown("#### לוח שיקום גריאטרי א' — יוני 2026")
        st.caption("לחץ על תא לשינוי. השורה שלך (רון) — עריכה ישירה ללא בקשה.")
        emps_with_mgr = ["רון (מנהל מחלקה)"] + EMPLOYEES_A
        mgr_grid = {**GRID_A, "רון (מנהל מחלקה)": {d:"w" for d in range(1,31)}}
        render_dept_with_export(emps_with_mgr, mgr_grid, "שיקום גריאטרי א'", "MGR")

    with tabs[1]:
        st.markdown("#### בקשות ממתינות — שיקום א'")
        my_dept_req = ALL_REQUESTS[ALL_REQUESTS["מחלקה"].str.contains("שיקום א")]
        pending = my_dept_req[my_dept_req["סטטוס"].str.contains("ממתין")]
        if pending.empty:
            st.success("אין בקשות ממתינות ✅")
        else:
            for i,row in pending.iterrows():
                with st.container(border=True):
                    c1,c2,c3,c4,c5 = st.columns([2,2,2,1,1])
                    c1.markdown(f"**{row['עובד']}**")
                    c2.write(row["תאריכים"]); c3.write(row["סוג"])
                    if c4.button("✅ אשר", key=f"mgr_ap_{i}", use_container_width=True): st.success("אושר!")
                    if c5.button("❌ דחה", key=f"mgr_rj_{i}", use_container_width=True): st.error("נדחה!")


def view_sidur_yomi_employee():
    st.markdown("## 🗓️ סידור יומי — לוח עבודה שלי")
    st.caption("יוני 2026 — קריאה בלבד. לחץ על תא לפרטים.")
    EMP_DATA = {d: GRID_A["יובל קירשנבוים"].get(d,"w") for d in range(1,31)}
    COLOR = {"w":"#dcfce7","h":"#dbeafe","2":"#fef9c3","p":"#ffedd5","a":"#f1f5f9","e":"#f8fafc"}
    LABEL = {"w":"עובד","h":"חופש","2":"202","p":"🔶 אחרי תורנות","a":"אחר","e":"עובד"}

    _day_header()
    for week in _grid():
        cols = st.columns(7)
        for ci,day in enumerate(week):
            with cols[ci]:
                if day is None:
                    st.markdown("<div class='dc-empty'></div>", unsafe_allow_html=True); continue
                s = EMP_DATA.get(day,"w")
                bg = COLOR.get(s,"#f8fafc")
                lbl = LABEL.get(s,"עובד")
                st.markdown(
                    f"<div style='background:{bg};border-radius:8px;padding:5px 2px;"
                    f"text-align:center;font-size:0.72rem;font-family:Rubik,sans-serif;"
                    f"min-height:34px;display:flex;align-items:center;justify-content:center;"
                    f"border:1px solid #e2e8f0'><b>{day}</b><br/>{lbl}</div>",
                    unsafe_allow_html=True)

    st.markdown("""<div style='direction:rtl;font-size:0.77rem;color:#64748b;margin:10px 0'>
    <span style='background:#dcfce7;padding:2px 8px;border-radius:4px'>עובד</span> &nbsp;
    <span style='background:#dbeafe;padding:2px 8px;border-radius:4px'>חופש</span> &nbsp;
    <span style='background:#fef9c3;padding:2px 8px;border-radius:4px'>202</span> &nbsp;
    <span style='background:#ffedd5;padding:2px 8px;border-radius:4px'>🔶 אחרי תורנות</span> &nbsp;
    <span style='background:#f1f5f9;padding:2px 8px;border-radius:4px'>אחר</span>
    </div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 👤 תפקיד + טאב")
    view = st.radio("", [
        "מתמחה — הגשת בקשות",
        "תורן חוץ — הגשת בקשות",
        "רופא בכיר — הגשת בקשות",
        "מנהל/ת — פאנל צוות (היעדרויות)",
        "מנהל/ת — סידור יומי",
        "מנהל מחלקה — סידור יומי",
        "מתמחה — לוח עבודה שלי",
    ], label_visibility="collapsed")
    st.divider()
    req_txt = "פתוח 🔓" if st.session_state.req_open else "סגור 🔒"
    st.caption(f"סטטוס הגשות יוני: **{req_txt}**")
    st.caption("🔧 מוק בלבד — נתוני יוני 2026 פיקטיביים")

# ─────────────────────────────────────────────────────────────
# Route
# ─────────────────────────────────────────────────────────────
if   view == "מתמחה — הגשת בקשות":              view_hagashat_bakshot("מתמחה")
elif view == "תורן חוץ — הגשת בקשות":            view_hagashat_bakshot("תורן חוץ")
elif view == "רופא בכיר — הגשת בקשות":           view_hagashat_bakshot("רופא בכיר")
elif view == "מנהל/ת — פאנל צוות (היעדרויות)":  view_tzevet_admin()
elif view == "מנהל/ת — סידור יומי":              view_sidur_yomi_admin()
elif view == "מנהל מחלקה — סידור יומי":          view_sidur_yomi_manager()
elif view == "מתמחה — לוח עבודה שלי":            view_sidur_yomi_employee()
