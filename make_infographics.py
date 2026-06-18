"""
make_infographics.py
Captures screenshots from the Streamlit shift-scheduling app and generates
HTML workflow infographics for each of the 6 user role types.

Usage:  python "D:/Projects/New Folder/make_infographics.py"
App must be running at http://localhost:8501
"""

import sys, os, time, base64, json
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ── Paths ────────────────────────────────────────────────────────────────────
BASE   = Path("D:/Projects/New Folder/infographics")
SS_DIR = BASE / "screenshots"
BASE.mkdir(exist_ok=True)
SS_DIR.mkdir(exist_ok=True)

APP_URL  = "http://localhost:8501"
PASSWORD = "1234"

# ── Known credentials per role ───────────────────────────────────────────────
CREDS = {
    "מנהל על":     "admin",
    "מנהל/ת":      "ציפי יעקב",
    "מנהל מחלקה":  "רון צליק",
    "מתמחה":       "בוריס גורוביץ",
    "רופא בכיר":   "אסנת שטיימן",
    "תורן חוץ":    "אחמד אלעמור",
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def wait(page, ms=2000):
    page.wait_for_timeout(ms)

def screenshot(page, name):
    path = SS_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    print(f"  📸 {name}.png")
    return str(path)

def click_tab(page, tab_text, retries=8):
    """Click a tab in the SAC iframe navbar. Returns True on success."""
    for _ in range(retries):
        result = page.evaluate(f"""
        (() => {{
          const sacFrame = Array.from(document.querySelectorAll('iframe'))
            .find(f => f.src && f.src.includes('sac'));
          if (!sacFrame) return 'no_frame';
          const doc = sacFrame.contentDocument || sacFrame.contentWindow.document;
          const btn = Array.from(doc.querySelectorAll('.ant-tabs-tab-btn'))
            .find(el => el.innerText && el.innerText.includes('{tab_text}'));
          if (btn) {{ btn.click(); return 'ok'; }}
          const all = Array.from(doc.querySelectorAll('.ant-tabs-tab-btn')).map(e=>e.innerText.trim()).join('|');
          return 'nf:' + all;
        }})()
        """)
        if result == 'ok':
            wait(page, 2200)
            return True
        if result.startswith('nf:'):
            return False  # tabs loaded but this tab not there
        # no_frame → iframe not ready yet
        time.sleep(0.6)
    return False

def visible_tabs(page, retries=12):
    """Return list of visible tab labels, waiting for SAC iframe."""
    for _ in range(retries):
        tabs = page.evaluate("""
        (() => {
          const sacFrame = Array.from(document.querySelectorAll('iframe'))
            .find(f => f.src && f.src.includes('sac'));
          if (!sacFrame) return null;
          const doc = sacFrame.contentDocument || sacFrame.contentWindow.document;
          const btns = doc.querySelectorAll('.ant-tabs-tab-btn');
          if (!btns.length) return null;
          return Array.from(btns).map(e=>e.innerText.trim());
        })()
        """)
        if tabs:
            return tabs
        time.sleep(0.5)
    return []

def current_role(page):
    tabs = visible_tabs(page)
    if not tabs:
        return 'unknown'
    if 'צוות' in tabs:                                        return 'מנהל על'
    if 'ניהול בקשות' in tabs and 'גאנט חודשי' in tabs:       return 'מנהל/ת'
    if 'ניהול בקשות' in tabs:                                 return 'מנהל מחלקה'
    if 'הגשת בקשות' in tabs and 'סידור תורנויות' in tabs:    return 'מתמחה'
    if 'הגשת בקשות' in tabs:                                  return 'רופא בכיר'
    if 'סידור תורנויות' in tabs:                              return 'תורן חוץ'
    return 'unknown:' + str(tabs)

def try_login(page, username, password=PASSWORD):
    """Log in. Returns True if successful."""
    try:
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=30000)

        # Wait for Streamlit to render (can take 8-15 s on cold start)
        try:
            page.wait_for_selector('input', timeout=25000)
        except PWTimeout:
            print(f"  ⚠️  Timeout waiting for input field")
            return False
        wait(page, 500)

        # If already logged in, log out first
        page_text = page.evaluate("document.body.innerText")
        if "התנתק" in page_text:
            do_logout(page)
            page.goto(APP_URL, wait_until="domcontentloaded", timeout=20000)
            try:
                page.wait_for_selector('input', timeout=20000)
            except PWTimeout:
                return False
            wait(page, 500)

        # Fill login form
        user_input = page.query_selector('input[aria-label="שם משתמש:"]') or \
                     page.query_selector('input[type="text"]')
        pass_input = page.query_selector('input[aria-label="סיסמה:"]') or \
                     page.query_selector('input[type="password"]')

        if not user_input or not pass_input:
            print(f"  ⚠️  Could not find login form inputs")
            return False

        user_input.click(); user_input.fill(username)
        pass_input.click(); pass_input.fill(password)

        # Click כניסה button
        btn = page.query_selector('button:has-text("כניסה")')
        if btn:
            btn.click()
        else:
            pass_input.press("Enter")

        # Wait for "התנתק" to appear (confirms Python code ran + user authenticated)
        # Google Sheets lookup can take 5-15 seconds
        try:
            page.wait_for_function(
                "document.body.innerText.includes('התנתק')",
                timeout=30000
            )
        except PWTimeout:
            # Login failed — check for error message
            txt = page.evaluate("document.body.innerText")[:200]
            print(f"  ✗  No התנתק after login (page: {txt[:80]!r})")
            return False

        # Now wait for SAC iframe to load tabs
        wait(page, 2500)
        tabs = visible_tabs(page, retries=30)
        if tabs:
            role = current_role(page)
            print(f"  ✅ Logged in as: '{username}'  →  role: {role}")
            return True

        print(f"  ✗  Logged in but no tabs visible for '{username}'")
        return False

    except Exception as e:
        print(f"  ⚠️  Error logging in as '{username}': {e}")
        return False

def do_logout(page):
    """Click the logout button."""
    try:
        btn = page.get_by_text("התנתק", exact=True)
        if btn.count():
            btn.first.click()
            wait(page, 2000)
            return True
    except:
        pass
    # Fallback: navigate to app root which resets session
    page.goto(APP_URL, wait_until="domcontentloaded", timeout=20000)
    wait(page, 1500)
    return False

# ── Static HTML fragments ─────────────────────────────────────────────────────

STATIC_FUTURE_ABSENCE_APPROVAL = """
<div class="static-section">
  <p class="static-intro">כאשר עובד/ת מגיש/ה <strong>חופש עתידי</strong> (לחודשים הבאים), הבקשה מגיעה ל<strong>ניהול בקשות</strong>:</p>
  <div class="wf-row">
    <div class="wf-box">
      <div class="wf-circle">1</div>
      <div class="wf-label">כנס/י ל<strong>ניהול בקשות</strong></div>
    </div>
    <div class="wf-arr">←</div>
    <div class="wf-box">
      <div class="wf-circle">2</div>
      <div class="wf-label">אתר/י הבקשה ב<strong>"בקשות ממתינות"</strong></div>
    </div>
    <div class="wf-arr">←</div>
    <div class="wf-box">
      <div class="wf-circle">3</div>
      <div class="wf-label">לחץ/י <strong>✅ אשר</strong> או <strong>❌ דחה</strong></div>
    </div>
    <div class="wf-arr">←</div>
    <div class="wf-box">
      <div class="wf-circle">4</div>
      <div class="wf-label">עובד/ת מקבל/ת <strong>הודעת מייל</strong> אוטומטית</div>
    </div>
  </div>
  <div class="static-note">
    📌 לאחר אישור — ניתן להוסיף היעדרות מאושרת ישירות מאותו טופס.
    הסטטוס מתעדכן אוטומטית בלוח העבודה של אותו חודש.
  </div>
</div>
"""

STATIC_FUTURE_ABSENCE_ADD = """
<div class="static-section">
  <p class="static-intro">ניתן להוסיף <strong>היעדרות מאושרת</strong> עבור כל עובד/ת ישירות מהמערכת — בלי שהעובד/ת יגיש/תגיש בקשה:</p>
  <div class="wf-row">
    <div class="wf-box">
      <div class="wf-circle">1</div>
      <div class="wf-label">כנס/י ל<strong>ניהול בקשות</strong></div>
    </div>
    <div class="wf-arr">←</div>
    <div class="wf-box">
      <div class="wf-circle">2</div>
      <div class="wf-label">גלול/י לחלק <strong>"הוספת היעדרות מאושרת"</strong></div>
    </div>
    <div class="wf-arr">←</div>
    <div class="wf-box">
      <div class="wf-circle">3</div>
      <div class="wf-label">בחר/י עובד/ת, סוג, תאריכים</div>
    </div>
    <div class="wf-arr">←</div>
    <div class="wf-box">
      <div class="wf-circle">4</div>
      <div class="wf-label">לחץ/י <strong>שמור</strong> — הבקשה מאושרת מיד</div>
    </div>
  </div>
</div>
"""

STATIC_ABSENCE_CONFLICT = """
<div class="static-section">
  <p class="static-intro">המערכת מתריעה כעת אוטומטית כש<strong>שני עובדים מאותה מחלקה</strong> נעדרים באותם ימים — בעת אישור בקשה או הוספת היעדרות:</p>
  <div class="wf-row">
    <div class="wf-box">
      <div class="wf-circle">1</div>
      <div class="wf-label">לחיצה על <strong>✅ אשר</strong> / <strong>שמור</strong> עם חפיפה במחלקה</div>
    </div>
    <div class="wf-arr">←</div>
    <div class="wf-box">
      <div class="wf-circle">2</div>
      <div class="wf-label">מופיעה <strong>אזהרת חפיפה</strong> עם שמות העובדים והתאריכים</div>
    </div>
    <div class="wf-arr">←</div>
    <div class="wf-box">
      <div class="wf-circle">3</div>
      <div class="wf-label">החלטה: <strong>✅ אשר למרות החפיפה</strong> או ביטול</div>
    </div>
  </div>
  <div class="static-note">
    🗑️ <strong>מחיקת בקשה מאושרת:</strong> פתח/י את החלק "מחיקת בקשה מאושרת", בחר/י את הבקשה ולחץ/י <strong>🗑️ מחק בקשה</strong> — ההיעדרות תוסר מלוח העבודה.
  </div>
</div>
"""

STATIC_PNIM_SIDES = """
<div class="static-section">
  <p class="static-intro">בלוח העבודה של <strong>פנימית גריאטרית</strong> העובדים מחולקים לשני צדדים, מסומנים בצבע לכל שבוע:</p>
  <div class="deadline-grid">
    <div class="dl-card" style="background:#fce7f315;border:1px solid #f9a8d4;">
      <div class="dl-head"><span class="dl-emoji">🌸</span><span class="dl-title">צד ורוד</span></div>
      <ul class="dl-list"><li>קבוצת עובדים אחת של פנימית</li></ul>
    </div>
    <div class="dl-card" style="background:#dbeafe15;border:1px solid #93c5fd;">
      <div class="dl-head"><span class="dl-emoji">🔵</span><span class="dl-title">צד כחול</span></div>
      <ul class="dl-list"><li>קבוצת העובדים השנייה</li></ul>
    </div>
  </div>
  <p class="static-intro" style="margin-top:10px;"><strong>➕ העברה זמנית</strong> — הוספת עובד/ת ממחלקה אחרת ליום מסוים:</p>
  <div class="wf-row">
    <div class="wf-box">
      <div class="wf-circle">1</div>
      <div class="wf-label">פתח/י <strong>"➕ העברה זמנית"</strong> מתחת ללוח</div>
    </div>
    <div class="wf-arr">←</div>
    <div class="wf-box">
      <div class="wf-circle">2</div>
      <div class="wf-label">בחר/י <strong>תאריך</strong>, <strong>עובד/ת</strong> (ובפנימית — צד 🌸/🔵)</div>
    </div>
    <div class="wf-arr">←</div>
    <div class="wf-box">
      <div class="wf-circle">3</div>
      <div class="wf-label">לביטול — <strong>✕ הסר</strong>; העובד/ת חוזר/ת למחלקת הבית</div>
    </div>
  </div>
</div>
"""

STATIC_INTERN_DEADLINES = """
<div class="static-section">
  <p class="static-intro">בלשונית <strong>הגשת בקשות</strong> יש שני סוגי הגשות, עם מועדי הגשה שונים:</p>
  <div class="deadline-grid">
    <div class="dl-card dl-night">
      <div class="dl-head">
        <span class="dl-emoji">🌙</span>
        <span class="dl-title">בקשת תורנויות</span>
        <span class="dl-badge dl-badge-night">עד ה-<strong>7</strong> לחודש</span>
      </div>
      <ul class="dl-list">
        <li>סמן/י ימי <strong>חסימה (אילוץ)</strong> — ימים שלא ניתן לשבץ</li>
        <li>סמן/י ימי <strong>בקשה</strong> — ימים שהיית מעדיף/ה לעבוד</li>
        <li>לחץ/י <strong>"שלח בקשות"</strong> לפני תאריך הסגירה</li>
      </ul>
    </div>
    <div class="dl-card dl-day">
      <div class="dl-head">
        <span class="dl-emoji">☀️</span>
        <span class="dl-title">חופש / יום 202</span>
        <span class="dl-badge dl-badge-day">עד ה-<strong>20</strong> לחודש</span>
      </div>
      <ul class="dl-list">
        <li>בחר/י <strong>טווח תאריכים</strong> לחופש או 202</li>
        <li>שלח/י בקשה → מנהל/ת המחלקה מאשר/ת</li>
        <li>מעקב סטטוס: ⏳ ממתין / ✅ מאושר / ❌ נדחה</li>
      </ul>
    </div>
  </div>
</div>
"""

STATIC_INTERN_FUTURE_ABSENCE = """
<div class="static-section">
  <p class="static-intro">ניתן להגיש בקשות חופש לחודשים <strong>הבאים</strong> בכל עת — גם כשההגשה לחודש הנוכחי סגורה:</p>
  <div class="wf-row">
    <div class="wf-box">
      <div class="wf-circle">1</div>
      <div class="wf-label">עבור/י ל<strong>הגשת בקשות</strong> ← <strong>☀️ חופש / 202</strong></div>
    </div>
    <div class="wf-arr">←</div>
    <div class="wf-box">
      <div class="wf-circle">2</div>
      <div class="wf-label">גלול/י לחלק <strong>"חופש עתידי"</strong></div>
    </div>
    <div class="wf-arr">←</div>
    <div class="wf-box">
      <div class="wf-circle">3</div>
      <div class="wf-label">בחר/י <strong>חופש עתידי</strong>, תאריכים ושלח/י</div>
    </div>
  </div>
  <div class="static-note">
    ✅ חופש עתידי מאושר מופיע אוטומטית בלוח העבודה בחודש הרלוונטי.
    הבקשה מועברת למנהל/ת המחלקה לאישור.
  </div>
</div>
"""

STATIC_SENIOR_FUTURE_ABSENCE = """
<div class="static-section">
  <p class="static-intro">ניתן להגיש בקשת חופש לחודשים הבאים בכל עת — ללא מגבלת תאריך הגשה:</p>
  <div class="wf-row">
    <div class="wf-box">
      <div class="wf-circle">1</div>
      <div class="wf-label">עבור/י ל<strong>הגשת בקשות</strong></div>
    </div>
    <div class="wf-arr">←</div>
    <div class="wf-box">
      <div class="wf-circle">2</div>
      <div class="wf-label">גלול/י לחלק <strong>"חופש עתידי"</strong></div>
    </div>
    <div class="wf-arr">←</div>
    <div class="wf-box">
      <div class="wf-circle">3</div>
      <div class="wf-label">בחר/י סוג, תאריכים ולחץ/י <strong>שלח</strong></div>
    </div>
    <div class="wf-arr">←</div>
    <div class="wf-box">
      <div class="wf-circle">4</div>
      <div class="wf-label">מנהל/ת מחלקה מאשר/ת</div>
    </div>
  </div>
</div>
"""

# ── Screenshot sequences per role ─────────────────────────────────────────────

def shots_manager_al(page):
    role = "super_admin"
    click_tab(page, "דוחות"); screenshot(page, f"{role}_01_reports")
    click_tab(page, "גאנט");   screenshot(page, f"{role}_02_gantt")
    click_tab(page, "סידור תורנויות"); screenshot(page, f"{role}_03_night_sched")
    click_tab(page, "סידור עבודה");    screenshot(page, f"{role}_04_work_sched")
    click_tab(page, "ניהול בקשות");    screenshot(page, f"{role}_05_requests")
    click_tab(page, "צוות");           screenshot(page, f"{role}_06_team")
    click_tab(page, "הגדרות");         screenshot(page, f"{role}_07_settings")
    return {
        "role_he": "מנהל על",
        "color": "#4f46e5",
        "icon": "🏥",
        "subtitle": "ניהול מלא של המערכת — סידורים, צוות, בקשות ודוחות",
        "steps": [
            {"tab": "דוחות וניהול", "icon": "📊", "img": f"{role}_01_reports",
             "caption": "צפייה בדוח הבעיות היומי, ניתוח שימוש משתמשים, בדיקת ימי חסימה קריטיים ועוד"},
            {"tab": "גאנט חודשי", "icon": "🗓️", "img": f"{role}_02_gantt",
             "caption": "שיוך עובדים למחלקות יומיות לחודש, הגדרת חודש פעיל, פתיחה/סגירת הגשות"},
            {"tab": "סידור תורנויות", "icon": "🌙", "img": f"{role}_03_night_sched",
             "caption": "לוח תורנויות לילה עם כל האילוצים והבקשות שהוגשו"},
            {"tab": "סידור עבודה", "icon": "📅", "img": f"{role}_04_work_sched",
             "caption": "בחירת מחלקה, עריכת לוח עבודה יומי, חלוקת פנימית לצד ורוד/כחול והעברה זמנית"},
            {"tab": "פנימית — צדדים והעברה זמנית", "icon": "🌸",
             "static_html": STATIC_PNIM_SIDES,
             "caption": ""},
            {"tab": "ניהול בקשות — אישור היעדרות עתידית", "icon": "🗂️",
             "img": f"{role}_05_requests",
             "caption": "אישור/דחיית בקשות היעדרות, צפייה בתצוגת גאנט של חופשות מאושרות עם בורר 12 חודשים קדימה"},
            {"tab": "תהליך אישור חופש עתידי", "icon": "✅",
             "static_html": STATIC_FUTURE_ABSENCE_APPROVAL,
             "caption": ""},
            {"tab": "הוספת היעדרות מאושרת ישירות", "icon": "➕",
             "static_html": STATIC_FUTURE_ABSENCE_ADD,
             "caption": ""},
            {"tab": "אזהרת חפיפה ומחיקת בקשה", "icon": "⚠️",
             "static_html": STATIC_ABSENCE_CONFLICT,
             "caption": ""},
            {"tab": "צוות", "icon": "👥", "img": f"{role}_06_team",
             "caption": "הוספה, עריכה והסרה של עובדים — שם, תפקיד, מחלקה, מכסה"},
            {"tab": "הגדרות", "icon": "⚙️", "img": f"{role}_07_settings",
             "caption": "שינוי סיסמה אישית"},
        ]
    }

def shots_manageret(page):
    role = "manager"
    click_tab(page, "גאנט");           screenshot(page, f"{role}_01_gantt")
    click_tab(page, "סידור עבודה");    screenshot(page, f"{role}_02_work_sched")
    click_tab(page, "ניהול בקשות");    screenshot(page, f"{role}_03_requests")
    click_tab(page, "הגדרות");         screenshot(page, f"{role}_04_settings")
    return {
        "role_he": "מנהל/ת",
        "color": "#0891b2",
        "icon": "👩‍💼",
        "subtitle": "ניהול סידור חודשי, לוח עבודה יומי ואישור בקשות היעדרות",
        "steps": [
            {"tab": "גאנט חודשי", "icon": "🗓️", "img": f"{role}_01_gantt",
             "caption": "שיוך עובדים למחלקות יומיות לפי חודש, הגדרת חודש פעיל, ייצוא סידור"},
            {"tab": "סידור עבודה", "icon": "📅", "img": f"{role}_02_work_sched",
             "caption": "צפייה ועריכה בלוח העבודה היומי לפי מחלקה, חלוקת פנימית לצד ורוד/כחול, העברה זמנית וייצוא לגיליון"},
            {"tab": "פנימית — צדדים והעברה זמנית", "icon": "🌸",
             "static_html": STATIC_PNIM_SIDES,
             "caption": ""},
            {"tab": "ניהול בקשות — אישור היעדרות עתידית", "icon": "🗂️",
             "img": f"{role}_03_requests",
             "caption": "אישור/דחיית בקשות היעדרות, צפייה בתצוגת גאנט של חופשות מאושרות עם בורר 12 חודשים קדימה"},
            {"tab": "תהליך אישור חופש עתידי", "icon": "✅",
             "static_html": STATIC_FUTURE_ABSENCE_APPROVAL,
             "caption": ""},
            {"tab": "הוספת היעדרות מאושרת ישירות", "icon": "➕",
             "static_html": STATIC_FUTURE_ABSENCE_ADD,
             "caption": ""},
            {"tab": "אזהרת חפיפה ומחיקת בקשה", "icon": "⚠️",
             "static_html": STATIC_ABSENCE_CONFLICT,
             "caption": ""},
            {"tab": "הגדרות", "icon": "⚙️", "img": f"{role}_04_settings",
             "caption": "שינוי סיסמה אישית"},
        ]
    }

def shots_dept_head(page):
    role = "dept_head"
    click_tab(page, "סידור עבודה");    screenshot(page, f"{role}_01_work_sched")
    click_tab(page, "ניהול בקשות");    screenshot(page, f"{role}_02_requests")
    click_tab(page, "הגדרות");         screenshot(page, f"{role}_03_settings")
    return {
        "role_he": "מנהל מחלקה",
        "color": "#059669",
        "icon": "🏢",
        "subtitle": "ניהול לוח עבודה ובקשות עובדי המחלקה",
        "steps": [
            {"tab": "סידור עבודה", "icon": "📅", "img": f"{role}_01_work_sched",
             "caption": "עריכת לוח עבודה יומי לעובדי המחלקה, חלוקת פנימית לצד ורוד/כחול, העברה זמנית וייצוא סידור"},
            {"tab": "פנימית — צדדים והעברה זמנית", "icon": "🌸",
             "static_html": STATIC_PNIM_SIDES,
             "caption": ""},
            {"tab": "ניהול בקשות — אישור היעדרות עתידית", "icon": "🗂️",
             "img": f"{role}_02_requests",
             "caption": "אישור/דחיית בקשות חופש של עובדי המחלקה, הוספת היעדרות מאושרת"},
            {"tab": "תהליך אישור חופש עתידי", "icon": "✅",
             "static_html": STATIC_FUTURE_ABSENCE_APPROVAL,
             "caption": ""},
            {"tab": "הוספת היעדרות מאושרת ישירות", "icon": "➕",
             "static_html": STATIC_FUTURE_ABSENCE_ADD,
             "caption": ""},
            {"tab": "אזהרת חפיפה ומחיקת בקשה", "icon": "⚠️",
             "static_html": STATIC_ABSENCE_CONFLICT,
             "caption": ""},
            {"tab": "הגדרות", "icon": "⚙️", "img": f"{role}_03_settings",
             "caption": "שינוי סיסמה אישית"},
        ]
    }

def shots_intern(page):
    role = "intern"
    click_tab(page, "הגשת בקשות");    screenshot(page, f"{role}_01_night_requests")
    page.evaluate("window.scrollBy(0, 500)"); wait(page, 800)
    screenshot(page, f"{role}_02_day_requests")
    click_tab(page, "סידור עבודה");   screenshot(page, f"{role}_03_work_cal")
    click_tab(page, "סידור תורנויות"); screenshot(page, f"{role}_04_night")
    click_tab(page, "הגדרות");        screenshot(page, f"{role}_05_settings")
    return {
        "role_he": "מתמחה",
        "color": "#7c3aed",
        "icon": "🩺",
        "subtitle": "הגשת בקשות תורנות ועיון בסידור עבודה אישי",
        "steps": [
            {"tab": "מועדי הגשה חשובים", "icon": "⏰",
             "static_html": STATIC_INTERN_DEADLINES,
             "caption": ""},
            {"tab": "הגשת אילוצים לתורנויות", "icon": "🌙",
             "img": "toranuyot",
             "caption": "בחירת ימי חסימה (אילוץ) ובקשה לתורנות — יש לשלוח לפני ה-7 לחודש"},
            {"tab": "הגשת בקשות ☀️ — חופש / 202", "icon": "☀️",
             "img": "daily",
             "caption": "הגשת בקשת חופש/202 לטווח תאריכים — יש לשלוח לפני ה-20 לחודש"},
            {"tab": "הגשת חופש עתידי", "icon": "🗓️",
             "static_html": STATIC_INTERN_FUTURE_ABSENCE,
             "img": "future_absence",
             "caption": ""},
            {"tab": "סידור עבודה", "icon": "📅", "img": "sidur",
             "caption": "לוח עבודה אישי לקריאה בלבד — צבע לכל סטטוס יומי"},
            {"tab": "הגדרות", "icon": "⚙️", "img": f"{role}_05_settings",
             "caption": "שינוי סיסמה אישית"},
        ]
    }

def shots_senior_doc(page):
    role = "senior_doctor"
    click_tab(page, "הגשת בקשות");   screenshot(page, f"{role}_01_absences")
    click_tab(page, "סידור עבודה");  screenshot(page, f"{role}_02_work_cal")
    click_tab(page, "הגדרות");       screenshot(page, f"{role}_03_settings")
    return {
        "role_he": "רופא בכיר",
        "color": "#b45309",
        "icon": "👨‍⚕️",
        "subtitle": "הגשת בקשות היעדרות ועיון בסידור עבודה יומי",
        "steps": [
            {"tab": "הגשת בקשות ☀️", "icon": "☀️", "img": "daily",
             "caption": "הגשת בקשות חופש/202 לפי טווח תאריכים"},
            {"tab": "הגשת חופש עתידי", "icon": "🗓️",
             "static_html": STATIC_SENIOR_FUTURE_ABSENCE,
             "img": "future_absence",
             "caption": ""},
            {"tab": "סידור עבודה", "icon": "📅", "img": "sidur",
             "caption": "לוח עבודה אישי לקריאה בלבד — סטטוס כל יום בצבע"},
            {"tab": "הגדרות", "icon": "⚙️", "img": f"{role}_03_settings",
             "caption": "שינוי סיסמה אישית"},
        ]
    }

def shots_extern(page):
    role = "extern"
    click_tab(page, "הגשת בקשות");     screenshot(page, f"{role}_01_constraints")
    click_tab(page, "סידור תורנויות"); screenshot(page, f"{role}_02_night")
    click_tab(page, "הגדרות");         screenshot(page, f"{role}_03_settings")
    return {
        "role_he": "תורן חוץ",
        "color": "#dc2626",
        "icon": "🔄",
        "subtitle": "הגשת אילוצי תורנות ועיון בשיבוצי לילה",
        "steps": [
            {"tab": "הגשת בקשות 🌙", "icon": "🌙", "img": f"{role}_01_constraints",
             "caption": "סימון ימי חסימה (אילוץ) ובקשות לתורנות לחודש הפעיל"},
            {"tab": "סידור תורנויות", "icon": "📋", "img": f"{role}_02_night",
             "caption": "צפייה בלוח תורנויות הלילה לחודש הנוכחי"},
            {"tab": "הגדרות", "icon": "⚙️", "img": f"{role}_03_settings",
             "caption": "שינוי סיסמה אישית"},
        ]
    }

SHOT_FNS = {
    "מנהל על":    shots_manager_al,
    "מנהל/ת":     shots_manageret,
    "מנהל מחלקה": shots_dept_head,
    "מתמחה":      shots_intern,
    "רופא בכיר":  shots_senior_doc,
    "תורן חוץ":   shots_extern,
}

FILE_NAMES = {
    "מנהל על":    "infographic_super_admin.html",
    "מנהל/ת":     "infographic_manager.html",
    "מנהל מחלקה": "infographic_dept_head.html",
    "מתמחה":      "infographic_intern.html",
    "רופא בכיר":  "infographic_senior_doctor.html",
    "תורן חוץ":   "infographic_extern.html",
}

# ── HTML generation ───────────────────────────────────────────────────────────

SYMBOL_LEGEND_HTML = """
<div class="legend-section">
  <h3 class="legend-title">🔑 מקרא סטטוסים</h3>
  <div class="legend-grid">
    <div class="legend-item"><span class="lsym lsym-e">ע</span><span class="lname">עובד</span></div>
    <div class="legend-item"><span class="lsym lsym-h">ח</span><span class="lname">חופש</span></div>
    <div class="legend-item"><span class="lsym lsym-2">202</span><span class="lname">יום 202</span></div>
    <div class="legend-item"><span class="lsym lsym-a">א</span><span class="lname">אחרי תורנות</span></div>
    <div class="legend-item"><span class="lsym lsym-o">+</span><span class="lname">אחר</span></div>
    <div class="legend-item"><span class="lsym lsym-t">ת</span><span class="lname">תורנות לילה</span></div>
  </div>
</div>
"""

def img_to_b64(img_name):
    path = SS_DIR / f"{img_name}.png"
    if not path.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()

def build_html(info):
    role_he  = info["role_he"]
    color    = info["color"]
    icon     = info["icon"]
    subtitle = info["subtitle"]
    steps    = info["steps"]

    cards_html = ""
    for i, step in enumerate(steps, 1):
        if step.get("static_html"):
            # Static workflow / info card — may optionally also show a screenshot
            caption_html = (f'<p class="step-caption">{step["caption"]}</p>'
                            if step.get("caption") else "")
            img_html = ""
            if step.get("img"):
                _img_data = img_to_b64(step["img"])
                img_html = (f'<img src="{_img_data}" alt="{step["tab"]}" class="step-img">'
                            if _img_data else
                            '<div class="step-img no-img">🖼️ אין תמונה</div>')
            cards_html += f"""
    <div class="step-card static-card">
      <div class="step-num" style="background:{color}">{i}</div>
      <div class="step-header">
        <span class="step-icon">{step['icon']}</span>
        <span class="step-tab">{step['tab']}</span>
      </div>
      <div class="step-static-body">{step['static_html']}</div>
      {img_html}
      {caption_html}
    </div>"""
        else:
            img_data = img_to_b64(step["img"])
            img_tag  = (f'<img src="{img_data}" alt="{step["tab"]}" class="step-img">'
                        if img_data else
                        '<div class="step-img no-img">🖼️ אין תמונה</div>')
            cards_html += f"""
    <div class="step-card">
      <div class="step-num" style="background:{color}">{i}</div>
      <div class="step-header">
        <span class="step-icon">{step['icon']}</span>
        <span class="step-tab">{step['tab']}</span>
      </div>
      {img_tag}
      <p class="step-caption">{step['caption']}</p>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>מדריך שימוש — {role_he}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Rubik:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Rubik', sans-serif; background: #f8fafc; color: #1e293b; direction: rtl; }}

  .header {{
    background: {color}; color: #fff; padding: 36px 48px 30px;
    display: flex; align-items: center; gap: 20px;
  }}
  .header-icon {{ font-size: 52px; line-height: 1; }}
  .header-text h1 {{ font-size: 1.85rem; font-weight: 700; margin-bottom: 6px; }}
  .header-text p  {{ font-size: 0.98rem; opacity: 0.88; }}

  /* ── Symbol legend ── */
  .legend-section {{
    background: #fff; margin: 24px 48px 0;
    padding: 18px 22px; border-radius: 12px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.09);
  }}
  .legend-title {{ font-size: 1rem; font-weight: 600; color: #1e293b; margin-bottom: 12px; }}
  .legend-grid {{
    display: flex; flex-wrap: wrap; gap: 10px 24px;
  }}
  .legend-item {{ display: flex; align-items: center; gap: 8px; font-size: 0.88rem; color: #475569; }}
  .lsym {{
    display: inline-flex; align-items: center; justify-content: center;
    width: 30px; height: 30px; border-radius: 6px;
    font-weight: 700; font-size: 0.82rem; color: #fff;
  }}
  .lsym-e  {{ background: #16a34a; }}
  .lsym-h  {{ background: #2563eb; }}
  .lsym-2  {{ background: #ca8a04; font-size: 0.65rem; }}
  .lsym-a  {{ background: #ea580c; }}
  .lsym-o  {{ background: #6b7280; }}
  .lsym-t  {{ background: #7c3aed; }}

  .login-note {{
    background: #fff; border-right: 4px solid {color}; margin: 18px 48px 0;
    padding: 14px 18px; border-radius: 8px; font-size: 0.9rem; color: #475569;
    box-shadow: 0 1px 3px rgba(0,0,0,0.07); display: flex; gap: 10px;
  }}
  .login-note strong {{ color: #1e293b; }}

  .steps {{
    display: grid; grid-template-columns: repeat(auto-fill, minmax(390px, 1fr));
    gap: 22px; padding: 24px 48px 48px;
  }}
  .step-card {{
    background: #fff; border-radius: 14px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.10), 0 3px 10px rgba(0,0,0,0.05);
    overflow: hidden; display: flex; flex-direction: column; position: relative;
    page-break-inside: avoid;
  }}
  .step-card.static-card {{ border-right: 4px solid {color}; }}
  .step-num {{
    position: absolute; top: 12px; right: 12px;
    width: 32px; height: 32px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 0.9rem; color: #fff; z-index: 2;
    box-shadow: 0 2px 5px rgba(0,0,0,0.22);
  }}
  .step-header {{ padding: 14px 18px 8px; padding-right: 54px; display: flex; align-items: center; gap: 8px; }}
  .step-icon  {{ font-size: 1.2rem; }}
  .step-tab   {{ font-size: 1rem; font-weight: 600; color: #1e293b; }}
  .step-img   {{
    width: 100%; display: block;
    border-top: 1px solid #f1f5f9; border-bottom: 1px solid #f1f5f9;
    max-height: 320px; object-fit: cover; object-position: top;
  }}
  .no-img {{
    height: 160px; display: flex; align-items: center; justify-content: center;
    font-size: 1.8rem; background: #f1f5f9; color: #94a3b8;
  }}
  .step-caption {{ padding: 12px 18px 16px; font-size: 0.87rem; color: #475569; line-height: 1.6; flex: 1; }}

  /* ── Static card body ── */
  .step-static-body {{ padding: 10px 18px 14px; }}

  .static-section {{ font-size: 0.87rem; color: #374151; }}
  .static-intro {{ margin-bottom: 12px; line-height: 1.6; }}

  /* workflow row */
  .wf-row {{ display: flex; flex-wrap: wrap; align-items: stretch; gap: 6px; margin-bottom: 12px; }}
  .wf-box {{
    flex: 1; min-width: 100px; background: #f8fafc;
    border: 1px solid #e2e8f0; border-radius: 8px;
    padding: 10px 10px 10px 10px; display: flex; flex-direction: column; gap: 6px;
    align-items: center; text-align: center;
  }}
  .wf-circle {{
    width: 26px; height: 26px; border-radius: 50%; background: {color};
    color: #fff; font-weight: 700; font-size: 0.8rem;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
  }}
  .wf-label {{ font-size: 0.82rem; color: #374151; line-height: 1.45; }}
  .wf-label strong {{ color: #1e293b; }}
  .wf-arr {{ align-self: center; font-size: 1.1rem; color: #94a3b8; flex-shrink: 0; }}

  .static-note {{
    background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px;
    padding: 8px 12px; font-size: 0.82rem; color: #166534; line-height: 1.5;
    margin-top: 8px;
  }}

  /* deadline grid */
  .deadline-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 6px; }}
  .dl-card {{ border-radius: 8px; padding: 12px; }}
  .dl-night {{ background: #1e1b4b10; border: 1px solid #a5b4fc; }}
  .dl-day   {{ background: #fefce810; border: 1px solid #fde047; }}
  .dl-head {{ display: flex; align-items: center; gap: 6px; margin-bottom: 8px; flex-wrap: wrap; }}
  .dl-emoji {{ font-size: 1.1rem; }}
  .dl-title {{ font-weight: 600; font-size: 0.88rem; color: #1e293b; }}
  .dl-badge {{
    margin-right: auto; padding: 2px 8px; border-radius: 999px;
    font-size: 0.75rem; font-weight: 600;
  }}
  .dl-badge-night {{ background: #4f46e5; color: #fff; }}
  .dl-badge-day   {{ background: #ca8a04; color: #fff; }}
  .dl-list {{ padding-right: 16px; font-size: 0.82rem; color: #374151; line-height: 1.7; }}

  @media print {{
    @page {{ margin: 10mm; size: A4; }}
    body {{ background: #fff; }}
    .header {{ print-color-adjust: exact; -webkit-print-color-adjust: exact; }}
    .step-num {{ print-color-adjust: exact; -webkit-print-color-adjust: exact; }}
    .steps {{ padding: 12px 0 0; }}
    .step-card {{ box-shadow: 0 0 0 1px #e2e8f0; break-inside: avoid; }}
    .legend-section {{ margin: 12px 0 0; }}
    .login-note {{ margin: 8px 0 0; }}
    .dl-badge {{ print-color-adjust: exact; -webkit-print-color-adjust: exact; }}
    .wf-circle {{ print-color-adjust: exact; -webkit-print-color-adjust: exact; }}
    .lsym {{ print-color-adjust: exact; -webkit-print-color-adjust: exact; }}
  }}
</style>
</head>
<body>

<div class="header">
  <div class="header-icon">{icon}</div>
  <div class="header-text">
    <h1>מדריך שימוש — {role_he}</h1>
    <p>{subtitle}</p>
  </div>
</div>

{SYMBOL_LEGEND_HTML}

<div class="login-note">
  <span>🔐</span>
  <div>
    <strong>כניסה למערכת:</strong> הכנס/י שם משתמש וסיסמה.
    לשינוי סיסמה — עבור/י ל<strong>הגדרות ← שינוי סיסמה</strong>.
  </div>
</div>

<div class="steps">
{cards_html}
</div>
</body>
</html>"""

# ── Main ──────────────────────────────────────────────────────────────────────

ROLE_ORDER = ["מנהל על", "מנהל/ת", "מנהל מחלקה", "מתמחה", "רופא בכיר", "תורן חוץ"]

def main():
    results = {}

    print("\n🚀 Starting screenshot capture...")
    print(f"   App:        {APP_URL}")
    print(f"   Output dir: {BASE}\n")

    PW_PROFILE = Path("D:/Projects/tmp/pw_profile")
    PW_PROFILE.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        # launch_persistent_context stores ALL browser data on D: (C: is full)
        ctx = pw.chromium.launch_persistent_context(
            str(PW_PROFILE),
            headless=True,
            viewport={"width": 1440, "height": 900},
            args=["--disable-dev-shm-usage"],
        )
        page = ctx.new_page()

        # Login page screenshot (before any login)
        print("[0] Login page screenshot")
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_selector('input', timeout=25000)
            wait(page, 800)
        except PWTimeout:
            pass
        screenshot(page, "login_screen")

        # Each role
        for role_key in ROLE_ORDER:
            username = CREDS.get(role_key)
            if not username:
                print(f"\n[{role_key}] ⚠️  No credentials — skipping")
                continue

            print(f"\n[{role_key}] Logging in as '{username}'...")
            if not try_login(page, username):
                print(f"  ⚠️  Login failed — skipping role")
                continue

            print(f"  Taking screenshots...")
            try:
                info = SHOT_FNS[role_key](page)
                results[role_key] = info
            except Exception as e:
                print(f"  ⚠️  Error taking screenshots: {e}")

            do_logout(page)

        ctx.close()

    # ── Generate HTML ──
    print("\n\n📄 Generating HTML files...")
    login_step = {
        "tab": "כניסה למערכת",
        "icon": "🔐",
        "img": "login_screen",
        "caption": "הזן/י שם משתמש וסיסמה. בכניסה ראשונה — שנה/י סיסמה בהגדרות."
    }
    for role_key in ROLE_ORDER:
        if role_key not in results:
            continue
        info = results[role_key]
        info["steps"] = [login_step] + info["steps"]
        html = build_html(info)
        out_path = BASE / FILE_NAMES[role_key]
        out_path.write_text(html, encoding="utf-8")
        print(f"  ✅ {out_path.name}")

    print(f"\n🎉 Done! {len(results)} infographic(s) in {BASE}")


class _NullPage:
    """Dummy page object used in --html-only mode so shots_*() can run without a browser."""
    def evaluate(self, *a, **kw): return 'ok'   # satisfies click_tab's result == 'ok' check
    def query_selector(self, *a, **kw): return None
    def screenshot(self, *a, **kw): pass
    def wait_for_timeout(self, *a, **kw): pass
    def goto(self, *a, **kw): pass
    def wait_for_selector(self, *a, **kw): pass
    def wait_for_function(self, *a, **kw): pass
    def get_by_text(self, *a, **kw): return self
    def count(self): return 0
    def first(self): return self
    def click(self, *a, **kw): pass
    def fill(self, *a, **kw): pass
    def press(self, *a, **kw): pass


# Short CLI aliases → role keys (for selective html-only regeneration)
ROLE_ALIASES = {
    "super_admin": "מנהל על",   "admin": "מנהל על",
    "manager": "מנהל/ת",
    "dept_head": "מנהל מחלקה",
    "intern": "מתמחה",
    "senior_doctor": "רופא בכיר", "senior": "רופא בכיר",
    "extern": "תורן חוץ",
}


def regen_html_only(only=None):
    """Rebuild HTML files from existing screenshots + static content (no browser).

    only : optional list of role_keys to limit regeneration to (default: all roles).
    """
    print("\n📄 Re-generating HTML from existing screenshots (html-only mode)...")
    _null = _NullPage()
    login_step = {
        "tab": "כניסה למערכת", "icon": "🔐", "img": "login_screen",
        "caption": "הזן/י שם משתמש וסיסמה. בכניסה ראשונה — שנה/י סיסמה בהגדרות."
    }
    targets = only if only else ROLE_ORDER
    for role_key in targets:
        shot_fn = SHOT_FNS[role_key]
        try:
            info = shot_fn(_null)
        except Exception as e:
            print(f"  ⚠️  Could not build info for {role_key}: {e}")
            continue
        info["steps"] = [login_step] + info["steps"]
        html = build_html(info)
        out_path = BASE / FILE_NAMES[role_key]
        out_path.write_text(html, encoding="utf-8")
        print(f"  ✅ {out_path.name}")
    print("Done.")


if __name__ == "__main__":
    if "--html-only" in sys.argv:
        # Patch screenshot() to silently skip (images already on disk from prior run)
        _orig_screenshot = screenshot
        def screenshot(page, name):  # noqa: F811
            path = SS_DIR / f"{name}.png"
            if path.exists():
                print(f"  (reuse) {name}.png")
            else:
                print(f"  (missing) {name}.png — will show placeholder")
            return str(path)
        # Any extra args after --html-only select specific roles, e.g.
        #   python make_infographics.py --html-only intern senior_doctor
        sel = [a for a in sys.argv[1:] if a != "--html-only"]
        only = None
        if sel:
            only = []
            for a in sel:
                key = ROLE_ALIASES.get(a, a)
                if key in SHOT_FNS:
                    only.append(key)
                else:
                    print(f"  ⚠️  Unknown role '{a}' — valid: {', '.join(ROLE_ALIASES)}")
        regen_html_only(only)
    else:
        main()
