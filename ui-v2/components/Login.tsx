'use client';
import { useState } from 'react';
import { SignIn } from '@phosphor-icons/react';
import { Cta, Field, Note } from './ui';
import { DEMO_USERS } from '@/lib/roles';
import { useStore } from '@/lib/store';

export default function Login({ onLogin }: { onLogin: (name: string) => void }) {
  const { login } = useStore();
  const [name, setName] = useState(DEMO_USERS[0].name);
  const [pw, setPw] = useState('••••••••');
  const [err, setErr] = useState('');
  const go = (n: string) => {
    if (!pw) return setErr('סיסמה שגויה');
    if (!login(n)) return setErr('שם המשתמש לא נמצא במערכת');
    onLogin(n);
  };
  const submit = (e: React.FormEvent) => { e.preventDefault(); go(name.trim()); };
  return (
    <div className="login">
      <div className="art">
        <h1>מערכת סידור עבודה<br />המערך הגריאטרי</h1>
      </div>
      <div className="form">
        <section className="shell"><div className="core">
          <form onSubmit={submit}>
            <h2 className="sec">כניסה</h2>
            <Field label="שם משתמש"><input className="input" value={name} onChange={(e) => setName(e.target.value)} autoComplete="username" /></Field>
            <Field label="סיסמה"><input className="input" type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="current-password" /></Field>
            {err && <Note kind="err">{err}</Note>}
            <Cta type="submit" icon={<SignIn size={16} />}>כניסה</Cta>
            <p className="muted small" style={{ margin: '16px 0 4px' }}>שכחת סיסמה? פנה/י למנהל המערכת.</p>
          </form>
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
        </div></section>
      </div>
    </div>
  );
}
