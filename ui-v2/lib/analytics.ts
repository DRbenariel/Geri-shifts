// Usage log for the live site (analytics_log, the same rows Streamlit's log_event writes).
// Fire-and-forget: a failure (read-only mode, no session, offline) is never shown to the user.
'use client';

const KEY = 'geri_session_id';

export function sessionId(): string {
  try {
    let id = sessionStorage.getItem(KEY);
    if (!id) { id = crypto.randomUUID(); sessionStorage.setItem(KEY, id); }
    return id;
  } catch { return ''; }
}

export function track(event_type: string, detail_1 = '', detail_2 = '') {
  try {
    fetch('/api/events', {
      method: 'POST', credentials: 'same-origin', keepalive: true,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event_type, detail_1, detail_2, session_id: sessionId(), vw: window.innerWidth }),
    }).catch(() => {});
  } catch { /* never breaks the page */ }
}
