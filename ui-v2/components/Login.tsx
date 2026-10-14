'use client';
import { useState } from 'react';
import { SignIn } from '@phosphor-icons/react';
import { Cta, Field, Note } from './ui';
import { ME } from '@/lib/mock';
import { useStore } from '@/lib/store';

export default function Login({ onLogin }: { onLogin: () => void }) {
  const { db } = useStore();
  const [name, setName] = useState(ME.name);
  const [pw, setPw] = useState('••••••••');
  const [err, setErr] = useState('');
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const n = name.trim();
    if (!db.staff.some((s) => s.name === n)) return setErr('שם המשתמש לא נמצא במערכת');
    if (!pw) return setErr('סיסמה שגויה');
    onLogin();
  };
  return (
    <div className="login">
      <div className="art">
        <h1>מערכת סידור עבודה<br />המערך הגריאטרי</h1>
        <p>תורנויות, סידור עבודה יומי, היעדרויות וכוננויות. במקום אחד.</p>
      </div>
      <div className="form">
        <section className="shell"><div className="core">
          <form onSubmit={submit}>
            <h2 className="sec">כניסה</h2>
            <Field label="שם משתמש"><input className="input" value={name} onChange={(e) => setName(e.target.value)} autoComplete="username" /></Field>
            <Field label="סיסמה"><input className="input" type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="current-password" /></Field>
            {err && <Note kind="err">{err}</Note>}
            <Cta type="submit" icon={<SignIn size={16} />}>כניסה</Cta>
            <p className="muted small" style={{ marginTop: 16 }}>דמו: כל השמות והנתונים בדויים.</p>
          </form>
        </div></section>
      </div>
    </div>
  );
}
