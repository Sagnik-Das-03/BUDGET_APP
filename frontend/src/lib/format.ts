export function fmtMoney(v: number | null | undefined): string {
  return '₹' + Number(v || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });
}

// Like fmtMoney, but keeps paise when the value actually has them (e.g. a
// transaction entered as 49.50) instead of always rounding to whole rupees -
// for per-transaction amounts, not aggregate totals, where rounding away a
// real entered value would misrepresent it rather than just tidy a sum.
export function fmtMoneyExact(v: number | null | undefined): string {
  return '₹' + Number(v || 0).toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

export function fmtPct(v: number | null | undefined): string {
  return (Number(v || 0) * 100).toFixed(1) + '%';
}

// Signed rupee amount with the +/- in front of the symbol (fmtMoney alone
// would render a negative as "₹-1,000", sign after the symbol).
export function fmtMoneySigned(v: number | null | undefined): string {
  const n = Number(v || 0);
  return (n < 0 ? '-' : '+') + fmtMoney(Math.abs(n));
}
