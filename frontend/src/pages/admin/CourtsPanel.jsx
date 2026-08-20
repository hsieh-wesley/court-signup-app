import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../AuthContext";
import { adminApi, api } from "../../apiClient";
import Modal from "../../components/Modal";

function courtStatus(court) {
  if (court.active_entry) return "active";
  if (court.waiting_entries.length > 0) return "queued";
  return "empty";
}

function AddCourtForm({ onCreate }) {
  const [number, setNumber] = useState("");
  const [capacity, setCapacity] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await onCreate({ number: Number(number) || undefined, capacity: Number(capacity) || undefined });
      setNumber("");
      setCapacity("");
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="form">
      <label>
        Court number (optional — next available if blank)
        <input
          type="number"
          min="1"
          max="100"
          value={number}
          onChange={(e) => setNumber(e.target.value)}
        />
      </label>
      <label>
        Capacity (optional)
        <input type="number" min="1" value={capacity} onChange={(e) => setCapacity(e.target.value)} />
      </label>
      {error && <p className="error">{error}</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? "Adding…" : "Add court"}
      </button>
    </form>
  );
}

function CourtManageModal({ court, onClose, onAction }) {
  const allPairs = [
    ...(court.active_entry ? court.active_entry.pairs.map((p) => ({ ...p, entryId: court.active_entry.id })) : []),
  ];

  return (
    <Modal title={`Manage ${court.name}`} onClose={onClose}>
      {!court.is_active && <p className="muted">Deactivated — not accepting signups.</p>}
      <h4>Current group</h4>
      {allPairs.length === 0 ? (
        <p className="muted">No one currently on this court.</p>
      ) : (
        <ul className="pair-list">
          {allPairs.map((pair) => (
            <li key={pair.id}>
              <span>{pair.players.join(" & ")}</span>
              <span>
                {pair.players.map((username) => (
                  <button key={username} onClick={() => onAction("removePlayer", court, username)}>
                    Remove {username}
                  </button>
                ))}
              </span>
            </li>
          ))}
        </ul>
      )}

      <h4>Waiting queue (FIFO order)</h4>
      {court.waiting_entries.length === 0 ? (
        <p className="muted">No one waiting.</p>
      ) : (
        <ol>
          {court.waiting_entries.map((entry) => (
            <li key={entry.id}>
              {entry.pairs.map((p) => p.players.join(" & ")).join(" + ")}
              {entry.open_slot && <span className="badge">Open slot</span>}
              {entry.pairs.map((pair) => (
                <span key={pair.id}>
                  {pair.players.map((username) => (
                    <button key={username} onClick={() => onAction("removePlayer", court, username)}>
                      Remove {username}
                    </button>
                  ))}
                </span>
              ))}
            </li>
          ))}
        </ol>
      )}

      <div className="mode-toggle">
        <button onClick={() => onAction("drop", court)}>Drop Court</button>
        {court.is_active ? (
          <button onClick={() => onAction("deactivate", court)}>Deactivate Court</button>
        ) : (
          <span className="muted">Not accepting signups</span>
        )}
      </div>
    </Modal>
  );
}

const SORTERS = {
  number: (a, b) => a.number - b.number,
  status: (a, b) => courtStatus(a).localeCompare(courtStatus(b)),
  queue: (a, b) => b.waiting_entries.length - a.waiting_entries.length,
  remaining: (a, b) =>
    (a.active_entry?.seconds_remaining ?? Infinity) - (b.active_entry?.seconds_remaining ?? Infinity),
};

export default function CourtsPanel({ locationId }) {
  const { token } = useAuth();
  const [courts, setCourts] = useState([]);
  const [error, setError] = useState(null);
  const [addOpen, setAddOpen] = useState(false);
  const [managingCourtId, setManagingCourtId] = useState(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortBy, setSortBy] = useState("number");

  async function refresh() {
    if (!locationId) return;
    const data = await api.getCourts(locationId);
    setCourts(data);
  }

  useEffect(() => {
    refresh();
  }, [locationId]);

  const visible = useMemo(() => {
    return courts
      .filter((c) => {
        if (statusFilter === "all") return true;
        if (statusFilter === "empty") return courtStatus(c) === "empty";
        if (statusFilter === "active") return courtStatus(c) === "active";
        if (statusFilter === "queued") return c.waiting_entries.length > 0;
        return true;
      })
      .sort(SORTERS[sortBy]);
  }, [courts, statusFilter, sortBy]);

  async function handleCreate(data) {
    await adminApi.createCourt(token, { locationId, ...data });
    setAddOpen(false);
    await refresh();
  }

  async function handleAction(action, court, username) {
    setError(null);
    try {
      if (action === "removePlayer") {
        if (!window.confirm(`Remove ${username} from ${court.name}?`)) return;
        await adminApi.removePlayerFromCourt(token, court.id, username);
      } else if (action === "drop") {
        if (!window.confirm(`Drop everyone from ${court.name}?`)) return;
        await adminApi.dropCourt(token, court.id);
        setManagingCourtId(null);
      } else if (action === "deactivate") {
        if (!window.confirm(`Deactivate ${court.name}? This drops any current occupants.`)) return;
        await adminApi.deactivateCourt(token, court.id);
        setManagingCourtId(null);
      }
      await refresh();
    } catch (err) {
      setError(err.message);
    }
  }

  const managingCourt = courts.find((c) => c.id === managingCourtId);

  return (
    <div>
      {error && <p className="error">{error}</p>}

      <div className="admin-toolbar">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="all">All</option>
          <option value="empty">Empty</option>
          <option value="active">Active</option>
          <option value="queued">Has Queue</option>
        </select>
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
          <option value="number">Sort: Court Number</option>
          <option value="status">Sort: Status</option>
          <option value="queue">Sort: Queue Size</option>
          <option value="remaining">Sort: Time Remaining</option>
        </select>
        <button onClick={() => setAddOpen(true)}>+ Add Court</button>
      </div>

      <table className="history-table">
        <thead>
          <tr>
            <th>Court</th>
            <th>Status</th>
            <th>Current Players</th>
            <th>Time Remaining</th>
            <th>Queue</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((court) => (
            <tr key={court.id}>
              <td>
                {court.name}
                {!court.is_active && <span className="badge">Deactivated</span>}
              </td>
              <td>{court.active_entry ? "On Court" : court.waiting_entries.length ? "Has Queue" : "Empty"}</td>
              <td>
                {court.active_entry
                  ? court.active_entry.pairs.map((p) => p.players.join("/")).join(" + ")
                  : "—"}
              </td>
              <td>
                {court.active_entry?.seconds_remaining != null
                  ? `${Math.ceil(court.active_entry.seconds_remaining / 60)} min`
                  : "—"}
              </td>
              <td>
                {court.waiting_entries.length
                  ? `${court.waiting_entries.length} group${court.waiting_entries.length > 1 ? "s" : ""}`
                  : "—"}
              </td>
              <td>
                <button onClick={() => setManagingCourtId(court.id)}>Manage</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {addOpen && (
        <Modal title="Add Court" onClose={() => setAddOpen(false)}>
          <AddCourtForm onCreate={handleCreate} />
        </Modal>
      )}

      {managingCourt && (
        <CourtManageModal
          court={managingCourt}
          onClose={() => setManagingCourtId(null)}
          onAction={handleAction}
        />
      )}
    </div>
  );
}
