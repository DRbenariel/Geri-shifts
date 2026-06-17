"""
calendars.py — functional-weekend detection, Streamlit-free.

Mirrors appy.py:get_functional_day_type (2606) and is_functional_weekend (2615)
exactly so the ported scheduler produces identical weekend/quota decisions.
"""
from datetime import date, datetime, timedelta


def get_functional_day_type(date_obj, special_days_df):
    """Returns 'רגיל' / 'כמו שישי (ערב חג)' / 'כמו שבת (חג)'."""
    date_str = date_obj.strftime('%Y-%m-%d') if isinstance(date_obj, date) else date_obj
    if special_days_df is not None and not special_days_df.empty and 'day_type' in special_days_df.columns:
        match = special_days_df[special_days_df['date'] == str(date_str)]
        if not match.empty:
            return match.iloc[0]['day_type']
    return 'רגיל'


def is_functional_weekend(date_obj, special_days_df):
    """True if the date acts as a weekend (Fri/Sat or special חג / ערב חג)."""
    if isinstance(date_obj, str):
        date_obj = datetime.strptime(date_obj, '%Y-%m-%d').date()
    if date_obj.weekday() in [4, 5]:  # Friday / Saturday
        return True
    day_type = get_functional_day_type(date_obj, special_days_df)
    if day_type in ['כמו שישי (ערב חג)', 'כמו שבת (חג)']:
        return True
    # the day BEFORE a "like-Friday" eve also behaves like a weekend
    tomorrow = date_obj + timedelta(days=1)
    if get_functional_day_type(tomorrow, special_days_df) == 'כמו שישי (ערב חג)':
        return True
    return False
