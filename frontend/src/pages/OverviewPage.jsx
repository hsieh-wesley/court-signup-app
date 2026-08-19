import { useEffect, useState } from "react";
import { useFacility } from "../LocationContext";
import { api } from "../apiClient";

// The Overview kiosk has no notion of "who's using it" — this modal always
// collects both players' full credentials, verifies them on submit, and
// clears itself immediately after. Nothing is ever persisted client-side.
function CourtJoinModal({ court, entry, onClose, onJoined }) {
  const [p1Username, setP1Username] = useState("");
  const [p1Password, setP1Password] = useState("");
  const [p2Username, setP2Username] = useState("");
  const [p2Password, setP2Password] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const credentials = [
        { username: p1Username.trim(), password: p1Password },
        { username: p2Username.trim(), password: p2Password },
      ];
      if (entry) {
        await api.joinOpenSlot(entry.id, credentials);
      } else {
        await api.joinQueue(court.id, [credentials]);
      }
      // Clear immediately — success or not, nothing about who typed this
      // should linger once the dialog is done with it.
      setP1Username("");
      setP1Password("");
      setP2Username("");
      setP2Password("");
      onJoined();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal card" onClick={(e) => e.stopPropagation()}>
        <h3>{entry ? `Join the waiting pair on ${court.name}` : `Start ${court.name}`}</h3>
        <form onSubmit={handleSubmit} className="form">
          <fieldset>
            <legend>Player 1</legend>
            <label>
              Username
              <input value={p1Username} onChange={(e) => setP1Username(e.target.value)} required />
            </label>
            <label>
              Password
              <input
                type="password"
                value={p1Password}
                onChange={(e) => setP1Password(e.target.value)}
                required
              />
            </label>
          </fieldset>
          <fieldset>
            <legend>Player 2</legend>
            <label>
              Username
              <input value={p2Username} onChange={(e) => setP2Username(e.target.value)} required />
            </label>
            <label>
              Password
              <input
                type="password"
                value={p2Password}
                onChange={(e) => setP2Password(e.target.value)}
                required
              />
            </label>
          </fieldset>
          {error && <p className="error">{error}</p>}
          <div className="mode-toggle">
            <button type="submit" disabled={submitting}>
              {submitting ? "Joining…" : "Join"}
            </button>
            <button type="button" onClick={onClose}>
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function CourtCard({ court, onPick }) {
  const active = court.active_entry;
  const openWaiting = court.waiting_entries.find((e) => e.open_slot);

  function joinTarget() {
    if (!active) return { court, entry: null };
    if (openWaiting) return { court, entry: openWaiting };
    return null;
  }

  const target = joinTarget();

  return (
    <div className="card">
      <h3>
        {court.name}
        {!court.is_active && <span className="badge">Deactivated</span>}
      </h3>
      {active ? (
        <div>
          <p className="muted">
            {active.seconds_remaining != null
              ? `${Math.ceil(active.seconds_remaining / 60)} min remaining`
              : "In progress"}
          </p>
          <ul className="pair-list">
            {active.pairs.map((pair) => (
              <li key={pair.id}>
                <span>{pair.players.join(" & ")}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="muted">Open</p>
      )}
      {court.waiting_entries.length > 0 && (
        <>
          <h4>Waiting</h4>
          <ul className="pair-list">
            {court.waiting_entries.map((entry) => (
              <li key={entry.id}>
                <span>
                  {entry.pairs.map((p) => p.players.join(" & ")).join(" + ")}
                  {entry.open_slot && <span className="badge">Open slot</span>}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      {court.is_active && target && (
        <button onClick={() => onPick(target)}>
          {target.entry ? "Join this pair" : "Start this court"}
        </button>
      )}
    </div>
  );
}

export default function OverviewPage() {
  const { selectedLocationId, selectedLocation } = useFacility();
  const [courts, setCourts] = useState([]);
  const [modalTarget, setModalTarget] = useState(null);

  async function refresh() {
    if (!selectedLocationId) return;
    const data = await api.getCourts(selectedLocationId);
    setCourts(data);
  }

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [selectedLocationId]);

  if (!selectedLocation) {
    return (
      <div className="page">
        <p className="muted">Loading facility…</p>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="card-grid">
        {courts.map((court) => (
          <CourtCard key={court.id} court={court} onPick={setModalTarget} />
        ))}
      </div>
      {modalTarget && (
        <CourtJoinModal
          court={modalTarget.court}
          entry={modalTarget.entry}
          onClose={() => setModalTarget(null)}
          onJoined={refresh}
        />
      )}
    </div>
  );
}
