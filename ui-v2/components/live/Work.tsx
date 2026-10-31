'use client';
import { useState } from 'react';
import { ArrowCounterClockwise, ArrowsLeftRight, Bell, FileXls, GoogleLogo, Moon, NotePencil, Plus, Sun, X } from '@phosphor-icons/react';
import { useApi, type Grid, type GridRow } from '@/lib/api';
import { DAILY_DEPTS, DOW_FULL, HEB_MONTHS } from '@/lib/mock';
import { useMe, useStore, ymOf } from '@/lib/store';
import { Bezel, Cta, Field, Modal, Note, PageHead, Person, PillSeg, StatusLegend, StatusPicker } from '../ui';
import { Load, MonthPick, STATUS_CLASS, dmy, enc, useAction, useDownload } from './common';

const first = (n: string) => n.replace('ד"ר ', '').trim().split(' ')[0];
const names = (v: string | string[] | null) => (Array.isArray(v) ? v : v ? [v] : []).filter((x) => x && x !== '---');

function weeks(g: Grid) {
  const out: (number | null)[][] = []; let wk: (number | null)[] = Array(g.days[0].weekday).fill(null);
  for (const d of g.days) { wk.push(d.day); if (wk.length === 7) { out.push(wk); wk = []; } }
  if (wk.length) out.push([...wk, ...Array(7 - wk.length).fill(null)]);
  return out;
}

function GridView({ g, me, onCycle }: { g: Grid; me: string; onCycle: (r: GridRow, d: number, rect: DOMRect) => void }) {
  const pnim = !!g.side_groups;
  const groups = pnim ? [{ k: 'ורוד', l: 'צד ורוד', c: 'pink' }, { k: 'כחול', l: 'צד כחול', c: 'blue' }] : [{ k: '', l: '', c: '' }];
  const day = (d: number) => g.days[d - 1];
  // Night duty is shown only for people on this board: an intern rotated elsewhere who did this
  // dept's night shift isn't part of this dept's day schedule.
  const onBoard = new Set(g.rows.map((r) => r.employee.trim()));
  return (
    <>
      {g.unassigned_side.length > 0 && <Note kind="warn">בלי צד בפנימית (לא מוצגים בגריד): {g.unassigned_side.join(', ')}</Note>}
      {g.rows.length === 0 && <Note kind="info">אין עובדים משובצים למחלקה בחודש זה בגאנט.</Note>}
      {weeks(g).map((wk, wi) => (
        <Bezel key={wi}>
          <div className="row" style={{ marginBottom: 14 }}><b style={{ fontSize: 18 }}>שבוע {wi + 1}</b></div>
          <div className="dgrid">
            <div className="corner" />
            {wk.map((d, i) => <div key={i} className={`dh ${i === 6 ? 'sat' : ''} ${i === 5 ? 'fri' : ''}`}>{DOW_FULL[i]}<b>{d ?? ''}</b></div>)}
            {groups.map((gr) => {
              const rows = g.rows.filter((r) => !pnim || r.side === gr.k);
              return [
                pnim && <div key={'h' + gr.k} className={`side-h ${gr.c}`}>{gr.l} · {rows.length}</div>,
                ...rows.flatMap((r) => [
                  <Person key={r.employee + wi} name={r.employee} role={r.transfer_days ? `${r.type} · העברה זמנית` : r.type} me={r.employee === me} />,
                  ...wk.map((d, i) => {
                    if (!d) return <span key={r.employee + i} />;
                    const c = r.cells[d - 1];
                    if (c.locked) return <button key={r.employee + i} className="cell locked" disabled title="מחוץ לימי ההעברה">-</button>;
                    const cls = c.blank_weekend ? 'E' : STATUS_CLASS[c.status ?? ''] ?? 'O';
                    return (
                      <button key={r.employee + i} className={`cell ${cls}`} data-k={`${r.employee}|${d}`}
                        disabled={!g.editable || c.status === 'תורנות' || c.blank_weekend || i === 6}
                        onClick={(e) => onCycle(r, d, e.currentTarget.getBoundingClientRect())} title={`${r.employee} · ${d}/${g.month} · ${c.status || 'לא הוגדר'}${c.note ? ' · ' + c.note : ''}${c.manual ? ' (ידני)' : ''}`}>
                        {c.blank_weekend ? '' : c.label}{c.note && <span className="nt" />}
                      </button>
                    );
                  }),
                ]),
              ];
            })}
            <div className="gsep" />
            <div className="meta-l"><Moon size={18} weight="light" />תורנ/ית</div>
            {wk.map((d, i) => { const n = d ? names(day(d).night_duty).filter((x) => onBoard.has(x.trim())) : []; return n.length ? <span key={'n' + i} className="mchip">{n.map(first).join(', ')}</span> : <span key={'n' + i} />; })}
            <div className="meta-l"><Sun size={18} weight="light" />שישי בוקר</div>
            {wk.map((d, i) => { const n = d ? names(day(d).friday_workers) : []; return n.length ? <span key={'f' + i} className="mchip">{n.map(first).join(', ')}</span> : <span key={'f' + i} />; })}
            <div className="meta-l"><Bell size={18} weight="light" />כונן/ית</div>
            {wk.map((d, i) => { const k = d ? day(d).konenut : ''; return k ? <span key={'k' + i} className="mchip k">{first(k)}</span> : <span key={'k' + i} />; })}
          </div>
        </Bezel>
      ))}
    </>
  );
}

const HOTKEYS: Record<string, string> = { 'עובד': 'ע', 'חופש': 'ח', '202': '2', 'אחרי תורנות': 'א', 'אחר': '+', '': '-' };
const SHORT: Record<string, string> = { 'עובד': 'ע', 'חופש': 'ח', '202': '202', 'אחרי תורנות': 'א', 'אחר': '+', '': '·' };

function DeptGridLive({ dept, ym, me }: { dept: string; ym: string; me: string }) {
  const q = useApi<Grid>(`/work/${enc(dept)}/${ym}`);
  const { run } = useAction();
  const { toast } = useStore();
  const [pick, setPick] = useState<{ r: GridRow; d: number; rect: DOMRect } | null>(null);
  const [noteFor, setNoteFor] = useState<{ r: GridRow; d: number; status: string; note: string } | null>(null);
  const body = (r: GridRow, d: number) => ({ dept, date: `${ym}-${String(d).padStart(2, '0')}`, employee: r.employee });
  // Every change offers undo: put back the previous manual value, or drop the override so the day is computed again.
  const undoFor = (r: GridRow, d: number) => {
    const prev = r.cells[d - 1];
    return prev.manual && prev.status && r.allowed_statuses.includes(prev.status)
      ? () => run('/work/cell', 'PUT', { ...body(r, d), status: prev.status, note: prev.note }).then(q.reload).catch(() => {})
      : () => run('/work/cell', 'DELETE', body(r, d)).then(q.reload).catch(() => {});
  };
  const apply = (r: GridRow, d: number, status: string | null, note?: string) => {
    setPick(null);
    const prev = r.cells[d - 1];
    const req = status === null ? run('/work/cell', 'DELETE', body(r, d)) : run('/work/cell', 'PUT', { ...body(r, d), status, note: note ?? prev.note });
    req.then(() => {
      q.reload();
      toast(`${first(r.employee)} · ${d}/${q.data?.month ?? ''}: ${prev.status || 'לא הוגדר'} ← ${status === null ? 'חישוב אוטומטי' : status || 'לא הוגדר'}`, 'info', { label: 'בטל', fn: undoFor(r, d) });
    }).catch(() => {});
  };
  return (
    <>
      <Load q={q}>{(g) => <><GridView g={g} me={me} onCycle={(r, d, rect) => setPick({ r, d, rect })} />{g.transfer_candidates && <TransferForm g={g} candidates={g.transfer_candidates} onDone={q.reload} />}</>}</Load>
      {pick && (() => {
        const c = pick.r.cells[pick.d - 1];
        return (
          <StatusPicker anchor={pick.rect} title={`${pick.r.employee} · ${pick.d}/${q.data?.month ?? ''}`} current={c.status ?? ''}
            options={pick.r.allowed_statuses.map((st) => ({ key: st, label: st || 'ריק (לא עובד/ת)', short: SHORT[st] ?? st, cls: STATUS_CLASS[st] ?? 'O', hotkey: HOTKEYS[st] }))}
            onPick={(k) => apply(pick.r, pick.d, k)} onClose={() => setPick(null)}
            extra={<>
              {c.manual && <button className="btn" onClick={() => apply(pick.r, pick.d, null)}><ArrowCounterClockwise size={14} />חזרה לחישוב אוטומטי</button>}
              <button className="btn" onClick={() => { setNoteFor({ r: pick.r, d: pick.d, status: c.status && pick.r.allowed_statuses.includes(c.status) ? c.status : pick.r.allowed_statuses[0], note: c.note }); setPick(null); }}><NotePencil size={14} />הערה</button>
            </>} />
        );
      })()}
      <Modal open={!!noteFor} onClose={() => setNoteFor(null)}>
        {noteFor && <>
          <h2 className="sec"><NotePencil size={22} />{noteFor.r.employee} · {noteFor.d}/{q.data?.month ?? ''}</h2>
          <Field label="סטטוס"><select className="input" value={noteFor.status} onChange={(e) => setNoteFor({ ...noteFor, status: e.target.value })}>
            {noteFor.r.allowed_statuses.map((st) => <option key={st} value={st}>{st || 'ריק'}</option>)}</select></Field>
          <Field label="הערה"><input className="input" value={noteFor.note} onChange={(e) => setNoteFor({ ...noteFor, note: e.target.value })} placeholder="למשל: קורס, ישיבה" /></Field>
          <div className="row">
            <Cta onClick={() => { apply(noteFor.r, noteFor.d, noteFor.status, noteFor.note); setNoteFor(null); }}>שמירה</Cta>
            <button className="btn" onClick={() => setNoteFor(null)}>ביטול</button>
          </div>
        </>}
      </Modal>
    </>
  );
}

/** Streamlit "העברה זמנית": add someone from another dept for one day, or remove such a day. */
function TransferForm({ g, candidates, onDone }: { g: Grid; candidates: string[]; onDone: () => void }) {
  const { run, busy } = useAction();
  const pnim = !!g.side_groups;
  const first = `${g.year_month}-01`;
  const last = `${g.year_month}-${String(g.days.length).padStart(2, '0')}`;
  const [f, setF] = useState({ employee: '', date: first, side: 'ורוד' });
  const list = Object.entries(g.transfers).flatMap(([emp, t]) => t.days.map((d) => ({ emp, d, side: t.side })))
    .sort((a, b) => a.d - b.d || a.emp.localeCompare(b.emp));
  const body = (employee: string, date: string, side = '') => ({ dept: g.dept, employee, date, side });
  const add = () => run('/work/transfer', 'POST', body(f.employee, f.date, pnim ? f.side : ''), `${f.employee} נוסף/ה ל${g.dept} ב-${dmy(f.date)}`)
    .then(() => { setF({ ...f, employee: '' }); onDone(); }).catch(() => {});
  return (
    <Bezel>
      <h2 className="sec"><ArrowsLeftRight size={22} />העברה זמנית</h2>
      <p className="muted small" style={{ marginBottom: 12 }}>הוספת עובד/ת ממחלקה אחרת ל{g.dept} ליום מסוים.{pnim ? ' בפנימית אפשר גם להעביר בין הצדדים.' : ''}</p>
      <div className={pnim ? 'cols3' : 'cols2'}>
        <Field label="עובד/ת"><select className="input" value={f.employee} onChange={(e) => setF({ ...f, employee: e.target.value })}>
          <option value="">בחר/י</option>{candidates.map((n) => <option key={n}>{n}</option>)}</select></Field>
        <Field label="תאריך"><input className="input" type="date" min={first} max={last} value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
        {pnim && <Field label="צד"><select className="input" value={f.side} onChange={(e) => setF({ ...f, side: e.target.value })}>
          <option value="ורוד">צד ורוד</option><option value="כחול">צד כחול</option></select></Field>}
      </div>
      <Cta variant="teal" icon={<Plus size={16} />} disabled={busy || !f.employee || f.date < first || f.date > last} onClick={add}>הוסף</Cta>
      {list.length > 0 && (
        <>
          <h3 className="sub" style={{ marginTop: 18 }}>העברות זמניות בחודש זה</h3>
          <div className="cardlist">{list.map((t) => {
            const ds = `${g.year_month}-${String(t.d).padStart(2, '0')}`;
            return (
              <div key={t.emp + t.d} className="rcard">
                <div className="main"><b>{t.emp}</b><div className="meta">{dmy(ds)}{pnim && t.side ? ` · צד ${t.side}` : ''}</div></div>
                <button className="btn no" disabled={busy} onClick={() => run('/work/transfer', 'DELETE', body(t.emp, ds), 'ההעברה הוסרה').then(onDone).catch(() => {})}><X size={14} />הסר</button>
              </div>
            );
          })}</div>
        </>
      )}
    </Bezel>
  );
}

/** Streamlit _render_export_buttons: batched Excel download + the WSD_<dept> tab in Sheets. */
function DeptExports({ dept, ym }: { dept: string; ym: string }) {
  const { download, busy } = useDownload();
  const { run, busy: sheetBusy } = useAction();
  const toSheet = async () => {
    // Open the tab first so Safari doesn't block it as a popup, then point it at the sheet.
    const w = window.open('', '_blank');
    try {
      const r = await run<{ url: string }>(`/export/work/${enc(dept)}/${ym}/sheet`, 'POST', undefined, 'הגיליון נוצר');
      if (r?.url && w) w.location.href = r.url; else w?.close();
    } catch { w?.close(); }
  };
  return (
    <>
      <button className="btn" disabled={busy} onClick={() => download(`/export/work/${enc(dept)}/${ym}`)}><FileXls size={16} />הורד Excel</button>
      <button className="btn" disabled={sheetBusy} onClick={toSheet}><GoogleLogo size={16} />פתח ב-Sheets</button>
    </>
  );
}

function ManagerWork({ depts }: { depts: string[] }) {
  const me = useMe();
  const [dept, setDept] = useState(depts[0]);
  const [ym, setYm] = useState(ymOf(new Date().getFullYear(), new Date().getMonth() + 1));
  const [y, m] = ym.split('-').map(Number);
  return (
    <>
      <PageHead eyebrow={`${HEB_MONTHS[m - 1]} ${y}`} title="סידור עבודה" sub={dept} actions={<><MonthPick value={ym} onChange={setYm} /><DeptExports dept={dept} ym={ym} /></>} />
      {depts.length > 1 && <div className="row" style={{ marginBottom: 18 }}><PillSeg value={dept} onChange={setDept} options={depts.map((d) => ({ v: d, l: d }))} /></div>}
      <StatusLegend />
      <DeptGridLive key={dept + ym} dept={dept} ym={ym} me={me.name} />
    </>
  );
}

function MyWork() {
  const me = useMe();
  const [ym, setYm] = useState(ymOf(new Date().getFullYear(), new Date().getMonth() + 1));
  const [y, m] = ym.split('-').map(Number);
  const q = useApi<{ dept: string }>(`/work/me/${ym}`);
  const { download, busy } = useDownload();
  return (
    <>
      <PageHead eyebrow={`${HEB_MONTHS[m - 1]} ${y}`} title="סידור עבודה"
        sub={q.data?.dept ? <>מחלקתך: <b>{q.data.dept}</b></> : q.loading ? '' : 'טרם שובצת למחלקה בחודש זה'}
        actions={<><MonthPick value={ym} onChange={setYm} />{q.data?.dept && <button className="btn" disabled={busy} onClick={() => download(`/export/me/${ym}`)}><FileXls size={16} />הורד לוח עבודה שלי</button>}</>} />
      <Load q={q}>{(r) => r.dept
        ? <><StatusLegend /><DeptGridLive key={ym} dept={r.dept} ym={ym} me={me.name} /></>
        : <Note kind="info">טרם שובצת למחלקה ב{HEB_MONTHS[m - 1]} {y}. הסידור יופיע כאן אחרי שיבוץ החודש בגאנט.</Note>}</Load>
    </>
  );
}

export default function LiveWork() {
  const me = useMe();
  if (me.type === 'מנהל על' || me.type === 'מנהל/ת') return <ManagerWork depts={DAILY_DEPTS} />;
  if (me.type === 'מנהל מחלקה') {
    const mine = DAILY_DEPTS.filter((d) => me.manage_depts.includes(d));
    return mine.length ? <ManagerWork depts={mine} /> : <><PageHead title="סידור עבודה" /><Note kind="warn">לא הוגדרו מחלקות בניהולך. פנה/י למנהל המערכת.</Note></>;
  }
  return <MyWork />;
}
