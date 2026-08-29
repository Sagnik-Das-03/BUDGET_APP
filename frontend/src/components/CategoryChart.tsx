import ReactECharts from 'echarts-for-react';
import { useMemo, useState } from 'react';
import type { EChartsOption } from 'echarts';
import type { CategoryDrilldownNode } from '../lib/types';
import { fmtMoney } from '../lib/format';
import { ChartTypeToggle } from './ChartTypeToggle';
import { useLocalStorage } from '../lib/useLocalStorage';

const TYPE_OPTIONS = [
  { type: 'bar', label: 'Bar' },
  { type: 'hbar', label: 'H-Bar' },
  { type: 'pie', label: 'Pie' },
  { type: 'donut', label: 'Donut' },
  { type: 'sunburst', label: 'Sunburst' },
];

export function CategoryChart({ tree, rangeLabel }: { tree: CategoryDrilldownNode[] | undefined; rangeLabel: string }) {
  const [type, setType] = useLocalStorage('dashboard.chartType.category', 'bar');
  const [selected, setSelected] = useState<string | null>(null);

  const option = useMemo<EChartsOption>(() => {
    const nodes = tree ?? [];
    const colored = nodes.map((c) => ({ name: c.name, value: c.value, itemStyle: { color: c.color } }));
    const names = nodes.map((c) => c.name);

    if (type === 'bar' || type === 'hbar') {
      const horizontal = type === 'hbar';
      return {
        tooltip: { trigger: 'item', valueFormatter: (v) => fmtMoney(v as number) },
        grid: { left: horizontal ? 100 : 50, right: 20, top: 20, bottom: horizontal ? 20 : 60 },
        xAxis: horizontal ? { type: 'value' } : { type: 'category', data: names, axisLabel: { rotate: 30 } },
        yAxis: horizontal ? { type: 'category', data: names } : { type: 'value' },
        series: [{ type: 'bar', data: colored, barMaxWidth: 36 }],
      };
    }
    if (type === 'pie' || type === 'donut') {
      return {
        tooltip: { trigger: 'item', valueFormatter: (v) => fmtMoney(v as number) },
        legend: { bottom: 0, type: 'scroll' },
        series: [{
          type: 'pie', radius: type === 'donut' ? ['40%', '70%'] : '65%', center: ['50%', '46%'],
          data: colored, label: { formatter: '{b}' },
        }],
      };
    }
    // sunburst
    return {
      tooltip: { valueFormatter: (v) => fmtMoney(v as number) },
      series: [{
        type: 'sunburst', radius: ['10%', '90%'], center: ['50%', '50%'],
        data: nodes.map((c) => ({
          name: c.name, value: c.value, itemStyle: { color: c.color },
          children: c.children.slice(0, 12).map((ch) => ({ name: ch.name, value: ch.value })),
        })),
        label: { minAngle: 8, rotate: 'tangential' },
        levels: [{}, { r0: '10%', r: '55%' }, { r0: '55%', r: '90%', label: { minAngle: 12 } }],
      }],
    };
  }, [tree, type]);

  function onEvents(params: any) {
    let categoryName: string | null = null;
    if (params.data && params.data.children) {
      categoryName = params.data.name;
    } else if (params.treePathInfo && params.treePathInfo.length > 1) {
      categoryName = params.treePathInfo[1].name;
    } else if (params.name) {
      categoryName = params.name;
    }
    if (categoryName) setSelected(categoryName);
  }

  const selectedNode = tree?.find((c) => c.name === selected);

  return (
    <div className="chart-card">
      <div className="chart-card-head">
        <h3>Spend by Category ({rangeLabel})</h3>
        <ChartTypeToggle value={type} onChange={setType} options={TYPE_OPTIONS} />
      </div>
      <ReactECharts
        option={option}
        className="echart"
        notMerge
        onEvents={{ click: onEvents }}
      />
      {selectedNode ? (
        <div className="drilldown-panel open">
          <div className="drilldown-panel-head">
            <strong>{selectedNode.name} — {selectedNode.children.length} transaction(s), {fmtMoney(selectedNode.value)}</strong>
            <button onClick={() => setSelected(null)}>✕ Close</button>
          </div>
          <table className="drilldown-table">
            <thead><tr><th>Date</th><th>Description</th><th className="amount">Amount</th></tr></thead>
            <tbody>
              {selectedNode.children.map((c, i) => (
                <tr key={i}><td>{c.date}</td><td>{c.name}</td><td className="amount">{fmtMoney(c.value)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="drilldown-hint">Click a category (or a slice/ring) to see its transactions.</div>
      )}
    </div>
  );
}
