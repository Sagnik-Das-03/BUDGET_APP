export function fmtMoney(v: number | null | undefined): string {
  return '₹' + Number(v || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });
}

export function fmtPct(v: number | null | undefined): string {
  return (Number(v || 0) * 100).toFixed(1) + '%';
}
