'use client';
import { useMemo, useState } from 'react';
import { Bell, DownloadSimple, Moon, NotePencil, Plus, ShareNetwork, Sun, X } from '@phosphor-icons/react';
import { useStore } from '@/lib/store';
import { DAILY_DEPTS, DOW_FULL, FRI_SLOTS, HEB_MONTHS, dowOf, daysIn, iso, type Role } from '@/lib/mock';
import { STATUS, codeToHe, cycleFor, deriveStatus, first, setManual, type Code, type DB } from '@/lib/logic';
import { Bezel, Cta, Field, Modal, Note, PageHead, Person, PillSeg, StatusLegend } from '../ui';

export const MONTHS12 = Array.from({ length: 12 }, (_, i) => { const m = ((9 + i) % 12) + 1; const y = 2026 + Math.floor((9 + i) / 12); return { y, m, v: `${y}-${String(m).padStart(2, '0')}`, l: `${HEB_MONTHS[m - 1]} ${y}` }; });

function weeksOf(y: number, m: number) {
  const n = daysIn(y, m); const out: (number | null)[][] = []; let wk: (number | null)[] = Array(dowOf(y, m, 1)).fill(null);
  for (let d = 1; d <= n; d++) { wk.push(d); if (wk.length === 7) { out.push(wk); wk = []; } }
  if (wk.length) out.push([...wk, ...Array(7 - wk.length).fill(null)]);
  return out;
}

interface Row { name: string; role: Role; side: string; transfer?: Set<number> }
function deptRows(db: DB, dept: string, ym: string): Row[] {
  const order: Role[] = ['מנהל מחלקה', 'רופא בכיר', 'מתמחה'];
  const base = db.rotation.filter((r) => r.year_month === '2026-11' && r.daily_dept === dept).map((r) => {
    const s = db.staff.find((x) => x.name === r.employee); return { name: r.employee, role: (s?.type ?? 'מתמחה') as Role, side: r.side };
  });
  // incoming temporary transfers (manual rows in this dept for people rotated elsewhere)
  const tr = new Map<string, Set<number>>();
  db.wsd.filter((w) => w.is_manual && w.daily_dept === dept && w.date.startsWith(ym) && !base.some((b) => b.name === w.employee))
    .forEach((w) => { if (!tr.has(w.employee)) tr.set(w.employee, new Set()); tr.get(w.employee)!.add(+w.date.slice(8)); });
  const trRows = [...tr.entries()].map(([name, days]) => { const s = db.staff.find((x) => x.name === name); return { name, role: (s?.type ?? 'מתמחה') as Role, side: dept === 'פנימית גריאטרית' ? 'כחול' : '', transfer: days }; });
  return [...base.sort((a, b) => order.indexOf(a.role) - order.indexOf(b.role)), ...trRows];
}

export function DeptGrid({ dept, y, m, editable, meName }: { dept: string; y: number; m: number; editable: boolean; meName?: string }) {
  const { db, mutate, toast } = useStore();
  const [fullEdit, setFullEdit] = useState(false);
  const [edit, setEdit] = useState<{ name: string; d: number; code: Code; note: string } | null>(null);
  const ym = `${y}-${String(m).padStart(2, '0')}`;
  const rows = useMemo(() => deptRows(db, dept, ym), [db, dept, ym]);
  const weeks = weeksOf(y, m);
  const pnim = dept === 'פנימית גריאטרית';
  const groups = pnim ? [{ k: 'ורוד', l: 'צד ורוד', c: 'pink' }, { k: 'כחול', l: 'צד כחול', c: 'blue' }] : [{ k: '', l: '', c: '' }];
  const kon = (d: number) => db.konenut.find((k) => k.date === iso(y, m, d));
  const konFor = (d: number) => { const k = kon(d); if (!k) return ''; return pnim ? k.pnim_dr : dept.endsWith("ב'") ? k.rehab_dr2 : k.rehab_dr1; };
  const nightNames = (d: number) => db.schedule.filter((r) => r.date === iso(y, m, d) && !r.dept.startsWith('שישי') && r.employee !== '---' && rows.some((x) => x.name === r.employee)).map((r) => first(r.employee));
  const friNames = (d: number) => db.schedule.filter((r) => r.date === iso(y, m, d) && FRI_SLOTS.includes(r.dept) && rows.some((x) => x.name === r.employee)).map((r) => first(r.employee));

  const click = (row: Row, d: number) => {
    const st = deriveStatus(db, y, m, d, row.name);
    if (fullEdit) return setEdit({ name: row.name, d, code: st.code, note: st.note });
    const cyc = cycleFor(row.role); const i = cyc.indexOf(st.code);
    const next = cyc[(i + 1) % cyc.length];
    mutate((x) => setManual(x, iso(y, m, d), row.name, dept, next));
  };

  return (
    <>
      {editable && (
        <div className="row" style={{ marginBottom: 14 }}>
          <PillSeg value={fullEdit ? 'f' : 'q'} onChange={(v) => setFullEdit(v === 'f')} options={[{ v: 'q', l: 'לחיצה מחליפה סטטוס' }, { v: 'f', l: 'עריכה עם הערה' }]} />
          <span className="muted small">שבת וימי תורנות מחושבים אוטומטית ונעולים לעריכה</span>
        </div>
      )}
      {weeks.map((wk, wi) => (
        <Bezel key={wi}>
          <div className="row" style={{ marginBottom: 14 }}>
            <b style={{ fontSize: 18 }}>שבוע {wi + 1}</b>
            <span className="muted small">{wk.find(Boolean)} - {[...wk].reverse().find(Boolean)} ב{HEB_MONTHS[m - 1]}</span>
          </div>
          <div className="dgrid">
            <div className="corner" />
            {wk.map((d, i) => <div key={i} className={`dh ${i === 6 ? 'sat' : ''} ${i === 5 ? 'fri' : ''}`}>{DOW_FULL[i]}<b>{d ?? ''}</b></div>)}
            {groups.map((g) => {
              const gr = rows.filter((r) => !pnim || r.side === g.k);
              return [
                pnim && <div key={'h' + g.k} className={`side-h ${g.c}`}>{g.l} · {gr.length}</div>,
                ...gr.flatMap((r) => [
                  <Person key={r.name} name={r.name} role={r.transfer ? `${r.role} · העברה זמנית` : r.role} me={r.name === meName} />,
                  ...wk.map((d, i) => {
                    if (!d) return <span key={r.name + i} />;
                    if (r.transfer && !r.transfer.has(d)) return <button key={r.name + i} className="cell locked" disabled title="מחוץ לימי ההעברה">-</button>;
                    const st = deriveStatus(db, y, m, d, r.name);
                    const locked = !editable || st.code === 'T' || i === 6;
                    return (
                      <button key={r.name + i} className={`cell ${st.code}`} disabled={locked} onClick={() => click(r, d)}
                        title={`${r.name} · ${d}/${m} · ${STATUS[st.code].he}${st.note ? ' · ' + st.note : ''}${st.manual ? ' (ידני)' : ''}`}
                        aria-label={`${r.name} ${d}/${m} ${STATUS[st.code].he}`}>
                        {STATUS[st.code].lab}{st.note && <span className="nt" />}
                      </button>
                    );
                  }),
                ]),
              ];
            })}
            <div className="gsep" />
            <div className="meta-l"><Moon size={18} weight="light" />תורנ/ית</div>
            {wk.map((d, i) => { const n = d ? nightNames(d) : []; return n.length ? <span key={'n' + i} className="mchip">{n.join(', ')}</span> : <span key={'n' + i} />; })}
            <div className="meta-l"><Sun size={18} weight="light" />שישי בוקר</div>
            {wk.map((d, i) => { const n = d ? friNames(d) : []; return n.length ? <span key={'f' + i} className="mchip">{n.join(', ')}</span> : <span key={'f' + i} />; })}
            <div className="meta-l"><Bell size={18} weight="light" />כונן/ית</div>
            {wk.map((d, i) => { const n = d ? konFor(d) : ''; return n ? <span key={'k' + i} className="mchip k">{first(n)}</span> : <span key={'k' + i} />; })}
          </div>
        </Bezel>
      ))}
      <Modal open={!!edit} onClose={() => setEdit(null)}>
        {edit && <>
          <h2 className="sec"><NotePencil size={22} />{edit.name} · {edit.d}/{m}</h2>
          <Field label="סטטוס">
            <select className="input" value={edit.code} onChange={(e) => setEdit({ ...edit, code: e.target.value as Code })}>
              {(['W', 'V', 'S', 'A', 'O', 'E'] as Code[]).map((c) => <option key={c} value={c}>{STATUS[c].he}</option>)}
            </select>
          </Field>
          <Field label="הערה"><input className="input" value={edit.note} onChange={(e) => setEdit({ ...edit, note: e.target.value })} placeholder="למשל: קורס, ישיבה, כוננות בית" /></Field>
          <div className="row">
            <Cta onClick={() => { mutate((x) => setManual(x, iso(y, m, edit.d), edit.name, dept, edit.code, edit.note)); toast(`נשמר: ${edit.name} ${edit.d}/${m} ${codeToHe(edit.code) || 'ללא סטטוס'}`); setEdit(null); }}>שמירה</Cta>
            <button className="btn" onClick={() => setEdit(null)}>ביטול</button>
          </div>
        </>}
      </Modal>
    </>
  );
}

function Transfers({ dept, y, m }: { dept: string; y: number; m: number }) {
  const { db, mutate, toast } = useStore();
  const ym = `${y}-${String(m).padStart(2, '0')}`;
  const inDept = new Set(db.rotation.filter((r) => r.daily_dept === dept).map((r) => r.employee));
  const list = db.wsd.filter((w) => w.is_manual && w.daily_dept === dept && w.date.startsWith(ym) && !inDept.has(w.employee));
  const cands = db.staff.filter((s) => ['מתמחה', 'רופא בכיר'].includes(s.type) && !inDept.has(s.name));
  const [emp, setEmp] = useState(cands[0]?.name ?? '');
  const [date, setDate] = useState(iso(y, m, 18));
  const [side, setSide] = useState('כחול');
  return (
    <Bezel>
      <h2 className="sec"><Plus size={20} />העברה זמנית למחלקה</h2>
      <div className="cols3">
        <Field label="עובד/ת"><select className="input" value={emp} onChange={(e) => setEmp(e.target.value)}>{cands.map((c) => <option key={c.name}>{c.name}</option>)}</select></Field>
        <Field label="תאריך"><input className="input" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
        {dept === 'פנימית גריאטרית'
          ? <Field label="צד"><select className="input" value={side} onChange={(e) => setSide(e.target.value)}><option>ורוד</option><option>כחול</option></select></Field>
          : <div />}
      </div>
      <Cta variant="teal" icon={<Plus size={16} />} onClick={() => { mutate((x) => setManual(x, date, emp, dept, 'W', 'העברה זמנית')); toast(`${emp} הועבר/ה ל${dept} ב-${date.slice(8)}/${+date.slice(5, 7)}`); }}>הוסף</Cta>
      <div style={{ marginTop: 18 }}>
        {list.length === 0 ? <p className="muted small">אין העברות זמניות בחודש זה.</p> : (
          <div className="chips">
            {list.map((w) => (
              <span key={w.employee + w.date} className="chip">{w.employee} · {+w.date.slice(8)}/{+w.date.slice(5, 7)}
                <button aria-label="הסר" onClick={() => { mutate((x) => { x.wsd = x.wsd.filter((r) => !(r.employee === w.employee && r.date === w.date)); }); toast('ההעברה הוסרה', 'info'); }}><X size={12} /></button>
              </span>
            ))}
          </div>
        )}
      </div>
    </Bezel>
  );
}

export function ExportButtons({ dept, label }: { dept: string; label: string }) {
  const { toast } = useStore();
  return (
    <>
      <Cta variant="light" icon={<DownloadSimple size={16} />} onClick={() => toast(`קובץ Excel הורד: ${dept}, ${label} (A4 לרוחב, בלוקים שבועיים)`)}>הורד Excel</Cta>
      <Cta variant="light" icon={<ShareNetwork size={16} />} onClick={() => toast(`נוצרה לשונית WSD ב-Google Sheets. שים לב: הגיליון משותף לכל מי שיש לו קישור.`, 'warn')}>פתח ב-Sheets</Cta>
    </>
  );
}

export default function Work() {
  const [dept, setDept] = useState(DAILY_DEPTS[0]);
  const [ym, setYm] = useState('2026-11');
  const mo = MONTHS12.find((x) => x.v === ym)!;
  return (
    <>
      <PageHead eyebrow={mo.l} title="סידור עבודה" sub={`${dept} · לחיצה על משבצת משנה סטטוס`}
        actions={<>
          <select className="input" style={{ width: 170 }} value={ym} onChange={(e) => setYm(e.target.value)} aria-label="חודש">{MONTHS12.map((x) => <option key={x.v} value={x.v}>{x.l}</option>)}</select>
          <ExportButtons dept={dept} label={mo.l} />
        </>} />
      <div className="row" style={{ marginBottom: 18 }}>
        <PillSeg value={dept} onChange={setDept} options={DAILY_DEPTS.map((d) => ({ v: d, l: d }))} />
      </div>
      {ym !== '2026-11' && <Note kind="info">לחודש זה עדיין אין שיבוץ מחלקות בגאנט. מוצגים ימי עבודה מחושבים בלבד.</Note>}
      <StatusLegend />
      <DeptGrid dept={dept} y={mo.y} m={mo.m} editable />
      <Transfers dept={dept} y={mo.y} m={mo.m} />
    </>
  );
}
