import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus } from 'lucide-react';
import { api } from '../lib/api';
import { fmtMoney } from '../lib/format';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
  'August', 'September', 'October', 'November', 'December'];

const SYNC_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  synced: 'default', pending: 'secondary', conflict: 'destructive', error: 'destructive',
};

const ANY = '__any__';

export function Transactions() {
  const queryClient = useQueryClient();
  const [year, setYear] = useState('');
  const [month, setMonth] = useState('');
  const [category, setCategory] = useState('');
  const [type, setType] = useState('');
  const [search, setSearch] = useState('');
  const [appliedFilters, setAppliedFilters] = useState({});
  const [showAddForm, setShowAddForm] = useState(false);
  const [newTxn, setNewTxn] = useState({
    date: new Date().toISOString().slice(0, 10), description: '', amount: '',
    transaction_type: 'Expense', category: '', account: 'Primary',
  });

  const categories = useQuery({ queryKey: ['categories'], queryFn: api.listCategories });
  const transactions = useQuery({
    queryKey: ['transactions', appliedFilters],
    queryFn: () => api.listTransactions(appliedFilters),
  });

  const deleteTxn = useMutation({
    mutationFn: (id: string) => api.deleteTransaction(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['transactions'] }),
  });

  const createTxn = useMutation({
    mutationFn: () => api.createTransaction({ ...newTxn, amount: parseFloat(newTxn.amount) }),
    onSuccess: () => {
      setShowAddForm(false);
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
    },
  });

  function applyFilters() {
    setAppliedFilters({
      year: year || undefined, month: month || undefined, category: category || undefined,
      type: type || undefined, search: search || undefined,
    });
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
        <Select value={category || ANY} onValueChange={(v) => setCategory(v === ANY ? '' : v)}>
          <SelectTrigger size="sm" className="w-[150px]"><SelectValue placeholder="Any category" /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Any category</SelectItem>
            {categories.data?.map((c) => <SelectItem key={c.id} value={c.name}>{c.name}</SelectItem>)}
          </SelectContent>
        </Select>
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
          <Plus className="size-4" /> Add Transaction
        </Button>
      </div>

      {showAddForm && (
        <Card className="mb-4">
          <CardContent className="flex flex-wrap items-center gap-2 pt-0">
            <Input type="date" value={newTxn.date} onChange={(e) => setNewTxn({ ...newTxn, date: e.target.value })} className="w-40" />
            <Input type="text" placeholder="Description" value={newTxn.description}
              onChange={(e) => setNewTxn({ ...newTxn, description: e.target.value })} className="w-48" />
            <Input type="number" placeholder="Amount" step="0.01" value={newTxn.amount}
              onChange={(e) => setNewTxn({ ...newTxn, amount: e.target.value })} className="w-32" />
            <Select value={newTxn.transaction_type} onValueChange={(v) => setNewTxn({ ...newTxn, transaction_type: v })}>
              <SelectTrigger size="sm" className="w-[110px]"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="Expense">Expense</SelectItem>
                <SelectItem value="Income">Income</SelectItem>
              </SelectContent>
            </Select>
            <Select value={newTxn.category || ANY} onValueChange={(v) => setNewTxn({ ...newTxn, category: v === ANY ? '' : v })}>
              <SelectTrigger size="sm" className="w-[150px]"><SelectValue placeholder="Category…" /></SelectTrigger>
              <SelectContent>
                <SelectItem value={ANY}>Category…</SelectItem>
                {categories.data?.map((c) => <SelectItem key={c.id} value={c.name}>{c.name}</SelectItem>)}
              </SelectContent>
            </Select>
            <Input type="text" placeholder="Account" value={newTxn.account}
              onChange={(e) => setNewTxn({ ...newTxn, account: e.target.value })} className="w-32" />
            <Button size="sm" disabled={!newTxn.description || !newTxn.amount} onClick={() => createTxn.mutate()}>Save</Button>
            <Button size="sm" variant="outline" onClick={() => setShowAddForm(false)}>Cancel</Button>
          </CardContent>
        </Card>
      )}

      <Card className="py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Date</TableHead><TableHead>Description</TableHead><TableHead>Category</TableHead>
              <TableHead>Account</TableHead><TableHead>Type</TableHead>
              <TableHead className="text-right">Amount</TableHead><TableHead>Sync</TableHead><TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!transactions.data?.length ? (
              <TableRow><TableCell colSpan={8}>
                <div className="py-8 text-center text-sm text-muted-foreground">No transactions match these filters.</div>
              </TableCell></TableRow>
            ) : transactions.data.map((t) => (
              <TableRow key={t.transaction_id}>
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
