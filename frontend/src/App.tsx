import { useQuery } from '@tanstack/react-query';
import { Navigate, Route, BrowserRouter, Routes } from 'react-router-dom';
import { NavBar } from './components/NavBar';
import { TopRightDrawers } from './components/TopRightDrawers';
import { Dashboard } from './pages/Dashboard';
import { Transactions } from './pages/Transactions';
import { Import } from './pages/Import';
import { Compare } from './pages/Compare';
import { Conflicts } from './pages/Conflicts';
import { Trash } from './pages/Trash';
import { Settings } from './pages/Settings';
import { Admin } from './pages/Admin';
import { api } from './lib/api';

// Admin has no nav link to any of these, but the routes still exist - guard
// them directly so typing/pasting a URL (or a stale tab) can't land the
// admin profile on Settings et al., and can't land any other profile on
// /admin either.
function RequireNonAdmin({ children }: { children: React.ReactNode }) {
  const users = useQuery({ queryKey: ['users'], queryFn: () => api.listUsers() });
  const isAdmin = users.data?.some((u) => u.is_active && u.username.toLowerCase() === 'admin') ?? false;
  if (isAdmin) return <Navigate to="/admin" replace />;
  return <>{children}</>;
}

function RequireAdmin({ children }: { children: React.ReactNode }) {
  const users = useQuery({ queryKey: ['users'], queryFn: () => api.listUsers() });
  const isAdmin = users.data?.some((u) => u.is_active && u.username.toLowerCase() === 'admin') ?? false;
  if (users.data && !isAdmin) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export function App() {
  return (
    <BrowserRouter>
      <div className="flex min-h-screen bg-background">
        <NavBar />
        {/* Rendered once, outside <Routes> - Ask's in-flight question and chat
            state must survive navigating between the left-nav tabs below, not
            just clicking around within one page. */}
        <TopRightDrawers />
        <main className="min-w-0 flex-1 px-6 py-8">
          <div className="mx-auto max-w-6xl">
            <Routes>
              <Route path="/" element={<RequireNonAdmin><Dashboard /></RequireNonAdmin>} />
              <Route path="/transactions" element={<RequireNonAdmin><Transactions /></RequireNonAdmin>} />
              <Route path="/import" element={<RequireNonAdmin><Import /></RequireNonAdmin>} />
              <Route path="/compare" element={<RequireNonAdmin><Compare /></RequireNonAdmin>} />
              <Route path="/conflicts" element={<RequireNonAdmin><Conflicts /></RequireNonAdmin>} />
              <Route path="/trash" element={<RequireNonAdmin><Trash /></RequireNonAdmin>} />
              <Route path="/settings" element={<RequireNonAdmin><Settings /></RequireNonAdmin>} />
              <Route path="/admin" element={<RequireAdmin><Admin /></RequireAdmin>} />
            </Routes>
          </div>
        </main>
      </div>
    </BrowserRouter>
  );
}
