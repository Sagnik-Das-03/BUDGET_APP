import { useCallback, useRef } from 'react';
import { useLocalStorage } from './useLocalStorage';

/**
 * A persisted width (in px) for a right-anchored panel, plus mousedown
 * handler for a drag handle on its LEFT edge. Since the panel is pinned to
 * the right edge of the viewport, its width is just the distance from the
 * cursor to the right edge - no need to track a drag delta.
 */
export function useResizableWidth(storageKey: string, defaultWidth: number, min = 320, max = 1100) {
  const [width, setWidth] = useLocalStorage(storageKey, defaultWidth);
  const draggingRef = useRef(false);

  const onDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    draggingRef.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    function onMove(ev: MouseEvent) {
      if (!draggingRef.current) return;
      const next = window.innerWidth - ev.clientX;
      setWidth(Math.min(max, Math.max(min, next)));
    }
    function onUp() {
      draggingRef.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    }
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [max, min]);

  return { width, onDragStart };
}
