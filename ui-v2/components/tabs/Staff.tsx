'use client';
import { useEffect, useState } from 'react';
import { Check, CloudArrowDown, FloppyDisk, LockSimple, Plus, PushPin, Star, Trash, UserPlus, X } from '@phosphor-icons/react';
import { useStore } from '@/lib/store';
import { DAILY_DEPTS, DAYS_IN_MONTH, DOW_FULL, HEB_MONTHS, MONTH, ROLES, STAFF_DEPTS, YEAR, dowOf, iso, type Role, type Staff } from '@/lib/mock';
import { absenceConflicts, constraintCounters, fmtRange } from '@/lib/logic';
import { Bezel, Cta, Expander, Field, Note, PageHead } from '../ui';

export function ConstraintCalendar({ cons, onToggle, special }: { cons: Record<number, 'B' | 'R'>; onToggle: (d: number) => void; special: Record<number, string> }) {
  const c = constraintCounters(cons);
  const ring = (val: number, max: number, ok: boolean) => {
    const r = 22, C = 2 * Math.PI * r, p = Math.min(val / max, 1);
    return <svg width="54" height="54" viewBox="0 0 54 54" aria-hidden><circle cx="27" cy="27" r={r} fill="none" stroke="#EEF1F3" strokeWidth="6" />
      <circle cx="27" cy="27" r={r} fill="none" stroke={ok ? 'var(--accent)' : 'var(--danger)'} strokeWidth="6" strokeLinecap="round" strokeDasharray={`${C * p} ${C}`} transform="rotate(-90 27 27)" style={{ transition: 'stroke-dasharray .8s var(--ease)' }} /></svg>;
  };
  return (
    <div className="split">
      <div className="cal">
        {DOW_FULL.map((h, i) => <div key={h} className={`h ${i >= 5 ? 'we' : ''}`}>{h}</div>)}
        {Array.from({ length: dowOf(YEAR, MONTH, 1) }, (_, i) => <div key={'b' + i} className="day blank" />)}
        {Array.from({ length: DAYS_IN_MONTH }, (_, i) => i + 1).map((d) => {
          const v = cons[d]; const we = dowOf(YEAR, MONTH, d) >= 5;
          return (
            <button key={d} className={`day ${v ?? ''} ${we ? 'we' : ''}`} onClick={() => onToggle(d)} aria-label={`${d}/${MONTH} ${v === 'B' ? 'חסימה' : v === 'R' ? 'בקשה' : 'רגיל'}`}>
              <span className="num">{d}{special[d] && <PushPin size={12} weight="fill" />}</span>
              {special[d] && <span className="sp">{special[d]}</span>}
              <span className="st">{v === 'B' && <><LockSimple size={13} weight="bold" /><span>חסימה</span></>}{v === 'R' && <><Star size={13} weight="fill" /><span>בקשה</span></>}</span>
            </button>
          );
        })}
      </div>
      <div className="cardlist">
        <div className="ring">{ring(c.blocks, 10, true)}<div><div className="t">חסימות</div><div className="v">{c.blocks}</div></div></div>
        <div className="ring">{ring(c.wishes, 2, c.okWish)}<div><div className="t">בקשות</div><div className="v">{c.wishes}<small> מתוך 2</small></div></div></div>
        <div className="ring">{ring(c.thu, 2, c.okThu)}<div><div className="t">ימי חמישי פנויים</div><div className="v">{c.thu}<small> מינימום 2</small></div></div></div>
        <div className="ring">{ring(c.wknd, 4, c.okWknd)}<div><div className="t">ימי סופ&quot;ש פנויים</div><div className="v">{c.wknd}<small> מינימום 4</small></div></div></div>
        <p className="muted small">רגיל, חסימה, בקשה: כל לחיצה מחליפה מצב. מנהל/ת יכול/ה לשמור גם אם הכללים לא מתקיימים.</p>
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
  return (
    <Bezel>
      <div className="row" style={{ marginBottom: 14 }}>
        <h2 className="sec" style={{ margin: 0 }}>טבלת צוות <span className="badge b-mute">{rows.length}</span></h2>
        <span className="grow" />
        <button className="btn" onClick={() => setRows([...rows, { name: '', type: 'מתמחה', dept: 'שיקום', monthly_quota: 6, weekend_quota: 1, only_home_dept: false, email: '', manage_depts: [], recurring_absent_days: '', manual_schedule_only: false }])}><Plus size={14} />שורה</button>
      </div>
      <div className="tbl-wrap"><table className="t">
        <thead><tr><th>שם</th><th>תפקיד</th><th>מחלקה</th><th>מכסה</th><th>סופ״ש</th><th>אימייל</th><th>מחלקות בניהולו</th><th>ימי היעדרות קבועים</th><th>שיבוץ ידני בלבד</th><th /></tr></thead>
        <tbody>{rows.map((r, i) => (
          <tr key={i}>
            <td><input className="input" value={r.name} onChange={(e) => upd(i, { name: e.target.value })} style={{ minWidth: 130 }} /></td>
            <td><select className="input" value={r.type} onChange={(e) => upd(i, { type: e.target.value as Role })}>{ROLES.map((x) => <option key={x}>{x}</option>)}</select></td>
            <td><select className="input" value={r.dept} onChange={(e) => upd(i, { dept: e.target.value })}>{STAFF_DEPTS.map((x) => <option key={x}>{x}</option>)}</select></td>
            <td><input className="input" type="number" value={r.monthly_quota} onChange={(e) => upd(i, { monthly_quota: +e.target.value })} style={{ width: 70 }} /></td>
            <td><input className="input" type="number" value={r.weekend_quota} onChange={(e) => upd(i, { weekend_quota: +e.target.value })} style={{ width: 70 }} /></td>
            <td><input className="input" dir="ltr" value={r.email} onChange={(e) => upd(i, { email: e.target.value })} style={{ minWidth: 170 }} /></td>
            <td className="small">{r.manage_depts.join(', ') || <span className="muted">-</span>}</td>
            <td><input className="input" value={r.recurring_absent_days} placeholder="למשל ד,ה" onChange={(e) => upd(i, { recurring_absent_days: e.target.value })} style={{ width: 80 }} /></td>
            <td style={{ textAlign: 'center' }}><input type="checkbox" checked={r.manual_schedule_only} onChange={(e) => upd(i, { manual_schedule_only: e.target.checked })} style={{ width: 18, height: 18, accentColor: 'var(--accent)' }} /></td>
            <td><button className="iconbtn" aria-label="מחק שורה" onClick={() => setRows(rows.filter((_, j) => j !== i))}><Trash size={14} /></button></td>
          </tr>
        ))}</tbody>
      </table></div>
      <div className="row" style={{ marginTop: 16 }}>
        <Cta icon={<FloppyDisk size={16} />} disabled={!dirty} onClick={() => { mutate((x) => { x.staff = rows.filter((r) => r.name.trim()); }); toast('השינויים בצוות נשמרו. עובדים חדשים קיבלו סיסמה 1234.'); }}>שמור שינויים בצוות</Cta>
        {dirty && <span className="muted small">יש שינויים שלא נשמרו</span>}
      </div>
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
  const toggle = (d: number) => setCons((c) => { const n = { ...c }; const v = n[d]; if (!v) n[d] = 'B'; else if (v === 'B') n[d] = 'R'; else delete n[d]; return n; });
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
