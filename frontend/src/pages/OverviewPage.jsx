import { useEffect, useMemo, useState } from "react";
import { UserMinus } from "lucide-react";
import { ALL_LOCATIONS, useFacility } from "../LocationContext";
import { api } from "../apiClient";
import { formatSeconds, useLiveCountdown } from "../timeFormat";
import { courtStatus, COURT_STATUS_BADGE, COURT_STATUS_LABEL, reservationInfo } from "../courtStatus";

function formatWindow(info) {
  const fmt = (d) =>
    d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  return `${fmt(info.start)} – ${fmt(info.end)}`;
}
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
  const remaining = useLiveCountdown(active?.paused ? null : active?.seconds_remaining ?? null, active?.id);
  const status = courtStatus(court);
  const info = reservationInfo(court);

  return (
    <div className="card">
      <div className="court-card-header">
        <h3 style={{ margin: 0 }}>{court.name}</h3>
        <Badge status={COURT_STATUS_BADGE[status]}>{COURT_STATUS_LABEL[status]}</Badge>
      </div>

      {info && (
        <p className="muted" style={{ fontSize: "var(--font-size-sm)" }}>
          {info.blocking ? "Reserved now" : "Reserved"} {formatWindow(info)}
        </p>
      )}

      {active ? (
        <div>
          {active.paused && <div className="court-timer">Paused</div>}
          {!active.paused && remaining != null && <div className="court-timer">{formatSeconds(remaining)}</div>}
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

// No dropdown on this page itself — which facility it shows is set by
// admin from the Admin console (LocationSwitcher there), not picked by
// whoever's standing at the kiosk. Customers on-site should only ever
// see (and sign up for) courts at their actual physical location, so a
// specific selection shows just that facility; "All Locations" (admin's
// choice, not the default assumption for a real kiosk) shows every
// active facility combined, grouped by location heading.
export default function OverviewPage() {
  const { selectedLocationId } = useFacility();
  const [courts, setCourts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalTarget, setModalTarget] = useState(null);

  async function refresh() {
    const data = await api.getCourts(selectedLocationId === ALL_LOCATIONS ? undefined : selectedLocationId);
    setCourts(data);
    setLoading(false);
  }

  useEffect(() => {
    setLoading(true);
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [selectedLocationId]);

  const groups = useMemo(() => {
    const byLocation = new Map();
    for (const court of courts) {
      if (!byLocation.has(court.location)) byLocation.set(court.location, []);
      byLocation.get(court.location).push(court);
    }
    return [...byLocation.entries()];
  }, [courts]);

  return (
    <div className="page">
      <div className="overview-toolbar">
        <QuickUnsignWidget onChanged={refresh} />
      </div>
      {loading ? (
        <p className="loading-state">Loading courts…</p>
      ) : courts.length === 0 ? (
        <p className="empty-state">No courts configured yet.</p>
      ) : (
        groups.map(([locationName, locationCourts]) => (
          <div key={locationName}>
            {groups.length > 1 && <h2 className="overview-location-heading">{locationName}</h2>}
            <div className="card-grid">
              {locationCourts.map((court) => (
                <CourtCard key={court.id} court={court} onPick={setModalTarget} />
              ))}
            </div>
          </div>
        ))
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
