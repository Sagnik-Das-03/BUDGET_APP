import type { Highlights } from '../lib/types';
import { fmtMoney } from '../lib/format';

export function MetricsRow({ highlights }: { highlights: Highlights | undefined }) {
  const comparison = highlights?.comparison;
  const delta = comparison?.net_delta_pct;

  return (
    <div className="metrics-row">
      <div className="metric-chip">
        <span className="metric-icon">🏆</span>
        <div>
          <div className="metric-label">Top Category</div>
          <div className="metric-value">
            {highlights?.top_category
              ? `${highlights.top_category.category} (${fmtMoney(highlights.top_category.total)})`
              : '—'}
          </div>
        </div>
      </div>
      <div className="metric-chip">
        <span className="metric-icon">🧾</span>
        <div>
          <div className="metric-label">Transactions</div>
          <div className="metric-value">{highlights?.transaction_count ?? '—'}</div>
        </div>
      </div>
      <div className="metric-chip">
        <span className="metric-icon">📆</span>
        <div>
          <div className="metric-label">Avg Daily Spend</div>
          <div className="metric-value">
            {highlights ? `${fmtMoney(highlights.avg_daily_spend)} / day` : '—'}
          </div>
        </div>
      </div>
      <div className="metric-chip">
        <span className="metric-icon">📈</span>
        <div>
          <div className="metric-label">vs Previous Period</div>
          <div className="metric-value">
            {!comparison ? '—' : delta === null || delta === undefined ? 'n/a' : (
              <span className={delta >= 0 ? 'delta-up' : 'delta-down'}>
                {delta >= 0 ? '▲' : '▼'} {Math.abs(delta * 100).toFixed(1)}% net
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
