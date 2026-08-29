import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { Upload } from 'lucide-react';
import { api } from '../lib/api';
import { fmtMoney } from '../lib/format';
import type { ImportPreviewResult, ImportRowPreview } from '../lib/types';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

interface RowState {
  row: ImportRowPreview;
  selected: boolean;
  category: string;
}

export function Import() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [account, setAccount] = useState('Primary');
  const [rowStates, setRowStates] = useState<RowState[] | null>(null);
  const [meta, setMeta] = useState<Pick<ImportPreviewResult, 'skipped_rows'> | null>(null);
  const [result, setResult] = useState<{ created_count: number } | null>(null);

  const categories = useQuery({ queryKey: ['categories'], queryFn: api.listCategories });
  const accounts = useQuery({ queryKey: ['accounts'], queryFn: api.listAccounts });

  const preview = useMutation({
    mutationFn: (file: File) => api.importPreview(file),
    onSuccess: (data) => {
      setResult(null);
      setMeta({ skipped_rows: data.skipped_rows });
      setRowStates(data.rows.map((row) => ({
        row,
        selected: !row.is_duplicate,
        category: row.category_guess,
      })));
    },
  });

  const commit = useMutation({
    mutationFn: (rows: RowState[]) => api.importCommit(rows.map((rs) => ({
      date: rs.row.date, description: rs.row.description, amount: rs.row.amount,
      transaction_type: rs.row.transaction_type, category: rs.category, account,
    }))),
    onSuccess: (data) => {
      setResult({ created_count: data.created_count });
      setRowStates(null);
      setFileName(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      queryClient.invalidateQueries({ queryKey: ['categories'] });
    },
  });

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    preview.mutate(file);
  }

  function toggleRow(rowKey: string, selected: boolean) {
    setRowStates((prev) => prev && prev.map((rs) => (rs.row.row_key === rowKey ? { ...rs, selected } : rs)));
  }

  function setRowCategory(rowKey: string, category: string) {
    setRowStates((prev) => prev && prev.map((rs) => (rs.row.row_key === rowKey ? { ...rs, category } : rs)));
  }

  const selectedRows = rowStates?.filter((rs) => rs.selected) ?? [];
  const duplicateCount = rowStates?.filter((rs) => rs.row.is_duplicate).length ?? 0;

  return (
    <>
      <h1 className="text-2xl font-bold tracking-tight">Import Transactions</h1>
      <p className="mb-5 mt-1 text-sm text-muted-foreground">
        Upload a bank statement CSV. Nothing is saved until you review the preview below and confirm.
      </p>

      <Card className="mb-5">
        <CardHeader>
          <CardTitle className="text-sm font-semibold">1. Choose a file</CardTitle>
          <CardDescription>Works with split Debit/Credit columns or a single signed Amount column - most Indian bank exports included.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3">
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            onChange={onFileChange}
            className="text-sm file:mr-3 file:rounded-md file:border file:border-input file:bg-transparent file:px-3 file:py-1.5 file:text-sm file:font-medium file:hover:bg-accent"
          />
          {preview.isPending && <span className="text-sm text-muted-foreground">Parsing…</span>}
          {preview.isError && <span className="text-sm text-destructive">{(preview.error as Error).message}</span>}
          {result && (
            <Badge variant="outline" className="text-emerald-600 dark:text-emerald-400">
              Imported {result.created_count} transaction{result.created_count === 1 ? '' : 's'} from {fileName ?? 'file'}
            </Badge>
          )}
        </CardContent>
      </Card>

      {rowStates && rowStates.length > 0 && (
        <Card>
          <CardHeader className="flex-row items-center justify-between gap-3 space-y-0">
            <div>
              <CardTitle className="text-sm font-semibold">2. Review before importing</CardTitle>
              <CardDescription>
                {rowStates.length} row{rowStates.length === 1 ? '' : 's'} parsed
                {meta && meta.skipped_rows > 0 ? `, ${meta.skipped_rows} skipped (no valid date/amount)` : ''}
                {duplicateCount > 0 ? ` — ${duplicateCount} look like duplicates of existing transactions and are unchecked by default` : ''}.
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Import into account</span>
              <Select value={account} onValueChange={setAccount}>
                <SelectTrigger size="sm" className="w-[140px]"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {accounts.data?.map((a) => <SelectItem key={a.id} value={a.name}>{a.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </CardHeader>
          <CardContent className="px-0">
            <div className="max-h-[520px] overflow-y-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8 pl-6"></TableHead>
                    <TableHead>Date</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead className="text-right">Amount</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Category</TableHead>
                    <TableHead className="pr-6"></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rowStates.map((rs) => (
                    <TableRow key={rs.row.row_key} className={!rs.selected ? 'opacity-50' : undefined}>
                      <TableCell className="pl-6">
                        <Checkbox checked={rs.selected} onCheckedChange={(v) => toggleRow(rs.row.row_key, v === true)} />
                      </TableCell>
                      <TableCell className="whitespace-nowrap">{rs.row.date}</TableCell>
                      <TableCell className="max-w-[360px] truncate" title={rs.row.description}>{rs.row.description}</TableCell>
                      <TableCell className="text-right tabular-nums">{fmtMoney(rs.row.amount)}</TableCell>
                      <TableCell>
                        <Badge variant={rs.row.transaction_type === 'Income' ? 'secondary' : 'outline'}>{rs.row.transaction_type}</Badge>
                      </TableCell>
                      <TableCell>
                        <Select value={rs.category} onValueChange={(v) => setRowCategory(rs.row.row_key, v)}>
                          <SelectTrigger size="sm" className="w-[150px]"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {categories.data?.map((c) => <SelectItem key={c.id} value={c.name}>{c.name}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </TableCell>
                      <TableCell className="pr-6">
                        {rs.row.is_duplicate && (
                          <Badge variant="destructive" title={`Matches existing transaction ${rs.row.duplicate_of}`}>
                            Possible duplicate
                          </Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
          <div className="flex items-center gap-3 border-t px-6 pt-6">
            <Button
              disabled={selectedRows.length === 0 || commit.isPending}
              onClick={() => commit.mutate(selectedRows)}
            >
              <Upload className="size-4" />
              {commit.isPending ? 'Importing…' : `Import ${selectedRows.length} selected transaction${selectedRows.length === 1 ? '' : 's'}`}
            </Button>
            {commit.isError && <span className="text-sm text-destructive">{(commit.error as Error).message}</span>}
          </div>
        </Card>
      )}
    </>
  );
}
