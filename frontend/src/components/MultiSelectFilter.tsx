import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';

export interface MultiSelectOption {
  value: string;
  label: string;
}

interface MultiSelectFilterProps {
  label: string;
  options: MultiSelectOption[];
  selected: string[];
  onSelectedChange: (values: string[]) => void;
  exclude: boolean;
  onExcludeChange: (exclude: boolean) => void;
  /** Called (in addition to closing the popover) when "Apply" is clicked - lets the
   * caller re-run its filter query immediately instead of waiting for a separate,
   * page-level "Filter" button. */
  onApply?: () => void;
  className?: string;
}

export function MultiSelectFilter({
  label, options, selected, onSelectedChange, exclude, onExcludeChange, onApply, className,
}: MultiSelectFilterProps) {
  const [open, setOpen] = useState(false);

  function toggle(value: string, checked: boolean) {
    onSelectedChange(checked ? [...selected, value] : selected.filter((v) => v !== value));
  }

  function applyAndClose() {
    onApply?.();
    setOpen(false);
  }

  const triggerLabel = selected.length === 0
    ? `Any ${label.toLowerCase()}`
    : `${label} ${exclude ? 'excl. ' : ''}(${selected.length})`;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className={className}>
          {triggerLabel}
          <ChevronDown className="size-3.5 opacity-60" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 p-3">
        <div className="mb-2.5 flex items-center justify-between gap-2 border-b pb-2.5">
          <Label htmlFor={`${label}-exclude`} className="text-xs text-muted-foreground">
            Exclude selected from results
          </Label>
          <Switch id={`${label}-exclude`} size="sm" checked={exclude} onCheckedChange={onExcludeChange} />
        </div>
        <div className="max-h-64 space-y-1.5 overflow-y-auto">
          {options.length === 0 ? (
            <p className="text-xs text-muted-foreground">No options.</p>
          ) : options.map((opt) => (
            <label key={opt.value} className="flex cursor-pointer items-center gap-2 text-sm">
              <Checkbox
                checked={selected.includes(opt.value)}
                onCheckedChange={(v) => toggle(opt.value, v === true)}
              />
              {opt.label}
            </label>
          ))}
        </div>
        <div className="mt-2 flex gap-2">
          {selected.length > 0 && (
            <Button variant="ghost" size="sm" className="h-7 flex-1 text-xs" onClick={() => onSelectedChange([])}>
              Clear
            </Button>
          )}
          <Button size="sm" className="h-7 flex-1 text-xs" onClick={applyAndClose}>
            Apply
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
