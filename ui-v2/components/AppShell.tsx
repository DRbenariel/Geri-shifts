'use client';
import { useEffect, useState, type ComponentType } from 'react';
import {
  CalendarDots, ChartBar, DotsThreeOutline, GearSix, MoonStars, ShieldCheck, SignOut, SquaresFour, Tray, UsersThree, type IconProps,
} from '@phosphor-icons/react';
import { useStore } from '@/lib/store';
import { ME } from '@/lib/mock';
import { initials } from '@/lib/logic';
import Login from './Login';
import Settings from './tabs/Settings';
import Night from './tabs/Night';
import StaffTab from './tabs/Staff';
import Reports from './tabs/Reports';
import OnCall from './tabs/OnCall';
import Gantt from './tabs/Gantt';
import Work from './tabs/Work';
import Requests from './tabs/Requests';

type TabKey = 'settings' | 'night' | 'staff' | 'reports' | 'oncall' | 'gantt' | 'work' | 'requests';
// Superadmin (מנהל על) tab order, from ui_components.render_navbar. הגשת בקשות is hidden for this role.
const TABS: { k: TabKey; he: string; short: string; I: ComponentType<IconProps>; C: ComponentType }[] = [
  { k: 'settings', he: 'הגדרות', short: 'הגדרות', I: GearSix, C: Settings },
  { k: 'night', he: 'סידור תורנויות', short: 'תורנויות', I: MoonStars, C: Night },
  { k: 'staff', he: 'צוות', short: 'צוות', I: UsersThree, C: StaffTab },
  { k: 'reports', he: 'דוחות וניהול', short: 'דוחות', I: ChartBar, C: Reports },
  { k: 'oncall', he: 'סידור כוננויות', short: 'כוננויות', I: ShieldCheck, C: OnCall },
  { k: 'gantt', he: 'גאנט חודשי', short: 'גאנט', I: SquaresFour, C: Gantt },
  { k: 'work', he: 'סידור עבודה', short: 'עבודה', I: CalendarDots, C: Work },
  { k: 'requests', he: 'ניהול בקשות', short: 'בקשות', I: Tray, C: Requests },
];
const MOBILE_PRIMARY: TabKey[] = ['reports', 'work', 'requests', 'night'];
const DEFAULT: TabKey = 'reports';

function readHash(): TabKey | 'login' {
  const h = typeof window === 'undefined' ? '' : window.location.hash.replace('#/', '').replace('#', '');
  if (h === 'login' || h === '') return 'login';
  return (TABS.find((t) => t.k === h)?.k) ?? DEFAULT;
}

export default function AppShell() {
  const { toasts } = useStore();
  const [route, setRoute] = useState<TabKey | 'login'>('login');
  const [more, setMore] = useState(false);
  useEffect(() => {
    const on = () => { setRoute(readHash()); setMore(false); window.scrollTo({ top: 0 }); };
    on(); window.addEventListener('hashchange', on); return () => window.removeEventListener('hashchange', on);
  }, []);
  const go = (k: TabKey | 'login') => { window.location.hash = `/${k}`; };

  const toastLayer = (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => <div key={t.id} className={`toast ${t.kind}`}>{t.msg}</div>)}
    </div>
  );
  if (route === 'login') return <><Login onLogin={() => go(DEFAULT)} />{toastLayer}</>;

  const tab = TABS.find((t) => t.k === route)!;
  const Page = tab.C;
  return (
    <div className="layout">
      <aside className="rail" aria-label="ניווט ראשי">
        <div className="logo" title="מערכת סידור עבודה המערך הגריאטרי">ג</div>
        {TABS.map((t) => (
          <a key={t.k} href={`#/${t.k}`} className={t.k === route ? 'on' : ''} data-tab={t.k} aria-current={t.k === route ? 'page' : undefined}>
            <t.I size={22} weight={t.k === route ? 'fill' : 'light'} />{t.he}
          </a>
        ))}
        <div className="me" title={`${ME.name} · ${ME.type}`}>{initials(ME.name)}</div>
        <button className="out" onClick={() => go('login')}><SignOut size={16} /> התנתק</button>
      </aside>
      <main className="page" key={route}><Page /></main>

      {more && (
        <div className="more-sheet"><div className="shell"><div className="core">
          {TABS.map((t) => <a key={t.k} href={`#/${t.k}`} className={t.k === route ? 'on' : ''}><t.I size={22} />{t.he}</a>)}
          <a href="#/login"><SignOut size={22} />התנתק</a>
        </div></div></div>
      )}
      <nav className="mob-nav" aria-label="ניווט">
        {MOBILE_PRIMARY.map((k) => { const t = TABS.find((x) => x.k === k)!; return (
          <a key={k} href={`#/${k}`} className={k === route ? 'on' : ''}><t.I size={20} weight={k === route ? 'fill' : 'light'} />{t.short}</a>
        ); })}
        <button className={more || !MOBILE_PRIMARY.includes(route) ? 'on' : ''} onClick={() => setMore(!more)}><DotsThreeOutline size={20} />עוד</button>
      </nav>
      {toastLayer}
    </div>
  );
}
