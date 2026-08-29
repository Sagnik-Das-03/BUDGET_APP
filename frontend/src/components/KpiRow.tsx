import {
  DndContext, type DragEndEvent, PointerSensor, closestCenter, useSensor, useSensors,
} from '@dnd-kit/core';
import {
  SortableContext, arrayMove, horizontalListSortingStrategy, useSortable,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useLocalStorage } from '../lib/useLocalStorage';

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
    opacity: isDragging ? 0.4 : 1,
  };
  return (
    <div ref={setNodeRef} style={style} className="kpi-tile" {...attributes} {...listeners}>
      <div className="kpi-label">{tile.label}</div>
      <div className="kpi-value">{tile.value}</div>
      {tile.sub && <div className={`kpi-goal-sub ${tile.sub.className || ''}`}>{tile.sub.text}</div>}
    </div>
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
      <p className="kpi-drag-hint">↕ Drag tiles to reorder — your layout is remembered on this device.</p>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={orderedIds} strategy={horizontalListSortingStrategy}>
          <div className="kpi-row">
            {ordered.map((tile) => <SortableTile key={tile.id} tile={tile} />)}
          </div>
        </SortableContext>
      </DndContext>
    </>
  );
}
