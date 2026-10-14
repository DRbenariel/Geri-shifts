'use client';
import { useState } from 'react';
import { ArrowsClockwise, CalendarPlus, Key, MagnifyingGlass, Plus, Trash } from '@phosphor-icons/react';
import { useStore } from '@/lib/store';
import { ME, type SpecialDay } from '@/lib/mock';
import { fmtDate } from '@/lib/logic';
import { Bezel, Cta, Field, Note, PageHead } from '../ui';

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
  const { db } = useStore();
  const mine = db.schedule.filter((r) => r.employee === ME.name && r.date >= '2026-10-06');
  return (
    <Bezel>
      <h2 className="sec"><ArrowsClockwise size={22} />חיפוש החלפות</h2>
      <Field label="המשמרות הקרובות שלי">
        <select className="input" disabled={!mine.length}>{mine.length ? mine.map((r) => <option key={r.date + r.dept}>{fmtDate(r.date)} {r.dept}</option>) : <option>אין לך משמרות קרובות</option>}</select>
      </Field>
      <Cta variant="teal" icon={<MagnifyingGlass size={16} />} disabled={!mine.length}>חפש מחליפים</Cta>
      <p className="muted small" style={{ marginTop: 12 }}>עובדים רואים כאן החלפה מלאה, כיסוי חד-צדדי והחלפה משולשת, ושולחים בקשה שמגיעה לאישורך בלשונית סידור תורנויות.</p>
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
  return (
    <>
      <PageHead eyebrow={`${ME.name} · ${ME.type}`} title="הגדרות" />
      <div className="cols2" style={{ alignItems: 'start' }}>
        <div><Password /><SwapSearch /></div>
        <div><SpecialDays /></div>
      </div>
    </>
  );
}
