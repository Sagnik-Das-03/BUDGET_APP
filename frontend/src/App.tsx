import { Route, BrowserRouter, Routes } from 'react-router-dom';
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
              <Route path="/" element={<Dashboard />} />
              <Route path="/transactions" element={<Transactions />} />
              <Route path="/import" element={<Import />} />
              <Route path="/compare" element={<Compare />} />
              <Route path="/conflicts" element={<Conflicts />} />
              <Route path="/trash" element={<Trash />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/admin" element={<Admin />} />
            </Routes>
          </div>
        </main>
      </div>
    </BrowserRouter>
  );
}
