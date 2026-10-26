'use client';
import { useEffect, useState } from 'react';
import { ArrowsClockwise, Check, Coffee, FileArrowUp, MagicWand, Moon, Prohibit, Question, Star, Sun, X } from '@phosphor-icons/react';
import { useApi, type NightCal, type NightSlot } from '@/lib/api';
import { DOW_FULL, HEB_MONTHS, dowOf } from '@/lib/mock';
import { handoff } from '@/lib/logic';
import { monthDays, useMe, ymOf } from '@/lib/store';
import { Bezel, Cta, Kpi, Modal, Note, PageHead, PillSeg } from '../ui';
import { Load, MonthPick, dmy, useAction } from './common';

const ORDER = ['שיקום', 'פנימית גריאטרית', 'שישי בוקר - שיקום (1)', 'שישי בוקר - שיקום (2)', 'שישי בוקר - פנימית (1)', 'שישי בוקר - פנימית (2)'];
const kind = (dept: string) => (dept.startsWith('שישי') ? 'fr' : dept === 'שיקום' ? 'sh' : 'pn');
const short = (dept: string) => (dept.startsWith('שישי') ? 'שישי' : dept === 'שיקום' ? 'שיקום' : 'פנימית');

function Month({ y, m, cell }: { y: number; m: number; cell: (d: number, date: string) => React.ReactNode }) {
  const lead = dowOf(y, m, 1);
  return (
    <div className="cal">
      {DOW_FULL.map((h, i) => <div key={h} className={`h ${i >= 5 ? 'we' : ''}`}>{h}</div>)}
      {Array.from({ length: lead }, (_, i) => <div key={'b' + i} className="day blank" />)}
      {monthDays(y, m).map((d) => cell(d, ymOf(y, m) + `-${String(d).padStart(2, '0')}`))}
    </div>
  );
}

function AdminNight() {
  const me = useMe();
  const [ym, setYm] = useState(ymOf(me.settings.active_year, me.settings.active_month));
  const [y, m] = ym.split('-').map(Number);
  const q = useApi<NightCal>(`/night/${ym}`);
  const swaps = useApi<{ index: number; requester: string; requester_date: string; requester_dept: string; candidate: string; candidate_date: string; candidate_dept: string; swap_type: string }[]>('/swaps/pending');
  const { run, busy } = useAction();
  const [summary, setSummary] = useState<string[]>([]);
  const [askAuto, setAskAuto] = useState<null | boolean>(null);
  const auto = async (weekends: boolean) => {
    setAskAuto(null);
    try {
      const r = await run<{ filled: number; total: number; messages: { text: string }[] }>(`/night/${ym}/auto`, 'POST', { only_weekends: weekends });
      if (r) { setSummary([`שובצו ${r.filled}/${r.total} משמרות`, ...r.messages.map((x) => x.text)]); q.reload(); }
    } catch { /* toast shown */ }
  };
  return (
    <>
      <PageHead eyebrow={`${HEB_MONTHS[m - 1]} ${y}`} title="סידור תורנויות"
        actions={<>
          <MonthPick value={ym} onChange={setYm} />
          <Cta variant="light" icon={<FileArrowUp size={16} />} disabled={busy} onClick={() => run(`/night/${ym}/export-sheet`, 'POST', undefined, 'הגיליון Schedule_Export עודכן').catch(() => {})}>עדכן Schedule_Export</Cta>
        </>} />
      <Load q={q}>{(cal) => {
        const empty = Object.entries(cal.slots).flatMap(([d, rows]) => rows.filter((r) => r.employee === '---').map((r) => ({ d, r })));
        const filled = Object.values(cal.slots).flat().filter((r) => r.employee !== '---').length;
        return (
          <div className="split">
            <div>
              {empty.length > 0 && (
                <Bezel>
                  <Note kind="err"><b>{empty.length} משמרות לא שובצו.</b></Note>
                  <div className="cardlist">
                    {empty.map(({ d, r }) => <div key={d + r.dept} className="rcard"><div className="main"><b>{dmy(d)} · {r.dept}</b><div className="meta"><Question size={13} />{r.empty_reason || 'ללא סיבה רשומה'}</div></div></div>)}
                  </div>
                </Bezel>
              )}
              <Bezel>
                <div className="row" style={{ marginBottom: 12 }}>
                  <h2 className="sec" style={{ margin: 0 }}>לוח החודש</h2><span className="grow" /><span className="muted small">{filled} משמרות משובצות</span>
                </div>
                <div className="row small muted" style={{ marginBottom: 12 }}>
                  <span className="slot sh">שיקום</span><span className="slot pn">פנימית</span><span className="slot fr">שישי בוקר</span><span className="slot empty">חסר</span>
                  <span className="mark"><Prohibit size={12} />חסימה</span><span className="mark"><Star size={12} weight="fill" />בקשה</span>
                </div>
                {cal.availability && !cal.availability.shown && <Note kind="info">לוח הזמינות היומי יוצג כשכל העובדים יגישו אילוצים.</Note>}
                <Month y={y} m={m} cell={(d, date) => {
                  const rows = [...(cal.slots[date] ?? [])].sort((a, b) => ORDER.indexOf(a.dept) - ORDER.indexOf(b.dept));
                  const reqs = cal.requests?.[date] ?? [];
                  const sp = cal.special_days.find((s) => s.date === date);
                  const bl = reqs.filter((r) => r.status === 'אילוץ').map((r) => r.employee);
                  const wi = reqs.filter((r) => r.status === 'בקשה').map((r) => r.employee);
                  const av = cal.availability?.shown ? cal.availability.available[date] ?? [] : null;
                  return (
                    <div key={d} className={`day ${dowOf(y, m, d) >= 5 ? 'we' : ''}`}>
                      <span className="num">{d}</span>
                      {sp && <span className="sp" title={sp.day_type}>{sp.description}</span>}
                      {rows.map((r) => r.employee === '---'
                        ? <span key={r.dept} className="slot empty" title={`${r.dept}: ${r.empty_reason}`}><Question size={11} />{short(r.dept)} חסר</span>
                        : <span key={r.dept} className={`slot ${kind(r.dept)}`} title={`${r.dept}: ${r.employee}${r.is_manual ? ' (ידני)' : ''}`}>{r.employee.trim()}</span>)}
                      {(bl.length > 0 || wi.length > 0) && (
                        <span className="who hide-m">
                          {bl.map((e) => <span key={'b' + e} className="b"><Prohibit size={10} weight="bold" />{e}</span>)}
                          {wi.map((e) => <span key={'r' + e} className="r"><Star size={10} weight="fill" />{e}</span>)}
                        </span>
                      )}
                      {av && av.length > 0 && <span className="who hide-m"><span title={av.join(', ')}>✅ {av.length} זמינים</span></span>}
                      {(bl.length > 0 || wi.length > 0) && (
                        <span className="who-m mob-only">{bl.length > 0 && <span className="b"><Prohibit size={9} weight="bold" />{bl.length}</span>}{wi.length > 0 && <span className="r"><Star size={9} weight="fill" />{wi.length}</span>}</span>
                      )}
                    </div>
                  );
                }} />
              </Bezel>
              <Bezel>
                <h2 className="sec"><ArrowsClockwise size={22} />בקשות החלפה ממתינות</h2>
                <Load q={swaps}>{(list) => list.length === 0 ? <p className="muted">אין בקשות ממתינות.</p> : (
                  <div className="cardlist">
                    {list.map((s) => (
                      <div key={s.index} className="rcard">
                        <div className="main"><b>{s.requester}: {dmy(s.requester_date)} {s.requester_dept} ← {s.candidate}</b>
                          <div className="meta">{s.swap_type === 'full' ? `בתמורה: ${s.candidate_date ? dmy(s.candidate_date) : ''} ${s.candidate_dept}` : s.swap_type === 'chain' ? 'החלפה משולשת' : 'כיסוי חד-צדדי'}</div></div>
                        <button className="btn ok" disabled={busy} onClick={() => run(`/swaps/${s.index}/approve`, 'POST', undefined, 'הבקשה אושרה').then(() => { swaps.reload(); q.reload(); }).catch(() => {})}><Check size={14} />אשר</button>
                        <button className="btn no" disabled={busy} onClick={() => run(`/swaps/${s.index}/reject`, 'POST', undefined, 'הבקשה נדחתה').then(swaps.reload).catch(() => {})}><X size={14} />דחה</button>
                      </div>
                    ))}
                  </div>
                )}</Load>
              </Bezel>
            </div>
            <div>
              <Bezel>
                <h2 className="sec">שיבוץ אוטומטי</h2>
                <div className="cardlist">
                  <Cta variant="teal" icon={<MagicWand size={16} />} disabled={busy} onClick={() => setAskAuto(false)}>{busy ? 'משבץ... (עד דקה)' : 'שיבוץ אוטומטי מלא'}</Cta>
                  <Cta variant="light" icon={<Coffee size={16} />} disabled={busy} onClick={() => setAskAuto(true)}>שיבוץ סופ&quot;שים בלבד</Cta>
                </div>
                {summary.length > 0 && <div style={{ marginTop: 14 }}><Note kind="ok">{summary.map((t) => <div key={t}>{t}</div>)}</Note></div>}
              </Bezel>
            </div>
            <Modal open={askAuto !== null} onClose={() => setAskAuto(null)}>
              <h2 className="sec"><MagicWand size={22} />{askAuto ? 'לשבץ אוטומטית את הסופ"שים?' : `לשבץ אוטומטית את ${HEB_MONTHS[m - 1]}?`}</h2>
              <ul className="confirm-list">
                <li><b>{Object.values(cal.slots).flat().filter((r) => r.is_manual && r.employee !== '---').length}</b> שיבוצים ידניים יישארו כמו שהם.</li>
                <li><b>{Object.values(cal.slots).flat().filter((r) => !r.is_manual && r.employee !== '---').length}</b> שיבוצים אוטומטיים קיימים {askAuto ? 'בסופ"שים ' : ''}יחושבו מחדש.</li>
                <li><b>{empty.length}</b> משמרות חסרות ינסו להתמלא.</li>
                <li>ההרצה לוקחת עד דקה. בשלב הזה אין עדיין ביטול אחרי הרצה מול הגיליון.</li>
              </ul>
              <div className="row">
                <Cta variant="teal" icon={<MagicWand size={16} />} onClick={() => auto(!!askAuto)}>הרץ שיבוץ</Cta>
                <button className="btn" onClick={() => setAskAuto(null)}>ביטול</button>
              </div>
            </Modal>
          </div>
        );
      }}</Load>
    </>
  );
}

function PersonalNight() {
  const me = useMe();
  const ym = ymOf(me.settings.active_year, me.settings.active_month);
  const [y, m] = ym.split('-').map(Number);
  const q = useApi<NightCal>(`/night/${ym}`);
  const [view, setView] = useState<'grid' | 'list'>('grid');
  useEffect(() => { if (window.matchMedia('(max-width: 767px)').matches) setView('list'); }, []);
  const openSwap = (date: string, r: NightSlot) => { handoff.swapShift = `${date}|${r.dept}`; window.location.hash = '/settings'; };
  return (
    <>
      <PageHead eyebrow={`${HEB_MONTHS[m - 1]} ${y}`} title="סידור תורנויות" sub="המשמרות שלך ומשמרות שעדיין לא אוישו" />
      <Load q={q}>{(cal) => {
        const mine = Object.entries(cal.slots).flatMap(([d, rows]) => rows.filter((r) => r.employee === me.name).map((r) => ({ d, r }))).sort((a, b) => a.d.localeCompare(b.d));
        if (Object.keys(cal.slots).length === 0) return <Note kind="info">עדיין לא פורסם סידור לחודש זה.</Note>;
        const nights = mine.filter((x) => !x.r.dept.startsWith('שישי'));
        const today = new Date().toISOString().slice(0, 10);
        const next = mine.find((x) => x.d >= today);
        return (
          <>
            <div className="kpis">
              <Kpi k="משמרות לילה החודש" v={nights.length} small={`מכסה ${me.monthly_quota}`} />
              <Kpi k="מתוכן בסופ״ש" v={nights.filter((x) => [5, 6].includes(new Date(x.d).getDay())).length} small={`מכסה ${me.weekend_quota}`} />
              {me.type === 'מתמחה' && <Kpi k="שישי בוקר" v={mine.length - nights.length} />}
              <Kpi k="המשמרת הבאה" v={next ? `${DOW_FULL[new Date(next.d).getDay()]} ${dmy(next.d)}` : 'אין'} small={next ? next.r.dept : ''} />
            </div>
            <Bezel>
              <div className="row" style={{ marginBottom: 16 }}>
                <h2 className="sec" style={{ margin: 0 }}>{view === 'grid' ? 'לוח החודש' : 'המשמרות שלי'}</h2><span className="grow" />
                <PillSeg value={view} onChange={setView} options={[{ v: 'list', l: 'הקרובות שלי' }, { v: 'grid', l: 'לוח' }]} />
              </div>
              {view === 'list' ? (mine.length === 0 ? <p className="muted">לא שובצת למשמרות החודש.</p> : (
                <div className="cardlist">
                  {mine.map(({ d, r }) => (
                    <div key={d + r.dept} className="rcard">
                      <span className={`slot ${kind(r.dept)}`}>{r.dept.startsWith('שישי') ? <Sun size={13} /> : <Moon size={13} />}</span>
                      <div className="main"><b>{DOW_FULL[new Date(d).getDay()]} {dmy(d)}</b><div className="meta">{r.dept}</div></div>
                      {d >= today && <button className="btn" onClick={() => openSwap(d, r)}><ArrowsClockwise size={14} />חפש החלפה</button>}
                    </div>
                  ))}
                </div>
              )) : (
                <Month y={y} m={m} cell={(d, date) => {
                  const rows = cal.slots[date] ?? [];
                  const sp = cal.special_days.find((s) => s.date === date);
                  return (
                    <div key={d} className={`day ${dowOf(y, m, d) >= 5 ? 'we' : ''}`}>
                      <span className="num">{d}</span>
                      {sp && <span className="sp">{sp.description}</span>}
                      {rows.map((r) => r.employee === '---'
                        ? <span key={r.dept} className="slot empty"><Question size={11} />{short(r.dept)} חסר</span>
                        : <button key={r.dept} className={`slot mine ${kind(r.dept)}`} onClick={() => openSwap(date, r)} title="חפש החלפה">{short(r.dept)}</button>)}
                    </div>
                  );
                }} />
              )}
            </Bezel>
          </>
        );
      }}</Load>
    </>
  );
}

export default function LiveNight() {
  const me = useMe();
  return me.type === 'מנהל על' ? <AdminNight /> : <PersonalNight />;
}
