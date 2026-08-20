import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useFacility } from "../LocationContext";
import { api } from "../apiClient";
import { formatSeconds, useLiveCountdown } from "../timeFormat";

function slotLabel(entry, slotIndex) {
  const pair = entry.pairs.find((p) => p.slot === slotIndex);
  if (pair) return pair.players.join(" & ");
  if (entry.status === "active") return "Slot closed (timer running)";
  return "Open slot";
}

function CourtColumn({ court }) {
  const active = court.active_entry;
  const remaining = useLiveCountdown(active?.seconds_remaining ?? null, active?.id);

  return (
    <div className="board-column">
      <h2>{court.name}</h2>
      {active ? (
        <div className="board-active">
          <div className="board-timer">{formatSeconds(remaining)}</div>
          <ul>
            <li>{slotLabel(active, 1)}</li>
            <li className={active.pairs.length < 2 ? "muted" : ""}>{slotLabel(active, 2)}</li>
          </ul>
        </div>
      ) : (
        <p className="muted">Court open</p>
      )}
      <h3>Queue</h3>
      {court.waiting_entries.length === 0 && <p className="muted">No one waiting</p>}
      <ol>
        {court.waiting_entries.map((entry) => (
          <li key={entry.id}>
            {entry.pairs.map((p) => p.players.join(" & ")).join(", ")}
            {entry.open_slot && <span className="badge">Open slot</span>}
          </li>
        ))}
      </ol>
    </div>
  );
}

export default function BoardPage() {
  // A TV/kiosk display can bookmark ?location_id=N directly (independent
  // of whatever an interactive player's browser has selected); otherwise
  // it falls back to the shared facility selection.
  const [searchParams] = useSearchParams();
  const urlLocationId = searchParams.get("location_id");
  const { selectedLocationId, selectedLocation, locations } = useFacility();
  const locationId = urlLocationId || selectedLocationId;
  const [courts, setCourts] = useState([]);

  useEffect(() => {
    async function refresh() {
      const data = await api.getCourts(locationId);
      setCourts(data);
    }
    refresh();
    const interval = setInterval(refresh, 7000);
    return () => clearInterval(interval);
  }, [locationId]);

  const locationName = urlLocationId
    ? locations.find((l) => String(l.id) === String(urlLocationId))?.name
    : selectedLocation?.name;

  return (
    <div className="board">
      {locationName && <h1 className="board-title">{locationName}</h1>}
      <div className="board-columns">
        {courts.map((court) => (
          <CourtColumn key={court.id} court={court} />
        ))}
      </div>
    </div>
  );
}
