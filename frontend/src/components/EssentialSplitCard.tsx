import { useState } from 'react';
import { ChevronDown, ChevronUp, PieChart } from 'lucide-react';
import type { EssentialSplit, EssentialSplitCategory } from '../lib/types';
import { fmtMoney, fmtPct } from '../lib/format';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

function CategoryList({ rows, dotClassName }: { rows: EssentialSplitCategory[]; dotClassName: string }) {
  if (!rows.length) return <p className="text-xs text-muted-foreground">None this period.</p>;
  return (
    <ul className="flex flex-col gap-1.5">
      {rows.map((r) => (
        <li key={r.category} className="flex items-center justify-between gap-3 text-sm">
          <span className="flex min-w-0 items-center gap-1.5">
            <span className={`size-2 shrink-0 rounded-full ${dotClassName}`} />
            <span className="truncate">{r.category}</span>
          </span>
          <span className="shrink-0 font-medium tabular-nums">{fmtMoney(r.total)}</span>
        </li>
      ))}
    </ul>
  );
}

// Takes already-fetched data as a prop (the "Essential Spend" KPI tile on the
// same page fetches the same essential_split endpoint) rather than issuing
// its own request. Purely descriptive, no threshold or judgment - is_essential
// itself is the user's own call, made per-category in Settings.
export function EssentialSplitCard({ data }: { data: EssentialSplit | undefined }) {
  const [showDetails, setShowDetails] = useState(false);
  if (!data || (data.essential === 0 && data.discretionary === 0)) return null;

  const essentialPct = data.essential_pct * 100;

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-2 space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2 text-sm font-semibold">
            <PieChart className="size-4 text-primary" /> Essential vs Discretionary
          </CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">Based on which categories are marked "Essential" in Settings.</p>
        </div>
        <Button variant="ghost" size="sm" className="h-7 shrink-0 px-2 text-xs" onClick={() => setShowDetails((v) => !v)}>
          {showDetails ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
          {showDetails ? 'Hide' : 'Breakdown'}
        </Button>
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

        {showDetails && (
          <div className="grid grid-cols-1 gap-4 border-t pt-3.5 sm:grid-cols-2">
            <div>
              <p className="mb-1.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">Essential</p>
              <CategoryList rows={data.essential_categories} dotClassName="bg-emerald-500" />
            </div>
            <div>
              <p className="mb-1.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">Discretionary</p>
              <CategoryList rows={data.discretionary_categories} dotClassName="bg-muted-foreground/40" />
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
