'use client';
import { useState, type ReactNode } from 'react';
import { ArrowClockwise } from '@phosphor-icons/react';
import { api, ApiError } from '@/lib/api';
import { HEB_MONTHS } from '@/lib/mock';
import { useStore } from '@/lib/store';
import { Note } from '../ui';

export function Loading() {
  return <div className="cardlist" aria-busy="true"><div className="loading-sk" /><div className="loading-sk" /></div>;
}

export function Failed({ error, retry }: { error: ApiError; retry: () => void }) {
  return (
    <Note kind="err">
      {error.message}{' '}
      <button className="btn" style={{ marginInlineStart: 8 }} onClick={retry}><ArrowClockwise size={14} />נסה שוב</button>
    </Note>
  );
}

/** Wraps a data hook result: skeleton while loading, error with retry, else the children. */
export function Load<T>({ q, children }: { q: { data: T | null; error: ApiError | null; loading: boolean; reload: () => void }; children: (d: T) => ReactNode }) {
  if (q.error) return <Failed error={q.error} retry={q.reload} />;
  if (q.loading && !q.data) return <Loading />;
  return q.data ? <>{children(q.data)}</> : null;
}

/** Months from 2 back to 9 ahead of today, as YYYY-MM. */
export function rollingMonths(): { v: string; y: number; m: number; l: string }[] {
  const t = new Date();
  return Array.from({ length: 12 }, (_, i) => {
    const d = new Date(t.getFullYear(), t.getMonth() - 2 + i, 1);
    const y = d.getFullYear(), m = d.getMonth() + 1;
    return { v: `${y}-${String(m).padStart(2, '0')}`, y, m, l: `${HEB_MONTHS[m - 1]} ${y}` };
  });
}

/** Months a month-number-only setting can hold: the server infers the year 5 months back to 6 ahead. */
export function inSettingWindow(ym: string): boolean {
  const t = new Date();
  const [y, m] = ym.split('-').map(Number);
  const diff = (y - t.getFullYear()) * 12 + (m - (t.getMonth() + 1));
  return diff >= -5 && diff <= 6;
}

export function MonthPick({ value, onChange, options }: { value: string; onChange: (v: string) => void; options?: { v: string; l: string }[] }) {
  const opts = options ?? rollingMonths();
  const all = opts.some((o) => o.v === value) ? opts : [{ v: value, l: value }, ...opts];
  return (
    <select className="input" style={{ width: 170 }} value={value} onChange={(e) => onChange(e.target.value)} aria-label="חודש">
      {all.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
    </select>
  );
}

/** Runs a write; toasts the server's Hebrew message on failure (including the read-only notice). */
export function useAction() {
  const { toast } = useStore();
  const [busy, setBusy] = useState(false);
  const run = async <T,>(path: string, method: string, body?: unknown, okMsg?: string): Promise<T | null> => {
    setBusy(true);
    try {
      const r = await api<T>(path, { method, body });
      if (okMsg) toast(okMsg);
      return r;
    } catch (e) {
      const err = e as ApiError;
      if (err.status !== 409) toast(err.message, err.status === 403 ? 'warn' : 'err');
      throw err;
    } finally { setBusy(false); }
  };
  return { run, busy };
}

/** Downloads an .xlsx from the API; toasts the server's Hebrew message on failure. */
export function useDownload() {
  const { toast } = useStore();
  const [busy, setBusy] = useState(false);
  const download = async (path: string) => {
    setBusy(true);
    try {
      const res = await fetch(`/api${path}`, { credentials: 'same-origin' });
      if (!res.ok) {
        let msg = 'שגיאה בייצוא. נסה/י שוב.';
        try { const j = await res.json(); if (typeof j?.detail === 'string') msg = j.detail; } catch { /* not JSON */ }
        toast(msg, 'err');
        return;
      }
      const cd = res.headers.get('Content-Disposition') ?? '';
      const m = /filename\*=UTF-8''([^;]+)/.exec(cd);
      const name = m ? decodeURIComponent(m[1]) : 'export.xlsx';
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement('a');
      a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch { toast('שגיאה בייצוא. נסה/י שוב.', 'err'); } finally { setBusy(false); }
  };
  return { download, busy };
}

export const enc = encodeURIComponent;
export const dmy = (ds: string) => { const [, m, d] = ds.split('-'); return `${+d}/${+m}`; };
export const range = (a: string, b: string) => (a === b ? dmy(a) : `${dmy(a)} - ${dmy(b)}`);
// Daily statuses (Hebrew, from geri_core) → the colour classes the grid already uses.
export const STATUS_CLASS: Record<string, string> = { 'עובד': 'W', 'חופש': 'V', '202': 'S', 'אחרי תורנות': 'A', 'אחר': 'O', 'תורנות': 'T', '': 'E' };
