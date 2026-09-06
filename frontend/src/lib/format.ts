export function fmtMoney(v: number | null | undefined): string {
  return '₹' + Number(v || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });
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
