'use client';
import { useEffect, useMemo, useState } from 'react';
import { CalendarPlus, ClockCounterClockwise, FloppyDisk, LockSimple, Moon, Sun } from '@phosphor-icons/react';
import { useApi } from '@/lib/api';
import { DOW_FULL, HEB_MONTHS, dowOf } from '@/lib/mock';
import { constraintCounters } from '@/lib/logic';
import { monthDays, useMe, ymOf } from '@/lib/store';
import { Bezel, Cta, Expander, Field, Note, PageHead } from '../ui';
import { ConstraintCalendar } from '../tabs/Staff';
import { Load, range, useAction } from './common';

type Cons = Record<number, 'B' | 'R'>;
const listDays = (c: Cons, v: 'B' | 'R') => Object.entries(c).filter(([, x]) => x === v).map(([d]) => +d).sort((a, b) => a - b);

function NightLive() {
  const me = useMe();
  const { active_year: y, active_month: m } = me.settings;
  const ym = ymOf(y, m);
  const q = useApi<{ blocked: number[]; wishes: number[] }>(`/constraints/${ym}`);
  const sd = useApi<{ date: string; description: string }[]>('/special-days');
  const { run, busy } = useAction();
  const saved = useMemo<Cons>(() => q.data ? { ...Object.fromEntries(q.data.blocked.map((d) => [d, 'B'])), ...Object.fromEntries(q.data.wishes.map((d) => [d, 'R'])) } : {}, [q.data]);
  const [cons, setCons] = useState<Cons>({});
  useEffect(() => setCons(saved), [saved]);
  const intern = me.type === 'מתמחה';
  const c = constraintCounters(cons, y, m);
  const errors = [!c.okWish && 'ניתן לבחור עד 2 בקשות (⭐) בלבד.', intern && !c.okThu && `יש להשאיר לפחות 2 ימי חמישי פנויים (כרגע ${c.thu}).`,
    intern && !c.okWknd && `יש להשאיר לפחות 4 ימי סופ״ש פנויים (כרגע ${c.wknd}).`].filter(Boolean) as string[];
  const dirty = JSON.stringify(listDays(cons, 'B')) + JSON.stringify(listDays(cons, 'R')) !== JSON.stringify(listDays(saved, 'B')) + JSON.stringify(listDays(saved, 'R'));
  const special = Object.fromEntries((sd.data ?? []).filter((s) => s.date.startsWith(ym)).map((s) => [+s.date.slice(8), s.description]));
  const toggle = (d: number) => setCons((x) => { const n = { ...x }; const v = n[d]; if (!v) n[d] = 'B'; else if (v === 'B') n[d] = 'R'; else delete n[d]; return n; });
  return (
    <Bezel>
      <h2 className="sec"><Moon size={22} />אילוצים לתורנויות · {HEB_MONTHS[m - 1]} {y}</h2>
      <Load q={q}>{() => (
        <>
          <ConstraintCalendar cons={cons} onToggle={toggle} special={special} rules={intern} y={y} m={m} />
          {errors.length > 0 && <Note kind="err">{errors.map((e) => <div key={e}>{e}</div>)}</Note>}
          <div className="row" style={{ marginTop: 14 }}>
            <Cta icon={<FloppyDisk size={16} />} disabled={!dirty || busy || errors.length > 0}
              onClick={() => run(`/constraints/${ym}`, 'PUT', { blocked: listDays(cons, 'B'), wishes: listDays(cons, 'R') }, 'האילוצים נשמרו').then(q.reload).catch(() => {})}>שמור אילוצים ובקשות</Cta>
            {!dirty && <span className="muted small">אין שינויים לשמירה</span>}
          </div>
        </>
      )}</Load>
    </Bezel>
  );
}

interface MyCal { approved_vac: number[]; approved_202: number[]; approved_future: number[]; pending: number[]; pending_types: Record<string, number>; night_shift: number[]; post_shift: number[] }
type Pick = '' | 'V' | 'S';

function DailyLive() {
  const me = useMe();
  const { daily_active_year: y, daily_active_month: m, daily_requests_open: open } = me.settings;
  const ym = ymOf(y, m);
  const q = useApi<{ calendar: MyCal; history: { id: string; start_date: string; end_date: string; type: string; status: string; approved_by: string; notes: string }[] }>(`/absences/me/${ym}`);
  const { run, busy } = useAction();
  const senior = me.type === 'רופא בכיר';
  const saved = useMemo(() => {
    const out: Record<number, Pick> = {};
    if (q.data) for (const d of q.data.calendar.pending) out[d] = q.data.calendar.pending_types[String(d)] === 2 ? 'S' : 'V';
    return out;
  }, [q.data]);
  const [picks, setPicks] = useState<Record<number, Pick>>({});
  useEffect(() => setPicks(saved), [saved]);
  const cycle: Pick[] = senior ? ['', 'V'] : ['', 'V', 'S'];
  const [fut, setFut] = useState({ start: '', end: '', note: '' });
  return (
    <>
      <Bezel>
        <h2 className="sec"><Sun size={22} />היעדרות מעבודה יומית · {HEB_MONTHS[m - 1]} {y}</h2>
        {!open && <Note kind="warn"><LockSimple size={14} /> הגשות לחודש {HEB_MONTHS[m - 1]} נסגרו על ידי המנהל. הלוח לצפייה בלבד.</Note>}
        <Load q={q}>{({ calendar: c }) => {
          const fixed = (d: number): [string, string] | null => {
            if (dowOf(y, m, d) >= 5) return ['', 'blank-we'];
            if (c.night_shift.includes(d)) return ['תורנות', 'T'];
            if (c.post_shift.includes(d)) return ['אחרי תורנות', 'A'];
            if (c.approved_202.includes(d)) return ['202 מאושר', 'S'];
            if (c.approved_vac.includes(d) || c.approved_future.includes(d)) return ['חופש מאושר', 'V'];
            return null;
          };
          const dirty = JSON.stringify(picks) !== JSON.stringify(saved);
          const save = () => run(`/absences/me/${ym}`, 'POST', {
            vacation: Object.keys(picks).map(Number).filter((d) => picks[d] === 'V'),
            days_202: Object.keys(picks).map(Number).filter((d) => picks[d] === 'S'),
          }, 'הבקשות נשמרו ונשלחו למנהל/ת המחלקה').then(q.reload).catch(() => {});
          return (
            <>
              <div className="cal abs-cal">
                {DOW_FULL.map((h, i) => <div key={h} className={`h ${i >= 5 ? 'we' : ''}`}>{h}</div>)}
                {Array.from({ length: dowOf(y, m, 1) }, (_, i) => <div key={'b' + i} className="day blank" />)}
                {monthDays(y, m).map((d) => {
                  const f = fixed(d);
                  if (f) return <div key={d} className={`day fixed ${f[1]}`}><span className="num">{d}</span><span className="st">{f[0]}</span></div>;
                  const p = picks[d] ?? '';
                  return <button key={d} className={`day pick ${p}`} disabled={!open} onClick={() => setPicks((x) => { const n = { ...x }; const nx = cycle[(cycle.indexOf(p) + 1) % cycle.length]; if (nx) n[d] = nx; else delete n[d]; return n; })}>
                    <span className="num">{d}</span><span className="st">{p === 'V' ? 'חופש' : p === 'S' ? '202' : ''}</span></button>;
                })}
              </div>
              <p className="muted small" style={{ margin: '10px 0' }}>לחיצה על יום: {senior ? 'עבודה → חופש → עבודה' : 'עבודה → חופש → 202 → עבודה'}.</p>
              <Cta icon={<FloppyDisk size={16} />} disabled={!open || !dirty || busy} onClick={save}>שמור</Cta>
            </>
          );
        }}</Load>
      </Bezel>
      <Expander title="חופש עתידי (תאריך רחוק)" icon={<CalendarPlus size={20} />}>
        <div className="cols3">
          <Field label="מתאריך"><input className="input" type="date" value={fut.start} onChange={(e) => setFut({ ...fut, start: e.target.value })} /></Field>
          <Field label="עד תאריך"><input className="input" type="date" value={fut.end} onChange={(e) => setFut({ ...fut, end: e.target.value })} /></Field>
          <Field label="הערה"><input className="input" value={fut.note} onChange={(e) => setFut({ ...fut, note: e.target.value })} /></Field>
        </div>
        <Cta variant="teal" icon={<CalendarPlus size={16} />} disabled={busy || !fut.start || !fut.end || fut.end < fut.start}
          onClick={() => run('/absences/future', 'POST', fut, 'בקשת החופש העתידי נשלחה').then(q.reload).catch(() => {})}>שלח בקשה</Cta>
      </Expander>
      <Bezel>
        <h2 className="sec"><ClockCounterClockwise size={22} />היסטוריית בקשות</h2>
        <Load q={q}>{({ history }) => history.length === 0 ? <p className="muted small">עדיין לא הגשת בקשות.</p> : (
          <div className="tbl-wrap"><table className="t"><thead><tr><th>תאריכים</th><th>סוג</th><th>סטטוס</th><th>אושר ע״י</th><th>הערה</th></tr></thead>
            <tbody>{[...history].sort((a, b) => b.start_date.localeCompare(a.start_date)).map((a) => <tr key={a.id}><td>{range(a.start_date, a.end_date)}</td><td>{a.type}</td>
              <td><span className={`badge ${a.status === 'approved' ? 'b-ok' : a.status === 'pending' ? 'b-warn' : 'b-err'}`}>{a.status === 'approved' ? 'אושר' : a.status === 'pending' ? 'ממתין' : 'נדחה'}</span></td>
              <td>{a.approved_by}</td><td className="muted">{a.notes}</td></tr>)}</tbody></table></div>
        )}</Load>
      </Bezel>
    </>
  );
}

export default function LiveSubmit() {
  const me = useMe();
  const night = me.type === 'מתמחה' || me.type === 'תורן חוץ';
  const daily = me.type === 'מתמחה' || me.type === 'רופא בכיר';
  return (
    <>
      <PageHead eyebrow={me.name} title="הגשת בקשות" />
      {night && <NightLive />}
      {daily && <DailyLive />}
    </>
  );
}
