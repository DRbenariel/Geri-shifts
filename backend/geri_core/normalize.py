"""Cell / name normalisation helpers (appy.py:61-116, 6132)."""
import pandas as pd


def strip_cell(s):
    """Strip only MATCHING surrounding quote pairs from a cell value."""
    s = str(s).strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


# Apostrophe/geresh variants → plain ASCII apostrophe
_APOS_VARIANTS = str.maketrans({
    '׳': "'",
    '’': "'",
    'ʼ': "'",
    '‘': "'",
    '`': "'",
})


def norm_dept(v) -> str:
    """Normalise a daily_dept string so apostrophe variants all compare equal."""
    return str(v).strip().translate(_APOS_VARIANTS)


def norm_dr(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise the daily_dept and side columns of a dept_rotation DataFrame."""
    if not df.empty and 'daily_dept' in df.columns:
        df = df.copy()
        df['daily_dept'] = df['daily_dept'].astype(str).apply(norm_dept)
    if 'side' not in df.columns:
        df['side'] = ''
    df['side'] = df['side'].fillna('').astype(str).str.strip()
    return df


def clean_sheet_values(vals) -> pd.DataFrame:
    """Raw get_all_values() output → clean DataFrame (header-only sheets keep columns)."""
    if not vals:
        return pd.DataFrame()
    headers = [strip_cell(h) for h in vals[0]]
    rows = []
    for row in vals[1:]:
        cleaned = [strip_cell(c) for c in row]
        while len(cleaned) < len(headers):
            cleaned.append('')
        rows.append(cleaned[:len(headers)])
    return pd.DataFrame(rows, columns=headers)


def is_true(v) -> bool:
    """Sheets stores booleans as "True"/"False" strings; never use astype(bool)."""
    if isinstance(v, bool):
        return v
    try:
        if pd.isna(v):
            return False
    except (TypeError, ValueError):
        pass
    return str(v).strip().lower() == 'true'


def parse_manage_depts(raw) -> list:
    """Comma-separated manage_depts → clean list (geresh ׳ → ')."""
    normalised = str(raw).strip().replace('׳', "'").replace('״', '״')
    return [d.strip() for d in normalised.split(',') if d.strip()]


def make_initials(name: str) -> str:
    parts = str(name).strip().split()
    return " ".join(p[0] for p in parts if p)


def safe_int(val, default=0):
    try:
        if pd.isna(val) or val == "":
            return default
        return int(float(val))
    except (ValueError, TypeError):
        return default
