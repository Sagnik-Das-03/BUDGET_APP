import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../lib/api';
import { fmtMoney } from '../lib/format';

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
  'August', 'September', 'October', 'November', 'December'];

const SYNC_COLORS: Record<string, string> = {
  synced: '#0ca30c', pending: '#898781', conflict: '#e34948', error: '#e34948',
};

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
      <h1>Transactions</h1>
      <p className="subtitle">Every transaction across every month and year, in one place.</p>

      <div className="filters">
        <input type="number" placeholder="Year" value={year} onChange={(e) => setYear(e.target.value)} />
        <select value={month} onChange={(e) => setMonth(e.target.value)}>
          <option value="">Any month</option>
          {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
        </select>
        <select value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">Any category</option>
          {categories.data?.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
        </select>
        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">Any type</option>
          <option value="Income">Income</option>
          <option value="Expense">Expense</option>
        </select>
        <input type="text" placeholder="Search description…" value={search} onChange={(e) => setSearch(e.target.value)} />
        <button className="btn" onClick={applyFilters}>Filter</button>
        <button className="btn primary" onClick={() => setShowAddForm(!showAddForm)}>+ Add Transaction</button>
      </div>

      {showAddForm && (
        <div className="chart-card" style={{ marginBottom: 16 }}>
          <div className="form-row">
            <input type="date" value={newTxn.date} onChange={(e) => setNewTxn({ ...newTxn, date: e.target.value })} />
            <input type="text" placeholder="Description" value={newTxn.description}
              onChange={(e) => setNewTxn({ ...newTxn, description: e.target.value })} />
            <input type="number" placeholder="Amount" step="0.01" value={newTxn.amount}
              onChange={(e) => setNewTxn({ ...newTxn, amount: e.target.value })} />
            <select value={newTxn.transaction_type} onChange={(e) => setNewTxn({ ...newTxn, transaction_type: e.target.value })}>
              <option>Expense</option><option>Income</option>
            </select>
            <select value={newTxn.category} onChange={(e) => setNewTxn({ ...newTxn, category: e.target.value })}>
              <option value="">Category…</option>
              {categories.data?.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
            </select>
            <input type="text" placeholder="Account" value={newTxn.account}
              onChange={(e) => setNewTxn({ ...newTxn, account: e.target.value })} />
            <button className="btn primary" disabled={!newTxn.description || !newTxn.amount}
              onClick={() => createTxn.mutate()}>Save</button>
            <button className="btn" onClick={() => setShowAddForm(false)}>Cancel</button>
          </div>
        </div>
      )}

      <table>
        <thead>
          <tr>
            <th>Date</th><th>Description</th><th>Category</th><th>Account</th><th>Type</th>
            <th className="amount">Amount</th><th>Sync</th><th></th>
          </tr>
        </thead>
        <tbody>
          {!transactions.data?.length ? (
            <tr><td colSpan={8}><div className="empty-state">No transactions match these filters.</div></td></tr>
          ) : transactions.data.map((t) => (
            <tr key={t.transaction_id}>
              <td>{t.date}</td>
              <td>{t.description}</td>
              <td>{t.category}</td>
              <td>{t.account}</td>
              <td>{t.transaction_type}</td>
              <td className="amount">{fmtMoney(t.amount)}</td>
              <td><span className="pill" style={{ background: SYNC_COLORS[t.sync_status] || '#898781' }}>{t.sync_status}</span></td>
              <td>
                <button className="btn danger" onClick={() => {
                  if (confirm('Delete this transaction?')) deleteTxn.mutate(t.transaction_id);
                }}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
