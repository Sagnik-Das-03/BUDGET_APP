import { Route, BrowserRouter, Routes } from 'react-router-dom';
import { NavBar } from './components/NavBar';
import { Dashboard } from './pages/Dashboard';
import { Transactions } from './pages/Transactions';
import { Compare } from './pages/Compare';
import { Conflicts } from './pages/Conflicts';
import { Settings } from './pages/Settings';
import { Logs } from './pages/Logs';

export function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-background">
        <NavBar />
        <main className="mx-auto max-w-6xl px-6 py-8">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/transactions" element={<Transactions />} />
            <Route path="/compare" element={<Compare />} />
            <Route path="/conflicts" element={<Conflicts />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/logs" element={<Logs />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
