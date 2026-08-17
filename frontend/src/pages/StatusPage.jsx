import { useEffect, useState } from "react";
import { useAuth } from "../AuthContext";
import { api } from "../apiClient";

const PAIR_LABELS = ["Pair A", "Pair B"];

function EntryCard({ entry, onUnsigned }) {
  const [error, setError] = useState(null);
  const [submittingPairId, setSubmittingPairId] = useState(null);

  async function handleUnsign(pair) {
    setError(null);
    setSubmittingPairId(pair.id);
    try {
      await onUnsigned(entry, pair.id);
    } catch (err) {
      setError(err.message);
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
      {error && <p className="error">{error}</p>}
    </div>
  );
}

export default function StatusPage() {
  const { token } = useAuth();
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    const data = await api.getMyStatus(token);
    setEntries(data);
    setLoading(false);
  }

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [token]);

  async function handleUnsigned(entry, pairId) {
    await api.unsignPair(token, entry.id, pairId);
    await refresh();
  }

  return (
    <div className="page">
      <h1>My status</h1>
      {loading && <p>Loading…</p>}
      {!loading && entries.length === 0 && <p className="muted">You're not in any queues.</p>}
      <div className="card-grid">
        {entries.map((entry) => (
          <EntryCard key={entry.id} entry={entry} onUnsigned={handleUnsigned} />
        ))}
      </div>
    </div>
  );
}
