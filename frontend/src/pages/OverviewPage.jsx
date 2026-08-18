import { useEffect, useState } from "react";
import { useAuth } from "../AuthContext";
import { useFacility } from "../LocationContext";
import { api } from "../apiClient";

function CourtJoinModal({ court, entry, onClose, onJoined }) {
  const { token, username, sessionLocationId, login } = useAuth();
  const { selectedLocationId } = useFacility();
  const authenticatedHere = !!token && String(sessionLocationId) === String(selectedLocationId);

  const [selfUsername, setSelfUsername] = useState(username || "");
  const [selfPassword, setSelfPassword] = useState("");
  const [partnerUsername, setPartnerUsername] = useState("");
  const [partnerPassword, setPartnerPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      let activeToken = token;
      let activeUsername = username;
      if (!authenticatedHere) {
        const data = await login(selfUsername.trim(), selfPassword, selectedLocationId);
        activeToken = data.token;
        activeUsername = data.username;
      }
      const credentials = [
        { username: activeUsername },
        { username: partnerUsername.trim(), password: partnerPassword },
      ];
      if (entry) {
        await api.joinOpenSlot(activeToken, entry.id, credentials);
      } else {
        await api.joinQueue(activeToken, court.id, [credentials]);
      }
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
          {!authenticatedHere ? (
            <>
              <label>
                Your username
                <input
                  value={selfUsername}
                  onChange={(e) => setSelfUsername(e.target.value)}
                  required
                />
              </label>
              <label>
                Your password
                <input
                  type="password"
                  value={selfPassword}
                  onChange={(e) => setSelfPassword(e.target.value)}
                  required
                />
              </label>
            </>
          ) : (
            <p className="muted">Signed in as {username}</p>
          )}
          <label>
            Partner's username
            <input
              value={partnerUsername}
              onChange={(e) => setPartnerUsername(e.target.value)}
              required
            />
          </label>
          <label>
            Partner's password
            <input
              type="password"
              value={partnerPassword}
              onChange={(e) => setPartnerPassword(e.target.value)}
              required
            />
          </label>
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

function CourtCard({ court, myUsername, onPick, onUnsign }) {
  const active = court.active_entry;
  const openWaiting = court.waiting_entries.find((e) => e.open_slot);

  function pairContainsMe(pair) {
    return myUsername && pair.players.includes(myUsername);
  }

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
                <span>
                  {pair.players.join(" & ")}
                  {pairContainsMe(pair) && <span className="badge">You</span>}
                </span>
                {pairContainsMe(pair) && (
                  <button onClick={() => onUnsign(active.id, pair.id)}>Unsign</button>
                )}
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
                {entry.pairs.some(pairContainsMe) && (
                  <button
                    onClick={() =>
                      onUnsign(entry.id, entry.pairs.find(pairContainsMe).id)
                    }
                  >
                    Unsign
                  </button>
                )}
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
  const { token, username } = useAuth();
  const { selectedLocationId, selectedLocation } = useFacility();
  const [courts, setCourts] = useState([]);
  const [modalTarget, setModalTarget] = useState(null);
  const [error, setError] = useState(null);

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

  async function handleUnsign(entryId, pairId) {
    setError(null);
    try {
      await api.unsignPair(token, entryId, pairId);
      await refresh();
    } catch (err) {
      setError(err.message);
    }
  }

  if (!selectedLocation) {
    return (
      <div className="page">
        <p className="muted">Loading facility…</p>
      </div>
    );
  }

  return (
    <div className="page">
      {error && <p className="error">{error}</p>}
      <div className="card-grid">
        {courts.map((court) => (
          <CourtCard
            key={court.id}
            court={court}
            myUsername={username}
            onPick={setModalTarget}
            onUnsign={handleUnsign}
          />
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
