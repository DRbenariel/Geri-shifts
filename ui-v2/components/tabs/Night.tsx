'use client';
import { useMemo, useState } from 'react';
import { ArrowsClockwise, Broom, Check, Coffee, FileArrowUp, Lightning, MagicWand, MagnifyingGlass, Prohibit, Question, Star, Trash, Warning, X } from '@phosphor-icons/react';
import { useStore } from '@/lib/store';
import { DAYS_IN_MONTH, DOW_FULL, EXTERNALS, FRI_SLOTS, HEB_MONTHS, INTERNS, MONTH, NIGHT_DEPTS, YEAR, dowOf, iso, type ShiftRow } from '@/lib/mock';
import { first, fmtDate, type DB } from '@/lib/logic';
import { Bezel, Cta, Expander, Field, Modal, Note, PageHead, Person, PillSeg } from '../ui';

const ALL_SLOTS = [...NIGHT_DEPTS, ...FRI_SLOTS];
const POOL = [...INTERNS, ...EXTERNALS];
const dayOf = (s: string) => +s.slice(8);
const isWeekend = (d: number) => [5, 6].includes(dowOf(YEAR, MONTH, d));

const blocked = (db: DB, emp: string, d: number) => db.requests.some((r) => r.employee === emp && r.date === iso(YEAR, MONTH, d) && r.status === 'אילוץ');
const wished = (db: DB, emp: string, d: number) => db.requests.some((r) => r.employee === emp && r.date === iso(YEAR, MONTH, d) && r.status === 'בקשה');
const worksNear = (db: DB, emp: string, d: number, ignore?: ShiftRow) =>
  db.schedule.some((r) => r !== ignore && r.employee === emp && !r.dept.startsWith('שישי') && Math.abs(dayOf(r.date) - d) <= 1);
const canTake = (db: DB, emp: string, d: number, slot: string, ignore?: ShiftRow) =>
  !blocked(db, emp, d) && !worksNear(db, emp, d, ignore) && !(EXTERNALS.includes(emp) && slot !== 'שיקום') && !(slot.startsWith('שישי') && EXTERNALS.includes(emp));

function DayCell({ d, db, onPick }: { d: number; db: DB; onPick: (d: number) => void }) {
  const date = iso(YEAR, MONTH, d);
  const rows = db.schedule.filter((r) => r.date === date);
  const sp = db.specialDays.find((s) => s.date === date);
  const nB = db.requests.filter((r) => r.date === date && r.status === 'אילוץ').length;
  const nR = db.requests.filter((r) => r.date === date && r.status === 'בקשה').length;
  const order = (r: ShiftRow) => ALL_SLOTS.indexOf(r.dept);
  return (
    <button className={`day ${isWeekend(d) ? 'we' : ''}`} onClick={() => onPick(d)} aria-label={`${d}/${MONTH}`}>
      <span className="num">{d}<span className="mark hide-m" title={`${nB} חסימות, ${nR} בקשות`}>{nB > 0 && <><Prohibit size={11} />{nB}</>} {nR > 0 && <><Star size={11} weight="fill" />{nR}</>}</span></span>
      {sp && <span className="sp" title={sp.day_type}>{sp.description}</span>}
      {[...rows].sort((a, b) => order(a) - order(b)).map((r) => (
        r.employee === '---'
          ? <span key={r.dept} className="slot empty" title={`${r.dept}: ${r.empty_reason ?? ''}`}><Question size={11} />{r.dept.startsWith('שישי') ? 'שישי' : r.dept === 'שיקום' ? 'ש' : 'פ'} חסר</span>
          : <span key={r.dept} className={`slot ${r.dept === 'שיקום' ? 'sh' : r.dept.startsWith('שישי') ? 'fr' : 'pn'}`} title={`${r.dept}: ${r.employee}${r.is_manual ? ' (ידני)' : ''}`}>{first(r.employee)}</span>
      ))}
    </button>
  );
}

function SwapHelper({ initDay }: { initDay: number }) {
  const { db, mutate, toast } = useStore();
  const [d, setD] = useState(initDay);
  const [slot, setSlot] = useState('פנימית גריאטרית');
  const [res, setRes] = useState<null | { avail: string[]; mutual: ShiftRow[]; cross: ShiftRow[]; rot: [ShiftRow, ShiftRow][] }>(null);
  const [pick, setPick] = useState('');
  const date = iso(YEAR, MONTH, d);
  const cur = db.schedule.find((r) => r.date === date && r.dept === slot);
  const slots = isWeekend(d) && dowOf(YEAR, MONTH, d) === 5 ? ALL_SLOTS : NIGHT_DEPTS;
  const find = () => {
    const avail = POOL.filter((p) => p !== cur?.employee && canTake(db, p, d, slot, cur));
    const mutual = db.schedule.filter((r) => r.date === date && r !== cur && r.employee !== '---' && !r.dept.startsWith('שישי') === !slot.startsWith('שישי'));
    const cross = db.schedule.filter((r) => r !== cur && r.employee !== '---' && r.date !== date && isWeekend(dayOf(r.date)) === isWeekend(d)
      && r.dept.startsWith('שישי') === slot.startsWith('שישי') && cur && cur.employee !== '---'
      && canTake(db, r.employee, d, slot, r) && canTake(db, cur.employee, dayOf(r.date), r.dept, cur)).slice(0, 5);
    const rot: [ShiftRow, ShiftRow][] = [];
    for (const a of cross) for (const b of db.schedule) {
      if (rot.length >= 5) break;
      if (b !== a && b !== cur && b.employee !== '---' && b.date !== a.date && b.date !== date && b.dept.startsWith('שישי') === a.dept.startsWith('שישי')) rot.push([a, b]);
    }
    setRes({ avail, mutual, cross, rot: rot.slice(0, 3) }); setPick(avail[0] ?? '');
  };
  const swap = (a: ShiftRow, b: ShiftRow) => mutate((x) => {
    const A = x.schedule.find((r) => r.date === a.date && r.dept === a.dept)!; const B = x.schedule.find((r) => r.date === b.date && r.dept === b.dept)!;
    [A.employee, B.employee] = [B.employee, A.employee]; A.is_manual = B.is_manual = true; A.empty_reason = B.empty_reason = undefined;
  });
  return (
    <>
      <div className="cols3">
        <Field label="תאריך"><select className="input" value={d} onChange={(e) => { setD(+e.target.value); setRes(null); }}>{Array.from({ length: DAYS_IN_MONTH }, (_, i) => <option key={i} value={i + 1}>{i + 1}/{MONTH} {DOW_FULL[dowOf(YEAR, MONTH, i + 1)]}</option>)}</select></Field>
        <Field label="משמרת"><select className="input" value={slot} onChange={(e) => { setSlot(e.target.value); setRes(null); }}>{slots.map((s) => <option key={s}>{s}</option>)}</select></Field>
        <Field label="מצב נוכחי"><div className="input" style={{ background: '#fff', boxShadow: 'inset 0 0 0 1px var(--line)' }}>{cur ? (cur.employee === '---' ? <span style={{ color: 'var(--Bt)' }}>לא משובץ · {cur.empty_reason}</span> : cur.employee) : 'אין משמרת כזו ביום זה'}</div></Field>
      </div>
      <Cta variant="teal" icon={<MagnifyingGlass size={16} />} onClick={find} disabled={!cur}>מצא החלפות אפשריות</Cta>
      {res && (
        <div className="cols2" style={{ marginTop: 20, gap: 20 }}>
          <div>
            <h3 className="sub">מחליפים זמינים ({res.avail.length})</h3>
            {res.avail.length === 0 ? <p className="muted small">אין מחליף ישיר שעומד בכל האילוצים.</p> : <>
              <select className="input" value={pick} onChange={(e) => setPick(e.target.value)} style={{ marginBottom: 10 }}>
                {res.avail.map((p) => <option key={p} value={p}>{p}{wished(db, p, d) ? ' ★ ביקש/ה' : ''}</option>)}
              </select>
              <Cta sm icon={<Check size={14} />} onClick={() => { mutate((x) => { const r = x.schedule.find((q) => q.date === date && q.dept === slot)!; r.employee = pick; r.is_manual = true; r.empty_reason = undefined; }); toast(`${pick} שובץ/ה ל${slot} ב-${d}/${MONTH}`); setRes(null); }}>בצע החלפה</Cta>
            </>}
          </div>
          <div>
            <h3 className="sub">החלפות הדדיות באותו יום</h3>
            {res.mutual.length === 0 ? <p className="muted small">אין.</p> : res.mutual.map((r) => (
              <div key={r.dept} className="rcard" style={{ marginBottom: 8 }}><div className="main"><b>{r.employee}</b><div className="meta">{r.dept}</div></div>
                <button className="btn" onClick={() => { cur && swap(cur, r); toast('בוצעה החלפה הדדית'); setRes(null); }}><ArrowsClockwise size={14} />החלף</button></div>
            ))}
          </div>
          <div>
            <h3 className="sub">החלפות הדדיות בין תאריכים</h3>
            {res.cross.length === 0 ? <p className="muted small">אין.</p> : res.cross.map((r) => (
              <div key={r.date + r.dept} className="rcard" style={{ marginBottom: 8 }}><div className="main"><b>{r.employee}</b><div className="meta">{fmtDate(r.date)} · {r.dept}</div></div>
                <button className="btn" onClick={() => { cur && swap(cur, r); toast('בוצעה החלפה בין תאריכים'); setRes(null); }}><ArrowsClockwise size={14} />החלף</button></div>
            ))}
          </div>
          <div>
            <h3 className="sub">מעגל החלפות</h3>
            {res.rot.length === 0 ? <p className="muted small">אין.</p> : res.rot.map(([a, b], i) => (
              <div key={i} className="rcard" style={{ marginBottom: 8 }}><div className="main"><b>{first(cur?.employee ?? '')} → {first(a.employee)} → {first(b.employee)}</b><div className="meta">{fmtDate(a.date)}, {fmtDate(b.date)}</div></div>
                <button className="btn" onClick={() => { toast('בוצע מעגל החלפות (דמו)'); setRes(null); }}>בצע מעגל</button></div>
            ))}
          </div>
        </div>
      )}
      <p className="muted small" style={{ marginTop: 14 }}>כללים: בוקר רק עם בוקר, סופ&quot;ש רק עם סופ&quot;ש, אין משמרות בימים צמודים, תורן חוץ לא בפנימית.</p>
    </>
  );
}

function SwapRequests() {
  const { db, mutate, toast } = useStore();
  const pending = db.swapRequests.filter((s) => s.status === 'pending');
  const label = { full: 'החלפה מלאה', partial: 'כיסוי חד-צדדי', chain: 'החלפה משולשת' };
  const act = (id: string, ok: boolean) => {
    mutate((x) => {
      const s = x.swapRequests.find((q) => q.id === id)!; s.status = ok ? 'approved' : 'rejected';
      if (!ok) return;
      const a = x.schedule.find((r) => r.date === s.requester_date && r.employee === s.requester);
      if (s.swap_type === 'full') { const b = x.schedule.find((r) => r.date === s.candidate_date && r.employee === s.candidate); if (a && b) { a.employee = s.candidate; b.employee = s.requester; a.is_manual = b.is_manual = true; } }
      else if (a) { a.employee = s.candidate; a.is_manual = true; }
    });
    toast(ok ? 'הבקשה אושרה והסידור עודכן' : 'הבקשה נדחתה', ok ? 'ok' : 'info');
  };
  return (
    <Bezel>
      <h2 className="sec"><ArrowsClockwise size={22} />בקשות החלפה ממתינות <span className="badge b-warn">{pending.length}</span></h2>
      {pending.length === 0 ? <p className="muted">אין בקשות ממתינות.</p> : (
        <div className="cardlist">
          {pending.map((s) => (
            <div key={s.id} className="rcard">
              <Person name={s.requester} role="מבקש/ת" />
              <div className="main">
                <b><span className="badge b-info" style={{ marginInlineEnd: 8 }}>{label[s.swap_type]}</span>{fmtDate(s.requester_date)} {s.requester_dept} ← {s.candidate}</b>
                <div className="meta">
                  {s.swap_type === 'full' && <span>בתמורה: {s.candidate_date && fmtDate(s.candidate_date)} {s.candidate_dept}</span>}
                  {s.swap_type === 'chain' && <span>{first(s.candidate)} עובר/ת לפנימית, {s.chain_ext} מכסה שיקום</span>}
                  {s.swap_type === 'partial' && <span>כיסוי ללא משמרת חוזרת</span>}
                  <span>נשלח {s.created_at}</span>
                </div>
              </div>
              <button className="btn ok" onClick={() => act(s.id, true)}><Check size={14} />אשר</button>
              <button className="btn no" onClick={() => act(s.id, false)}><X size={14} />דחה</button>
            </div>
          ))}
        </div>
      )}
    </Bezel>
  );
}

export default function Night() {
  const { db, mutate, toast } = useStore();
  const [view, setView] = useState<'grid' | 'list'>('grid');
  const [busy, setBusy] = useState('');
  const [summary, setSummary] = useState('');
  const [confirm, setConfirm] = useState<'' | 'auto' | 'all'>('');
  const [helperDay, setHelperDay] = useState(14);
  const [helperKey, setHelperKey] = useState(0);
  const [mo, setMo] = useState({ d: 20, slot: 'שיקום', emp: INTERNS[0] });

  const empty = db.schedule.filter((r) => r.employee === '---');
  const filled = db.schedule.filter((r) => r.employee !== '---');
  const nightTotal = DAYS_IN_MONTH * 2, friTotal = 16;
  const notSubmitted = POOL.filter((p) => !db.requests.some((r) => r.employee === p));
  const weeks = useMemo(() => {
    const out: (number | null)[][] = []; let wk: (number | null)[] = Array(dowOf(YEAR, MONTH, 1)).fill(null);
    for (let d = 1; d <= DAYS_IN_MONTH; d++) { wk.push(d); if (wk.length === 7) { out.push(wk); wk = []; } }
    if (wk.length) out.push([...wk, ...Array(7 - wk.length).fill(null)]); return out;
  }, []);

  const run = (weekendsOnly: boolean) => {
    setBusy(weekendsOnly ? 'we' : 'all'); setSummary('');
    setTimeout(() => {
      setBusy('');
      const n = filled.filter((r) => !r.dept.startsWith('שישי')).length, f = filled.filter((r) => r.dept.startsWith('שישי')).length;
      setSummary(`שיבוץ הושלם (CP-SAT, ${weekendsOnly ? 'סופ"שים בלבד' : 'חודש מלא'}): ${n}/${nightTotal} משמרות לילה, ${f}/${friTotal} שישי בוקר שובצו`);
      toast('השיבוץ האוטומטי הסתיים');
    }, 1600);
  };
  const fixes = (r: ShiftRow) => {
    const d = dayOf(r.date);
    const direct = POOL.filter((p) => canTake(db, p, d, r.dept)).slice(0, 2).map((p) => ({ t: 'שיבוץ ישיר', l: `שבץ את ${p}${wished(db, p, d) ? ' (ביקש/ה את היום)' : ''}`, emp: p }));
    const moveFrom = db.schedule.find((q) => q.date === r.date && q.dept !== r.dept && q.employee !== '---' && INTERNS.includes(q.employee));
    const move = moveFrom ? [{ t: 'העברת משמרת', l: `העבר את ${moveFrom.employee} מ${moveFrom.dept} ותורן חוץ יכסה`, emp: moveFrom.employee }] : [];
    return [...direct, ...move];
  };
  const applyFix = (r: ShiftRow, emp: string) => {
    if (EXTERNALS.includes(emp) && r.dept !== 'שיקום') return toast('תורן חוץ לא יכול להשתבץ בפנימית', 'err');
    mutate((x) => { const q = x.schedule.find((s) => s.date === r.date && s.dept === r.dept)!; q.employee = emp; q.is_manual = true; q.empty_reason = undefined; });
    toast(`${emp} שובץ/ה ל${r.dept} ב-${fmtDate(r.date)}`);
  };

  return (
    <>
      <PageHead eyebrow={`${HEB_MONTHS[MONTH - 1]} ${YEAR}`} title="סידור תורנויות"
        sub={`${filled.length} משמרות משובצות · ${empty.length} חסרות`}
        actions={<Cta variant="light" icon={<FileArrowUp size={16} />} onClick={() => toast('הגיליון Schedule_Export עודכן (תאריך, יום, פנימית, שיקום, 4 משמרות שישי בוקר)')}>עדכן Schedule_Export</Cta>} />

      <div className="split">
        <div>
          {empty.length > 0 && (
            <Bezel>
              <Note kind="err"><b>{empty.length} משמרות לא שובצו.</b> לחיצה על תיקון מציע משבץ מיד.</Note>
              <div className="cardlist">
                {empty.map((r) => (
                  <div key={r.date + r.dept} className="rcard">
                    <div className="main"><b>{fmtDate(r.date)} · {r.dept}</b><div className="meta"><Question size={13} />{r.empty_reason}</div></div>
                    <div className="row">
                      {fixes(r).map((f) => <button key={f.l} className="btn" onClick={() => applyFix(r, f.emp)}><Lightning size={14} weight="fill" />{f.t}: {f.l}</button>)}
                    </div>
                  </div>
                ))}
              </div>
            </Bezel>
          )}
          <Bezel>
            <div className="row" style={{ marginBottom: 16 }}>
              <h2 className="sec" style={{ margin: 0 }}>לוח החודש</h2>
              <span className="grow" />
              <PillSeg value={view} onChange={setView} options={[{ v: 'grid', l: 'לוח' }, { v: 'list', l: 'רשימה' }]} />
            </div>
            <div className="row small muted" style={{ marginBottom: 12 }}>
              <span className="slot sh">שיקום</span><span className="slot pn">פנימית</span><span className="slot fr">שישי בוקר</span><span className="slot empty">חסר</span>
              <span className="mark"><Prohibit size={12} />חסימות</span><span className="mark"><Star size={12} weight="fill" />בקשות</span>
            </div>
            {notSubmitted.length > 0 && <Note kind="info">לוח הזמינות היומי יוצג כשכולם יגישו אילוצים. חסרים: {notSubmitted.join(', ')}.</Note>}
            {view === 'grid' ? (
              <div className="cal">
                {DOW_FULL.map((h, i) => <div key={h} className={`h ${i >= 5 ? 'we' : ''}`}>{h}</div>)}
                {weeks.flat().map((d, i) => d ? <DayCell key={i} d={d} db={db} onPick={(x) => { setHelperDay(x); setHelperKey((k) => k + 1); document.getElementById('helper')?.scrollIntoView({ behavior: 'smooth' }); }} /> : <div key={i} className="day blank" />)}
              </div>
            ) : (
              <div className="cardlist">
                {Array.from({ length: DAYS_IN_MONTH }, (_, i) => i + 1).map((d) => {
                  const rows = db.schedule.filter((r) => r.date === iso(YEAR, MONTH, d));
                  const e = rows.filter((r) => r.employee === '---').length;
                  return (
                    <div key={d} className="rcard">
                      <div className="main"><b>{d}/{MONTH} {DOW_FULL[dowOf(YEAR, MONTH, d)]}</b> {e > 0 ? <span className="badge b-err"><Warning size={12} />{e} חסר</span> : <span className="badge b-ok">{rows.length} שובצו</span>}
                        <div className="meta">{rows.map((r) => <span key={r.dept}>{r.dept}: <b>{r.employee === '---' ? 'חסר' : r.employee}</b></span>)}</div></div>
                    </div>
                  );
                })}
              </div>
            )}
          </Bezel>
          <Bezel id="helper">
            <h2 className="sec"><MagicWand size={22} />עוזר החלפות חכם</h2>
            <SwapHelper key={helperKey} initDay={helperDay} />
          </Bezel>
          <SwapRequests />
        </div>

        <div>
          <Bezel>
            <h2 className="sec">שיבוץ אוטומטי</h2>
            <div className="cardlist">
              <Cta variant="teal" icon={<MagicWand size={16} />} onClick={() => run(false)} disabled={!!busy}>{busy === 'all' ? 'משבץ...' : 'שיבוץ אוטומטי מלא'}</Cta>
              <Cta variant="light" icon={<Coffee size={16} />} onClick={() => run(true)} disabled={!!busy}>{busy === 'we' ? 'משבץ...' : 'שיבוץ סופ"שים בלבד'}</Cta>
            </div>
            {summary && <div style={{ marginTop: 14 }}><Note kind="ok">{summary}</Note></div>}
          </Bezel>
          <Bezel>
            <h2 className="sec">הגדרות חודש</h2>
            <Field label="חודש לצפייה ועריכה"><select className="input" defaultValue={MONTH}>{HEB_MONTHS.map((m, i) => <option key={m} value={i + 1}>{m} {YEAR}</option>)}</select></Field>
            <Field label="חודש פתוח להגשת אילוצים">
              <select className="input" value={db.settings.active_month} onChange={(e) => { const v = +e.target.value; mutate((x) => { x.settings.active_month = v; }); toast(`ההגשה פתוחה עכשיו ל${HEB_MONTHS[v - 1]}`); }}>
                {HEB_MONTHS.map((m, i) => <option key={m} value={i + 1}>{m} {YEAR}</option>)}
              </select>
            </Field>
          </Bezel>
          <Expander title="שיבוץ ידני (דריסה)" icon={<Lightning size={20} />}>
            <Field label="תאריך"><select className="input" value={mo.d} onChange={(e) => setMo({ ...mo, d: +e.target.value })}>{Array.from({ length: DAYS_IN_MONTH }, (_, i) => <option key={i} value={i + 1}>{i + 1}/{MONTH}</option>)}</select></Field>
            <Field label="משמרת"><select className="input" value={mo.slot} onChange={(e) => setMo({ ...mo, slot: e.target.value })}>{ALL_SLOTS.map((s) => <option key={s}>{s}</option>)}</select></Field>
            <Field label="עובד/ת"><select className="input" value={mo.emp} onChange={(e) => setMo({ ...mo, emp: e.target.value })}>{POOL.map((p) => <option key={p}>{p}</option>)}</select></Field>
            <div className="row">
              <Cta sm icon={<Check size={14} />} onClick={() => {
                if (blocked(db, mo.emp, mo.d)) return toast(`${mo.emp} חסמ/ה את ${mo.d}/${MONTH}. השיבוץ נחסם.`, 'err');
                mutate((x) => { const date = iso(YEAR, MONTH, mo.d); const i = x.schedule.findIndex((r) => r.date === date && r.dept === mo.slot); const row = { date, dept: mo.slot, employee: mo.emp, is_manual: true }; if (i >= 0) x.schedule[i] = row; else x.schedule.push(row); });
                toast(`${mo.emp} שובץ/ה ידנית ל${mo.slot} ב-${mo.d}/${MONTH}`);
              }}>שיבוץ</Cta>
              <button className="btn" onClick={() => { mutate((x) => { x.schedule = x.schedule.filter((r) => !(r.date === iso(YEAR, MONTH, mo.d) && r.dept === mo.slot)); }); toast('המשמרת בוטלה', 'info'); }}><X size={14} />בטל</button>
            </div>
          </Expander>
          <Expander title="ניקוי" icon={<Broom size={20} />}>
            <div className="cardlist">
              <button className="btn" onClick={() => setConfirm('auto')}><Broom size={14} />נקה אוטומטי (חודש זה)</button>
              <button className="btn no" onClick={() => setConfirm('all')}><Trash size={14} />נקה הכל (חודש זה)</button>
            </div>
          </Expander>
        </div>
      </div>

      <Modal open={!!confirm} onClose={() => setConfirm('')}>
        <h2 className="sec">{confirm === 'all' ? 'למחוק את כל המשמרות של החודש?' : 'למחוק את המשמרות שנקבעו אוטומטית?'}</h2>
        <p className="muted" style={{ marginBottom: 16 }}>{confirm === 'all' ? 'כולל שיבוצים ידניים. אי אפשר לבטל.' : 'שיבוצים ידניים יישארו.'}</p>
        <div className="row">
          <Cta variant="danger" icon={<Trash size={16} />} onClick={() => { mutate((x) => { x.schedule = x.schedule.filter((r) => confirm === 'auto' && r.is_manual); }); toast('החודש נוקה', 'warn'); setConfirm(''); }}>מחק</Cta>
          <button className="btn" onClick={() => setConfirm('')}>ביטול</button>
        </div>
      </Modal>
    </>
  );
}
