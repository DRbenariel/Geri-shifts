'use client';
import { useEffect, useState, type ComponentType } from 'react';
import {
  CalendarCheck, CalendarDots, ChartBar, DotsThreeOutline, GearSix, LockSimple, LockSimpleOpen, MoonStars, ShieldCheck, SignOut, SquaresFour, Tray, UsersThree, type IconProps,
} from '@phosphor-icons/react';
import { useStore } from '@/lib/store';
import { HEB_MONTHS } from '@/lib/mock';
import { initials } from '@/lib/logic';
import { MOBILE_PRIMARY, homeTab, tabsForRole, type TabKey } from '@/lib/roles';
import Login from './Login';
import Settings from './tabs/Settings';
import Night from './tabs/Night';
import Submit from './tabs/Submit';
import StaffTab from './tabs/Staff';
import Reports from './tabs/Reports';
import OnCall from './tabs/OnCall';
import Gantt from './tabs/Gantt';
import Work from './tabs/Work';
import Requests from './tabs/Requests';

// Tab order from ui_components.render_navbar; which tabs a role gets comes from lib/roles.ts.
const TABS: { k: TabKey; he: string; short: string; I: ComponentType<IconProps>; C: ComponentType }[] = [
  { k: 'settings', he: 'הגדרות', short: 'הגדרות', I: GearSix, C: Settings },
  { k: 'night', he: 'סידור תורנויות', short: 'תורנויות', I: MoonStars, C: Night },
  { k: 'submit', he: 'הגשת בקשות', short: 'הגשה', I: CalendarCheck, C: Submit },
  { k: 'staff', he: 'צוות', short: 'צוות', I: UsersThree, C: StaffTab },
  { k: 'reports', he: 'דוחות וניהול', short: 'דוחות', I: ChartBar, C: Reports },
  { k: 'oncall', he: 'סידור כוננויות', short: 'כוננויות', I: ShieldCheck, C: OnCall },
  { k: 'gantt', he: 'גאנט חודשי', short: 'גאנט', I: SquaresFour, C: Gantt },
  { k: 'work', he: 'סידור עבודה', short: 'עבודה', I: CalendarDots, C: Work },
  { k: 'requests', he: 'ניהול בקשות', short: 'בקשות', I: Tray, C: Requests },
];

const readHash = () => (typeof window === 'undefined' ? '' : window.location.hash.replace('#/', '').replace('#', ''));

export default function AppShell() {
  const { toasts, me, db, logout } = useStore();
  const [hash, setHash] = useState('');
  const [more, setMore] = useState(false);
  useEffect(() => {
    const on = () => { setHash(readHash()); setMore(false); window.scrollTo({ top: 0 }); };
    on(); window.addEventListener('hashchange', on); return () => window.removeEventListener('hashchange', on);
  }, []);
  const go = (k: string) => { window.location.hash = `/${k}`; };

  const toastLayer = (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => <div key={t.id} className={`toast ${t.kind}`}>{t.msg}</div>)}
    </div>
  );
  // No session: every address shows the login screen.
  if (!me) return <><Login onLogin={(n) => { const u = db.staff.find((s) => s.name === n)!; go(homeTab(u.type)); }} />{toastLayer}</>;

  const allowed = tabsForRole(me.type);
  const tabs = TABS.filter((t) => allowed.includes(t.k));
  // A tab outside the role (deep link, old bookmark) falls back to the role's home tab.
  const route: TabKey = allowed.includes(hash as TabKey) ? (hash as TabKey) : homeTab(me.type);
  const tab = TABS.find((t) => t.k === route)!;
  const Page = tab.C;
  const primary = MOBILE_PRIMARY[me.type];
  const hasMore = tabs.length > primary.length;
  const out = () => { logout(); go('login'); };
  const s = db.settings;

  return (
    <div className="layout">
      <aside className="rail" aria-label="ניווט ראשי">
        <div className="logo" title="מערכת סידור עבודה המערך הגריאטרי">ג</div>
        {tabs.map((t) => (
          <a key={t.k} href={`#/${t.k}`} className={t.k === route ? 'on' : ''} data-tab={t.k} aria-current={t.k === route ? 'page' : undefined}>
            <t.I size={22} weight={t.k === route ? 'fill' : 'light'} />{t.he}
          </a>
        ))}
        <div className="me" title={`${me.name} · ${me.type}`}>{initials(me.name)}</div>
        <button className="out" onClick={out}><SignOut size={16} /> התנתק</button>
      </aside>
      <main className="page" key={route + me.name}>
        <div className="statusbar">
          <span className="who"><b>{me.name}</b> · {me.type}</span>
          <span className="grow" />
          {route !== 'night' && allowed.includes('night') && <span className="pill"><MoonStars size={14} />חודש פעיל לתורנויות: <b>{HEB_MONTHS[s.active_month - 1]}</b></span>}
          {me.type !== 'תורן חוץ' && (
            <span className={`pill ${s.daily_requests_open ? 'ok' : 'lock'}`}>
              {s.daily_requests_open ? <LockSimpleOpen size={14} /> : <LockSimple size={14} />}
              הגשות היעדרות ל{HEB_MONTHS[s.daily_active_month - 1]}: <b>{s.daily_requests_open ? 'פתוחות' : 'סגורות'}</b>
            </span>
          )}
          <button className="btn mob-only out-m" onClick={out}><SignOut size={14} />התנתק</button>
        </div>
        <Page />
      </main>

      {more && (
        <div className="more-sheet"><div className="shell"><div className="core">
          {tabs.map((t) => <a key={t.k} href={`#/${t.k}`} className={t.k === route ? 'on' : ''}><t.I size={22} />{t.he}</a>)}
          <a href="#/login" onClick={(e) => { e.preventDefault(); out(); }}><SignOut size={22} />התנתק</a>
        </div></div></div>
      )}
      <nav className="mob-nav" aria-label="ניווט">
        {primary.map((k) => { const t = TABS.find((x) => x.k === k)!; return (
          <a key={k} href={`#/${k}`} className={k === route ? 'on' : ''}><t.I size={20} weight={k === route ? 'fill' : 'light'} />{t.short}</a>
        ); })}
        {hasMore && <button className={more || !primary.includes(route) ? 'on' : ''} onClick={() => setMore(!more)}><DotsThreeOutline size={20} />עוד</button>}
      </nav>
      {toastLayer}
    </div>
  );
}
