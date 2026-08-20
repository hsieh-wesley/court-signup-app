import { useEffect, useMemo, useState } from "react";
import { Plus, X } from "lucide-react";
import { useAuth } from "../../AuthContext";
import { adminApi, api } from "../../apiClient";
import Modal from "../../components/Modal";
import Badge from "../../components/Badge";
import { formatSeconds, useLiveCountdown } from "../../timeFormat";
import { courtStatus, COURT_STATUS_BADGE, COURT_STATUS_LABEL } from "../../courtStatus";

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
      <button type="submit" className="btn btn-primary" disabled={submitting}>
        {submitting ? "Adding…" : "Add court"}
      </button>
    </form>
  );
}

function RemoveButton({ username, onRemove }) {
  return (
    <button className="btn btn-ghost btn-sm" onClick={onRemove}>
      <X size={13} />
      {username}
    </button>
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
              <span style={{ display: "flex", gap: "var(--space-1)" }}>
                {pair.players.map((username) => (
                  <RemoveButton
                    key={username}
                    username={username}
                    onRemove={() => onAction("removePlayer", court, username)}
                  />
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
        <ol style={{ paddingLeft: "var(--space-5)", display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
          {court.waiting_entries.map((entry) => (
            <li key={entry.id}>
              <span style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", flexWrap: "wrap" }}>
                {entry.pairs.map((p) => p.players.join(" & ")).join(" + ")}
                {entry.open_slot && <Badge status="warning">Open slot</Badge>}
                {entry.pairs.map((pair) =>
                  pair.players.map((username) => (
                    <RemoveButton
                      key={username}
                      username={username}
                      onRemove={() => onAction("removePlayer", court, username)}
                    />
                  ))
                )}
              </span>
            </li>
          ))}
        </ol>
      )}

      <div className="button-row">
        <button className="btn btn-danger" onClick={() => onAction("drop", court)}>
          Drop Court
        </button>
        {court.is_active ? (
          <button className="btn btn-danger" onClick={() => onAction("deactivate", court)}>
            Deactivate Court
          </button>
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

function CourtRow({ court, onManage }) {
  const active = court.active_entry;
  const remaining = useLiveCountdown(active?.seconds_remaining ?? null, active?.id);
  const status = courtStatus(court);

  return (
    <tr>
      <td>{court.name}</td>
      <td>
        <Badge status={COURT_STATUS_BADGE[status]}>{COURT_STATUS_LABEL[status]}</Badge>
      </td>
      <td>{active ? active.pairs.map((p) => p.players.join("/")).join(" + ") : "—"}</td>
      <td style={{ fontFamily: "var(--font-mono)" }}>{remaining != null ? formatSeconds(remaining) : "—"}</td>
      <td>
        {court.waiting_entries.length
          ? `${court.waiting_entries.length} group${court.waiting_entries.length > 1 ? "s" : ""}`
          : "—"}
      </td>
      <td>
        <button className="btn btn-secondary btn-sm" onClick={onManage}>
          Manage
        </button>
      </td>
    </tr>
  );
}

export default function CourtsPanel({ locationId }) {
  const { token } = useAuth();
  const [courts, setCourts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [addOpen, setAddOpen] = useState(false);
  const [managingCourtId, setManagingCourtId] = useState(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortBy, setSortBy] = useState("number");

  async function refresh() {
    if (!locationId) return;
    const data = await api.getCourts(locationId);
    setCourts(data);
    setLoading(false);
  }

  useEffect(() => {
    setLoading(true);
    refresh();
  }, [locationId]);

  const visible = useMemo(() => {
    return courts
      .filter((c) => statusFilter === "all" || courtStatus(c) === statusFilter)
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
        <label>
          Status
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="all">All</option>
            <option value="available">Available</option>
            <option value="in_play">In Play</option>
            <option value="queue">Queue</option>
            <option value="inactive">Inactive</option>
          </select>
        </label>
        <label>
          Sort
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
            <option value="number">Court Number</option>
            <option value="status">Status</option>
            <option value="queue">Queue Size</option>
            <option value="remaining">Time Remaining</option>
          </select>
        </label>
        <span className="spacer" />
        <button className="btn btn-primary" onClick={() => setAddOpen(true)}>
          <Plus size={15} />
          Add Court
        </button>
      </div>

      {loading ? (
        <p className="loading-state">Loading courts…</p>
      ) : visible.length === 0 ? (
        <p className="empty-state">No courts match these filters.</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
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
                <CourtRow key={court.id} court={court} onManage={() => setManagingCourtId(court.id)} />
              ))}
            </tbody>
          </table>
        </div>
      )}

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
