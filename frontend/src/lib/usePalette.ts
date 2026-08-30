import { useQuery } from '@tanstack/react-query';
import { api } from './api';
import { PALETTE as DEFAULT_PALETTE } from './palette';

/** Chart colors (Income/Expenses/Net/Goal/SIP/Cash Savings), customizable in
 * Settings and persisted server-side - falls back to the built-in defaults
 * before the fetch resolves or for any color the user hasn't overridden. */
export function usePalette() {
  const { data } = useQuery({ queryKey: ['chartPalette'], queryFn: api.getPalette, staleTime: Infinity });
  return {
    income: data?.income ?? DEFAULT_PALETTE.income,
    expenses: data?.expenses ?? DEFAULT_PALETTE.expenses,
    net: data?.net ?? DEFAULT_PALETTE.net,
    goal: data?.goal ?? DEFAULT_PALETTE.goal,
    sip: data?.sip ?? DEFAULT_PALETTE.sip,
    cashSavings: data?.cash_savings ?? DEFAULT_PALETTE.cashSavings,
  };
}
