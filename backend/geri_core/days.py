"""Functional day types: real weekends plus special days (appy.py:947-964, 3432-3458)."""
from datetime import date, datetime, timedelta

import pandas as pd

from .constants import LIKE_FRIDAY, LIKE_SATURDAY


def to_date(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if hasattr(v, 'strftime') and not isinstance(v, str):   # pandas Timestamp
        return v.date()
    return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


def get_functional_day_type(date_obj, special_days_df: pd.DataFrame) -> str:
    """'רגיל', 'כמו שישי (ערב חג)' or 'כמו שבת (חג)'."""
    date_str = date_obj.strftime('%Y-%m-%d') if isinstance(date_obj, date) else date_obj
    if special_days_df is not None and not special_days_df.empty and 'day_type' in special_days_df.columns:
        match = special_days_df[special_days_df['date'] == str(date_str)]
        if not match.empty:
            return match.iloc[0]['day_type']
    return 'רגיל'


def is_functional_weekend(date_obj, special_days_df) -> bool:
    """Fri/Sat, a special Fri/Sat-like day, or the day before a 'like Friday' day."""
    if isinstance(date_obj, str):
        date_obj = datetime.strptime(date_obj, '%Y-%m-%d').date()
    if date_obj.weekday() in [4, 5]:
        return True
    day_type = get_functional_day_type(date_obj, special_days_df)
    if day_type in [LIKE_FRIDAY, LIKE_SATURDAY]:
        return True
    tomorrow = date_obj + timedelta(days=1)
    if get_functional_day_type(tomorrow, special_days_df) == LIKE_FRIDAY:
        return True
    return False


def is_functional_friday(ctx, date_obj_or_str) -> bool:
    d = (datetime.strptime(date_obj_or_str, "%Y-%m-%d").date()
         if isinstance(date_obj_or_str, str) else date_obj_or_str)
    if (d.weekday() + 1) % 7 == 5:
        return True
    return get_functional_day_type(d, ctx.special_days) == LIKE_FRIDAY


def is_functional_saturday(ctx, date_obj_or_str) -> bool:
    d = (datetime.strptime(date_obj_or_str, "%Y-%m-%d").date()
         if isinstance(date_obj_or_str, str) else date_obj_or_str)
    if (d.weekday() + 1) % 7 == 6:
        return True
    return get_functional_day_type(d, ctx.special_days) == LIKE_SATURDAY


def heb_weekday_idx(d: date) -> int:
    """Sun=0 … Sat=6."""
    return (d.weekday() + 1) % 7
