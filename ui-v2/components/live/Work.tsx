'use client';
import { useState } from 'react';
import { Bell, Moon, Sun } from '@phosphor-icons/react';
import { useApi, type Grid, type GridRow } from '@/lib/api';
import { DAILY_DEPTS, DOW_FULL, HEB_MONTHS } from '@/lib/mock';
import { useMe, useStore, ymOf } from '@/lib/store';
import { Bezel, Note, PageHead, Person, PillSeg, StatusLegend } from '../ui';
import { Load, MonthPick, STATUS_CLASS, enc, useAction } from './common';

const first = (n: string) => n.replace('ד"ר ', '').trim().split(' ')[0];
const names = (v: string | string[] | null) => (Array.isArray(v) ? v : v ? [v] : []).filter((x) => x && x !== '---');

function weeks(g: Grid) {
  const out: (number | null)[][] = []; let wk: (number | null)[] = Array(g.days[0].weekday).fill(null);
  for (const d of g.days) { wk.push(d.day); if (wk.length === 7) { out.push(wk); wk = []; } }
  if (wk.length) out.push([...wk, ...Array(7 - wk.length).fill(null)]);
  return out;
}

function GridView({ g, me, onCycle }: { g: Grid; me: string; onCycle: (r: GridRow, d: number) => void }) {
  const pnim = !!g.side_groups;
  const groups = pnim ? [{ k: 'ורוד', l: 'צד ורוד', c: 'pink' }, { k: 'כחול', l: 'צד כחול', c: 'blue' }] : [{ k: '', l: '', c: '' }];
  const day = (d: number) => g.days[d - 1];
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
                        onClick={() => onCycle(r, d)} title={`${r.employee} · ${d}/${g.month} · ${c.status || 'לא הוגדר'}${c.note ? ' · ' + c.note : ''}${c.manual ? ' (ידני)' : ''}`}>
                        {c.blank_weekend ? '' : c.label}{c.note && <span className="nt" />}
                      </button>
                    );
                  }),
                ]),
              ];
            })}
            <div className="gsep" />
            <div className="meta-l"><Moon size={18} weight="light" />תורנ/ית</div>
            {wk.map((d, i) => { const n = d ? names(day(d).night_duty) : []; return n.length ? <span key={'n' + i} className="mchip">{n.map(first).join(', ')}</span> : <span key={'n' + i} />; })}
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

function DeptGridLive({ dept, ym, me }: { dept: string; ym: string; me: string }) {
  const q = useApi<Grid>(`/work/${enc(dept)}/${ym}`);
  const { run } = useAction();
  const { toast } = useStore();
  const cycle = (r: GridRow, d: number) => {
    const body = { dept, date: `${ym}-${String(d).padStart(2, '0')}`, employee: r.employee };
    const prev = r.cells[d - 1];
    run<{ status: string }>('/work/cell/cycle', 'POST', body).then((res) => {
      q.reload();
      // Undo: put back a previous manual value, or drop the override so the day is computed again.
      const restore = prev.manual && prev.status && r.allowed_statuses.includes(prev.status)
        ? () => run('/work/cell', 'PUT', { ...body, status: prev.status, note: prev.note }).then(q.reload).catch(() => {})
        : () => run('/work/cell', 'DELETE', body).then(q.reload).catch(() => {});
      toast(`${first(r.employee)} · ${d}/${q.data?.month ?? ''}: ${prev.status || 'לא הוגדר'} ← ${res?.status || 'לא הוגדר'}`, 'info', { label: 'בטל', fn: restore });
    }).catch(() => {});
  };
  return <Load q={q}>{(g) => <GridView g={g} me={me} onCycle={cycle} />}</Load>;
}

function ManagerWork({ depts }: { depts: string[] }) {
  const me = useMe();
  const [dept, setDept] = useState(depts[0]);
  const [ym, setYm] = useState(ymOf(new Date().getFullYear(), new Date().getMonth() + 1));
  const [y, m] = ym.split('-').map(Number);
  return (
    <>
      <PageHead eyebrow={`${HEB_MONTHS[m - 1]} ${y}`} title="סידור עבודה" sub={dept} actions={<MonthPick value={ym} onChange={setYm} />} />
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
  return (
    <>
      <PageHead eyebrow={`${HEB_MONTHS[m - 1]} ${y}`} title="סידור עבודה"
        sub={q.data?.dept ? <>מחלקתך: <b>{q.data.dept}</b></> : q.loading ? '' : 'טרם שובצת למחלקה בחודש זה'}
        actions={<MonthPick value={ym} onChange={setYm} />} />
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
