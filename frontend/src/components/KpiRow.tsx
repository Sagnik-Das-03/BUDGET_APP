import { useState } from 'react';
import {
  DndContext, type DragEndEvent, PointerSensor, closestCenter, useSensor, useSensors,
} from '@dnd-kit/core';
import {
  SortableContext, arrayMove, horizontalListSortingStrategy, useSortable,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Eye, EyeOff, GripVertical, Info, X } from 'lucide-react';
import { useLocalStorage } from '../lib/useLocalStorage';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

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
  tile, revealed, onHide,
}: {
  tile: KpiTileData;
  revealed: boolean;
  onHide: (id: string) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: tile.id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };
  return (
    <Card
      ref={setNodeRef}
      style={style}
      className={cn(
        'group relative min-w-[170px] flex-1 py-0 select-none',
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
    </Card>
  );
}

export function KpiRow({ tiles }: { tiles: KpiTileData[] }) {
  const [order, setOrder] = useLocalStorage<string[]>('dashboard.kpiOrder', tiles.map((t) => t.id));
  const [hidden, setHidden] = useLocalStorage<string[]>('dashboard.kpiHidden', []);
  // Deliberately NOT persisted - the whole point is that numbers start
  // masked every time the dashboard is opened (e.g. screen-sharing, or
  // someone glancing at your phone), not just once per device.
  const [revealed, setRevealed] = useState(false);
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
        <p className="text-[11px] text-muted-foreground">↕ Drag tiles to reorder — your layout is remembered on this device.</p>
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
              <SortableTile key={tile.id} tile={tile} revealed={revealed} onHide={hideTile} />
            ))}
          </div>
        </SortableContext>
      </DndContext>
    </>
  );
}
