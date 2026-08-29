import ReactECharts from 'echarts-for-react';
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { EChartsOption } from 'echarts';
import { api } from '../lib/api';
import { fmtMoney, fmtPct } from '../lib/format';
import { shiftMonthValue, thisMonthValue } from '../lib/dates';
import { PeriodPicker, resolvePeriod, type PeriodValue } from '../components/PeriodPicker';
import { PALETTE } from '../lib/palette';

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
  if (d === null) return <span style={{ color: 'var(--ink-muted)' }}>—</span>;
  const up = d >= 0;
  return <span className={up ? 'delta-up' : 'delta-down'}>{up ? '▲' : '▼'} {Math.abs(d * 100).toFixed(1)}%</span>;
}

export function Compare() {
  const thisMonth = thisMonthValue();
  const [periodA, setPeriodA] = useState<PeriodValue>({
    type: 'month', month: thisMonth, week: '', from: '', to: '',
  });
  const [periodB, setPeriodB] = useState<PeriodValue>({
    type: 'month', month: shiftMonthValue(thisMonth, -1), week: '', from: '', to: '',
  });

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
      tooltip: { trigger: 'axis', valueFormatter: (v) => fmtMoney(v as number) },
      legend: { bottom: 0 },
      grid: { left: 60, right: 20, top: 20, bottom: 60 },
      xAxis: { type: 'category', data: names, axisLabel: { rotate: 30 } },
      yAxis: { type: 'value' },
      series: [
        { name: resolvedA?.label ?? 'Period A', type: 'bar', data: names.map((n) => byNameA[n] ?? 0), color: PALETTE.income, barMaxWidth: 28 },
        { name: resolvedB?.label ?? 'Period B', type: 'bar', data: names.map((n) => byNameB[n] ?? 0), color: PALETTE.expenses, barMaxWidth: 28 },
      ],
    };
  }, [categoryA.data, categoryB.data, resolvedA, resolvedB]);

  return (
    <>
      <h1>Compare</h1>
      <p className="subtitle">Put any two weeks, months, or custom date ranges side by side.</p>

      <div className="chart-grid" style={{ marginBottom: 20 }}>
        <PeriodPicker title="Period A" value={periodA} onChange={setPeriodA} />
        <PeriodPicker title="Period B" value={periodB} onChange={setPeriodB} />
      </div>

      {!resolvedA || !resolvedB ? (
        <div className="empty-state">Pick a valid range for both periods.</div>
      ) : (
        <>
          <table style={{ marginBottom: 24 }}>
            <thead>
              <tr>
                <th>Metric</th>
                <th className="amount">{resolvedA.label}</th>
                <th className="amount">{resolvedB.label}</th>
                <th className="amount">Change</th>
              </tr>
            </thead>
            <tbody>
              {METRICS.map((m) => {
                const a = summaryA.data?.[m.key] ?? 0;
                const b = summaryB.data?.[m.key] ?? 0;
                return (
                  <tr key={m.key}>
                    <td>{m.label}</td>
                    <td className="amount">{fmtMoney(a)}</td>
                    <td className="amount">{fmtMoney(b)}</td>
                    <td className="amount"><DeltaCell a={a} b={b} /></td>
                  </tr>
                );
              })}
              <tr>
                <td>Savings Rate</td>
                <td className="amount">{fmtPct(summaryA.data?.savings_rate)}</td>
                <td className="amount">{fmtPct(summaryB.data?.savings_rate)}</td>
                <td className="amount">—</td>
              </tr>
            </tbody>
          </table>

          <div className="chart-card full">
            <h3>Spend by Category: {resolvedA.label} vs {resolvedB.label}</h3>
            <ReactECharts option={chartOption} className="echart tall" notMerge />
          </div>
        </>
      )}
    </>
  );
}
