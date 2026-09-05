import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useRef, useState } from 'react';
import { Plus, Trash2, X } from 'lucide-react';
import { api } from '../lib/api';
import { fmtMoney } from '../lib/format';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { MultiSelectFilter } from '@/components/MultiSelectFilter';

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
  'August', 'September', 'October', 'November', 'December'];

const SYNC_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  synced: 'default', pending: 'secondary', conflict: 'destructive', error: 'destructive',
};

const ANY = '__any__';

let nextRowId = 1;
interface NewRow {
  id: number;
  date: string;
  description: string;
  amount: string;
  transaction_type: string;
  category: string;
  account: string;
  suggestion?: string;
  categoryTouched?: boolean;
}
function emptyRow(): NewRow {
  return {
    id: nextRowId++, date: new Date().toISOString().slice(0, 10), description: '', amount: '',
    transaction_type: 'Expense', category: '', account: 'Primary',
  };
}

export function Transactions() {
  const queryClient = useQueryClient();
  const [year, setYear] = useState('');
  const [month, setMonth] = useState('');
  const [category, setCategory] = useState<string[]>([]);
  const [categoryExclude, setCategoryExclude] = useState(false);
  const [account, setAccount] = useState<string[]>([]);
  const [accountExclude, setAccountExclude] = useState(false);
  const [type, setType] = useState('');
  const [search, setSearch] = useState('');
  const [appliedFilters, setAppliedFilters] = useState({});
  const [showAddForm, setShowAddForm] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [newRows, setNewRows] = useState<NewRow[]>([emptyRow()]);

  const categories = useQuery({ queryKey: ['categories'], queryFn: api.listCategories });
  const accounts = useQuery({ queryKey: ['accounts'], queryFn: api.listAccounts });
  const transactions = useQuery({
    queryKey: ['transactions', appliedFilters],
    queryFn: () => api.listTransactions(appliedFilters),
  });

  const deleteTxn = useMutation({
    mutationFn: (id: string) => api.deleteTransaction(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['transactions'] }),
  });

  const bulkDelete = useMutation({
    mutationFn: (ids: string[]) => api.bulkDeleteTransactions(ids),
    onSuccess: () => {
      setSelected(new Set());
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
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
    setSelected(checked ? new Set(transactions.data?.map((t) => t.transaction_id)) : new Set());
  }

  const allVisibleSelected = !!transactions.data?.length && transactions.data.every((t) => selected.has(t.transaction_id));

  const filteredTotals = useMemo(() => {
    const rows = transactions.data ?? [];
    let income = 0;
    let expenses = 0;
    for (const t of rows) {
      if (t.transaction_type === 'Income') income += t.amount;
      else expenses += t.amount;
    }
    return { count: rows.length, income, expenses, net: income - expenses };
  }, [transactions.data]);

  const validRows = newRows.filter((r) => r.description.trim() && r.category && parseFloat(r.amount) > 0);

  function updateRow(id: number, patch: Partial<NewRow>) {
    setNewRows((rows) => rows.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }
  function addRow() {
    setNewRows((rows) => [...rows, emptyRow()]);
  }
  function removeRow(id: number) {
    setNewRows((rows) => (rows.length > 1 ? rows.filter((r) => r.id !== id) : rows));
  }

  const suggestTimers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  function onDescriptionChange(rowId: number, value: string) {
    updateRow(rowId, { description: value, suggestion: undefined });
    const existing = suggestTimers.current.get(rowId);
    if (existing) clearTimeout(existing);
    if (value.trim().length < 2) return;
    suggestTimers.current.set(rowId, setTimeout(async () => {
      try {
        const [{ suggestion }, { category: suggestedCategory }] = await Promise.all([
          api.autocomplete(value),
          api.categorize(value),
        ]);
        if (suggestion) updateRow(rowId, { suggestion });
        // Never override a category the user picked themselves.
        setNewRows((rows) => rows.map((r) => (
          r.id === rowId && !r.categoryTouched && !r.category && suggestedCategory
            ? { ...r, category: suggestedCategory }
            : r
        )));
      } catch {
        // Local AI features are optional - fail silently if unavailable.
      }
    }, 400));
  }

  function acceptSuggestion(rowId: number, suggestion: string) {
    updateRow(rowId, { description: suggestion, suggestion: undefined });
  }

  const bulkCreateTxn = useMutation({
    mutationFn: () => api.bulkCreateTransactions(validRows.map((r) => ({
      date: r.date, description: r.description, amount: parseFloat(r.amount),
      transaction_type: r.transaction_type, category: r.category, account: r.account || 'Primary',
    }))),
    onSuccess: () => {
      setShowAddForm(false);
      setNewRows([emptyRow()]);
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
    },
  });

  function applyFilters() {
    setAppliedFilters({
      year: year || undefined, month: month || undefined,
      category: category.length ? category : undefined, category_exclude: categoryExclude,
      account: account.length ? account : undefined, account_exclude: accountExclude,
      type: type || undefined, search: search || undefined,
    });
    setSelected(new Set());
  }

  return (
    <>
      <h1 className="text-2xl font-bold tracking-tight">Transactions</h1>
      <p className="mb-5 mt-1 text-sm text-muted-foreground">Every transaction across every month and year, in one place.</p>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Input type="number" placeholder="Year" value={year} onChange={(e) => setYear(e.target.value)} className="w-24" />
        <Select value={month || ANY} onValueChange={(v) => setMonth(v === ANY ? '' : v)}>
          <SelectTrigger size="sm" className="w-[130px]"><SelectValue placeholder="Any month" /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Any month</SelectItem>
            {MONTHS.map((m, i) => <SelectItem key={m} value={String(i + 1)}>{m}</SelectItem>)}
          </SelectContent>
        </Select>
        <MultiSelectFilter
          label="Category"
          options={categories.data?.map((c) => ({ value: c.name, label: c.name })) ?? []}
          selected={category}
          onSelectedChange={setCategory}
          exclude={categoryExclude}
          onExcludeChange={setCategoryExclude}
        />
        <MultiSelectFilter
          label="Account"
          options={accounts.data?.map((a) => ({ value: a.name, label: a.name })) ?? []}
          selected={account}
          onSelectedChange={setAccount}
          exclude={accountExclude}
          onExcludeChange={setAccountExclude}
        />
        <Select value={type || ANY} onValueChange={(v) => setType(v === ANY ? '' : v)}>
          <SelectTrigger size="sm" className="w-[130px]"><SelectValue placeholder="Any type" /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Any type</SelectItem>
            <SelectItem value="Income">Income</SelectItem>
            <SelectItem value="Expense">Expense</SelectItem>
          </SelectContent>
        </Select>
        <Input type="text" placeholder="Search description…" value={search} onChange={(e) => setSearch(e.target.value)} className="w-56" />
        <Button variant="outline" size="sm" onClick={applyFilters}>Filter</Button>
        <Button size="sm" onClick={() => setShowAddForm(!showAddForm)}>
          <Plus className="size-4" /> Add Transactions
        </Button>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-1 text-sm text-muted-foreground">
        <span>{filteredTotals.count} transaction{filteredTotals.count === 1 ? '' : 's'}</span>
        <span>Income <span className="font-semibold text-emerald-600 dark:text-emerald-400">{fmtMoney(filteredTotals.income)}</span></span>
        <span>Expenses <span className="font-semibold text-destructive">{fmtMoney(filteredTotals.expenses)}</span></span>
        <span>Net <span className={`font-semibold ${filteredTotals.net >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive'}`}>{fmtMoney(filteredTotals.net)}</span></span>
      </div>

      {selected.size > 0 && (
        <div className="mb-4 flex items-center gap-2.5 rounded-lg border border-destructive/40 bg-destructive/5 px-3.5 py-2.5">
          <span className="text-sm font-medium">{selected.size} selected</span>
          <Button
            variant="destructive"
            size="sm"
            disabled={bulkDelete.isPending}
            onClick={() => {
              if (confirm(`Delete ${selected.size} selected transaction${selected.size === 1 ? '' : 's'}? This cannot be undone from the UI.`)) {
                bulkDelete.mutate(Array.from(selected));
              }
            }}
          >
            <Trash2 className="size-4" />
            {bulkDelete.isPending ? 'Deleting…' : 'Delete Selected'}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())}>Clear selection</Button>
        </div>
      )}

      {showAddForm && (
        <Card className="mb-4 py-0">
          <div className="max-h-[420px] overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-6">Date</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead>Amount</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>Account</TableHead>
                  <TableHead className="pr-6"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {newRows.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell className="pl-6">
                      <Input type="date" value={row.date} onChange={(e) => updateRow(row.id, { date: e.target.value })} className="w-40" />
                    </TableCell>
                    <TableCell>
                      <Input type="text" placeholder="Description" value={row.description}
                        onChange={(e) => onDescriptionChange(row.id, e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Tab' && row.suggestion) {
                            e.preventDefault();
                            acceptSuggestion(row.id, row.suggestion);
                          }
                        }}
                        className="min-w-[160px]" />
                      {row.suggestion && (
                        <button
                          type="button"
                          className="mt-1 block text-xs text-muted-foreground hover:text-foreground"
                          onClick={() => acceptSuggestion(row.id, row.suggestion!)}
                        >
                          → {row.suggestion} <span className="opacity-60">(Tab)</span>
                        </button>
                      )}
                    </TableCell>
                    <TableCell>
                      <Input type="number" placeholder="Amount" step="0.01" value={row.amount}
                        onChange={(e) => updateRow(row.id, { amount: e.target.value })} className="w-28" />
                    </TableCell>
                    <TableCell>
                      <Select value={row.transaction_type} onValueChange={(v) => updateRow(row.id, { transaction_type: v })}>
                        <SelectTrigger size="sm" className="w-[110px]"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="Expense">Expense</SelectItem>
                          <SelectItem value="Income">Income</SelectItem>
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell>
                      <Select value={row.category || ANY} onValueChange={(v) => updateRow(row.id, { category: v === ANY ? '' : v, categoryTouched: true })}>
                        <SelectTrigger size="sm" className="w-[150px]"><SelectValue placeholder="Category…" /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value={ANY}>Category…</SelectItem>
                          {categories.data?.map((c) => <SelectItem key={c.id} value={c.name}>{c.name}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell>
                      <Input type="text" placeholder="Account" value={row.account}
                        onChange={(e) => updateRow(row.id, { account: e.target.value })} className="w-28" />
                    </TableCell>
                    <TableCell className="pr-6">
                      <Button variant="ghost" size="sm" disabled={newRows.length === 1} onClick={() => removeRow(row.id)}>
                        <X className="size-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="flex flex-wrap items-center gap-2 border-t px-6 py-3">
            <Button variant="outline" size="sm" onClick={addRow}>
              <Plus className="size-4" /> Add row
            </Button>
            <Button size="sm" disabled={validRows.length === 0 || bulkCreateTxn.isPending} onClick={() => bulkCreateTxn.mutate()}>
              {bulkCreateTxn.isPending
                ? 'Saving…'
                : `Save ${validRows.length} Transaction${validRows.length === 1 ? '' : 's'}`}
            </Button>
            <Button size="sm" variant="outline" onClick={() => { setShowAddForm(false); setNewRows([emptyRow()]); }}>Cancel</Button>
            {bulkCreateTxn.isError && <span className="text-sm text-destructive">{(bulkCreateTxn.error as Error).message}</span>}
          </div>
        </Card>
      )}

      <Card className="py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8 pl-6">
                <Checkbox
                  checked={allVisibleSelected}
                  onCheckedChange={(v) => toggleAll(v === true)}
                  aria-label="Select all visible transactions"
                />
              </TableHead>
              <TableHead>Date</TableHead><TableHead>Description</TableHead><TableHead>Category</TableHead>
              <TableHead>Account</TableHead><TableHead>Type</TableHead>
              <TableHead className="text-right">Amount</TableHead><TableHead>Sync</TableHead><TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!transactions.data?.length ? (
              <TableRow><TableCell colSpan={9}>
                <div className="py-8 text-center text-sm text-muted-foreground">No transactions match these filters.</div>
              </TableCell></TableRow>
            ) : transactions.data.map((t) => (
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
                <TableCell><Badge variant={SYNC_VARIANT[t.sync_status] ?? 'secondary'}>{t.sync_status}</Badge></TableCell>
                <TableCell>
                  <Button variant="destructive" size="sm" onClick={() => {
                    if (confirm('Delete this transaction?')) deleteTxn.mutate(t.transaction_id);
                  }}>Delete</Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </>
  );
}
