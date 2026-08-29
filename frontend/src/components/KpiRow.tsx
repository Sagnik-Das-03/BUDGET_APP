import {
  DndContext, type DragEndEvent, PointerSensor, closestCenter, useSensor, useSensors,
} from '@dnd-kit/core';
import {
  SortableContext, arrayMove, horizontalListSortingStrategy, useSortable,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical } from 'lucide-react';
import { useLocalStorage } from '../lib/useLocalStorage';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';

export interface KpiTileData {
  id: string;
  label: string;
  value: string;
  sub?: { text: string; className?: string };
}

function SortableTile({ tile }: { tile: KpiTileData }) {
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
          <div className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">{tile.label}</div>
          <GripVertical className="size-3.5 shrink-0 cursor-grab text-muted-foreground/0 transition-colors group-hover:text-muted-foreground/60 active:cursor-grabbing" />
        </div>
        <div className="mt-1.5 text-2xl font-bold tabular-nums">{tile.value}</div>
        {tile.sub && (
          <div
            className={cn(
              'mt-1.5 text-[11px]',
              tile.sub.className === 'met' && 'text-emerald-600 dark:text-emerald-400',
              tile.sub.className === 'behind' && 'text-destructive',
              !tile.sub.className && 'text-muted-foreground',
            )}
          >
            {tile.sub.text}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function KpiRow({ tiles }: { tiles: KpiTileData[] }) {
  const [order, setOrder] = useLocalStorage<string[]>('dashboard.kpiOrder', tiles.map((t) => t.id));
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const orderedIds = order.filter((id) => tiles.some((t) => t.id === id));
  tiles.forEach((t) => { if (!orderedIds.includes(t.id)) orderedIds.push(t.id); });
  const ordered = orderedIds.map((id) => tiles.find((t) => t.id === id)!).filter(Boolean);

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = orderedIds.indexOf(String(active.id));
    const newIndex = orderedIds.indexOf(String(over.id));
    setOrder(arrayMove(orderedIds, oldIndex, newIndex));
  }

  return (
    <>
      <p className="-mt-3.5 mb-4 text-[11px] text-muted-foreground">↕ Drag tiles to reorder — your layout is remembered on this device.</p>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={orderedIds} strategy={horizontalListSortingStrategy}>
          <div className="mb-6 flex flex-wrap gap-4">
            {ordered.map((tile) => <SortableTile key={tile.id} tile={tile} />)}
          </div>
        </SortableContext>
      </DndContext>
    </>
  );
}
