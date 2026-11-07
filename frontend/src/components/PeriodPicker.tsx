import { monthBounds, monthLabel, weekBounds, yearBounds } from '../lib/dates';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Input } from '@/components/ui/input';

export type PeriodType = 'week' | 'month' | 'year' | 'custom';

export interface PeriodValue {
  type: PeriodType;
  week: string;
  month: string;
  year: string;
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
    const b = monthBounds(v.month);
    // monthBounds() clips date_to to today for the current, still-in-progress
    // month (see its own docstring) - reflected in the label too, so "up to
    // today" is never silently mistaken for the full month's data.
    const [y, m] = v.month.split('-').map(Number);
    const naturalEnd = new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10);
    const label = b.date_to < naturalEnd ? `${monthLabel(v.month)} (to ${b.date_to})` : monthLabel(v.month);
    return { label, ...b };
  }
  if (v.type === 'year' && v.year) {
    return { label: v.year, ...yearBounds(v.year) };
  }
  if (v.type === 'custom' && v.from && v.to) {
    // A day-matched reference month (Compare.tsx's referenceMonthPeriod)
    // always starts on the 1st and stays within that one month - shown as
    // "<Month> (to <date>)", same convention as the current month's own
    // clipped label above, instead of a bare, less legible date range.
    const sameMonth = v.from.slice(0, 7) === v.to.slice(0, 7);
    const label = v.from.endsWith('-01') && sameMonth ? `${monthLabel(v.from.slice(0, 7))} (to ${v.to})` : `${v.from} → ${v.to}`;
    return { label, date_from: v.from, date_to: v.to };
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
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-semibold">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          value={value.type}
          onValueChange={(v) => v && onChange({ ...value, type: v as PeriodType })}
        >
          <ToggleGroupItem value="week">Week</ToggleGroupItem>
          <ToggleGroupItem value="month">Month</ToggleGroupItem>
          <ToggleGroupItem value="year">Year</ToggleGroupItem>
          <ToggleGroupItem value="custom">Custom range</ToggleGroupItem>
        </ToggleGroup>
        {value.type === 'week' && (
          <Input type="week" value={value.week} onChange={(e) => onChange({ ...value, week: e.target.value })} />
        )}
        {value.type === 'month' && (
          <Input type="month" value={value.month} onChange={(e) => onChange({ ...value, month: e.target.value })} />
        )}
        {value.type === 'year' && (
          <Input
            type="number" inputMode="numeric" placeholder="YYYY" value={value.year}
            onChange={(e) => onChange({ ...value, year: e.target.value })}
          />
        )}
        {value.type === 'custom' && (
          <div className="flex items-center gap-2">
            <Input type="date" value={value.from} onChange={(e) => onChange({ ...value, from: e.target.value })} />
            <span className="text-xs text-muted-foreground">to</span>
            <Input type="date" value={value.to} onChange={(e) => onChange({ ...value, to: e.target.value })} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
