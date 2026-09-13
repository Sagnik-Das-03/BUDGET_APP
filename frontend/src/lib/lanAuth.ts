// The Android host's LAN password (see backend/app/auth.py's dynamic-
// password branch, set from the phone's own "LAN Password" card). Kept in
// sessionStorage, not localStorage - cleared when the tab closes, matching
// how a personal LAN dashboard should behave rather than remembering the
// password forever on a shared/borrowed browser. The username half of
// Basic Auth is never checked server-side (see auth_glue.py) - always sent
// empty. No-op on desktop: nothing ever calls setLanPassword() there, so
// lanAuthHeader() stays empty and every request goes out exactly as before.
const STORAGE_KEY = 'budget_tracker.lanPassword';

export function getLanPassword(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null; // private-mode/blocked storage - request() just goes out unauthenticated
  }
}

export function setLanPassword(password: string): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, password);
  } catch {
    // ignore - see getLanPassword()
  }
}

export function lanAuthHeader(): Record<string, string> {
  const password = getLanPassword();
  return password ? { Authorization: `Basic ${btoa(`:${password}`)}` } : {};
}
