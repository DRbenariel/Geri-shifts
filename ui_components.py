import streamlit as st
import streamlit_antd_components as sac
import streamlit_shadcn_ui as ui

def setup_style():
    """Injects the global CSS for the Medical Slate & Indigo theme."""
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
    /* Force ALL buttons to Indigo - v2 */
    button, 
    div[data-testid="stButton"] > button, 
    div[data-testid="stFormSubmitButton"] > button,
    .stButton > button,
    [kind="primary"],
    [kind="secondary"] {
        background: #4f46e5 !important;
        background-color: #4f46e5 !important;
        background-image: none !important;
        color: white !important;
        transition: all 0.2s;
        box-shadow: none !important;
        border: none !important;
        border-radius: 8px !important;
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
        background: #4338ca !important;
        background-color: #4338ca !important;
        background-image: none !important;
        color: white !important;
        border: none !important;
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
    
    /* Force text to stick to the right side with padding */
    .ant-menu-item {
        flex-direction: row-reverse !important;
        justify-content: flex-end !important;
        text-align: right !important;
        direction: rtl !important;
        padding-right: 24px !important;
        padding-left: 8px !important;
    }
    
    /* Force text content to align right and add padding */
    .ant-menu-title-content,
    .ant-menu-item-content,
    .ant-menu-item span {
        text-align: right !important;
        direction: rtl !important;
        display: block !important;
        width: 100% !important;
        padding-right: 12px !important;
    }
    
    /* Move icon to the left side (in RTL, this means visual right) */
    .ant-menu-item .anticon {
        margin-left: 8px !important;
        margin-right: 0 !important;
        order: 2 !important;
    }
    
    /* Force the menu item content to be on the right */
    .ant-menu-item-content {
        order: 1 !important;
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
    /* Remove extra padding from columns containing chips */
    div[data-testid="column"] {
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

    </style>
    """, unsafe_allow_html=True)

def render_navbar(role):
    """Renders the responsive navigation bar."""
    
    # Define standard menu items
    items = []
    
    # Build items in reverse order for RTL effect
    if role == "מנהל/ת":
        items.append(sac.MenuItem('דוחות וניהול', icon='bar-chart-line'))
        items.append(sac.MenuItem('צוות', icon='people'))
    
    # Show "הגשת אילוצים" ONLY for non-admins
    if role != "מנהל/ת":
        items.append(sac.MenuItem('הגשת אילוצים', icon='calendar-check'))
    
    items.append(sac.MenuItem('לוח שיבוץ', icon='calendar-week'))
    items.append(sac.MenuItem('הגדרות', icon='gear'))
    
    # Wrap in RTL container using HTML dir attribute
    st.markdown('<div dir="rtl" style="text-align: right;">', unsafe_allow_html=True)
    result = sac.menu(
        items=items,
        index=0,
        format_func='title',
        size='lg',
        variant='filled',
        color='#4f46e5', # Explicit Hex to match buttons
        open_all=True,
        return_index=False
    )
    st.markdown('</div>', unsafe_allow_html=True)
    return result

def render_mobile_bottom_nav(role):
    """Renders a bottom navigation bar specifically for mobile."""
    # Note: SAC doesn't have a built-in 'bottom' mode, so we use st.columns at the bottom or stick to Top Nav for now.
    # For this iteration, we will use the Top Horizontal Menu which is mobile responsive (scrolls horizontally).
    pass
