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

// Admin's password-free equivalent of Join This Pair / Sign Up — plain
// usernames only, no credentials. `size` is 2 (fill one open slot) or a
// tab-selectable 2/4 (start a whole new group).
// A plain text input would let admin typo a username that then fails on
// submit — this narrows to matching real accounts as you type, so a
// name can only be picked, never mistyped. Filters client-side (the
// player list is small enough per facility) rather than round-tripping
// to the server on every keystroke.
function UsernameAutocomplete({ value, onChange, usernames, placeholder }) {
  const [open, setOpen] = useState(false);

  const matches = useMemo(() => {
    const term = value.trim().toLowerCase();
    if (!term) return [];
    return usernames.filter((u) => u.toLowerCase().includes(term)).slice(0, 8);
  }, [value, usernames]);

  return (
    <div className="username-autocomplete">
      <input
        placeholder={placeholder}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        autoComplete="off"
        required
        style={{ maxWidth: "10rem" }}
      />
      {open && matches.length > 0 && (
        <ul className="username-autocomplete-list">
          {matches.map((u) => (
            <li key={u}>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onChange(u);
                  setOpen(false);
                }}
              >
                {u}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function UsernamesForm({ size, allowGroupSize, knownUsernames, onSubmit, submitLabel }) {
  const [groupSize, setGroupSize] = useState(size || 2);
  const [fields, setFields] = useState(["", "", "", ""]);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const activeSize = allowGroupSize ? groupSize : size;

  function setField(i, value) {
    setFields((f) => f.map((v, idx) => (idx === i ? value : v)));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const names = fields.slice(0, activeSize).map((u) => u.trim());
      await onSubmit(names);
      setFields(["", "", "", ""]);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="form">
      {allowGroupSize && (
        <div className="tabs tabs-segmented">
          <button type="button" className={groupSize === 2 ? "active" : ""} onClick={() => setGroupSize(2)}>
            2 players
          </button>
          <button type="button" className={groupSize === 4 ? "active" : ""} onClick={() => setGroupSize(4)}>
            4 players
          </button>
        </div>
      )}
      <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
        {Array.from({ length: activeSize }).map((_, i) => (
          <UsernameAutocomplete
            key={i}
            placeholder={`Player ${i + 1} username`}
            value={fields[i]}
            onChange={(v) => setField(i, v)}
            usernames={knownUsernames}
          />
        ))}
      </div>
      {error && <p className="error">{error}</p>}
      <button type="submit" className="btn btn-primary btn-sm" disabled={submitting}>
        {submitting ? "Working…" : submitLabel}
      </button>
    </form>
  );
}

function MoveToControl({ entryId, otherCourts, onMove }) {
  const [targetCourtId, setTargetCourtId] = useState("");
  const [error, setError] = useState(null);
  if (!otherCourts.length) return null;

  async function handleMove() {
    setError(null);
    try {
      await onMove(entryId, targetCourtId);
      setTargetCourtId("");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "var(--space-1)" }}>
      <select
        value={targetCourtId}
        onChange={(e) => setTargetCourtId(e.target.value)}
        aria-label="Move to court"
      >
        <option value="">Move to…</option>
        {otherCourts.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>
      <button type="button" className="btn btn-secondary btn-sm" disabled={!targetCourtId} onClick={handleMove}>
        Move
      </button>
      {error && <span className="error">{error}</span>}
    </span>
  );
}

function CourtManageModal({ court, allCourts, knownUsernames, onClose, onAction }) {
  const allPairs = [
    ...(court.active_entry ? court.active_entry.pairs.map((p) => ({ ...p, entryId: court.active_entry.id })) : []),
  ];
  const otherCourts = allCourts.filter((c) => c.id !== court.id && c.is_active);

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
              <span style={{ display: "flex", alignItems: "center", gap: "var(--space-1)", flexWrap: "wrap" }}>
                {pair.players.map((username) => (
                  <RemoveButton
                    key={username}
                    username={username}
                    onRemove={() => onAction("removePlayer", court, username)}
                  />
                ))}
                <MoveToControl
                  entryId={pair.entryId}
                  otherCourts={otherCourts}
                  onMove={(entryId, targetCourtId) => onAction("move", court, { entryId, targetCourtId })}
                />
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
                <MoveToControl
                  entryId={entry.id}
                  otherCourts={otherCourts}
                  onMove={(entryId, targetCourtId) => onAction("move", court, { entryId, targetCourtId })}
                />
              </span>
              {entry.open_slot && (
                <UsernamesForm
                  size={2}
                  knownUsernames={knownUsernames}
                  submitLabel="Fill Slot"
                  onSubmit={(usernames) => onAction("joinOpenSlot", court, { entryId: entry.id, usernames })}
                />
              )}
            </li>
          ))}
        </ol>
      )}

      {court.is_active && (
        <>
          <h4>Add a group directly (no password needed)</h4>
          <UsernamesForm
            allowGroupSize
            knownUsernames={knownUsernames}
            submitLabel="Add to Court"
            onSubmit={(usernames) => onAction("addGroup", court, { usernames })}
          />
        </>
      )}

      <div className="button-row" style={{ marginTop: "var(--space-4)" }}>
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
  const [knownUsernames, setKnownUsernames] = useState([]);

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

  // For the Manage modal's username autocomplete — every account that
  // could actually be added to a court right now (has a working login).
  useEffect(() => {
    if (!locationId) return;
    adminApi.listPlayers(token, locationId).then((players) => {
      setKnownUsernames(
        players.filter((p) => p.has_login && p.login_active).map((p) => p.username)
      );
    });
  }, [locationId, token]);

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

  // addGroup/joinOpenSlot/move each have their own inline error display
  // right next to their control (UsernamesForm / MoveToControl) — their
  // errors bubble there instead of also flashing the panel-level banner,
  // which would be invisible anyway while the Manage modal covers it.
  // removePlayer/drop/deactivate have no per-action display, so the
  // banner (shown after the modal closes, or for removePlayer's inline
  // confirm) is the only place those show an error.
  async function handleAction(action, court, payload) {
    setError(null);
    if (action === "addGroup") {
      await adminApi.addGroupToCourt(token, court.id, payload.usernames);
      await refresh();
      return;
    }
    if (action === "joinOpenSlot") {
      await adminApi.joinOpenSlotAdmin(token, payload.entryId, payload.usernames);
      await refresh();
      return;
    }
    if (action === "move") {
      await adminApi.moveEntry(token, payload.entryId, payload.targetCourtId);
      await refresh();
      return;
    }
    try {
      if (action === "removePlayer") {
        const username = payload;
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

  if (!locationId) {
    return <p className="empty-state">Select a specific facility above to manage its courts.</p>;
  }

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
          allCourts={courts}
          knownUsernames={knownUsernames}
          onClose={() => setManagingCourtId(null)}
          onAction={handleAction}
        />
      )}
    </div>
  );
}
