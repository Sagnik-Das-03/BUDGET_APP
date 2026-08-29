import ReactECharts from 'echarts-for-react';
import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import type { BudgetVsActual } from '../lib/types';
import { PALETTE } from '../lib/palette';
import { ChartTypeToggle } from './ChartTypeToggle';
import { useLocalStorage } from '../lib/useLocalStorage';

export function BudgetChart({ rows }: { rows: BudgetVsActual[] | undefined }) {
  const [type, setType] = useLocalStorage('dashboard.chartType.budget', 'bar');

  const option = useMemo<EChartsOption>(() => {
    const data = rows ?? [];
    const horizontal = type === 'hbar';
    const names = data.map((r) => r.category);
    return {
      tooltip: { trigger: 'axis', valueFormatter: (v) => `₹${Number(v).toLocaleString('en-IN')}` },
      legend: { bottom: 0 },
      grid: { left: horizontal ? 100 : 50, right: 20, top: 20, bottom: horizontal ? 40 : 60 },
      xAxis: horizontal ? { type: 'value' } : { type: 'category', data: names, axisLabel: { rotate: 30 } },
      yAxis: horizontal ? { type: 'category', data: names } : { type: 'value' },
      series: [
        { name: 'Goal', type: 'bar', data: data.map((r) => r.goal), color: PALETTE.goal, barMaxWidth: 22 },
        { name: 'Actual', type: 'bar', data: data.map((r) => r.actual), color: PALETTE.income, barMaxWidth: 22 },
      ],
    };
  }, [rows, type]);

  return (
    <div className="chart-card">
      <div className="chart-card-head">
        <h3>Budget Goal vs Actual (This Month)</h3>
        <ChartTypeToggle
          value={type} onChange={setType}
          options={[{ type: 'bar', label: 'Bar' }, { type: 'hbar', label: 'H-Bar' }]}
        />
      </div>
      <ReactECharts option={option} className="echart" notMerge />
    </div>
  );
}
