import { useQuery } from '@tanstack/react-query';
import { NavLink } from 'react-router-dom';
import {
  AlertTriangle, ArrowLeftRight, GitCompare, LayoutDashboard,
  ShieldCheck, Settings, Trash2, Upload, Wallet,
} from 'lucide-react';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';
import { SyncStatusWidget } from './SyncStatus';
import { ModeToggle } from './ModeToggle';
import { UserSwitcher } from './UserSwitcher';

const LINKS = [
  { to: '/', label: 'Dashboard', end: true, icon: LayoutDashboard },
  { to: '/transactions', label: 'Transactions', icon: ArrowLeftRight },
  { to: '/import', label: 'Import', icon: Upload },
  { to: '/compare', label: 'Compare', icon: GitCompare },
  { to: '/conflicts', label: 'Conflicts', icon: AlertTriangle },
  { to: '/trash', label: 'Trash', icon: Trash2 },
  { to: '/settings', label: 'Settings', icon: Settings },
];

// Ask and Logs live in TopRightDrawers (rendered from App.tsx) instead of
// here - they're drawers reachable from every page, not routed tabs.
export function NavBar() {
  // Same query UserSwitcher already runs, so this is a cache hit, not an
  // extra request - just used here to decide whether to show the Admin link
  // at all, since it's only meaningful while signed in as that profile.
  const users = useQuery({ queryKey: ['users'], queryFn: () => api.listUsers() });
  const isAdmin = users.data?.some((u) => u.is_active && u.username.toLowerCase() === 'admin') ?? false;
  const links = isAdmin ? [...LINKS, { to: '/admin', label: 'Admin', icon: ShieldCheck }] : LINKS;

  return (
    <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col border-r bg-card/80 backdrop-blur supports-backdrop-filter:bg-card/60">
      <div className="flex items-center gap-2 px-5 py-4 text-[15px] font-semibold">
        <Wallet className="size-5 shrink-0 text-primary" />
        Budget Tracker
      </div>
      <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-3">
        {links.map((l) => (
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
        <UserSwitcher />
        <SyncStatusWidget />
        <ModeToggle />
      </div>
    </aside>
  );
}
