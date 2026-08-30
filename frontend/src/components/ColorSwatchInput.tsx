import { cn } from '@/lib/utils';

interface Props {
  value: string;
  onChange: (value: string) => void;
  title?: string;
  size?: 'sm' | 'md';
  className?: string;
}

/** A circular color-picker trigger with a consistent look across browsers -
 * the visible swatch is a plain div painted with the current color, not the
 * native <input type="color"> rendering (which varies a lot per browser and
 * looks like a flat, dated square). The native input still sits on top,
 * fully transparent, so clicking it opens the OS color picker as normal. */
export function ColorSwatchInput({ value, onChange, title, size = 'md', className }: Props) {
  return (
    <span
      className={cn(
        'relative inline-block shrink-0 rounded-full ring-1 ring-border shadow-sm transition-transform hover:scale-110 hover:shadow-md',
        size === 'sm' ? 'size-4' : 'size-8',
        className,
      )}
      style={{ backgroundColor: value }}
    >
      <input
        type="color"
        value={value}
        title={title}
        onChange={(e) => onChange(e.target.value)}
        className="absolute inset-0 size-full cursor-pointer opacity-0"
      />
    </span>
  );
}
