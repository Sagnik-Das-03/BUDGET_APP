const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'];

export function monthLabel(periodKey: string): string {
  const [year, month] = periodKey.split('-').map(Number);
  return `${MONTH_NAMES[month - 1]} ${year}`;
}

const iso = (d: Date) => d.toISOString().slice(0, 10);

/** Inclusive [date_from, date_to] bounds for a "YYYY-MM" period key. */
export function monthBounds(periodKey: string): { date_from: string; date_to: string } {
  const [year, month] = periodKey.split('-').map(Number);
  const from = new Date(Date.UTC(year, month - 1, 1));
  const to = new Date(Date.UTC(year, month, 0)); // day 0 of next month = last day of this month
  return { date_from: iso(from), date_to: iso(to) };
}

/** Inclusive [date_from, date_to] Monday-Sunday bounds for a "YYYY-Www" ISO week
 * value (what <input type="week"> produces). */
export function weekBounds(weekValue: string): { date_from: string; date_to: string } {
  const [yearStr, weekStr] = weekValue.split('-W');
  const year = Number(yearStr), week = Number(weekStr);
  // ISO 8601: the week containing the year's first Thursday is week 1.
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const jan4Day = jan4.getUTCDay() || 7; // Monday=1 .. Sunday=7
  const monday = new Date(jan4);
  monday.setUTCDate(jan4.getUTCDate() - jan4Day + 1 + (week - 1) * 7);
  const sunday = new Date(monday);
  sunday.setUTCDate(monday.getUTCDate() + 6);
  return { date_from: iso(monday), date_to: iso(sunday) };
}

export function thisWeekValue(): string {
  const now = new Date();
  const d = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
  const dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum); // nearest Thursday
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil((((d.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(weekNo).padStart(2, '0')}`;
}

export function thisMonthValue(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

export function shiftMonthValue(monthValue: string, delta: number): string {
  const [year, month] = monthValue.split('-').map(Number);
  const d = new Date(Date.UTC(year, month - 1 + delta, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
}

export function todayValue(): string {
  return iso(new Date());
}
