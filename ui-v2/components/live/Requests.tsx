'use client';
import { useState } from 'react';
import { Check, Plus, Tray, Warning, X } from '@phosphor-icons/react';
import { ApiError, useApi, type AbsGantt, type Pending } from '@/lib/api';
import { DAILY_DEPTS, DOW_LETTER, dowOf } from '@/lib/mock';
import { useMe, ymOf } from '@/lib/store';
import { Bezel, Cta, Expander, Field, Modal, Note, PageHead, Person, PillSeg, useDayTip } from '../ui';
import { Load, MonthPick, range, STATUS_CLASS, useAction } from './common';

const TYPE_BADGE: Record<string, string> = { 'חופש': 'b-info', '202': 'b-warn', 'חופש עתידי': 'b-teal', 'היעדרות אחרת': 'b-mute' };

function PendingList({ filter, onChange }: { filter: string; onChange: () => void }) {
  const q = useApi<Pending[]>(`/absences/pending${filter !== 'הכל' ? `?dept=${encodeURIComponent(filter)}` : ''}`);
  const { run, busy } = useAction();
  const [ask, setAsk] = useState<{ id: string; question: string } | null>(null);
  const approve = async (id: string, force = false) => {
    try { await run(`/absences/${id}/approve`, 'POST', { force }, 'הבקשה אושרה'); setAsk(null); q.reload(); onChange(); }
    catch (e) { if ((e as ApiError).status === 409) setAsk({ id, question: (e as ApiError).message }); }
  };
  return (
    <Load q={q}>{(list) => (
      <>
        {list.length === 0 ? <p className="muted">אין בקשות ממתינות.</p> : (
          <div className="cardlist">
            {list.map((a) => (
              <div key={a.id} className="rcard" style={a.conflicts.length ? { boxShadow: 'inset 0 0 0 1.5px var(--danger)' } : undefined}>
                <Person name={a.employee} />
                <div className="main">
                  <b>{range(a.start_date, a.end_date)} <span className={`badge ${TYPE_BADGE[a.type] ?? 'b-mute'}`}>{a.type}</span></b>
                  <div className="meta"><span>{a.dept_canonical || a.dept_at_request || '—'}</span>{a.notes && <span>&quot;{a.notes}&quot;</span>}</div>
                  {a.conflicts.length > 0 && <div className="meta" style={{ color: 'var(--danger)' }}><Warning size={14} weight="fill" />חפיפה עם {a.conflicts.map((c) => c.employee).join(', ')}</div>}
                </div>
                <button className="btn ok" disabled={busy} onClick={() => approve(a.id)}><Check size={14} />אשר</button>
                <button className="btn no" disabled={busy} onClick={() => run(`/absences/${a.id}/reject`, 'POST', undefined, 'הבקשה נדחתה').then(() => { q.reload(); onChange(); }).catch(() => {})}><X size={14} />דחה</button>
              </div>
            ))}
          </div>
        )}
        <Modal open={!!ask} onClose={() => setAsk(null)}>
          <h2 className="sec"><Warning size={22} />יש חפיפה</h2>
          <p style={{ whiteSpace: 'pre-line', marginBottom: 16 }}>{ask?.question}</p>
          <div className="row">
            <Cta onClick={() => ask && approve(ask.id, true)}>כן, אשר למרות החפיפה</Cta>
            <button className="btn" onClick={() => setAsk(null)}>ביטול</button>
          </div>
        </Modal>
      </>
    )}</Load>
  );
}

function GanttLive({ filter, scope, manager }: { filter: string; scope: string[]; manager: boolean }) {
  const [ym, setYm] = useState(ymOf(new Date().getFullYear(), new Date().getMonth() + 1));
  const [y, m] = ym.split('-').map(Number);
  const dept = filter !== 'הכל' ? filter : manager && scope.length === 1 ? scope[0] : '';
  const q = useApi<AbsGantt | Record<string, AbsGantt>>(`/absences/gantt/${ym}${dept ? `?dept=${encodeURIComponent(dept)}` : ''}`);
  const days = Array.from({ length: new Date(y, m, 0).getDate() }, (_, i) => i + 1).filter((d) => dowOf(y, m, d) <= 4);
  const { bind, node } = useDayTip();
  return (
    <Bezel>
      <div className="row" style={{ marginBottom: 14 }}><h2 className="sec" style={{ margin: 0 }}>כל ההיעדרויות בחודש</h2><span className="grow" /><MonthPick value={ym} onChange={setYm} /></div>
      <Load q={q}>{(raw) => {
        // Managers get {dept: gantt}; admins one gantt across departments.
        const parts: AbsGantt[] = 'by_dept' in raw ? [raw as AbsGantt] : Object.values(raw as Record<string, AbsGantt>);
        const by: Record<string, Record<string, [number, string][]>> = Object.assign({}, ...parts.map((p) => p.by_dept));
        const confMap = new Map(parts.flatMap((p) => p.conflicts.map((c) => [`${c.dept}|${c.day}`, c.employees] as const)));
        const notes: Record<string, Record<string, string>> = Object.assign({}, ...parts.map((p) => p.notes ?? {}));
        const depts = Object.keys(by).filter((d) => !manager || scope.includes(d));
        if (depts.length === 0) return <p className="muted">אין היעדרויות בחודש זה.</p>;
        return depts.map((d) => (
          <div key={d} style={{ marginBottom: 20 }}>
            <h3 className="sub">{d}</h3>
            <div className="tbl-wrap"><table className="t abs-t">
              <thead><tr><th>עובד/ת</th>{days.map((x) => <th key={x} className="num">{x}<div className="muted small">{DOW_LETTER[dowOf(y, m, x)]}</div></th>)}</tr></thead>
              <tbody>{Object.entries(by[d]).map(([emp, items]) => {
                const map = Object.fromEntries(items);
                return <tr key={emp}><td style={{ whiteSpace: 'nowrap' }}>{emp}</td>{days.map((x) => {
                  const st = map[x];
                  if (!st) return <td key={x} />;
                  const others = (confMap.get(`${d}|${x}`) ?? []).filter((o) => o !== emp);
                  const note = notes[emp]?.[String(x)];
                  const lines = [st, ...(note ? [note] : [])];
                  return <td key={x} className={`gc ${STATUS_CLASS[st] ?? 'O'} ${others.length ? 'ov' : ''}`} {...bind(lines)}>{st === '202' ? '202' : st[0]}</td>;
                })}</tr>;
              })}</tbody>
            </table></div>
          </div>
        ));
      }}</Load>
      {node}
    </Bezel>
  );
}

function AddAbsenceLive({ onDone }: { onDone: () => void }) {
  const people = useApi<{ name: string; type: string }[]>('/people');
  const { run, busy } = useAction();
  const [f, setF] = useState({ employee: '', start: '', end: '', type: 'חופש', note: '' });
  const [ask, setAsk] = useState('');
  const send = async (force = false) => {
    try { await run('/absences', 'POST', { ...f, force }, `נוספה היעדרות מאושרת ל${f.employee}`); setAsk(''); onDone(); }
    catch (e) { if ((e as ApiError).status === 409) setAsk((e as ApiError).message); }
  };
  return (
    <Expander title="הוסף היעדרות לעובד/ת" icon={<Plus size={20} />}>
      <Load q={people}>{(list) => (
        <>
          <div className="cols3">
            <Field label="עובד/ת"><select className="input" value={f.employee} onChange={(e) => setF({ ...f, employee: e.target.value })}>
              <option value="">בחר/י</option>{list.filter((p) => ['מתמחה', 'רופא בכיר', 'מנהל מחלקה'].includes(p.type)).map((p) => <option key={p.name}>{p.name}</option>)}</select></Field>
            <Field label="מתאריך"><input className="input" type="date" value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} /></Field>
            <Field label="עד תאריך"><input className="input" type="date" value={f.end} onChange={(e) => setF({ ...f, end: e.target.value })} /></Field>
            <Field label="סוג"><select className="input" value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })}><option>חופש</option><option>202</option><option>היעדרות אחרת</option></select></Field>
            <Field label="הערה"><input className="input" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field>
          </div>
          {ask && <Note kind="warn"><div style={{ whiteSpace: 'pre-line' }}>{ask}</div></Note>}
          <Cta variant="teal" icon={<Check size={16} />} disabled={busy || !f.employee || !f.start || !f.end} onClick={() => send(!!ask)}>{ask ? 'כן, הוסף למרות החפיפה' : 'הוסף היעדרות מאושרת'}</Cta>
        </>
      )}</Load>
    </Expander>
  );
}

export default function LiveRequests() {
  const me = useMe();
  const manager = me.type === 'מנהל מחלקה';
  const scope = manager ? DAILY_DEPTS.filter((d) => me.manage_depts.includes(d)) : DAILY_DEPTS;
  const [filter, setFilter] = useState('הכל');
  const [tick, setTick] = useState(0);
  if (scope.length === 0) return <><PageHead title="ניהול בקשות" /><Note kind="warn">לא הוגדרו מחלקות בניהולך. פנה/י למנהל המערכת.</Note></>;
  return (
    <>
      <PageHead eyebrow={manager ? `המחלקות שלך: ${scope.join(', ')}` : 'היעדרויות מעבודה יומית'} title="ניהול בקשות" />
      {!manager && (
        <div className="row" style={{ marginBottom: 18 }}>
          <span className="muted small">סינון לפי מחלקה</span>
          <PillSeg value={filter} onChange={setFilter} options={['הכל', ...scope].map((d) => ({ v: d, l: d }))} />
        </div>
      )}
      <Bezel><h2 className="sec"><Tray size={22} />בקשות ממתינות</h2><PendingList key={filter + tick} filter={filter} onChange={() => setTick((t) => t + 1)} /></Bezel>
      <GanttLive key={'g' + filter + tick} filter={filter} scope={scope} manager={manager} />
      <AddAbsenceLive onDone={() => setTick((t) => t + 1)} />
    </>
  );
}
