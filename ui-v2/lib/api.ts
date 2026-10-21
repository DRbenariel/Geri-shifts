// Client for the FastAPI layer (backend/api). Same origin: the Cloudflare Worker proxies /api/* to Cloud Run,
// so the httpOnly session cookie stays first-party.
'use client';
import { useCallback, useEffect, useRef, useState } from 'react';

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T = unknown>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: opts.method ?? 'GET',
    credentials: 'same-origin',
    headers: opts.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  const text = await res.text();
  let data: unknown = null;
  try { data = text ? JSON.parse(text) : null; } catch { /* non-JSON error page */ }
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    throw new ApiError(res.status, typeof detail === 'string' ? detail : 'שגיאה בשרת. נסה/י שוב.');
  }
  return data as T;
}

/** True when a backend answers /api/health; the static demo has none, so it stays on mock data. */
export async function detectLive(): Promise<boolean> {
  try {
    const r = await fetch('/api/health', { credentials: 'same-origin' });
    if (!r.ok) return false;
    const j = await r.json();
    return j?.ok === true;
  } catch { return false; }
}

/** GET with loading/error state; `reload` refetches. path=null skips the request. */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(!!path);
  // Only the latest request may update state: a slow earlier reload must not overwrite a newer one.
  const seq = useRef(0);
  const load = useCallback(async () => {
    if (!path) return;
    const mine = ++seq.current;
    setLoading(true); setError(null);
    try { const d = await api<T>(path); if (mine === seq.current) setData(d); }
    catch (e) { if (mine === seq.current) setError(e as ApiError); }
    finally { if (mine === seq.current) setLoading(false); }
  }, [path]);
  useEffect(() => { load(); }, [load]);
  return { data, error, loading, reload: load };
}

// ---- Response shapes (geri_core view models) ----
export interface Settings { active_month: number; active_year: number; daily_active_month: number; daily_active_year: number; daily_requests_open: boolean }
export interface MeResp {
  name: string; role: string; tabs: string[]; home: string; manage_depts: string[];
  monthly_quota: string | number; weekend_quota: string | number; settings: Settings; read_only: boolean;
}
export interface NightSlot { dept: string; employee: string; is_manual: boolean; empty_reason: string }
export interface NightCal {
  year: number; month: number; slots: Record<string, NightSlot[]>;
  special_days: { date: string; description: string; day_type: string }[];
  requests?: Record<string, { employee: string; status: string }[]>;
  availability?: { shown: boolean; available: Record<string, string[]>; wished: Record<string, string[]> };
}
export interface GridCell { day: number; status: string | null; label: string; note: string; manual: boolean; locked: boolean; blank_weekend: boolean }
export interface GridRow { employee: string; type: string; side: string; transfer_days: number[] | null; allowed_statuses: string[]; cells: GridCell[] }
export interface Grid {
  dept: string; year: number; month: number; year_month: string; editable: boolean;
  side_groups: Record<string, string[]> | null; unassigned_side: string[];
  rows: GridRow[];
  days: { day: number; date: string; weekday: number; night_duty: string | string[] | null; friday_workers: string[] | null; konenut: string | null }[];
  transfers: Record<string, { days: number[]; side: string }>;
}
export interface Pending {
  id: string; employee: string; start_date: string; end_date: string; type: string; notes?: string;
  dept_at_request: string; dept_canonical: string; created_at?: string; conflict_question: string;
  conflicts: { employee: string; start: string; end: string }[];
}
export interface AbsGantt { by_dept: Record<string, Record<string, [number, string][]>>; notes?: Record<string, Record<string, string>>; conflicts: { dept: string; day: number; employees: string[] }[] }
