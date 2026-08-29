import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';

interface Props {
  options: { type: string; label: string }[];
  value: string;
  onChange: (type: string) => void;
}

export function ChartTypeToggle({ options, value, onChange }: Props) {
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      value={value}
      onValueChange={(v) => v && onChange(v)}
    >
      {options.map((opt) => (
        <ToggleGroupItem key={opt.type} value={opt.type} className="px-2.5 text-xs">
          {opt.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
