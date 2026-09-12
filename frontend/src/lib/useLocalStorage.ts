import { useLayoutEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from './api';

function readValue<T>(key: string, initial: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw !== null ? (JSON.parse(raw) as T) : initial;
  } catch {
    return initial;
  }
}

// Per-user: every profile keeps its own chart types, page sizes, filters,
// drawer widths, etc, namespaced by the active username, so switching users
// always resets these views to whatever that profile last left them as
// (or the default, the first time) instead of carrying over the previous
// profile's state. Shares the same ['users'] query the nav/switcher already
// run, so this is a cache hit after the first load, not an extra request.
export function useLocalStorage<T>(key: string, initial: T): [T, (v: T) => void] {
  const users = useQuery({ queryKey: ['users'], queryFn: () => api.listUsers() });
  const activeUsername = users.data?.find((u) => u.is_active)?.username ?? 'default';
  const namespacedKey = `${activeUsername}:${key}`;

  const [value, setValue] = useState<T>(() => readValue(namespacedKey, initial));

  // Lazy useState init only runs once, so switching users (which changes
  // namespacedKey without unmounting the component) needs an explicit
  // re-sync - useLayoutEffect (not useEffect) so it happens before paint,
  // avoiding a flash of the previous user's value.
  useLayoutEffect(() => {
    setValue(readValue(namespacedKey, initial));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [namespacedKey]);

  useLayoutEffect(() => {
    try {
      localStorage.setItem(namespacedKey, JSON.stringify(value));
    } catch {
      /* ignore */
    }
  }, [namespacedKey, value]);

  return [value, setValue];
}
