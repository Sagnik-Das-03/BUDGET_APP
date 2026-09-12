import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, Lock, Pencil, Plus, Sparkles, Trash2, Unlock, X } from 'lucide-react';
import { api } from '../lib/api';
import { fmtMoney } from '../lib/format';
import { useLocalStorage } from '../lib/useLocalStorage';
import { useConfirmDialog } from '../lib/useConfirmDialog';
import type { Transaction, ViewFilters } from '../lib/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { MultiSelectFilter } from '@/components/MultiSelectFilter';
import { SaveViewPopover } from '@/components/SaveViewPopover';
import { ModelBadge } from '@/components/ModelBadge';

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
  'August', 'September', 'October', 'November', 'December'];

const SYNC_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  synced: 'default', pending: 'secondary', conflict: 'destructive', error: 'destructive',
};

const ANY = '__any__';
const PAGE_SIZE_OPTIONS = [25, 50, 100];

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
  suggestionDurationSec?: number;
  categoryTouched?: boolean;
}
function emptyRow(): NewRow {
  return {
    id: nextRowId++, date: new Date().toISOString().slice(0, 10), description: '', amount: '',
    transaction_type: 'Expense', category: '', account: 'Primary',
  };
}

interface EditDraft {
  date: string;
  description: string;
  amount: string;
  transaction_type: string;
  category: string;
  account: string;
}
function draftFromTransaction(t: Transaction): EditDraft {
  return {
    date: t.date, description: t.description, amount: String(t.amount),
    transaction_type: t.transaction_type, category: t.category, account: t.account,
  };
}

interface SavedView {
  id: string;
  name: string;
  filters: ViewFilters;
}

function buildQueryParams(f: ViewFilters) {
  return {
    year: f.year || undefined, month: f.month || undefined,
    category: f.category.length ? f.category : undefined, category_exclude: f.categoryExclude,
    account: f.account.length ? f.account : undefined, account_exclude: f.accountExclude,
    type: f.type || undefined, search: f.search || undefined,
  };
}

function computeTotals(rows: Transaction[]) {
  let income = 0;
  let expenses = 0;
  for (const t of rows) {
    if (t.transaction_type === 'Income') income += t.amount;
    else expenses += t.amount;
  }
  return { count: rows.length, income, expenses, net: income - expenses };
}

export function Transactions() {
  const queryClient = useQueryClient();
  const { confirm, dialog: confirmDialog } = useConfirmDialog();
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
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useLocalStorage('budget_tracker.transactionsPageSize', 50);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<EditDraft | null>(null);
  const [quickAddText, setQuickAddText] = useState('');
  const [savedViews, setSavedViews] = useLocalStorage<SavedView[]>('budget_tracker.savedViews', []);
  const [compareIds, setCompareIds] = useState<Set<string>>(new Set());
  // Per-device, not a server setting - a lightweight "don't let me fat-finger
  // an edit" guard, not an access-control mechanism (the API itself is
  // unaffected either way).
  const [editsLocked, setEditsLocked] = useLocalStorage('budget_tracker.transactionsEditsLocked', false);

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

  const updateTxn = useMutation({
    mutationFn: ({ id, draft }: { id: string; draft: EditDraft }) => api.updateTransaction(id, {
      date: draft.date, description: draft.description, amount: parseFloat(draft.amount),
      transaction_type: draft.transaction_type, category: draft.category, account: draft.account || 'Primary',
    }),
    onSuccess: () => {
      setEditingId(null);
      setEditDraft(null);
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
    },
  });

  function startEdit(t: Transaction) {
    setEditingId(t.transaction_id);
    setEditDraft(draftFromTransaction(t));
  }
  function cancelEdit() {
    setEditingId(null);
    setEditDraft(null);
  }
  function saveEdit() {
    if (!editingId || !editDraft) return;
    updateTxn.mutate({ id: editingId, draft: editDraft });
  }
  const editValid = !!editDraft && editDraft.description.trim() && editDraft.category && parseFloat(editDraft.amount) > 0;

  function toggleRow(id: string, checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id); else next.delete(id);
      return next;
    });
  }

  // "Select all" only touches the current page - selections on other pages
  // (from paging through and checking a few there too) are left alone.
  function toggleAll(checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      for (const t of pagedRows) {
        if (checked) next.add(t.transaction_id); else next.delete(t.transaction_id);
      }
      return next;
    });
  }

  const filteredTotals = useMemo(() => computeTotals(transactions.data ?? []), [transactions.data]);

  const totalPages = Math.max(1, Math.ceil((transactions.data?.length ?? 0) / pageSize));
  const currentPage = Math.min(page, totalPages);
  const pagedRows = (transactions.data ?? []).slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const allVisibleSelected = !!pagedRows.length && pagedRows.every((t) => selected.has(t.transaction_id));

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
    updateRow(rowId, { description: value, suggestion: undefined, suggestionDurationSec: undefined });
    const existing = suggestTimers.current.get(rowId);
    if (existing) clearTimeout(existing);
    if (value.trim().length < 2) return;
    suggestTimers.current.set(rowId, setTimeout(async () => {
      try {
        const rowDate = newRows.find((r) => r.id === rowId)?.date;
        const autocompleteStart = Date.now();
        const [{ suggestion }, { category: suggestedCategory }] = await Promise.all([
          api.autocomplete(value, rowDate),
          api.categorize(value),
        ]);
        const suggestionDurationSec = (Date.now() - autocompleteStart) / 1000;
        if (suggestion) updateRow(rowId, { suggestion, suggestionDurationSec });
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

  function currentFiltersSnapshot(): ViewFilters {
    return { year, month, category, categoryExclude, account, accountExclude, type, search };
  }

  function applyFilters() {
    setAppliedFilters(buildQueryParams(currentFiltersSnapshot()));
    setSelected(new Set());
    setPage(1);
  }

  function clearFilters() {
    setYear(''); setMonth('');
    setCategory([]); setCategoryExclude(false);
    setAccount([]); setAccountExclude(false);
    setType(''); setSearch('');
    setAppliedFilters({});
    setSelected(new Set());
    setPage(1);
  }

  const hasActiveFilters = !!(year || month || category.length || account.length || type || search);

  function saveCurrentView(name: string) {
    setSavedViews([...savedViews, { id: crypto.randomUUID(), name, filters: currentFiltersSnapshot() }]);
  }

  function applyView(view: SavedView) {
    setYear(view.filters.year); setMonth(view.filters.month);
    setCategory(view.filters.category); setCategoryExclude(view.filters.categoryExclude);
    setAccount(view.filters.account); setAccountExclude(view.filters.accountExclude);
    setType(view.filters.type); setSearch(view.filters.search);
    setAppliedFilters(buildQueryParams(view.filters));
    setSelected(new Set());
    setPage(1);
  }

  function deleteView(id: string) {
    setSavedViews(savedViews.filter((v) => v.id !== id));
    setCompareIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  }

  function toggleCompare(id: string, checked: boolean) {
    setCompareIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id); else next.delete(id);
      return next;
    });
  }

  const compareViews = savedViews.filter((v) => compareIds.has(v.id));
  const compareQueries = useQueries({
    queries: compareViews.map((v) => ({
      queryKey: ['savedViewTransactions', v.id, v.filters],
      queryFn: () => api.listTransactions(buildQueryParams(v.filters)),
      enabled: compareViews.length >= 2,
    })),
  });

  const quickAddStartRef = useRef(0);
  const [quickAddDuration, setQuickAddDuration] = useState<number | null>(null);
  const quickAdd = useMutation({
    mutationFn: (text: string) => api.quickAdd(text),
    onSuccess: (parsed) => {
      setQuickAddDuration((Date.now() - quickAddStartRef.current) / 1000);
      setQuickAddText('');
      setShowAddForm(true);
      const filled: NewRow = {
        id: nextRowId++, date: parsed.date, description: parsed.description, amount: String(parsed.amount),
        transaction_type: parsed.transaction_type, category: parsed.category, account: parsed.account,
        categoryTouched: true,
      };
      setNewRows((rows) => {
        const emptyIdx = rows.findIndex((r) => !r.description.trim() && !parseFloat(r.amount));
        if (emptyIdx >= 0) {
          const copy = [...rows];
          copy[emptyIdx] = filled;
          return copy;
        }
        return [...rows, filled];
      });
    },
  });

  function runQuickAdd() {
    const text = quickAddText.trim();
    if (!text || quickAdd.isPending) return;
    quickAddStartRef.current = Date.now();
    setQuickAddDuration(null);
    quickAdd.mutate(text);
  }

  return (
    <>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold tracking-tight">Transactions</h1>
        <label className="flex items-center gap-2 text-sm">
          {editsLocked ? <Lock className="size-4 text-muted-foreground" /> : <Unlock className="size-4 text-muted-foreground" />}
          <Label className="text-sm text-muted-foreground">{editsLocked ? 'Edits locked' : 'Edits enabled'}</Label>
          <Switch checked={!editsLocked} onCheckedChange={(v) => setEditsLocked(!v)} aria-label="Enable editing transactions" />
        </label>
      </div>
      <p className="mb-5 mt-1 text-sm text-muted-foreground">Every transaction across every month and year, in one place.</p>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Sparkles className="size-4 shrink-0 text-primary" />
        <Input
          placeholder='Quick add: "Zomato 250 today"'
          value={quickAddText}
          onChange={(e) => setQuickAddText(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') runQuickAdd(); }}
          className="max-w-xs"
          disabled={editsLocked}
        />
        <Button variant="outline" size="sm" disabled={editsLocked || quickAdd.isPending || !quickAddText.trim()} onClick={runQuickAdd}>
          {quickAdd.isPending ? 'Parsing…' : 'Add'}
        </Button>
        <ModelBadge task="quick_add" />
        {quickAdd.isError && <span className="text-sm text-destructive">{(quickAdd.error as Error).message}</span>}
        {!quickAdd.isPending && quickAddDuration !== null && (
          <span className="text-xs text-muted-foreground">Parsed in {quickAddDuration.toFixed(1)}s</span>
        )}
      </div>

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
          onApply={applyFilters}
        />
        <MultiSelectFilter
          label="Account"
          options={accounts.data?.map((a) => ({ value: a.name, label: a.name })) ?? []}
          selected={account}
          onSelectedChange={setAccount}
          exclude={accountExclude}
          onExcludeChange={setAccountExclude}
          onApply={applyFilters}
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
        {hasActiveFilters && (
          <Button variant="ghost" size="sm" onClick={clearFilters}>
            <X className="size-4" /> Clear
          </Button>
        )}
        {hasActiveFilters && <SaveViewPopover filters={currentFiltersSnapshot()} onSave={saveCurrentView} />}
        <Button size="sm" disabled={editsLocked} onClick={() => setShowAddForm(!showAddForm)}>
          <Plus className="size-4" /> Add Transactions
        </Button>
      </div>

      {savedViews.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">Saved views (check 2+ to compare):</span>
          {savedViews.map((v) => (
            <div key={v.id} className="flex items-center gap-1.5 rounded-full border py-1 pl-2 pr-1 text-xs">
              <Checkbox
                checked={compareIds.has(v.id)}
                onCheckedChange={(c) => toggleCompare(v.id, c === true)}
                aria-label={`Include ${v.name} in comparison`}
                className="size-3.5"
              />
              <button type="button" className="hover:underline" onClick={() => applyView(v)}>{v.name}</button>
              <button type="button" aria-label={`Delete ${v.name}`} className="text-muted-foreground hover:text-destructive" onClick={() => deleteView(v.id)}>
                <X className="size-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {compareViews.length >= 2 && (
        <Card className="mb-4 py-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Metric</TableHead>
                {compareViews.map((v) => <TableHead key={v.id} className="text-right">{v.name}</TableHead>)}
              </TableRow>
            </TableHeader>
            <TableBody>
              {(['count', 'income', 'expenses', 'net'] as const).map((metric) => (
                <TableRow key={metric}>
                  <TableCell className="capitalize">{metric}</TableCell>
                  {compareViews.map((v, i) => {
                    const totals = computeTotals(compareQueries[i]?.data ?? []);
                    return (
                      <TableCell key={v.id} className="text-right tabular-nums">
                        {compareQueries[i]?.isLoading ? '…' : metric === 'count' ? totals.count : fmtMoney(totals[metric])}
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

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
            disabled={editsLocked || bulkDelete.isPending}
            onClick={async () => {
              if (await confirm(`Delete ${selected.size} selected transaction${selected.size === 1 ? '' : 's'}? This cannot be undone from the UI.`)) {
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
                          {row.suggestionDurationSec !== undefined && (
                            <span className="opacity-60"> · {row.suggestionDurationSec.toFixed(1)}s</span>
                          )}
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
            <span className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground">
              Autocomplete <ModelBadge task="autocomplete" />
            </span>
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
            {!pagedRows.length ? (
              <TableRow><TableCell colSpan={9}>
                <div className="py-8 text-center text-sm text-muted-foreground">No transactions match these filters.</div>
              </TableCell></TableRow>
            ) : pagedRows.map((t) => (
              editingId === t.transaction_id && editDraft ? (
                <TableRow key={t.transaction_id} data-state="selected">
                  <TableCell className="pl-6" />
                  <TableCell>
                    <Input type="date" value={editDraft.date}
                      onChange={(e) => setEditDraft({ ...editDraft, date: e.target.value })} className="w-40" />
                  </TableCell>
                  <TableCell>
                    <Input type="text" value={editDraft.description}
                      onChange={(e) => setEditDraft({ ...editDraft, description: e.target.value })}
                      className="min-w-[160px]" />
                  </TableCell>
                  <TableCell>
                    <Select value={editDraft.category || ANY} onValueChange={(v) => setEditDraft({ ...editDraft, category: v === ANY ? '' : v })}>
                      <SelectTrigger size="sm" className="w-[150px]"><SelectValue placeholder="Category…" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value={ANY}>Category…</SelectItem>
                        {categories.data?.map((c) => <SelectItem key={c.id} value={c.name}>{c.name}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell>
                    <Input type="text" value={editDraft.account}
                      onChange={(e) => setEditDraft({ ...editDraft, account: e.target.value })} className="w-28" />
                  </TableCell>
                  <TableCell>
                    <Select value={editDraft.transaction_type} onValueChange={(v) => setEditDraft({ ...editDraft, transaction_type: v })}>
                      <SelectTrigger size="sm" className="w-[110px]"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Expense">Expense</SelectItem>
                        <SelectItem value="Income">Income</SelectItem>
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell>
                    <Input type="number" step="0.01" value={editDraft.amount}
                      onChange={(e) => setEditDraft({ ...editDraft, amount: e.target.value })} className="w-28 text-right" />
                  </TableCell>
                  <TableCell><Badge variant={SYNC_VARIANT[t.sync_status] ?? 'secondary'}>{t.sync_status}</Badge></TableCell>
                  <TableCell className="whitespace-nowrap">
                    <Button size="sm" disabled={!editValid || updateTxn.isPending} onClick={saveEdit}>
                      {updateTxn.isPending ? 'Saving…' : 'Save'}
                    </Button>
                    <Button variant="outline" size="sm" className="ml-1.5" onClick={cancelEdit}>Cancel</Button>
                    {updateTxn.isError && <div className="mt-1 text-xs text-destructive">{(updateTxn.error as Error).message}</div>}
                  </TableCell>
                </TableRow>
              ) : (
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
                  <TableCell className="whitespace-nowrap">
                    <Button variant="outline" size="sm" disabled={editsLocked} onClick={() => startEdit(t)}>
                      <Pencil className="size-4" />
                    </Button>
                    <Button variant="destructive" size="sm" className="ml-1.5" disabled={editsLocked} onClick={async () => {
                      if (await confirm('Delete this transaction?')) deleteTxn.mutate(t.transaction_id);
                    }}>Delete</Button>
                  </TableCell>
                </TableRow>
              )
            ))}
          </TableBody>
        </Table>
      </Card>

      {!!transactions.data?.length && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
          <div className="flex items-center gap-2.5">
            <span>
              Showing {(currentPage - 1) * pageSize + 1}–{Math.min(currentPage * pageSize, transactions.data.length)} of {transactions.data.length}
            </span>
            <Select value={String(pageSize)} onValueChange={(v) => { setPageSize(Number(v)); setPage(1); }}>
              <SelectTrigger size="sm" className="w-[110px]"><SelectValue /></SelectTrigger>
              <SelectContent>
                {PAGE_SIZE_OPTIONS.map((n) => <SelectItem key={n} value={String(n)}>{n} / page</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" disabled={currentPage <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
              <ChevronLeft className="size-4" /> Previous
            </Button>
            <span>Page {currentPage} of {totalPages}</span>
            <Button variant="outline" size="sm" disabled={currentPage >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>
              Next <ChevronRight className="size-4" />
            </Button>
          </div>
        </div>
      )}

      {confirmDialog}
    </>
  );
}
