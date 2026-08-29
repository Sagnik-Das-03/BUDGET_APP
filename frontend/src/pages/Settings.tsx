import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { fmtMoney } from '../lib/format';

export function Settings() {
  const queryClient = useQueryClient();
  const config = useQuery({ queryKey: ['syncConfig'], queryFn: api.syncConfig });
  const savingsGoal = useQuery({ queryKey: ['savingsGoal'], queryFn: api.getSavingsGoal });
  const budgets = useQuery({ queryKey: ['budgets'], queryFn: api.listBudgets });
  const categories = useQuery({ queryKey: ['categories'], queryFn: api.listCategories });
  const accounts = useQuery({ queryKey: ['accounts'], queryFn: api.listAccounts });

  const invalidate = (key: string) => queryClient.invalidateQueries({ queryKey: [key] });

  const [goalInput, setGoalInput] = useState('');
  useEffect(() => {
    if (savingsGoal.data?.goal_amount) setGoalInput(String(savingsGoal.data.goal_amount));
  }, [savingsGoal.data]);

  const [intervalInput, setIntervalInput] = useState('');
  useEffect(() => {
    if (config.data) setIntervalInput(String(config.data.sync_interval_seconds));
  }, [config.data]);
  const saveInterval = useMutation({
    mutationFn: (seconds: number) => api.setSyncInterval(seconds),
    onSuccess: () => invalidate('syncConfig'),
  });

  const saveSavingsGoal = useMutation({
    mutationFn: (amount: number) => api.setSavingsGoal(amount),
    onSuccess: () => invalidate('savingsGoal'),
  });
  const clearSavingsGoal = useMutation({
    mutationFn: () => api.clearSavingsGoal(),
    onSuccess: () => { setGoalInput(''); invalidate('savingsGoal'); },
  });

  const [budgetInputs, setBudgetInputs] = useState<Record<string, string>>({});
  const saveBudget = useMutation({
    mutationFn: ({ category, amount }: { category: string; amount: number }) => api.setBudget(category, amount),
    onSuccess: () => invalidate('budgets'),
  });
  const clearBudget = useMutation({
    mutationFn: (category: string) => api.clearBudget(category),
    onSuccess: () => invalidate('budgets'),
  });

  const [newCatName, setNewCatName] = useState('');
  const [newCatColor, setNewCatColor] = useState('#898781');
  const addCategory = useMutation({
    mutationFn: () => api.addCategory(newCatName, newCatColor),
    onSuccess: () => { setNewCatName(''); invalidate('categories'); },
  });
  const deactivateCategory = useMutation({
    mutationFn: (id: number) => api.deactivateCategory(id),
    onSuccess: () => invalidate('categories'),
  });

  const [newAcctName, setNewAcctName] = useState('');
  const addAccount = useMutation({
    mutationFn: () => api.addAccount(newAcctName),
    onSuccess: () => { setNewAcctName(''); invalidate('accounts'); },
  });
  const deactivateAccount = useMutation({
    mutationFn: (id: number) => api.deactivateAccount(id),
    onSuccess: () => invalidate('accounts'),
  });

  const goalByCategory: Record<string, number> = {};
  budgets.data?.filter((b) => !b.period_key).forEach((b) => { goalByCategory[b.category] = b.goal_amount; });

  return (
    <>
      <h1>Settings</h1>

      <h2>Google Sheets sync</h2>
      <p className="subtitle">
        Credentials: {config.data?.credentials_configured ? '✓ configured' : '✗ not configured — see docs/service_account_setup.md'}<br />
        Spreadsheet ID: {config.data?.google_spreadsheet_id || 'not set (add GOOGLE_SPREADSHEET_ID to .env)'}<br />
        Sync interval: every {config.data?.sync_interval_seconds}s
      </p>
      <div className="form-row">
        <label htmlFor="interval-input" style={{ fontSize: 13 }}>Change to</label>
        <input id="interval-input" type="number" min={config.data?.sync_interval_min ?? 15} step="5"
          style={{ width: 90 }} value={intervalInput} onChange={(e) => setIntervalInput(e.target.value)} />
        <span className="subtitle" style={{ margin: 0 }}>seconds</span>
        <button className="btn primary" onClick={() => {
          const v = parseInt(intervalInput, 10);
          const min = config.data?.sync_interval_min ?? 15;
          if (!v || v < min) { alert(`Enter at least ${min} seconds`); return; }
          saveInterval.mutate(v);
        }}>Save</button>
        <span className="subtitle" style={{ margin: 0 }}>
          Takes effect immediately, no restart — overrides SYNC_INTERVAL_SECONDS in .env
          (default: {config.data?.sync_interval_default}s) until changed again here.
        </span>
      </div>

      <h2>Net Savings Goal</h2>
      <p className="subtitle">A monthly target on overall Net Savings (Income minus true Expenses) - separate from per-category budgets.</p>
      <div className="form-row">
        <input type="number" step="0.01" min="0" placeholder="e.g. 30000" style={{ width: 150 }}
          value={goalInput} onChange={(e) => setGoalInput(e.target.value)} />
        <button className="btn primary" onClick={() => {
          const v = parseFloat(goalInput);
          if (!v || v <= 0) { alert('Enter a goal amount greater than 0'); return; }
          saveSavingsGoal.mutate(v);
        }}>Save</button>
        {savingsGoal.data?.goal_amount ? (
          <button className="btn" onClick={() => clearSavingsGoal.mutate()}>Clear</button>
        ) : null}
        <span className="subtitle" style={{ margin: 0 }}>
          {savingsGoal.data?.goal_amount ? `Current goal: ${fmtMoney(savingsGoal.data.goal_amount)} / month` : 'No goal set'}
        </span>
      </div>

      <h2>Budgets</h2>
      <p className="subtitle">Set a recurring monthly goal per category. The Dashboard warns you when a category crosses 90% of its goal for the current month.</p>
      <table>
        <thead><tr><th>Category</th><th className="amount">Monthly Goal</th><th></th></tr></thead>
        <tbody>
          {categories.data?.filter((c) => c.name !== 'Income').map((c) => {
            const goal = goalByCategory[c.name];
            const inputValue = budgetInputs[c.name] ?? (goal ? String(goal) : '');
            return (
              <tr key={c.id}>
                <td><span className="swatch" style={{ background: c.color_hex }} /> {c.name}</td>
                <td className="amount">
                  <input type="number" step="0.01" min="0" style={{ width: 110, textAlign: 'right' }}
                    placeholder="No goal" value={inputValue}
                    onChange={(e) => setBudgetInputs({ ...budgetInputs, [c.name]: e.target.value })} />
                </td>
                <td>
                  <button className="btn" onClick={() => {
                    const v = parseFloat(inputValue);
                    if (!v || v <= 0) { alert('Enter a goal amount greater than 0'); return; }
                    saveBudget.mutate({ category: c.name, amount: v });
                  }}>Save</button>
                  {goal ? <button className="btn" onClick={() => clearBudget.mutate(c.name)}>Clear</button> : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <h2>Categories</h2>
      <div className="category-list">
        {categories.data?.map((c) => (
          <span key={c.id} className="category-chip">
            <span className="swatch" style={{ background: c.color_hex }} />{c.name}
            <button style={{ border: 'none', background: 'none', cursor: 'pointer', color: '#e34948' }}
              onClick={() => {
                if (confirm("Deactivate this category? Historical transactions keep it, but it won't be selectable for new ones.")) {
                  deactivateCategory.mutate(c.id);
                }
              }}>✕</button>
          </span>
        ))}
      </div>
      <div className="form-row">
        <input type="text" placeholder="New category name" value={newCatName} onChange={(e) => setNewCatName(e.target.value)} />
        <input type="color" value={newCatColor} onChange={(e) => setNewCatColor(e.target.value)} />
        <button className="btn primary" disabled={!newCatName.trim()} onClick={() => addCategory.mutate()}>Add Category</button>
      </div>

      <h2>Accounts</h2>
      <div className="category-list">
        {accounts.data?.map((a) => (
          <span key={a.id} className="category-chip">{a.name}
            <button style={{ border: 'none', background: 'none', cursor: 'pointer', color: '#e34948' }}
              onClick={() => { if (confirm('Deactivate this account?')) deactivateAccount.mutate(a.id); }}>✕</button>
          </span>
        ))}
      </div>
      <div className="form-row">
        <input type="text" placeholder="New account name" value={newAcctName} onChange={(e) => setNewAcctName(e.target.value)} />
        <button className="btn primary" disabled={!newAcctName.trim()} onClick={() => addAccount.mutate()}>Add Account</button>
      </div>
    </>
  );
}
