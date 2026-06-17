"""
scheduling_core — Streamlit-free scheduling logic shared by the Flask backend
and (eventually) daily_report.py.

Contents:
  - calendars.is_functional_weekend  — Fri/Sat + special-day weekend detection
  - validity.check_assignment_validity — single source of truth for hard constraints
  - swaps.find_swap_candidates        — 3-tier (full/partial/chain) swap search

run_smart_scheduling (the production assigner) is added in a later milestone
alongside its Flask endpoint + Streamlit parity test.
"""
from .calendars import is_functional_weekend
from .validity import check_assignment_validity
from .swaps import find_swap_candidates

__all__ = ['is_functional_weekend', 'check_assignment_validity', 'find_swap_candidates']
