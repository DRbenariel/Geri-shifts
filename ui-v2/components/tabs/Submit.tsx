'use client';
import { useMemo, useState } from 'react';
import { CalendarPlus, ClockCounterClockwise, FloppyDisk, LockSimple, Moon, PushPin, Sun, Warning } from '@phosphor-icons/react';
import { useMe, useStore } from '@/lib/store';
import { DOW_FULL, HEB_MONTHS, YEAR, daysIn, dowOf, iso, type Absence } from '@/lib/mock';
import { STATUS, absenceConflicts, constraintCounters, deptOf, deriveStatus, fmtDate, fmtRange } from '@/lib/logic';
import { Bezel, Cta, Expander, Field, MarkMode, Note, PageHead, SaveBar } from '../ui';
import { ConstraintCalendar } from './Staff';

type Cons = Record<number, 'B' | 'R'>;
const diff = (a: number[], b: number[]) => a.filter((x) => !b.includes(x));
const days = (c: Cons, v: 'B' | 'R') => Object.entries(c).filter(([, x]) => x === v).map(([d]) => +d).sort((x, y) => x - y);
const list = (ds: number[], m: number) => ds.map((d) => `${d}/${m}`).join(', ');

/** 🌙 Night-shift constraints (SCREENS_PLAN 4.5 / 4.6). Interns must keep 2 Thursdays and 4 weekend days free; externals only the ≤2 wishes rule. */
function NightConstraints() {
  const { db, mutate, toast } = useStore();
  const me = useMe();
  const m = db.settings.active_month;
  const intern = me.type === 'מתמחה';
  const saved = useMemo<Cons>(() => Object.fromEntries(db.requests.filter((r) => r.employee === me.name && +r.date.slice(5, 7) === m)
    .map((r) => [+r.date.slice(8), r.status === 'אילוץ' ? 'B' : 'R'])), [db.requests, me.name, m]);
  const [cons, setCons] = useState<Cons>(saved);
  const special = Object.fromEntries(db.specialDays.filter((s) => +s.date.slice(5, 7) === m).map((s) => [+s.date.slice(8), s.description]));
  const toggle = (d: number, v: 'B' | 'R' | null) => setCons((c) => { const n = { ...c }; if (v) n[d] = v; else delete n[d]; return n; });

  const c = constraintCounters(cons, YEAR, m);
  const errors = [
    !c.okWish && 'ניתן לבחור עד 2 בקשות בלבד.',
    intern && !c.okThu && `יש להשאיר לפחות 2 ימי חמישי פנויים (כרגע ${c.thu}).`,
    intern && !c.okWknd && `יש להשאיר לפחות 4 ימי סופ״ש פנויים (כרגע ${c.wknd}).`,
  ].filter(Boolean) as string[];
  const [sB, sR, nB, nR] = [days(saved, 'B'), days(saved, 'R'), days(cons, 'B'), days(cons, 'R')];
  const changes = [
    diff(nB, sB).length > 0 && `➕ נוספו לחסימה: ${list(diff(nB, sB), m)}`,
    diff(sB, nB).length > 0 && `➖ הוסרו מחסימה: ${list(diff(sB, nB), m)}`,
    diff(nR, sR).length > 0 && `➕ נוספו לבקשה: ${list(diff(nR, sR), m)}`,
    diff(sR, nR).length > 0 && `➖ הוסרו מבקשה: ${list(diff(sR, nR), m)}`,
  ].filter(Boolean) as string[];
  const nChanged = diff(nB, sB).length + diff(sB, nB).length + diff(nR, sR).length + diff(sR, nR).length;
  const save = () => {
    if (errors.length) return toast('השמירה נחסמה: יש לתקן את השגיאות', 'err');
    mutate((x) => {
      x.requests = x.requests.filter((r) => !(r.employee === me.name && +r.date.slice(5, 7) === m))
        .concat(Object.entries(cons).map(([d, v]) => ({ employee: me.name, date: iso(YEAR, m, +d), status: v === 'B' ? 'אילוץ' as const : 'בקשה' as const })));
    });
    toast(`האילוצים לחודש ${HEB_MONTHS[m - 1]} נשמרו`);
  };
  return (
    <Bezel>
      <h2 className="sec"><Moon size={22} />אילוצים לתורנויות · {HEB_MONTHS[m - 1]} {YEAR}</h2>
      {Object.keys(special).length > 0 && (
        <Note kind="info"><PushPin size={14} weight="fill" /> ימים מיוחדים החודש: {Object.entries(special).map(([d, t]) => `${d}/${m} ${t}`).join(' · ')}</Note>
      )}
      <p className="muted small" style={{ marginBottom: 14 }}>
        מה שמור עכשיו: {sB.length ? <>חסימות: {list(sB, m)}</> : 'אין חסימות'}{sR.length > 0 && <> · בקשות: {list(sR, m)}</>}
      </p>
      <ConstraintCalendar cons={cons} onToggle={toggle} special={special} rules={intern} />
      {changes.length > 0 && <div className="changes">{changes.map((t) => <div key={t}>{t}</div>)}</div>}
      {sB.length > 0 && nB.length === 0 && <Note kind="warn">הסרת את כל החסימות. ודא/י שזה מכוון.</Note>}
      {errors.length > 0 && <Note kind="err">{errors.map((e) => <div key={e}>{e}</div>)}</Note>}
      <SaveBar changes={nChanged} label="שמור אילוצים ובקשות" onSave={save} />
    </Bezel>
  );
}

type Pick = '' | 'V' | 'S';
/** ☀️ Absence from daily work (SCREENS_PLAN 4.5 / 4.7), for the daily active month, which is separate from the night month. */
function DailyAbsence() {
  const { db, mutate, toast } = useStore();
  const me = useMe();
  const senior = me.type === 'רופא בכיר';
  const m = db.settings.daily_active_month, y = YEAR, n = daysIn(y, m);
  const open = db.settings.daily_requests_open;
  const ym = `${y}-${String(m).padStart(2, '0')}`;
  const dept = deptOf(db, me.name, ym)?.daily_dept ?? '';
  const inMonth = (a: Absence) => a.start_date.slice(0, 7) === ym && a.employee === me.name;
  const savedPicks = useMemo(() => {
    const out: Record<number, Pick> = {};
    db.absences.filter((a) => inMonth(a) && a.status === 'pending' && (a.type === 'חופש' || a.type === '202')).forEach((a) => {
      for (let d = +a.start_date.slice(8); d <= +a.end_date.slice(8); d++) out[d] = a.type === '202' ? 'S' : 'V';
    });
    return out;
  }, [db.absences]); // eslint-disable-line react-hooks/exhaustive-deps
  const [picks, setPicks] = useState<Record<number, Pick>>(savedPicks);
  const nDirty = new Set([...Object.keys(picks), ...Object.keys(savedPicks)].filter((d) => picks[+d] !== savedPicks[+d])).size;

  // Fixed days: night shift, post-night, approved absence. Fri/Sat aren't requestable.
  const fixed = (d: number) => {
    const w = dowOf(y, m, d);
    if (w >= 5) return { lab: '', cls: 'blank-we' };
    const st = deriveStatus(db, y, m, d, me.name);
    const appr = db.absences.find((a) => a.employee === me.name && a.status === 'approved' && a.start_date <= iso(y, m, d) && a.end_date >= iso(y, m, d));
    if (st.code === 'T' || st.code === 'A') return { lab: STATUS[st.code].he, cls: st.code };
    if (appr) return { lab: `${appr.type === '202' ? '202' : 'חופש'} מאושר`, cls: appr.type === '202' ? 'S' : 'V' };
    return null;
  };
  const [mode, setMode] = useState<'V' | 'S'>('V');
  const click = (d: number) => setPicks((p) => { const q = { ...p }; if (q[d] === mode) delete q[d]; else q[d] = mode; return q; });

  // Contiguous runs of the same type become one request each.
  const runs = () => {
    const out: { s: number; e: number; t: Pick }[] = [];
    Object.keys(picks).map(Number).sort((a, b) => a - b).forEach((d) => {
      const last = out[out.length - 1];
      if (last && last.t === picks[d] && d === last.e + 1) last.e = d; else out.push({ s: d, e: d, t: picks[d] });
    });
    return out;
  };
  const overlaps = runs().flatMap((r) => absenceConflicts(db, { employee: me.name, start_date: iso(y, m, r.s), end_date: iso(y, m, r.e), dept_at_request: dept }));
  const save = () => {
    mutate((x) => {
      x.absences = x.absences.filter((a) => !(inMonth(a) && a.status === 'pending' && (a.type === 'חופש' || a.type === '202')));
      runs().forEach((r, i) => x.absences.push({ id: `p${Date.now()}${i}`, employee: me.name, start_date: iso(y, m, r.s), end_date: iso(y, m, r.e), type: r.t === 'S' ? '202' : 'חופש', status: 'pending', dept_at_request: dept, approved_by: '', notes: '', created_at: '2026-10-18' }));
    });
    toast('הבקשות נשמרו ונשלח מייל למנהל/ת המחלקה');
  };
  const lead = dowOf(y, m, 1);
  const mineAll = db.absences.filter((a) => a.employee === me.name).sort((a, b) => b.start_date.localeCompare(a.start_date));

  return (
    <>
      <Bezel>
        <h2 className="sec"><Sun size={22} />היעדרות מעבודה יומית · {HEB_MONTHS[m - 1]} {y}</h2>
        {!open && <Note kind="warn"><LockSimple size={14} /> הגשות לחודש {HEB_MONTHS[m - 1]} נסגרו על ידי המנהל. הלוח לצפייה בלבד.</Note>}
        {!dept && <Note kind="info">טרם שובצת למחלקה בחודש זה. הבקשה תגיע למנהל/ת אחרי השיבוץ.</Note>}
        <div className="legend">
          <div className="lg"><span className="V">ח</span>בקשה לחופש</div>
          {!senior && <div className="lg"><span className="S">202</span>בקשה ל-202</div>}
          <div className="lg"><span className="T">ת</span>תורנות (קבוע)</div>
          <div className="lg"><span className="A">א</span>אחרי תורנות (קבוע)</div>
        </div>
        {!senior && <MarkMode value={mode} onChange={setMode} options={[{ v: 'V' as const, label: 'חופש', hint: 'יום חופש', cls: 'V' }, ...(senior ? [] : [{ v: 'S' as const, label: '202', hint: 'יום 202', cls: 'S' }])]} />}
        <div className="cal abs-cal">
          {DOW_FULL.map((h, i) => <div key={h} className={`h ${i >= 5 ? 'we' : ''}`}>{h}</div>)}
          {Array.from({ length: lead }, (_, i) => <div key={'b' + i} className="day blank" />)}
          {Array.from({ length: n }, (_, i) => i + 1).map((d) => {
            const f = fixed(d);
            if (f) return <div key={d} className={`day fixed ${f.cls}`} title={f.lab}><span className="num">{d}</span><span className="st">{f.lab}</span></div>;
            const p = picks[d] ?? '';
            return (
              <button key={d} className={`day pick ${p}`} disabled={!open} onClick={() => click(d)} aria-label={`${d}/${m} ${p === 'V' ? 'חופש' : p === 'S' ? '202' : 'עבודה'}`}>
                <span className="num">{d}</span><span className="st">{p === 'V' ? 'חופש' : p === 'S' ? '202' : ''}</span>
              </button>
            );
          })}
        </div>
        <p className="muted small" style={{ margin: '10px 0' }}>לחיצה על יום מסמנת {mode === 'V' ? 'חופש' : '202'}, ולחיצה נוספת מבטלת. ימים קבועים לא ניתנים לשינוי.</p>
        {overlaps.length > 0 && <Note kind="warn"><Warning size={14} /> כבר מאושרים בחופש מ{dept}: {[...new Set(overlaps.map((o) => `${o.employee} (${fmtRange(o.start_date, o.end_date)})`))].join(', ')}. אפשר לשמור, וההחלטה אצל המנהל/ת.</Note>}
        <SaveBar changes={nDirty} label="שמור בקשות היעדרות" onSave={save} disabled={!open} />
      </Bezel>
      <FutureVacation />
      <Bezel>
        <h2 className="sec"><ClockCounterClockwise size={22} />היסטוריית בקשות</h2>
        {mineAll.length === 0 ? <p className="muted small">עדיין לא הגשת בקשות.</p> : (
          <div className="tbl-wrap"><table className="t"><thead><tr><th>תאריכים</th><th>סוג</th><th>סטטוס</th><th>אושר ע״י</th><th>הערה</th></tr></thead>
            <tbody>{mineAll.map((a) => <tr key={a.id}><td>{fmtRange(a.start_date, a.end_date)}</td><td>{a.type}</td>
              <td><span className={`badge ${a.status === 'approved' ? 'b-ok' : a.status === 'pending' ? 'b-warn' : 'b-err'}`}>{a.status === 'approved' ? 'אושר' : a.status === 'pending' ? 'ממתין' : 'נדחה'}</span></td>
              <td>{a.approved_by}</td><td className="muted">{a.notes}</td></tr>)}</tbody></table></div>
        )}
      </Bezel>
    </>
  );
}

function FutureVacation() {
  const { db, mutate, toast } = useStore();
  const me = useMe();
  const [f, setF] = useState({ start: '2027-01-10', end: '2027-01-14', notes: '' });
  const ym = f.start.slice(0, 7);
  const dept = deptOf(db, me.name, ym)?.daily_dept ?? '';
  return (
    <Expander title="חופש עתידי (תאריך רחוק)" icon={<CalendarPlus size={20} />}>
      <p className="muted small" style={{ marginBottom: 12 }}>לחופש בחודש שעוד לא נפתח להגשות. לא תלוי בפתיחה או סגירה של ההגשות.</p>
      <div className="cols3">
        <Field label="מתאריך"><input className="input" type="date" value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} /></Field>
        <Field label="עד תאריך"><input className="input" type="date" value={f.end} onChange={(e) => setF({ ...f, end: e.target.value })} /></Field>
        <Field label="הערה"><input className="input" value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} placeholder="למשל: טיסה לחו״ל" /></Field>
      </div>
      {!dept && <Note kind="warn">לא נמצא שיבוץ מחלקה ל{HEB_MONTHS[+ym.slice(5) - 1]} {ym.slice(0, 4)}. הבקשה תישמר ותגיע למנהל/ת אחרי השיבוץ.</Note>}
      <Cta variant="teal" icon={<CalendarPlus size={16} />} disabled={!f.start || !f.end || f.end < f.start} onClick={() => {
        mutate((x) => { x.absences.push({ id: 'f' + Date.now(), employee: me.name, start_date: f.start, end_date: f.end, type: 'חופש עתידי', status: 'pending', dept_at_request: dept, approved_by: '', notes: f.notes, created_at: '2026-10-18' }); });
        toast(`בקשת חופש עתידי נשלחה: ${fmtDate(f.start)} - ${fmtDate(f.end)}`);
      }}>שלח בקשה</Cta>
    </Expander>
  );
}

export default function Submit() {
  const { db } = useStore();
  const me = useMe();
  const night = me.type === 'מתמחה' || me.type === 'תורן חוץ';
  const daily = me.type === 'מתמחה' || me.type === 'רופא בכיר';
  return (
    <>
      <PageHead title="הגשת בקשות"
        sub={night ? `לחודש: ${HEB_MONTHS[db.settings.active_month - 1]} ${YEAR}` : `היעדרות מעבודה יומית: ${HEB_MONTHS[db.settings.daily_active_month - 1]} ${YEAR}`} />
      {night && <NightConstraints />}
      {daily && <DailyAbsence />}
    </>
  );
}
