import ReactECharts from 'echarts-for-react';
import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import type { MonthlyBreakdownRow } from '../lib/types';
import { fmtPct } from '../lib/format';
import { usePalette } from '../lib/usePalette';
import { useLocalStorage } from '../lib/useLocalStorage';
import { useIsDark } from '@/lib/useIsDark';
import { chartTheme } from '@/lib/chartTheme';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Toggle } from '@/components/ui/toggle';

// Net Savings / Income for every month on record - pure arithmetic, already
// computed by monthly_breakdown() for the Dashboard's month/year dropdowns,
// just plotted here as its own trend instead of a table of numbers.
export function SavingsRateTrendChart({
  rows, height = 280,
}: { rows: MonthlyBreakdownRow[] | undefined; height?: number | string }) {
  const isDark = useIsDark();
  const t = chartTheme(isDark);
  const palette = usePalette();
  // Abs view answers "how big was the swing" regardless of direction - useful
  // for spotting volatile months at a glance without a losing month's negative
  // bar reading as smaller than it is. Off by default: sign (saved vs. lost)
  // is the more important fact most of the time.
  const [absValue, setAbsValue] = useLocalStorage('dashboard.savingsRateTrend.abs', false);

  const option = useMemo<EChartsOption>(() => {
    const data = rows ?? [];
    const values = data.map((r) => (absValue ? Math.abs(r.savings_rate) : r.savings_rate));
    return {
      backgroundColor: 'transparent',
      textStyle: { color: t.text },
      tooltip: {
        trigger: 'axis',
        valueFormatter: (v) => fmtPct(v as number),
        backgroundColor: t.tooltipBg,
        borderColor: t.tooltipBorder,
        textStyle: { color: t.text },
      },
      grid: { left: 50, right: 20, top: 20, bottom: 40 },
      xAxis: {
        type: 'category', data: data.map((r) => r.period_key),
        axisLabel: { rotate: 45, color: t.muted }, axisLine: { lineStyle: { color: t.grid } },
      },
      yAxis: {
        type: 'value', axisLabel: { color: t.muted, formatter: (v: number) => `${(v * 100).toFixed(0)}%` },
        splitLine: { lineStyle: { color: t.grid } },
      },
      series: [{
        type: 'line', data: values, smooth: true,
        areaStyle: { color: palette.net, opacity: 0.12 }, color: palette.net,
        markLine: absValue ? undefined : {
          silent: true, symbol: 'none', lineStyle: { color: t.muted, type: 'dashed' }, data: [{ yAxis: 0 }],
        },
      }],
    };
  }, [rows, t, palette, absValue]);

  if (!rows || rows.length < 2) return null;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle className="text-sm font-semibold">Monthly Savings Rate</CardTitle>
        <Toggle
          size="sm" variant="outline" pressed={absValue} onPressedChange={setAbsValue}
          aria-label="Show absolute value"
        >
          Abs
        </Toggle>
      </CardHeader>
      <CardContent>
        <ReactECharts option={option} className="w-full" style={{ height }} notMerge />
      </CardContent>
    </Card>
  );
}
