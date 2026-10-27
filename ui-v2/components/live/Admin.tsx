'use client';
import { useEffect, useState } from 'react';
import { CheckCircle, FloppyDisk, Lightning, LockSimple, LockSimpleOpen, Table, Warning, WarningOctagon } from '@phosphor-icons/react';
import { useApi } from '@/lib/api';
import { DOW_FULL, HEB_MONTHS, dowOf } from '@/lib/mock';
import { useMe, useStore, ymOf } from '@/lib/store';
import { Bezel, Cta, Kpi, Note, PageHead, Person, useTip } from '../ui';
import { Load, MonthPick, dmy, useAction } from './common';

// ── גאנט חודשי ───────────────────────────────────────────────────────────────
interface GRow { name: string; type: string; options: string[]; dept: string | null; invalid_existing: boolean; side: string; manual_schedule_only: boolean }

export function LiveGantt() {
  const me = useMe();
  const { refreshMe, toast } = useStore();
  const [ym, setYm] = useState(ymOf(me.settings.daily_active_year, me.settings.daily_active_month));
  const [y, m] = ym.split('-').map(Number);
  const q = useApi<{ rows: GRow[]; summary: { total: number; by_dept: Record<string, number> } }>(`/gantt/${ym}`);
  const { run, busy } = useAction();
  const [form, setForm] = useState<Record<string, { dept: string; side: string }>>({});
  useEffect(() => { if (q.data) setForm(Object.fromEntries(q.data.rows.map((r) => [r.name, { dept: r.dept ?? '', side: r.side }]))); }, [q.data]);
  const active = me.settings.daily_active_month === m && me.settings.daily_active_year === y;
  const open = me.settings.daily_requests_open;
  const save = () => {
    const assignments = Object.fromEntries(Object.entries(form).map(([n, v]) => [n, v.dept || '— לא שובץ —']));
    const sides = Object.fromEntries(Object.entries(form).filter(([, v]) => v.side).map(([n, v]) => [n, v.side]));
    run<{ saved: number; migrated: number }>(`/gantt/${ym}`, 'PUT', { assignments, sides }).then((r) => {
      if (r) toast(`השיבוץ נשמר${r.migrated ? `. הועברו ${r.migrated} בקשות היעדרות` : ''}`); q.reload();
    }).catch(() => {});
  };
  return (
    <>
      <PageHead eyebrow="שיוך עובדים למחלקות" title="גאנט חודשי" />
      <Bezel>
        <div className="row">
          <div className="field" style={{ margin: 0 }}><label>חודש לתכנון ועריכה</label><MonthPick value={ym} onChange={setYm} /></div>
          <span className="grow" />
          {active
            ? <span className="badge b-ok" style={{ fontSize: 14, padding: '6px 14px' }}><CheckCircle size={16} weight="fill" />זהו החודש הפעיל</span>
            : <Cta variant="teal" icon={<Lightning size={16} />} disabled={busy} onClick={() => run(`/gantt/${ym}/activate`, 'POST', undefined, `${HEB_MONTHS[m - 1]} הוא עכשיו החודש הפעיל`).then(refreshMe).catch(() => {})}>הפוך את {HEB_MONTHS[m - 1]} לחודש פעיל</Cta>}
          {active && <Cta variant={open ? 'light' : 'teal'} icon={open ? <LockSimple size={16} /> : <LockSimpleOpen size={16} />} disabled={busy}
            onClick={() => run('/settings/daily_requests_open', 'PUT', { open: !open }, open ? 'ההגשות נסגרו' : 'ההגשות נפתחו').then(refreshMe).catch(() => {})}>{open ? 'סגור הגשות' : 'פתח הגשות'}</Cta>}
        </div>
      </Bezel>
      <Load q={q}>{(d) => (
        <Bezel>
          <h2 className="sec">שיוך ל{HEB_MONTHS[m - 1]} {y}</h2>
          {d.rows.some((r) => r.manual_schedule_only) && <Note kind="warn">סידור ידני בלבד: {d.rows.filter((r) => r.manual_schedule_only).map((r) => r.name).join(', ')}</Note>}
          <div className="tbl-wrap"><table className="t">
            <thead><tr><th>עובד/ת</th><th>מחלקה</th><th>צד (פנימית)</th></tr></thead>
            <tbody>{d.rows.map((r) => {
              const v = form[r.name] ?? { dept: '', side: '' };
              return (
                <tr key={r.name}>
                  <td><Person name={r.name} role={r.type} /></td>
                  <td><select className="input" value={v.dept} style={r.invalid_existing ? { boxShadow: 'inset 0 0 0 1.5px var(--danger)' } : undefined}
                    onChange={(e) => setForm({ ...form, [r.name]: { dept: e.target.value, side: e.target.value === 'פנימית גריאטרית' ? v.side : '' } })}>
                    <option value="">לא שובץ</option>{r.options.filter((o) => o !== '— לא שובץ —').map((o) => <option key={o}>{o}</option>)}</select></td>
                  <td><select className="input" value={v.side} disabled={v.dept !== 'פנימית גריאטרית'} onChange={(e) => setForm({ ...form, [r.name]: { ...v, side: e.target.value } })}>
                    <option value="">-</option><option value="ורוד">צד ורוד</option><option value="כחול">צד כחול</option></select></td>
                </tr>
              );
            })}</tbody>
          </table></div>
          <div className="row" style={{ marginTop: 18 }}>
            <Cta icon={<FloppyDisk size={16} />} disabled={busy} onClick={save}>שמור שיבוץ</Cta><span className="grow" />
            {Object.entries(d.summary.by_dept).map(([k, n]) => <span key={k} className="chip">{k}: <b>{n}</b></span>)}
          </div>
        </Bezel>
      )}</Load>
    </>
  );
}

// ── סידור כוננויות ───────────────────────────────────────────────────────────
interface KDay { date: string; pnim_dr: string; rehab_dr1: string; rehab_dr2: string }

export function LiveOnCall() {
  const [ym, setYm] = useState(ymOf(new Date().getFullYear(), new Date().getMonth() + 1));
  const [y, m] = ym.split('-').map(Number);
  const q = useApi<{ days: KDay[]; doctors: string[] }>(`/oncall/${ym}`);
  const { run, busy } = useAction();
  const [draft, setDraft] = useState<KDay[]>([]);
  useEffect(() => { if (q.data) setDraft(q.data.days); }, [q.data]);
  const dirty = q.data && JSON.stringify(draft) !== JSON.stringify(q.data.days);
  const cols: [keyof KDay, string][] = [['pnim_dr', 'פנימית'], ['rehab_dr1', 'שיקום 1'], ['rehab_dr2', 'שיקום 2']];
  return (
    <>
      <PageHead eyebrow={`${HEB_MONTHS[m - 1]} ${y}`} title="סידור כוננויות" actions={<MonthPick value={ym} onChange={setYm} />} />
      <Load q={q}>{(d) => (
        <Bezel>
          <div className="tbl-wrap"><table className="t">
            <thead><tr><th>תאריך</th>{cols.map(([, l]) => <th key={l}>{l}</th>)}</tr></thead>
            <tbody>{draft.map((row, i) => (
              <tr key={row.date} className={dowOf(y, m, +row.date.slice(8)) >= 5 ? 'we-row' : ''}>
                <td className="num">{dmy(row.date)} {DOW_FULL[dowOf(y, m, +row.date.slice(8))]}</td>
                {cols.map(([k]) => (
                  <td key={k}><select className="input" value={row[k]} onChange={(e) => setDraft(draft.map((r, j) => (j === i ? { ...r, [k]: e.target.value } : r)))}>
                    <option value="">-</option>{row[k] && !d.doctors.includes(row[k]) && <option>{row[k]}</option>}{d.doctors.map((n) => <option key={n}>{n}</option>)}</select></td>
                ))}
              </tr>
            ))}</tbody>
          </table></div>
          <div className="row" style={{ marginTop: 16 }}>
            <Cta icon={<FloppyDisk size={16} />} disabled={!dirty || busy} onClick={() => run(`/oncall/${ym}`, 'PUT', { days: draft }, 'סידור הכוננויות נשמר').then(q.reload).catch(() => {})}>שמור שינויים</Cta>
            {dirty && <span className="muted small">יש שינויים שלא נשמרו</span>}
          </div>
        </Bezel>
      )}</Load>
    </>
  );
}

// ── צוות ─────────────────────────────────────────────────────────────────────
export function LiveStaff() {
  const q = useApi<{ columns: string[]; rows: Record<string, string | number | boolean>[]; only_home: string[] }>('/staff');
  const LABEL: Record<string, string> = { name: 'שם', type: 'תפקיד', dept: 'מחלקה', monthly_quota: 'מכסה', weekend_quota: 'סופ״ש', email: 'אימייל', manage_depts: 'מחלקות בניהולו', recurring_absent_days: 'ימי היעדרות קבועים', manual_schedule_only: 'שיבוץ ידני בלבד' };
  return (
    <>
      <PageHead eyebrow="מנהל על" title="צוות" sub={q.data ? `${q.data.rows.length} אנשי צוות` : ''} />
      <Note kind="info">עריכת הצוות (הוספה, מחיקה ושינוי פרטים) תיפתח בשלב הכתיבה. בינתיים מוצגים הנתונים מהגיליון.</Note>
      <Load q={q}>{(d) => {
        const cols = d.columns.filter((c) => LABEL[c]);
        return (
          <Bezel>
            <div className="tbl-wrap"><table className="t">
              <thead><tr>{cols.map((c) => <th key={c}>{LABEL[c]}</th>)}<th>מוגבל/ת למחלקת הבית</th></tr></thead>
              <tbody>{d.rows.map((r) => (
                <tr key={String(r.name)}>{cols.map((c) => <td key={c} className={c === 'email' ? 'small' : ''} dir={c === 'email' ? 'ltr' : undefined}>{typeof r[c] === 'boolean' ? (r[c] ? '✓' : '') : String(r[c] ?? '')}</td>)}
                  <td>{d.only_home.includes(String(r.name)) ? '✓' : ''}</td></tr>
              ))}</tbody>
            </table></div>
          </Bezel>
        );
      }}</Load>
    </>
  );
}

// ── דוחות וניהול ─────────────────────────────────────────────────────────────
interface Report {
  submissions: { total: number; submitted: number; pending: number; rows: { name: string; type: string; submitted: boolean; blocks: number; wishes: number }[] };
  shift_counts: { employee: string; sh: number; pn: number; fri: number }[];
  problems: { generated_at: string | null; rows: { severity: string; problem_type: string; description: string }[] };
  fairness: { name: string; wed: number; thu: number; friday_morning: number; net: number }[];
}
const scoreColor = (s: number) => (s >= 1 ? 'var(--W)' : s <= -2 ? 'var(--B)' : s < 0 ? 'var(--S)' : '#F4F6F8');
const SERIES = [{ k: 'sh', l: 'תורנות שיקום', c: 'var(--chart1)' }, { k: 'pn', l: 'תורנות פנג״ר', c: 'var(--chart3)' }, { k: 'fri', l: 'שישי בוקר', c: 'var(--chart2)' }] as const;

export function LiveReports() {
  const me = useMe();
  const [ym, setYm] = useState(ymOf(me.settings.active_year, me.settings.active_month));
  const [y, m] = ym.split('-').map(Number);
  const q = useApi<Report>(`/reports/${ym}`);
  const { bind, node } = useTip();
  const [asTable, setAsTable] = useState(false);
  return (
    <>
      <PageHead eyebrow={`${HEB_MONTHS[m - 1]} ${y}`} title="דוחות וניהול" sub="לוח בקרה חודשי" actions={<MonthPick value={ym} onChange={setYm} />} />
      <Load q={q}>{(r) => {
        const crit = r.problems.rows.filter((p) => p.severity === 'קריטי');
        const tot = (d: Report['shift_counts'][number]) => d.sh + d.pn + d.fri;
        const max = Math.max(1, ...r.shift_counts.map(tot));
        return (
          <>
            <div className="kpis">
              <Kpi k="סה״כ צוות תורנויות" v={r.submissions.total} />
              <Kpi k="הגישו אילוצים" v={r.submissions.submitted} small={`מתוך ${r.submissions.total}`} />
              <Kpi k="ממתינים להגשה" v={r.submissions.pending} />
              <Kpi k="בעיות קריטיות" v={crit.length} icon={<WarningOctagon size={14} weight="fill" color="var(--danger)" />} />
            </div>
            <div className="split">
              <div>
                <Bezel>
                  <div className="row" style={{ marginBottom: 12 }}>
                    <h2 className="sec" style={{ margin: 0 }}>ספירת תורנויות</h2><span className="grow" />
                    <button className="btn" onClick={() => setAsTable(!asTable)}><Table size={14} />{asTable ? 'תרשים' : 'טבלה'}</button>
                  </div>
                  <div className="row" style={{ marginBottom: 12 }}>{SERIES.map((x) => <span key={x.k} className="row small"><span style={{ width: 12, height: 12, borderRadius: 3, background: x.c }} />{x.l}</span>)}</div>
                  {r.shift_counts.length === 0 ? <p className="muted">אין שיבוצים לחודש זה.</p> : asTable ? (
                    <table className="t"><thead><tr><th>עובד/ת</th>{SERIES.map((x) => <th key={x.k}>{x.l}</th>)}<th>סה״כ</th></tr></thead>
                      <tbody>{r.shift_counts.map((d) => <tr key={d.employee}><td>{d.employee}</td>{SERIES.map((x) => <td key={x.k} className="num">{d[x.k]}</td>)}<td className="num">{tot(d)}</td></tr>)}</tbody></table>
                  ) : (
                    <div className="bars">{r.shift_counts.map((d) => (
                      <div key={d.employee} className="bar-row"><span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{d.employee}</span>
                        <div className="bar-track">{SERIES.map((x) => d[x.k] > 0 && <div key={x.k} className="bar-seg" style={{ width: `${(d[x.k] / max) * 100}%`, background: x.c }} {...bind(`${d.employee}: ${d[x.k]} ${x.l}`)} />)}</div>
                        <span className="num" style={{ fontWeight: 700 }}>{tot(d)}</span></div>
                    ))}</div>
                  )}
                  {node}
                </Bezel>
                <Bezel>
                  <h2 className="sec"><Warning size={22} />דוח בעיות צפויות</h2>
                  <p className="muted small" style={{ marginBottom: 10 }}>סריקה אחרונה: {r.problems.generated_at ?? 'אין'}</p>
                  {r.problems.rows.length === 0 ? <p className="muted">אין דוח.</p> : (
                    <div className="cardlist">{r.problems.rows.map((p, i) => (
                      <div key={i} className="rcard"><span className={`badge ${p.severity === 'קריטי' ? 'b-err' : p.severity === 'אזהרה' ? 'b-warn' : 'b-info'}`}>{p.severity}</span>
                        <div className="main"><b>{p.problem_type}</b><div className="meta">{p.description}</div></div></div>
                    ))}</div>
                  )}
                </Bezel>
              </div>
              <div>
                <Bezel>
                  <h2 className="sec">סטטוס הגשות</h2>
                  <div className="cardlist">{r.submissions.rows.map((s) => (
                    <div key={s.name} className="rcard"><Person name={s.name} role={s.type} />
                      <div className="main">{s.submitted ? <span className="badge b-ok">הגיש/ה</span> : <span className="badge b-warn">טרם הגיש/ה</span>}
                        <div className="meta">{s.blocks} חסימות · {s.wishes} בקשות</div></div></div>
                  ))}</div>
                </Bezel>
                <Bezel>
                  <h2 className="sec">מעקב הוגנות</h2>
                  <p className="muted small" style={{ marginBottom: 10 }}>מתמחים בלבד, כל החודשים. ציון = רביעי פחות (חמישי + שישי בוקר).</p>
                  {r.fairness.length === 0 ? <p className="muted">אין שיבוצים.</p> : (
                    <div className="tbl-wrap"><table className="t"><thead><tr><th>מתמחה</th><th>ד׳</th><th>ה׳</th><th>ו׳ בוקר</th><th>ציון</th></tr></thead>
                      <tbody>{r.fairness.map((f) => <tr key={f.name}><td>{f.name}</td><td className="num">{f.wed}</td><td className="num">{f.thu}</td><td className="num">{f.friday_morning}</td>
                        <td className="num" style={{ background: scoreColor(f.net), borderRadius: 8, textAlign: 'center' }}>{f.net > 0 ? '+' : ''}{f.net}</td></tr>)}</tbody></table></div>
                  )}
                </Bezel>
              </div>
            </div>
          </>
        );
      }}</Load>
    </>
  );
}
