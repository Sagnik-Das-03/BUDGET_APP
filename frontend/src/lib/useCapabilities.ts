import { useQuery } from '@tanstack/react-query';
import { api } from './api';

// One frontend build serves both the desktop app and the Android read-only
// server (see android_dashboard/server.py) - this is the single source of
// truth for which one is currently talking to us, read off the same
// /api/sync/config request Dashboard.tsx already makes (react-query dedupes
// the ['syncConfig'] key, so calling this from several components costs one
// network request, not several).
export function useCapabilities() {
  const config = useQuery({ queryKey: ['syncConfig'], queryFn: api.syncConfig });
  return {
    readOnly: config.data?.read_only ?? false,
    loaded: config.data !== undefined,
  };
}
