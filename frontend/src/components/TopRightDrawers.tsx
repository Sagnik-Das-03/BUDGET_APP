import { ScrollText, Sparkles } from 'lucide-react';
import { AskDrawer } from './AskDrawer';
import { LogsDrawer } from './LogsDrawer';
import { ModeToggle } from './ModeToggle';
import { Button } from '@/components/ui/button';

// Fixed to the viewport, rendered once outside <Routes> in App.tsx, so these
// stay reachable (and Ask's own state stays alive) no matter which left-nav
// tab is currently showing.
export function TopRightDrawers() {
  return (
    <div className="fixed right-6 top-4 z-40 flex items-center gap-2">
      <ModeToggle />
      <AskDrawer
        trigger={
          <Button variant="outline" size="icon" aria-label="Ask Your Budget" title="Ask Your Budget">
            <Sparkles className="size-4" />
          </Button>
        }
      />
      <LogsDrawer
        trigger={
          <Button variant="outline" size="icon" aria-label="Sync Logs" title="Sync Logs">
            <ScrollText className="size-4" />
          </Button>
        }
      />
    </div>
  );
}
