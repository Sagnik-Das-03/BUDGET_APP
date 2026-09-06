import { PieChart } from 'lucide-react';
import type { EssentialSplit } from '../lib/types';
import { fmtMoney, fmtPct } from '../lib/format';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

// Takes already-fetched data as a prop (the "Essential Spend" KPI tile on the
// same page fetches the same essential_split endpoint) rather than issuing
// its own request. Purely descriptive, no threshold or judgment - is_essential
// itself is the user's own call, made per-category in Settings.
export function EssentialSplitCard({ data }: { data: EssentialSplit | undefined }) {
  if (!data || (data.essential === 0 && data.discretionary === 0)) return null;

  const essentialPct = data.essential_pct * 100;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          <PieChart className="size-4 text-primary" /> Essential vs Discretionary
        </CardTitle>
        <p className="text-xs text-muted-foreground">Based on which categories are marked "Essential" in Settings.</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-3.5">
        <div className="h-3 w-full overflow-hidden rounded-full bg-muted">
          <div className="h-full bg-emerald-500" style={{ width: `${essentialPct}%` }} />
        </div>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 shrink-0 rounded-full bg-emerald-500" />
            Essential <span className="font-semibold tabular-nums">{fmtMoney(data.essential)}</span>
            <span className="text-xs text-muted-foreground">({fmtPct(data.essential_pct)})</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 shrink-0 rounded-full bg-muted-foreground/40" />
            Discretionary <span className="font-semibold tabular-nums">{fmtMoney(data.discretionary)}</span>
            <span className="text-xs text-muted-foreground">({fmtPct(data.discretionary_pct)})</span>
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
