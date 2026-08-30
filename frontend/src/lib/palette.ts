// Validated with the dataviz skill's validate_palette.js against both the light
// (#fcfcfb) and dark (#1c1b19) chart surfaces - kept in sync with the backend
// default in app/api/appearance.py, which is what's actually served once a
// user has no override yet; this is just the pre-fetch fallback.
export const PALETTE = {
  income: '#3b82f6',
  expenses: '#f43f5e',
  net: '#6366f1',
  goal: '#898781',
  sip: '#d97706',
  cashSavings: '#0d9488',
};
