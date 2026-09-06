import ReactECharts from 'echarts-for-react';
import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import type { MonthlyBreakdownRow } from '../lib/types';
import { fmtPct } from '../lib/format';
import { usePalette } from '../lib/usePalette';
import { useIsDark } from '@/lib/useIsDark';
import { chartTheme } from '@/lib/chartTheme';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

// Net Savings / Income for every month on record - pure arithmetic, already
// computed by monthly_breakdown() for the Dashboard's month/year dropdowns,
// just plotted here as its own trend instead of a table of numbers.
export function SavingsRateTrendChart({ rows }: { rows: MonthlyBreakdownRow[] | undefined }) {
  const isDark = useIsDark();
  const t = chartTheme(isDark);
  const palette = usePalette();

  const option = useMemo<EChartsOption>(() => {
    const data = rows ?? [];
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
        type: 'line', data: data.map((r) => r.savings_rate), smooth: true,
        areaStyle: { color: palette.net, opacity: 0.12 }, color: palette.net,
        markLine: { silent: true, symbol: 'none', lineStyle: { color: t.muted, type: 'dashed' }, data: [{ yAxis: 0 }] },
      }],
    };
  }, [rows, t, palette]);

  if (!rows || rows.length < 2) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-semibold">Monthly Savings Rate</CardTitle>
      </CardHeader>
      <CardContent>
        <ReactECharts option={option} className="h-[280px] w-full" notMerge />
      </CardContent>
    </Card>
  );
}
