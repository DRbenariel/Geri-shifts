"""geri_core — the business logic of appy.py with no Streamlit dependency.

Every function takes a `DataContext` (the request-scoped replacement for
st.session_state) as its first argument. Writes go through `ctx.save()`, which
is synchronous. Nothing here renders UI.

Modules
  context      DataContext, sheet loading/normalisation, derived indexes
  store        SheetStore protocol, GSheetStore (gspread), MemoryStore (tests)
  constants    departments, statuses, cycles, tabs per role
  days         functional Friday/Saturday/weekend
  people       dept resolution, managers, role ordering
  daily        סידור עבודה: derive_auto_status, cell edits, transfers, grid model
  absences     day-absence requests: submit, approve/reject/delete, conflicts, Gantt
  night        night shifts: validity, swaps, manual edits, availability
  scheduling   greedy + CP-SAT auto-scheduler
  constraints  night constraint/wish submission + validation
  staff        login (SHA-256 → bcrypt upgrade), passwords, staff table
  admin        settings, special days, כוננויות, גאנט חודשי
  exports      Excel bytes, Schedule_Export, WSD_ sheets
  reports      dashboard, fairness, problem scan, analytics
"""
from .context import DataContext
from .store import GSheetStore, MemoryStore, SaveError

__all__ = ['DataContext', 'GSheetStore', 'MemoryStore', 'SaveError']
