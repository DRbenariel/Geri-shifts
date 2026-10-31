'use client';
import { useState } from 'react';
import { ArrowsClockwise, CalendarPlus, Key, MagnifyingGlass, Plus, Trash } from '@phosphor-icons/react';
import { useMe, useStore } from '@/lib/store';
import { roleLabel, type ShiftRow, type SpecialDay } from '@/lib/mock';
import { NIGHT_POOL, canTake, fmtDate, handoff, isWeekendDay, wishedOn } from '@/lib/logic';

const TODAY = '2026-10-18';
import { Bezel, Cta, Field, Note, PageHead, Person } from '../ui';

function Password() {
  const { toast } = useStore();
  const [f, setF] = useState({ cur: '', a: '', b: '' });
  const [err, setErr] = useState('');
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!f.cur) return setErr('הסיסמה הנוכחית שגויה');
    if (!f.a) return setErr('הסיסמה החדשה ריקה');
    if (f.a !== f.b) return setErr('הסיסמאות החדשות לא תואמות');
    setErr(''); setF({ cur: '', a: '', b: '' }); toast('הסיסמה עודכנה');
  };
  return (
    <Bezel>
      <h2 className="sec"><Key size={22} />שינוי סיסמה</h2>
      <form onSubmit={submit}>
        <Field label="סיסמה נוכחית"><input className="input" type="password" value={f.cur} onChange={(e) => setF({ ...f, cur: e.target.value })} autoComplete="current-password" /></Field>
        <Field label="סיסמה חדשה"><input className="input" type="password" value={f.a} onChange={(e) => setF({ ...f, a: e.target.value })} autoComplete="new-password" /></Field>
        <Field label="אימות סיסמה חדשה"><input className="input" type="password" value={f.b} onChange={(e) => setF({ ...f, b: e.target.value })} autoComplete="new-password" /></Field>
        {err && <Note kind="err">{err}</Note>}
        <Cta type="submit" icon={<Key size={16} />}>עדכן סיסמה</Cta>
      </form>
    </Bezel>
  );
}

function SwapSearch() {
  const { db, mutate, toast } = useStore();
  const me = useMe();
  const mine = db.schedule.filter((r) => r.employee === me.name && r.date >= TODAY).sort((a, b) => a.date.localeCompare(b.date));
  const key = (r: ShiftRow) => `${r.date}|${r.dept}`;
  const [sel, setSel] = useState(() => { const h = handoff.swapShift; handoff.swapShift = ''; return mine.some((r) => key(r) === h) ? h : (mine[0] ? key(mine[0]) : ''); });
  const [res, setRes] = useState<null | { full: ShiftRow[]; cover: string[] }>(null);
  const cur = mine.find((r) => key(r) === sel);
  const d = cur ? +cur.date.slice(8) : 0;
  const pending = cur && db.swapRequests.some((q) => q.status === 'pending' && q.requester === me.name && q.requester_date === cur.date);
  const find = () => {
    if (!cur) return;
    const fri = cur.dept.startsWith('שישי');
    const full = db.schedule.filter((r) => r.employee !== '---' && r.employee !== me.name && r.date !== cur.date && r.dept.startsWith('שישי') === fri
      && isWeekendDay(+r.date.slice(8)) === isWeekendDay(d)
      && canTake(db, r.employee, d, cur.dept, r) && canTake(db, me.name, +r.date.slice(8), r.dept, cur)).slice(0, 6);
    const cover = NIGHT_POOL.filter((p) => p !== me.name && canTake(db, p, d, cur.dept));
    setRes({ full, cover });
  };
  const send = (candidate: string, swap_type: 'full' | 'partial', other?: ShiftRow) => {
    if (!cur) return;
    mutate((x) => { x.swapRequests.push({ id: 'q' + Date.now(), requester: me.name, requester_date: cur.date, requester_dept: cur.dept, candidate, candidate_date: other?.date ?? '', candidate_dept: other?.dept ?? cur.dept, swap_type, created_at: '2026-10-18 12:00', status: 'pending' }); });
    toast('הבקשה נשלחה למנהל/ת לאישור'); setRes(null);
  };
  const star = (n: string) => (wishedOn(db, n, d) ? ' ★' : '');
  return (
    <Bezel>
      <h2 className="sec"><ArrowsClockwise size={22} />חיפוש החלפות</h2>
      <Field label="המשמרות הקרובות שלי">
        <select className="input" value={sel} onChange={(e) => { setSel(e.target.value); setRes(null); }}>
          {mine.map((r) => <option key={key(r)} value={key(r)}>{fmtDate(r.date)} · {r.dept}</option>)}
        </select>
      </Field>
      {pending
        ? <Note kind="info">כבר נשלחה בקשת החלפה למשמרת הזו, והיא ממתינה לאישור.</Note>
        : <Cta variant="teal" icon={<MagnifyingGlass size={16} />} onClick={find}>חפש מחליפים</Cta>}
      {res && (
        <div style={{ marginTop: 18 }}>
          <h3 className="sub">החלפה מלאה ({res.full.length})</h3>
          {res.full.length === 0 ? <p className="muted small">אין החלפה מלאה שעומדת בכל הכללים.</p> : (
            <div className="cardlist" style={{ marginBottom: 16 }}>
              {res.full.map((r) => (
                <div key={key(r) + r.employee} className="rcard">
                  <Person name={r.employee} role={db.staff.find((x) => x.name === r.employee)?.type} />
                  <div className="main"><b>{r.employee}{star(r.employee)}</b><div className="meta">מציע/ה: {fmtDate(r.date)} · {r.dept}</div></div>
                  <button className="btn" onClick={() => send(r.employee, 'full', r)}><ArrowsClockwise size={14} />בקש החלפה</button>
                </div>
              ))}
            </div>
          )}
          <h3 className="sub">כיסוי חד-צדדי ({res.cover.length})</h3>
          {res.cover.length === 0 ? <p className="muted small">אין מי שיכול/ה לכסות.</p> : (
            <div className="cardlist" style={{ marginBottom: 16 }}>
              {res.cover.map((n) => (
                <div key={n} className="rcard">
                  <Person name={n} role={db.staff.find((x) => x.name === n)?.type} />
                  <div className="main"><b>{n}{star(n)}</b><div className="meta">מכסה/ה את המשמרת בלי משמרת חוזרת</div></div>
                  <button className="btn" onClick={() => send(n, 'partial')}><ArrowsClockwise size={14} />בקש כיסוי</button>
                </div>
              ))}
            </div>
          )}
          <h3 className="sub">החלפה משולשת</h3>
          <p className="muted small">אין אפשרויות כרגע.</p>
          <p className="muted small" style={{ marginTop: 10 }}>★ ביקש/ה לעבוד באותו יום. כל בקשה מגיעה למנהל/ת לאישור.</p>
        </div>
      )}
    </Bezel>
  );
}

function SpecialDays() {
  const { db, mutate, toast } = useStore();
  const [f, setF] = useState<SpecialDay>({ date: '2026-11-26', description: '', day_type: 'לידיעה בלבד' });
  const list = [...db.specialDays].sort((a, b) => a.date.localeCompare(b.date));
  const badge = { 'לידיעה בלבד': 'b-info', 'כמו שישי (ערב חג)': 'b-warn', 'כמו שבת (חג)': 'b-err' } as const;
  return (
    <Bezel>
      <h2 className="sec"><CalendarPlus size={22} />ימים מיוחדים וחגים</h2>
      <div className="cols3">
        <Field label="תאריך"><input className="input" type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
        <Field label="תיאור"><input className="input" value={f.description} placeholder="למשל: ערב חג" onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
        <Field label="סוג יום"><select className="input" value={f.day_type} onChange={(e) => setF({ ...f, day_type: e.target.value as SpecialDay['day_type'] })}>
          <option>לידיעה בלבד</option><option>כמו שישי (ערב חג)</option><option>כמו שבת (חג)</option></select></Field>
      </div>
      <Cta variant="teal" icon={<Plus size={16} />} onClick={() => { if (!f.description.trim()) return toast('חסר תיאור', 'err'); mutate((x) => { x.specialDays.push({ ...f }); }); toast(`נוסף: ${fmtDate(f.date)} ${f.description}`); setF({ ...f, description: '' }); }}>הוסף יום</Cta>
      <div className="tbl-wrap" style={{ marginTop: 18 }}><table className="t"><tbody>
        {list.map((s) => (
          <tr key={s.date + s.description}><td className="num">{fmtDate(s.date)}</td><td>{s.description}</td><td><span className={`badge ${badge[s.day_type]}`}>{s.day_type}</span></td>
            <td style={{ textAlign: 'left' }}><button className="iconbtn" aria-label="מחק" onClick={() => { mutate((x) => { x.specialDays = x.specialDays.filter((q) => !(q.date === s.date && q.description === s.description)); }); toast('היום נמחק', 'info'); }}><Trash size={14} /></button></td></tr>
        ))}
      </tbody></table></div>
    </Bezel>
  );
}

export default function Settings() {
  const { db } = useStore();
  const me = useMe();
  // Swap search: everyone except מנהל/ת, and only with upcoming shifts. Special days: מנהל על only (SCREENS_PLAN 4.2).
  const swaps = me.type !== 'מנהל/ת' && db.schedule.some((r) => r.employee === me.name && r.date >= TODAY);
  const special = me.type === 'מנהל על';
  return (
    <>
      <PageHead eyebrow={`${me.name} · ${roleLabel(me.type)}`} title="הגדרות" />
      <div className={swaps || special ? 'cols2' : ''} style={{ alignItems: 'start', maxWidth: swaps || special ? undefined : 560 }}>
        <div><Password />{special && swaps && <SwapSearch />}</div>
        {(swaps || special) && <div>{special ? <SpecialDays /> : <SwapSearch />}</div>}
      </div>
    </>
  );
}
