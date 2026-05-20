import streamlit as st
import streamlit_antd_components as sac
import streamlit_shadcn_ui as ui

def setup_style():
    """Injects the global CSS for the Medical Slate & Indigo theme.
    Guarded with a session-state flag so the 11 KB CSS block is only
    injected once per session (not on every Streamlit rerun).
    """
    if st.session_state.get('_style_injected'):
        return
    st.session_state['_style_injected'] = True
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Rubik:wght@300;400;500;700&display=swap');
    
    /* --- Global Reset & Typography --- */
    html, body, [data-testid="stAppViewContainer"], .main { 
        direction: rtl; 
        text-align: right !important; 
        font-family: 'Rubik', sans-serif;
        background-color: #f8fafc; /* Slate 50 - Lighter, cleaner background */
        color: #1e293b; /* Slate 800 */
    }
    
    /* --- Streamlit Component Overrides --- */
    h1, h2, h3, h4, h5, h6 { color: #0f172a !important; font-weight: 700; }
    p, label { color: #334155 !important; }
    
    /* --- Main Header Layout --- */
    .main-header {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
        margin-bottom: 2rem;
        gap: 0.5rem;
        width: 100%;
    }
    .main-header h1 {
        margin: 0 !important;
        font-size: 2rem !important;
    }
    .header-actions {
        display: flex;
        justify-content: center;
        width: 100%;
    }
    
    /* Buttons (Modern Indigo) */
    div.stButton > button {
        background-color: #4f46e5; /* Indigo 600 */
        color: white !important;
        border-radius: 10px;
        border: none;
        padding: 0.6rem 1.2rem;
        font-weight: 500;
        box-shadow: 0 4px 6px -1px rgba(79, 70, 229, 0.1);
        transition: all 0.2s;
    }
    div.stButton > button:hover {
        background-color: #4338ca; /* Indigo 700 */
        box-shadow: 0 10px 15px -3px rgba(79, 70, 229, 0.2);
    }

    /* Tabs - Forced RTL */
    .stTabs [data-baseweb="tab-list"] {
        direction: rtl;
        justify-content: flex-start;
        gap: 8px;
        float: right; /* Helps force alignment in some containers */
    }
    .stTabs [data-baseweb="tab-panel"] {
        direction: rtl;
        text-align: right;
    }
    
    /* --- Card Styling (for Mobile Feed) --- */
    .shift-card {
        background: white;
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        border: 1px solid #e2e8f0;
        margin-bottom: 12px;
        transition: transform 0.2s;
    }
    .shift-card:active { transform: scale(0.98); }
    
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
    .card-date { font-weight: 700; color: #334155; font-size: 1.1rem; }
    .card-badge { padding: 4px 8px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; }
    
    /* Status Colors */
    .status-ok { background: #dcfce7; color: #166534; } /* Green */
    .status-warn { background: #fef9c3; color: #854d0e; } /* Yellow */
    .status-err { background: #fee2e2; color: #991b1b; } /* Red */

    /* Hide Default Elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* --- Aggressive Layout Fixes --- */
    /* Hide Streamlit's default header decoration/hamburger if causing space issues */
    header[data-testid="stHeader"] {
        background: transparent;
        visibility: hidden; /* Hide the top bar entirely if desired for clean look */
    }
    
    .main .block-container { 
        padding-top: 1rem !important; 
        padding-bottom: 80px; 
    }

    /* --- ULTRA-AGGRESSIVE Button Styling --- */
    /* Force ALL buttons to premium Indigo */
    button, 
    div[data-testid="stButton"] > button, 
    div[data-testid="stFormSubmitButton"] > button,
    .stButton > button,
    [kind="primary"],
    [kind="secondary"] {
        background: linear-gradient(135deg, #4f46e5 0%, #4338ca 100%) !important;
        background-image: linear-gradient(135deg, #4f46e5 0%, #4338ca 100%) !important;
        color: white !important;
        transition: all 0.2s ease-in-out !important;
        box-shadow: 0 4px 6px -1px rgba(79, 70, 229, 0.2), 0 2px 4px -1px rgba(79, 70, 229, 0.1) !important;
        border: none !important;
        border-radius: 12px !important;
        font-weight: 500 !important;
        letter-spacing: 0.5px !important;
        padding-top: 0.5rem !important;
        padding-bottom: 0.5rem !important;
    }
    button *,
    div[data-testid="stButton"] > button *,
    div[data-testid="stFormSubmitButton"] > button * {
        color: white !important;
    }
    button:hover,
    div[data-testid="stButton"] > button:hover, 
    div[data-testid="stFormSubmitButton"] > button:hover,
    .stButton > button:hover {
        background: linear-gradient(135deg, #4338ca 0%, #3730a3 100%) !important;
        background-image: linear-gradient(135deg, #4338ca 0%, #3730a3 100%) !important;
        color: white !important;
        border: none !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 10px 15px -3px rgba(79, 70, 229, 0.3), 0 4px 6px -2px rgba(79, 70, 229, 0.15) !important;
    }
    button:active,
    div[data-testid="stButton"] > button:active, 
    div[data-testid="stFormSubmitButton"] > button:active,
    .stButton > button:active {
        transform: translateY(0) !important;
        box-shadow: 0 2px 4px -1px rgba(79, 70, 229, 0.2) !important;
    }

    /* --- Custom Checkbox Styling (Large & Round) --- */
    div[data-testid="stCheckbox"] label span[role="checkbox"] {
        width: 1.5rem !important;
        height: 1.5rem !important;
        border-radius: 50% !important; /* Make it round */
        border: 2px solid #cbd5e1 !important;
        transition: all 0.2s ease-in-out;
    }
    
    /* Checked State */
    div[data-testid="stCheckbox"] label span[role="checkbox"][aria-checked="true"] {
        background-color: #4f46e5 !important; /* Indigo 600 */
        border-color: #4f46e5 !important;
    }
    
    /* Align checkbox to center in grid cells */
    div[data-testid="stCheckbox"] {
        justify-content: center !important;
        padding-top: 4px;
    }

    /* RTL Alignment Fixes for Selectbox & Input */
    div[data-testid="stSelectbox"] div[data-baseweb="select"] {
        direction: rtl;
        text-align: right;
    }
    div[data-testid="stSelectbox"] label, div[data-testid="stSelectbox"] label p {
        text-align: right !important;
        width: 100%;
        direction: rtl;
    }
    
    
    /* --- ULTRA-AGGRESSIVE Navbar RTL Fix --- */
    /* Force the entire menu container to RTL */
    div[class*="ant-menu"] {
        direction: rtl !important;
    }
    
    /* Force text to stick to the right side */
    .ant-menu-item {
        flex-direction: row !important; /* Keep natural flow in RTL */
        justify-content: flex-start !important; /* Start from the right in RTL */
        text-align: right !important;
        direction: rtl !important;
        padding-right: 24px !important;
        padding-left: 16px !important;
    }
    
    /* Force text content to align right */
    .ant-menu-title-content,
    .ant-menu-item-content,
    .ant-menu-item span {
        text-align: right !important;
        direction: rtl !important;
        display: inline-block !important;
    }
    
    /* Move icon to the right side */
    .ant-menu-item .anticon {
        margin-left: 12px !important; /* Space between icon and text */
        margin-right: 0 !important;
    }
    
    /* Force the menu item content to be on the right */
    .ant-menu-item-content {
        flex: 1 !important;
        text-align: right !important;
    }
    
    /* --- Force Navbar Background Color --- */
    .ant-menu-item-selected,
    .ant-menu-item-active,
    .ant-menu-item:hover {
        background-color: #4f46e5 !important;
        background: #4f46e5 !important;
    }
    /* Force all menu items to have indigo background when filled variant */
    [class*="ant-menu"][class*="filled"] .ant-menu-item {
        background-color: #4f46e5 !important;
    }
    
    /* --- Chip Background Styling --- */
    /* Make selected chips have light background matching page */
    .ant-tag-checkable-checked {
        background-color: rgba(79, 70, 229, 0.1) !important;
        border-color: #4f46e5 !important;
        color: #4f46e5 !important;
    }
    .ant-tag-checkable {
        background-color: white !important;
    }
    
    /* --- Minimize Column Padding for Chip Grid --- */
    /* Remove padding but specifically target chip areas */
    div.calendar-grid-container div[data-testid="column"] {
        padding: 2px !important;
    }
    
    /* Make chip containers fit content */
    .ant-tag {
        margin: 2px auto !important;
        display: block !important;
        width: fit-content !important;
    }

    /* --- Calendar Assignment Styling (Button-like) --- */
    .slot {
        background-color: #4f46e5 !important; /* Indigo 600 */
        color: white !important;
        padding: 4px 8px !important;
        border-radius: 6px !important;
        margin-top: 4px !important;
        font-size: 0.85rem !important;
        text-align: center !important;
        display: block !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1) !important;
        border: none !important;
    }
    .slot span, .dept-label {
        color: white !important;
    }
    .dept-label {
        font-weight: 700 !important;
        margin-left: 4px !important;
        opacity: 0.9;
    }
    .empty-slot {
        background-color: #f1f5f9 !important; /* Slate 100 */
        color: #64748b !important; /* Slate 500 */
        border: 1px dashed #cbd5e1 !important;
    }
    .empty-slot span {
        color: #64748b !important;
    }

    /* Optimized Single-Component Calendar Grid via Key Targeting */
    /* Target via Flex-Wrap detection (Most robust for SAC) */
    div[class*="st-key-const_batch"] div[style*="wrap"],
    div[class*="st-key-wish_batch"] div[style*="wrap"] {
        display: grid !important;
        grid-template-columns: repeat(7, 1fr) !important;
        gap: 6px !important;
        justify-items: center !important;
    }

    /* Fallback/Specific Child Targeting */
    div[class*="st-key-const_batch"] > div:first-child > div,
    div[class*="st-key-wish_batch"] > div:first-child > div {
         display: grid !important;
         grid-template-columns: repeat(7, 1fr) !important;
    }
    
    /* Target the chip items inside */
    div[class*="st-key-const_batch"] div[role="button"],
    div[class*="st-key-wish_batch"] div[role="button"] {
        width: 100% !important;
        min-width: 0 !important;
        justify-content: center !important;
        margin: 0 !important;
        padding: 4px 0 !important;
        border-radius: 6px !important;
    }
    
    /* Hide spacers */
    div[class*="st-key-const_batch"] div[role="button"]:has(span:empty),
    div[class*="st-key-wish_batch"] div[role="button"]:has(span:empty) {
        visibility: hidden !important;
        pointer-events: none !important;
    }
    /* Fallback for browsers not supporting :has (though most do now) */
    /* We can also rely on the label text if needed, but :has is safe enough for modern browsers */

    /* Global Right Alignment for specific containers */
    .element-container, .stMarkdown {
        direction: rtl;
        text-align: right;
    }

    /* --- Universal Mobile Fixes --- */
    @media (max-width: 768px) {
        /* Allow tables/data_editors to scroll horizontally, instead of squishing and splitting text */
        [data-testid="stDataFrame"] table, [data-testid="stDataEditor"] table {
            white-space: nowrap !important;
        }
        
        /* Make metric cards stack gracefully and have minimum widths */
        div[data-testid="stHorizontalBlock"]:has(.metric-card) {
            display: flex !important;
            flex-direction: column !important;
        }
        
        /* If metric html renders directly into markdown, force horizontal scroller */
        .metric-card {
            min-width: 100% !important;
            margin-bottom: 15px !important;
        }
    }

    /* ── RTL date-picker popup ─────────────────────────────────── */
    /* Force Streamlit's st.date_input calendar popup to RTL layout  */
    [data-baseweb="calendar"] {
        direction: rtl !important;
    }
    [data-baseweb="calendar"] [data-testid="calendar-header"] {
        direction: rtl !important;
    }
    /* Week day header row inside the popup */
    [data-baseweb="calendar"] [role="columnheader"],
    [data-baseweb="calendar"] [role="gridcell"] {
        direction: rtl !important;
    }
    /* Flip the prev/next month arrows so they point correctly in RTL */
    [data-baseweb="calendar"] button[aria-label*="Previous"],
    [data-baseweb="calendar"] button[aria-label*="previous"] {
        order: 1 !important;
    }
    [data-baseweb="calendar"] button[aria-label*="Next"],
    [data-baseweb="calendar"] button[aria-label*="next"] {
        order: -1 !important;
    }

    </style>
    """, unsafe_allow_html=True)

def render_navbar(role):
    """Renders the responsive navigation bar.
    Role-based visibility:
      - סידור תורנויות + הגשת בקשות: מתמחה / תורנ/ית חוץ / מנהל/ת (לא: מנהל מחלקה / רופא/ה בכירה)
      - צוות + דוחות: מנהל/ת בלבד
      - סידור יומי / סידור חודשי: כולם חוץ מ-תורן חוץ — תווית משתנה לפי תפקיד
    """
    items = []

    items.append(sac.TabsItem('הגדרות', icon='gear'))

    # סידור תורנויות (תורנויות לילה) — מנהל מחלקה ורופא/ה בכירה לא רואים
    if role not in ("מנהל מחלקה", "רופא בכיר"):
        items.append(sac.TabsItem('סידור תורנויות', icon='calendar-week'))

    # הגשת בקשות — לא לאדמין. מנהל/ת מחלקה רואה (היעדרות עצמית, מאושרת אוטומטית)
    if role != "מנהל/ת":
        items.append(sac.TabsItem('הגשת בקשות', icon='calendar-check'))

    # אדמין-בלבד
    if role == "מנהל/ת":
        items.append(sac.TabsItem('צוות', icon='people'))
        items.append(sac.TabsItem('דוחות וניהול', icon='bar-chart-line'))

    # סידור יומי / סידור חודשי — תורן חוץ לא רואה
    # אדמין רואה את שניהם: "סידור חודשי" (תכנון + 5 תתי-טאבים) + "סידור יומי" (תצוגת מנהל מחלקה)
    if role == "מנהל/ת":
        items.append(sac.TabsItem('סידור חודשי', icon='calendar3'))
        items.append(sac.TabsItem('סידור יומי',  icon='calendar-day'))
    elif role != "תורן חוץ":
        items.append(sac.TabsItem('סידור יומי', icon='calendar3'))

    # ── Default index after first login ───────────────────────────
    if 'nav_initialized' not in st.session_state:
        # Find the most useful default per role
        labels = [it.label for it in items]
        if role == "מנהל/ת":
            default = 'דוחות וניהול'
        elif role in ("מנהל מחלקה", "רופא בכיר"):
            default = 'סידור יומי'
        else:
            default = 'הגשת בקשות'
        st.session_state.current_nav_index = labels.index(default) if default in labels else 0
        st.session_state.nav_initialized = True

    # Clamp current_nav_index in case the items list changed
    if st.session_state.current_nav_index >= len(items):
        st.session_state.current_nav_index = 0

    st.markdown('<div dir="rtl" style="text-align: right;">', unsafe_allow_html=True)
    result = sac.tabs(
        items=items,
        index=st.session_state.current_nav_index,
        format_func='title',
        size='lg',
        color='#4f46e5',
        return_index=False,
        align='center'
    )
    st.markdown('</div>', unsafe_allow_html=True)

    selected_idx = 0
    for i, item in enumerate(items):
        if item.label == result:
            selected_idx = i
            break
    st.session_state.current_nav_index = selected_idx

    return result

def render_mobile_bottom_nav(role):
    """Renders a bottom navigation bar specifically for mobile."""
    # Note: SAC doesn't have a built-in 'bottom' mode, so we use st.columns at the bottom or stick to Top Nav for now.
    # For this iteration, we will use the Top Horizontal Menu which is mobile responsive (scrolls horizontally).
    pass
