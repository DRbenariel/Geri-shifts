import {
  Absence, DOW_LETTER, FRI_SLOTS, Konenut, MONTH, RequestRow, Role, Rotation, ShiftRow, SpecialDay, Staff, SwapReq, WsdRow, YEAR,
  absences, dowOf, iso, konenut, requests, rotation, schedule, settings, specialDays, staff, swapRequests, wsdManual,
} from './mock';

export interface DB {
  staff: Staff[]; schedule: ShiftRow[]; requests: RequestRow[]; specialDays: SpecialDay[]; rotation: Rotation[];
  absences: Absence[]; wsd: WsdRow[]; konenut: Konenut[]; swapRequests: SwapReq[];
  settings: { active_month: number; daily_active_month: number; daily_requests_open: boolean };
}
export const initialDB = (): DB => structuredClone({
  staff, schedule, requests, specialDays, rotation, absences, wsd: wsdManual, konenut, swapRequests, settings,
});

// ---- Daily status codes (labels from appy.py:1727)
export type Code = 'W' | 'V' | 'S' | 'A' | 'O' | 'T' | 'E';
export const STATUS: Record<Code, { he: string; lab: string }> = {
  W: { he: 'עובד', lab: 'ע' }, V: { he: 'חופש', lab: 'ח' }, S: { he: '202', lab: '202' },
  A: { he: 'אחרי תורנות', lab: 'א' }, O: { he: 'אחר', lab: '+' }, T: { he: 'תורנות', lab: 'ת' }, E: { he: 'לא הוגדר', lab: '·' },
};
const HE_TO_CODE: Record<string, Code> = { 'עובד': 'W', 'חופש': 'V', '202': 'S', 'אחרי תורנות': 'A', 'אחר': 'O', 'תורנות': 'T', '': 'E' };
export const codeToHe = (c: Code) => (c === 'E' ? '' : STATUS[c].he);

/** Manual-cycle order per role (appy.py:1718, _cycle_for_role 1787). */
export function cycleFor(role: Role): Code[] {
  if (role === 'מנהל מחלקה') return ['E', 'W'];
  if (role === 'רופא בכיר') return ['W', 'V', 'A', 'O', 'E'];
  return ['W', 'V', 'S', 'A', 'O', 'E'];
}

export const nightOn = (db: DB, date: string, emp: string) => db.schedule.some((r) => r.date === date && r.employee === emp && !r.dept.startsWith('שישי'));
export const friOn = (db: DB, date: string, emp: string) => db.schedule.some((r) => r.date === date && r.employee === emp && FRI_SLOTS.includes(r.dept));

/** Mirrors _derive_auto_status priority order (appy.py:1831). */
export function deriveStatus(db: DB, y: number, m: number, d: number, emp: string): { code: Code; manual: boolean; note: string } {
  const date = iso(y, m, d);
  const w = dowOf(y, m, d);
  const person = db.staff.find((s) => s.name === emp);
  const man = db.wsd.find((r) => r.date === date && r.employee === emp && r.is_manual);
  if (w === 6) return { code: 'V', manual: false, note: '' };
  if (w === 5) return { code: friOn(db, date, emp) ? 'W' : 'V', manual: false, note: '' };
  if (man) return { code: HE_TO_CODE[man.status] ?? 'O', manual: true, note: man.note };
  const ab = db.absences.find((a) => a.employee === emp && a.status === 'approved' && a.start_date <= date && a.end_date >= date);
  if (ab) return { code: ab.type === '202' ? 'S' : 'V', manual: false, note: ab.notes };
  if (person?.recurring_absent_days.split(',').map((s) => s.trim()).includes(DOW_LETTER[w])) return { code: 'V', manual: false, note: 'היעדרות קבועה' };
  if (nightOn(db, date, emp)) return { code: 'T', manual: false, note: '' };
  const prev = new Date(y, m - 1, d - 1);
  if (nightOn(db, iso(prev.getFullYear(), prev.getMonth() + 1, prev.getDate()), emp)) return { code: 'A', manual: false, note: '' };
  if (person && (person.type === 'מנהל מחלקה' || person.manual_schedule_only)) return { code: 'E', manual: false, note: '' };
  return { code: 'W', manual: false, note: '' };
}

export function setManual(db: DB, date: string, emp: string, dept: string, code: Code, note?: string) {
  const i = db.wsd.findIndex((r) => r.date === date && r.employee === emp);
  const row: WsdRow = { date, employee: emp, daily_dept: dept, status: codeToHe(code), note: note ?? (i >= 0 ? db.wsd[i].note : ''), is_manual: true };
  if (i >= 0) db.wsd[i] = { ...db.wsd[i], ...row }; else db.wsd.push(row);
}

export const deptOf = (db: DB, emp: string, ym = '2026-11') => db.rotation.find((r) => r.employee === emp && r.year_month === ym);

/** Approved absences in the same dept overlapping the given range (appy.py _absence_conflicts 1616). */
export function absenceConflicts(db: DB, a: Pick<Absence, 'employee' | 'start_date' | 'end_date' | 'dept_at_request'>) {
  return db.absences.filter((b) => b.status === 'approved' && b.employee !== a.employee && b.dept_at_request === a.dept_at_request
    && b.start_date <= a.end_date && b.end_date >= a.start_date);
}

export const fmtDate = (s: string) => { const [, m, d] = s.split('-'); return `${+d}/${+m}`; };
export const fmtRange = (a: string, b: string) => (a === b ? fmtDate(a) : `${fmtDate(a)} - ${fmtDate(b)}`);
export const initials = (n: string) => n.replace('ד"ר ', '').split(' ').map((x) => x[0]).join('');
export const first = (n: string) => n.replace('ד"ר ', '').split(' ')[0];
export const isDoctor = (r: Role) => r === 'רופא בכיר' || r === 'מנהל מחלקה' || r === 'מנהל/ת' || r === 'מנהל על';

/** Constraint validation for interns (appy.py 8228-8410). */
export function constraintCounters(cons: Record<number, 'B' | 'R'>, y = YEAR, m = MONTH) {
  let blocks = 0, wishes = 0, thu = 0, wknd = 0;
  const n = new Date(y, m, 0).getDate();
  for (let d = 1; d <= n; d++) {
    const v = cons[d]; const w = dowOf(y, m, d);
    if (v === 'B') blocks++;
    if (v === 'R') wishes++;
    if (w === 4 && v !== 'B') thu++;
    if ((w === 5 || w === 6) && v !== 'B') wknd++;
  }
  return { blocks, wishes, thu, wknd, okWish: wishes <= 2, okThu: thu >= 2, okWknd: wknd >= 4 };
}
