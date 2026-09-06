import { useEffect, useRef, useState } from 'react';

// Measures how long the most recently completed fetch actually took, in
// seconds - unlike useElapsedSeconds (a live per-second ticking display for
// WHILE a request is in flight), this captures one fixed, precise duration
// once it finishes, and only for a fetch that started during this
// component's current mount. Navigating away and back remounts fresh with a
// cached result already sitting in the QueryClient - there's no way to know
// how long that PRIOR generation took, so this correctly returns null
// rather than showing a misleading "0.0s".
export function useLastDuration(isFetching: boolean): number | null {
  const [duration, setDuration] = useState<number | null>(null);
  const startRef = useRef<number | null>(null);

  useEffect(() => {
    if (isFetching) {
      startRef.current = Date.now();
    } else if (startRef.current !== null) {
      setDuration((Date.now() - startRef.current) / 1000);
      startRef.current = null;
    }
  }, [isFetching]);

  return duration;
}
