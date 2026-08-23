// Single source of truth for "what state is this court in" — reused by
// Overview's CourtCard, the Board's CourtColumn, and Admin's CourtsPanel,
// which each used to derive a similar classification independently.
export function courtStatus(court) {
  if (!court.is_active) return "inactive";
  if (court.active_entry) return "in_play";
  if (court.waiting_entries.length > 0) return "queue";
  return "available";
}

export const COURT_STATUS_LABEL = {
  available: "Available",
  in_play: "In Play",
  queue: "Queue",
  inactive: "Inactive",
};

export const COURT_STATUS_BADGE = {
  available: "success",
  in_play: "accent",
  queue: "warning",
  inactive: "neutral",
};

// Orthogonal to courtStatus() above -- a court can be in any of those 4
// states AND have a reservation window. `blocking` means "inside the
// window right now" (the queue can't be promoted onto the court until
// reservation_end passes).
export function reservationInfo(court) {
  if (!court.reservation_start || !court.reservation_end) return null;
  const start = new Date(court.reservation_start);
  const end = new Date(court.reservation_end);
  const now = new Date();
  return { start, end, blocking: now >= start && now < end };
}
