import { monthBounds, monthLabel, weekBounds } from '../lib/dates';

export type PeriodType = 'week' | 'month' | 'custom';

export interface PeriodValue {
  type: PeriodType;
  week: string;
  month: string;
  from: string;
  to: string;
}

export interface ResolvedPeriod {
  label: string;
  date_from: string;
  date_to: string;
}

export function resolvePeriod(v: PeriodValue): ResolvedPeriod | null {
  if (v.type === 'week' && v.week) {
    const b = weekBounds(v.week);
    return { label: `Week of ${b.date_from}`, ...b };
  }
  if (v.type === 'month' && v.month) {
    return { label: monthLabel(v.month), ...monthBounds(v.month) };
  }
  if (v.type === 'custom' && v.from && v.to) {
    return { label: `${v.from} → ${v.to}`, date_from: v.from, date_to: v.to };
  }
  return null;
}

interface Props {
  title: string;
  value: PeriodValue;
  onChange: (v: PeriodValue) => void;
}

export function PeriodPicker({ title, value, onChange }: Props) {
  return (
    <div className="chart-card">
      <h3 style={{ marginBottom: 10 }}>{title}</h3>
      <div className="form-row" style={{ marginBottom: 8 }}>
        {(['week', 'month', 'custom'] as PeriodType[]).map((t) => (
          <label key={t} style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 4 }}>
            <input type="radio" name={`${title}-type`} checked={value.type === t}
              onChange={() => onChange({ ...value, type: t })} />
            {t === 'week' ? 'Week' : t === 'month' ? 'Month' : 'Custom range'}
          </label>
        ))}
      </div>
      {value.type === 'week' && (
        <input type="week" value={value.week} onChange={(e) => onChange({ ...value, week: e.target.value })} />
      )}
      {value.type === 'month' && (
        <input type="month" value={value.month} onChange={(e) => onChange({ ...value, month: e.target.value })} />
      )}
      {value.type === 'custom' && (
        <div className="form-row" style={{ marginBottom: 0 }}>
          <input type="date" value={value.from} onChange={(e) => onChange({ ...value, from: e.target.value })} />
          <span style={{ fontSize: 13 }}>to</span>
          <input type="date" value={value.to} onChange={(e) => onChange({ ...value, to: e.target.value })} />
        </div>
      )}
    </div>
  );
}
