import { Route, BrowserRouter, Routes } from 'react-router-dom';
import { NavBar } from './components/NavBar';
import { Dashboard } from './pages/Dashboard';
import { Transactions } from './pages/Transactions';
import { Import } from './pages/Import';
import { Compare } from './pages/Compare';
import { Conflicts } from './pages/Conflicts';
import { Trash } from './pages/Trash';
import { Ask } from './pages/Ask';
import { Settings } from './pages/Settings';
import { Logs } from './pages/Logs';

export function App() {
  return (
    <BrowserRouter>
      <div className="flex min-h-screen bg-background">
        <NavBar />
        <main className="min-w-0 flex-1 px-6 py-8">
          <div className="mx-auto max-w-6xl">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/transactions" element={<Transactions />} />
              <Route path="/import" element={<Import />} />
              <Route path="/compare" element={<Compare />} />
              <Route path="/conflicts" element={<Conflicts />} />
              <Route path="/trash" element={<Trash />} />
              <Route path="/ask" element={<Ask />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/logs" element={<Logs />} />
            </Routes>
          </div>
        </main>
      </div>
    </BrowserRouter>
  );
}
