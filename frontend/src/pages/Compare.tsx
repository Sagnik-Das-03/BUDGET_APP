import ReactECharts from 'echarts-for-react';
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { EChartsOption } from 'echarts';
import { api } from '../lib/api';
import { fmtMoney, fmtPct } from '../lib/format';
import { shiftMonthValue, thisMonthValue } from '../lib/dates';
import { PeriodPicker, resolvePeriod, type PeriodValue } from '../components/PeriodPicker';
import { PALETTE } from '../lib/palette';
import { useIsDark } from '@/lib/useIsDark';
import { chartTheme } from '@/lib/chartTheme';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { cn } from '@/lib/utils';

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

export function Compare() {
  const thisMonth = thisMonthValue();
  const [periodA, setPeriodA] = useState<PeriodValue>({
    type: 'month', month: thisMonth, week: '', from: '', to: '',
  });
  const [periodB, setPeriodB] = useState<PeriodValue>({
    type: 'month', month: shiftMonthValue(thisMonth, -1), week: '', from: '', to: '',
  });
  const isDark = useIsDark();
  const t = chartTheme(isDark);

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
        { name: resolvedA?.label ?? 'Period A', type: 'bar', data: names.map((n) => byNameA[n] ?? 0), color: PALETTE.income, barMaxWidth: 28 },
        { name: resolvedB?.label ?? 'Period B', type: 'bar', data: names.map((n) => byNameB[n] ?? 0), color: PALETTE.expenses, barMaxWidth: 28 },
      ],
    };
  }, [categoryA.data, categoryB.data, resolvedA, resolvedB, t]);

  return (
    <>
      <h1 className="text-2xl font-bold tracking-tight">Compare</h1>
      <p className="mb-5 mt-1 text-sm text-muted-foreground">Put any two weeks, months, or custom date ranges side by side.</p>

      <div className="mb-5 grid grid-cols-1 gap-5 md:grid-cols-2">
        <PeriodPicker title="Period A" value={periodA} onChange={setPeriodA} />
        <PeriodPicker title="Period B" value={periodB} onChange={setPeriodB} />
      </div>

      {!resolvedA || !resolvedB ? (
        <div className="py-8 text-center text-sm text-muted-foreground">Pick a valid range for both periods.</div>
      ) : (
        <>
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
        </>
      )}
    </>
  );
}
