'use client';
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';
import { DB, initialDB } from './logic';
import type { Staff } from './mock';

type ToastKind = 'ok' | 'warn' | 'err' | 'info';
interface Toast { id: number; msg: string; kind: ToastKind }
interface Store {
  db: DB;
  mutate: (fn: (draft: DB) => void) => void;
  toast: (msg: string, kind?: ToastKind) => void;
  toasts: Toast[];
  me: Staff | null;
  login: (name: string) => boolean;
  logout: () => void;
}
const Ctx = createContext<Store | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [db, setDb] = useState<DB>(initialDB);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [meName, setMeName] = useState<string | null>(null);
  const mutate = useCallback((fn: (d: DB) => void) => {
    setDb((prev) => { const next = structuredClone(prev); fn(next); return next; });
  }, []);
  const toast = useCallback((msg: string, kind: ToastKind = 'ok') => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, msg, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3200);
  }, []);
  const login = useCallback((name: string) => {
    if (!db.staff.some((s) => s.name === name)) return false;
    setMeName(name); return true;
  }, [db.staff]);
  const logout = useCallback(() => setMeName(null), []);
  const me = db.staff.find((s) => s.name === meName) ?? null;
  return <Ctx.Provider value={{ db, mutate, toast, toasts, me, login, logout }}>{children}</Ctx.Provider>;
}
export function useStore() {
  const s = useContext(Ctx);
  if (!s) throw new Error('useStore outside StoreProvider');
  return s;
}
/** The logged-in user. Only used inside the shell, which renders tabs only after login. */
export function useMe(): Staff {
  const { me } = useStore();
  if (!me) throw new Error('useMe before login');
  return me;
}
