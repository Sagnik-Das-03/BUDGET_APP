const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'];

export function monthLabel(periodKey: string): string {
  const [year, month] = periodKey.split('-').map(Number);
  return `${MONTH_NAMES[month - 1]} ${year}`;
}

const iso = (d: Date) => d.toISOString().slice(0, 10);

/** Inclusive [date_from, date_to] bounds for a "YYYY-MM" period key - clipped
 * to today when periodKey is the CURRENT month, since no transaction dated
 * after today could exist anyway (a real aggregate never changes from this -
 * it's purely so callers can tell a still-in-progress month apart from a
 * completed one, e.g. to avoid comparing a partial month against a full one
 * and reporting a misleading swing - see Compare.tsx's monthToDatePeriod). */
export function monthBounds(periodKey: string): { date_from: string; date_to: string } {
  const [year, month] = periodKey.split('-').map(Number);
  const from = new Date(Date.UTC(year, month - 1, 1));
  const to = new Date(Date.UTC(year, month, 0)); // day 0 of next month = last day of this month
  const toIso = iso(to);
  const todayIso = todayValue();
  const clip = periodKey === thisMonthValue() && todayIso < toIso;
  return { date_from: iso(from), date_to: clip ? todayIso : toIso };
}

/** Same [date_from, date_to] as monthBounds, but clipped to at most dayCount
 * days into the month (clamped to the month's actual length) - lets a
 * REFERENCE month be compared fairly against a still-in-progress one
 * covering the same number of days, instead of a full month against a
 * partial one (which makes the partial one look artificially lower on
 * every metric - see Compare.tsx's "This month vs last month" preset). */
export function monthToDateBounds(periodKey: string, dayCount: number): { date_from: string; date_to: string } {
  const [year, month] = periodKey.split('-').map(Number);
  const from = new Date(Date.UTC(year, month - 1, 1));
  const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const to = new Date(Date.UTC(year, month - 1, Math.min(dayCount, daysInMonth)));
  return { date_from: iso(from), date_to: iso(to) };
}

/** Inclusive [date_from, date_to] Jan 1 - Dec 31 bounds for a "YYYY" year value. */
export function yearBounds(year: string): { date_from: string; date_to: string } {
  return { date_from: `${year}-01-01`, date_to: `${year}-12-31` };
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

function isoWeekValue(input: Date): string {
  const d = new Date(Date.UTC(input.getUTCFullYear(), input.getUTCMonth(), input.getUTCDate()));
  const dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum); // nearest Thursday
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil((((d.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(weekNo).padStart(2, '0')}`;
}

export function thisWeekValue(): string {
  return isoWeekValue(new Date());
}

/** Shift a "YYYY-Www" value by `delta` whole weeks, recomputing the ISO week
 * number rather than just subtracting - so crossing a year boundary (e.g.
 * week 1 going back a week) lands on the correct week of the correct year. */
export function shiftWeekValue(weekValue: string, delta: number): string {
  const monday = new Date(`${weekBounds(weekValue).date_from}T00:00:00Z`);
  monday.setUTCDate(monday.getUTCDate() + delta * 7);
  return isoWeekValue(monday);
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
