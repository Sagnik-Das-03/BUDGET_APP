import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Trash2, X } from 'lucide-react';
import { api } from '../lib/api';
import { fmtMoney } from '../lib/format';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

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

  const [pendingDeleteResult, setPendingDeleteResult] = useState<{ total: number } | null>(null);
  const deletePending = useMutation({
    mutationFn: () => api.deletePendingTransactions(),
    onSuccess: (data) => {
      setPendingDeleteResult({ total: data.total });
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
    },
  });

  const goalByCategory: Record<string, number> = {};
  budgets.data?.filter((b) => !b.period_key).forEach((b) => { goalByCategory[b.category] = b.goal_amount; });

  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-2xl font-bold tracking-tight">Settings</h1>

      <Card>
        <CardHeader>
          <CardTitle>Google Sheets sync</CardTitle>
          <CardDescription className="space-y-0.5">
            <div>Credentials: {config.data?.credentials_configured ? '✓ configured' : '✗ not configured — see docs/service_account_setup.md'}</div>
            <div>Spreadsheet ID: {config.data?.google_spreadsheet_id || 'not set (add GOOGLE_SPREADSHEET_ID to .env)'}</div>
            <div>Sync interval: every {config.data?.sync_interval_seconds}s</div>
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-2.5">
          <Label htmlFor="interval-input" className="text-sm">Change to</Label>
          <Input id="interval-input" type="number" min={config.data?.sync_interval_min ?? 15} step="5"
            className="w-24" value={intervalInput} onChange={(e) => setIntervalInput(e.target.value)} />
          <span className="text-sm text-muted-foreground">seconds</span>
          <Button size="sm" onClick={() => {
            const v = parseInt(intervalInput, 10);
            const min = config.data?.sync_interval_min ?? 15;
            if (!v || v < min) { alert(`Enter at least ${min} seconds`); return; }
            saveInterval.mutate(v);
          }}>Save</Button>
          <span className="text-xs text-muted-foreground">
            Takes effect immediately, no restart — overrides SYNC_INTERVAL_SECONDS in .env
            (default: {config.data?.sync_interval_default}s) until changed again here.
          </span>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Net Savings Goal</CardTitle>
          <CardDescription>A monthly target on overall Net Savings (Income minus true Expenses) - separate from per-category budgets.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-2.5">
          <Input type="number" step="0.01" min="0" placeholder="e.g. 30000" className="w-36"
            value={goalInput} onChange={(e) => setGoalInput(e.target.value)} />
          <Button size="sm" onClick={() => {
            const v = parseFloat(goalInput);
            if (!v || v <= 0) { alert('Enter a goal amount greater than 0'); return; }
            saveSavingsGoal.mutate(v);
          }}>Save</Button>
          {savingsGoal.data?.goal_amount ? (
            <Button size="sm" variant="outline" onClick={() => clearSavingsGoal.mutate()}>Clear</Button>
          ) : null}
          <span className="text-xs text-muted-foreground">
            {savingsGoal.data?.goal_amount ? `Current goal: ${fmtMoney(savingsGoal.data.goal_amount)} / month` : 'No goal set'}
          </span>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Budgets</CardTitle>
          <CardDescription>Set a recurring monthly goal per category. The Dashboard warns you when a category crosses 90% of its goal for the current month.</CardDescription>
        </CardHeader>
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow><TableHead className="pl-6">Category</TableHead><TableHead className="text-right">Monthly Goal</TableHead><TableHead className="pr-6"></TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {categories.data?.filter((c) => c.name !== 'Income').map((c) => {
                const goal = goalByCategory[c.name];
                const inputValue = budgetInputs[c.name] ?? (goal ? String(goal) : '');
                return (
                  <TableRow key={c.id}>
                    <TableCell className="pl-6">
                      <span className="mr-1.5 inline-block size-2.5 rounded-full align-middle" style={{ background: c.color_hex }} /> {c.name}
                    </TableCell>
                    <TableCell className="text-right">
                      <Input type="number" step="0.01" min="0" className="ml-auto w-28 text-right"
                        placeholder="No goal" value={inputValue}
                        onChange={(e) => setBudgetInputs({ ...budgetInputs, [c.name]: e.target.value })} />
                    </TableCell>
                    <TableCell className="pr-6">
                      <div className="flex justify-end gap-1.5">
                        <Button size="sm" variant="outline" onClick={() => {
                          const v = parseFloat(inputValue);
                          if (!v || v <= 0) { alert('Enter a goal amount greater than 0'); return; }
                          saveBudget.mutate({ category: c.name, amount: v });
                        }}>Save</Button>
                        {goal ? <Button size="sm" variant="ghost" onClick={() => clearBudget.mutate(c.name)}>Clear</Button> : null}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Categories</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {categories.data?.map((c) => (
              <Badge key={c.id} variant="outline" className="gap-1.5 py-1 pl-1 pr-2 text-xs">
                <span className="inline-block size-2.5 rounded-full" style={{ background: c.color_hex }} />
                {c.name}
                <button
                  className="ml-0.5 text-muted-foreground hover:text-destructive"
                  onClick={() => {
                    if (confirm("Deactivate this category? Historical transactions keep it, but it won't be selectable for new ones.")) {
                      deactivateCategory.mutate(c.id);
                    }
                  }}
                >
                  <X className="size-3" />
                </button>
              </Badge>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2.5">
            <Input type="text" placeholder="New category name" value={newCatName} onChange={(e) => setNewCatName(e.target.value)} className="w-48" />
            <input type="color" value={newCatColor} onChange={(e) => setNewCatColor(e.target.value)}
              className="h-9 w-12 cursor-pointer rounded-md border border-input p-1" />
            <Button size="sm" disabled={!newCatName.trim()} onClick={() => addCategory.mutate()}>Add Category</Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Accounts</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {accounts.data?.map((a) => (
              <Badge key={a.id} variant="outline" className="gap-1.5 py-1 pl-2.5 pr-2 text-xs">
                {a.name}
                <button
                  className="ml-0.5 text-muted-foreground hover:text-destructive"
                  onClick={() => { if (confirm('Deactivate this account?')) deactivateAccount.mutate(a.id); }}
                >
                  <X className="size-3" />
                </button>
              </Badge>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2.5">
            <Input type="text" placeholder="New account name" value={newAcctName} onChange={(e) => setNewAcctName(e.target.value)} className="w-48" />
            <Button size="sm" disabled={!newAcctName.trim()} onClick={() => addAccount.mutate()}>Add Account</Button>
          </div>
        </CardContent>
      </Card>

      <Card className="border-destructive/40">
        <CardHeader>
          <CardTitle className="text-destructive">Data management</CardTitle>
          <CardDescription>
            Deletes every transaction still waiting to sync (or that previously failed to sync) - e.g. to discard
            a bad CSV import before it ever reaches Google Sheets. Already-synced transactions are never touched.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-2.5">
          <Button
            variant="destructive"
            size="sm"
            disabled={deletePending.isPending}
            onClick={() => {
              if (confirm(
                'Delete ALL pending / failed-sync transactions? This cannot be undone from the UI.\n\n' +
                'Transactions already synced to Google Sheets are not affected.',
              )) {
                setPendingDeleteResult(null);
                deletePending.mutate();
              }
            }}
          >
            <Trash2 className="size-4" />
            {deletePending.isPending ? 'Deleting…' : 'Delete all pending transactions'}
          </Button>
          {pendingDeleteResult && (
            <span className="text-xs text-muted-foreground">
              Deleted {pendingDeleteResult.total} transaction{pendingDeleteResult.total === 1 ? '' : 's'}.
            </span>
          )}
          {deletePending.isError && (
            <span className="text-xs text-destructive">{(deletePending.error as Error).message}</span>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
