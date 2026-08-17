import { useEffect, useState } from "react";
import { useAuth } from "../AuthContext";
import { api } from "../apiClient";

export default function JoinPage() {
  const { token, username } = useAuth();
  const [courts, setCourts] = useState([]);
  const [courtId, setCourtId] = useState("");
  const [mode, setMode] = useState("new"); // "new" | "join"

  const [groupSize, setGroupSize] = useState(2);
  const [partner, setPartner] = useState("");
  const [secondPair, setSecondPair] = useState(["", ""]);

  const [selectedEntryId, setSelectedEntryId] = useState("");
  const [joinPartner, setJoinPartner] = useState("");

  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    refreshCourts();
  }, []);

  async function refreshCourts() {
    const data = await api.getCourts();
    setCourts(data);
    setCourtId((current) => current || (data.length ? String(data[0].id) : ""));
  }

  const selectedCourt = courts.find((c) => String(c.id) === courtId);
  const waitingEntries = selectedCourt?.waiting_entries || [];
  const openEntries = waitingEntries
    .map((entry, index) => ({ ...entry, position: index + 1 }))
    .filter((e) => e.open_slot);

  useEffect(() => {
    setSelectedEntryId(openEntries.length ? String(openEntries[0].id) : "");
  }, [courtId, courts]);

  async function handleSubmitNew(e) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    const pairs = [[username, partner.trim()]];
    if (groupSize === 4) pairs.push(secondPair.map((n) => n.trim()));
    if (pairs.some((pair) => pair.some((n) => !n))) {
      setError("Please fill in all partner usernames.");
      return;
    }
    setSubmitting(true);
    try {
      const entry = await api.joinQueue(token, Number(courtId), pairs);
      setSuccess(
        entry.status === "active"
          ? "You're on the court now!"
          : "You're in the queue — check My Status for your position."
      );
      setPartner("");
      setSecondPair(["", ""]);
      await refreshCourts();
    } catch (err) {
      setError(err.message);
      await refreshCourts();
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSubmitJoin(e) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    if (!selectedEntryId) {
      setError("Pick a pair to join.");
      return;
    }
    if (!joinPartner.trim()) {
      setError("Please fill in your partner's username.");
      return;
    }
    setSubmitting(true);
    try {
      await api.joinOpenSlot(token, Number(selectedEntryId), [username, joinPartner.trim()]);
      setSuccess("You've joined the queue position — check My Status.");
      setJoinPartner("");
      await refreshCourts();
    } catch (err) {
      setError(err.message);
      await refreshCourts();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page page-narrow">
      <h1>Join a queue</h1>

      <label>
        Court
        <select value={courtId} onChange={(e) => setCourtId(e.target.value)}>
          {courts.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </label>

      <div className="mode-toggle">
        <button
          type="button"
          className={mode === "new" ? "active" : ""}
          onClick={() => setMode("new")}
        >
          Start a new position
        </button>
        <button
          type="button"
          className={mode === "join" ? "active" : ""}
          onClick={() => setMode("join")}
        >
          Join an existing pair
        </button>
      </div>

      {mode === "new" && (
        <form onSubmit={handleSubmitNew} className="form">
          <label>
            Group size
            <select value={groupSize} onChange={(e) => setGroupSize(Number(e.target.value))}>
              <option value={2}>2 (one pair)</option>
              <option value={4}>4 (two pairs)</option>
            </select>
          </label>

          <label>
            You
            <input value={username} disabled />
          </label>
          <label>
            Your partner
            <input value={partner} onChange={(e) => setPartner(e.target.value)} required />
          </label>

          {groupSize === 4 && (
            <>
              <label>
                Second pair — player 1
                <input
                  value={secondPair[0]}
                  onChange={(e) => setSecondPair([e.target.value, secondPair[1]])}
                  required
                />
              </label>
              <label>
                Second pair — player 2
                <input
                  value={secondPair[1]}
                  onChange={(e) => setSecondPair([secondPair[0], e.target.value])}
                  required
                />
              </label>
            </>
          )}

          {error && <p className="error">{error}</p>}
          {success && <p className="success">{success}</p>}
          <button type="submit" disabled={submitting || !courtId}>
            {submitting ? "Joining…" : "Join queue"}
          </button>
        </form>
      )}

      {mode === "join" && (
        <form onSubmit={handleSubmitJoin} className="form">
          {openEntries.length === 0 ? (
            <p className="muted">No open pairs to join on this court right now.</p>
          ) : (
            <label>
              Pair to join
              <select value={selectedEntryId} onChange={(e) => setSelectedEntryId(e.target.value)}>
                {openEntries.map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    Join {entry.pairs[0].players.join(" & ")} — position {entry.position}
                  </option>
                ))}
              </select>
            </label>
          )}

          <label>
            You
            <input value={username} disabled />
          </label>
          <label>
            Your partner
            <input value={joinPartner} onChange={(e) => setJoinPartner(e.target.value)} required />
          </label>

          {error && <p className="error">{error}</p>}
          {success && <p className="success">{success}</p>}
          <button type="submit" disabled={submitting || !selectedEntryId}>
            {submitting ? "Joining…" : "Join pair"}
          </button>
        </form>
      )}
    </div>
  );
}
