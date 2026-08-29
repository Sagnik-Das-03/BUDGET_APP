import ReactECharts from 'echarts-for-react';
import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import type { TrendForRange, TrendRow } from '../lib/types';
import { PALETTE } from '../lib/palette';
import { ChartTypeToggle } from './ChartTypeToggle';
import { useLocalStorage } from '../lib/useLocalStorage';

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
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0 },
      grid: { left: 50, right: 20, top: 20, bottom: 40 },
      xAxis: { type: 'category', data: labels },
      yAxis: { type: 'value' },
      series: [
        mk('Income', rows.map((r) => r.income), PALETTE.income),
        mk('Expenses', rows.map((r) => r.expenses), PALETTE.expenses),
        mk('Net Savings', rows.map((r) => r.net), PALETTE.net),
      ],
    };
  }, [data, type]);

  return (
    <div className="chart-card full">
      <div className="chart-card-head">
        <h3>{data ? GRANULARITY_TITLE[data.granularity] : 'Trend'}</h3>
        <ChartTypeToggle
          value={type}
          onChange={setType}
          options={[{ type: 'line', label: 'Line' }, { type: 'bar', label: 'Bar' }]}
        />
      </div>
      <ReactECharts option={option} className="echart tall" notMerge />
    </div>
  );
}
