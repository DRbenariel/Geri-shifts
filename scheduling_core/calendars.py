"""
calendars.py — functional-weekend detection, Streamlit-free.

Ported from daily_report.py:is_functional_weekend_standalone (itself a replica
of appy.py:is_functional_weekend). A "functional weekend" is Fri/Sat OR a
special day typed as חג / ערב חג (and the day before an ערב-חג).
"""
from datetime import datetime, timedelta


def is_functional_weekend(date_obj, special_days_df):
    """True if date_obj counts as a weekend for scheduling/quota purposes."""
    if isinstance(date_obj, str):
        date_obj = datetime.strptime(date_obj, '%Y-%m-%d').date()
    if date_obj.weekday() in (4, 5):  # Friday / Saturday
        return True
    d_str = date_obj.strftime('%Y-%m-%d')
    if special_days_df is not None and not special_days_df.empty and 'day_type' in special_days_df.columns:
        match = special_days_df[special_days_df['date'] == d_str]
        if not match.empty:
            day_type = match.iloc[0]['day_type']
            if day_type in ('כמו שישי (ערב חג)', 'כמו שבת (חג)'):
                return True
        # day-before-erev-chag is treated as a weekend too
        tom_str = (date_obj + timedelta(days=1)).strftime('%Y-%m-%d')
        match2 = special_days_df[special_days_df['date'] == tom_str]
        if not match2.empty and match2.iloc[0]['day_type'] == 'כמו שישי (ערב חג)':
            return True
    return False
