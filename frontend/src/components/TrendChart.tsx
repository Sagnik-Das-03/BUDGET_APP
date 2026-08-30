import ReactECharts from 'echarts-for-react';
import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import type { TrendForRange, TrendRow } from '../lib/types';
import { usePalette } from '../lib/usePalette';
import { ChartTypeToggle } from './ChartTypeToggle';
import { useLocalStorage } from '../lib/useLocalStorage';
import { useIsDark } from '@/lib/useIsDark';
import { chartTheme } from '@/lib/chartTheme';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const GRANULARITY_TITLE: Record<string, string> = {
  daily: 'Daily Breakdown (This Week)',
  weekly: 'Weekly Breakdown (This Month)',
  monthly: 'Monthly Breakdown (This Year)',
  yearly: 'Yearly Breakdown (All Time)',
};

function rowLabel(row: TrendRow): string {
  return String(row.day ?? row.week_key ?? row.period_key ?? row.year ?? '');
}

export function TrendChart({ data }: { data: TrendForRange | undefined }) {
  const [type, setType] = useLocalStorage('dashboard.chartType.trend', 'line');
  const isDark = useIsDark();
  const t = chartTheme(isDark);
  const palette = usePalette();

  const option = useMemo<EChartsOption>(() => {
    const rows = data?.rows ?? [];
    const labels = rows.map(rowLabel);
    const seriesType: 'bar' | 'line' = type === 'bar' ? 'bar' : 'line';
    const mk = (name: string, values: number[], color: string) => ({
      name, type: seriesType, data: values, color,
      smooth: seriesType === 'line' ? 0.2 : undefined,
      lineStyle: { width: 2 }, symbolSize: 6,
    });
    return {
      backgroundColor: 'transparent',
      textStyle: { color: t.text },
      tooltip: {
        trigger: 'axis',
        backgroundColor: t.tooltipBg,
        borderColor: t.tooltipBorder,
        textStyle: { color: t.text },
      },
      legend: { bottom: 0, textStyle: { color: t.muted } },
      grid: { left: 50, right: 20, top: 20, bottom: 40 },
      xAxis: { type: 'category', data: labels, axisLine: { lineStyle: { color: t.grid } }, axisLabel: { color: t.muted } },
      yAxis: { type: 'value', splitLine: { lineStyle: { color: t.grid } }, axisLabel: { color: t.muted } },
      series: [
        mk('Income', rows.map((r) => r.income), palette.income),
        mk('Expenses', rows.map((r) => r.expenses), palette.expenses),
        mk('Net Savings', rows.map((r) => r.net), palette.net),
      ],
    };
  }, [data, type, t, palette]);

  return (
    <Card className="col-span-full">
      <CardHeader className="flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle className="text-sm font-semibold">{data ? GRANULARITY_TITLE[data.granularity] : 'Trend'}</CardTitle>
        <ChartTypeToggle
          value={type}
          onChange={setType}
          options={[{ type: 'line', label: 'Line' }, { type: 'bar', label: 'Bar' }]}
        />
      </CardHeader>
      <CardContent>
        <ReactECharts option={option} className="w-full h-[340px]" notMerge />
      </CardContent>
    </Card>
  );
}
