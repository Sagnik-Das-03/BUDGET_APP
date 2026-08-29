import { NavLink } from 'react-router-dom';
import { SyncStatusWidget } from './SyncStatus';

export function NavBar() {
  return (
    <nav className="topnav">
      <div className="brand">💰 Budget Tracker</div>
      <div className="navlinks">
        <NavLink to="/" end>Dashboard</NavLink>
        <NavLink to="/transactions">Transactions</NavLink>
        <NavLink to="/compare">Compare</NavLink>
        <NavLink to="/conflicts">Conflicts</NavLink>
        <NavLink to="/settings">Settings</NavLink>
        <NavLink to="/logs">Logs</NavLink>
      </div>
      <SyncStatusWidget />
    </nav>
  );
}
