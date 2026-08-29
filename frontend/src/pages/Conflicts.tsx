import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import { fmtMoney } from '../lib/format';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

export function Conflicts() {
  const queryClient = useQueryClient();
  const conflicts = useQuery({ queryKey: ['conflicts'], queryFn: api.listConflicts });

  const resolve = useMutation({
    mutationFn: ({ id, keep }: { id: string; keep: 'app' | 'sheets' }) => api.resolveConflict(id, keep),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['conflicts'] }),
  });

  return (
    <>
      <h1 className="text-2xl font-bold tracking-tight">Conflicts</h1>
      <p className="mb-5 mt-1 text-sm text-muted-foreground">
        A transaction changed on both sides between syncs. Pick which value to keep — nothing is overwritten silently.
      </p>
      {!conflicts.data?.length ? (
        <div className="py-8 text-center text-sm text-muted-foreground">No conflicts. Everything in sync.</div>
      ) : (
        <div className="flex flex-col gap-4">
          {conflicts.data.map((r) => (
            <Card key={r.transaction_id} className="border-destructive/40">
              <CardHeader>
                <CardTitle className="font-mono text-sm font-medium">{r.transaction_id}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="rounded-lg bg-muted p-3 text-sm">
                    <h4 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">App value</h4>
                    {r.app_value.date} — {r.app_value.description}<br />
                    {fmtMoney(r.app_value.amount)} · {r.app_value.transaction_type} · {r.app_value.category} · {r.app_value.account}
                  </div>
                  <div className="rounded-lg bg-muted p-3 text-sm">
                    <h4 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Google Sheets value</h4>
                    {r.sheet_value ? (
                      <>{r.sheet_value.date} — {r.sheet_value.description}<br />
                        {fmtMoney(r.sheet_value.amount)} · {r.sheet_value.transaction_type} · {r.sheet_value.category} · {r.sheet_value.account}</>
                    ) : '—'}
                  </div>
                </div>
                <div className="mt-3.5 flex gap-2">
                  <Button size="sm" onClick={() => resolve.mutate({ id: r.transaction_id, keep: 'app' })}>Keep App</Button>
                  <Button size="sm" variant="outline" onClick={() => resolve.mutate({ id: r.transaction_id, keep: 'sheets' })}>Keep Sheets</Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
