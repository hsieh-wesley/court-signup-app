import { useEffect, useState } from "react";
import { UserMinus } from "lucide-react";
import { useFacility } from "../LocationContext";
import { api } from "../apiClient";
import { formatSeconds, useLiveCountdown } from "../timeFormat";
import { courtStatus, COURT_STATUS_BADGE, COURT_STATUS_LABEL } from "../courtStatus";
import Modal from "../components/Modal";
import Badge from "../components/Badge";

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

function GroupSizeTabs({ groupSize, setGroupSize }) {
  return (
    <div className="tabs tabs-segmented">
      <button type="button" className={groupSize === 2 ? "active" : ""} onClick={() => setGroupSize(2)}>
        2 players
      </button>
      <button type="button" className={groupSize === 4 ? "active" : ""} onClick={() => setGroupSize(4)}>
        4 players
      </button>
    </div>
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
    <Modal
      title={
        isCreate
          ? `Sign up for ${court.name}${court.active_entry ? " (joins the queue)" : ""}`
          : `Join the waiting pair on ${court.name}`
      }
      onClose={handleCancel}
    >
      {isCreate && <GroupSizeTabs groupSize={groupSize} setGroupSize={setGroupSize} />}
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
        <div className="button-row">
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? "Joining…" : "Join"}
          </button>
          <button type="button" className="btn btn-secondary" onClick={handleCancel}>
            Cancel
          </button>
        </div>
      </form>
    </Modal>
  );
}

// Collapsed by default so the board stays clean — expands into the same
// 2-vs-4-player credentials shape CourtJoinModal uses for signing up,
// clears on submit or cancel, and never keeps anything after that.
function QuickUnsignWidget({ onChanged }) {
  const [expanded, setExpanded] = useState(false);
  const [groupSize, setGroupSize] = useState(2);
  const [p1, setP1] = useState(emptyPlayer());
  const [p2, setP2] = useState(emptyPlayer());
  const [p3, setP3] = useState(emptyPlayer());
  const [p4, setP4] = useState(emptyPlayer());
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  function reset() {
    setGroupSize(2);
    setP1(emptyPlayer());
    setP2(emptyPlayer());
    setP3(emptyPlayer());
    setP4(emptyPlayer());
    setError(null);
    setExpanded(false);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const pairs = [
        [
          { username: p1.username.trim(), password: p1.password },
          { username: p2.username.trim(), password: p2.password },
        ],
      ];
      if (groupSize === 4) {
        pairs.push([
          { username: p3.username.trim(), password: p3.password },
          { username: p4.username.trim(), password: p4.password },
        ]);
      }
      await api.quickUnsign(pairs);
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
      <button className="btn btn-secondary" onClick={() => setExpanded(true)}>
        <UserMinus size={15} />
        Unsign
      </button>
    );
  }

  return (
    <div className="card quick-unsign-card">
      <h3>Unsign</h3>
      <GroupSizeTabs groupSize={groupSize} setGroupSize={setGroupSize} />
      <form onSubmit={handleSubmit} className="form">
        <fieldset>
          <legend>{groupSize === 4 ? "Pair A" : "Player 1 & 2"}</legend>
          <PlayerFields label="Player 1" player={p1} onChange={setP1} />
          <PlayerFields label="Player 2" player={p2} onChange={setP2} />
        </fieldset>
        {groupSize === 4 && (
          <fieldset>
            <legend>Pair B</legend>
            <PlayerFields label="Player 3" player={p3} onChange={setP3} />
            <PlayerFields label="Player 4" player={p4} onChange={setP4} />
          </fieldset>
        )}
        {error && <p className="error">{error}</p>}
        <div className="button-row">
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? "Unsigning…" : "Unsign"}
          </button>
          <button type="button" className="btn btn-secondary" onClick={reset}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}

function CourtCard({ court, onPick }) {
  const active = court.active_entry;
  const remaining = useLiveCountdown(active?.seconds_remaining ?? null, active?.id);
  const status = courtStatus(court);

  return (
    <div className="card">
      <div className="court-card-header">
        <h3 style={{ margin: 0 }}>{court.name}</h3>
        <Badge status={COURT_STATUS_BADGE[status]}>{COURT_STATUS_LABEL[status]}</Badge>
      </div>

      {active ? (
        <div>
          {remaining != null && <div className="court-timer">{formatSeconds(remaining)}</div>}
          <ul className="pair-list">
            {active.pairs.map((pair) => (
              <li key={pair.id}>
                <span>{pair.players.join(" & ")}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="muted">{court.is_active ? "Open — no one on this court" : "Not accepting signups"}</p>
      )}

      {court.waiting_entries.length > 0 && (
        <>
          <div className="court-section-label">Waiting queue</div>
          <ul className="pair-list">
            {court.waiting_entries.map((entry, i) => (
              <li key={entry.id}>
                <span style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                  <span className="queue-index">{i + 1}</span>
                  {entry.pairs.map((p) => p.players.join(" & ")).join(" + ")}
                  {entry.open_slot && <Badge status="warning">Open slot</Badge>}
                </span>
                {entry.open_slot && (
                  <button className="btn btn-secondary btn-sm" onClick={() => onPick({ court, entry })}>
                    Join this pair
                  </button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      {court.is_active && (
        <button
          className="btn btn-primary"
          style={{ marginTop: "var(--space-4)", width: "100%" }}
          onClick={() => onPick({ court, entry: null })}
        >
          Sign Up
        </button>
      )}
    </div>
  );
}

export default function OverviewPage() {
  const { selectedLocationId, selectedLocation } = useFacility();
  const [courts, setCourts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalTarget, setModalTarget] = useState(null);

  async function refresh() {
    if (!selectedLocationId) return;
    const data = await api.getCourts(selectedLocationId);
    setCourts(data);
    setLoading(false);
  }

  useEffect(() => {
    setLoading(true);
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [selectedLocationId]);

  if (!selectedLocation) {
    return (
      <div className="page">
        <p className="loading-state">Loading facility…</p>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="overview-toolbar">
        <QuickUnsignWidget onChanged={refresh} />
      </div>
      {loading ? (
        <p className="loading-state">Loading courts…</p>
      ) : courts.length === 0 ? (
        <p className="empty-state">No courts configured for this facility yet.</p>
      ) : (
        <div className="card-grid">
          {courts.map((court) => (
            <CourtCard key={court.id} court={court} onPick={setModalTarget} />
          ))}
        </div>
      )}
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
