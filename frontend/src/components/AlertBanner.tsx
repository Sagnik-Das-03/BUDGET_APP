import { Link } from 'react-router-dom';
import type { BudgetAlert } from '../lib/types';
import { fmtMoney } from '../lib/format';

export function AlertBanner({ alerts }: { alerts: BudgetAlert[] | undefined }) {
  if (!alerts || !alerts.length) return <div className="alert-banner" />;
  return (
    <div className="alert-banner">
      {alerts.map((a) => (
        <div key={a.category} className={`alert-row ${a.status}`}>
          <span className="alert-icon">{a.status === 'critical' ? '🛑' : '⚠️'}</span>
          <span className="alert-cat">{a.category}</span>
          <span>
            {a.status === 'critical' ? 'is over budget' : 'is close to its budget'} —{' '}
            {fmtMoney(a.actual)} of {fmtMoney(a.goal)} ({(a.pct * 100).toFixed(0)}%) this month
          </span>
          <Link to="/settings">Edit goal</Link>
        </div>
      ))}
    </div>
  );
}
