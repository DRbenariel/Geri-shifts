'use client';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ArrowUpLeft, CaretDown, CheckCircle, Info, Warning, XCircle } from '@phosphor-icons/react';
import { STATUS, type Code, initials } from '@/lib/logic';
import type { Role } from '@/lib/mock';

export function Bezel({ children, tight, className = '', id }: { children: ReactNode; tight?: boolean; className?: string; id?: string }) {
  return <section className={`shell ${className}`} id={id}><div className={`core ${tight ? 'tight' : ''}`}>{children}</div></section>;
}

export function Expander({ title, icon, children, open: init = false, badge }: { title: string; icon?: ReactNode; children: ReactNode; open?: boolean; badge?: ReactNode }) {
  const [open, setOpen] = useState(init);
  return (
    <Bezel>
      <button className="exp-h" aria-expanded={open} onClick={() => setOpen(!open)}>
        {icon}{title}{badge}<span className="chev"><CaretDown size={16} weight="bold" /></span>
      </button>
      {open && <div className="exp-b">{children}</div>}
    </Bezel>
  );
}

export function PageHead({ eyebrow, title, sub, actions }: { eyebrow?: string; title: string; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <>
      {eyebrow && <span className="eyebrow">{eyebrow}</span>}
      <div className="top">
        <div><h1>{title}</h1>{sub && <div className="sub">{sub}</div>}</div>
        {actions && <div className="actions">{actions}</div>}
      </div>
    </>
  );
}

export function Cta({ children, icon, onClick, disabled, variant = '', sm, type = 'button' }:
  { children: ReactNode; icon?: ReactNode; onClick?: () => void; disabled?: boolean; variant?: '' | 'light' | 'teal' | 'danger'; sm?: boolean; type?: 'button' | 'submit' }) {
  return (
    <button type={type} className={`cta ${variant} ${sm ? 'sm' : ''}`} onClick={onClick} disabled={disabled}>
      {children}<span className="ic">{icon ?? <ArrowUpLeft size={16} weight="light" />}</span>
    </button>
  );
}

export function PillSeg<T extends string | number>({ value, options, onChange }: { value: T; options: { v: T; l: string }[]; onChange: (v: T) => void }) {
  return (
    <div className="pillseg" role="tablist">
      {options.map((o) => <button key={String(o.v)} role="tab" aria-selected={o.v === value} className={o.v === value ? 'on' : ''} onClick={() => onChange(o.v)}>{o.l}</button>)}
    </div>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return <div className="field"><label>{label}</label>{children}</div>;
}

export function Note({ kind = 'info', children }: { kind?: 'info' | 'warn' | 'err' | 'ok'; children: ReactNode }) {
  const I = kind === 'ok' ? CheckCircle : kind === 'err' ? XCircle : kind === 'warn' ? Warning : Info;
  return <div className={`note ${kind}`}><I size={18} weight="fill" /><div>{children}</div></div>;
}

export function Avatar({ name, role }: { name: string; role?: Role }) {
  const cls = role === 'מתמחה' ? 'int' : role === 'תורן חוץ' ? 'ext' : 'sen';
  return <div className={`av ${cls}`}>{initials(name)}</div>;
}
export function Person({ name, role, me }: { name: string; role?: Role | string; me?: boolean }) {
  return (
    <div className={`person ${me ? 'me' : ''}`}>
      <Avatar name={name} role={role as Role} />
      <div style={{ minWidth: 0 }}><div className="n">{name}</div>{role && <div className="r">{role}</div>}</div>
    </div>
  );
}

export function StatusLegend({ codes = ['W', 'V', 'S', 'A', 'T', 'O', 'E'] as Code[] }) {
  return (
    <div className="legend">
      {codes.map((k) => <div key={k} className="lg"><span className={k}>{STATUS[k].lab === STATUS[k].he ? '' : STATUS[k].lab}</span>{STATUS[k].he}</div>)}
    </div>
  );
}

export function Modal({ open, onClose, children }: { open: boolean; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k);
  }, [open, onClose]);
  if (!open) return null;
  return <div className="overlay" onClick={onClose}><div className="modal" onClick={(e) => e.stopPropagation()}><Bezel>{children}</Bezel></div></div>;
}

/** Small floating panel anchored to a trigger, closes on outside click. */
export function Popover({ trigger, children }: { trigger: (toggle: () => void) => ReactNode; children: (close: () => void) => ReactNode }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', h); return () => document.removeEventListener('mousedown', h);
  }, [open]);
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      {trigger(() => setOpen((o) => !o))}
      {open && <div className="popover" style={{ top: '110%', insetInlineStart: 0 }}>{children(() => setOpen(false))}</div>}
    </div>
  );
}

/** Tooltip that follows the pointer; used by chart marks. */
export function useTip() {
  const [tip, setTip] = useState<{ x: number; y: number; t: string } | null>(null);
  const bind = (t: string) => ({
    onMouseMove: (e: React.MouseEvent) => setTip({ x: e.clientX, y: e.clientY, t }),
    onMouseLeave: () => setTip(null),
  });
  const node = tip ? <div className="tip" style={{ left: tip.x + 12, top: tip.y - 34 }}>{tip.t}</div> : null;
  return { bind, node };
}
