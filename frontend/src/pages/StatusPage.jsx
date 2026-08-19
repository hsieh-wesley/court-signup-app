import { useState } from "react";
import { useFacility } from "../LocationContext";
import { api } from "../apiClient";

const PAIR_LABELS = ["Pair A", "Pair B"];

function EntryCard({ entry, onUnsign }) {
  const [submittingPairId, setSubmittingPairId] = useState(null);

  async function handleUnsign(pair) {
    setSubmittingPairId(pair.id);
    try {
      await onUnsign(entry, pair.id);
    } finally {
      setSubmittingPairId(null);
    }
  }

  return (
    <div className="card">
      <h3>
        {entry.court} — {entry.status === "active" ? "On court now" : "Waiting"}
      </h3>
      {entry.status === "active" && entry.seconds_remaining != null && (
        <p className="muted">{Math.ceil(entry.seconds_remaining / 60)} min remaining</p>
      )}
      <ul className="pair-list">
        {entry.pairs.map((pair, i) => (
          <li key={pair.id}>
            <span>
              {PAIR_LABELS[i] || `Pair ${i + 1}`}: {pair.players.join(" & ")}
            </span>
            <button onClick={() => handleUnsign(pair)} disabled={submittingPairId === pair.id}>
              {submittingPairId === pair.id ? "Unsigning…" : "Unsign this pair"}
            </button>
          </li>
        ))}
        {entry.open_slot && (
          <li className="muted">Open slot — waiting for a pair to join</li>
        )}
      </ul>
    </div>
  );
}

// My Status is a one-shot credential check, not a logged-in view — the
// public kiosk never remembers who looked this up. Credentials are held
// only in this component's local state for the duration of the lookup, so
// unsign buttons can resubmit them without asking twice; refreshing the
// page or navigating away forgets them completely.
export default function StatusPage() {
  const { selectedLocationId } = useFacility();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [checkedCredentials, setCheckedCredentials] = useState(null);
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function refresh(creds) {
    const data = await api.checkStatus(creds.username, creds.password, selectedLocationId);
    setEntries(data);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const creds = { username: username.trim(), password };
      await refresh(creds);
      setCheckedCredentials(creds);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
      setPassword("");
    }
  }

  async function handleUnsign(entry, pairId) {
    await api.unsignPair(entry.id, pairId, checkedCredentials.username, checkedCredentials.password);
    await refresh(checkedCredentials);
  }

  function handleDone() {
    setCheckedCredentials(null);
    setEntries(null);
    setUsername("");
    setPassword("");
  }

  if (!checkedCredentials) {
    return (
      <div className="page page-narrow">
        <h1>My status</h1>
        <p className="muted">Enter your username and password to check your current court/queue status.</p>
        <form onSubmit={handleSubmit} className="form">
          <label>
            Username
            <input value={username} onChange={(e) => setUsername(e.target.value)} required />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          {error && <p className="error">{error}</p>}
          <button type="submit" disabled={submitting}>
            {submitting ? "Checking…" : "Check status"}
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="page">
      <h1>My status — {checkedCredentials.username}</h1>
      {entries.length === 0 && <p className="muted">You're not in any queues.</p>}
      <div className="card-grid">
        {entries.map((entry) => (
          <EntryCard key={entry.id} entry={entry} onUnsign={handleUnsign} />
        ))}
      </div>
      <button onClick={handleDone}>Done</button>
    </div>
  );
}
