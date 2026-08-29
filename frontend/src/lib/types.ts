export interface Category {
  id: number;
  name: string;
  color_hex: string;
  is_active: boolean;
  counts_as_expense: boolean;
}

export interface Account {
  id: number;
  name: string;
  account_type: string;
  is_active: boolean;
}

export interface Transaction {
  transaction_id: string;
  date: string;
  description: string;
  amount: number;
  transaction_type: 'Income' | 'Expense';
  category: string;
  account: string;
  period_key: string;
  notes: string | null;
  source: string;
  sync_status: 'pending' | 'synced' | 'conflict' | 'error';
  created_at: string;
  updated_at: string;
}

export interface Totals {
  income: number;
  expenses: number;
  sip: number;
  cash_savings: number;
  net: number;
  savings_rate: number;
}

export interface CategoryTotal {
  category: string;
  total: number;
  color: string;
}

export interface CategoryDrilldownChild {
  name: string;
  value: number;
  date: string;
  transaction_id: string;
}

export interface CategoryDrilldownNode {
  name: string;
  color: string;
  value: number;
  children: CategoryDrilldownChild[];
}

export interface Highlights {
  top_category: CategoryTotal | null;
  transaction_count: number;
  avg_daily_spend: number;
  days: number;
  comparison: {
    income_delta_pct: number | null;
    expenses_delta_pct: number | null;
    net_delta_pct: number | null;
    previous_range: { date_from: string; date_to: string };
  } | null;
}

export interface TrendRow {
  period_key?: string;
  week_key?: string;
  day?: string;
  year?: string;
  label?: string;
  income: number;
  expenses: number;
  net: number;
}

export interface TrendForRange {
  granularity: 'daily' | 'weekly' | 'monthly' | 'yearly';
  rows: TrendRow[];
}

export interface BudgetVsActual {
  category: string;
  goal: number;
  actual: number;
}

export interface BudgetAlert {
  category: string;
  goal: number;
  actual: number;
  pct: number;
  status: 'warning' | 'critical';
}

export interface Budget {
  category: string;
  period_key: string | null;
  goal_amount: number;
}

export interface SavingsGoalProgress {
  goal: number | null;
  actual?: number;
  pct?: number;
  status?: 'met' | 'warning' | 'behind';
}

export interface SyncStatus {
  state: 'not_configured' | 'idle' | 'syncing' | 'error';
  last_synced_at: string | null;
  last_summary: Record<string, unknown> | null;
  last_error: string | null;
}

export interface SyncLogEntry {
  timestamp: string;
  level: 'info' | 'warn' | 'error';
  message: string;
}

export interface ConflictRow {
  transaction_id: string;
  app_value: {
    date: string; description: string; amount: number; transaction_type: string;
    category: string; account: string; notes: string | null;
  };
  sheet_value: {
    date: string; description: string; amount: number; transaction_type: string;
    category: string; account: string; notes: string | null; deleted?: boolean;
  } | null;
}

export type RangeKey = 'this_week' | 'this_month' | 'this_year' | 'all_time';

export interface SyncConfig {
  credentials_configured: boolean;
  google_spreadsheet_id: string;
  sync_interval_seconds: number;
  sync_interval_default: number;
  sync_interval_min: number;
}
