import { useQuery } from '@tanstack/react-query';
import { ScrollText } from 'lucide-react';
import { api } from '../lib/api';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription, SheetTrigger } from '@/components/ui/sheet';

const LEVEL_VARIANT: Record<string, 'secondary' | 'destructive' | 'outline'> = {
  info: 'secondary', warn: 'outline', error: 'destructive',
};

// LogsTable only mounts while the drawer is open (Radix's Dialog.Content -
// which Sheet is built on - isn't rendered in the DOM at all when closed),
// so the 15s polling interval starts/stops with it automatically rather
// than running in the background when nobody's looking at it.
export function LogsDrawer({ trigger }: { trigger: React.ReactNode }) {
  return (
    <Sheet>
      <SheetTrigger asChild>{trigger}</SheetTrigger>
      <SheetContent side="right" className="w-full sm:max-w-xl">
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
  const logs = useQuery({ queryKey: ['syncLogs'], queryFn: api.syncLogs, refetchInterval: 15000 });

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
      <Table>
        <TableHeader>
          <TableRow><TableHead>Time</TableHead><TableHead>Level</TableHead><TableHead>Message</TableHead></TableRow>
        </TableHeader>
        <TableBody>
          {!logs.data?.length ? (
            <TableRow><TableCell colSpan={3}>
              <div className="py-8 text-center text-sm text-muted-foreground">No sync activity yet.</div>
            </TableCell></TableRow>
          ) : logs.data.map((r, i) => (
            <TableRow key={i}>
              <TableCell className="whitespace-nowrap">{new Date(r.timestamp).toLocaleString()}</TableCell>
              <TableCell><Badge variant={LEVEL_VARIANT[r.level] ?? 'secondary'}>{r.level}</Badge></TableCell>
              <TableCell className="break-words">{r.message}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
