import { useEffect, useRef, useState } from 'react';

// Counts seconds since `active` last became true - resets to 0 whenever it
// goes false then true again. Used to show "12s elapsed…" while waiting on a
// slow local-model call, since these local AI features can take anywhere
// from a couple seconds to over a minute and a static "please wait" message
// gives no sense of whether it's still working.
export function useElapsedSeconds(active: boolean): number {
  const [seconds, setSeconds] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (active) {
      setSeconds(0);
      intervalRef.current = setInterval(() => setSeconds((s) => s + 1), 1000);
    } else if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [active]);

  return seconds;
}
