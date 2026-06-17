"""
config.py — constants and paths for the Flask backend.

Values can be overridden by environment variables on Render
(SPREADSHEET_KEY especially). Credentials are read in db.py.
"""
import os

SCOPES = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive',
]

# Spreadsheet key — same workbook the Streamlit app + daily_report.py use.
SPREADSHEET_KEY = os.environ.get(
    'SPREADSHEET_KEY', '1fmjfqA04VMfbBYHw2OXqoY08X7heazlx0Cr2Uaa2LkY')

YEAR = 2026

MAIN_DEPTS = ['פנימית גריאטרית', 'שיקום']
DAILY_DEPTS = ['שיקום גריאטרי א׳', 'שיקום גריאטרי ב׳', 'פנימית גריאטרית']
FRIDAY_DEPTS = [
    'שישי בוקר - שיקום (1)', 'שישי בוקר - שיקום (2)',
    'שישי בוקר - פנימית (1)', 'שישי בוקר - פנימית (2)',
]

CACHE_TTL = 15  # seconds — reads are cached briefly; writes invalidate

HERE = os.path.dirname(os.path.abspath(__file__))   # the frontend/ directory
ROOT = os.path.dirname(HERE)                          # repo root
