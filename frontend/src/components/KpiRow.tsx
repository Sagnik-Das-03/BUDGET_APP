import { useRef, useState } from 'react';
import {
  DndContext, type DragEndEvent, PointerSensor, closestCenter, useSensor, useSensors,
} from '@dnd-kit/core';
import {
  SortableContext, arrayMove, horizontalListSortingStrategy, useSortable,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Eye, EyeOff, GripVertical, Info, Maximize2, X } from 'lucide-react';
import { useLocalStorage } from '../lib/useLocalStorage';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

const MIN_TILE_WIDTH = 150;
const MAX_TILE_WIDTH = 440;

// Masked in place of the real value/sub-text while numbers are hidden - a
// fixed string rather than something derived from the real value's length,
// so the mask itself can't leak a hint (e.g. "big number vs small number").
const MASK = '••••••';

export interface KpiTileData {
  id: string;
  label: string;
  value: string;
  /** Plain-English explanation of what this KPI means and how it's computed - shown in a hover tooltip. */
  description?: string;
  sub?: { text: string; className?: string };
}

function SortableTile({
  tile, revealed, width, onHide, onMaximize, onResize, onResetWidth,
}: {
  tile: KpiTileData;
  revealed: boolean;
  width: number | undefined;
  onHide: (id: string) => void;
  onMaximize: (tile: KpiTileData) => void;
  onResize: (id: string, width: number) => void;
  onResetWidth: (id: string) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: tile.id });
  const cardRef = useRef<HTMLDivElement | null>(null);
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    flex: width ? `0 0 ${width}px` : undefined,
  };

  function onResizeStart(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    const startX = e.clientX;
    const startWidth = width ?? cardRef.current?.getBoundingClientRect().width ?? 190;
    function onMove(ev: MouseEvent) {
      const next = Math.min(MAX_TILE_WIDTH, Math.max(MIN_TILE_WIDTH, startWidth + (ev.clientX - startX)));
      onResize(tile.id, next);
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
    <Card
      ref={(node) => { setNodeRef(node); cardRef.current = node; }}
      style={style}
      className={cn(
        'group relative min-w-[150px] flex-1 py-0 select-none',
        isDragging && 'opacity-40 shadow-lg',
      )}
      {...attributes}
      {...listeners}
    >
      <CardContent className="px-5 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1">
            <div className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">{tile.label}</div>
            {tile.description && (
              <Tooltip>
                <TooltipTrigger
                  onPointerDown={(e) => e.stopPropagation()}
                  className="text-muted-foreground/50 hover:text-muted-foreground"
                  aria-label={`What is ${tile.label}?`}
                >
                  <Info className="size-3" />
                </TooltipTrigger>
                <TooltipContent>{tile.description}</TooltipContent>
              </Tooltip>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => { e.stopPropagation(); onMaximize(tile); }}
              className="text-muted-foreground/0 transition-colors group-hover:text-muted-foreground/60 hover:text-foreground!"
              aria-label={`Maximize ${tile.label} tile`}
            >
              <Maximize2 className="size-3.5" />
            </button>
            <button
              type="button"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => { e.stopPropagation(); onHide(tile.id); }}
              className="text-muted-foreground/0 transition-colors group-hover:text-muted-foreground/60 hover:text-destructive!"
              aria-label={`Hide ${tile.label} tile`}
            >
              <EyeOff className="size-3.5" />
            </button>
            <GripVertical className="size-3.5 shrink-0 cursor-grab text-muted-foreground/0 transition-colors group-hover:text-muted-foreground/60 active:cursor-grabbing" />
          </div>
        </div>
        <div className="mt-1.5 text-2xl font-bold tabular-nums">{revealed ? tile.value : MASK}</div>
        {tile.sub && (
          <div
            className={cn(
              'mt-1.5 text-[11px]',
              tile.sub.className === 'met' && 'text-emerald-600 dark:text-emerald-400',
              tile.sub.className === 'behind' && 'text-destructive',
              !tile.sub.className && 'text-muted-foreground',
            )}
          >
            {revealed ? tile.sub.text : MASK}
          </div>
        )}
      </CardContent>
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label={`Resize ${tile.label} tile`}
        onPointerDown={(e) => e.stopPropagation()}
        onMouseDown={onResizeStart}
        onDoubleClick={(e) => { e.stopPropagation(); onResetWidth(tile.id); }}
        title="Drag to resize, double-click to reset"
        className="absolute inset-y-0 right-0 z-10 w-1.5 translate-x-1/2 cursor-col-resize touch-none group/resize"
      >
        <div className="mx-auto h-full w-px bg-transparent transition-colors group-hover/resize:bg-border group-active/resize:bg-primary" />
      </div>
    </Card>
  );
}

export function KpiRow({ tiles }: { tiles: KpiTileData[] }) {
  const [order, setOrder] = useLocalStorage<string[]>('dashboard.kpiOrder', tiles.map((t) => t.id));
  const [hidden, setHidden] = useLocalStorage<string[]>('dashboard.kpiHidden', []);
  const [widths, setWidths] = useLocalStorage<Record<string, number>>('dashboard.kpiWidths', {});
  // Deliberately NOT persisted - the whole point is that numbers start
  // masked every time the dashboard is opened (e.g. screen-sharing, or
  // someone glancing at your phone), not just once per device.
  const [revealed, setRevealed] = useState(false);
  const [maximized, setMaximized] = useState<KpiTileData | null>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const orderedIds = order.filter((id) => tiles.some((t) => t.id === id));
  tiles.forEach((t) => { if (!orderedIds.includes(t.id)) orderedIds.push(t.id); });
  const visibleIds = orderedIds.filter((id) => !hidden.includes(id));
  const ordered = visibleIds.map((id) => tiles.find((t) => t.id === id)!).filter(Boolean);
  const hiddenTiles = tiles.filter((t) => hidden.includes(t.id));

  function hideTile(id: string) {
    if (!hidden.includes(id)) setHidden([...hidden, id]);
  }
  function unhideTile(id: string) {
    setHidden(hidden.filter((x) => x !== id));
  }
  function resizeTile(id: string, width: number) {
    setWidths({ ...widths, [id]: width });
  }
  function resetTileWidth(id: string) {
    if (!(id in widths)) return;
    const next = { ...widths };
    delete next[id];
    setWidths(next);
  }

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = visibleIds.indexOf(String(active.id));
    const newIndex = visibleIds.indexOf(String(over.id));
    setOrder([...arrayMove(visibleIds, oldIndex, newIndex), ...hidden]);
  }

  return (
    <>
      <div className="-mt-3.5 mb-4 flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] text-muted-foreground">↕ Drag to reorder, drag the right edge to resize — remembered on this device.</p>
        <Button variant="ghost" size="sm" className="h-7 gap-1.5 text-xs" onClick={() => setRevealed((r) => !r)}>
          {revealed ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
          {revealed ? 'Hide numbers' : 'Show numbers'}
        </Button>
      </div>
      {hiddenTiles.length > 0 && (
        <div className="-mt-2 mb-4 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
          <span>Hidden:</span>
          {hiddenTiles.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => unhideTile(t.id)}
              className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 hover:bg-accent"
            >
              {t.label} <X className="size-3" />
            </button>
          ))}
        </div>
      )}
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={visibleIds} strategy={horizontalListSortingStrategy}>
          <div className="mb-6 flex flex-wrap gap-4">
            {ordered.map((tile) => (
              <SortableTile
                key={tile.id}
                tile={tile}
                revealed={revealed}
                width={widths[tile.id]}
                onHide={hideTile}
                onMaximize={setMaximized}
                onResize={resizeTile}
                onResetWidth={resetTileWidth}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>

      <Dialog open={!!maximized} onOpenChange={(open) => !open && setMaximized(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{maximized?.label}</DialogTitle>
          </DialogHeader>
          <div className="text-5xl font-bold tabular-nums">{revealed ? maximized?.value : MASK}</div>
          {maximized?.sub && (
            <div
              className={cn(
                'text-sm',
                maximized.sub.className === 'met' && 'text-emerald-600 dark:text-emerald-400',
                maximized.sub.className === 'behind' && 'text-destructive',
                !maximized.sub.className && 'text-muted-foreground',
              )}
            >
              {revealed ? maximized.sub.text : MASK}
            </div>
          )}
          {maximized?.description && (
            <p className="text-sm text-muted-foreground">{maximized.description}</p>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
