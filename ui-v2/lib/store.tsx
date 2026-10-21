'use client';
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { DB, initialDB } from './logic';
import type { Role } from './mock';
import { api, detectLive, type MeResp, type Settings } from './api';
import { homeTab, tabsForRole, type TabKey } from './roles';
import { daysIn } from './mock';

type ToastKind = 'ok' | 'warn' | 'err' | 'info';
export interface ToastAction { label: string; fn: () => void }
interface Toast { id: number; msg: string; kind: ToastKind; action?: ToastAction }

/** The logged-in user, the same shape in demo and live mode. */
export interface Me {
  name: string; type: Role; manage_depts: string[]; monthly_quota: number; weekend_quota: number;
  tabs: TabKey[]; home: TabKey; settings: Settings; readOnly: boolean;
}

interface Store {
  db: DB;
  mutate: (fn: (draft: DB) => void) => void;
  toast: (msg: string, kind?: ToastKind, action?: ToastAction) => void;
  dismiss: (id: number) => void;
  toasts: Toast[];
  /** null while checking for a backend; true = real data via /api, false = demo data. */
  live: boolean | null;
  me: Me | null;
  login: (name: string, password?: string) => Promise<string | null>;
  logout: () => void;
  refreshMe: () => Promise<void>;
}
const Ctx = createContext<Store | null>(null);

const yearOf = (m: number) => { const t = new Date(); let y = t.getFullYear(); if (m < t.getMonth() + 1 - 5) y += 1; else if (m > t.getMonth() + 1 + 6) y -= 1; return y; };
const fromApi = (r: MeResp): Me => ({
  name: r.name, type: r.role as Role, manage_depts: r.manage_depts,
  monthly_quota: Number(r.monthly_quota) || 0, weekend_quota: Number(r.weekend_quota) || 0,
  tabs: r.tabs as TabKey[], home: r.home as TabKey, settings: r.settings, readOnly: r.read_only,
});

export function StoreProvider({ children }: { children: ReactNode }) {
  const [db, setDb] = useState<DB>(initialDB);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [live, setLive] = useState<boolean | null>(null);
  const [liveMe, setLiveMe] = useState<Me | null>(null);
  const [demoName, setDemoName] = useState<string | null>(null);

  useEffect(() => {
    detectLive().then(async (ok) => {
      setLive(ok);
      if (ok) { try { setLiveMe(fromApi(await api<MeResp>('/me'))); } catch { /* not logged in */ } }
    });
  }, []);

  const mutate = useCallback((fn: (d: DB) => void) => {
    setDb((prev) => { const next = structuredClone(prev); fn(next); return next; });
  }, []);
  const dismiss = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  // A toast with an action (e.g. undo) stays longer so there is time to use it.
  const toast = useCallback((msg: string, kind: ToastKind = 'ok', action?: ToastAction) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, msg, kind, action }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), action ? 8000 : 3600);
  }, []);

  /** Returns an error message, or null on success. */
  const login = useCallback(async (name: string, password = '') => {
    if (live) {
      try { setLiveMe(fromApi(await api<MeResp>('/auth/login', { method: 'POST', body: { username: name, password } }))); return null; }
      catch (e) { return (e as Error).message; }
    }
    if (!db.staff.some((s) => s.name === name)) return 'שם המשתמש לא נמצא במערכת';
    setDemoName(name); return null;
  }, [live, db.staff]);
  const logout = useCallback(() => {
    if (live) { api('/auth/logout', { method: 'POST' }).catch(() => {}); setLiveMe(null); } else setDemoName(null);
  }, [live]);
  const refreshMe = useCallback(async () => { if (live) setLiveMe(fromApi(await api<MeResp>('/me'))); }, [live]);

  let me: Me | null = liveMe;
  if (!live) {
    const s = db.staff.find((x) => x.name === demoName);
    const st = db.settings;
    me = s ? {
      name: s.name, type: s.type, manage_depts: s.manage_depts, monthly_quota: s.monthly_quota, weekend_quota: s.weekend_quota,
      tabs: tabsForRole(s.type), home: homeTab(s.type), readOnly: false,
      settings: { ...st, active_year: yearOf(st.active_month), daily_active_year: yearOf(st.daily_active_month) },
    } : null;
  }
  return <Ctx.Provider value={{ db, mutate, toast, dismiss, toasts, live, me, login, logout, refreshMe }}>{children}</Ctx.Provider>;
}
export function useStore() {
  const s = useContext(Ctx);
  if (!s) throw new Error('useStore outside StoreProvider');
  return s;
}
/** The logged-in user. Only used inside the shell, which renders tabs only after login. */
export function useMe(): Me {
  const { me } = useStore();
  if (!me) throw new Error('useMe before login');
  return me;
}
export const ymOf = (y: number, m: number) => `${y}-${String(m).padStart(2, '0')}`;
export const monthDays = (y: number, m: number) => Array.from({ length: daysIn(y, m) }, (_, i) => i + 1);
