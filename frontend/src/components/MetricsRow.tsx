import { CalendarDays, Receipt, TrendingDown, TrendingUp, Trophy } from 'lucide-react';
import type { Highlights } from '../lib/types';
import { fmtMoney } from '../lib/format';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';

function MetricChip({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
}) {
  return (
    <Card className="flex-1 min-w-[190px] py-0">
      <CardContent className="flex items-center gap-3 px-4 py-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-accent text-accent-foreground">
          {icon}
        </div>
        <div className="min-w-0">
          <div className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">{label}</div>
          <div className="truncate text-sm font-semibold">{value}</div>
        </div>
      </CardContent>
    </Card>
  );
}

export function MetricsRow({ highlights }: { highlights: Highlights | undefined }) {
  const comparison = highlights?.comparison;
  const delta = comparison?.net_delta_pct;

  return (
    <div className="mb-5 flex flex-wrap gap-3">
      <MetricChip
        icon={<Trophy className="size-4" />}
        label="Top Category"
        value={
          highlights?.top_category
            ? `${highlights.top_category.category} (${fmtMoney(highlights.top_category.total)})`
            : '—'
        }
      />
      <MetricChip
        icon={<Receipt className="size-4" />}
        label="Transactions"
        value={highlights?.transaction_count ?? '—'}
      />
      <MetricChip
        icon={<CalendarDays className="size-4" />}
        label="Avg Daily Spend"
        value={highlights ? `${fmtMoney(highlights.avg_daily_spend)} / day` : '—'}
      />
      <MetricChip
        icon={delta !== null && delta !== undefined && delta < 0 ? <TrendingDown className="size-4" /> : <TrendingUp className="size-4" />}
        label="vs Previous Period"
        value={
          !comparison ? '—' : delta === null || delta === undefined ? 'n/a' : (
            <span className={cn(delta >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive')}>
              {delta >= 0 ? '▲' : '▼'} {Math.abs(delta * 100).toFixed(1)}% net
            </span>
          )
        }
      />
    </div>
  );
}
