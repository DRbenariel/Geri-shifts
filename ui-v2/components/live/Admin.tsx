'use client';
import { useEffect, useMemo, useState } from 'react';
import { ArrowsClockwise, ChartLineUp, Check, CheckCircle, FileXls, FloppyDisk, Lightning, LockSimple, LockSimpleOpen, Moon, Plus, Sun, Table, Trash, UserGear, UserMinus, UserPlus, Warning, WarningOctagon, X } from '@phosphor-icons/react';
import { ApiError, useApi, type Pending } from '@/lib/api';
import { DAILY_DEPTS, DOW_FULL, HEB_MONTHS, ROLES, STAFF_DEPTS, dowOf, roleLabel } from '@/lib/mock';
import { useMe, useStore, ymOf } from '@/lib/store';
import { Bezel, Cta, Expander, Field, Kpi, Modal, Note, PageHead, Person, PillSeg, SaveBar, useTip } from '../ui';
import { ConstraintCalendar } from '../tabs/Staff';
import { HBars, VBars } from '../tabs/Reports';
import { Load, MonthPick, dmy, inSettingWindow, range, useAction, useDownload } from './common';

// ── גאנט חודשי ───────────────────────────────────────────────────────────────
interface GRow { name: string; type: string; options: string[]; dept: string | null; invalid_existing: boolean; side: string; manual_schedule_only: boolean }

export function LiveGantt() {
  const me = useMe();
  const { refreshMe, toast } = useStore();
  const [ym, setYm] = useState(ymOf(me.settings.daily_active_year, me.settings.daily_active_month));
  const [y, m] = ym.split('-').map(Number);
  const q = useApi<{ rows: GRow[]; summary: { total: number; by_dept: Record<string, number> } }>(`/gantt/${ym}`);
  const { run, busy } = useAction();
  const xl = useDownload();
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
            : <Cta variant="teal" icon={<Lightning size={16} />} disabled={busy || !inSettingWindow(ym)} onClick={() => run(`/gantt/${ym}/activate`, 'POST', undefined, `${HEB_MONTHS[m - 1]} הוא עכשיו החודש הפעיל`).then(refreshMe).catch(() => {})}>הפוך את {HEB_MONTHS[m - 1]} לחודש פעיל</Cta>}
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
            <button className="btn" disabled={xl.busy} onClick={() => xl.download(`/export/work-all/${ym}`)}><FileXls size={16} />Excel, כל המחלקות</button>
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

// ── צוות ──────────────────────────────────────────────────────────────
type SRow = Record<string, string | number | boolean>;
const truthy = (v: unknown) => v === true || String(v).trim().toLowerCase() === 'true';
const deptsOf = (v: unknown) => String(v ?? '').split(',').map((s) => s.trim()).filter(Boolean);

function DeptChips({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  return (
    <div className="chips">{DAILY_DEPTS.map((d) => {
      const on = value.includes(d);
      return <button key={d} type="button" className={`chip ${on ? 'sel' : ''}`} onClick={() => onChange(on ? value.filter((x) => x !== d) : [...value, d])}>{on && <Check size={12} />}{d}</button>;
    })}</div>
  );
}

function AddEmployeeLive({ onDone }: { onDone: () => void }) {
  const { run, busy } = useAction();
  const blank = { name: '', type: 'מתמחה', email: '', dept: 'שיקום', monthly_quota: 6, weekend_quota: 1, only_home: false, manage_depts: [] as string[] };
  const [f, setF] = useState(blank);
  const add = () => run('/staff', 'POST', { ...f, name: f.name.trim(), manage_depts: f.type === 'מנהל מחלקה' ? f.manage_depts : [] },
    `${f.name.trim()} נוסף/ה. סיסמה ראשונית: 1234`).then(() => { setF(blank); onDone(); }).catch(() => {});
  return (
    <Expander title="הוספת עובד/ת" icon={<UserPlus size={20} />}>
      <div className="cols3">
        <Field label="שם מלא"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="תפקיד"><select className="input" value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })}>{ROLES.map((r) => <option key={r} value={r}>{roleLabel(r)}</option>)}</select></Field>
        <Field label="אימייל (להתראות)"><input className="input" type="email" dir="ltr" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="מחלקה"><select className="input" value={f.dept} onChange={(e) => setF({ ...f, dept: e.target.value })}>{STAFF_DEPTS.map((d) => <option key={d}>{d}</option>)}</select></Field>
        <Field label="מכסה חודשית"><input className="input" type="number" min={0} value={f.monthly_quota} onChange={(e) => setF({ ...f, monthly_quota: +e.target.value })} /></Field>
        <Field label="מכסת סופ״ש"><input className="input" type="number" min={0} value={f.weekend_quota} onChange={(e) => setF({ ...f, weekend_quota: +e.target.value })} /></Field>
      </div>
      <label className="check" style={{ marginBottom: 14 }}><input type="checkbox" checked={f.only_home} onChange={(e) => setF({ ...f, only_home: e.target.checked })} />מוגבל/ת למחלקה זו בלבד</label>
      {f.type === 'מנהל מחלקה' && <Field label="מחלקות בניהולו/ה"><DeptChips value={f.manage_depts} onChange={(v) => setF({ ...f, manage_depts: v })} /></Field>}
      <Cta variant="teal" icon={<Plus size={16} />} disabled={busy || !f.name.trim()} onClick={add}>הוסף לצוות</Cta>
    </Expander>
  );
}

// Streamlit צוות → "ניהול אילוצים ומשמרות": one employee's night constraints (no submission rules)
// and their day-absence requests.
type Cons = Record<number, 'B' | 'R'>;
interface AbsRow { id: string; start_date: string; end_date: string; type: string; status: string; approved_by: string; notes: string }

function EmployeeConstraints({ name, ym }: { name: string; ym: string }) {
  const [y, m] = ym.split('-').map(Number);
  const q = useApi<{ blocked: number[]; wishes: number[] }>(`/constraints/${ym}?employee=${encodeURIComponent(name)}`);
  const sd = useApi<{ date: string; description: string }[]>('/special-days');
  const { run, busy } = useAction();
  const saved = useMemo<Cons>(() => q.data ? { ...Object.fromEntries(q.data.blocked.map((d) => [d, 'B'])), ...Object.fromEntries(q.data.wishes.map((d) => [d, 'R'])) } : {}, [q.data]);
  const [cons, setCons] = useState<Cons>({});
  useEffect(() => setCons(saved), [saved]);
  const special = Object.fromEntries((sd.data ?? []).filter((s) => s.date.startsWith(ym)).map((s) => [+s.date.slice(8), s.description]));
  const nChanged = new Set([...Object.keys(cons), ...Object.keys(saved)].filter((d) => cons[+d] !== saved[+d])).size;
  const days = (v: 'B' | 'R') => Object.entries(cons).filter(([, x]) => x === v).map(([d]) => +d).sort((a, b) => a - b);
  return (
    <Load q={q}>{() => (
      <>
        <p className="muted small" style={{ marginBottom: 10 }}>עריכה כמנהל על: בלי כללי ההגשה (חמישי, סופ״ש, מספר בקשות).</p>
        <ConstraintCalendar cons={cons} rules={false} special={special} y={y} m={m}
          onToggle={(d, v) => setCons((c) => { const n = { ...c }; if (v) n[d] = v; else delete n[d]; return n; })} />
        <SaveBar changes={nChanged} label={`שמור אילוצים ל${name}`} busy={busy}
          onSave={() => run(`/constraints/${ym}`, 'PUT', { employee: name, blocked: days('B'), wishes: days('R') }, `האילוצים של ${name} עודכנו`).then(q.reload).catch(() => {})} />
      </>
    )}</Load>
  );
}

function EmployeeAbsences({ name }: { name: string }) {
  const hist = useApi<AbsRow[]>(`/absences/history?employee=${encodeURIComponent(name)}`);
  const pend = useApi<Pending[]>('/absences/pending');
  const { run, busy } = useAction();
  const [ask, setAsk] = useState<{ id: string; question: string } | null>(null);
  const reload = () => { hist.reload(); pend.reload(); };
  const approve = async (id: string, force = false) => {
    try { await run(`/absences/${id}/approve`, 'POST', { force }, 'הבקשה אושרה'); setAsk(null); reload(); }
    catch (e) { if ((e as ApiError).status === 409) setAsk({ id, question: (e as ApiError).message }); }
  };
  const mine = (pend.data ?? []).filter((a) => a.employee.trim() === name);
  return (
    <>
      <h3 className="sub">ממתינות לאישור ({mine.length})</h3>
      {mine.length === 0 ? <p className="muted small" style={{ marginBottom: 14 }}>אין בקשות ממתינות.</p> : (
        <div className="cardlist" style={{ marginBottom: 14 }}>{mine.map((a) => (
          <div key={a.id} className="rcard" style={a.conflicts.length ? { boxShadow: 'inset 0 0 0 1.5px var(--danger)' } : undefined}>
            <div className="main"><b>{range(a.start_date, a.end_date)} · {a.type}</b>
              {a.notes && <div className="meta">&quot;{a.notes}&quot;</div>}
              {a.conflicts.length > 0 && <div className="meta" style={{ color: 'var(--danger)' }}><Warning size={14} weight="fill" />חפיפה עם {a.conflicts.map((c) => c.employee).join(', ')}</div>}</div>
            <button className="btn ok" disabled={busy} onClick={() => approve(a.id)}><Check size={14} />אשר</button>
            <button className="btn no" disabled={busy} onClick={() => run(`/absences/${a.id}/reject`, 'POST', undefined, 'הבקשה נדחתה').then(reload).catch(() => {})}><X size={14} />דחה</button>
          </div>
        ))}</div>
      )}
      <h3 className="sub">היסטוריה מלאה</h3>
      <Load q={hist}>{(rows) => rows.length === 0 ? <p className="muted small">אין בקשות היעדרות.</p> : (
        <div className="tbl-wrap"><table className="t"><thead><tr><th>תאריכים</th><th>סוג</th><th>סטטוס</th><th>אושר ע״י</th><th>הערה</th></tr></thead>
          <tbody>{[...rows].sort((a, b) => b.start_date.localeCompare(a.start_date)).map((a) => (
            <tr key={a.id}><td>{range(a.start_date, a.end_date)}</td><td>{a.type}</td>
              <td><span className={`badge ${a.status === 'approved' ? 'b-ok' : a.status === 'pending' ? 'b-warn' : 'b-err'}`}>{a.status === 'approved' ? 'אושר' : a.status === 'pending' ? 'ממתין' : 'נדחה'}</span></td>
              <td>{a.approved_by}</td><td className="muted">{a.notes}</td></tr>))}</tbody></table></div>
      )}</Load>
      <Modal open={!!ask} onClose={() => setAsk(null)}>
        <h2 className="sec"><Warning size={22} />יש חפיפה</h2>
        <p style={{ whiteSpace: 'pre-line', marginBottom: 16 }}>{ask?.question}</p>
        <div className="row">
          <Cta onClick={() => ask && approve(ask.id, true)}>כן, אשר למרות החפיפה</Cta>
          <button className="btn" onClick={() => setAsk(null)}>ביטול</button>
        </div>
      </Modal>
    </>
  );
}

function EmployeeManager() {
  const me = useMe();
  const people = useApi<{ name: string; type: string }[]>('/people');
  const [name, setName] = useState('');
  const [ym, setYm] = useState(ymOf(me.settings.active_year, me.settings.active_month));
  const p = people.data?.find((x) => x.name === name);
  const night = p && ['מתמחה', 'תורן חוץ'].includes(p.type);
  const daily = p && ['מתמחה', 'רופא בכיר', 'מנהל מחלקה'].includes(p.type);
  return (
    <Bezel>
      <h2 className="sec"><UserGear size={22} />ניהול אילוצים והיעדרויות לעובד/ת</h2>
      <Load q={people}>{(list) => (
        <div className="row" style={{ marginBottom: 16 }}>
          <select className="input" style={{ flex: '1 1 200px' }} value={name} onChange={(e) => setName(e.target.value)} aria-label="עובד/ת">
            <option value="">בחר/י עובד/ת</option>
            {list.map((x) => <option key={x.name} value={x.name}>{x.name} · {roleLabel(x.type)}</option>)}
          </select>
          {night && <MonthPick value={ym} onChange={setYm} />}
        </div>
      )}</Load>
      {p && !night && !daily && <Note kind="info">ל{roleLabel(p.type)} אין אילוצי תורנויות או בקשות היעדרות.</Note>}
      {night && <><h3 className="sub"><Moon size={16} /> אילוצים לתורנויות · {HEB_MONTHS[+ym.slice(5) - 1]} {ym.slice(0, 4)}</h3><EmployeeConstraints key={name + ym} name={name} ym={ym} /></>}
      {daily && <div style={{ marginTop: night ? 22 : 0 }}><h3 className="sub"><Sun size={16} /> היעדרויות מעבודה יומית</h3><EmployeeAbsences key={name} name={name} /></div>}
    </Bezel>
  );
}

export function LiveStaff() {
  const q = useApi<{ columns: string[]; rows: SRow[]; only_home: string[] }>('/staff');
  const { run, busy } = useAction();
  // Each row keeps the name it was loaded with, so a rename keeps that person's password on the server.
  const [rows, setRows] = useState<(SRow & { _original_name: string })[]>([]);
  const [home, setHome] = useState<string[]>([]);
  const [del, setDel] = useState<number | null>(null);
  const load = () => {
    if (!q.data) return;
    setRows(q.data.rows.map((r) => ({ ...r, _original_name: String(r.name ?? '') })));
    setHome(q.data.only_home);
  };
  useEffect(load, [q.data]);
  const dirty = !!q.data && (JSON.stringify(rows.map(({ _original_name, ...r }) => r)) !== JSON.stringify(q.data.rows) || JSON.stringify(home) !== JSON.stringify(q.data.only_home));
  const upd = (i: number, p: SRow) => setRows(rows.map((r, j) => (j === i ? { ...r, ...p } : r)));
  const has = (c: string) => !!q.data?.columns.includes(c);
  const save = () => {
    const names = rows.map((r) => String(r.name).trim()).filter(Boolean);
    run('/staff', 'PUT', { rows: rows.filter((r) => String(r.name).trim()), only_home: home.filter((n) => names.includes(n)) },
      'השינויים בצוות נשמרו. עובדים חדשים קיבלו סיסמה 1234.').then(q.reload).catch(() => {});
  };
  const names = rows.map((r) => String(r.name).trim()).filter(Boolean);
  const dup = names.find((n, i) => names.indexOf(n) !== i);
  return (
    <>
      <PageHead eyebrow="מנהל על" title="צוות" sub={q.data ? `${q.data.rows.length} אנשי צוות` : ''} />
      <AddEmployeeLive onDone={q.reload} />
      <Load q={q}>{() => (
        <Bezel>
          <div className="row" style={{ marginBottom: 14 }}>
            <h2 className="sec" style={{ margin: 0 }}>טבלת צוות <span className="badge b-mute">{rows.length}</span></h2>
          </div>
          <Note kind="warn">שמירה כאן כותבת את כל טבלת הצוות. שינוי שנעשה בינתיים ישירות בגיליון או ב-Streamlit יידרס.</Note>
          <div className="tbl-wrap"><table className="t">
            <thead><tr><th aria-label="מחיקה" /><th>שם</th><th>תפקיד</th><th>מחלקה</th><th>מכסה</th><th>סופ״ש</th><th>אימייל</th><th>מחלקות בניהולו/ה</th>
              <th>מוגבל/ת למחלקת הבית</th>{has('recurring_absent_days') && <th>ימי היעדרות קבועים</th>}{has('manual_schedule_only') && <th>שיבוץ ידני בלבד</th>}</tr></thead>
            <tbody>{rows.map((r, i) => {
              const nm = String(r.name ?? '');
              return (
                <tr key={i}>
                  <td><button className="iconbtn del" aria-label={`מחק את ${nm || 'השורה'}`} title="מחק עובד/ת" onClick={() => setDel(i)}><UserMinus size={16} /></button></td>
                  <td><input className="input" value={nm} onChange={(e) => {
                    const v = e.target.value;
                    if (home.includes(nm)) setHome(home.map((h) => (h === nm ? v : h)));
                    upd(i, { name: v });
                  }} style={{ minWidth: 130 }} /></td>
                  <td><select className="input" style={{ minWidth: 128 }} value={String(r.type ?? '')} onChange={(e) => upd(i, { type: e.target.value })}>
                    {!ROLES.includes(String(r.type) as never) && <option value={String(r.type ?? '')}>{String(r.type ?? '')}</option>}
                    {ROLES.map((x) => <option key={x} value={x}>{roleLabel(x)}</option>)}</select></td>
                  <td><select className="input" style={{ minWidth: 150 }} value={String(r.dept ?? '')} onChange={(e) => upd(i, { dept: e.target.value })}>
                    {!STAFF_DEPTS.includes(String(r.dept)) && <option value={String(r.dept ?? '')}>{String(r.dept ?? '') || '-'}</option>}
                    {STAFF_DEPTS.map((x) => <option key={x}>{x}</option>)}</select></td>
                  <td><input className="input" type="number" min={0} value={String(r.monthly_quota ?? '')} onChange={(e) => upd(i, { monthly_quota: e.target.value })} style={{ width: 70 }} /></td>
                  <td><input className="input" type="number" min={0} value={String(r.weekend_quota ?? '')} onChange={(e) => upd(i, { weekend_quota: e.target.value })} style={{ width: 70 }} /></td>
                  <td><input className="input" dir="ltr" value={String(r.email ?? '')} onChange={(e) => upd(i, { email: e.target.value })} style={{ minWidth: 170 }} /></td>
                  <td>{r.type === 'מנהל מחלקה'
                    ? <DeptChips value={deptsOf(r.manage_depts)} onChange={(v) => upd(i, { manage_depts: v.join(',') })} />
                    : <span className="muted small">{deptsOf(r.manage_depts).join(', ') || '-'}</span>}</td>
                  <td style={{ textAlign: 'center' }}><input type="checkbox" aria-label={`${nm} מוגבל/ת למחלקת הבית`} checked={home.includes(nm)}
                    onChange={(e) => setHome(e.target.checked ? [...home, nm] : home.filter((h) => h !== nm))} style={{ width: 18, height: 18, accentColor: 'var(--accent)' }} /></td>
                  {has('recurring_absent_days') && <td><input className="input" value={String(r.recurring_absent_days ?? '')} placeholder="למשל ד,ה" onChange={(e) => upd(i, { recurring_absent_days: e.target.value })} style={{ width: 80 }} /></td>}
                  {has('manual_schedule_only') && <td style={{ textAlign: 'center' }}><input type="checkbox" aria-label={`${nm} שיבוץ ידני בלבד`} checked={truthy(r.manual_schedule_only)}
                    onChange={(e) => upd(i, { manual_schedule_only: e.target.checked ? 'True' : 'False' })} style={{ width: 18, height: 18, accentColor: 'var(--accent)' }} /></td>}
                </tr>
              );
            })}</tbody>
          </table></div>
          {dup && <Note kind="err">השם {dup} מופיע פעמיים בטבלה.</Note>}
          <div className="row" style={{ marginTop: 16 }}>
            <Cta icon={<FloppyDisk size={16} />} disabled={!dirty || busy || !!dup} onClick={save}>שמור שינויים בצוות</Cta>
            {dirty && <><span className="muted small">יש שינויים שלא נשמרו</span><button className="btn" onClick={load}>בטל שינויים</button></>}
          </div>
          <Modal open={del !== null} onClose={() => setDel(null)}>
            {del !== null && rows[del] && <>
              <h2 className="sec"><UserMinus size={22} />להסיר את {String(rows[del].name) || 'השורה'} מהצוות?</h2>
              <p className="muted" style={{ marginBottom: 12 }}>העובד/ת לא יוכל/תוכל להתחבר ולא יופיע/תופיע בשיבוצים הבאים. תורנויות, אילוצים והיעדרויות שכבר רשומים נשארים בגיליון.</p>
              <Note kind="info">ההסרה נשמרת רק בלחיצה על "שמור שינויים בצוות".</Note>
              <div className="row" style={{ marginTop: 16 }}>
                <Cta variant="danger" icon={<Trash size={16} />} onClick={() => { setRows(rows.filter((_, j) => j !== del)); setDel(null); }}>הסר מהטבלה</Cta>
                <button className="btn" onClick={() => setDel(null)}>ביטול</button>
              </div>
            </>}
          </Modal>
        </Bezel>
      )}</Load>
      <EmployeeManager />
    </>
  );
}

// ── דוחות וניהול ─────────────────────────────────────────────────────────────
interface Report {
  submissions: { total: number; submitted: number; pending: number; rows: { name: string; type: string; submitted: boolean; blocks: number; wishes: number }[] };
  shift_counts: { employee: string; sh: number; pn: number; fri: number }[];
  problems: { generated_at: string | null; month: string | null; headline: { critical: number; warning: number } | null; rows: { severity: string; problem_type: string; description: string }[] };
  fairness: { name: string; wed: number; thu: number; friday_morning: number; net: number }[];
}
const scoreColor = (s: number) => (s >= 1 ? 'var(--W)' : s <= -2 ? 'var(--B)' : s < 0 ? 'var(--S)' : '#F4F6F8');
const SERIES = [{ k: 'sh', l: 'תורנות שיקום', c: 'var(--chart1)' }, { k: 'pn', l: 'תורנות פנג״ר', c: 'var(--chart3)' }, { k: 'fri', l: 'שישי בוקר', c: 'var(--chart2)' }] as const;

interface Analytics {
  empty: boolean; kpi?: { logins: number; unique_users: number; mobile_pct: number; avg_submits_per_month: number };
  per_user?: { user: string; logins: number; submits: number; swap_searches: number; swap_requests: number; device: string }[];
  blocking?: { employee: string; blocks: number; pct: number; level: string }[];
  tab_entries?: Record<string, number>; tab_avg_seconds?: Record<string, number>;
  logins_by_hour?: number[]; devices?: Record<string, number>; reload_suspects?: string[]; submits_by_day?: number[];
}
const DEVICE: Record<string, string> = { mobile: 'טלפון', desktop: 'מחשב', unknown: 'לא ידוע' };

/** Streamlit "📈 ניתוח שימוש במערכת", sections A–I, from analytics_log. Loaded only when opened. */
function AnalyticsLive({ ym }: { ym: string }) {
  const q = useApi<Analytics>(`/reports/analytics/${ym}`);
  const [tab, setTab] = useState<'use' | 'time'>('use');
  return (
    <Load q={q}>{(a) => a.empty ? <p className="muted">עדיין אין נתוני שימוש.</p> : (
      <>
        <div className="kpis">
          <Kpi k="כניסות" v={a.kpi!.logins} /><Kpi k="משתמשים ייחודיים" v={a.kpi!.unique_users} />
          <Kpi k="מהטלפון" v={`${a.kpi!.mobile_pct}%`} small={`מחשב ${100 - a.kpi!.mobile_pct}%`} />
          <Kpi k="הגשות בממוצע לחודש" v={Math.round(a.kpi!.avg_submits_per_month * 10) / 10} />
        </div>
        <div className="cols2" style={{ gap: 24 }}>
          <div><h3 className="sub">כניסות לפי שעה</h3>
            <VBars values={a.logins_by_hour!} labels={a.logins_by_hour!.map((_, i) => (i % 3 === 0 ? String(i) : ''))} fmt={(v, i) => `${String(i).padStart(2, '0')}:00 · ${v} כניסות`} /></div>
          <div><h3 className="sub">יום בחודש שבו מגישים אילוצים</h3>
            <VBars values={a.submits_by_day!} labels={a.submits_by_day!.map((_, i) => (i % 5 === 0 ? String(i + 1) : ''))} fmt={(v, i) => `${i + 1} בחודש · ${v} הגשות`} /></div>
          <div style={{ marginTop: 20 }}>
            <div className="row" style={{ marginBottom: 10 }}><h3 className="sub" style={{ margin: 0 }}>שימוש בלשוניות</h3><span className="grow" />
              <PillSeg value={tab} onChange={setTab} options={[{ v: 'use', l: 'כניסות' }, { v: 'time', l: 'זמן ממוצע' }]} /></div>
            {tab === 'use'
              ? <HBars rows={Object.entries(a.tab_entries!).sort((x, y) => y[1] - x[1])} unit="כניסות" />
              : <HBars rows={Object.entries(a.tab_avg_seconds!).sort((x, y) => y[1] - x[1])} unit="שניות" />}
            <h3 className="sub" style={{ marginTop: 18 }}>סוג מכשיר</h3>
            <HBars rows={Object.entries(a.devices!).map(([k, v]) => [DEVICE[k] ?? k, v] as [string, number])} unit="כניסות" />
          </div>
          <div style={{ marginTop: 20 }}>
            <h3 className="sub">פעילות לפי משתמש/ת</h3>
            <div className="tbl-wrap" style={{ marginBottom: 18 }}><table className="t"><thead><tr><th>משתמש/ת</th><th>כניסות</th><th>הגשות</th><th>חיפושי החלפה</th><th>בקשות החלפה</th><th>מכשיר עיקרי</th></tr></thead>
              <tbody>{[...a.per_user!].sort((x, y) => y.logins - x.logins).map((u) => <tr key={u.user}><td>{u.user}</td><td className="num">{u.logins}</td><td className="num">{u.submits}</td>
                <td className="num">{u.swap_searches}</td><td className="num">{u.swap_requests}</td><td>{DEVICE[u.device] ?? u.device}</td></tr>)}</tbody></table></div>
            <h3 className="sub">שיעור חסימה לפי עובד/ת ({HEB_MONTHS[+ym.slice(5) - 1]})</h3>
            {a.blocking!.length === 0 ? <p className="muted small">אין חסימות בחודש זה.</p> : (
              <div className="tbl-wrap"><table className="t"><thead><tr><th>עובד/ת</th><th>חסימות</th><th>% מהחודש</th><th>סטטוס</th></tr></thead>
                <tbody>{a.blocking!.map((b) => <tr key={b.employee}><td>{b.employee}</td><td className="num">{b.blocks}</td><td className="num">{b.pct}%</td>
                  <td>{b.level === 'red' ? <span className="badge b-err"><WarningOctagon size={12} weight="fill" />גבוה</span> : b.level === 'yellow' ? <span className="badge b-warn"><Warning size={12} weight="fill" />בינוני</span> : <span className="badge b-ok">תקין</span>}</td></tr>)}</tbody></table></div>
            )}
            <h3 className="sub" style={{ marginTop: 18 }}>רענונים אפשריים (שתי כניסות בתוך 5 דקות)</h3>
            {a.reload_suspects!.length === 0 ? <p className="muted small">אין.</p> : <p className="small">{a.reload_suspects!.join(', ')}</p>}
          </div>
        </div>
      </>
    )}</Load>
  );
}

export function LiveReports() {
  const me = useMe();
  const [ym, setYm] = useState(ymOf(me.settings.active_year, me.settings.active_month));
  const [y, m] = ym.split('-').map(Number);
  const q = useApi<Report>(`/reports/${ym}`);
  const { bind, node } = useTip();
  const scan = useAction();
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
                  <div className="row" style={{ marginBottom: 8 }}>
                    <h2 className="sec" style={{ margin: 0 }}><Warning size={22} />דוח בעיות צפויות</h2><span className="grow" />
                    <button className="btn" disabled={scan.busy} onClick={() => scan.run(`/reports/${ym}/scan`, 'POST', undefined, 'הסריקה הסתיימה').then(q.reload).catch(() => {})}>
                      <ArrowsClockwise size={14} />{scan.busy ? 'סורק... (עד דקה)' : `הרץ סריקה ל${HEB_MONTHS[m - 1]}`}</button>
                  </div>
                  <p className="muted small" style={{ marginBottom: 10 }}>סריקה אחרונה: {r.problems.generated_at ?? 'אין'}{r.problems.month ? ` · לחודש ${HEB_MONTHS[+r.problems.month.slice(5) - 1]}` : ''}</p>
                  {r.problems.headline && (r.problems.headline.critical > 0 || r.problems.headline.warning > 0) && (
                    <Note kind="warn"><b>ימים קשים לאיוש:</b>{r.problems.headline.critical > 0 && ` ${r.problems.headline.critical} ימים קריטיים (50%+ חסמו)`}{r.problems.headline.critical > 0 && r.problems.headline.warning > 0 && ' ·'}{r.problems.headline.warning > 0 && ` ${r.problems.headline.warning} ימים בסיכון (30%+ חסמו)`}</Note>
                  )}
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
      <Expander title="ניתוח שימוש במערכת" icon={<ChartLineUp size={20} />}><AnalyticsLive ym={ym} /></Expander>
    </>
  );
}
