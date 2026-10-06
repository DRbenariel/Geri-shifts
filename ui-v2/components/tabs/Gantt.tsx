'use client';
import { useEffect, useState } from 'react';
import { CheckCircle, DownloadSimple, FloppyDisk, Lightning, LockSimple, LockSimpleOpen } from '@phosphor-icons/react';
import { useStore } from '@/lib/store';
import { DAILY_DEPTS, HEB_MONTHS, type Role, type Rotation } from '@/lib/mock';
import { Bezel, Cta, Note, PageHead, Person } from '../ui';
import { MONTHS12 } from './Work';

const ORDER: Role[] = ['מנהל מחלקה', 'רופא בכיר', 'מתמחה'];

export default function Gantt() {
  const { db, mutate, toast } = useStore();
  const [ym, setYm] = useState('2026-11');
  const mo = MONTHS12.find((x) => x.v === ym)!;
  const people = db.staff.filter((s) => ORDER.includes(s.type)).sort((a, b) => ORDER.indexOf(a.type) - ORDER.indexOf(b.type));
  const load = () => Object.fromEntries(people.map((p) => { const r = db.rotation.find((x) => x.employee === p.name && x.year_month === ym); return [p.name, { dept: r?.daily_dept ?? '', side: r?.side ?? '' }]; }));
  const [form, setForm] = useState<Record<string, { dept: string; side: string }>>(load);
  const [errors, setErrors] = useState<string[]>([]);
  useEffect(() => { setForm(load()); setErrors([]); }, [ym]); // eslint-disable-line react-hooks/exhaustive-deps

  const isActive = db.settings.daily_active_month === mo.m;
  const open = db.settings.daily_requests_open;
  const manualOnly = people.filter((p) => p.manual_schedule_only);
  const counts = DAILY_DEPTS.map((d) => [d, Object.values(form).filter((v) => v.dept === d).length] as const);

  const save = () => {
    const errs = Object.entries(form).filter(([, v]) => v.dept === 'פנימית גריאטרית' && !v.side).map(([n]) => `${n}: בפנימית חובה לבחור צד`);
    setErrors(errs);
    if (errs.length) return toast('השמירה נחסמה: יש שגיאות בטופס', 'err');
    mutate((x) => {
      x.rotation = x.rotation.filter((r) => !(r.year_month === ym && people.some((p) => p.name === r.employee)));
      Object.entries(form).forEach(([employee, v]) => { if (v.dept) x.rotation.push({ employee, year_month: ym, daily_dept: v.dept, side: (v.side as Rotation['side']) }); });
    });
    toast(`השיבוץ ל${mo.l} נשמר. בקשות היעדרות פתוחות הועברו למחלקה החדשה.`);
  };

  return (
    <>
      <PageHead eyebrow="שיוך עובדים למחלקות" title="גאנט חודשי"
        actions={<Cta variant="light" icon={<DownloadSimple size={16} />} onClick={() => toast(`Excel לכל המחלקות הורד: ${mo.l}, גיליון לכל מחלקה, A4 לרוחב`)}>Excel כל המחלקות</Cta>} />
      <Bezel>
        <div className="row">
          <div className="field" style={{ margin: 0, minWidth: 220 }}>
            <label>חודש לתכנון ועריכה</label>
            <select className="input" value={ym} onChange={(e) => setYm(e.target.value)}>{MONTHS12.map((x) => <option key={x.v} value={x.v}>{x.l}</option>)}</select>
          </div>
          <span className="grow" />
          {isActive
            ? <span className="badge b-ok" style={{ fontSize: 14, padding: '6px 14px' }}><CheckCircle size={16} weight="fill" />זהו החודש הפעיל</span>
            : <Cta variant="teal" icon={<Lightning size={16} />} onClick={() => { mutate((x) => { x.settings.daily_active_month = mo.m; x.settings.daily_requests_open = true; }); toast(`${mo.l} הוא עכשיו החודש הפעיל, וההגשות נפתחו`); }}>הפוך את {HEB_MONTHS[mo.m - 1]} לחודש פעיל</Cta>}
          {isActive && (
            <Cta variant={open ? 'light' : 'teal'} icon={open ? <LockSimple size={16} /> : <LockSimpleOpen size={16} />}
              onClick={() => { mutate((x) => { x.settings.daily_requests_open = !open; }); toast(open ? 'הגשת בקשות היעדרות נסגרה' : 'הגשת בקשות היעדרות נפתחה', 'info'); }}>
              {open ? 'סגור הגשות' : 'פתח הגשות'}
            </Cta>
          )}
        </div>
      </Bezel>

      {manualOnly.length > 0 && <Note kind="warn">סידור ידני בלבד: {manualOnly.map((p) => p.name).join(', ')}. ימי העבודה שלהם לא יתמלאו אוטומטית.</Note>}
      {errors.length > 0 && <Note kind="err">{errors.map((e) => <div key={e}>{e}</div>)}</Note>}

      <Bezel>
        <h2 className="sec">שיוך ל{mo.l}</h2>
        <div className="tbl-wrap"><table className="t">
          <thead><tr><th>עובד/ת</th><th>מחלקה</th><th>צד (פנימית)</th></tr></thead>
          <tbody>
            {people.map((p) => {
              const v = form[p.name] ?? { dept: '', side: '' };
              const bad = v.dept === 'פנימית גריאטרית' && !v.side && errors.length > 0;
              const depts = p.type === 'מנהל מחלקה' ? p.manage_depts : DAILY_DEPTS;
              return (
                <tr key={p.name}>
                  <td><Person name={p.name} role={p.type} /></td>
                  <td><select className="input" value={v.dept} onChange={(e) => setForm({ ...form, [p.name]: { dept: e.target.value, side: e.target.value === 'פנימית גריאטרית' ? v.side : '' } })}>
                    <option value="">לא שובץ</option>{depts.map((d) => <option key={d}>{d}</option>)}</select></td>
                  <td><select className="input" value={v.side} disabled={v.dept !== 'פנימית גריאטרית'} style={bad ? { boxShadow: 'inset 0 0 0 1.5px var(--danger)' } : undefined}
                    onChange={(e) => setForm({ ...form, [p.name]: { ...v, side: e.target.value } })}>
                    <option value="">-</option><option value="ורוד">צד ורוד</option><option value="כחול">צד כחול</option></select></td>
                </tr>
              );
            })}
          </tbody>
        </table></div>
        <div className="row" style={{ marginTop: 18 }}>
          <Cta icon={<FloppyDisk size={16} />} onClick={save}>שמור שיבוץ ל{HEB_MONTHS[mo.m - 1]}</Cta>
          <span className="grow" />
          {counts.map(([d, c]) => <span key={d} className="chip">{d}: <b>{c}</b></span>)}
        </div>
      </Bezel>
    </>
  );
}
