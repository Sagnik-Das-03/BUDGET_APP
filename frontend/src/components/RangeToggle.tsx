import type { RangeKey } from '../lib/types';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';

const RANGES: { key: RangeKey; label: string }[] = [
  { key: 'this_week', label: 'This Week' },
  { key: 'this_month', label: 'This Month' },
  { key: 'this_year', label: 'This Year' },
  { key: 'all_time', label: 'All Time' },
];

export function RangeToggle({ value, onChange }: { value: RangeKey; onChange: (r: RangeKey) => void }) {
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      value={value}
      onValueChange={(v) => v && onChange(v as RangeKey)}
      className="bg-card"
    >
      {RANGES.map((r) => (
        <ToggleGroupItem key={r.key} value={r.key} className="text-xs sm:text-sm">
          {r.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
