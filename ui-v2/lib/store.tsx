'use client';
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';
import { DB, initialDB } from './logic';

type ToastKind = 'ok' | 'warn' | 'err' | 'info';
interface Toast { id: number; msg: string; kind: ToastKind }
interface Store {
  db: DB;
  mutate: (fn: (draft: DB) => void) => void;
  toast: (msg: string, kind?: ToastKind) => void;
  toasts: Toast[];
}
const Ctx = createContext<Store | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [db, setDb] = useState<DB>(initialDB);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const mutate = useCallback((fn: (d: DB) => void) => {
    setDb((prev) => { const next = structuredClone(prev); fn(next); return next; });
  }, []);
  const toast = useCallback((msg: string, kind: ToastKind = 'ok') => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, msg, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3200);
  }, []);
  return <Ctx.Provider value={{ db, mutate, toast, toasts }}>{children}</Ctx.Provider>;
}
export function useStore() {
  const s = useContext(Ctx);
  if (!s) throw new Error('useStore outside StoreProvider');
  return s;
}
