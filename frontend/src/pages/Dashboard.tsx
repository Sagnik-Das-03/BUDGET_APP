import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { api, type DateBounds } from '../lib/api';
import { fmtMoney, fmtPct } from '../lib/format';
import { monthBounds, monthLabel, yearBounds } from '../lib/dates';
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
  const [selectedMonth, setSelectedMonthRaw] = useState<string | null>(null);
  const [selectedYear, setSelectedYearRaw] = useState<string | null>(null);

  function setRange(r: RangeKey) {
    setRangeRaw(r);
    setSelectedMonthRaw(null); // drilled-into month/year only makes sense within the range it came from
    setSelectedYearRaw(null);
  }

  function setSelectedMonth(pk: string | null) {
    setSelectedMonthRaw(pk);
    // picking a month outside the currently-selected year (or clearing the month
    // while a year is selected) falls back to that year's full-year view, not all-time
    if (pk && selectedYear && !pk.startsWith(selectedYear)) setSelectedYearRaw(pk.slice(0, 4));
  }

  function setSelectedYear(y: string | null) {
    setSelectedYearRaw(y);
    // narrowing to a year clears a month selection that no longer belongs to it
    if (y && selectedMonth && !selectedMonth.startsWith(y)) setSelectedMonthRaw(null);
  }

  // Drilling into one month of "This Year"/"All Time", or one whole year of "All
  // Time", narrows the KPI/metrics/category queries accordingly, via the same
  // range=custom&date_from=&date_to= the backend already supports - the Trend
  // chart itself stays un-narrowed, still showing the whole range's shape for
  // context. A month selection is more specific than a year selection.
  const drillKind: 'month' | 'year' | null =
    (range === 'this_year' || range === 'all_time') && selectedMonth ? 'month'
    : range === 'all_time' && selectedYear ? 'year'
    : null;
  const effectiveRange = drillKind ? 'custom' : range;
  const effectiveBounds: DateBounds | undefined =
    drillKind === 'month' ? monthBounds(selectedMonth!)
    : drillKind === 'year' ? yearBounds(selectedYear!)
    : undefined;

  const config = useQuery({ queryKey: ['syncConfig'], queryFn: api.syncConfig });
  const summary = useQuery({
    queryKey: ['summary', effectiveRange, selectedYear, selectedMonth],
    queryFn: () => api.summary(effectiveRange, effectiveBounds),
  });
  const highlights = useQuery({
    queryKey: ['highlights', effectiveRange, selectedYear, selectedMonth],
    queryFn: () => api.highlights(effectiveRange, effectiveBounds),
  });
  const trend = useQuery({ queryKey: ['trendForRange', range], queryFn: () => api.trendForRange(range) });
  const categoryTree = useQuery({
    queryKey: ['categoryDrilldown', effectiveRange, selectedYear, selectedMonth],
    queryFn: () => api.categoryDrilldown(effectiveRange, 'Expense', effectiveBounds),
  });
  const budget = useQuery({ queryKey: ['budgetVsActual'], queryFn: api.budgetVsActual });
  const monthlyBreakdown = useQuery({
    queryKey: ['monthlyBreakdown'], queryFn: api.monthlyBreakdown, enabled: range === 'all_time',
  });
  const alerts = useQuery({ queryKey: ['budgetAlerts'], queryFn: api.budgetAlerts });
  // The goal is inherently monthly, so it only makes sense to compare against a
  // specific month - when one's drilled into (from This Year or All Time), compare
  // against that month instead of always defaulting to the real current month.
  const goalPeriodKey = drillKind === 'month' ? selectedMonth! : undefined;
  const savingsGoal = useQuery({
    queryKey: ['savingsGoalProgress', goalPeriodKey],
    queryFn: () => api.savingsGoalProgress(goalPeriodKey),
  });

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
      sub: g?.goal ? {
        text: `${goalIcon} ${(g.pct! * 100).toFixed(0)}% of ${fmtMoney(g.goal)} goal (${goalPeriodKey ? monthLabel(goalPeriodKey) : 'this month'})`.trim(),
        className: goalCls,
      } : undefined,
    },
    { id: 'rate', label: 'Savings Rate', value: fmtPct(s?.savings_rate) },
  ];

  const monthOptions = range === 'this_year' && trend.data?.granularity === 'monthly'
    ? trend.data.rows.map((r) => r.period_key!).filter(Boolean)
    : range === 'all_time' && monthlyBreakdown.data
    ? monthlyBreakdown.data.map((r) => r.period_key).filter((pk) => !selectedYear || pk.startsWith(selectedYear))
    : [];

  const yearOptions = range === 'all_time' && monthlyBreakdown.data
    ? Array.from(new Set(monthlyBreakdown.data.map((r) => r.period_key.slice(0, 4)))).sort()
    : [];

  const categoryLabel =
    drillKind === 'month' ? monthLabel(selectedMonth!)
    : drillKind === 'year' ? selectedYear!
    : RANGE_LABEL[range];

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
        {yearOptions.length > 0 && (
          <Select value={selectedYear ?? '__all__'} onValueChange={(v) => setSelectedYear(v === '__all__' ? null : v)}>
            <SelectTrigger size="sm" className="w-[110px]">
              <SelectValue placeholder="All years" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All years</SelectItem>
              {yearOptions.map((y) => <SelectItem key={y} value={y}>{y}</SelectItem>)}
            </SelectContent>
          </Select>
        )}
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
