import ReactECharts from 'echarts-for-react';
import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import type { MonthlyBreakdownRow } from '../lib/types';
import { fmtMoney, fmtPct } from '../lib/format';
import { usePalette } from '../lib/usePalette';
import { useLocalStorage } from '../lib/useLocalStorage';
import { useIsDark } from '@/lib/useIsDark';
import { chartTheme } from '@/lib/chartTheme';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';

// Net Savings / Income for every month on record - pure arithmetic, already
// computed by monthly_breakdown() for the Dashboard's month/year dropdowns,
// just plotted here as its own trend instead of a table of numbers.
export function SavingsRateTrendChart({
  rows, height = 280,
}: { rows: MonthlyBreakdownRow[] | undefined; height?: number | string }) {
  const isDark = useIsDark();
  const t = chartTheme(isDark);
  const palette = usePalette();
  // Raw view plots the actual rupee Net Savings for the month instead of its
  // share of income - useful when the % reading is misleading on its own
  // (e.g. a tiny-income month swinging the rate wildly even though the real
  // rupee amount barely moved). Off by default: the rate is the more usual
  // thing to track month over month.
  const [rawAmount, setRawAmount] = useLocalStorage('dashboard.savingsRateTrend.raw', false);

  const option = useMemo<EChartsOption>(() => {
    const data = rows ?? [];
    const values = data.map((r) => (rawAmount ? r.net : r.savings_rate));
    return {
      backgroundColor: 'transparent',
      textStyle: { color: t.text },
      tooltip: {
        trigger: 'axis',
        valueFormatter: (v) => (rawAmount ? fmtMoney(v as number) : fmtPct(v as number)),
        backgroundColor: t.tooltipBg,
        borderColor: t.tooltipBorder,
        textStyle: { color: t.text },
      },
      grid: { left: 60, right: 20, top: 20, bottom: 40 },
      xAxis: {
        type: 'category', data: data.map((r) => r.period_key),
        // 'auto' picks the widest spacing that still fits every label
        // horizontally (dropping some rather than tilting them) - with many
        // months on record, rotated text was harder to read than fewer,
        // evenly-spaced, upright labels.
        axisLabel: { color: t.muted, interval: 'auto' }, axisLine: { lineStyle: { color: t.grid } },
      },
      yAxis: {
        type: 'value',
        axisLabel: {
          color: t.muted,
          formatter: (v: number) => (rawAmount ? fmtMoney(v) : `${(v * 100).toFixed(0)}%`),
        },
        splitLine: { lineStyle: { color: t.grid } },
      },
      series: [{
        type: 'line', data: values, smooth: true,
        areaStyle: { color: palette.net, opacity: 0.12 }, color: palette.net,
        markLine: {
          silent: true, symbol: 'none', lineStyle: { color: t.muted, type: 'dashed' }, data: [{ yAxis: 0 }],
        },
      }],
    };
  }, [rows, t, palette, rawAmount]);

  if (!rows || rows.length < 2) return null;

  return (
    <Card>
      <CardHeader className="flex-col items-start gap-2 space-y-0">
        <CardTitle className="text-sm font-semibold">
          Monthly {rawAmount ? 'Net Savings' : 'Savings Rate'}
        </CardTitle>
        <ToggleGroup
          type="single" variant="outline" size="sm"
          value={rawAmount ? 'amount' : 'rate'}
          onValueChange={(v) => v && setRawAmount(v === 'amount')}
        >
          <ToggleGroupItem value="rate" className="px-2.5 text-xs">Rate</ToggleGroupItem>
          <ToggleGroupItem value="amount" className="px-2.5 text-xs">Amount</ToggleGroupItem>
        </ToggleGroup>
      </CardHeader>
      <CardContent>
        <ReactECharts option={option} className="w-full" style={{ height }} notMerge />
      </CardContent>
    </Card>
  );
}
