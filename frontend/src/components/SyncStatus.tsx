import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Loader2, RefreshCw, Settings2, TriangleAlert } from 'lucide-react';
import { api } from '../lib/api';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

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

  if (!status) return null;

  let label: string;
  let icon = <RefreshCw className="size-3.5" />;
  let cls = 'text-muted-foreground';

  if (status.state === 'not_configured') {
    label = 'Sync not configured';
    icon = <Settings2 className="size-3.5" />;
  } else if (status.state === 'syncing') {
    label = 'Syncing…';
    icon = <Loader2 className="size-3.5 animate-spin" />;
  } else if (status.state === 'error') {
    label = 'Sync failed';
    icon = <TriangleAlert className="size-3.5" />;
    cls = 'text-destructive';
  } else {
    const when = status.last_synced_at ? new Date(status.last_synced_at).toLocaleTimeString() : 'never';
    label = `Synced — ${when}`;
    icon = <CheckCircle2 className="size-3.5" />;
    cls = 'text-emerald-600 dark:text-emerald-400';
  }

  return (
    <div className={cn('flex items-center gap-1.5 text-xs font-medium whitespace-nowrap', cls)}>
      {icon}
      <span className="hidden sm:inline">{label}</span>
      <Button
        variant="ghost"
        size="sm"
        className="h-6 px-2 text-xs"
        onClick={() => syncNow.mutate()}
        disabled={syncNow.isPending}
      >
        {syncNow.isPending ? '…' : 'Sync now'}
      </Button>
    </div>
  );
}
