import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Gauge, OctagonAlert, TriangleAlert } from 'lucide-react';
import { api } from '../lib/api';
import { fmtMoney, fmtPct } from '../lib/format';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

// Pure arithmetic (amount-so-far / days-elapsed * days-in-period), computed
// server-side in calc.forecast() - no AI model involved, so this renders
// immediately on every Dashboard load like the anomaly/alert banners.
// Deliberately hidden for a period that's already over (is_current=false):
// a "projection" for a closed month is just its final actual, not a
// forward-looking guess, so there's nothing useful to show.
export function ForecastCard() {
  const forecast = useQuery({ queryKey: ['forecast'], queryFn: () => api.forecast() });
  const f = forecast.data;
  if (!f || !f.is_current) return null;

  const pacingRows = f.category_pace.filter((r) => r.status !== 'on_track');

  return (
    <Card className="mb-5 py-4">
      <CardHeader className="gap-1 px-5">
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          <Gauge className="size-4 text-primary" /> At This Pace
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Day {f.days_elapsed} of {f.days_in_period} — projected to month-end if income and spending keep up at today's average daily rate.
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 px-5">
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <span className="text-muted-foreground">Projected Income <span className="font-semibold tabular-nums text-foreground">{fmtMoney(f.projected_income)}</span></span>
          <span className="text-muted-foreground">Projected Expenses <span className="font-semibold tabular-nums text-foreground">{fmtMoney(f.projected_expenses)}</span></span>
          <span className="text-muted-foreground">
            Projected Net{' '}
            <span className={cn('font-semibold tabular-nums', f.projected_net >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive')}>
              {fmtMoney(f.projected_net)}
            </span>
          </span>
          <span className="text-muted-foreground">Projected Savings Rate <span className="font-semibold tabular-nums text-foreground">{fmtPct(f.projected_savings_rate)}</span></span>
        </div>

        {pacingRows.length > 0 && (
          <div className="flex flex-col gap-2">
            {pacingRows.map((r) => (
              <div
                key={r.category}
                className={cn(
                  'flex items-center gap-2.5 rounded-lg border px-3.5 py-2.5 text-sm',
                  r.status === 'over'
                    ? 'border-red-200 bg-red-50 text-red-900 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-200'
                    : 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-200',
                )}
              >
                {r.status === 'over' ? <OctagonAlert className="size-4 shrink-0" /> : <TriangleAlert className="size-4 shrink-0" />}
                <span className="font-semibold">{r.category}</span>
                <span>
                  is pacing to {r.status === 'over' ? 'exceed' : 'approach'} its budget — projected {fmtMoney(r.projected)} of{' '}
                  {fmtMoney(r.goal)} ({(r.pct * 100).toFixed(0)}%), only {fmtMoney(r.actual)} spent so far
                </span>
                <Link to="/settings" className="ml-auto shrink-0 text-xs font-medium underline underline-offset-2">
                  Edit goal
                </Link>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
