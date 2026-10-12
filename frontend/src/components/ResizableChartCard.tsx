import { useRef, type ReactNode } from 'react';
import { Maximize2 } from 'lucide-react';

const MIN_WIDTH = 340;
const MAX_WIDTH = 1200;

export { MIN_WIDTH as CHART_MIN_WIDTH, MAX_WIDTH as CHART_MAX_WIDTH };

// Draws the resize handle / maximize button OVER whatever chart card is
// passed as children - it does not size itself. Sizing is the containing
// SortableGrid item's job (via its `style` prop), since that's the actual
// flex child dnd-kit measures and animates - a size set on a node nested
// inside it has no effect on the real flex layout.
export function ResizableChartCard({
  onResize, onResetWidth, onMaximize, children,
}: {
  onResize: (width: number) => void;
  onResetWidth: () => void;
  onMaximize: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement | null>(null);

  function onResizeStart(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    const startX = e.clientX;
    const startWidth = ref.current?.getBoundingClientRect().width ?? 480;
    function onMove(ev: MouseEvent) {
      const next = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth + (ev.clientX - startX)));
      onResize(next);
    }
    function onUp() {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }

  return (
    <div ref={ref} className="relative w-full">
      <button
        type="button"
        onPointerDown={(e) => e.stopPropagation()}
        onClick={(e) => { e.stopPropagation(); onMaximize(); }}
        className="absolute right-10 top-2.5 z-20 rounded p-1 text-muted-foreground/0 transition-colors group-hover:text-muted-foreground/60 hover:bg-accent hover:text-foreground!"
        aria-label="Maximize this chart"
      >
        <Maximize2 className="size-4" />
      </button>
      {children}
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize this chart"
        onPointerDown={(e) => e.stopPropagation()}
        onMouseDown={onResizeStart}
        onDoubleClick={(e) => { e.stopPropagation(); onResetWidth(); }}
        title="Drag to resize, double-click to reset"
        className="absolute inset-y-0 -right-2.5 z-20 w-1.5 cursor-col-resize touch-none"
      >
        <div className="mx-auto h-full w-px bg-transparent transition-colors hover:bg-border active:bg-primary" />
      </div>
    </div>
  );
}
