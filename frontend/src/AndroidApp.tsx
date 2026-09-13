import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { api, request, type DateBounds } from './lib/api';
import { fmtMoney, fmtPct } from './lib/format';
import { monthBounds, monthLabel, yearBounds } from './lib/dates';
import type { RangeKey } from './lib/types';
import { RangeToggle } from './components/RangeToggle';
import { MetricsRow } from './components/MetricsRow';
import { AlertBanner } from './components/AlertBanner';
import { KpiRow, type KpiTileData } from './components/KpiRow';
import { TrendChart } from './components/TrendChart';
import { CategoryChart } from './components/CategoryChart';
import { BudgetChart } from './components/BudgetChart';
import { CategoryTrends } from './components/CategoryTrends';
import { CategoryConsistency } from './components/CategoryConsistency';
import { SpendingPatternCard } from './components/SpendingPatternCard';
import { SavingsRateTrendChart } from './components/SavingsRateTrendChart';
import { EssentialSplitCard } from './components/EssentialSplitCard';
import { SortableGrid } from './components/SortableGrid';
import { ModeToggle } from './components/ModeToggle';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const RANGE_LABEL: Record<RangeKey, string> = {
  this_week: 'This Week', this_month: 'This Month', this_year: 'This Year', all_time: 'All Time',
};

// Read-only counterpart to pages/Dashboard.tsx, for the Android app (see
// budget_tracker/android/ and android_dashboard/) - same components, same
// frontend/src/lib/api.ts calls (the Python server there implements the
// identical /api/dashboard/* contract, computed from Sheet data instead of
// SQLite - see android_dashboard/calculations.py), just without NavBar,
// routing, or InsightCard (no local LLM on this build). A user switcher
// replaces the desktop app's left-nav one, calling /api/active_user - the
// backend's own "one active profile at a time" model, so every query below
// stays exactly as Dashboard.tsx wrote it with no awareness profiles exist.
function UserSwitcher() {
  const queryClient = useQueryClient();
  const users = useQuery({ queryKey: ['users'], queryFn: () => request<{ name: string }[]>('/users') });
  const active = useQuery({ queryKey: ['activeUser'], queryFn: () => request<{ name: string }>('/api/active_user') });

  if (!users.data || users.data.length <= 1) return null;

  async function select(name: string) {
    await request('/api/active_user', { method: 'POST', body: JSON.stringify({ name }) });
    queryClient.invalidateQueries();
  }

  return (
    <div className="mb-4 flex items-center gap-2">
      <span className="text-xs text-muted-foreground">Viewing</span>
      <Select value={active.data?.name} onValueChange={select}>
        <SelectTrigger size="sm" className="w-[140px]"><SelectValue /></SelectTrigger>
        <SelectContent>
          {users.data.map((u) => <SelectItem key={u.name} value={u.name}>{u.name}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  );
}

function ReadOnlyDashboard() {
  const [range, setRangeRaw] = useState<RangeKey>('this_month');
  const [selectedMonth, setSelectedMonthRaw] = useState<string | null>(null);
  const [selectedYear, setSelectedYearRaw] = useState<string | null>(null);

  function setRange(r: RangeKey) {
    setRangeRaw(r);
    setSelectedMonthRaw(null);
    setSelectedYearRaw(null);
  }

  function setSelectedMonth(pk: string | null) {
    setSelectedMonthRaw(pk);
    if (pk && selectedYear && !pk.startsWith(selectedYear)) setSelectedYearRaw(pk.slice(0, 4));
  }

  function setSelectedYear(y: string | null) {
    setSelectedYearRaw(y);
    if (y && selectedMonth && !selectedMonth.startsWith(y)) setSelectedMonthRaw(null);
  }

  const drillKind: 'month' | 'year' | null =
    (range === 'this_year' || range === 'all_time') && selectedMonth ? 'month'
    : range === 'all_time' && selectedYear ? 'year'
    : null;
  const effectiveRange = drillKind ? 'custom' : range;
  const effectiveBounds: DateBounds | undefined =
    drillKind === 'month' ? monthBounds(selectedMonth!)
    : drillKind === 'year' ? yearBounds(selectedYear!)
    : undefined;

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
  const monthlyBreakdown = useQuery({ queryKey: ['monthlyBreakdown'], queryFn: api.monthlyBreakdown });
  const alerts = useQuery({ queryKey: ['budgetAlerts'], queryFn: api.budgetAlerts });
  const essentialSplit = useQuery({
    queryKey: ['essentialSplit', effectiveRange, selectedYear, selectedMonth],
    queryFn: () => api.essentialSplit(effectiveRange, effectiveBounds),
  });
  const savingsStreak = useQuery({ queryKey: ['savingsStreak'], queryFn: api.savingsStreak });
  const spendConcentration = useQuery({
    queryKey: ['spendConcentration', effectiveRange, selectedYear, selectedMonth],
    queryFn: () => api.spendConcentration(effectiveRange, 3, effectiveBounds),
  });
  const goalPeriodKey = drillKind === 'month' ? selectedMonth! : undefined;
  const savingsGoal = useQuery({
    queryKey: ['savingsGoalProgress', goalPeriodKey],
    queryFn: () => api.savingsGoalProgress(goalPeriodKey),
  });

  const s = summary.data;
  const g = savingsGoal.data;
  const goalCls = g?.status === 'met' ? 'met' : g?.status === 'behind' ? 'behind' : '';
  const goalIcon = g?.status === 'met' ? '✓' : g?.status === 'behind' ? '⚠' : '';

  const budgetUtilization = useMemo(() => {
    const budgeted = (budget.data ?? []).filter((r) => r.goal > 0);
    if (!budgeted.length) return null;
    const totalGoal = budgeted.reduce((sum, r) => sum + r.goal, 0);
    const totalActual = budgeted.reduce((sum, r) => sum + r.actual, 0);
    return { totalGoal, totalActual, pct: totalGoal ? totalActual / totalGoal : 0 };
  }, [budget.data]);

  const largestExpense = useMemo(() => {
    let best: { name: string; value: number; category: string } | null = null;
    for (const node of categoryTree.data ?? []) {
      for (const child of node.children) {
        if (!best || child.value > best.value) best = { name: child.name, value: child.value, category: node.name };
      }
    }
    return best;
  }, [categoryTree.data]);

  const tiles: KpiTileData[] = [
    { id: 'income', label: 'Income', value: fmtMoney(s?.income), description: 'Total money received this period, across all accounts.' },
    { id: 'expenses', label: 'Expenses', value: fmtMoney(s?.expenses), description: 'True consumption only this period. SIP and Cash Savings are tracked separately below since that money is still yours, not spent.' },
    { id: 'sip', label: 'SIP', value: fmtMoney(s?.sip), description: 'Money invested via SIP (Systematic Investment Plan) this period — counted as savings, not spending.' },
    { id: 'cash-savings', label: 'Cash Savings', value: fmtMoney(s?.cash_savings), description: 'Money moved into savings, or household/family transfers, this period — still yours, not counted as an expense.' },
    {
      id: 'net', label: 'Net Savings', value: fmtMoney(s?.net),
      description: 'Income minus Expenses. SIP and Cash Savings aren’t subtracted here since they’re not real spending — this is what’s actually left over this period.',
      sub: g?.goal ? {
        text: `${goalIcon} ${(g.pct! * 100).toFixed(0)}% of ${fmtMoney(g.goal)} goal (${goalPeriodKey ? monthLabel(goalPeriodKey) : 'this month'})`.trim(),
        className: goalCls,
      } : undefined,
    },
    { id: 'rate', label: 'Savings Rate', value: fmtPct(s?.savings_rate), description: 'Net Savings as a share of Income — how much of what you earned this period you kept.' },
    {
      id: 'budget-utilization', label: 'Budget Utilization',
      value: budgetUtilization ? fmtPct(budgetUtilization.pct) : '—',
      description: 'Total actual spend vs. total budgeted goal, summed across every category that has a goal set.',
      sub: budgetUtilization ? { text: `${fmtMoney(budgetUtilization.totalActual)} of ${fmtMoney(budgetUtilization.totalGoal)} budgeted`, className: budgetUtilization.pct >= 1 ? 'behind' : undefined } : undefined,
    },
    {
      id: 'largest-expense', label: 'Largest Expense',
      value: largestExpense ? fmtMoney(largestExpense.value) : '—',
      description: 'The single biggest transaction this period, and the category it fell under.',
      sub: largestExpense ? { text: `${largestExpense.name} · ${largestExpense.category}` } : undefined,
    },
    {
      id: 'essential-split', label: 'Essential Spend',
      value: essentialSplit.data ? fmtPct(essentialSplit.data.essential_pct) : '—',
      description: 'Share of real spending on categories marked "Essential" vs. flexible/discretionary spending.',
      sub: essentialSplit.data ? { text: `${fmtMoney(essentialSplit.data.essential)} essential · ${fmtMoney(essentialSplit.data.discretionary)} discretionary` } : undefined,
    },
    {
      id: 'savings-streak', label: 'Savings Streak',
      value: savingsStreak.data ? `${savingsStreak.data.current_streak_months} mo` : '—',
      description: 'Consecutive fully-completed months with a positive Net Savings, counting back from the most recent closed month.',
      sub: savingsStreak.data?.best_streak_months ? { text: `Best: ${savingsStreak.data.best_streak_months} mo` } : undefined,
    },
    {
      id: 'spend-concentration', label: 'Top 3 Concentration',
      value: spendConcentration.data ? fmtPct(spendConcentration.data.pct) : '—',
      description: 'Share of this period\'s real spending that came from just the 3 largest single transactions.',
      sub: spendConcentration.data ? { text: `${fmtMoney(spendConcentration.data.top_sum)} of ${fmtMoney(spendConcentration.data.total)}` } : undefined,
    },
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
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <RangeToggle value={range} onChange={setRange} />
        {yearOptions.length > 0 && (
          <Select value={selectedYear ?? '__all__'} onValueChange={(v) => setSelectedYear(v === '__all__' ? null : v)}>
            <SelectTrigger size="sm" className="w-[110px]"><SelectValue placeholder="All years" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All years</SelectItem>
              {yearOptions.map((y) => <SelectItem key={y} value={y}>{y}</SelectItem>)}
            </SelectContent>
          </Select>
        )}
        {monthOptions.length > 0 && (
          <Select value={selectedMonth ?? '__all__'} onValueChange={(v) => setSelectedMonth(v === '__all__' ? null : v)}>
            <SelectTrigger size="sm" className="w-[160px]"><SelectValue placeholder="All months" /></SelectTrigger>
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

      <SortableGrid
        storageKey="android.dashboard.cardOrder"
        handle
        className="grid grid-cols-1 gap-5 md:grid-cols-2"
        items={[
          { id: 'trend', node: <TrendChart data={trend.data} /> },
          { id: 'category', node: <CategoryChart tree={categoryTree.data} rangeLabel={categoryLabel} /> },
          { id: 'budget', node: <BudgetChart rows={budget.data} /> },
          { id: 'category-trends', node: <CategoryTrends range={effectiveRange} dateBounds={effectiveBounds} /> },
          { id: 'category-consistency', node: <CategoryConsistency /> },
          { id: 'spending-pattern', node: <SpendingPatternCard range={effectiveRange} dateBounds={effectiveBounds} /> },
          { id: 'savings-rate-trend', node: <SavingsRateTrendChart rows={monthlyBreakdown.data} /> },
          { id: 'essential-split', node: <EssentialSplitCard data={essentialSplit.data} />, className: 'md:col-span-2' },
        ]}
      />
    </>
  );
}

export function AndroidApp() {
  const active = useQuery({ queryKey: ['activeUser'], queryFn: () => request<{ name: string }>('/api/active_user') });

  // Every effect of switching users flows through react-query's cache -
  // this key just forces a full remount of the dashboard subtree so no
  // stale component-local state (drilled-into month/year, etc.) survives
  // a switch, mirroring the desktop app's own "reset views on switch" rule.
  const dashboardKey = active.data?.name ?? 'loading';

  useEffect(() => {
    document.title = active.data?.name ? `Budget Dashboard - ${active.data.name}` : 'Budget Dashboard';
  }, [active.data?.name]);

  return (
    <div className="min-h-screen bg-background px-4 py-6 sm:px-6">
      <div className="mx-auto max-w-6xl">
        <div className="mb-1 flex items-center justify-between gap-3">
          <h1 className="text-2xl font-bold tracking-tight">Budget Dashboard</h1>
          <ModeToggle />
        </div>
        <p className="mb-4 mt-1 text-sm text-muted-foreground">
          Read-only, live from Google Sheets - viewing and editing transactions happens in the main app.
        </p>
        <UserSwitcher />
        <ReadOnlyDashboard key={dashboardKey} />
      </div>
    </div>
  );
}
