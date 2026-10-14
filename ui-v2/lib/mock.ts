// Fictional mock data for the clickable mockup. No names or values come from the live sheet.
// Shapes mirror the Google Sheets schemas in appy.py init_db() so the real app can reuse the types.

export type Role = 'מתמחה' | 'תורן חוץ' | 'רופא בכיר' | 'מנהל מחלקה' | 'מנהל/ת' | 'מנהל על';

export interface Staff {
  name: string;
  type: Role;
  dept: string;
  monthly_quota: number;
  weekend_quota: number;
  only_home_dept: boolean;
  email: string;
  manage_depts: string[];
  recurring_absent_days: string; // Hebrew day letters, e.g. "ה" or "ד,ה"
  manual_schedule_only: boolean;
}
export interface ShiftRow { date: string; dept: string; employee: string; is_manual: boolean; empty_reason?: string }
export interface RequestRow { employee: string; date: string; status: 'אילוץ' | 'בקשה' }
export interface SpecialDay { date: string; description: string; day_type: 'לידיעה בלבד' | 'כמו שישי (ערב חג)' | 'כמו שבת (חג)' }
export interface Absence {
  id: string; employee: string; start_date: string; end_date: string;
  type: 'חופש' | '202' | 'חופש עתידי' | 'היעדרות אחרת';
  status: 'pending' | 'approved' | 'rejected';
  dept_at_request: string; approved_by: string; notes: string; created_at: string;
}
export interface Rotation { employee: string; year_month: string; daily_dept: string; side: '' | 'ורוד' | 'כחול' }
export interface WsdRow { date: string; employee: string; daily_dept: string; status: string; note: string; is_manual: boolean; side?: string }
export interface Konenut { date: string; pnim_dr: string; rehab_dr1: string; rehab_dr2: string }
export interface SwapReq {
  id: string; requester: string; requester_date: string; requester_dept: string;
  candidate: string; candidate_date: string; candidate_dept: string;
  swap_type: 'full' | 'partial' | 'chain'; chain_ext?: string; chain_ext_dept?: string; created_at: string; status: 'pending' | 'approved' | 'rejected';
}

export const YEAR = 2026;
export const MONTH = 11; // night-shift month on screen + open for constraints
export const DAYS_IN_MONTH = 30;
export const HEB_MONTHS = ['ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני', 'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר'];
export const DOW = ['א׳', 'ב׳', 'ג׳', 'ד׳', 'ה׳', 'ו׳', 'ש׳'];
export const DOW_FULL = ['ראשון', 'שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת'];
export const DOW_LETTER = ['א', 'ב', 'ג', 'ד', 'ה', 'ו', 'ש'];

export const NIGHT_DEPTS = ['שיקום', 'פנימית גריאטרית'];
export const FRI_SLOTS = ['שישי בוקר - שיקום (1)', 'שישי בוקר - שיקום (2)', 'שישי בוקר - פנימית (1)', 'שישי בוקר - פנימית (2)'];
export const DAILY_DEPTS = ["שיקום גריאטרי א'", "שיקום גריאטרי ב'", 'פנימית גריאטרית'];
export const STAFF_DEPTS = ['שיקום', 'פנימית גריאטרית', 'כללי', 'הנהלה', 'זה״ב'];
export const ROLES: Role[] = ['מתמחה', 'תורן חוץ', 'רופא בכיר', 'מנהל מחלקה', 'מנהל/ת', 'מנהל על'];

export const ME = { name: 'ענבל רז', type: 'מנהל על' as Role };

const S = (name: string, type: Role, dept: string, extra: Partial<Staff> = {}): Staff => ({
  name, type, dept, monthly_quota: type === 'מתמחה' ? 6 : type === 'תורן חוץ' ? 4 : 0, weekend_quota: type === 'מתמחה' ? 1 : type === 'תורן חוץ' ? 2 : 0,
  only_home_dept: false, email: '', manage_depts: [], recurring_absent_days: '', manual_schedule_only: false, ...extra,
});

export const INTERNS = ['נועה ברק', 'איתי שגיא', 'מאיה רוזן', 'עומר דהן', 'ליאור קציר', 'הדס אלמוג', 'יונתן פרץ', 'שירה לוי'];
export const EXTERNALS = ['ד"ר אמיר חדד', 'ד"ר סיוון כץ', 'ד"ר דניאל אורן'];

export const staff: Staff[] = [
  ...INTERNS.map((n, i) => S(n, 'מתמחה', i < 5 ? 'שיקום' : 'פנימית גריאטרית', { email: `intern${i + 1}@example.org` })),
  ...EXTERNALS.map((n, i) => S(n, 'תורן חוץ', 'שיקום', { only_home_dept: true, email: `ext${i + 1}@example.org` })),
  S('ד"ר רחל אבירם', 'רופא בכיר', 'שיקום', { email: 'senior1@example.org' }),
  S('ד"ר יואב מזרחי', 'רופא בכיר', 'פנימית גריאטרית', { email: 'senior2@example.org' }),
  S('ד"ר תמר שושן', 'רופא בכיר', 'שיקום', { email: 'senior3@example.org', recurring_absent_days: 'ה' }),
  S('ד"ר שולמית גל', 'מנהל מחלקה', 'שיקום', { email: 'head1@example.org', manage_depts: ["שיקום גריאטרי א'", "שיקום גריאטרי ב'"] }),
  S('ד"ר אבי נחום', 'מנהל מחלקה', 'פנימית גריאטרית', { email: 'head2@example.org', manage_depts: ['פנימית גריאטרית'], manual_schedule_only: true }),
  S('מיכל דוד', 'מנהל/ת', 'הנהלה', { email: 'admin@example.org' }),
  S(ME.name, 'מנהל על', 'הנהלה', { email: 'super@example.org' }),
];

export const iso = (y: number, m: number, d: number) => `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
export const dowOf = (y: number, m: number, d: number) => new Date(y, m - 1, d).getDay();
export const daysIn = (y: number, m: number) => new Date(y, m, 0).getDate();

// ---- Night shifts, November 2026. Rotation keeps a 2-day rest gap; externals only in שיקום.
function buildSchedule(): ShiftRow[] {
  const rows: ShiftRow[] = [];
  const on: Record<number, string[]> = {};
  for (let d = 1; d <= DAYS_IN_MONTH; d++) {
    const pn = INTERNS[(d * 3) % 8];
    const sh = d % 3 === 0 ? EXTERNALS[(d / 3) % 3] : INTERNS[(d * 3 + 4) % 8];
    on[d] = [pn, sh];
    const date = iso(YEAR, MONTH, d);
    rows.push({ date, dept: 'שיקום', employee: sh, is_manual: d === 21 });
    if (d === 14) rows.push({ date, dept: 'פנימית גריאטרית', employee: '---', is_manual: false, empty_reason: 'כל הזמינים חסמו את היום' });
    else rows.push({ date, dept: 'פנימית גריאטרית', employee: pn, is_manual: false });
  }
  for (const d of [6, 13, 20, 27]) {
    const busy = new Set([...(on[d] || []), ...(on[d - 1] || [])]);
    const pool = INTERNS.filter((n) => !busy.has(n));
    FRI_SLOTS.forEach((slot, k) => {
      const date = iso(YEAR, MONTH, d);
      if (d === 27 && k === 3) rows.push({ date, dept: slot, employee: '---', is_manual: false, empty_reason: 'אין מתמחה פנוי שלא עבד בלילה הקודם' });
      else rows.push({ date, dept: slot, employee: pool[(k + d) % pool.length], is_manual: false });
    });
  }
  return rows;
}
export const schedule: ShiftRow[] = buildSchedule();

// ---- Night constraints. Two people have not submitted yet.
export const NOT_SUBMITTED = ['שירה לוי', 'ד"ר דניאל אורן'];
function buildRequests(): RequestRow[] {
  const out: RequestRow[] = [];
  const pool = [...INTERNS, ...EXTERNALS].filter((n) => !NOT_SUBMITTED.includes(n));
  pool.forEach((name, i) => {
    const mine = new Set(schedule.filter((r) => r.employee === name).map((r) => +r.date.slice(8)));
    for (let d = 1; d <= DAYS_IN_MONTH; d++) {
      if (mine.has(d)) continue;
      if ((d + i * 5) % 7 === 0 && d % 3 !== 0) out.push({ employee: name, date: iso(YEAR, MONTH, d), status: 'אילוץ' });
      if (d === 14 && i % 2 === 0) out.push({ employee: name, date: iso(YEAR, MONTH, d), status: 'אילוץ' });
    }
    const w1 = ((i * 4) % 28) + 1, w2 = ((i * 4 + 11) % 28) + 1;
    [w1, w2].forEach((d) => { if (!mine.has(d) && !out.some((r) => r.employee === name && r.date === iso(YEAR, MONTH, d))) out.push({ employee: name, date: iso(YEAR, MONTH, d), status: 'בקשה' }); });
  });
  return out;
}
export const requests: RequestRow[] = buildRequests();

export const specialDays: SpecialDay[] = [
  { date: '2026-11-18', description: 'יום עיון מחלקתי', day_type: 'לידיעה בלבד' },
  { date: '2026-12-04', description: 'ערב חנוכה', day_type: 'לידיעה בלבד' },
  { date: '2026-12-31', description: 'סגירת שנה, כוננות מצומצמת', day_type: 'כמו שישי (ערב חג)' },
];

export const rotation: Rotation[] = [
  ["ד\"ר שולמית גל", "שיקום גריאטרי א'", ''], ['ד"ר רחל אבירם', "שיקום גריאטרי א'", ''], ['נועה ברק', "שיקום גריאטרי א'", ''],
  ['איתי שגיא', "שיקום גריאטרי א'", ''], ['מאיה רוזן', "שיקום גריאטרי א'", ''],
  ['ד"ר תמר שושן', "שיקום גריאטרי ב'", ''], ['עומר דהן', "שיקום גריאטרי ב'", ''], ['ליאור קציר', "שיקום גריאטרי ב'", ''],
  ['ד"ר אבי נחום', 'פנימית גריאטרית', 'ורוד'], ['ד"ר יואב מזרחי', 'פנימית גריאטרית', 'ורוד'], ['הדס אלמוג', 'פנימית גריאטרית', 'ורוד'],
  ['יונתן פרץ', 'פנימית גריאטרית', 'כחול'], ['שירה לוי', 'פנימית גריאטרית', 'כחול'],
].map(([employee, daily_dept, side]) => ({ employee, year_month: '2026-11', daily_dept, side: side as Rotation['side'] }));

export const absences: Absence[] = [
  { id: 'a1', employee: 'ד"ר רחל אבירם', start_date: '2026-11-02', end_date: '2026-11-05', type: 'חופש', status: 'approved', dept_at_request: "שיקום גריאטרי א'", approved_by: 'ד"ר שולמית גל', notes: '', created_at: '2026-10-01' },
  { id: 'a2', employee: 'מאיה רוזן', start_date: '2026-11-09', end_date: '2026-11-11', type: 'חופש', status: 'approved', dept_at_request: "שיקום גריאטרי א'", approved_by: 'ד"ר שולמית גל', notes: 'חופשה משפחתית', created_at: '2026-10-02' },
  { id: 'a3', employee: 'ד"ר יואב מזרחי', start_date: '2026-11-05', end_date: '2026-11-05', type: '202', status: 'approved', dept_at_request: 'פנימית גריאטרית', approved_by: 'ד"ר אבי נחום', notes: '', created_at: '2026-10-03' },
  { id: 'a4', employee: 'עומר דהן', start_date: '2026-11-23', end_date: '2026-11-24', type: 'חופש', status: 'approved', dept_at_request: "שיקום גריאטרי ב'", approved_by: 'ד"ר שולמית גל', notes: '', created_at: '2026-10-03' },
  { id: 'a5', employee: 'איתי שגיא', start_date: '2026-11-10', end_date: '2026-11-10', type: 'חופש', status: 'pending', dept_at_request: "שיקום גריאטרי א'", approved_by: '', notes: 'אירוע משפחתי', created_at: '2026-10-04' },
  { id: 'a6', employee: 'הדס אלמוג', start_date: '2026-11-17', end_date: '2026-11-17', type: '202', status: 'pending', dept_at_request: 'פנימית גריאטרית', approved_by: '', notes: '', created_at: '2026-10-05' },
  { id: 'a7', employee: 'ליאור קציר', start_date: '2026-12-20', end_date: '2026-12-24', type: 'חופש עתידי', status: 'pending', dept_at_request: "שיקום גריאטרי ב'", approved_by: '', notes: 'טיסה לחו"ל', created_at: '2026-10-05' },
  { id: 'a8', employee: 'נועה ברק', start_date: '2026-11-18', end_date: '2026-11-18', type: 'חופש', status: 'rejected', dept_at_request: "שיקום גריאטרי א'", approved_by: 'ד"ר שולמית גל', notes: 'יום עיון מחלקתי', created_at: '2026-10-01' },
];

export const wsdManual: WsdRow[] = [
  { date: '2026-11-01', employee: 'ליאור קציר', daily_dept: "שיקום גריאטרי ב'", status: 'אחר', note: 'קורס החייאה', is_manual: true },
  { date: '2026-11-16', employee: 'יונתן פרץ', daily_dept: "שיקום גריאטרי א'", status: 'עובד', note: 'העברה זמנית', is_manual: true },
  { date: '2026-11-17', employee: 'יונתן פרץ', daily_dept: "שיקום גריאטרי א'", status: 'עובד', note: 'העברה זמנית', is_manual: true },
];

const DOCS = ['ד"ר רחל אבירם', 'ד"ר יואב מזרחי', 'ד"ר תמר שושן', 'ד"ר שולמית גל', 'ד"ר אבי נחום'];
export const konenut: Konenut[] = Array.from({ length: DAYS_IN_MONTH }, (_, i) => {
  const d = i + 1;
  return { date: iso(YEAR, MONTH, d), pnim_dr: DOCS[d % 5], rehab_dr1: DOCS[(d + 2) % 5], rehab_dr2: d % 4 === 0 ? '' : DOCS[(d + 3) % 5] };
});
export const KONENUT_DOCS = DOCS;

export const swapRequests: SwapReq[] = [
  { id: 's1', requester: 'עומר דהן', requester_date: '2026-11-12', requester_dept: 'שיקום', candidate: 'הדס אלמוג', candidate_date: '2026-11-19', candidate_dept: 'פנימית גריאטרית', swap_type: 'full', created_at: '2026-10-05 09:12', status: 'pending' },
  { id: 's2', requester: 'נועה ברק', requester_date: '2026-11-08', requester_dept: 'פנימית גריאטרית', candidate: 'מאיה רוזן', candidate_date: '', candidate_dept: 'שיקום', swap_type: 'chain', chain_ext: 'ד"ר אמיר חדד', chain_ext_dept: 'שיקום', created_at: '2026-10-05 21:40', status: 'pending' },
  { id: 's3', requester: 'יונתן פרץ', requester_date: '2026-11-25', requester_dept: 'פנימית גריאטרית', candidate: 'ליאור קציר', candidate_date: '', candidate_dept: 'פנימית גריאטרית', swap_type: 'partial', created_at: '2026-10-06 07:03', status: 'pending' },
];

export const settings = { active_month: 11, daily_active_month: 11, daily_requests_open: true };

// ---- Reports (mock numbers, labeled as demo data in the UI)
export const dailyReport = [
  { severity: 'קריטי', problem_type: 'ימי שיא חסימה', description: '14/11: 6 מתוך 11 אנשי צוות פעילים חסמו את היום (55%)' },
  { severity: 'קריטי', problem_type: '[שיבוץ] יום ריק', description: '14/11 פנימית גריאטרית: אין אף מועמד זמין גם בכללי הגיבוי' },
  { severity: 'קריטי', problem_type: '[שיבוץ] יום ריק', description: '27/11 שישי בוקר - פנימית (2): אין מתמחה פנוי' },
  { severity: 'אזהרה', problem_type: 'לא הגישו', description: 'שירה לוי, ד"ר דניאל אורן טרם הגישו אילוצים לנובמבר' },
  { severity: 'אזהרה', problem_type: 'סיכון מכסה', description: 'ליאור קציר: 5 ימים זמינים, מכסה חודשית 6' },
  { severity: 'אזהרה', problem_type: 'כיסוי סופ"ש', description: '27/11 (שישי): רק 2 מועמדים זמינים' },
  { severity: 'אזהרה', problem_type: '[שיבוץ] שיבוץ בקושי', description: '21/11 שיקום: שובץ רק בהקלת מרווח מנוחה' },
  { severity: 'מידע', problem_type: '[שיבוץ] סיכום שיבוץ', description: 'אסטרטגיה הטובה ביותר: tier | משמרות רגילות: 59/60 שובצו | שישי בוקר: 15/16 שובצו | ימים ריקים: 2 | שיבוצי גיבוי: 1 | ימים קריטיים: 2 (14/11, 27/11)' },
];
export const analytics = {
  logins: 412, uniqueUsers: 17, mobilePct: 64, avgSubmissions: 1.8,
  byHour: [0, 0, 0, 0, 0, 1, 6, 18, 31, 22, 17, 14, 21, 19, 15, 12, 16, 24, 29, 33, 41, 37, 22, 9],
  tabs: [['הגשת בקשות', 318], ['סידור עבודה', 274], ['סידור תורנויות', 251], ['הגדרות', 96], ['ניהול בקשות', 88], ['גאנט חודשי', 41], ['דוחות וניהול', 37], ['סידור כוננויות', 29], ['צוות', 18]] as [string, number][],
  tabSeconds: [['סידור עבודה', 142], ['הגשת בקשות', 118], ['ניהול בקשות', 97], ['גאנט חודשי', 88], ['סידור תורנויות', 74], ['דוחות וניהול', 66], ['צוות', 51], ['סידור כוננויות', 47], ['הגדרות', 22]] as [string, number][],
  refreshes: [['מאיה רוזן', 7], ['עומר דהן', 4], ['ד"ר סיוון כץ', 3]] as [string, number][],
  submitDay: [3, 9, 14, 11, 6, 4, 2, 1, 1, 0, 1, 0, 0, 0, 0],
};
