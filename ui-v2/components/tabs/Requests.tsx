'use client';
import { useState } from 'react';
import { Check, EnvelopeSimple, Plus, Table, Trash, Tray, Warning, X } from '@phosphor-icons/react';
import { useStore } from '@/lib/store';
import { DAILY_DEPTS, DOW_FULL, dowOf, daysIn, iso, type Absence } from '@/lib/mock';
import { STATUS, absenceConflicts, deptOf, deriveStatus, fmtRange, type Code } from '@/lib/logic';
import { Bezel, Cta, Expander, Field, Note, PageHead, Person, PillSeg } from '../ui';
import { MONTHS12 } from './Work';

const TYPE_BADGE: Record<string, string> = { 'חופש': 'b-info', '202': 'b-warn', 'חופש עתידי': 'b-teal', 'היעדרות אחרת': 'b-mute' };

function Pending({ filter }: { filter: string }) {
  const { db, mutate, toast } = useStore();
  const list = db.absences.filter((a) => a.status === 'pending' && (filter === 'הכל' || a.dept_at_request === filter));
  const decide = (a: Absence, ok: boolean) => {
    mutate((x) => { const r = x.absences.find((q) => q.id === a.id)!; r.status = ok ? 'approved' : 'rejected'; r.approved_by = 'ענבל רז'; });
    toast(`${ok ? 'אושר' : 'נדחה'}: ${a.employee} ${fmtRange(a.start_date, a.end_date)}. נשלח מייל לעובד/ת.`, ok ? 'ok' : 'info');
  };
  if (list.length === 0) return <p className="muted">אין בקשות ממתינות{filter !== 'הכל' ? ` ב${filter}` : ''}.</p>;
  return (
    <div className="cardlist">
      {list.map((a) => {
        const conf = absenceConflicts(db, a);
        const role = db.staff.find((s) => s.name === a.employee)?.type;
        return (
          <div key={a.id} className="rcard" style={conf.length ? { boxShadow: 'inset 0 0 0 1.5px var(--danger)' } : undefined}>
            <Person name={a.employee} role={role} />
            <div className="main">
              <b>{fmtRange(a.start_date, a.end_date)} <span className={`badge ${TYPE_BADGE[a.type]}`}>{a.type}</span></b>
              <div className="meta"><span>{a.dept_at_request}</span>{a.notes && <span>&quot;{a.notes}&quot;</span>}<span>הוגש {a.created_at.slice(8)}/{+a.created_at.slice(5, 7)}</span></div>
              {conf.length > 0 && <div className="meta" style={{ color: 'var(--danger)' }}><Warning size={14} weight="fill" />חפיפה עם {conf.map((c) => `${c.employee} (${fmtRange(c.start_date, c.end_date)})`).join(', ')}</div>}
            </div>
            {conf.length === 0
              ? <button className="btn ok" onClick={() => decide(a, true)}><Check size={14} />אשר</button>
              : <button className="btn ok" onClick={() => decide(a, true)} title="יש חפיפה עם היעדרות מאושרת"><Check size={14} />כן, אשר למרות החפיפה</button>}
            <button className="btn no" onClick={() => decide(a, false)}><X size={14} />דחה</button>
          </div>
        );
      })}
    </div>
  );
}

function AbsenceGantt({ filter }: { filter: string }) {
  const { db } = useStore();
  const [ym, setYm] = useState('2026-11');
  const mo = MONTHS12.find((x) => x.v === ym)!;
  const n = daysIn(mo.y, mo.m);
  const weeks: number[][] = []; let wk: number[] = [];
  for (let d = 1; d <= n; d++) { const w = dowOf(mo.y, mo.m, d); if (w <= 4) wk.push(d); if (w === 4 || d === n) { if (wk.length) weeks.push(wk); wk = []; } }
  const depts = filter === 'הכל' ? DAILY_DEPTS : [filter];
  const absent = (c: Code) => c === 'V' || c === 'S' || c === 'A' || c === 'O';
  return (
    <Bezel>
      <div className="row" style={{ marginBottom: 14 }}>
        <h2 className="sec" style={{ margin: 0 }}>כל ההיעדרויות בחודש</h2><span className="grow" />
        <select className="input" style={{ width: 170 }} value={ym} onChange={(e) => setYm(e.target.value)}>{MONTHS12.map((x) => <option key={x.v} value={x.v}>{x.l}</option>)}</select>
      </div>
      <div className="legend">
        {(['V', 'S', 'A', 'O'] as Code[]).map((c) => <div key={c} className="lg"><span className={c}>{STATUS[c].lab === STATUS[c].he ? '' : STATUS[c].lab}</span>{STATUS[c].he}</div>)}
        <div className="lg"><span className="gcell ov" style={{ width: 24, height: 24 }} />חפיפה במחלקה</div>
      </div>
      {depts.map((dept) => {
        const emps = db.rotation.filter((r) => r.daily_dept === dept).map((r) => r.employee);
        return (
          <div key={dept} style={{ marginBottom: 22 }}>
            <h3 className="sub">{dept}</h3>
            {weeks.map((w, wi) => (
              <div key={wi} className="gantt" style={{ marginBottom: 10 }}>
                <div className="gh" style={{ textAlign: 'right' }}>שבוע {wi + 1}</div>
                {Array.from({ length: 5 }, (_, i) => { const d = w.find((x) => dowOf(mo.y, mo.m, x) === i); return <div key={i} className="gh">{DOW_FULL[i]}<b>{d ?? ''}</b></div>; })}
                {emps.map((e) => [
                  <div key={e} className="small" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{e}</div>,
                  ...Array.from({ length: 5 }, (_, i) => {
                    const d = w.find((x) => dowOf(mo.y, mo.m, x) === i);
                    if (!d) return <div key={e + i} />;
                    const c = deriveStatus(db, mo.y, mo.m, d, e).code;
                    if (!absent(c)) return <div key={e + i} className="gcell" />;
                    const real = (x: Code) => x === 'V' || x === 'S' || x === 'O';
                    const others = real(c) ? emps.filter((o) => o !== e && real(deriveStatus(db, mo.y, mo.m, d, o).code)) : [];
                    return <div key={e + i} className={`gcell ${c} ${others.length ? 'ov' : ''}`} title={others.length ? `חפיפה: ${[e, ...others].join(', ')}` : `${e}: ${STATUS[c].he}`}>{STATUS[c].lab}</div>;
                  }),
                ])}
              </div>
            ))}
          </div>
        );
      })}
    </Bezel>
  );
}

function AddAbsence() {
  const { db, mutate, toast } = useStore();
  const emps = db.staff.filter((s) => ['מתמחה', 'רופא בכיר', 'מנהל מחלקה'].includes(s.type));
  const [f, setF] = useState({ employee: emps[0].name, start_date: '2026-11-25', end_date: '2026-11-26', type: 'חופש' as Absence['type'], notes: '' });
  const dept = deptOf(db, f.employee)?.daily_dept ?? '';
  const conf = absenceConflicts(db, { ...f, dept_at_request: dept });
  const add = () => {
    mutate((x) => { x.absences.push({ id: 'n' + Date.now(), ...f, status: 'approved', dept_at_request: dept, approved_by: 'ענבל רז', created_at: '2026-10-06' }); });
    toast(`נוספה היעדרות מאושרת: ${f.employee} ${fmtRange(f.start_date, f.end_date)}`);
  };
  return (
    <Expander title="הוסף היעדרות עתידית לעובד/ת" icon={<Plus size={20} />}>
      <div className="cols3">
        <Field label="עובד/ת"><select className="input" value={f.employee} onChange={(e) => setF({ ...f, employee: e.target.value })}>{emps.map((s) => <option key={s.name}>{s.name}</option>)}</select></Field>
        <Field label="מתאריך"><input className="input" type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} /></Field>
        <Field label="עד תאריך"><input className="input" type="date" value={f.end_date} onChange={(e) => setF({ ...f, end_date: e.target.value })} /></Field>
        <Field label="סוג"><select className="input" value={f.type} onChange={(e) => setF({ ...f, type: e.target.value as Absence['type'] })}><option>חופש</option><option>202</option><option>היעדרות אחרת</option></select></Field>
        <Field label="הערה"><input className="input" value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
      </div>
      {conf.length > 0 && <Note kind="warn">חפיפה ב{dept}: {conf.map((c) => `${c.employee} ${fmtRange(c.start_date, c.end_date)}`).join(', ')}</Note>}
      <Cta variant="teal" icon={<Check size={16} />} onClick={add}>{conf.length ? 'כן, הוסף למרות החפיפה' : 'הוסף היעדרות מאושרת'}</Cta>
    </Expander>
  );
}

function DeleteApproved() {
  const { db, mutate, toast } = useStore();
  const appr = db.absences.filter((a) => a.status === 'approved');
  const [id, setId] = useState(appr[0]?.id ?? '');
  const [sure, setSure] = useState(false);
  return (
    <Expander title="מחיקת בקשה מאושרת" icon={<Trash size={20} />}>
      <Field label="בקשה"><select className="input" value={id} onChange={(e) => setId(e.target.value)}>{appr.map((a) => <option key={a.id} value={a.id}>{a.employee} · {fmtRange(a.start_date, a.end_date)} · {a.type}</option>)}</select></Field>
      <label className="check" style={{ marginBottom: 14 }}><input type="checkbox" checked={sure} onChange={(e) => setSure(e.target.checked)} />אני בטוח/ה. הימים יחזרו לסטטוס המחושב בסידור העבודה.</label>
      <Cta variant="danger" icon={<Trash size={16} />} disabled={!sure || !id} onClick={() => { mutate((x) => { x.absences = x.absences.filter((a) => a.id !== id); }); setSure(false); toast('הבקשה נמחקה', 'warn'); }}>מחק בקשה</Cta>
    </Expander>
  );
}

function TableView() {
  const { db } = useStore();
  const rows = db.absences.filter((a) => a.status === 'approved' && a.end_date >= '2026-10-06').sort((a, b) => a.start_date.localeCompare(b.start_date));
  return (
    <Expander title="תצוגת טבלה" icon={<Table size={20} />}>
      <div className="tbl-wrap"><table className="t">
        <thead><tr><th>עובד/ת</th><th>מחלקה</th><th>תאריכים</th><th>סוג</th><th>אושר ע״י</th><th>הערה</th></tr></thead>
        <tbody>{rows.map((a) => <tr key={a.id}><td>{a.employee}</td><td>{a.dept_at_request}</td><td>{fmtRange(a.start_date, a.end_date)}</td><td><span className={`badge ${TYPE_BADGE[a.type]}`}>{a.type}</span></td><td>{a.approved_by}</td><td className="muted">{a.notes}</td></tr>)}</tbody>
      </table></div>
    </Expander>
  );
}

export default function Requests() {
  const { db } = useStore();
  const [filter, setFilter] = useState('הכל');
  const n = db.absences.filter((a) => a.status === 'pending').length;
  return (
    <>
      <PageHead eyebrow="היעדרויות מעבודה יומית" title="ניהול בקשות" sub={<span className="row"><EnvelopeSimple size={16} />כל אישור או דחייה שולחים מייל לעובד/ת</span>} />
      <div className="row" style={{ marginBottom: 18 }}>
        <span className="muted small">סינון לפי מחלקה</span>
        <PillSeg value={filter} onChange={setFilter} options={['הכל', ...DAILY_DEPTS].map((d) => ({ v: d, l: d }))} />
      </div>
      <Bezel>
        <h2 className="sec"><Tray size={22} />בקשות ממתינות <span className="badge b-warn">{n}</span></h2>
        <Pending filter={filter} />
      </Bezel>
      <AbsenceGantt filter={filter} />
      <AddAbsence />
      <DeleteApproved />
      <TableView />
    </>
  );
}
