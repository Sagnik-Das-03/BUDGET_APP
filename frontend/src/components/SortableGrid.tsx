import type { ReactNode } from 'react';
import {
  DndContext, type DragEndEvent, PointerSensor, closestCenter, useSensor, useSensors,
} from '@dnd-kit/core';
import { SortableContext, arrayMove, rectSortingStrategy, useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical } from 'lucide-react';
import { useLocalStorage } from '../lib/useLocalStorage';
import { cn } from '@/lib/utils';

export interface SortableGridItem {
  id: string;
  node: ReactNode;
}

function SortableTile({ id, handle, children }: { id: string; handle: boolean; children: ReactNode }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });
  const style = { transform: CSS.Transform.toString(transform), transition };

  // Whole-tile dragging suits inert content (a KPI-style tile with just
  // text) - a dedicated grip handle is for tiles with their own interactive
  // content (chart type toggles, click-to-drill, dropdowns), where spreading
  // the drag listeners over the whole card would swallow those clicks.
  if (!handle) {
    return (
      <div
        ref={setNodeRef} style={style} className={cn(isDragging && 'z-10 opacity-40')}
        {...attributes} {...listeners}
      >
        {children}
      </div>
    );
  }

  return (
    <div ref={setNodeRef} style={style} className={cn('group relative', isDragging && 'z-10 opacity-40 shadow-lg')}>
      <button
        type="button"
        className="absolute right-2.5 top-2.5 z-10 cursor-grab rounded p-1 text-muted-foreground/0 transition-colors group-hover:text-muted-foreground/60 hover:bg-accent active:cursor-grabbing"
        aria-label="Drag to reorder"
        {...attributes}
        {...listeners}
      >
        <GripVertical className="size-4" />
      </button>
      {children}
    </div>
  );
}

interface SortableGridProps {
  /** localStorage key this grid's order is saved under - keep it unique per grid. */
  storageKey: string;
  items: SortableGridItem[];
  className?: string;
  /** True for tiles with their own interactive content (charts, dropdowns) -
   * renders a dedicated grip handle instead of making the whole tile a drag source. */
  handle?: boolean;
}

// Generic drag-to-reorder grid, order persisted to localStorage (so it's
// remembered on this device, same as KpiRow's tile order). Any item not
// present in the saved order (a tile added after the user last reordered)
// is appended at the end rather than dropped.
export function SortableGrid({ storageKey, items, className, handle = false }: SortableGridProps) {
  const [order, setOrder] = useLocalStorage<string[]>(storageKey, items.map((i) => i.id));
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const orderedIds = order.filter((id) => items.some((i) => i.id === id));
  for (const item of items) {
    if (!orderedIds.includes(item.id)) orderedIds.push(item.id);
  }
  const ordered = orderedIds.map((id) => items.find((i) => i.id === id)!).filter(Boolean);

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = orderedIds.indexOf(String(active.id));
    const newIndex = orderedIds.indexOf(String(over.id));
    setOrder(arrayMove(orderedIds, oldIndex, newIndex));
  }

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={orderedIds} strategy={rectSortingStrategy}>
        <div className={className}>
          {ordered.map((item) => (
            <SortableTile key={item.id} id={item.id} handle={handle}>{item.node}</SortableTile>
          ))}
        </div>
      </SortableContext>
    </DndContext>
  );
}
