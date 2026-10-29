'use client';
import { useState } from 'react';
import { ArrowsClockwise, CalendarPlus, Key, MagnifyingGlass, Plus, Trash } from '@phosphor-icons/react';
import { useApi } from '@/lib/api';
import { handoff } from '@/lib/logic';
import { useMe } from '@/lib/store';
import { roleLabel } from '@/lib/mock';
import { Bezel, Cta, Field, Note, PageHead, Person } from '../ui';
import { Load, dmy, useAction } from './common';

function Password() {
  const { run, busy } = useAction();
  const [f, setF] = useState({ current: '', new: '', confirm: '' });
  return (
    <Bezel>
      <h2 className="sec"><Key size={22} />שינוי סיסמה</h2>
      <form onSubmit={(e) => { e.preventDefault(); run('/me/password', 'POST', f, 'הסיסמה עודכנה').then(() => setF({ current: '', new: '', confirm: '' })).catch(() => {}); }}>
        <Field label="סיסמה נוכחית"><input className="input" type="password" value={f.current} onChange={(e) => setF({ ...f, current: e.target.value })} autoComplete="current-password" /></Field>
        <Field label="סיסמה חדשה"><input className="input" type="password" value={f.new} onChange={(e) => setF({ ...f, new: e.target.value })} autoComplete="new-password" /></Field>
        <Field label="אימות סיסמה חדשה"><input className="input" type="password" value={f.confirm} onChange={(e) => setF({ ...f, confirm: e.target.value })} autoComplete="new-password" /></Field>
        <Cta type="submit" icon={<Key size={16} />} disabled={busy}>עדכן סיסמה</Cta>
      </form>
    </Bezel>
  );
}

interface Cand { name: string; type: string; wished: boolean; their_shift: { date: string; dept: string } | null }
interface Chain { facilitator_name: string; external_name: string; facilitator_wished: boolean; external_wished: boolean }

function Swaps() {
  const mine = useApi<{ date: string; dept: string }[]>('/swaps/mine');
  const { run, busy } = useAction();
  const [sel, setSel] = useState(() => { const h = handoff.swapShift; handoff.swapShift = ''; return h; });
  const [res, setRes] = useState<{ full: Cand[]; partial: Cand[]; chain: Chain[] } | null>(null);
  return (
    <Load q={mine}>{(shifts) => {
      if (shifts.length === 0) return null;
      const key = (s: { date: string; dept: string }) => `${s.date}|${s.dept}`;
      const cur = shifts.find((s) => key(s) === sel) ?? shifts[0];
      const find = () => run<{ full: Cand[]; partial: Cand[]; chain: Chain[] }>(`/swaps/search?date=${cur.date}&dept=${encodeURIComponent(cur.dept)}`, 'GET').then(setRes).catch(() => {});
      const send = (kind: string, candidate: string, chain_ext = '') =>
        run('/swaps', 'POST', { date: cur.date, dept: cur.dept, kind, candidate, chain_ext }, 'הבקשה נשלחה למנהל/ת לאישור').then(() => setRes(null)).catch(() => {});
      return (
        <Bezel>
          <h2 className="sec"><ArrowsClockwise size={22} />חיפוש החלפות</h2>
          <Field label="המשמרות הקרובות שלי">
            <select className="input" value={key(cur)} onChange={(e) => { setSel(e.target.value); setRes(null); }}>
              {shifts.map((s) => <option key={key(s)} value={key(s)}>{dmy(s.date)} · {s.dept}</option>)}
            </select>
          </Field>
          <Cta variant="teal" icon={<MagnifyingGlass size={16} />} disabled={busy} onClick={find}>{busy ? 'מחפש...' : 'חפש מחליפים'}</Cta>
          {res && (
            <div style={{ marginTop: 18 }}>
              {([['full', 'החלפה מלאה'], ['partial', 'כיסוי חד-צדדי']] as const).map(([k, l]) => (
                <div key={k}>
                  <h3 className="sub">{l} ({res[k].length})</h3>
                  {res[k].length === 0 ? <p className="muted small" style={{ marginBottom: 12 }}>אין.</p> : (
                    <div className="cardlist" style={{ marginBottom: 16 }}>
                      {res[k].map((c) => (
                        <div key={c.name} className="rcard">
                          <Person name={c.name} role={c.type} />
                          <div className="main"><b>{c.name}{c.wished ? ' ★' : ''}</b>{c.their_shift && <div className="meta">מציע/ה: {dmy(c.their_shift.date)} · {c.their_shift.dept}</div>}</div>
                          <button className="btn" disabled={busy} onClick={() => send(k, c.name)}><ArrowsClockwise size={14} />בקש</button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              <h3 className="sub">החלפה משולשת ({res.chain.length})</h3>
              {res.chain.length === 0 ? <p className="muted small">אין.</p> : res.chain.map((c) => (
                <div key={c.facilitator_name + c.external_name} className="rcard" style={{ marginBottom: 8 }}>
                  <div className="main"><b>{c.facilitator_name} עובר/ת לפנימית, {c.external_name} מכסה שיקום</b></div>
                  <button className="btn" disabled={busy} onClick={() => send('chain', c.facilitator_name, c.external_name)}>בקש</button>
                </div>
              ))}
              <p className="muted small" style={{ marginTop: 10 }}>★ ביקש/ה לעבוד באותו יום.</p>
            </div>
          )}
        </Bezel>
      );
    }}</Load>
  );
}

function SpecialDays() {
  const q = useApi<{ date: string; description: string; day_type: string }[]>('/special-days');
  const { run, busy } = useAction();
  const [f, setF] = useState({ date: '', description: '', day_type: 'לידיעה בלבד' });
  const badge: Record<string, string> = { 'לידיעה בלבד': 'b-info', 'כמו שישי (ערב חג)': 'b-warn', 'כמו שבת (חג)': 'b-err' };
  return (
    <Bezel>
      <h2 className="sec"><CalendarPlus size={22} />ימים מיוחדים וחגים</h2>
      <div className="cols3">
        <Field label="תאריך"><input className="input" type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
        <Field label="תיאור"><input className="input" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
        <Field label="סוג יום"><select className="input" value={f.day_type} onChange={(e) => setF({ ...f, day_type: e.target.value })}><option>לידיעה בלבד</option><option>כמו שישי (ערב חג)</option><option>כמו שבת (חג)</option></select></Field>
      </div>
      <Cta variant="teal" icon={<Plus size={16} />} disabled={busy || !f.date || !f.description.trim()} onClick={() => run('/special-days', 'POST', f, 'היום נוסף').then(q.reload).catch(() => {})}>הוסף יום</Cta>
      <Load q={q}>{(list) => (
        <div className="tbl-wrap" style={{ marginTop: 18 }}><table className="t"><tbody>
          {list.map((s, i) => ({ s, i })).sort((a, b) => a.s.date.localeCompare(b.s.date)).map(({ s, i }) => (
            <tr key={i}><td className="num">{dmy(s.date)}</td><td>{s.description}</td><td><span className={`badge ${badge[s.day_type] ?? 'b-mute'}`}>{s.day_type}</span></td>
              <td style={{ textAlign: 'left' }}><button className="iconbtn" aria-label="מחק" disabled={busy} onClick={() => { if (confirm(`למחוק את ${s.description}?`)) run(`/special-days/${i}`, 'DELETE', undefined, 'היום נמחק').then(q.reload).catch(() => {}); }}><Trash size={14} /></button></td></tr>
          ))}
        </tbody></table></div>
      )}</Load>
    </Bezel>
  );
}

export default function LiveSettings() {
  const me = useMe();
  const swaps = me.type !== 'מנהל/ת';
  const special = me.type === 'מנהל על';
  return (
    <>
      <PageHead eyebrow={`${me.name} · ${roleLabel(me.type)}`} title="הגדרות" />
      <div className="cols2" style={{ alignItems: 'start' }}>
        <div><Password />{special && swaps && <Swaps />}</div>
        <div>{special ? <SpecialDays /> : swaps ? <Swaps /> : <Note kind="info">אין הגדרות נוספות לתפקיד זה.</Note>}</div>
      </div>
    </>
  );
}
