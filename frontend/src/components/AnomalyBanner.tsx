import { TrendingUp } from 'lucide-react';
import type { Anomaly } from '../lib/types';
import { fmtMoney } from '../lib/format';

export function AnomalyBanner({ anomalies }: { anomalies: Anomaly[] | undefined }) {
  if (!anomalies || !anomalies.length) return null;
  return (
    <div className="mb-5 flex flex-col gap-2">
      {anomalies.map((a) => (
        <div
          key={a.transaction_id}
          className="flex items-center gap-2.5 rounded-lg border border-sky-200 bg-sky-50 px-3.5 py-2.5 text-sm text-sky-900 dark:border-sky-900/50 dark:bg-sky-950/40 dark:text-sky-200"
        >
          <TrendingUp className="size-4 shrink-0" />
          <span className="font-semibold">{a.description}</span>
          <span>
            — {fmtMoney(a.amount)} is {a.multiple.toFixed(1)}x your usual {a.category} spend ({fmtMoney(a.category_avg)} avg)
          </span>
        </div>
      ))}
    </div>
  );
}
