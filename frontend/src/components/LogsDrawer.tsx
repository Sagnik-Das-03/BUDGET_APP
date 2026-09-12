import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { ChevronLeft, ChevronRight, ScrollText } from 'lucide-react';
import { api } from '../lib/api';
import { useLocalStorage } from '../lib/useLocalStorage';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription, SheetTrigger } from '@/components/ui/sheet';

const LEVEL_VARIANT: Record<string, 'secondary' | 'destructive' | 'outline'> = {
  info: 'secondary', warn: 'outline', error: 'destructive',
};

const PAGE_SIZE_OPTIONS = [25, 50, 100];

// LogsTable only mounts while the drawer is open (Radix's Dialog.Content -
// which Sheet is built on - isn't rendered in the DOM at all when closed),
// so the 15s polling interval starts/stops with it automatically rather
// than running in the background when nobody's looking at it.
export function LogsDrawer({ trigger }: { trigger: React.ReactNode }) {
  return (
    <Sheet>
      <SheetTrigger asChild>{trigger}</SheetTrigger>
      <SheetContent side="right" className="flex w-full flex-col sm:max-w-xl">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <ScrollText className="size-4" /> Sync Logs
          </SheetTitle>
          <SheetDescription>Recent sync activity, most recent first.</SheetDescription>
        </SheetHeader>
        <LogsTable />
      </SheetContent>
    </Sheet>
  );
}

function LogsTable() {
  const logs = useQuery({ queryKey: ['syncLogs'], queryFn: () => api.syncLogs(), refetchInterval: 15000 });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useLocalStorage('budget_tracker.logsPageSize', 50);

  const totalPages = Math.max(1, Math.ceil((logs.data?.length ?? 0) / pageSize));
  const currentPage = Math.min(page, totalPages);
  const pagedRows = (logs.data ?? []).slice((currentPage - 1) * pageSize, currentPage * pageSize);

  return (
    <>
      <div className="min-h-0 flex-1 overflow-y-auto px-4">
        <Table>
          <TableHeader>
            <TableRow><TableHead>Time</TableHead><TableHead>Level</TableHead><TableHead>Message</TableHead></TableRow>
          </TableHeader>
          <TableBody>
            {!pagedRows.length ? (
              <TableRow><TableCell colSpan={3}>
                <div className="py-8 text-center text-sm text-muted-foreground">No sync activity yet.</div>
              </TableCell></TableRow>
            ) : pagedRows.map((r, i) => (
              <TableRow key={i}>
                <TableCell className="whitespace-nowrap">{new Date(r.timestamp).toLocaleString()}</TableCell>
                <TableCell><Badge variant={LEVEL_VARIANT[r.level] ?? 'secondary'}>{r.level}</Badge></TableCell>
                <TableCell className="break-words">{r.message}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {!!logs.data?.length && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-t px-4 py-3 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <span>
              {(currentPage - 1) * pageSize + 1}–{Math.min(currentPage * pageSize, logs.data.length)} of {logs.data.length}
            </span>
            <Select value={String(pageSize)} onValueChange={(v) => { setPageSize(Number(v)); setPage(1); }}>
              <SelectTrigger size="sm" className="w-[100px] text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                {PAGE_SIZE_OPTIONS.map((n) => <SelectItem key={n} value={String(n)}>{n} / page</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-1.5">
            <Button variant="outline" size="sm" className="h-7 px-2" disabled={currentPage <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
              <ChevronLeft className="size-3.5" />
            </Button>
            <span>Page {currentPage} of {totalPages}</span>
            <Button variant="outline" size="sm" className="h-7 px-2" disabled={currentPage >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>
              <ChevronRight className="size-3.5" />
            </Button>
          </div>
        </div>
      )}
    </>
  );
}
