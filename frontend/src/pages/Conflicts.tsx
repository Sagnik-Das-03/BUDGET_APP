import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import { fmtMoney } from '../lib/format';

export function Conflicts() {
  const queryClient = useQueryClient();
  const conflicts = useQuery({ queryKey: ['conflicts'], queryFn: api.listConflicts });

  const resolve = useMutation({
    mutationFn: ({ id, keep }: { id: string; keep: 'app' | 'sheets' }) => api.resolveConflict(id, keep),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['conflicts'] }),
  });

  return (
    <>
      <h1>Conflicts</h1>
      <p className="subtitle">A transaction changed on both sides between syncs. Pick which value to keep — nothing is overwritten silently.</p>
      {!conflicts.data?.length ? (
        <div className="empty-state">No conflicts. Everything in sync.</div>
      ) : conflicts.data.map((r) => (
        <div key={r.transaction_id} className="conflict-card">
          <strong>{r.transaction_id}</strong>
          <div className="conflict-values">
            <div className="conflict-col">
              <h4>App value</h4>
              {r.app_value.date} — {r.app_value.description}<br />
              {fmtMoney(r.app_value.amount)} · {r.app_value.transaction_type} · {r.app_value.category} · {r.app_value.account}
            </div>
            <div className="conflict-col">
              <h4>Google Sheets value</h4>
              {r.sheet_value ? (
                <>{r.sheet_value.date} — {r.sheet_value.description}<br />
                  {fmtMoney(r.sheet_value.amount)} · {r.sheet_value.transaction_type} · {r.sheet_value.category} · {r.sheet_value.account}</>
              ) : '—'}
            </div>
          </div>
          <button className="btn primary" onClick={() => resolve.mutate({ id: r.transaction_id, keep: 'app' })}>Keep App</button>{' '}
          <button className="btn" onClick={() => resolve.mutate({ id: r.transaction_id, keep: 'sheets' })}>Keep Sheets</button>
        </div>
      ))}
    </>
  );
}
