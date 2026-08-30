import ReactECharts from 'echarts-for-react';
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { EChartsOption } from 'echarts';
import { ArrowDown, ArrowUp, ArrowUpDown, TrendingDown, TrendingUp } from 'lucide-react';
import { api } from '../lib/api';
import { fmtMoney, fmtPct } from '../lib/format';
import { shiftMonthValue, thisMonthValue } from '../lib/dates';
import { PeriodPicker, resolvePeriod, type PeriodValue } from '../components/PeriodPicker';
import { usePalette } from '../lib/usePalette';
import { useIsDark } from '@/lib/useIsDark';
import { chartTheme } from '@/lib/chartTheme';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { cn } from '@/lib/utils';

type SortKey = 'category' | 'a' | 'b' | 'delta' | 'deltaPct';

const METRICS: { key: 'income' | 'expenses' | 'sip' | 'cash_savings' | 'net'; label: string }[] = [
  { key: 'income', label: 'Income' },
  { key: 'expenses', label: 'Expenses' },
  { key: 'sip', label: 'SIP' },
  { key: 'cash_savings', label: 'Cash Savings' },
  { key: 'net', label: 'Net Savings' },
];

function deltaPct(a: number, b: number): number | null {
  if (!a) return null;
  return (b - a) / Math.abs(a);
}

function DeltaCell({ a, b }: { a: number; b: number }) {
  const d = deltaPct(a, b);
  if (d === null) return <span className="text-muted-foreground">—</span>;
  const up = d >= 0;
  return (
    <span className={cn(up ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive')}>
      {up ? '▲' : '▼'} {Math.abs(d * 100).toFixed(1)}%
    </span>
  );
}

function monthPeriod(month: string): PeriodValue {
  return { type: 'month', month, week: '', from: '', to: '' };
}

export function Compare() {
  const thisMonth = thisMonthValue();
  const [periodA, setPeriodA] = useState<PeriodValue>(monthPeriod(thisMonth));
  const [periodB, setPeriodB] = useState<PeriodValue>(monthPeriod(shiftMonthValue(thisMonth, -1)));
  const [sortKey, setSortKey] = useState<SortKey>('delta');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const isDark = useIsDark();
  const t = chartTheme(isDark);
  const palette = usePalette();

  function applyPreset(monthA: string, monthB: string) {
    setPeriodA(monthPeriod(monthA));
    setPeriodB(monthPeriod(monthB));
  }

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('desc'); }
  }

  const resolvedA = resolvePeriod(periodA);
  const resolvedB = resolvePeriod(periodB);

  const summaryA = useQuery({
    queryKey: ['compareSummary', resolvedA],
    queryFn: () => api.summary('custom', { date_from: resolvedA!.date_from, date_to: resolvedA!.date_to }),
    enabled: !!resolvedA,
  });
  const summaryB = useQuery({
    queryKey: ['compareSummary', resolvedB],
    queryFn: () => api.summary('custom', { date_from: resolvedB!.date_from, date_to: resolvedB!.date_to }),
    enabled: !!resolvedB,
  });
  const categoryA = useQuery({
    queryKey: ['compareCategory', resolvedA],
    queryFn: () => api.byCategory('custom', 'Expense', { date_from: resolvedA!.date_from, date_to: resolvedA!.date_to }),
    enabled: !!resolvedA,
  });
  const categoryB = useQuery({
    queryKey: ['compareCategory', resolvedB],
    queryFn: () => api.byCategory('custom', 'Expense', { date_from: resolvedB!.date_from, date_to: resolvedB!.date_to }),
    enabled: !!resolvedB,
  });

  const chartOption = useMemo<EChartsOption>(() => {
    const names = Array.from(new Set([
      ...(categoryA.data ?? []).map((c) => c.category),
      ...(categoryB.data ?? []).map((c) => c.category),
    ])).sort();
    const byNameA = Object.fromEntries((categoryA.data ?? []).map((c) => [c.category, c.total]));
    const byNameB = Object.fromEntries((categoryB.data ?? []).map((c) => [c.category, c.total]));
    return {
      backgroundColor: 'transparent',
      textStyle: { color: t.text },
      tooltip: {
        trigger: 'axis',
        valueFormatter: (v) => fmtMoney(v as number),
        backgroundColor: t.tooltipBg,
        borderColor: t.tooltipBorder,
        textStyle: { color: t.text },
      },
      legend: { bottom: 0, textStyle: { color: t.muted } },
      grid: { left: 60, right: 20, top: 20, bottom: 60 },
      xAxis: { type: 'category', data: names, axisLabel: { rotate: 30, color: t.muted }, axisLine: { lineStyle: { color: t.grid } } },
      yAxis: { type: 'value', splitLine: { lineStyle: { color: t.grid } }, axisLabel: { color: t.muted } },
      series: [
        { name: resolvedA?.label ?? 'Period A', type: 'bar', data: names.map((n) => byNameA[n] ?? 0), color: palette.income, barMaxWidth: 28 },
        { name: resolvedB?.label ?? 'Period B', type: 'bar', data: names.map((n) => byNameB[n] ?? 0), color: palette.expenses, barMaxWidth: 28 },
      ],
    };
  }, [categoryA.data, categoryB.data, resolvedA, resolvedB, t, palette]);

  const categoryComparison = useMemo(() => {
    const names = Array.from(new Set([
      ...(categoryA.data ?? []).map((c) => c.category),
      ...(categoryB.data ?? []).map((c) => c.category),
    ]));
    const byNameA = Object.fromEntries((categoryA.data ?? []).map((c) => [c.category, c.total]));
    const byNameB = Object.fromEntries((categoryB.data ?? []).map((c) => [c.category, c.total]));
    return names.map((category) => {
      const a = byNameA[category] ?? 0;
      const b = byNameB[category] ?? 0;
      const delta = b - a;
      return { category, a, b, delta, deltaPct: a === 0 ? null : delta / a };
    });
  }, [categoryA.data, categoryB.data]);

  const sortedCategoryComparison = useMemo(() => {
    const rows = [...categoryComparison];
    rows.sort((x, y) => {
      const cmp = sortKey === 'category' ? x.category.localeCompare(y.category)
        : sortKey === 'deltaPct' ? (x.deltaPct ?? -Infinity) - (y.deltaPct ?? -Infinity)
        : x[sortKey] - y[sortKey];
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return rows;
  }, [categoryComparison, sortKey, sortDir]);

  // Biggest absolute change (₹), not biggest %, so a category going from ₹10 to
  // ₹50 (a dramatic-looking +400%) doesn't outrank a real ₹5,000 swing elsewhere.
  const biggestMover = useMemo(() => {
    if (!categoryComparison.length) return null;
    const top = categoryComparison.reduce((max, c) => (Math.abs(c.delta) > Math.abs(max.delta) ? c : max));
    return top.delta === 0 ? null : top;
  }, [categoryComparison]);

  function SortHead({ label, sortKeyValue, align = 'left' }: { label: string; sortKeyValue: SortKey; align?: 'left' | 'right' }) {
    const active = sortKey === sortKeyValue;
    const Icon = !active ? ArrowUpDown : sortDir === 'asc' ? ArrowUp : ArrowDown;
    return (
      <TableHead className={align === 'right' ? 'text-right' : undefined}>
        <button
          type="button"
          onClick={() => toggleSort(sortKeyValue)}
          className={cn(
            'inline-flex items-center gap-1 hover:text-foreground',
            align === 'right' && 'flex-row-reverse',
            active && 'text-foreground',
          )}
        >
          {label}
          <Icon className="size-3" />
        </button>
      </TableHead>
    );
  }

  return (
    <>
      <h1 className="text-2xl font-bold tracking-tight">Compare</h1>
      <p className="mb-5 mt-1 text-sm text-muted-foreground">Put any two weeks, months, or custom date ranges side by side.</p>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">Quick:</span>
        <Button variant="outline" size="sm" onClick={() => applyPreset(thisMonth, shiftMonthValue(thisMonth, -1))}>
          This month vs last month
        </Button>
        <Button variant="outline" size="sm" onClick={() => applyPreset(thisMonth, shiftMonthValue(thisMonth, -12))}>
          This month vs same month last year
        </Button>
      </div>

      <div className="mb-5 grid grid-cols-1 gap-5 md:grid-cols-2">
        <PeriodPicker title="Period A" value={periodA} onChange={setPeriodA} />
        <PeriodPicker title="Period B" value={periodB} onChange={setPeriodB} />
      </div>

      {!resolvedA || !resolvedB ? (
        <div className="py-8 text-center text-sm text-muted-foreground">Pick a valid range for both periods.</div>
      ) : (
        <>
          {biggestMover && (
            <div className={cn(
              'mb-5 flex items-center gap-2.5 rounded-lg border px-3.5 py-2.5 text-sm',
              biggestMover.delta > 0
                ? 'border-red-200 bg-red-50 text-red-900 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-200'
                : 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900/50 dark:bg-emerald-950/40 dark:text-emerald-200',
            )}>
              {biggestMover.delta > 0 ? <TrendingUp className="size-4 shrink-0" /> : <TrendingDown className="size-4 shrink-0" />}
              <span className="font-semibold">Biggest mover: {biggestMover.category}</span>
              <span>
                {biggestMover.delta > 0 ? 'up' : 'down'} {fmtMoney(Math.abs(biggestMover.delta))}
                {biggestMover.deltaPct !== null && ` (${biggestMover.delta > 0 ? '+' : ''}${(biggestMover.deltaPct * 100).toFixed(0)}%)`}
              </span>
            </div>
          )}

          <Card className="mb-6 py-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Metric</TableHead>
                  <TableHead className="text-right">{resolvedA.label}</TableHead>
                  <TableHead className="text-right">{resolvedB.label}</TableHead>
                  <TableHead className="text-right">Change</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {METRICS.map((m) => {
                  const a = summaryA.data?.[m.key] ?? 0;
                  const b = summaryB.data?.[m.key] ?? 0;
                  return (
                    <TableRow key={m.key}>
                      <TableCell>{m.label}</TableCell>
                      <TableCell className="text-right tabular-nums">{fmtMoney(a)}</TableCell>
                      <TableCell className="text-right tabular-nums">{fmtMoney(b)}</TableCell>
                      <TableCell className="text-right"><DeltaCell a={a} b={b} /></TableCell>
                    </TableRow>
                  );
                })}
                <TableRow>
                  <TableCell>Savings Rate</TableCell>
                  <TableCell className="text-right tabular-nums">{fmtPct(summaryA.data?.savings_rate)}</TableCell>
                  <TableCell className="text-right tabular-nums">{fmtPct(summaryB.data?.savings_rate)}</TableCell>
                  <TableCell className="text-right">—</TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-semibold">Spend by Category: {resolvedA.label} vs {resolvedB.label}</CardTitle>
            </CardHeader>
            <CardContent>
              <ReactECharts option={chartOption} className="w-full h-[340px]" notMerge />
            </CardContent>
          </Card>

          <Card className="mt-6 py-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <SortHead label="Category" sortKeyValue="category" />
                  <SortHead label={resolvedA.label} sortKeyValue="a" align="right" />
                  <SortHead label={resolvedB.label} sortKeyValue="b" align="right" />
                  <SortHead label="Change (₹)" sortKeyValue="delta" align="right" />
                  <SortHead label="Change (%)" sortKeyValue="deltaPct" align="right" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {!sortedCategoryComparison.length ? (
                  <TableRow><TableCell colSpan={5}>
                    <div className="py-8 text-center text-sm text-muted-foreground">No expense categories in either period.</div>
                  </TableCell></TableRow>
                ) : sortedCategoryComparison.map((row) => (
                  <TableRow key={row.category}>
                    <TableCell>{row.category}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmtMoney(row.a)}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmtMoney(row.b)}</TableCell>
                    <TableCell className={cn(
                      'text-right tabular-nums font-medium',
                      row.delta > 0 && 'text-destructive',
                      row.delta < 0 && 'text-emerald-600 dark:text-emerald-400',
                    )}>
                      {row.delta > 0 ? '+' : ''}{fmtMoney(row.delta)}
                    </TableCell>
                    <TableCell className={cn(
                      'text-right tabular-nums',
                      row.delta > 0 && 'text-destructive',
                      row.delta < 0 && 'text-emerald-600 dark:text-emerald-400',
                    )}>
                      {row.a === 0 ? (
                        <span className="text-muted-foreground">New</span>
                      ) : (
                        `${row.deltaPct! > 0 ? '+' : ''}${(row.deltaPct! * 100).toFixed(0)}%`
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </>
      )}
    </>
  );
}
