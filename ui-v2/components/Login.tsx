'use client';
import { useState } from 'react';
import { SignIn } from '@phosphor-icons/react';
import { Cta, Field, Note } from './ui';
import { DEMO_USERS } from '@/lib/roles';
import { useStore } from '@/lib/store';

export default function Login({ onLogin }: { onLogin: () => void }) {
  const { login, live } = useStore();
  const [name, setName] = useState(live ? '' : DEMO_USERS[0].name);
  const [pw, setPw] = useState(live ? '' : '••••••••');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const go = async (n: string) => {
    if (!n) return setErr('שם המשתמש לא נמצא במערכת');
    if (!pw) return setErr('סיסמה שגויה');
    setBusy(true); setErr('');
    const e = await login(n, pw);
    setBusy(false);
    if (e) return setErr(e);
    onLogin();
  };
  const submit = (e: React.FormEvent) => { e.preventDefault(); go(name.trim()); };
  return (
    <div className="login">
      {/* Decorative month grid: a few cells lit like night shifts. */}
      <div className="login-grid" aria-hidden="true">
        {Array.from({ length: 140 }, (_, i) => <i key={i} className={LIT.has(i % 49) ? 'n' : undefined} />)}
      </div>
      <div className="login-col">
        <div className="login-brand">
          <h1>המערך הגריאטרי</h1>
          <p>סידור עבודה ותורנויות</p>
        </div>
        <div className="login-card">
          <form onSubmit={submit}>
            <Field label="שם משתמש"><input className="input" value={name} onChange={(e) => setName(e.target.value)} autoComplete="username" /></Field>
            <Field label="סיסמה"><input className="input" type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="current-password" /></Field>
            {err && <Note kind="err">{err}</Note>}
            <Cta type="submit" variant="teal" icon={<SignIn size={16} />} disabled={busy}>{busy ? 'מתחבר/ת...' : 'כניסה'}</Cta>
            <p className="muted small" style={{ margin: '14px 0 0', textAlign: 'center' }}>שכחת סיסמה? פנה/י למנהל המערכת.</p>
          </form>
          {!live && (
            <div className="demo-users">
              <p className="muted small">דמו: כניסה מהירה לפי תפקיד (כל השמות והנתונים בדויים)</p>
              <div className="chips">
                {DEMO_USERS.map((u) => (
                  <button key={u.name} type="button" className="chip" data-user={u.role} onClick={() => go(u.name)}>
                    <b>{u.role}</b>{u.name}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const LIT = new Set([2, 8, 12, 17, 21, 24, 29, 31, 38, 40, 45]);
