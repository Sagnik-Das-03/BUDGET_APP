import type { RangeKey } from '../lib/types';

const RANGES: { key: RangeKey; label: string }[] = [
  { key: 'this_week', label: 'This Week' },
  { key: 'this_month', label: 'This Month' },
  { key: 'this_year', label: 'This Year' },
  { key: 'all_time', label: 'All Time' },
];

export function RangeToggle({ value, onChange }: { value: RangeKey; onChange: (r: RangeKey) => void }) {
  return (
    <div className="range-toggle">
      {RANGES.map((r) => (
        <button key={r.key} className={r.key === value ? 'active' : ''} onClick={() => onChange(r.key)}>
          {r.label}
        </button>
      ))}
    </div>
  );
}
