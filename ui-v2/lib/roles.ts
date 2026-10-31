// Tabs per role. Mirrors backend/geri_core/constants.py tabs_for_role / default_tab_for_role (tested there),
// and the mobile bottom bar from SCREENS_PLAN.md §2.
import type { Role } from './mock';

export type TabKey = 'settings' | 'night' | 'submit' | 'staff' | 'reports' | 'oncall' | 'gantt' | 'work' | 'requests';

export function tabsForRole(role: Role): TabKey[] {
  const t: TabKey[] = ['settings'];
  if (!['מנהל מחלקה', 'רופא בכיר', 'מנהל/ת'].includes(role)) t.push('night');
  if (!['מנהל/ת', 'מנהל על', 'מנהל מחלקה'].includes(role)) t.push('submit');
  if (role === 'מנהל על') t.push('staff', 'reports');
  if (role === 'מנהל על' || role === 'מנהל/ת') t.push('oncall', 'gantt');
  if (role !== 'תורן חוץ') t.push('work');
  if (['מנהל על', 'מנהל/ת', 'מנהל מחלקה'].includes(role)) t.push('requests');
  return t;
}

const HOME: Partial<Record<Role, TabKey>> = { 'מנהל על': 'reports', 'מנהל/ת': 'gantt', 'מנהל מחלקה': 'work', 'רופא בכיר': 'work' };
export function homeTab(role: Role): TabKey {
  const h = HOME[role] ?? 'submit';
  return tabsForRole(role).includes(h) ? h : tabsForRole(role)[0];
}

export const MOBILE_PRIMARY: Record<Role, TabKey[]> = {
  'מנהל על': ['reports', 'work', 'requests', 'night'],
  'מנהל/ת': ['gantt', 'work', 'requests', 'oncall'],
  'מנהל מחלקה': ['work', 'requests', 'settings'],
  'רופא בכיר': ['work', 'submit', 'settings'],
  'מתמחה': ['submit', 'night', 'work', 'settings'],
  'תורן חוץ': ['submit', 'night', 'settings'],
};

export const isAdmin = (r: Role) => r === 'מנהל על' || r === 'מנהל/ת';

/** Demo quick-pick on the login screen: one fictional user per role, chosen because they have data in the mock. */
export const DEMO_USERS: { name: string; role: Role }[] = [
  { name: 'ענבל רז', role: 'מנהל על' },
  { name: 'מיכל דוד', role: 'מנהל/ת' },
  { name: 'ד"ר שולמית גל', role: 'מנהל מחלקה' },
  { name: 'ד"ר רחל אבירם', role: 'רופא בכיר' },
  { name: 'נועה ברק', role: 'מתמחה' },
  { name: 'ד"ר אמיר חדד', role: 'תורן חוץ' },
];
