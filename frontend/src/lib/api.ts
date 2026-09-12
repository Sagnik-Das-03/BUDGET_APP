import type {
  Account, AskResponse, Budget, BudgetAlert, BudgetVsActual, Category, CategoryDrilldownNode,
  CategoryTotal, CategoryTrend, CategoryVolatility, ChartPalette, ChatMessage, ChatThread, ConflictRow,
  EssentialSplit, Highlights, ImportCommitResult, ImportPreviewResult, ImportRowIn, Insight, LlmStatus,
  MonthlyBreakdownRow, QuickAddResult, SavedView, SavingsGoalProgress, SavingsStreak, SpendConcentration,
  SpendingPattern, SyncConfig, SyncLogEntry, SyncStatus, Totals, Transaction, TrashedTransaction, TrendForRange,
  ViewFilters,
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
  categoryTrends: (range: string, type = 'Expense', dateBounds?: DateBounds) =>
    request<CategoryTrend[]>(`/api/dashboard/category_trends${qs({ range, type, ...dateBounds })}`),
  categoryVolatility: (months = 6) =>
    request<CategoryVolatility[]>(`/api/dashboard/category_volatility${qs({ months })}`),
  spendingPattern: (range: string, dateBounds?: DateBounds) =>
    request<SpendingPattern>(`/api/dashboard/spending_pattern${qs({ range, ...dateBounds })}`),
  essentialSplit: (range: string, dateBounds?: DateBounds) =>
    request<EssentialSplit>(`/api/dashboard/essential_split${qs({ range, ...dateBounds })}`),
  savingsStreak: () => request<SavingsStreak>('/api/dashboard/savings_streak'),
  spendConcentration: (range: string, topN = 3, dateBounds?: DateBounds) =>
    request<SpendConcentration>(`/api/dashboard/spend_concentration${qs({ range, top_n: topN, ...dateBounds })}`),

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
  setCategoryEssential: (id: number, is_essential: boolean) =>
    request<Category>(`/api/categories/${id}/is_essential${qs({ is_essential })}`, { method: 'PUT' }),
  listAccounts: () => request<Account[]>('/api/accounts'),
  addAccount: (name: string) => request<Account>('/api/accounts', { method: 'POST', body: JSON.stringify({ name }) }),
  deactivateAccount: (id: number) => request(`/api/accounts/${id}`, { method: 'DELETE' }),

  // ---------- transactions ----------
  listTransactions: (filters: Record<string, QueryValue>) =>
    request<Transaction[]>(`/api/transactions${qs(filters)}`),
  createTransaction: (payload: Record<string, unknown>) =>
    request<Transaction>('/api/transactions', { method: 'POST', body: JSON.stringify(payload) }),
  updateTransaction: (id: string, payload: Record<string, unknown>) =>
    request<Transaction>(`/api/transactions/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
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

  // ---------- local AI features ----------
  llmStatus: () => request<LlmStatus>('/api/llm/status'),
  autocomplete: (text: string, date?: string) =>
    request<{ suggestion: string }>('/api/llm/autocomplete', { method: 'POST', body: JSON.stringify({ text, date }) }),
  categorize: (description: string) =>
    request<{ category: string }>('/api/llm/categorize', { method: 'POST', body: JSON.stringify({ description }) }),
  suggestViewName: (filters: ViewFilters) =>
    request<{ name: string }>('/api/llm/suggest_view_name', {
      method: 'POST',
      body: JSON.stringify({
        category: filters.category, category_exclude: filters.categoryExclude,
        account: filters.account, account_exclude: filters.accountExclude,
        type: filters.type || undefined, search: filters.search || undefined,
        year: filters.year || undefined, month: filters.month || undefined,
      }),
    }),
  insight: (range: string, dateBounds?: DateBounds, label?: string) =>
    request<Insight>(`/api/llm/insight${qs({ range, label, ...dateBounds })}`),
  compareRecap: (payload: {
    label_a: string; label_b: string; date_from_a: string; date_to_a: string;
    date_from_b: string; date_to_b: string;
  }) => request<{ recap: string }>('/api/llm/compare_recap', { method: 'POST', body: JSON.stringify(payload) }),
  llmModelStatus: (task: string) =>
    request<{ task: string; available: boolean; loaded: boolean }>(`/api/llm/model_status/${task}`),
  warmupModel: (task: string) =>
    request<{ task: string; loaded: boolean }>(`/api/llm/warmup/${task}`, { method: 'POST' }),
  ask: (question: string, threadId?: number | null) =>
    request<AskResponse>('/api/llm/ask', {
      method: 'POST', body: JSON.stringify({ question, thread_id: threadId ?? null }),
    }),
  chatThreads: () => request<ChatThread[]>('/api/llm/chat/threads'),
  createChatThread: () => request<ChatThread>('/api/llm/chat/threads', { method: 'POST' }),
  chatMessages: (threadId: number) => request<ChatMessage[]>(`/api/llm/chat/threads/${threadId}/messages`),
  deleteChatThread: (threadId: number) =>
    request<{ deleted: boolean }>(`/api/llm/chat/threads/${threadId}`, { method: 'DELETE' }),
  sendChatFeedback: (messageId: number, helpful: boolean, note?: string) =>
    request<{ recorded: boolean }>(`/api/llm/chat/messages/${messageId}/feedback`, {
      method: 'POST', body: JSON.stringify({ helpful, note: note ?? null }),
    }),
  quickAdd: (text: string) =>
    request<QuickAddResult>('/api/llm/quick_add', { method: 'POST', body: JSON.stringify({ text }) }),

  // ---------- saved views ----------
  listSavedViews: () => request<SavedView[]>('/api/saved_views'),
  createSavedView: (name: string, filters: ViewFilters) =>
    request<SavedView>('/api/saved_views', { method: 'POST', body: JSON.stringify({ name, filters }) }),
  deleteSavedView: (id: number) =>
    request<{ deleted: boolean }>(`/api/saved_views/${id}`, { method: 'DELETE' }),

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
  resolveConflict: (id: string, keep: 'app' | 'sheets' | 'both') =>
    request(`/api/conflicts/${id}/resolve`, { method: 'POST', body: JSON.stringify({ keep }) }),

  // ---------- sync ----------
  syncStatus: () => request<SyncStatus>('/api/sync/status'),
  syncConfig: () => request<SyncConfig>('/api/sync/config'),
  setSyncInterval: (seconds: number) =>
    request<{ sync_interval_seconds: number }>('/api/sync/interval', { method: 'POST', body: JSON.stringify({ seconds }) }),
  syncNow: () => request('/api/sync/now', { method: 'POST' }),
  setSheetSortDirection: (descending: boolean) =>
    request<{ sheet_sort_descending: boolean }>('/api/sync/sort_direction', { method: 'POST', body: JSON.stringify({ descending }) }),
  compactSheetNow: () =>
    request<{ removed_blank: number; reordered: boolean } | { error: string }>('/api/sync/compact', { method: 'POST' }),
  setTabOrderDirection: (descending: boolean) =>
    request<{ period_tab_sort_descending: boolean }>('/api/sync/tab_order_direction', { method: 'POST', body: JSON.stringify({ descending }) }),
  reorderTabsNow: () =>
    request<{ reordered: boolean } | { error: string }>('/api/sync/reorder_tabs', { method: 'POST' }),
  syncLogs: (limit = 500) => request<SyncLogEntry[]>(`/api/sync/logs?limit=${limit}`),
};
