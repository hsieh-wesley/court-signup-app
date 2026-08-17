import { useEffect, useState } from "react";
import { useAuth } from "../AuthContext";
import { api } from "../apiClient";

function EntryCard({ entry, onUnsigned }) {
  const [selected, setSelected] = useState([]);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  function toggle(name) {
    setSelected((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]
    );
  }

  async function handleUnsign() {
    setError(null);
    if (selected.length === 0 || selected.length % 2 !== 0) {
      setError("Pick an even number of players to unsign (2 or 4).");
      return;
    }
    setSubmitting(true);
    try {
      await onUnsigned(entry, selected);
      setSelected([]);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
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
      <ul className="member-list">
        {entry.members.map((m) => (
          <li key={m}>
            <label>
              <input
                type="checkbox"
                checked={selected.includes(m)}
                onChange={() => toggle(m)}
              />
              {m}
            </label>
          </li>
        ))}
      </ul>
      {error && <p className="error">{error}</p>}
      <button onClick={handleUnsign} disabled={submitting}>
        {submitting ? "Unsigning…" : "Unsign selected"}
      </button>
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

  async function handleUnsigned(entry, usernames) {
    await api.unsign(token, entry.id, usernames);
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
