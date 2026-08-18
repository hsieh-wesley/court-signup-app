import { useEffect, useState } from "react";
import { useAuth } from "../AuthContext";
import { adminApi, api } from "../apiClient";

function CredentialBanner({ credentials, onDismiss }) {
  if (!credentials.length) return null;
  return (
    <div className="card">
      <strong>New password{credentials.length > 1 ? "s" : ""} — copy now, won't be shown again:</strong>
      <ul>
        {credentials.map((c) => (
          <li key={c.username}>
            {c.username}: <code>{c.password}</code>
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
        {submitting ? "Adding…" : "Add Player"}
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
      await onSave(player.id, { displayName, username: player.has_login ? username : undefined });
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="form">
      <label>
        Display name
        <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
      </label>
      {player.has_login && (
        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} />
        </label>
      )}
      {error && <p className="error">{error}</p>}
      <button type="submit">Save</button>
      <button type="button" onClick={onCancel}>Cancel</button>
    </form>
  );
}

function PlayerRow({ player, onAction, onSave }) {
  const [editing, setEditing] = useState(false);

  if (editing) {
    return (
      <div className="card">
        <EditPlayerForm
          player={player}
          onSave={async (id, data) => {
            await onSave(id, data);
            setEditing(false);
          }}
          onCancel={() => setEditing(false)}
        />
      </div>
    );
  }

  return (
    <div className="card">
      <h3>
        {player.display_name}
        {!player.is_active && <span className="badge">Archived</span>}
      </h3>
      <p className="muted">
        {player.username ? `@${player.username}` : "no login"}
        {player.has_login && (player.login_active ? " — login enabled" : " — login disabled")}
      </p>
      {player.current_assignment && (
        <p className="muted">
          On {player.current_assignment.court} ({player.current_assignment.status})
        </p>
      )}
      <div className="mode-toggle">
        <button onClick={() => setEditing(true)}>Edit</button>
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
    </div>
  );
}

function UsersPanel() {
  const { token } = useAuth();
  const [players, setPlayers] = useState([]);
  const [credentials, setCredentials] = useState([]);
  const [error, setError] = useState(null);

  async function refresh() {
    setPlayers(await adminApi.listPlayers(token));
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleCreate({ displayName, username, enableLogin }) {
    const result = await adminApi.createPlayer(token, { displayName, username, enableLogin });
    if (result.password) setCredentials([{ username: result.username, password: result.password }]);
    await refresh();
  }

  async function handleBulkTest() {
    setError(null);
    try {
      const results = await adminApi.createTestPlayers(token, 8);
      setCredentials(results.map((r) => ({ username: r.username, password: r.password })));
      await refresh();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleSave(playerId, data) {
    await adminApi.editPlayer(token, playerId, data);
    await refresh();
  }

  async function handleAction(action, player) {
    try {
      if (action === "addLogin") {
        const username = player.username || prompt("Username for this player:", player.display_name.toLowerCase().replace(/\s+/g, ""));
        if (!username) return;
        const result = await adminApi.addLogin(token, player.id, username);
        setCredentials([{ username: result.username, password: result.password }]);
      } else if (action === "resetPassword") {
        if (!confirm(`Reset ${player.display_name}'s password? Their current password will stop working.`)) return;
        const result = await adminApi.resetPassword(token, player.id);
        setCredentials([{ username: result.username, password: result.password }]);
      } else if (action === "disableLogin") {
        if (!confirm(`Disable login for ${player.display_name}? They won't be able to sign in until it's re-enabled.`)) return;
        await adminApi.disableLogin(token, player.id);
      } else if (action === "deactivate") {
        if (!confirm(`Deactivate ${player.display_name}? This removes them from any current court and disables login.`)) return;
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
      <div className="card">
        <h3>Add Player</h3>
        <AddPlayerForm onCreate={handleCreate} />
      </div>
      <p>
        <button onClick={handleBulkTest}>Generate 8 test players</button>
      </p>
      <div className="card-grid">
        {players.map((p) => (
          <PlayerRow key={p.id} player={p} onAction={handleAction} onSave={handleSave} />
        ))}
      </div>
    </div>
  );
}

function AddCourtForm({ onCreate }) {
  const [name, setName] = useState("");
  const [capacity, setCapacity] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await onCreate({ name, capacity: capacity ? Number(capacity) : undefined });
      setName("");
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
        Court name
        <input value={name} onChange={(e) => setName(e.target.value)} required />
      </label>
      <label>
        Capacity (optional)
        <input value={capacity} onChange={(e) => setCapacity(e.target.value)} type="number" min="1" />
      </label>
      {error && <p className="error">{error}</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? "Adding…" : "Add Court"}
      </button>
    </form>
  );
}

function CourtCard({ court, onAction }) {
  const allPairs = [
    ...(court.active_entry ? court.active_entry.pairs.map((p) => ({ ...p, entryId: court.active_entry.id })) : []),
    ...court.waiting_entries.flatMap((e) => e.pairs.map((p) => ({ ...p, entryId: e.id }))),
  ];

  return (
    <div className="card">
      <h3>
        {court.name}
        {!court.is_active && <span className="badge">Deactivated</span>}
      </h3>
      <p className="muted">Capacity {court.capacity}</p>
      {allPairs.length === 0 && <p className="muted">No one currently on this court.</p>}
      <ul className="pair-list">
        {allPairs.map((pair) => (
          <li key={pair.id}>
            <span>{pair.players.join(" & ")}</span>
            {pair.players.map((username) => (
              <button key={username} onClick={() => onAction("removePlayer", court, username)}>
                Remove {username}
              </button>
            ))}
          </li>
        ))}
      </ul>
      <div className="mode-toggle">
        <button onClick={() => onAction("drop", court)}>Drop Court</button>
        {court.is_active ? (
          <button onClick={() => onAction("deactivate", court)}>Deactivate Court</button>
        ) : (
          <span className="muted">Not accepting signups</span>
        )}
      </div>
    </div>
  );
}

function CourtsPanel() {
  const { token } = useAuth();
  const [courts, setCourts] = useState([]);
  const [error, setError] = useState(null);

  async function refresh() {
    setCourts(await api.getCourts());
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleCreate(data) {
    await adminApi.createCourt(token, data);
    await refresh();
  }

  async function handleAction(action, court, username) {
    try {
      if (action === "removePlayer") {
        if (!confirm(`Remove ${username} from ${court.name}?`)) return;
        await adminApi.removePlayerFromCourt(token, court.id, username);
      } else if (action === "drop") {
        if (!confirm(`Drop ${court.name} and return everyone to unsigned status?`)) return;
        await adminApi.dropCourt(token, court.id);
      } else if (action === "deactivate") {
        if (!confirm(`Deactivate ${court.name}? It will stop accepting new signups.`)) return;
        await adminApi.deactivateCourt(token, court.id);
      }
      await refresh();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div>
      {error && <p className="error">{error}</p>}
      <div className="card">
        <h3>Add Court</h3>
        <AddCourtForm onCreate={handleCreate} />
      </div>
      <div className="card-grid">
        {courts.map((c) => (
          <CourtCard key={c.id} court={c} onAction={handleAction} />
        ))}
      </div>
    </div>
  );
}

export default function AdminPage() {
  const [tab, setTab] = useState("users");
  return (
    <div className="page">
      <h1>Admin</h1>
      <div className="mode-toggle">
        <button className={tab === "users" ? "active" : ""} onClick={() => setTab("users")}>
          Users
        </button>
        <button className={tab === "courts" ? "active" : ""} onClick={() => setTab("courts")}>
          Courts
        </button>
      </div>
      {tab === "users" ? <UsersPanel /> : <CourtsPanel />}
    </div>
  );
}
