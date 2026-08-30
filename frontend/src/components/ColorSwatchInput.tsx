import { useState } from 'react';
import { HexColorPicker } from 'react-colorful';
import { cn } from '@/lib/utils';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Input } from '@/components/ui/input';

interface Props {
  value: string;
  onChange: (value: string) => void;
  title?: string;
  size?: 'sm' | 'md';
  className?: string;
}

const HEX_RE = /^#[0-9a-fA-F]{6}$/;

/** A circular color-picker trigger that opens an in-page popover (react-colorful's
 * saturation/hue picker + a hex field) instead of the browser's native <input
 * type="color">, which on Windows opens the OS's own classic color dialog - a
 * jarring, unstyleable, decades-old UI that breaks out of the page entirely. */
export function ColorSwatchInput({ value, onChange, title, size = 'md', className }: Props) {
  const [open, setOpen] = useState(false);
  const [hexInput, setHexInput] = useState(value);

  function commitHex(raw: string) {
    const v = raw.startsWith('#') ? raw : `#${raw}`;
    if (HEX_RE.test(v)) onChange(v.toUpperCase());
  }

  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); if (o) setHexInput(value); }}>
      <PopoverTrigger asChild>
        <button
          type="button"
          title={title}
          aria-label={title ?? 'Choose color'}
          className={cn(
            'inline-block shrink-0 cursor-pointer rounded-full ring-1 ring-border shadow-sm transition-transform hover:scale-110 hover:shadow-md',
            size === 'sm' ? 'size-4' : 'size-8',
            className,
          )}
          style={{ backgroundColor: value }}
        />
      </PopoverTrigger>
      <PopoverContent className="w-auto space-y-3 p-3">
        <HexColorPicker
          color={value}
          onChange={(c) => { const hex = c.toUpperCase(); onChange(hex); setHexInput(hex); }}
        />
        <div className="flex items-center gap-2">
          <span className="size-7 shrink-0 rounded-md ring-1 ring-border" style={{ backgroundColor: value }} />
          <Input
            value={hexInput}
            onChange={(e) => setHexInput(e.target.value)}
            onBlur={() => commitHex(hexInput)}
            onKeyDown={(e) => { if (e.key === 'Enter') commitHex(hexInput); }}
            className="h-8 font-mono text-xs"
            maxLength={7}
            spellCheck={false}
          />
        </div>
      </PopoverContent>
    </Popover>
  );
}
