import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

const LEVEL_VARIANT: Record<string, 'secondary' | 'destructive' | 'outline'> = {
  info: 'secondary', warn: 'outline', error: 'destructive',
};

export function Logs() {
  const logs = useQuery({ queryKey: ['syncLogs'], queryFn: api.syncLogs, refetchInterval: 15000 });

  return (
    <>
      <h1 className="text-2xl font-bold tracking-tight">Sync Logs</h1>
      <p className="mb-5 mt-1 text-sm text-muted-foreground">Recent sync activity, most recent first.</p>
      <Card className="py-0">
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
                <TableCell>{new Date(r.timestamp).toLocaleString()}</TableCell>
                <TableCell><Badge variant={LEVEL_VARIANT[r.level] ?? 'secondary'}>{r.level}</Badge></TableCell>
                <TableCell>{r.message}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </>
  );
}
