'use client';
import { useEffect, useState } from 'react';
import { Check, CloudArrowDown, FloppyDisk, LockSimple, Plus, PushPin, Star, Trash, UserMinus, UserPlus, Warning, X } from '@phosphor-icons/react';
import { useStore } from '@/lib/store';
import { DAILY_DEPTS, DOW_FULL, HEB_MONTHS, MONTH, ROLES, STAFF_DEPTS, YEAR, dowOf, iso, type Role, type Staff } from '@/lib/mock';
import { absenceConflicts, constraintCounters, fmtRange } from '@/lib/logic';
import { Bezel, Cta, Expander, Field, MarkMode, Modal, Note, PageHead } from '../ui';

/** rules=false hides the Thursday/weekend counters (תורן חוץ, and the admin editor which saves without enforcing them). */
/** Marking mode: pick "חסימה" or "בקשה" once, then each tap marks a day with it (tap again to clear). */
export function ConstraintCalendar({ cons, onToggle, special, rules = true, y = YEAR, m = MONTH }: { cons: Record<number, 'B' | 'R'>; onToggle: (d: number, v: 'B' | 'R' | null) => void; special: Record<number, string>; rules?: boolean; y?: number; m?: number }) {
  const c = constraintCounters(cons, y, m);
  const [mode, setMode] = useState<'B' | 'R'>('B');
  const tap = (d: number) => onToggle(d, cons[d] === mode ? null : mode);
  const nDays = new Date(y, m, 0).getDate();
  // Rule counters as one compact line above the calendar, so they stay in view while tapping (no progress rings).
  const ctr = (label: string, val: string, ok: boolean | null, rule = '') => (
    <span className={`ctr ${ok === null ? '' : ok ? 'ok' : 'bad'}`} title={rule}>
      {ok === false ? <Warning size={14} weight="fill" /> : ok ? <Check size={14} weight="bold" /> : null}
      <b>{val}</b> {label}
    </span>
  );
  return (
    <div>
      <div className="ctrs" aria-live="polite">
        {ctr('חסימות', String(c.blocks), null)}
        {ctr('בקשות', `${c.wishes}/2`, c.okWish, 'עד 2 בקשות')}
        {rules && ctr('ה׳ פנויים', String(c.thu), c.okThu, 'צריך לפחות 2 ימי חמישי פנויים')}
        {rules && ctr('סופ״ש פנויים', String(c.wknd), c.okWknd, 'צריך לפחות 4 ימי סופ״ש פנויים')}
      </div>
      <MarkMode value={mode} onChange={setMode} options={[
        { v: 'B', label: 'חסימה', hint: 'לא יכול/ה', cls: 'B', icon: <LockSimple size={15} weight="bold" /> },
        { v: 'R', label: 'בקשה', hint: 'רוצה לעבוד', cls: 'R', icon: <Star size={15} weight="fill" /> },
      ]} />
      <p className="muted small tap-hint">לחיצה על יום מסמנת {mode === 'B' ? 'חסימה' : 'בקשה'}. לחיצה נוספת מבטלת.{rules && ' צריך להשאיר לפחות 2 ימי חמישי ו-4 ימי סופ״ש פנויים.'}</p>
      <div className="cal">
        {DOW_FULL.map((h, i) => <div key={h} className={`h ${i >= 5 ? 'we' : ''}`}>{h}</div>)}
        {Array.from({ length: dowOf(y, m, 1) }, (_, i) => <div key={'b' + i} className="day blank" />)}
        {Array.from({ length: nDays }, (_, i) => i + 1).map((d) => {
          const v = cons[d]; const we = dowOf(y, m, d) >= 5;
          return (
            <button key={d} className={`day ${v ?? ''} ${we ? 'we' : ''}`} onClick={() => tap(d)} aria-label={`${d}/${m} ${v === 'B' ? 'חסימה' : v === 'R' ? 'בקשה' : 'פנוי'}`}>
              <span className="num">{d}{special[d] && <PushPin size={12} weight="fill" />}</span>
              {special[d] && <span className="sp">{special[d]}</span>}
              <span className="st">{v === 'B' && <><LockSimple size={13} weight="bold" /><span>חסימה</span></>}{v === 'R' && <><Star size={13} weight="fill" /><span>בקשה</span></>}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function AddEmployee() {
  const { mutate, toast } = useStore();
  const blank = { name: '', type: 'מתמחה' as Role, email: '', dept: 'שיקום', monthly_quota: 6, weekend_quota: 1, only_home_dept: false, manage_depts: [] as string[] };
  const [f, setF] = useState(blank);
  const [ok, setOk] = useState('');
  const add = () => {
    if (!f.name.trim()) return toast('חסר שם', 'err');
    mutate((x) => { x.staff.push({ ...f, name: f.name.trim(), recurring_absent_days: '', manual_schedule_only: false }); });
    setOk(`${f.name} נוסף/ה. סיסמה ראשונית: 1234 (יש להחליף בכניסה הראשונה).`); setF(blank);
  };
  return (
    <Expander title="הוספת עובד/ת" icon={<UserPlus size={20} />}>
      {ok && <Note kind="ok">{ok}</Note>}
      <div className="cols3">
        <Field label="שם מלא"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="תפקיד"><select className="input" value={f.type} onChange={(e) => setF({ ...f, type: e.target.value as Role })}>{ROLES.map((r) => <option key={r}>{r}</option>)}</select></Field>
        <Field label="אימייל"><input className="input" type="email" dir="ltr" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="מחלקה"><select className="input" value={f.dept} onChange={(e) => setF({ ...f, dept: e.target.value })}>{STAFF_DEPTS.map((d) => <option key={d}>{d}</option>)}</select></Field>
        <Field label="מכסה חודשית"><input className="input" type="number" value={f.monthly_quota} onChange={(e) => setF({ ...f, monthly_quota: +e.target.value })} /></Field>
        <Field label="מכסת סופ״ש"><input className="input" type="number" value={f.weekend_quota} onChange={(e) => setF({ ...f, weekend_quota: +e.target.value })} /></Field>
      </div>
      <label className="check" style={{ marginBottom: 14 }}><input type="checkbox" checked={f.only_home_dept} onChange={(e) => setF({ ...f, only_home_dept: e.target.checked })} />מוגבל/ת למחלקה זו בלבד</label>
      {f.type === 'מנהל מחלקה' && (
        <Field label="מחלקות בניהולו/ה">
          <div className="chips">{DAILY_DEPTS.map((d) => { const on = f.manage_depts.includes(d); return <button key={d} className={`chip ${on ? 'sel' : ''}`} onClick={() => setF({ ...f, manage_depts: on ? f.manage_depts.filter((x) => x !== d) : [...f.manage_depts, d] })}>{on && <Check size={12} />}{d}</button>; })}</div>
        </Field>
      )}
      <Cta variant="teal" icon={<Plus size={16} />} onClick={add}>הוסף לצוות</Cta>
    </Expander>
  );
}

function StaffTable() {
  const { db, mutate, toast } = useStore();
  const [rows, setRows] = useState<Staff[]>(() => structuredClone(db.staff));
  useEffect(() => { setRows(structuredClone(db.staff)); }, [db.staff]);
  const dirty = JSON.stringify(rows) !== JSON.stringify(db.staff);
  const upd = (i: number, p: Partial<Staff>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...p } : r)));
  const [del, setDel] = useState<string | null>(null);
  // What still references the employee: shown before deleting, so open shifts can be reassigned first.
  const refs = (name: string) => ({
    shifts: db.schedule.filter((r) => r.employee === name).length,
    cons: db.requests.filter((r) => r.employee === name).length,
    abs: db.absences.filter((a) => a.employee === name && a.status !== 'rejected').length,
  });
  const askDelete = (i: number) => {
    const r = rows[i];
    if (!db.staff.some((s) => s.name === r.name)) return setRows(rows.filter((_, j) => j !== i)); // unsaved row: just drop it
    setDel(r.name);
  };
  const doDelete = (name: string) => {
    mutate((x) => { x.staff = x.staff.filter((s) => s.name !== name); x.requests = x.requests.filter((r) => r.employee !== name); });
    toast(`${name} נמחק/ה מהצוות`, 'warn'); setDel(null);
  };
  return (
    <Bezel>
      <div className="row" style={{ marginBottom: 14 }}>
        <h2 className="sec" style={{ margin: 0 }}>טבלת צוות <span className="badge b-mute">{rows.length}</span></h2>
        <span className="grow" />
        <button className="btn" onClick={() => setRows([...rows, { name: '', type: 'מתמחה', dept: 'שיקום', monthly_quota: 6, weekend_quota: 1, only_home_dept: false, email: '', manage_depts: [], recurring_absent_days: '', manual_schedule_only: false }])}><Plus size={14} />שורה</button>
      </div>
      <div className="tbl-wrap"><table className="t">
        <thead><tr><th aria-label="מחיקה" /><th>שם</th><th>תפקיד</th><th>מחלקה</th><th>מכסה</th><th>סופ״ש</th><th>אימייל</th><th>מחלקות בניהולו</th><th>ימי היעדרות קבועים</th><th>שיבוץ ידני בלבד</th></tr></thead>
        <tbody>{rows.map((r, i) => (
          <tr key={i}>
            <td><button className="iconbtn del" aria-label={`מחק את ${r.name || 'השורה'}`} title="מחק עובד/ת" onClick={() => askDelete(i)}><UserMinus size={16} /></button></td>
            <td><input className="input" value={r.name} onChange={(e) => upd(i, { name: e.target.value })} style={{ minWidth: 130 }} /></td>
            <td><select className="input" value={r.type} onChange={(e) => upd(i, { type: e.target.value as Role })}>{ROLES.map((x) => <option key={x}>{x}</option>)}</select></td>
            <td><select className="input" value={r.dept} onChange={(e) => upd(i, { dept: e.target.value })}>{STAFF_DEPTS.map((x) => <option key={x}>{x}</option>)}</select></td>
            <td><input className="input" type="number" value={r.monthly_quota} onChange={(e) => upd(i, { monthly_quota: +e.target.value })} style={{ width: 70 }} /></td>
            <td><input className="input" type="number" value={r.weekend_quota} onChange={(e) => upd(i, { weekend_quota: +e.target.value })} style={{ width: 70 }} /></td>
            <td><input className="input" dir="ltr" value={r.email} onChange={(e) => upd(i, { email: e.target.value })} style={{ minWidth: 170 }} /></td>
            <td className="small">{r.manage_depts.join(', ') || <span className="muted">-</span>}</td>
            <td><input className="input" value={r.recurring_absent_days} placeholder="למשל ד,ה" onChange={(e) => upd(i, { recurring_absent_days: e.target.value })} style={{ width: 80 }} /></td>
            <td style={{ textAlign: 'center' }}><input type="checkbox" checked={r.manual_schedule_only} onChange={(e) => upd(i, { manual_schedule_only: e.target.checked })} style={{ width: 18, height: 18, accentColor: 'var(--accent)' }} /></td>
          </tr>
        ))}</tbody>
      </table></div>
      <div className="row" style={{ marginTop: 16 }}>
        <Cta icon={<FloppyDisk size={16} />} disabled={!dirty} onClick={() => { mutate((x) => { x.staff = rows.filter((r) => r.name.trim()); }); toast('השינויים בצוות נשמרו. עובדים חדשים קיבלו סיסמה 1234.'); }}>שמור שינויים בצוות</Cta>
        {dirty && <span className="muted small">יש שינויים שלא נשמרו</span>}
      </div>
      <Modal open={!!del} onClose={() => setDel(null)}>
        {del && (() => { const c = refs(del); return <>
          <h2 className="sec"><UserMinus size={22} />למחוק את {del} מהצוות?</h2>
          <p className="muted" style={{ marginBottom: 12 }}>העובד/ת לא יוכל/תוכל להתחבר ולא יופיע/תופיע בשיבוצים הבאים. האילוצים שלו/ה לחודש הפתוח יימחקו.</p>
          {c.shifts + c.abs > 0
            ? <Note kind="warn">עדיין רשומים על שמו/ה: {c.shifts > 0 && <b>{c.shifts} תורנויות</b>}{c.shifts > 0 && c.abs > 0 && ', '}{c.abs > 0 && <b>{c.abs} היעדרויות</b>}. הן נשארות בסידור ויש לשבץ מחליף ידנית.</Note>
            : <Note kind="info">אין לו/ה תורנויות או היעדרויות רשומות.</Note>}
          <div className="row" style={{ marginTop: 16 }}>
            <Cta variant="danger" icon={<Trash size={16} />} onClick={() => doDelete(del)}>מחק עובד/ת</Cta>
            <button className="btn" onClick={() => setDel(null)}>ביטול</button>
          </div>
        </>; })()}
      </Modal>
    </Bezel>
  );
}

function PerEmployee() {
  const { db, mutate, toast } = useStore();
  const pool = db.staff.filter((s) => s.type === 'מתמחה' || s.type === 'תורן חוץ' || s.type === 'רופא בכיר');
  const [emp, setEmp] = useState(pool[0].name);
  const fromDb = () => Object.fromEntries(db.requests.filter((r) => r.employee === emp).map((r) => [+r.date.slice(8), r.status === 'אילוץ' ? 'B' : 'R'])) as Record<number, 'B' | 'R'>;
  const [cons, setCons] = useState(fromDb);
  useEffect(() => { setCons(fromDb()); }, [emp]); // eslint-disable-line react-hooks/exhaustive-deps
  const special = Object.fromEntries(db.specialDays.filter((s) => s.date.startsWith('2026-11')).map((s) => [+s.date.slice(8), s.description]));
  const toggle = (d: number, v: 'B' | 'R' | null) => setCons((c) => { const n = { ...c }; if (v) n[d] = v; else delete n[d]; return n; });
  const myAbs = db.absences.filter((a) => a.employee === emp);
  return (
    <Bezel>
      <h2 className="sec">ניהול אילוצים ומשמרות לעובד/ת</h2>
      <div className="row" style={{ marginBottom: 18 }}>
        <select className="input" style={{ width: 240 }} value={emp} onChange={(e) => setEmp(e.target.value)}>{pool.map((s) => <option key={s.name}>{s.name}</option>)}</select>
        <span className="muted small">{HEB_MONTHS[MONTH - 1]} {YEAR}</span>
      </div>
      <ConstraintCalendar cons={cons} onToggle={toggle} special={special} />
      <div style={{ marginTop: 16 }}>
        <Cta icon={<FloppyDisk size={16} />} onClick={() => { mutate((x) => { x.requests = x.requests.filter((r) => r.employee !== emp).concat(Object.entries(cons).map(([d, v]) => ({ employee: emp, date: iso(YEAR, MONTH, +d), status: v === 'B' ? 'אילוץ' as const : 'בקשה' as const }))); }); toast(`האילוצים של ${emp} נשמרו`); }}>שמור שינויים לעובד/ת זה/ו</Cta>
      </div>
      <h3 className="sub" style={{ marginTop: 28 }}>היעדרויות יומיות</h3>
      {myAbs.filter((a) => a.status === 'pending').map((a) => {
        const conf = absenceConflicts(db, a);
        return (
          <div key={a.id} className="rcard" style={{ marginBottom: 10 }}>
            <div className="main"><b>{fmtRange(a.start_date, a.end_date)} · {a.type}</b><div className="meta">{conf.length ? `חפיפה עם ${conf.map((c) => c.employee).join(', ')}` : 'אין חפיפה'}</div></div>
            <button className="btn ok" onClick={() => { mutate((x) => { x.absences.find((q) => q.id === a.id)!.status = 'approved'; }); toast('אושר'); }}><Check size={14} />{conf.length ? 'כן, אשר למרות החפיפה' : 'אשר'}</button>
            <button className="btn no" onClick={() => { mutate((x) => { x.absences.find((q) => q.id === a.id)!.status = 'rejected'; }); toast('נדחה', 'info'); }}><X size={14} />דחה</button>
          </div>
        );
      })}
      {myAbs.length === 0 ? <p className="muted small">אין היעדרויות.</p> : (
        <div className="tbl-wrap"><table className="t"><thead><tr><th>תאריכים</th><th>סוג</th><th>סטטוס</th><th>אושר ע״י</th><th>הערה</th></tr></thead>
          <tbody>{myAbs.map((a) => <tr key={a.id}><td>{fmtRange(a.start_date, a.end_date)}</td><td>{a.type}</td>
            <td><span className={`badge ${a.status === 'approved' ? 'b-ok' : a.status === 'pending' ? 'b-warn' : 'b-err'}`}>{a.status === 'approved' ? 'אושר' : a.status === 'pending' ? 'ממתין' : 'נדחה'}</span></td>
            <td>{a.approved_by}</td><td className="muted">{a.notes}</td></tr>)}</tbody></table></div>
      )}
    </Bezel>
  );
}

export default function StaffTab() {
  const { db, mutate, toast } = useStore();
  const nightPool = db.staff.filter((s) => s.type === 'מתמחה' || s.type === 'תורן חוץ');
  return (
    <>
      <PageHead eyebrow="מנהל על" title="צוות" sub={`${db.staff.length} אנשי צוות`}
        actions={<button className="btn" onClick={() => toast('הנתונים סונכרנו מהענן. עריכות ישירות בגיליון נדרסו.', 'warn')}><CloudArrowDown size={16} />סנכרן נתונים מהענן</button>} />
      <AddEmployee />
      <Bezel>
        <h2 className="sec">מוגבלים למחלקת הבית בלבד</h2>
        <div className="chips">
          {nightPool.map((s) => <button key={s.name} className={`chip ${s.only_home_dept ? 'sel' : ''}`} onClick={() => mutate((x) => { const p = x.staff.find((q) => q.name === s.name)!; p.only_home_dept = !p.only_home_dept; })}>{s.only_home_dept && <Check size={12} />}{s.name}</button>)}
        </div>
      </Bezel>
      <StaffTable />
      <PerEmployee />
      <p className="muted small">כל אנשי הצוות והכתובות בדמו בדויים.</p>
    </>
  );
}
