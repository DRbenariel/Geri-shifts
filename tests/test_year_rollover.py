"""Year inference for month-only settings (active_month, daily_active_month)."""
import ast
import pathlib
from datetime import date

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load(path, name):
    # Pull one function out of the module source, so appy.py (Streamlit) doesn't have to be imported.
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    ns = {"date": date}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), path, "exec"), ns)
    return ns[name]


IMPLS = [_load("daily_report.py", "year_for_month"), _load("appy.py", "_year_for_month")]


@pytest.mark.parametrize("impl", IMPLS)
@pytest.mark.parametrize("today, month, year", [
    (date(2026, 12, 18), 1, 2027),   # December, opening January
    (date(2026, 12, 18), 12, 2026),
    (date(2026, 12, 18), 7, 2026),   # 5 months back
    (date(2026, 12, 18), 6, 2027),   # 6 months ahead
    (date(2027, 1, 5), 12, 2026),    # January, still viewing December
    (date(2027, 1, 5), 8, 2026),
    (date(2027, 1, 5), 7, 2027),
    (date(2026, 10, 19), 11, 2026),
    (date(2026, 10, 19), 4, 2027),
    (date(2026, 10, 19), 5, 2026),
    (date(2026, 6, 1), 1, 2026),
    (date(2026, 6, 1), 12, 2026),
])
def test_year_for_month(impl, today, month, year):
    assert impl(month, today) == year


def test_same_rule_in_both_files():
    for d in range(0, 730, 7):
        today = date.fromordinal(date(2026, 1, 1).toordinal() + d)
        for m in range(1, 13):
            assert IMPLS[0](m, today) == IMPLS[1](m, today)
