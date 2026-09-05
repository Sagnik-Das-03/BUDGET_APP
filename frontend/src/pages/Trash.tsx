import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { RotateCcw, Trash2 } from 'lucide-react';
import { api } from '../lib/api';
import { fmtMoney } from '../lib/format';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

export function Trash() {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const trash = useQuery({ queryKey: ['trash'], queryFn: api.listTrash });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['trash'] });
    queryClient.invalidateQueries({ queryKey: ['transactions'] });
  }

  const restore = useMutation({
    mutationFn: (id: string) => api.restoreTransaction(id),
    onSuccess: invalidate,
  });

  const permanentDelete = useMutation({
    mutationFn: (id: string) => api.permanentDeleteTransaction(id),
    onSuccess: invalidate,
    onError: (err: Error) => alert(err.message),
  });

  const bulkRestore = useMutation({
    mutationFn: (ids: string[]) => api.bulkRestoreTransactions(ids),
    onSuccess: () => {
      setSelected(new Set());
      invalidate();
    },
  });

  const bulkPermanentDelete = useMutation({
    mutationFn: (ids: string[]) => api.bulkPermanentDeleteTransactions(ids),
    onSuccess: (result) => {
      setSelected(new Set());
      invalidate();
      if (result.blocked > 0) {
        alert(`${result.deleted} permanently deleted. ${result.blocked} skipped - their deletion hasn't synced to Google Sheets yet.`);
      }
    },
  });

  function toggleRow(id: string, checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id); else next.delete(id);
      return next;
    });
  }

  function toggleAll(checked: boolean) {
    setSelected(checked ? new Set(trash.data?.map((t) => t.transaction_id)) : new Set());
  }

  const allVisibleSelected = !!trash.data?.length && trash.data.every((t) => selected.has(t.transaction_id));

  return (
    <>
      <h1 className="text-2xl font-bold tracking-tight">Trash</h1>
      <p className="mb-5 mt-1 text-sm text-muted-foreground">
        Deleted transactions stay here until you restore them or delete them permanently.
      </p>

      {selected.size > 0 && (
        <div className="mb-4 flex items-center gap-2.5 rounded-lg border bg-muted/40 px-3.5 py-2.5">
          <span className="text-sm font-medium">{selected.size} selected</span>
          <Button
            variant="outline"
            size="sm"
            disabled={bulkRestore.isPending}
            onClick={() => bulkRestore.mutate(Array.from(selected))}
          >
            <RotateCcw className="size-4" />
            {bulkRestore.isPending ? 'Restoring…' : 'Restore Selected'}
          </Button>
          <Button
            variant="destructive"
            size="sm"
            disabled={bulkPermanentDelete.isPending}
            onClick={() => {
              if (confirm(`Permanently delete ${selected.size} transaction${selected.size === 1 ? '' : 's'}? This cannot be undone.`)) {
                bulkPermanentDelete.mutate(Array.from(selected));
              }
            }}
          >
            <Trash2 className="size-4" />
            {bulkPermanentDelete.isPending ? 'Deleting…' : 'Delete Permanently'}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())}>Clear selection</Button>
        </div>
      )}

      <Card className="py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8 pl-6">
                <Checkbox
                  checked={allVisibleSelected}
                  onCheckedChange={(v) => toggleAll(v === true)}
                  aria-label="Select all trashed transactions"
                />
              </TableHead>
              <TableHead>Date</TableHead><TableHead>Description</TableHead><TableHead>Category</TableHead>
              <TableHead>Account</TableHead><TableHead>Type</TableHead>
              <TableHead className="text-right">Amount</TableHead><TableHead>Deleted</TableHead><TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!trash.data?.length ? (
              <TableRow><TableCell colSpan={9}>
                <div className="py-8 text-center text-sm text-muted-foreground">Trash is empty.</div>
              </TableCell></TableRow>
            ) : trash.data.map((t) => (
              <TableRow key={t.transaction_id} data-state={selected.has(t.transaction_id) ? 'selected' : undefined}>
                <TableCell className="pl-6">
                  <Checkbox
                    checked={selected.has(t.transaction_id)}
                    onCheckedChange={(v) => toggleRow(t.transaction_id, v === true)}
                    aria-label={`Select ${t.description}`}
                  />
                </TableCell>
                <TableCell className="whitespace-nowrap">{t.date}</TableCell>
                <TableCell className="max-w-[380px] whitespace-normal break-words">{t.description}</TableCell>
                <TableCell>{t.category}</TableCell>
                <TableCell>{t.account}</TableCell>
                <TableCell>{t.transaction_type}</TableCell>
                <TableCell className="text-right tabular-nums">{fmtMoney(t.amount)}</TableCell>
                <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                  {new Date(t.deleted_at).toLocaleDateString()}
                  {!t.can_permanently_delete && (
                    <Badge variant="secondary" className="ml-2">awaiting sync</Badge>
                  )}
                </TableCell>
                <TableCell className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => restore.mutate(t.transaction_id)}>
                    <RotateCcw className="size-4" /> Restore
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    disabled={!t.can_permanently_delete}
                    title={t.can_permanently_delete ? undefined : "Deletion hasn't synced to Google Sheets yet"}
                    onClick={() => {
                      if (confirm('Permanently delete this transaction? This cannot be undone.')) {
                        permanentDelete.mutate(t.transaction_id);
                      }
                    }}
                  >
                    Delete Permanently
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </>
  );
}
