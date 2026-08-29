import ReactECharts from 'echarts-for-react';
import { useMemo, useState } from 'react';
import type { EChartsOption } from 'echarts';
import type { CategoryDrilldownNode } from '../lib/types';
import { fmtMoney } from '../lib/format';
import { ChartTypeToggle } from './ChartTypeToggle';
import { useLocalStorage } from '../lib/useLocalStorage';
import { useIsDark } from '@/lib/useIsDark';
import { chartTheme } from '@/lib/chartTheme';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { X } from 'lucide-react';

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
  const isDark = useIsDark();
  const t = chartTheme(isDark);

  const option = useMemo<EChartsOption>(() => {
    const nodes = tree ?? [];
    const colored = nodes.map((c) => ({ name: c.name, value: c.value, itemStyle: { color: c.color } }));
    const names = nodes.map((c) => c.name);
    const base: EChartsOption = {
      backgroundColor: 'transparent',
      textStyle: { color: t.text },
      tooltip: {
        trigger: 'item',
        valueFormatter: (v) => fmtMoney(v as number),
        backgroundColor: t.tooltipBg,
        borderColor: t.tooltipBorder,
        textStyle: { color: t.text },
      },
    };

    if (type === 'bar' || type === 'hbar') {
      const horizontal = type === 'hbar';
      return {
        ...base,
        grid: { left: horizontal ? 100 : 50, right: 20, top: 20, bottom: horizontal ? 20 : 60 },
        xAxis: horizontal
          ? { type: 'value', splitLine: { lineStyle: { color: t.grid } }, axisLabel: { color: t.muted } }
          : { type: 'category', data: names, axisLabel: { rotate: 30, color: t.muted }, axisLine: { lineStyle: { color: t.grid } } },
        yAxis: horizontal
          ? { type: 'category', data: names, axisLabel: { color: t.muted }, axisLine: { lineStyle: { color: t.grid } } }
          : { type: 'value', splitLine: { lineStyle: { color: t.grid } }, axisLabel: { color: t.muted } },
        series: [{ type: 'bar', data: colored, barMaxWidth: 36 }],
      };
    }
    if (type === 'pie' || type === 'donut') {
      return {
        ...base,
        legend: { bottom: 0, type: 'scroll', textStyle: { color: t.muted } },
        series: [{
          type: 'pie', radius: type === 'donut' ? ['40%', '70%'] : '65%', center: ['50%', '46%'],
          data: colored, label: { formatter: '{b}', color: t.text },
        }],
      };
    }
    // sunburst
    return {
      ...base,
      series: [{
        type: 'sunburst', radius: ['10%', '90%'], center: ['50%', '50%'],
        data: nodes.map((c) => ({
          name: c.name, value: c.value, itemStyle: { color: c.color },
          children: c.children.slice(0, 12).map((ch) => ({ name: ch.name, value: ch.value })),
        })),
        label: { minAngle: 8, rotate: 'tangential', color: t.text },
        levels: [{}, { r0: '10%', r: '55%' }, { r0: '55%', r: '90%', label: { minAngle: 12 } }],
      }],
    };
  }, [tree, type, t]);

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
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle className="text-sm font-semibold">Spend by Category ({rangeLabel})</CardTitle>
        <ChartTypeToggle value={type} onChange={setType} options={TYPE_OPTIONS} />
      </CardHeader>
      <CardContent>
        <ReactECharts
          option={option}
          className="w-full h-[280px]"
          notMerge
          onEvents={{ click: onEvents }}
        />
        {selectedNode ? (
          <div className="mt-3.5 border-t pt-3.5">
            <div className="mb-2.5 flex items-center justify-between">
              <strong className="text-sm">
                {selectedNode.name} — {selectedNode.children.length} transaction(s), {fmtMoney(selectedNode.value)}
              </strong>
              <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => setSelected(null)}>
                <X className="size-3.5" /> Close
              </Button>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {selectedNode.children.map((c, i) => (
                  <TableRow key={i}>
                    <TableCell>{c.date}</TableCell>
                    <TableCell>{c.name}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmtMoney(c.value)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : (
          <div className="mt-2 text-xs text-muted-foreground">Click a category (or a slice/ring) to see its transactions.</div>
        )}
      </CardContent>
    </Card>
  );
}
