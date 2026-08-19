import { useEffect, useState } from "react";
import { useFacility } from "../LocationContext";
import { api } from "../apiClient";

function emptyPlayer() {
  return { username: "", password: "" };
}

function PlayerFields({ label, player, onChange }) {
  return (
    <label>
      {label}
      <input
        placeholder="username"
        value={player.username}
        onChange={(e) => onChange({ ...player, username: e.target.value })}
        required
      />
      <input
        placeholder="password"
        type="password"
        value={player.password}
        onChange={(e) => onChange({ ...player, password: e.target.value })}
        required
      />
    </label>
  );
}

// The Overview kiosk has no notion of "who's using it" — this modal always
// collects every player's full credentials, verifies them on submit, and
// clears itself immediately after. Nothing is ever persisted client-side.
// `entry === null` means "sign up as a new group" (2 or 4 players, your
// choice — the backend decides active-vs-waiting automatically). A given
// `entry` means "join this specific waiting pair's open slot" (always
// exactly 2 players).
function CourtJoinModal({ court, entry, onClose, onJoined }) {
  const isCreate = entry === null;
  const [groupSize, setGroupSize] = useState(2);
  const [p1, setP1] = useState(emptyPlayer());
  const [p2, setP2] = useState(emptyPlayer());
  const [p3, setP3] = useState(emptyPlayer());
  const [p4, setP4] = useState(emptyPlayer());
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  function clearFields() {
    setP1(emptyPlayer());
    setP2(emptyPlayer());
    setP3(emptyPlayer());
    setP4(emptyPlayer());
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const pair1 = [
        { username: p1.username.trim(), password: p1.password },
        { username: p2.username.trim(), password: p2.password },
      ];
      if (isCreate) {
        const pairs = [pair1];
        if (groupSize === 4) {
          pairs.push([
            { username: p3.username.trim(), password: p3.password },
            { username: p4.username.trim(), password: p4.password },
          ]);
        }
        await api.joinQueue(court.id, pairs);
      } else {
        await api.joinOpenSlot(entry.id, pair1);
      }
      clearFields();
      onJoined();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  function handleCancel() {
    clearFields();
    onClose();
  }

  return (
    <div className="modal-backdrop" onClick={handleCancel}>
      <div className="modal card" onClick={(e) => e.stopPropagation()}>
        <h3>
          {isCreate
            ? `Sign up for ${court.name}${court.active_entry ? " (joins the queue)" : ""}`
            : `Join the waiting pair on ${court.name}`}
        </h3>
        {isCreate && (
          <div className="mode-toggle">
            <button
              type="button"
              className={groupSize === 2 ? "active" : ""}
              onClick={() => setGroupSize(2)}
            >
              2 players
            </button>
            <button
              type="button"
              className={groupSize === 4 ? "active" : ""}
              onClick={() => setGroupSize(4)}
            >
              4 players
            </button>
          </div>
        )}
        <form onSubmit={handleSubmit} className="form">
          <fieldset>
            <legend>{isCreate && groupSize === 4 ? "Pair A" : "Player 1 & 2"}</legend>
            <PlayerFields label="Player 1" player={p1} onChange={setP1} />
            <PlayerFields label="Player 2" player={p2} onChange={setP2} />
          </fieldset>
          {isCreate && groupSize === 4 && (
            <fieldset>
              <legend>Pair B</legend>
              <PlayerFields label="Player 3" player={p3} onChange={setP3} />
              <PlayerFields label="Player 4" player={p4} onChange={setP4} />
            </fieldset>
          )}
          {error && <p className="error">{error}</p>}
          <div className="mode-toggle">
            <button type="submit" disabled={submitting}>
              {submitting ? "Joining…" : "Join"}
            </button>
            <button type="button" onClick={handleCancel}>
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// Collapsed by default so the board stays clean — expands into the same
// two-pair-of-credentials shape used everywhere else, clears on submit or
// cancel, and never keeps anything after that.
function QuickUnsignWidget({ onChanged }) {
  const [expanded, setExpanded] = useState(false);
  const [p1, setP1] = useState(emptyPlayer());
  const [p2, setP2] = useState(emptyPlayer());
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  function reset() {
    setP1(emptyPlayer());
    setP2(emptyPlayer());
    setError(null);
    setExpanded(false);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.quickUnsign(p1.username.trim(), p1.password, p2.username.trim(), p2.password);
      reset();
      onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (!expanded) {
    return (
      <button className="quick-unsign-toggle" onClick={() => setExpanded(true)}>
        Unsign
      </button>
    );
  }

  return (
    <div className="card quick-unsign-card">
      <h3>Unsign</h3>
      <form onSubmit={handleSubmit} className="form">
        <PlayerFields label="Player 1" player={p1} onChange={setP1} />
        <PlayerFields label="Player 2" player={p2} onChange={setP2} />
        {error && <p className="error">{error}</p>}
        <div className="mode-toggle">
          <button type="submit" disabled={submitting}>
            {submitting ? "Unsigning…" : "Unsign"}
          </button>
          <button type="button" onClick={reset}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}

function CourtCard({ court, onPick }) {
  const active = court.active_entry;

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
                {entry.open_slot && (
                  <button onClick={() => onPick({ court, entry })}>Join this pair</button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      {court.is_active && (
        <button onClick={() => onPick({ court, entry: null })}>Sign Up</button>
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
      <div className="overview-toolbar">
        <QuickUnsignWidget onChanged={refresh} />
      </div>
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
