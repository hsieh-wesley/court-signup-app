import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../AuthContext";
import { adminApi } from "../../apiClient";
import Modal from "../../components/Modal";

const STATUS_LABELS = {
  on_court: "On Court",
  in_queue: "In Queue",
  waiting_room: "Waiting Room",
  not_checked_in: "Not Checked In",
};

function statusText(player) {
  const label = STATUS_LABELS[player.status] || player.status;
  if (player.status === "on_court" && player.court_number != null) {
    return `On Court ${player.court_number}`;
  }
  if (player.status === "in_queue" && player.court_number != null) {
    return `In Queue · Court ${player.court_number}`;
  }
  return label;
}

function loginText(player) {
  if (!player.has_login) return "No login";
  return player.login_active ? "Enabled" : "Disabled";
}

function CredentialBanner({ credentials, onDismiss }) {
  if (!credentials.length) return null;
  return (
    <div className="card">
      <h3>Generated credentials</h3>
      <ul className="pair-list">
        {credentials.map((c) => (
          <li key={c.username}>
            <span>
              {c.username}: <strong>{c.password}</strong>
            </span>
          </li>
        ))}
      </ul>
      <button onClick={onDismiss}>Dismiss</button>
    </div>
  );
}

function AddPlayerForm({ onCreate }) {
  const [displayName, setDisplayName] = useState("");
  const [username, setUsername] = useState("");
  const [enableLogin, setEnableLogin] = useState(true);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await onCreate({ displayName, username: enableLogin ? username : "", enableLogin });
      setDisplayName("");
      setUsername("");
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="form">
      <label>
        Display name
        <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
      </label>
      <label>
        <input
          type="checkbox"
          checked={enableLogin}
          onChange={(e) => setEnableLogin(e.target.checked)}
        />
        {" "}Enable login access
      </label>
      {enableLogin && (
        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} required />
        </label>
      )}
      {error && <p className="error">{error}</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? "Creating…" : "Create player"}
      </button>
    </form>
  );
}

function EditPlayerForm({ player, onSave, onCancel }) {
  const [displayName, setDisplayName] = useState(player.display_name);
  const [username, setUsername] = useState(player.username || "");
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    try {
      await onSave(player.id, {
        displayName,
        username: player.has_login ? username : undefined,
      });
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="form">
      <label>
        Display name
        <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
      </label>
      {player.has_login && (
        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} required />
        </label>
      )}
      {error && <p className="error">{error}</p>}
      <div className="mode-toggle">
        <button type="submit">Save</button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function PlayerRow({ player, onAction, onSave }) {
  const [editing, setEditing] = useState(false);

  if (editing) {
    return (
      <tr>
        <td colSpan={7}>
          <EditPlayerForm
            player={player}
            onSave={async (id, data) => {
              await onSave(id, data);
              setEditing(false);
            }}
            onCancel={() => setEditing(false)}
          />
        </td>
      </tr>
    );
  }

  return (
    <tr>
      <td>
        {player.display_name}
        {!player.is_active && <span className="badge">Archived</span>}
      </td>
      <td>{player.username ? `@${player.username}` : "—"}</td>
      <td>{statusText(player)}</td>
      <td>{loginText(player)}</td>
      <td>
        {player.checked_in_at
          ? new Date(player.checked_in_at).toLocaleTimeString([], {
              hour: "numeric",
              minute: "2-digit",
            })
          : "—"}
      </td>
      <td>{new Date(player.created_at).toLocaleDateString()}</td>
      <td>
        <div className="row-actions">
          <button onClick={() => setEditing(true)}>Edit</button>
          <details className="actions-menu">
            <summary>⋯</summary>
            <div className="actions-menu-list">
              {!player.has_login && (
                <button onClick={() => onAction("addLogin", player)}>Add Login</button>
              )}
              {player.has_login && player.login_active && (
                <>
                  <button onClick={() => onAction("resetPassword", player)}>Reset Password</button>
                  <button onClick={() => onAction("disableLogin", player)}>Disable Login</button>
                </>
              )}
              {player.has_login && !player.login_active && (
                <button onClick={() => onAction("addLogin", player)}>Re-enable Login</button>
              )}
              {player.is_active && (
                <button onClick={() => onAction("deactivate", player)}>Deactivate</button>
              )}
            </div>
          </details>
        </div>
      </td>
    </tr>
  );
}

const SORTERS = {
  name: (a, b) => a.display_name.localeCompare(b.display_name),
  status: (a, b) => (a.status > b.status ? 1 : a.status < b.status ? -1 : 0),
  checkin: (a, b) => new Date(b.checked_in_at || 0) - new Date(a.checked_in_at || 0),
  created: (a, b) => new Date(b.created_at) - new Date(a.created_at),
};

export default function UsersPanel({ locationId }) {
  const { token } = useAuth();
  const [players, setPlayers] = useState([]);
  const [credentials, setCredentials] = useState([]);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortBy, setSortBy] = useState("name");
  const [addOpen, setAddOpen] = useState(false);
  const [testToolsOpen, setTestToolsOpen] = useState(false);

  async function refresh() {
    const data = await adminApi.listPlayers(token, locationId);
    setPlayers(data);
  }

  useEffect(() => {
    refresh();
  }, [locationId]);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return players
      .filter((p) => {
        if (statusFilter !== "all" && p.status !== statusFilter) return false;
        if (!term) return true;
        return (
          p.display_name.toLowerCase().includes(term) ||
          (p.username || "").toLowerCase().includes(term)
        );
      })
      .sort(SORTERS[sortBy]);
  }, [players, search, statusFilter, sortBy]);

  async function handleCreate({ displayName, username, enableLogin }) {
    const payload = await adminApi.createPlayer(token, { displayName, username, enableLogin });
    if (payload.password) {
      setCredentials((c) => [...c, { username: payload.username, password: payload.password }]);
    }
    setAddOpen(false);
    await refresh();
  }

  async function handleBulkTest() {
    const results = await adminApi.createTestPlayers(token, 8);
    setCredentials(results);
    await refresh();
  }

  async function handleSave(playerId, data) {
    await adminApi.editPlayer(token, playerId, data);
    await refresh();
  }

  async function handleAction(action, player) {
    setError(null);
    try {
      if (action === "addLogin") {
        const suggested = player.username || player.display_name.toLowerCase().replace(/\s+/g, "");
        const username = window.prompt("Username for login:", suggested);
        if (!username) return;
        const payload = await adminApi.addLogin(token, player.id, username);
        setCredentials((c) => [...c, { username: payload.username, password: payload.password }]);
      } else if (action === "resetPassword") {
        if (!window.confirm(`Reset ${player.display_name}'s password?`)) return;
        const payload = await adminApi.resetPassword(token, player.id);
        setCredentials((c) => [...c, { username: payload.username, password: payload.password }]);
      } else if (action === "disableLogin") {
        if (!window.confirm(`Disable login for ${player.display_name}?`)) return;
        await adminApi.disableLogin(token, player.id);
      } else if (action === "deactivate") {
        if (!window.confirm(`Deactivate ${player.display_name}? This removes them from any court/queue.`)) return;
        await adminApi.deactivatePlayer(token, player.id);
      }
      await refresh();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div>
      <CredentialBanner credentials={credentials} onDismiss={() => setCredentials([])} />
      {error && <p className="error">{error}</p>}

      <div className="admin-toolbar">
        <input
          placeholder="Search name or username"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="all">All</option>
          <option value="waiting_room">Waiting Room</option>
          <option value="in_queue">In Queue</option>
          <option value="on_court">On Court</option>
          <option value="not_checked_in">Not Checked In</option>
        </select>
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
          <option value="name">Sort: Name</option>
          <option value="status">Sort: Status</option>
          <option value="checkin">Sort: Check-In Time</option>
          <option value="created">Sort: Account Created</option>
        </select>
        <button onClick={() => setAddOpen(true)}>+ Add Player</button>
      </div>

      <table className="history-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Username</th>
            <th>Status</th>
            <th>Login</th>
            <th>Checked In</th>
            <th>Account Created</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((player) => (
            <PlayerRow key={player.id} player={player} onAction={handleAction} onSave={handleSave} />
          ))}
        </tbody>
      </table>

      <details className="dev-tools" open={testToolsOpen} onToggle={(e) => setTestToolsOpen(e.target.open)}>
        <summary>Development/Test Tools</summary>
        <button onClick={handleBulkTest}>Generate 8 Test Players</button>
      </details>

      {addOpen && (
        <Modal title="Add Player" onClose={() => setAddOpen(false)}>
          <AddPlayerForm onCreate={handleCreate} />
        </Modal>
      )}
    </div>
  );
}
