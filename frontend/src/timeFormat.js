import { useEffect, useState } from "react";

// Seeds from `seconds` (the API's live-computed value) and ticks it down
// locally once per second, resyncing whenever a fresh poll changes
// `seconds` or `key` (e.g. a different active entry). Same pattern
// BoardPage's CourtColumn originated, now shared everywhere a court's
// remaining time is shown live.
export function useLiveCountdown(seconds, key) {
  const [remaining, setRemaining] = useState(seconds ?? null);

  useEffect(() => {
    setRemaining(seconds ?? null);
    if (seconds == null) return;
    const tick = setInterval(() => {
      setRemaining((r) => (r != null && r > 0 ? r - 1 : 0));
    }, 1000);
    return () => clearInterval(tick);
  }, [key, seconds]);

  return remaining;
}

export function formatSeconds(total) {
  if (total == null) return null;
  const m = Math.floor(total / 60)
    .toString()
    .padStart(2, "0");
  const s = Math.floor(total % 60)
    .toString()
    .padStart(2, "0");
  return `${m}:${s}`;
}
