// Records the review video for the superadmin mockup.
// Usage: serve ./out on :3100 (python -m http.server 3100 --directory out), then `node scripts/record.mjs`.
// Output: review/version-b.mp4 (+ raw webm clips in review/raw). Uses the Chromium build cached by Playwright 1.58.
import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import { mkdirSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import ffmpeg from 'ffmpeg-static';

const BASE = process.env.BASE_URL ?? 'http://localhost:3100/';
const OUT = resolve('review');
const RAW = join(OUT, 'raw');
rmSync(RAW, { recursive: true, force: true });
mkdirSync(RAW, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const failures = [];
async function step(name, fn) {
  try { await fn(); } catch (e) { failures.push(`${name}: ${e.message.split('\n')[0]}`); }
}

// Visible cursor + click ripple, since recorded video has no OS cursor.
const CURSOR = `
  window.addEventListener('DOMContentLoaded', () => {
    const c = document.createElement('div');
    c.style.cssText = 'position:fixed;z-index:99999;width:22px;height:22px;border-radius:50%;background:rgba(14,26,31,.35);border:2px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.3);pointer-events:none;transform:translate(-50%,-50%);transition:transform .15s;left:-50px;top:-50px';
    document.body.appendChild(c);
    addEventListener('mousemove', (e) => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
    addEventListener('mousedown', () => { c.style.transform = 'translate(-50%,-50%) scale(.7)'; c.style.background = 'rgba(15,118,110,.6)'; }, true);
    addEventListener('mouseup', () => { c.style.transform = 'translate(-50%,-50%)'; c.style.background = 'rgba(14,26,31,.35)'; }, true);
  });`;

const card = (title, sub) => `<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;900&display=swap" rel="stylesheet"></head>
<body style="margin:0;height:100vh;display:grid;place-items:center;background:#0E1A1F;color:#fff;font-family:Heebo,sans-serif;
background-image:radial-gradient(circle at 20% 20%,rgba(13,148,136,.55),transparent 50%),radial-gradient(circle at 90% 80%,rgba(217,119,6,.25),transparent 45%)">
<div style="text-align:center;padding:24px"><div style="font-size:min(64px,10vw);font-weight:900;letter-spacing:-.03em;line-height:1.05">${title}</div>
<div style="margin-top:16px;font-size:min(22px,5vw);opacity:.75">${sub}</div></div></body></html>`;

async function glide(page, sel, opts = {}) {
  const el = page.locator(sel).first();
  await el.scrollIntoViewIfNeeded();
  const b = await el.boundingBox();
  if (!b) throw new Error(`no box for ${sel}`);
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 18 });
  await sleep(opts.pause ?? 250);
  if (opts.click !== false) await el.click();
  await sleep(opts.after ?? 700);
}
async function scrollBy(page, dy, steps = 12) {
  for (let i = 0; i < steps; i++) { await page.mouse.wheel(0, dy / steps); await sleep(45); }
  await sleep(350);
}
const nav = (page, tab) => glide(page, `aside.rail a[data-tab="${tab}"]`, { after: 1200 });

async function desktop(browser) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, recordVideo: { dir: RAW, size: { width: 1440, height: 900 } }, locale: 'he-IL' });
  await ctx.addInitScript(CURSOR);
  const page = await ctx.newPage();
  await page.setContent(card('Geri-shifts · ממשק חדש', 'גרסה B · Premium · מבט מנהל על · נתוני דמו בדויים'));
  await sleep(3000);

  await page.goto(BASE + '#/login'); await sleep(1500);
  await step('login', () => glide(page, 'button[type=submit]', { after: 1800 }));

  // דוחות וניהול (default tab)
  await step('reports', async () => {
    await glide(page, '.bar-seg', { click: false, after: 900 });
    await scrollBy(page, 700); await sleep(600);
    await glide(page, 'text=הרץ סריקה עכשיו', { after: 1800 });
    await scrollBy(page, 900);
    await glide(page, 'text=ניתוח שימוש במערכת', { after: 1200 });
    await scrollBy(page, 700); await sleep(800);
  });

  // סידור עבודה
  await step('work', async () => {
    await nav(page, 'work');
    for (const i of [8, 9, 9]) await glide(page, `.dgrid .cell:not([disabled]) >> nth=${i}`, { after: 450 });
    await glide(page, 'text=עריכה עם הערה', { after: 600 });
    await glide(page, '.dgrid .cell:not([disabled]) >> nth=15', { after: 800 });
    await page.locator('.modal input.input').fill('ישיבת צוות'); await sleep(600);
    await glide(page, '.modal button.cta', { after: 1200 });
    await glide(page, 'button:has-text("פנימית גריאטרית")', { after: 1400 });
    await scrollBy(page, 900); await sleep(500);
  });

  // סידור תורנויות
  await step('night', async () => {
    await nav(page, 'night');
    await glide(page, '.rcard .btn >> nth=0', { after: 1500 });
    await scrollBy(page, 500);
    await glide(page, 'text=רשימה', { after: 1000 });
    await scrollBy(page, 600);
    await glide(page, 'text=לוח', { after: 800 });
    await glide(page, 'text=שיבוץ אוטומטי מלא', { after: 2400 });
    await page.locator('#helper').scrollIntoViewIfNeeded(); await sleep(500);
    await glide(page, 'text=מצא החלפות אפשריות', { after: 1600 });
    await scrollBy(page, 700);
    await glide(page, '.btn.ok >> nth=0', { after: 1400 });
  });

  // ניהול בקשות
  await step('requests', async () => {
    await nav(page, 'requests');
    await glide(page, '.rcard .btn.ok >> nth=0', { after: 1500 });
    await scrollBy(page, 700); await sleep(500);
    await glide(page, '.gcell.ov', { click: false, after: 1200 });
    await scrollBy(page, 900);
  });

  // גאנט חודשי
  await step('gantt', async () => {
    await nav(page, 'gantt');
    await page.locator('table.t tbody tr >> nth=6').locator('select >> nth=0').selectOption('פנימית גריאטרית'); await sleep(700);
    await scrollBy(page, 600);
    await glide(page, 'text=שמור שיבוץ', { after: 1600 });
    await page.locator('table.t tbody tr >> nth=6').locator('select >> nth=1').selectOption('כחול'); await sleep(700);
    await glide(page, 'text=שמור שיבוץ', { after: 1600 });
  });

  // סידור כוננויות
  await step('oncall', async () => {
    await nav(page, 'oncall');
    await page.locator('.desk-only select >> nth=6').selectOption({ index: 2 }); await sleep(800);
    await scrollBy(page, 500);
    await glide(page, 'text=שמור שינויים', { after: 1400 });
  });

  // צוות
  await step('staff', async () => {
    await nav(page, 'staff');
    await glide(page, 'text=הוספת עובד/ת', { after: 900 });
    await scrollBy(page, 1500, 18);
    for (const d of [5, 6, 13]) await glide(page, `.split .cal button.day >> nth=${d - 1}`, { after: 400 });
    await sleep(800);
  });

  // הגדרות
  await step('settings', async () => {
    await nav(page, 'settings');
    await page.locator('input[placeholder="למשל: ערב חג"]').fill('ערב חג מדומה'); await sleep(500);
    await glide(page, 'text=הוסף יום', { after: 1500 });
  });

  await page.setContent(card('ובטלפון', 'אותן לשוניות, ניווט תחתון, גריד שבועי צפוף')); await sleep(2200);
  const v = page.video(); await ctx.close(); return v.path();
}

async function mobile(browser) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, recordVideo: { dir: RAW, size: { width: 390, height: 844 } }, locale: 'he-IL' });
  const page = await ctx.newPage();
  const tap = async (sel, after = 900) => { const el = page.locator(sel).first(); await el.scrollIntoViewIfNeeded(); await el.tap(); await sleep(after); };
  await page.goto(BASE + '#/login'); await sleep(1200);
  await step('m-login', () => tap('button[type=submit]', 1600));
  await step('m-reports', async () => { await page.mouse.wheel(0, 600); await sleep(900); });
  await step('m-work', async () => {
    await tap('.mob-nav a[href="#/work"]', 1400);
    await page.mouse.wheel(0, 380); await sleep(700);
    await tap('.dgrid .cell:not([disabled]) >> nth=9', 600); await tap('.dgrid .cell:not([disabled]) >> nth=9', 900);
  });
  await step('m-requests', async () => { await tap('.mob-nav a[href="#/requests"]', 1400); await page.mouse.wheel(0, 500); await sleep(900); });
  await step('m-more', async () => { await tap('.mob-nav button', 1200); await tap('.more-sheet a[href="#/oncall"]', 1400); await tap('.mob-only button.day >> nth=19', 1200); await page.mouse.wheel(0, 600); await sleep(1000); });
  await page.setContent(card('גרסה B', 'סוף הסיור')); await sleep(2000);
  const v = page.video(); await ctx.close(); return v.path();
}

const browser = await chromium.launch({ headless: true });
const deskClip = await desktop(browser);
const mobClip = await mobile(browser);
await browser.close();

renameSync(deskClip, join(RAW, '1-desktop.webm'));
renameSync(mobClip, join(RAW, '2-mobile.webm'));

// Desktop as-is; phone centered on a dark 1440x900 canvas; then join.
const run = (args) => execFileSync(ffmpeg, ['-y', '-loglevel', 'error', ...args], { stdio: 'inherit' });
run(['-i', join(RAW, '1-desktop.webm'), '-vf', 'fps=30,format=yuv420p', '-c:v', 'libx264', '-crf', '22', '-preset', 'medium', join(RAW, '1.mp4')]);
run(['-i', join(RAW, '2-mobile.webm'), '-vf', 'scale=-2:860,pad=1440:900:(ow-iw)/2:(oh-ih)/2:color=0x0E1A1F,fps=30,format=yuv420p', '-c:v', 'libx264', '-crf', '22', '-preset', 'medium', join(RAW, '2.mp4')]);
writeFileSync(join(RAW, 'list.txt'), `file '1.mp4'\nfile '2.mp4'\n`);
run(['-f', 'concat', '-safe', '0', '-i', join(RAW, 'list.txt'), '-c', 'copy', '-movflags', '+faststart', join(OUT, 'version-b.mp4')]);

console.log(`video: ${join(OUT, 'version-b.mp4')}`);
if (failures.length) { console.log('steps that failed (video continued):'); failures.forEach((f) => console.log(' - ' + f)); }
