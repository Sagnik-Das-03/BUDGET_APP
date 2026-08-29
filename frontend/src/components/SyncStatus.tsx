import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';

export function SyncStatusWidget() {
  const queryClient = useQueryClient();
  const { data: status } = useQuery({
    queryKey: ['syncStatus'],
    queryFn: api.syncStatus,
    refetchInterval: 15000,
  });

  const syncNow = useMutation({
    mutationFn: api.syncNow,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['syncStatus'] }),
  });

  if (!status) return <div className="sync-status">…</div>;

  let label: string;
  let cls = '';
  if (status.state === 'not_configured') { label = '⚙ Sync not configured'; }
  else if (status.state === 'syncing') { label = '⟳ Syncing…'; }
  else if (status.state === 'error') { label = '⚠ Sync failed'; cls = 'error'; }
  else {
    const when = status.last_synced_at ? new Date(status.last_synced_at).toLocaleTimeString() : 'never';
    label = `✓ Synced — ${when}`;
    cls = 'ok';
  }

  return (
    <div className={`sync-status ${cls}`}>
      {label}
      <button onClick={() => syncNow.mutate()} disabled={syncNow.isPending}>
        {syncNow.isPending ? '…' : 'Sync Now'}
      </button>
    </div>
  );
}
