import { useQuery } from '@tanstack/react-query';
import { Activity } from 'lucide-react';
import { api } from '../lib/api';
import { fmtMoney } from '../lib/format';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const STATUS_LABEL: Record<string, string> = { stable: 'Stable', moderate: 'Moderate', volatile: 'Volatile' };
const STATUS_CLASS: Record<string, string> = {
  stable: 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/40 dark:text-emerald-300',
  moderate: 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-300',
  volatile: 'border-red-200 bg-red-50 text-red-700 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300',
};

// Coefficient of variation (stdev/mean) of each category's monthly totals
// over the last 6 fully-elapsed months - pure statistics, no AI. A "stable"
// category is a good candidate for a tight fixed budget goal; a "volatile"
// one swings too much month to month for one number to mean much.
export function CategoryConsistency() {
  const volatility = useQuery({ queryKey: ['categoryVolatility'], queryFn: () => api.categoryVolatility() });
  const rows = volatility.data ?? [];
  if (!rows.length) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          <Activity className="size-4 text-primary" /> Spending Consistency
        </CardTitle>
        <p className="text-xs text-muted-foreground">Based on each category's month-to-month totals over the last 6 months.</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-2.5">
        {rows.map((r) => (
          <div key={r.category} className="flex items-center justify-between gap-3 text-sm">
            <span className="font-medium">{r.category}</span>
            <span className="flex items-center gap-2.5">
              <span className="text-xs text-muted-foreground tabular-nums">avg {fmtMoney(r.avg_monthly)}/mo</span>
              <Badge variant="outline" className={STATUS_CLASS[r.status]}>{STATUS_LABEL[r.status]}</Badge>
            </span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
