export function ResizeHandle({ onMouseDown }: { onMouseDown: (e: React.MouseEvent) => void }) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize panel"
      onMouseDown={onMouseDown}
      className="absolute inset-y-0 left-0 z-10 w-1.5 -translate-x-1/2 cursor-col-resize touch-none group"
    >
      <div className="mx-auto h-full w-px bg-transparent transition-colors group-hover:bg-border group-active:bg-primary" />
    </div>
  );
}
