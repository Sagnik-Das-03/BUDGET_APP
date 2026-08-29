import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { api, type DateBounds } from '../lib/api';
import { fmtMoney, fmtPct } from '../lib/format';
import { monthBounds, monthLabel } from '../lib/dates';
import type { RangeKey } from '../lib/types';
import { RangeToggle } from '../components/RangeToggle';
import { MetricsRow } from '../components/MetricsRow';
import { AlertBanner } from '../components/AlertBanner';
import { KpiRow, type KpiTileData } from '../components/KpiRow';
import { TrendChart } from '../components/TrendChart';
import { CategoryChart } from '../components/CategoryChart';
import { BudgetChart } from '../components/BudgetChart';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const RANGE_LABEL: Record<RangeKey, string> = {
  this_week: 'This Week', this_month: 'This Month', this_year: 'This Year', all_time: 'All Time',
};

export function Dashboard() {
  const [range, setRangeRaw] = useState<RangeKey>('this_month');
  const [selectedMonth, setSelectedMonth] = useState<string | null>(null);

  function setRange(r: RangeKey) {
    setRangeRaw(r);
    setSelectedMonth(null); // drilled-into month only makes sense within the year it came from
  }

  // Drilling into one month of "This Year" narrows the KPI/metrics/category
  // queries to that month, via the same range=custom&date_from=&date_to= the
  // backend already supports - the Trend chart itself stays un-narrowed, still
  // showing the whole year's month-by-month shape for context.
  const drilled = range === 'this_year' && selectedMonth;
  const effectiveRange = drilled ? 'custom' : range;
  const effectiveBounds: DateBounds | undefined = drilled ? monthBounds(selectedMonth) : undefined;

  const config = useQuery({ queryKey: ['syncConfig'], queryFn: api.syncConfig });
  const summary = useQuery({
    queryKey: ['summary', effectiveRange, selectedMonth],
    queryFn: () => api.summary(effectiveRange, effectiveBounds),
  });
  const highlights = useQuery({
    queryKey: ['highlights', effectiveRange, selectedMonth],
    queryFn: () => api.highlights(effectiveRange, effectiveBounds),
  });
  const trend = useQuery({ queryKey: ['trendForRange', range], queryFn: () => api.trendForRange(range) });
  const categoryTree = useQuery({
    queryKey: ['categoryDrilldown', effectiveRange, selectedMonth],
    queryFn: () => api.categoryDrilldown(effectiveRange, 'Expense', effectiveBounds),
  });
  const budget = useQuery({ queryKey: ['budgetVsActual'], queryFn: api.budgetVsActual });
  const alerts = useQuery({ queryKey: ['budgetAlerts'], queryFn: api.budgetAlerts });
  const savingsGoal = useQuery({ queryKey: ['savingsGoalProgress'], queryFn: api.savingsGoalProgress });

  const s = summary.data;
  const g = savingsGoal.data;
  const goalCls = g?.status === 'met' ? 'met' : g?.status === 'behind' ? 'behind' : '';
  const goalIcon = g?.status === 'met' ? '✓' : g?.status === 'behind' ? '⚠' : '';

  const tiles: KpiTileData[] = [
    { id: 'income', label: 'Income', value: fmtMoney(s?.income) },
    { id: 'expenses', label: 'Expenses', value: fmtMoney(s?.expenses) },
    { id: 'sip', label: 'SIP', value: fmtMoney(s?.sip) },
    { id: 'cash-savings', label: 'Cash Savings', value: fmtMoney(s?.cash_savings) },
    {
      id: 'net', label: 'Net Savings', value: fmtMoney(s?.net),
      sub: g?.goal ? { text: `${goalIcon} ${(g.pct! * 100).toFixed(0)}% of ${fmtMoney(g.goal)} goal (this month)`.trim(), className: goalCls } : undefined,
    },
    { id: 'rate', label: 'Savings Rate', value: fmtPct(s?.savings_rate) },
  ];

  const monthOptions = range === 'this_year' && trend.data?.granularity === 'monthly'
    ? trend.data.rows.map((r) => r.period_key!).filter(Boolean)
    : [];

  const categoryLabel = drilled ? monthLabel(selectedMonth) : RANGE_LABEL[range];

  return (
    <>
      <h1 className="text-2xl font-bold tracking-tight">Finance Dashboard</h1>
      <p className="mb-5 mt-1 text-sm text-muted-foreground">
        {config.data?.credentials_configured
          ? 'Live view of your budget, computed straight from the database.'
          : <>⚙ Google Sheets sync isn't configured yet — see <a href="/settings" className="underline underline-offset-2">Settings</a>. The dashboard below still works from local data.</>}
      </p>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <RangeToggle value={range} onChange={setRange} />
        {monthOptions.length > 0 && (
          <Select value={selectedMonth ?? '__all__'} onValueChange={(v) => setSelectedMonth(v === '__all__' ? null : v)}>
            <SelectTrigger size="sm" className="w-[160px]">
              <SelectValue placeholder="All months" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All months</SelectItem>
              {monthOptions.map((pk) => <SelectItem key={pk} value={pk}>{monthLabel(pk)}</SelectItem>)}
            </SelectContent>
          </Select>
        )}
      </div>

      <AlertBanner alerts={alerts.data} />
      <MetricsRow highlights={highlights.data} />
      <KpiRow tiles={tiles} />

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <TrendChart data={trend.data} />
        <CategoryChart tree={categoryTree.data} rangeLabel={categoryLabel} />
        <BudgetChart rows={budget.data} />
      </div>
    </>
  );
}
