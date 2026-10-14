'use client';
import { useState } from 'react';
import { ArrowsClockwise, FloppyDisk, Hospital, Wheelchair } from '@phosphor-icons/react';
import { useStore } from '@/lib/store';
import { DAYS_IN_MONTH, DOW_FULL, HEB_MONTHS, MONTH, YEAR, dowOf, iso, type Konenut } from '@/lib/mock';
import { first, initials } from '@/lib/logic';
import { Bezel, Cta, Field, PageHead } from '../ui';

const ROLES_K: { k: keyof Omit<Konenut, 'date'>; l: string; I: typeof Hospital }[] = [
  { k: 'pnim_dr', l: 'פנ׳', I: Hospital }, { k: 'rehab_dr1', l: 'ש׳1', I: Wheelchair }, { k: 'rehab_dr2', l: 'ש׳2', I: Wheelchair },
];

export default function OnCall() {
  const { db, mutate, toast } = useStore();
  const docs = db.staff.filter((s) => ['רופא בכיר', 'מנהל מחלקה', 'מנהל/ת', 'מנהל על'].includes(s.type)).map((s) => s.name);
  const [draft, setDraft] = useState<Konenut[]>(() => structuredClone(db.konenut));
  const [day, setDay] = useState(14);
  const dirty = JSON.stringify(draft) !== JSON.stringify(db.konenut);
  const set = (d: number, k: keyof Omit<Konenut, 'date'>, v: string) => {
    if (v === '__free') { const t = window.prompt('שם הרופא/ה:'); if (!t) return; v = t; }
    setDraft((x) => x.map((r) => (r.date === iso(YEAR, MONTH, d) ? { ...r, [k]: v } : r)));
  };
  const rowOf = (d: number) => draft.find((r) => r.date === iso(YEAR, MONTH, d))!;
  const lead = Array(dowOf(YEAR, MONTH, 1)).fill(null);
  const Sel = ({ d, k }: { d: number; k: keyof Omit<Konenut, 'date'> }) => {
    const v = rowOf(d)[k];
    return (
      <select className="input" style={{ padding: '5px 8px', fontSize: 12, borderRadius: 10 }} value={docs.includes(v) || !v ? v : v} onChange={(e) => set(d, k, e.target.value)} aria-label={`${d}/${MONTH} ${k}`}>
        <option value="">-</option>
        {!docs.includes(v) && v && <option value={v}>{v}</option>}
        {docs.map((n) => <option key={n} value={n}>{first(n)} {n.split(' ').slice(-1)}</option>)}
        <option value="__free">הקלד שם...</option>
      </select>
    );
  };
  return (
    <>
      <PageHead eyebrow={`${HEB_MONTHS[MONTH - 1]} ${YEAR}`} title="סידור כוננויות"
        actions={<>
          <button className="btn" onClick={() => toast('רשימת הרופאים רועננה', 'info')}><ArrowsClockwise size={14} />רענן רשימת רופאים</button>
          <select className="input" style={{ width: 150 }} defaultValue={MONTH}>{[10, 11, 12].map((m) => <option key={m} value={m}>{String(m).padStart(2, '0')}/{YEAR}</option>)}</select>
        </>} />
      <div className="legend">
        <div className="lg"><span className="T"><Hospital size={14} /></span>פנ׳ · פנימית</div>
        <div className="lg"><span className="W"><Wheelchair size={14} /></span>ש׳1 · שיקום 1</div>
        <div className="lg"><span className="W"><Wheelchair size={14} /></span>ש׳2 · שיקום 2</div>
      </div>

      <div className="desk-only">
        <Bezel>
          <div className="cal">
            {DOW_FULL.map((h, i) => <div key={h} className={`h ${i >= 5 ? 'we' : ''}`}>{h}</div>)}
            {lead.map((_, i) => <div key={'l' + i} className="day blank" />)}
            {Array.from({ length: DAYS_IN_MONTH }, (_, i) => i + 1).map((d) => (
              <div key={d} className={`day ${dowOf(YEAR, MONTH, d) >= 5 ? 'we' : ''}`} style={{ gap: 5 }}>
                <span className="num">{d}</span>
                {ROLES_K.map((r) => <div key={r.k} className="row" style={{ gap: 4, flexWrap: 'nowrap' }}><span className="small muted" style={{ width: 24 }}>{r.l}</span><Sel d={d} k={r.k} /></div>)}
              </div>
            ))}
          </div>
          <div className="row" style={{ marginTop: 18 }}>
            <Cta icon={<FloppyDisk size={16} />} disabled={!dirty} onClick={() => { mutate((x) => { x.konenut = draft; }); toast('סידור הכוננויות לחודש נשמר'); }}>שמור שינויים</Cta>
            {dirty && <span className="muted small">יש שינויים שלא נשמרו</span>}
          </div>
        </Bezel>
      </div>

      <div className="mob-only">
        <Bezel tight>
          <div className="cal">
            {DOW_FULL.map((h) => <div key={h} className="h">{h[0]}</div>)}
            {lead.map((_, i) => <div key={'l' + i} className="day blank" />)}
            {Array.from({ length: DAYS_IN_MONTH }, (_, i) => i + 1).map((d) => {
              const r = rowOf(d);
              return (
                <button key={d} className={`day ${d === day ? 'today' : ''}`} onClick={() => setDay(d)} style={{ fontSize: 9, gap: 1 }}>
                  <span className="num">{d}</span>
                  {ROLES_K.map((k) => <span key={k.k}>{r[k.k] ? initials(r[k.k]) : '-'}</span>)}
                </button>
              );
            })}
          </div>
        </Bezel>
        <Bezel>
          <h2 className="sec">{day}/{MONTH} {DOW_FULL[dowOf(YEAR, MONTH, day)]}</h2>
          {ROLES_K.map((r) => <Field key={r.k} label={r.l}><Sel d={day} k={r.k} /></Field>)}
          <Cta icon={<FloppyDisk size={16} />} onClick={() => { mutate((x) => { x.konenut = x.konenut.map((q) => (q.date === iso(YEAR, MONTH, day) ? rowOf(day) : q)); }); toast(`נשמר יום ${day}/${MONTH}`); }}>שמור יום זה</Cta>
        </Bezel>
      </div>
    </>
  );
}
