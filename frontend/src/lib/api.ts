import type {
  Account, Budget, BudgetAlert, BudgetVsActual, Category, CategoryDrilldownNode,
  CategoryTotal, ChartPalette, ConflictRow, Highlights, ImportCommitResult, ImportPreviewResult, ImportRowIn,
  MonthlyBreakdownRow, SavingsGoalProgress, SyncConfig, SyncLogEntry,
  SyncStatus, Totals, Transaction, TrashedTransaction, TrendForRange,
} from './types';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : (undefined as T);
}

type QueryValue = string | number | boolean | string[] | undefined;

function qs(params: Record<string, QueryValue>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === '') continue;
    if (Array.isArray(v)) {
      for (const item of v) parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(item)}`);
    } else {
      parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
    }
  }
  return parts.length ? `?${parts.join('&')}` : '';
}

export interface DateBounds {
  date_from?: string;
  date_to?: string;
}

export const api = {
  // ---------- dashboard ----------
  // A caller passing dateBounds also passes range: 'custom' to activate them -
  // see Dashboard.tsx's effectiveRange(). Backend: app/api/dashboard.py's
  // _resolve_range() already supports range=custom&date_from=&date_to=.
  summary: (range: string, dateBounds?: DateBounds) =>
    request<Totals>(`/api/dashboard/summary${qs({ range, ...dateBounds })}`),
  byCategory: (range: string, type = 'Expense', dateBounds?: DateBounds) =>
    request<CategoryTotal[]>(`/api/dashboard/by_category${qs({ range, type, ...dateBounds })}`),
  categoryDrilldown: (range: string, type = 'Expense', dateBounds?: DateBounds) =>
    request<CategoryDrilldownNode[]>(`/api/dashboard/category_drilldown${qs({ range, type, ...dateBounds })}`),
  highlights: (range: string, dateBounds?: DateBounds) =>
    request<Highlights>(`/api/dashboard/highlights${qs({ range, ...dateBounds })}`),
  trendForRange: (range: string) => request<TrendForRange>(`/api/dashboard/trend_for_range${qs({ range })}`),
  budgetVsActual: () => request<BudgetVsActual[]>('/api/dashboard/budget_vs_actual'),
  monthlyBreakdown: () => request<MonthlyBreakdownRow[]>('/api/dashboard/monthly_breakdown'),
  budgetAlerts: () => request<BudgetAlert[]>('/api/dashboard/budget_alerts'),

  // ---------- savings goal ----------
  getSavingsGoal: () => request<{ period_key: string; goal_amount: number | null }>('/api/savings_goal'),
  setSavingsGoal: (goal_amount: number) =>
    request('/api/savings_goal', { method: 'POST', body: JSON.stringify({ goal_amount }) }),
  clearSavingsGoal: () => request('/api/savings_goal', { method: 'DELETE' }),
  savingsGoalProgress: (periodKey?: string) =>
    request<SavingsGoalProgress>(`/api/savings_goal/progress${qs({ period_key: periodKey })}`),

  // ---------- budgets ----------
  listBudgets: () => request<Budget[]>('/api/budgets'),
  setBudget: (category: string, goal_amount: number) =>
    request('/api/budgets', { method: 'POST', body: JSON.stringify({ category, goal_amount }) }),
  clearBudget: (category: string) => request(`/api/budgets/${encodeURIComponent(category)}`, { method: 'DELETE' }),

  // ---------- categories / accounts ----------
  listCategories: () => request<Category[]>('/api/categories'),
  addCategory: (name: string, color_hex: string) =>
    request<Category>('/api/categories', { method: 'POST', body: JSON.stringify({ name, color_hex }) }),
  updateCategory: (id: number, name: string, color_hex: string) =>
    request<Category>(`/api/categories/${id}`, { method: 'PUT', body: JSON.stringify({ name, color_hex }) }),
  deactivateCategory: (id: number) => request(`/api/categories/${id}`, { method: 'DELETE' }),
  listAccounts: () => request<Account[]>('/api/accounts'),
  addAccount: (name: string) => request<Account>('/api/accounts', { method: 'POST', body: JSON.stringify({ name }) }),
  deactivateAccount: (id: number) => request(`/api/accounts/${id}`, { method: 'DELETE' }),

  // ---------- transactions ----------
  listTransactions: (filters: Record<string, QueryValue>) =>
    request<Transaction[]>(`/api/transactions${qs(filters)}`),
  createTransaction: (payload: Record<string, unknown>) =>
    request<Transaction>('/api/transactions', { method: 'POST', body: JSON.stringify(payload) }),
  bulkCreateTransactions: (transactions: Record<string, unknown>[]) =>
    request<Transaction[]>('/api/transactions/bulk', { method: 'POST', body: JSON.stringify({ transactions }) }),
  deleteTransaction: (id: string) => request(`/api/transactions/${id}`, { method: 'DELETE' }),
  bulkDeleteTransactions: (transaction_ids: string[]) =>
    request<{ deleted_count: number }>('/api/transactions/bulk_delete', { method: 'POST', body: JSON.stringify({ transaction_ids }) }),
  deletePendingTransactions: () =>
    request<{ hard_deleted: number; soft_deleted: number; total: number }>('/api/transactions/pending', { method: 'DELETE' }),

  // ---------- trash ----------
  listTrash: () => request<TrashedTransaction[]>('/api/transactions/trash'),
  restoreTransaction: (id: string) => request<Transaction>(`/api/transactions/${id}/restore`, { method: 'POST' }),
  bulkRestoreTransactions: (transaction_ids: string[]) =>
    request<{ restored_count: number }>('/api/transactions/bulk_restore', { method: 'POST', body: JSON.stringify({ transaction_ids }) }),
  permanentDeleteTransaction: (id: string) => request(`/api/transactions/${id}/permanent`, { method: 'DELETE' }),
  bulkPermanentDeleteTransactions: (transaction_ids: string[]) =>
    request<{ deleted: number; blocked: number; not_found: number }>('/api/transactions/bulk_permanent_delete', { method: 'POST', body: JSON.stringify({ transaction_ids }) }),

  // ---------- appearance ----------
  getPalette: () => request<ChartPalette>('/api/appearance/palette'),
  setPalette: (partial: Partial<ChartPalette>) =>
    request<ChartPalette>('/api/appearance/palette', { method: 'PUT', body: JSON.stringify(partial) }),
  resetPalette: () => request<ChartPalette>('/api/appearance/palette', { method: 'DELETE' }),

  // ---------- csv import ----------
  importPreview: async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch('/api/imports/csv/preview', { method: 'POST', body: formData });
    if (!res.ok) {
      const body = await res.text();
      throw new Error(`${res.status}: ${body}`);
    }
    return res.json() as Promise<ImportPreviewResult>;
  },
  importCommit: (rows: ImportRowIn[]) =>
    request<ImportCommitResult>('/api/imports/csv/commit', { method: 'POST', body: JSON.stringify({ rows }) }),

  // ---------- conflicts ----------
  listConflicts: () => request<ConflictRow[]>('/api/conflicts'),
  resolveConflict: (id: string, keep: 'app' | 'sheets') =>
    request(`/api/conflicts/${id}/resolve`, { method: 'POST', body: JSON.stringify({ keep }) }),

  // ---------- sync ----------
  syncStatus: () => request<SyncStatus>('/api/sync/status'),
  syncConfig: () => request<SyncConfig>('/api/sync/config'),
  setSyncInterval: (seconds: number) =>
    request<{ sync_interval_seconds: number }>('/api/sync/interval', { method: 'POST', body: JSON.stringify({ seconds }) }),
  syncNow: () => request('/api/sync/now', { method: 'POST' }),
  syncLogs: () => request<SyncLogEntry[]>('/api/sync/logs?limit=200'),
};
