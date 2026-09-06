import ReactECharts from 'echarts-for-react';
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { EChartsOption } from 'echarts';
import { CalendarClock } from 'lucide-react';
import { api, type DateBounds } from '../lib/api';
import { fmtMoney } from '../lib/format';
import { usePalette } from '../lib/usePalette';
import { useIsDark } from '@/lib/useIsDark';
import { chartTheme } from '@/lib/chartTheme';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const DAY_ABBR: Record<string, string> = {
  Monday: 'Mon', Tuesday: 'Tue', Wednesday: 'Wed', Thursday: 'Thu', Friday: 'Fri', Saturday: 'Sat', Sunday: 'Sun',
};

interface SpendingPatternCardProps {
  range: string;
  dateBounds?: DateBounds;
}

// Pure descriptive breakdown of WHEN expense spending happens within a week
// and within a month - no AI, no threshold. Explains, for example, why an
// early-month "at this pace" forecast can overshoot if spending is
// naturally front-loaded, or surfaces a "weekend spender" pattern.
export function SpendingPatternCard({ range, dateBounds }: SpendingPatternCardProps) {
  const isDark = useIsDark();
  const t = chartTheme(isDark);
  const palette = usePalette();
  const pattern = useQuery({
    queryKey: ['spendingPattern', range, dateBounds?.date_from, dateBounds?.date_to],
    queryFn: () => api.spendingPattern(range, dateBounds),
  });

  const barOption = (labels: string[], values: number[]): EChartsOption => ({
    backgroundColor: 'transparent',
    textStyle: { color: t.text },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v) => fmtMoney(v as number),
      backgroundColor: t.tooltipBg,
      borderColor: t.tooltipBorder,
      textStyle: { color: t.text },
    },
    grid: { left: 50, right: 12, top: 12, bottom: 24 },
    xAxis: { type: 'category', data: labels, axisLabel: { color: t.muted }, axisLine: { lineStyle: { color: t.grid } } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: t.grid } }, axisLabel: { color: t.muted } },
    series: [{ type: 'bar', data: values, color: palette.expenses, barMaxWidth: 28 }],
  });

  const dowOption = useMemo(() => {
    const rows = pattern.data?.by_day_of_week ?? [];
    return barOption(rows.map((r) => DAY_ABBR[r.day!] ?? r.day!), rows.map((r) => r.total));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pattern.data, t, palette]);

  const thirdOption = useMemo(() => {
    const rows = pattern.data?.by_month_third ?? [];
    return barOption(rows.map((r) => r.label!), rows.map((r) => r.total));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pattern.data, t, palette]);

  const total = (pattern.data?.by_day_of_week ?? []).reduce((sum, r) => sum + r.total, 0);
  if (!total) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          <CalendarClock className="size-4 text-primary" /> Spending Pattern
        </CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <p className="mb-1 text-xs text-muted-foreground">By day of week</p>
          <ReactECharts option={dowOption} className="h-[180px] w-full" notMerge />
        </div>
        <div>
          <p className="mb-1 text-xs text-muted-foreground">By part of the month</p>
          <ReactECharts option={thirdOption} className="h-[180px] w-full" notMerge />
        </div>
      </CardContent>
    </Card>
  );
}
