'use client';
import { useMemo, useState } from 'react';
import { ArrowsClockwise, ChartLineUp, Info, Robot, Table, Warning, WarningOctagon } from '@phosphor-icons/react';
import { useStore } from '@/lib/store';
import { HEB_MONTHS, MONTH, YEAR, analytics, dailyReport, dowOf } from '@/lib/mock';
import { Bezel, Expander, PageHead, PillSeg, useTip } from '../ui';

function Kpi({ k, v, small, icon }: { k: string; v: string | number; small?: string; icon?: React.ReactNode }) {
  return <Bezel tight><div className="kpi"><div className="k">{icon}{k}</div><div className="v">{v}{small && <small> {small}</small>}</div></div></Bezel>;
}

/** Horizontal stacked bars, 2 series (validated palette: #0D9488 / #D97706). */
function ShiftBars({ data }: { data: { name: string; reg: number; fri: number }[] }) {
  const { bind, node } = useTip();
  const [asTable, setAsTable] = useState(false);
  const max = Math.max(...data.map((d) => d.reg + d.fri), 1);
  return (
    <>
      <div className="row" style={{ marginBottom: 12 }}>
        <span className="row small"><span style={{ width: 12, height: 12, borderRadius: 3, background: 'var(--chart1)' }} />משמרות לילה</span>
        <span className="row small"><span style={{ width: 12, height: 12, borderRadius: 3, background: 'var(--chart2)' }} />שישי בוקר</span>
        <span className="grow" />
        <button className="btn" onClick={() => setAsTable(!asTable)}><Table size={14} />{asTable ? 'תרשים' : 'טבלה'}</button>
      </div>
      {asTable ? (
        <table className="t"><thead><tr><th>עובד/ת</th><th>לילה</th><th>שישי בוקר</th><th>סה״כ</th></tr></thead>
          <tbody>{data.map((d) => <tr key={d.name}><td>{d.name}</td><td className="num">{d.reg}</td><td className="num">{d.fri}</td><td className="num">{d.reg + d.fri}</td></tr>)}</tbody></table>
      ) : (
        <div className="bars">
          {data.map((d) => (
            <div key={d.name} className="bar-row">
              <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{d.name}</span>
              <div className="bar-track">
                {d.reg > 0 && <div className="bar-seg" style={{ width: `${(d.reg / max) * 100}%`, background: 'var(--chart1)' }} {...bind(`${d.name}: ${d.reg} משמרות לילה`)} />}
                {d.fri > 0 && <div className="bar-seg" style={{ width: `${(d.fri / max) * 100}%`, background: 'var(--chart2)' }} {...bind(`${d.name}: ${d.fri} שישי בוקר`)} />}
              </div>
              <span className="num" style={{ fontWeight: 700 }}>{d.reg + d.fri}</span>
            </div>
          ))}
        </div>
      )}
      {node}
    </>
  );
}

function VBars({ values, labels, fmt }: { values: number[]; labels: string[]; fmt: (v: number, i: number) => string }) {
  const { bind, node } = useTip();
  const max = Math.max(...values, 1);
  return (
    <>
      <div className="vbars" dir="ltr">{values.map((v, i) => <div key={i} className="vbar" style={{ height: `${(v / max) * 100}%` }} {...bind(fmt(v, i))} />)}</div>
      <div className="axis" dir="ltr">{labels.map((l, i) => <span key={i}>{l}</span>)}</div>
      {node}
    </>
  );
}

function HBars({ rows, unit }: { rows: [string, number][]; unit: string }) {
  const { bind, node } = useTip();
  const max = Math.max(...rows.map((r) => r[1]), 1);
  return (
    <div className="bars">
      {rows.map(([k, v]) => (
        <div key={k} className="bar-row"><span>{k}</span>
          <div className="bar-track"><div className="bar-seg" style={{ width: `${(v / max) * 100}%`, background: 'var(--chart1)' }} {...bind(`${k}: ${v} ${unit}`)} /></div>
          <span className="num">{v}</span></div>
      ))}
      {node}
    </div>
  );
}

const SEV = { 'קריטי': { c: 'b-err', I: WarningOctagon }, 'אזהרה': { c: 'b-warn', I: Warning }, 'מידע': { c: 'b-info', I: Info } } as const;

export default function Reports() {
  const { db, toast } = useStore();
  const [scanning, setScanning] = useState(false);
  const [scannedAt, setScannedAt] = useState('היום 10:00 (GitHub Actions)');
  const [aTab, setATab] = useState<'use' | 'time'>('use');
  const pool = db.staff.filter((s) => s.type === 'מתמחה' || s.type === 'תורן חוץ');
  const submitted = pool.filter((p) => db.requests.some((r) => r.employee === p.name));
  const shiftData = useMemo(() => pool.map((p) => ({
    name: p.name,
    reg: db.schedule.filter((r) => r.employee === p.name && !r.dept.startsWith('שישי')).length,
    fri: db.schedule.filter((r) => r.employee === p.name && r.dept.startsWith('שישי')).length,
  })).sort((a, b) => b.reg + b.fri - (a.reg + a.fri)), [db, pool]);
  const fairness = pool.filter((p) => p.type === 'מתמחה').map((p) => {
    const mine = db.schedule.filter((r) => r.employee === p.name);
    const wd = (w: number) => mine.filter((r) => !r.dept.startsWith('שישי') && dowOf(YEAR, MONTH, +r.date.slice(8)) === w).length;
    const fri = mine.filter((r) => r.dept.startsWith('שישי')).length;
    return { name: p.name, wed: wd(3), thu: wd(4), fri, score: wd(3) - (wd(4) + fri) };
  });
  const crit = new Set(dailyReport.filter((r) => r.severity === 'קריטי').map((r) => r.description.slice(0, 5))).size;
  const warn = dailyReport.filter((r) => r.severity === 'אזהרה').length;
  const groups = [...new Set(dailyReport.map((r) => r.problem_type))];
  const scoreColor = (s: number) => (s >= 1 ? 'var(--W)' : s <= -2 ? 'var(--B)' : s < 0 ? 'var(--S)' : '#F4F6F8');

  return (
    <>
      <PageHead eyebrow={`${HEB_MONTHS[MONTH - 1]} ${YEAR}`} title="דוחות וניהול" sub="לוח בקרה חודשי" />
      <div className="kpis">
        <Kpi k="סה״כ צוות תורנויות" v={pool.length} />
        <Kpi k="הגישו אילוצים" v={submitted.length} small={`מתוך ${pool.length}`} />
        <Kpi k="ממתינים להגשה" v={pool.length - submitted.length} />
        <Kpi k="בעיות קריטיות" v={crit} icon={<WarningOctagon size={14} weight="fill" color="var(--danger)" />} />
      </div>

      <div className="split">
        <div>
          <Bezel>
            <h2 className="sec">ספירת תורנויות</h2>
            <ShiftBars data={shiftData} />
          </Bezel>
          <Bezel>
            <div className="row" style={{ marginBottom: 12 }}>
              <h2 className="sec" style={{ margin: 0 }}><Robot size={22} />דוח בעיות צפויות</h2>
              <span className="grow" />
              <button className="btn" disabled={scanning} onClick={() => { setScanning(true); setTimeout(() => { setScanning(false); setScannedAt('עכשיו'); toast('הסריקה הסתיימה. הגיליון daily_report עודכן.'); }, 1400); }}>
                <ArrowsClockwise size={14} className={scanning ? 'spin' : ''} />{scanning ? 'סורק...' : 'הרץ סריקה עכשיו'}</button>
            </div>
            <div className="row" style={{ marginBottom: 16 }}>
              <span className="badge b-err" style={{ fontSize: 14, padding: '6px 12px' }}><WarningOctagon size={15} weight="fill" />{crit} ימים קריטיים</span>
              <span className="badge b-warn" style={{ fontSize: 14, padding: '6px 12px' }}><Warning size={15} weight="fill" />{warn} אזהרות</span>
              <span className="muted small">סריקה אחרונה: {scannedAt}</span>
            </div>
            {groups.map((g) => (
              <div key={g} style={{ marginBottom: 14 }}>
                <h3 className="sub">{g}</h3>
                {dailyReport.filter((r) => r.problem_type === g).map((r, i) => { const s = SEV[r.severity as keyof typeof SEV]; return (
                  <div key={i} className="row" style={{ alignItems: 'flex-start', marginBottom: 6, flexWrap: 'nowrap' }}>
                    <span className={`badge ${s.c}`}><s.I size={12} weight="fill" />{r.severity}</span><span className="small">{r.description}</span>
                  </div>); })}
              </div>
            ))}
          </Bezel>
        </div>
        <div>
          <Bezel>
            <h2 className="sec">סטטוס הגשות</h2>
            <table className="t"><tbody>{pool.map((p) => { const ok = submitted.includes(p); return (
              <tr key={p.name}><td>{p.name}</td><td style={{ textAlign: 'left' }}><span className={`badge ${ok ? 'b-ok' : 'b-err'}`}>{ok ? 'הוגש' : 'טרם הוגש'}</span></td></tr>); })}</tbody></table>
          </Bezel>
          <Bezel>
            <h2 className="sec">מעקב הוגנות</h2>
            <p className="muted small" style={{ marginBottom: 10 }}>ציון = רביעי פחות (חמישי + שישי בוקר)</p>
            <table className="t"><thead><tr><th>מתמחה</th><th>ד׳</th><th>ה׳</th><th>ו׳ בוקר</th><th>ציון</th></tr></thead>
              <tbody>{fairness.map((f) => <tr key={f.name}><td>{f.name}</td><td className="num">{f.wed}</td><td className="num">{f.thu}</td><td className="num">{f.fri}</td>
                <td className="num" style={{ background: scoreColor(f.score), borderRadius: 8, textAlign: 'center' }}>{f.score > 0 ? '+' : ''}{f.score}</td></tr>)}</tbody></table>
          </Bezel>
        </div>
      </div>

      <Expander title="ניתוח שימוש במערכת" icon={<ChartLineUp size={20} />} badge={<span className="badge b-mute">נתוני דמו</span>}>
        <div className="kpis">
          <Kpi k="כניסות" v={analytics.logins} /><Kpi k="משתמשים ייחודיים" v={analytics.uniqueUsers} />
          <Kpi k="מהטלפון" v={`${analytics.mobilePct}%`} small={`מחשב ${100 - analytics.mobilePct}%`} /><Kpi k="הגשות בממוצע לחודש" v={analytics.avgSubmissions} />
        </div>
        <div className="cols2" style={{ gap: 24 }}>
          <div><h3 className="sub">כניסות לפי שעה</h3>
            <VBars values={analytics.byHour} labels={analytics.byHour.map((_, i) => (i % 3 === 0 ? String(i) : ''))} fmt={(v, i) => `${String(i).padStart(2, '0')}:00 · ${v} כניסות`} /></div>
          <div><h3 className="sub">יום בחודש שבו מגישים אילוצים</h3>
            <VBars values={analytics.submitDay} labels={analytics.submitDay.map((_, i) => String(i + 1))} fmt={(v, i) => `${i + 1} בחודש · ${v} הגשות`} /></div>
          <div style={{ marginTop: 20 }}>
            <div className="row" style={{ marginBottom: 10 }}><h3 className="sub" style={{ margin: 0 }}>שימוש בלשוניות</h3><span className="grow" />
              <PillSeg value={aTab} onChange={setATab} options={[{ v: 'use', l: 'כניסות' }, { v: 'time', l: 'זמן ממוצע' }]} /></div>
            {aTab === 'use' ? <HBars rows={analytics.tabs} unit="כניסות" /> : <HBars rows={analytics.tabSeconds} unit="שניות" />}
          </div>
          <div style={{ marginTop: 20 }}>
            <h3 className="sub">פעילות לפי משתמש/ת</h3>
            <table className="t" style={{ marginBottom: 18 }}><thead><tr><th>משתמש/ת</th><th>כניסות</th><th>הגשות</th><th>מכשיר עיקרי</th></tr></thead>
              <tbody>{db.staff.slice(0, 8).map((s, i) => <tr key={s.name}><td>{s.name}</td><td className="num">{41 - i * 4}</td><td className="num">{s.type === 'מתמחה' ? 2 - (i % 2) : 0}</td><td>{i % 3 === 2 ? 'מחשב' : 'טלפון'}</td></tr>)}</tbody></table>
            <h3 className="sub">שיעור חסימות לפי עובד/ת</h3>
            <table className="t"><tbody>{pool.filter((p) => submitted.includes(p)).map((p, i) => { const rate = Math.round((db.requests.filter((r) => r.employee === p.name && r.status === 'אילוץ').length / 30) * 100 + i * 7) % 75; return (
              <tr key={p.name}><td>{p.name}</td><td className="num">{rate}%</td><td>{rate > 60 ? <span className="badge b-err">גבוה</span> : rate > 40 ? <span className="badge b-warn">בינוני</span> : null}</td></tr>); })}</tbody></table>
            <h3 className="sub" style={{ marginTop: 18 }}>רענונים אפשריים (2 כניסות בתוך 5 דקות)</h3>
            <table className="t"><tbody>{analytics.refreshes.map(([n, c]) => <tr key={n}><td>{n}</td><td className="num">{c}</td></tr>)}</tbody></table>
          </div>
        </div>
      </Expander>
    </>
  );
}
