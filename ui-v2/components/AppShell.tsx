'use client';
import { useEffect, useRef, useState, type ComponentType } from 'react';
import {
  CalendarCheck, CalendarDots, ChartBar, GearSix, LockSimple, LockSimpleOpen, MoonStars, ShieldCheck, SignOut, SquaresFour, Tray, UsersThree, type IconProps,
} from '@phosphor-icons/react';
import { useStore } from '@/lib/store';
import { HEB_MONTHS, roleLabel } from '@/lib/mock';
import { MOBILE_PRIMARY, type TabKey } from '@/lib/roles';
import { track } from '@/lib/analytics';
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
import LiveNight from './live/Night';
import LiveWork from './live/Work';
import LiveRequests from './live/Requests';
import LiveSubmit from './live/Submit';
import LiveSettings from './live/Settings';
import { LiveGantt, LiveOnCall, LiveReports, LiveStaff } from './live/Admin';

// Tab order from ui_components.render_navbar; which tabs a role gets comes from lib/roles.ts.
// C: demo screen on mock data; L: the same screen on the real API (live mode).
const TABS: { k: TabKey; he: string; short: string; I: ComponentType<IconProps>; C: ComponentType; L: ComponentType }[] = [
  { k: 'settings', he: 'הגדרות', short: 'הגדרות', I: GearSix, C: Settings, L: LiveSettings },
  { k: 'night', he: 'סידור תורנויות', short: 'תורנויות', I: MoonStars, C: Night, L: LiveNight },
  { k: 'submit', he: 'הגשת בקשות', short: 'הגשה', I: CalendarCheck, C: Submit, L: LiveSubmit },
  { k: 'staff', he: 'צוות', short: 'צוות', I: UsersThree, C: StaffTab, L: LiveStaff },
  { k: 'reports', he: 'דוחות וניהול', short: 'דוחות', I: ChartBar, C: Reports, L: LiveReports },
  { k: 'oncall', he: 'סידור כוננויות', short: 'כוננויות', I: ShieldCheck, C: OnCall, L: LiveOnCall },
  { k: 'gantt', he: 'גאנט חודשי', short: 'גאנט', I: SquaresFour, C: Gantt, L: LiveGantt },
  { k: 'work', he: 'סידור עבודה', short: 'עבודה', I: CalendarDots, C: Work, L: LiveWork },
  { k: 'requests', he: 'ניהול בקשות', short: 'בקשות', I: Tray, C: Requests, L: LiveRequests },
];

const readHash = () => (typeof window === 'undefined' ? '' : window.location.hash.replace('#/', '').replace('#', ''));

/** API_WRITE_SHEETS → the screens they open, for the read-only banner (analytics_log is silent logging). */
const SHEET_SCREENS: Record<string, string> = {
  requests: 'אילוצי לילה', absence_requests: 'בקשות היעדרות וסידור עבודה', schedule: 'סידור תורנויות והחלפות',
  staff: 'צוות', dept_rotation: 'גאנט חודשי', settings: 'חודש פעיל', special_days: 'ימים מיוחדים',
  konenut: 'כוננות', daily_report: 'סריקת בעיות', 'WSD_*': 'ייצוא ל-Sheets',
};
const openScreens = (sheets: string[]) => sheets.map((s) => SHEET_SCREENS[s]).filter(Boolean);

export default function AppShell() {
  const { toasts, dismiss, me, live, logout } = useStore();
  const [hash, setHash] = useState('');
  const navRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const on = () => { setHash(readHash()); window.scrollTo({ top: 0 }); };
    on(); window.addEventListener('hashchange', on); return () => window.removeEventListener('hashchange', on);
  }, []);
  const go = (k: string) => { window.location.hash = `/${k}`; };
  useEffect(() => { navRef.current?.querySelector('.on')?.scrollIntoView({ inline: 'center', block: 'nearest' }); }, [hash, me]);
  // Keep the address bar on the tab actually shown (landing tab after login, fallback for tabs outside the role).
  useEffect(() => { if (me && !me.tabs.includes(hash as TabKey)) window.history.replaceState(null, '', `#/${me.home}`); }, [hash, me]);
  // Usage log (live only): entering a tab, and the seconds spent on the one left (Streamlit's tab_view).
  const tabSeen = useRef<{ he: string; at: number } | null>(null);
  const shownTab = me ? (me.tabs.includes(hash as TabKey) ? (hash as TabKey) : me.home) : null;
  useEffect(() => {
    if (!live || !me || !shownTab) { tabSeen.current = null; return; }
    const he = TABS.find((t) => t.k === shownTab)?.he ?? shownTab;
    const prev = tabSeen.current;
    if (prev?.he === he) return;
    if (prev) track('tab_view', prev.he, String(Math.round((Date.now() - prev.at) / 1000)));
    track('tab_view', he, 'enter');
    tabSeen.current = { he, at: Date.now() };
  }, [live, me, shownTab]);

  const toastLayer = (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`}>
          <span>{t.msg}</span>
          {t.action && <button className="toast-act" onClick={() => { t.action!.fn(); dismiss(t.id); }}>{t.action.label}</button>}
        </div>
      ))}
    </div>
  );
  if (live === null) return <div className="boot" aria-busy="true" />;
  // No session: every address shows the login screen.
  if (!me) return <><Login onLogin={() => go('')} />{toastLayer}</>;

  const allowed = me.tabs;
  const tabs = TABS.filter((t) => allowed.includes(t.k));
  // A tab outside the role (deep link, old bookmark) falls back to the role's home tab.
  const route: TabKey = allowed.includes(hash as TabKey) ? (hash as TabKey) : me.home;
  const tab = TABS.find((t) => t.k === route)!;
  const Page = live ? tab.L : tab.C;
  const primary = MOBILE_PRIMARY[me.type].filter((k) => allowed.includes(k));
  const mobileTabs = [...primary.map((k) => tabs.find((t) => t.k === k)!), ...tabs.filter((t) => !primary.includes(t.k))];
  const out = () => { logout(); go('login'); };
  const s = me.settings;

  return (
    <div className="layout">
      <aside className="rail" aria-label="ניווט ראשי">
        {tabs.map((t) => (
          <a key={t.k} href={`#/${t.k}`} className={t.k === route ? 'on' : ''} data-tab={t.k} aria-current={t.k === route ? 'page' : undefined}>
            <t.I size={22} weight={t.k === route ? 'fill' : 'light'} />{t.he}
          </a>
        ))}
        <button className="out" onClick={out}><SignOut size={16} /> התנתק</button>
      </aside>
      <main className="page" key={route + me.name}>
        <div className="statusbar">
          <span className="who"><b>{me.name}</b> · {roleLabel(me.type)}</span>
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
        {me.readOnly && <div className="ro-banner">{openScreens(me.writeSheets).length
          ? <>פתוח כאן לעריכה: <b>{openScreens(me.writeSheets).join(', ')}</b>. כל השאר לצפייה בלבד, ושינויים בו נעשים עדיין באפליקציה הקיימת.</>
          : 'המערכת החדשה פתוחה כרגע לצפייה בלבד, על הנתונים האמיתיים. שינויים נעשים עדיין באפליקציה הקיימת.'}</div>}
        <Page />
      </main>

      {/* Mobile: one swipeable strip with every tab of the role, the bar's usual four first. */}
      <nav className="mob-nav" aria-label="ניווט" ref={navRef}>
        {mobileTabs.map((t) => (
          <a key={t.k} href={`#/${t.k}`} className={t.k === route ? 'on' : ''} data-tab={t.k}><t.I size={20} weight={t.k === route ? 'fill' : 'light'} />{t.short}</a>
        ))}
      </nav>
      {toastLayer}
    </div>
  );
}
