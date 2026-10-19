"""Staff management + authentication (appy.py:3260-3325, 6309-6345, 6849-7094)."""
from __future__ import annotations

import hashlib

import pandas as pd

from .constants import DEFAULT_PASSWORD
from .normalize import is_true

try:
    import bcrypt
except ImportError:          # bcrypt optional: legacy SHA-256 still works without it
    bcrypt = None


# ── passwords ────────────────────────────────────────────────────────────────
def sha256_hex(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


# While the Streamlit app runs next to the API it can only read SHA-256, so the API
# switches this on: new and changed passwords stay SHA-256 until Streamlit is retired.
LEGACY_HASHES = False


def use_legacy_hashes(flag: bool = True):
    global LEGACY_HASHES
    LEGACY_HASHES = bool(flag)


def hash_password(pw: str) -> str:
    """New hashes are bcrypt when available; legacy readers keep accepting SHA-256."""
    if bcrypt is None or LEGACY_HASHES:
        return sha256_hex(pw)
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, stored: str) -> bool:
    stored = str(stored or '')
    if stored.startswith('$2'):
        return bcrypt is not None and bcrypt.checkpw(pw.encode(), stored.encode())
    return sha256_hex(pw) == stored


def needs_upgrade(stored: str) -> bool:
    return bcrypt is not None and not LEGACY_HASHES and not str(stored or '').startswith('$2')


class AuthError(Exception):
    pass


def login(ctx, username: str, password: str, upgrade_hash=True) -> dict:
    """Live-read staff, check password, return {name, role}. Upgrades SHA-256 → bcrypt on success."""
    username = str(username).strip()
    staff_df = ctx.fetch_live("staff")
    if 'name' not in staff_df.columns:
        raise AuthError("לא ניתן לטעון את רשימת הצוות — נסה שוב")
    staff_df['name'] = staff_df['name'].astype(str).str.strip()
    match = staff_df[staff_df['name'] == username]
    if match.empty:
        raise AuthError("שם המשתמש לא נמצא במערכת")
    stored = match.iloc[0]['password']
    if not verify_password(password, stored):
        raise AuthError("סיסמה שגויה")
    if upgrade_hash and needs_upgrade(stored):
        try:
            staff_df.loc[staff_df['name'] == username, 'password'] = hash_password(password)
            ctx.save("staff", staff_df)
            ctx.staff.loc[ctx.staff['name'].astype(str).str.strip() == username, 'password'] = \
                staff_df.loc[staff_df['name'] == username, 'password'].iloc[0]
        except Exception:
            pass     # login must not fail because the upgrade write failed
    return {'name': username, 'role': str(match.iloc[0]['type'])}


def change_password(ctx, user_name, current, new, confirm):
    rec = ctx.staff[ctx.staff['name'] == user_name]
    if rec.empty:
        raise ValueError("שגיאה: משתמש לא נמצא.")
    if not verify_password(current, rec.iloc[0]['password']):
        raise ValueError("סיסמה נוכחית שגויה.")
    if not new:
        raise ValueError("לא ניתן להגדיר סיסמה ריקה.")
    if new != confirm:
        raise ValueError("הסיסמאות החדשות אינן תואמות.")
    ctx.staff.loc[ctx.staff['name'] == user_name, 'password'] = hash_password(new)
    ctx.save("staff", ctx.staff)


# ── staff table ──────────────────────────────────────────────────────────────
EDITABLE_COLUMNS = ['name', 'type', 'dept', 'monthly_quota', 'weekend_quota', 'email',
                    'manage_depts', 'recurring_absent_days', 'manual_schedule_only']
HIDDEN_COLUMNS = ('password', 'only_home_dept', 'whatsapp_link')


def staff_view(ctx) -> dict:
    """Rows for the editor (no passwords) + the only_home_dept multiselect state."""
    sf = ctx.staff.copy()
    if 'only_home_dept' not in sf.columns:
        sf['only_home_dept'] = False
    sf['only_home_dept'] = sf['only_home_dept'].apply(is_true)
    cols = [c for c in EDITABLE_COLUMNS if c in sf.columns]
    cols += [c for c in sf.columns if c not in cols and c not in HIDDEN_COLUMNS]
    valid = [n for n in sf['name'].tolist() if str(n).strip() and n != '---']
    homes = [n for n in sf[sf['only_home_dept']]['name'].dropna().tolist() if n in valid]
    rows = sf[cols].astype(object).where(pd.notna(sf[cols]), '').to_dict('records')
    return {'columns': cols, 'rows': rows, 'only_home': homes}


def add_employee(ctx, name, type_, dept, monthly_quota=6, weekend_quota=1, only_home=False,
                 email='', manage_depts=''):
    name = str(name)
    if not name.strip():
        raise ValueError("חובה להזין שם.")
    if name in ctx.staff['name'].values:
        raise ValueError(f"העובד/ת {name} כבר קיים/ת.")
    row = {'name': name, 'type': type_, 'dept': dept, 'monthly_quota': monthly_quota,
           'weekend_quota': weekend_quota, 'only_home_dept': only_home,
           'password': hash_password(DEFAULT_PASSWORD), 'email': str(email).strip(),
           'manage_depts': (",".join(manage_depts) if isinstance(manage_depts, (list, tuple))
                            else str(manage_depts)).strip(),
           'recurring_absent_days': ''}
    before = ctx.staff
    ctx.staff = pd.concat([ctx.staff, pd.DataFrame([row])], ignore_index=True)
    try:
        ctx.save("staff", ctx.staff)
    except Exception:
        ctx.staff = before          # roll back the ghost row on a failed write
        raise
    return row


def save_staff_table(ctx, edited_rows: list, only_home_names: list):
    """Batch save from the editor. Passwords are kept by name (the Streamlit
    version matched by row index, which broke when rows were reordered). A
    renamed row passes its old name as `_original_name` to keep its password;
    genuinely new names get the default password."""
    latest = ctx.fetch_live("staff")
    old = latest if not latest.empty else ctx.staff
    pw_by_name = {}
    if 'password' in old.columns:
        pw_by_name = dict(zip(old['name'].astype(str).str.strip(), old['password']))
    out = []
    for r in edited_rows:
        r = dict(r)
        orig = str(r.pop('_original_name', '') or '').strip()
        nm = str(r.get('name', '')).strip()
        if not nm:
            continue
        r['only_home_dept'] = r.get('name') in only_home_names
        r['password'] = pw_by_name.get(orig or nm) or hash_password(DEFAULT_PASSWORD)
        out.append(r)
    new = pd.DataFrame(out)
    ctx.staff = new
    ctx.save("staff", new)
    return new
