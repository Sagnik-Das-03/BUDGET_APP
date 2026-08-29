import ReactECharts from 'echarts-for-react';
import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import type { BudgetVsActual } from '../lib/types';
import { PALETTE } from '../lib/palette';
import { ChartTypeToggle } from './ChartTypeToggle';
import { useLocalStorage } from '../lib/useLocalStorage';
import { useIsDark } from '@/lib/useIsDark';
import { chartTheme } from '@/lib/chartTheme';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export function BudgetChart({ rows }: { rows: BudgetVsActual[] | undefined }) {
  const [type, setType] = useLocalStorage('dashboard.chartType.budget', 'bar');
  const isDark = useIsDark();
  const t = chartTheme(isDark);

  const option = useMemo<EChartsOption>(() => {
    const data = rows ?? [];
    const horizontal = type === 'hbar';
    const names = data.map((r) => r.category);
    return {
      backgroundColor: 'transparent',
      textStyle: { color: t.text },
      tooltip: {
        trigger: 'axis',
        valueFormatter: (v) => `₹${Number(v).toLocaleString('en-IN')}`,
        backgroundColor: t.tooltipBg,
        borderColor: t.tooltipBorder,
        textStyle: { color: t.text },
      },
      legend: { bottom: 0, textStyle: { color: t.muted } },
      grid: { left: horizontal ? 100 : 50, right: 20, top: 20, bottom: horizontal ? 40 : 60 },
      xAxis: horizontal
        ? { type: 'value', splitLine: { lineStyle: { color: t.grid } }, axisLabel: { color: t.muted } }
        : { type: 'category', data: names, axisLabel: { rotate: 30, color: t.muted }, axisLine: { lineStyle: { color: t.grid } } },
      yAxis: horizontal
        ? { type: 'category', data: names, axisLabel: { color: t.muted }, axisLine: { lineStyle: { color: t.grid } } }
        : { type: 'value', splitLine: { lineStyle: { color: t.grid } }, axisLabel: { color: t.muted } },
      series: [
        { name: 'Goal', type: 'bar', data: data.map((r) => r.goal), color: PALETTE.goal, barMaxWidth: 22 },
        { name: 'Actual', type: 'bar', data: data.map((r) => r.actual), color: PALETTE.income, barMaxWidth: 22 },
      ],
    };
  }, [rows, type, t]);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle className="text-sm font-semibold">Budget Goal vs Actual (This Month)</CardTitle>
        <ChartTypeToggle
          value={type} onChange={setType}
          options={[{ type: 'bar', label: 'Bar' }, { type: 'hbar', label: 'H-Bar' }]}
        />
      </CardHeader>
      <CardContent>
        <ReactECharts option={option} className="w-full h-[280px]" notMerge />
      </CardContent>
    </Card>
  );
}
