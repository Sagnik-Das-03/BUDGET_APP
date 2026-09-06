import { useQuery } from '@tanstack/react-query';
import { ArrowDown, ArrowUp, TrendingUpDown } from 'lucide-react';
import { api, type DateBounds } from '../lib/api';
import { fmtMoney } from '../lib/format';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface CategoryTrendsProps {
  range: string;
  dateBounds?: DateBounds;
}

// How each category moved vs. the immediately preceding period of the same
// kind (last week/month/year) - pure arithmetic on by_category(), no AI.
// Nothing to compare against for all_time or a custom drilled-into range, so
// the endpoint comes back empty and this renders nothing rather than an
// empty card.
export function CategoryTrends({ range, dateBounds }: CategoryTrendsProps) {
  const trends = useQuery({
    queryKey: ['categoryTrends', range, dateBounds?.date_from, dateBounds?.date_to],
    queryFn: () => api.categoryTrends(range, 'Expense', dateBounds),
  });
  const rows = (trends.data ?? []).filter((r) => r.current !== 0 || r.previous !== 0).slice(0, 6);
  if (!rows.length) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          <TrendingUpDown className="size-4 text-primary" /> Category Trends
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2.5">
        {rows.map((r) => {
          const up = r.delta_abs > 0;
          const flat = r.delta_abs === 0;
          return (
            <div key={r.category} className="flex items-center justify-between gap-3 text-sm">
              <span className="font-medium">{r.category}</span>
              <span className="flex items-center gap-2 tabular-nums text-muted-foreground">
                {fmtMoney(r.previous)} → {fmtMoney(r.current)}
                <span
                  className={cn(
                    'flex items-center gap-0.5 font-semibold',
                    flat ? 'text-muted-foreground' : up ? 'text-destructive' : 'text-emerald-600 dark:text-emerald-400',
                  )}
                >
                  {!flat && (up ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />)}
                  {r.delta_pct === null ? 'new' : `${Math.abs(r.delta_pct * 100).toFixed(0)}%`}
                </span>
              </span>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
