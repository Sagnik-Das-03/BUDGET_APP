import { NavLink } from 'react-router-dom';
import {
  AlertTriangle, ArrowLeftRight, GitCompare, LayoutDashboard, ScrollText,
  Settings, Sparkles, Trash2, Upload, Wallet,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { SyncStatusWidget } from './SyncStatus';
import { ModeToggle } from './ModeToggle';

const LINKS = [
  { to: '/', label: 'Dashboard', end: true, icon: LayoutDashboard },
  { to: '/transactions', label: 'Transactions', icon: ArrowLeftRight },
  { to: '/import', label: 'Import', icon: Upload },
  { to: '/compare', label: 'Compare', icon: GitCompare },
  { to: '/conflicts', label: 'Conflicts', icon: AlertTriangle },
  { to: '/trash', label: 'Trash', icon: Trash2 },
  { to: '/ask', label: 'Ask', icon: Sparkles },
  { to: '/settings', label: 'Settings', icon: Settings },
  { to: '/logs', label: 'Logs', icon: ScrollText },
];

export function NavBar() {
  return (
    <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col border-r bg-card/80 backdrop-blur supports-backdrop-filter:bg-card/60">
      <div className="flex items-center gap-2 px-5 py-4 text-[15px] font-semibold">
        <Wallet className="size-5 shrink-0 text-primary" />
        Budget Tracker
      </div>
      <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-3">
        {LINKS.map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            end={l.end}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-accent text-accent-foreground'
                  : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground',
              )
            }
          >
            <l.icon className="size-4 shrink-0" />
            {l.label}
          </NavLink>
        ))}
      </nav>
      <div className="flex flex-col gap-2.5 border-t px-3 py-3">
        <SyncStatusWidget />
        <ModeToggle />
      </div>
    </aside>
  );
}
