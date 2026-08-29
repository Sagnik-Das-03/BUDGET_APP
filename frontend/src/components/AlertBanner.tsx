import { Link } from 'react-router-dom';
import { OctagonAlert, TriangleAlert } from 'lucide-react';
import type { BudgetAlert } from '../lib/types';
import { fmtMoney } from '../lib/format';
import { cn } from '@/lib/utils';

export function AlertBanner({ alerts }: { alerts: BudgetAlert[] | undefined }) {
  if (!alerts || !alerts.length) return null;
  return (
    <div className="mb-5 flex flex-col gap-2">
      {alerts.map((a) => (
        <div
          key={a.category}
          className={cn(
            'flex items-center gap-2.5 rounded-lg border px-3.5 py-2.5 text-sm',
            a.status === 'critical'
              ? 'border-red-200 bg-red-50 text-red-900 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-200'
              : 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-200',
          )}
        >
          {a.status === 'critical' ? <OctagonAlert className="size-4 shrink-0" /> : <TriangleAlert className="size-4 shrink-0" />}
          <span className="font-semibold">{a.category}</span>
          <span>
            {a.status === 'critical' ? 'is over budget' : 'is close to its budget'} —{' '}
            {fmtMoney(a.actual)} of {fmtMoney(a.goal)} ({(a.pct * 100).toFixed(0)}%) this month
          </span>
          <Link to="/settings" className="ml-auto shrink-0 text-xs font-medium underline underline-offset-2">
            Edit goal
          </Link>
        </div>
      ))}
    </div>
  );
}
