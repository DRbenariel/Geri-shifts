"""Synthetic, fictional dataset shaped like the live sheets (no real names or data).

Deliberately includes the known data-quality edge cases: a trailing-space name,
geresh (׳) in manage_depts, "True"/"False" strings for booleans, legacy
dept_at_request values, special days that behave like Friday/Saturday, manual
WSD overrides, day-specific transfers with sides, and manager self-planting.
"""
import calendar
import random
import uuid
from datetime import date, timedelta

import pandas as pd

YEAR = 2026
MONTH = 11
PREV = 10

INTERNS = ['נועה ברק', 'איתי שגיא', 'מאיה רוזן', 'עומר דהן', 'ליאור קציר', 'הדס אלמוג',
           'יונתן פרץ', 'שירה לוי', 'תמר גולן', 'אלון מזרחי', 'רוני אבן ', 'גל שחר']   # trailing space
EXTERNALS = ['אמיר חדד', 'סיוון כץ', 'דניאל אורן', 'מיכל טל']
SENIORS = ['דפנה ירון', 'עידו נחום', 'רות שמש', 'אסף ברנר']
MANAGERS = [('יעל כרמי', "שיקום גריאטרי א'"), ('בועז לנדאו', "שיקום גריאטרי ב׳"),
            ('אורית סלע', 'פנימית גריאטרית'), ('רון צליק', 'פנימית גריאטרית')]
ADMINS = [('ענבל רז', 'מנהל על'), ('קרן מור', 'מנהל/ת')]

SHIKUM_A, SHIKUM_B, PNIM = "שיקום גריאטרי א'", "שיקום גריאטרי ב'", 'פנימית גריאטרית'


def build(seed=7):
    rnd = random.Random(seed)
    staff = []
    for i, n in enumerate(INTERNS):
        staff.append({'name': n, 'type': 'מתמחה', 'dept': 'שיקום' if i % 3 == 0 else 'פנימית גריאטרית',
                      'monthly_quota': '6' if i % 4 else '5', 'weekend_quota': '1',
                      'password': 'x', 'only_home_dept': 'True' if i in (2, 7) else 'False',
                      'email': f'i{i}@example.org' if i % 2 == 0 else '', 'manage_depts': '',
                      'recurring_absent_days': 'ג' if i == 4 else '',
                      'manual_schedule_only': 'True' if i == 9 else 'False'})
    for i, n in enumerate(EXTERNALS):
        staff.append({'name': n, 'type': 'תורן חוץ', 'dept': 'שיקום', 'monthly_quota': '4',
                      'weekend_quota': '2', 'password': 'x', 'only_home_dept': 'False', 'email': '',
                      'manage_depts': '', 'recurring_absent_days': '', 'manual_schedule_only': 'False'})
    for i, n in enumerate(SENIORS):
        staff.append({'name': n, 'type': 'רופא בכיר', 'dept': 'כללי', 'monthly_quota': '0',
                      'weekend_quota': '0', 'password': 'x', 'only_home_dept': 'False',
                      'email': f's{i}@example.org', 'manage_depts': '',
                      'recurring_absent_days': 'ד,ה' if i == 1 else '', 'manual_schedule_only': 'False'})
    for i, (n, d) in enumerate(MANAGERS):
        staff.append({'name': n, 'type': 'מנהל מחלקה', 'dept': 'הנהלה', 'monthly_quota': '0',
                      'weekend_quota': '0', 'password': 'x', 'only_home_dept': 'False',
                      'email': f'm{i}@example.org', 'manage_depts': d, 'recurring_absent_days': '',
                      'manual_schedule_only': 'False'})
    for n, t in ADMINS:
        staff.append({'name': n, 'type': t, 'dept': 'הנהלה', 'monthly_quota': '0', 'weekend_quota': '0',
                      'password': 'x', 'only_home_dept': 'False', 'email': '', 'manage_depts': '',
                      'recurring_absent_days': '', 'manual_schedule_only': 'False'})
    staff = pd.DataFrame(staff)

    # dept_rotation for Oct + Nov. INTERNS[11] has no Nov row (intern-default path).
    rot = []
    pools = [SHIKUM_A, SHIKUM_B, PNIM]
    for ym in (f"{YEAR}-{PREV:02d}", f"{YEAR}-{MONTH:02d}"):
        for i, n in enumerate(INTERNS):
            if ym.endswith(f"{MONTH:02d}") and i == 11:
                continue
            d = pools[(i + (ym.endswith('10'))) % 3]
            rot.append({'employee': n.strip(), 'year_month': ym, 'daily_dept': d,
                        'side': ('ורוד' if i % 2 else 'כחול') if d == PNIM else ''})
        for i, n in enumerate(SENIORS):
            d = pools[i % 3]
            rot.append({'employee': n, 'year_month': ym, 'daily_dept': d,
                        'side': ('ורוד' if i % 2 else '') if d == PNIM else ''})   # one side-less senior
    rot = pd.DataFrame(rot)

    days = calendar.monthrange(YEAR, MONTH)[1]
    reqs = []
    for n in INTERNS + EXTERNALS:
        if n == INTERNS[5]:
            continue          # one person never submits
        picks = rnd.sample(range(1, days + 1), 6)
        for d in picks[:4]:
            reqs.append({'employee': n, 'date': f"{YEAR}-{MONTH:02d}-{d:02d}", 'status': 'אילוץ'})
        for d in picks[4:]:
            reqs.append({'employee': n, 'date': f"{YEAR}-{MONTH:02d}-{d:02d}", 'status': 'בקשה'})
    reqs = pd.DataFrame(reqs)

    special = pd.DataFrame([
        {'date': f"{YEAR}-{MONTH:02d}-11", 'description': 'ערב חג', 'day_type': 'כמו שישי (ערב חג)'},
        {'date': f"{YEAR}-{MONTH:02d}-12", 'description': 'חג', 'day_type': 'כמו שבת (חג)'},
        {'date': f"{YEAR}-{MONTH:02d}-24", 'description': 'יום עיון', 'day_type': 'לידיעה בלבד'},
    ])

    # October history: two depts filled round-robin (gives fairness / last-assignment data)
    sched = []
    eligible_p = [n for n in INTERNS]
    eligible_s = INTERNS + EXTERNALS
    for d in range(1, 32):
        ds = f"{YEAR}-{PREV:02d}-{d:02d}"
        sched.append({'date': ds, 'dept': 'פנימית גריאטרית', 'employee': eligible_p[d % len(eligible_p)],
                      'is_manual': 'False', 'empty_reason': ''})
        sched.append({'date': ds, 'dept': 'שיקום', 'employee': eligible_s[(d * 5) % len(eligible_s)],
                      'is_manual': 'False', 'empty_reason': ''})
    # A few November manual rows + a failed slot
    sched += [
        {'date': f"{YEAR}-{MONTH:02d}-03", 'dept': 'שיקום', 'employee': EXTERNALS[0], 'is_manual': 'True', 'empty_reason': ''},
        {'date': f"{YEAR}-{MONTH:02d}-05", 'dept': 'פנימית גריאטרית', 'employee': INTERNS[0], 'is_manual': 'True', 'empty_reason': ''},
        {'date': f"{YEAR}-{MONTH:02d}-09", 'dept': 'שיקום', 'employee': '---', 'is_manual': 'False', 'empty_reason': 'x'},
    ]
    sched = pd.DataFrame(sched)

    def aid():
        return str(uuid.UUID(int=rnd.getrandbits(128)))
    ar = pd.DataFrame([
        {'id': aid(), 'employee': SENIORS[0], 'start_date': f"{YEAR}-{MONTH:02d}-02", 'end_date': f"{YEAR}-{MONTH:02d}-04",
         'type': 'חופש', 'status': 'approved', 'dept_at_request': 'שיקום', 'manager_email': '', 'approved_by': 'x',
         'notes': '', 'created_at': '', 'responded_at': ''},
        {'id': aid(), 'employee': INTERNS[3], 'start_date': f"{YEAR}-{MONTH:02d}-03", 'end_date': f"{YEAR}-{MONTH:02d}-03",
         'type': '202', 'status': 'approved', 'dept_at_request': SHIKUM_A, 'manager_email': '', 'approved_by': 'x',
         'notes': '', 'created_at': '', 'responded_at': ''},
        {'id': aid(), 'employee': INTERNS[6], 'start_date': f"{YEAR}-{MONTH:02d}-16", 'end_date': f"{YEAR}-{MONTH:02d}-19",
         'type': 'חופש עתידי', 'status': 'approved', 'dept_at_request': '', 'manager_email': '', 'approved_by': 'x',
         'notes': 'טיול', 'created_at': '', 'responded_at': ''},
        {'id': aid(), 'employee': INTERNS[0], 'start_date': f"{YEAR}-{MONTH:02d}-03", 'end_date': f"{YEAR}-{MONTH:02d}-04",
         'type': 'חופש', 'status': 'pending', 'dept_at_request': SHIKUM_A, 'manager_email': 'm0@example.org',
         'approved_by': '', 'notes': '', 'created_at': '', 'responded_at': ''},
        {'id': aid(), 'employee': INTERNS[2], 'start_date': f"{YEAR}-{MONTH:02d}-17", 'end_date': f"{YEAR}-{MONTH:02d}-17",
         'type': 'היעדרות אחרת', 'status': 'pending', 'dept_at_request': PNIM, 'manager_email': '',
         'approved_by': '', 'notes': 'כנס', 'created_at': '', 'responded_at': ''},
        {'id': aid(), 'employee': INTERNS[8], 'start_date': f"{YEAR}-{MONTH:02d}-25", 'end_date': f"{YEAR}-{MONTH:02d}-26",
         'type': '202', 'status': 'pending', 'dept_at_request': 'פנימית גריאטרית', 'manager_email': '',
         'approved_by': '', 'notes': '', 'created_at': '', 'responded_at': ''},
        {'id': aid(), 'employee': INTERNS[1], 'start_date': f"{YEAR}-{MONTH:02d}-10", 'end_date': f"{YEAR}-{MONTH:02d}-10",
         'type': 'חופש', 'status': 'rejected', 'dept_at_request': SHIKUM_B, 'manager_email': '',
         'approved_by': 'x', 'notes': '', 'created_at': '', 'responded_at': ''},
    ])

    wsd = pd.DataFrame([
        # plain manual overrides with notes
        {'date': f"{YEAR}-{MONTH:02d}-04", 'employee': INTERNS[1], 'daily_dept': SHIKUM_B, 'status': 'אחר',
         'note': 'קורס', 'is_manual': 'True', 'side': ''},
        {'date': f"{YEAR}-{MONTH:02d}-05", 'employee': SENIORS[2], 'daily_dept': PNIM, 'status': 'חופש',
         'note': '', 'is_manual': 'True', 'side': ''},
        # day-specific transfer of a שיקום intern into פנימית (blue side), and into שיקום ב'
        {'date': f"{YEAR}-{MONTH:02d}-10", 'employee': INTERNS[0], 'daily_dept': PNIM, 'status': 'עובד',
         'note': '', 'is_manual': 'True', 'side': 'כחול'},
        {'date': f"{YEAR}-{MONTH:02d}-18", 'employee': INTERNS[0], 'daily_dept': PNIM, 'status': 'עובד',
         'note': '', 'is_manual': 'True', 'side': 'כחול'},
        {'date': f"{YEAR}-{MONTH:02d}-17", 'employee': INTERNS[2], 'daily_dept': SHIKUM_B, 'status': 'עובד',
         'note': '', 'is_manual': 'True', 'side': ''},
        # manager un-plants self + manual-only intern planted once
        {'date': f"{YEAR}-{MONTH:02d}-09", 'employee': 'יעל כרמי', 'daily_dept': SHIKUM_A, 'status': '',
         'note': '', 'is_manual': 'True', 'side': ''},
        {'date': f"{YEAR}-{MONTH:02d}-15", 'employee': INTERNS[9], 'daily_dept': SHIKUM_A, 'status': 'עובד',
         'note': '', 'is_manual': 'True', 'side': ''},
        # non-manual (auto) row that must be ignored by the manual branch
        {'date': f"{YEAR}-{MONTH:02d}-19", 'employee': INTERNS[4], 'daily_dept': PNIM, 'status': 'חופש',
         'note': '', 'is_manual': 'False', 'side': ''},
    ])

    konenut = pd.DataFrame([
        {'date': f"{YEAR}-{MONTH:02d}-{d:02d}", 'pnim_dr': SENIORS[d % 4], 'rehab_dr1': SENIORS[(d + 1) % 4],
         'rehab_dr2': '' if d % 3 else SENIORS[(d + 2) % 4]} for d in range(1, 15)])

    settings = pd.DataFrame([{'key': 'active_month', 'value': str(MONTH)},
                             {'key': 'daily_active_month', 'value': str(MONTH)},
                             {'key': 'daily_requests_open', 'value': 'True'}])
    swap = pd.DataFrame(columns=['requester', 'requester_date', 'requester_dept', 'candidate',
                                 'candidate_date', 'candidate_dept', 'swap_type', 'chain_ext',
                                 'chain_ext_dept', 'created_at', 'status'])
    return {'staff': staff, 'schedule': sched, 'requests': reqs, 'special_days': special,
            'dept_rotation': rot, 'absence_requests': ar, 'work_schedule_daily': wsd,
            'konenut': konenut, 'settings': settings, 'swap_requests': swap}
