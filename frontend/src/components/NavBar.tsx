import { NavLink } from 'react-router-dom';
import { Wallet } from 'lucide-react';
import { cn } from '@/lib/utils';
import { SyncStatusWidget } from './SyncStatus';
import { ModeToggle } from './ModeToggle';

const LINKS = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/transactions', label: 'Transactions' },
  { to: '/import', label: 'Import' },
  { to: '/compare', label: 'Compare' },
  { to: '/conflicts', label: 'Conflicts' },
  { to: '/trash', label: 'Trash' },
  { to: '/settings', label: 'Settings' },
  { to: '/logs', label: 'Logs' },
];

export function NavBar() {
  return (
    <header className="sticky top-0 z-40 border-b bg-card/80 backdrop-blur supports-backdrop-filter:bg-card/60">
      <div className="mx-auto flex max-w-6xl items-center gap-6 px-6 py-3">
        <div className="flex items-center gap-2 text-[15px] font-semibold">
          <Wallet className="size-5 text-primary" />
          Budget Tracker
        </div>
        <nav className="flex flex-1 items-center gap-1 overflow-x-auto">
          {LINKS.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              className={({ isActive }) =>
                cn(
                  'rounded-md px-3 py-1.5 text-sm font-medium whitespace-nowrap transition-colors',
                  isActive
                    ? 'bg-accent text-accent-foreground'
                    : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground',
                )
              }
            >
              {l.label}
            </NavLink>
          ))}
        </nav>
        <SyncStatusWidget />
        <ModeToggle />
      </div>
    </header>
  );
}
