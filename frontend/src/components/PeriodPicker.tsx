import { monthBounds, monthLabel, weekBounds } from '../lib/dates';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Input } from '@/components/ui/input';

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
          <ToggleGroupItem value="custom">Custom range</ToggleGroupItem>
        </ToggleGroup>
        {value.type === 'week' && (
          <Input type="week" value={value.week} onChange={(e) => onChange({ ...value, week: e.target.value })} />
        )}
        {value.type === 'month' && (
          <Input type="month" value={value.month} onChange={(e) => onChange({ ...value, month: e.target.value })} />
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
