import { useEffect, useState } from "react";
import { useAuth } from "../AuthContext";
import { useFacility } from "../LocationContext";
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
          On {player.current_assignment.location} — {player.current_assignment.court} (
          {player.current_assignment.status})
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
  const [number, setNumber] = useState("");
  const [capacity, setCapacity] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await onCreate({
        number: number ? Number(number) : undefined,
        capacity: capacity ? Number(capacity) : undefined,
      });
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
        <input value={number} onChange={(e) => setNumber(e.target.value)} type="number" min="1" max="100" />
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
  const { locations, selectedLocationId, setSelectedLocationId } = useFacility();
  const [courts, setCourts] = useState([]);
  const [error, setError] = useState(null);

  async function refresh() {
    if (!selectedLocationId) return;
    setCourts(await api.getCourts(selectedLocationId));
  }

  useEffect(() => {
    refresh();
  }, [selectedLocationId]);

  async function handleCreate(data) {
    await adminApi.createCourt(token, { locationId: selectedLocationId, ...data });
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
      <label>
        Managing location
        <select value={selectedLocationId || ""} onChange={(e) => setSelectedLocationId(e.target.value)}>
          {locations.map((loc) => (
            <option key={loc.id} value={loc.id}>
              {loc.name}
            </option>
          ))}
        </select>
      </label>
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

function AddLocationForm({ onCreate }) {
  const [name, setName] = useState("");
  const [courtCount, setCourtCount] = useState("10");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await onCreate({ name, courtCount: Number(courtCount) || 10 });
      setName("");
      setCourtCount("10");
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="form">
      <label>
        Location name
        <input value={name} onChange={(e) => setName(e.target.value)} required />
      </label>
      <label>
        Number of courts (1-100, default 10)
        <input
          value={courtCount}
          onChange={(e) => setCourtCount(e.target.value)}
          type="number"
          min="1"
          max="100"
        />
      </label>
      {error && <p className="error">{error}</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? "Adding…" : "Add Location"}
      </button>
    </form>
  );
}

function LocationCard({ location, onAction }) {
  const [countInput, setCountInput] = useState(String(location.court_count));

  return (
    <div className="card">
      <h3>
        {location.name}
        {!location.is_active && <span className="badge">Deactivated</span>}
      </h3>
      <p className="muted">
        {location.active_court_count} active / {location.court_count} total courts
      </p>
      <div className="mode-toggle">
        <input
          value={countInput}
          onChange={(e) => setCountInput(e.target.value)}
          type="number"
          min="1"
          max="100"
          style={{ width: "5rem" }}
        />
        <button onClick={() => onAction("setCount", location, Number(countInput))}>
          Set court count
        </button>
      </div>
      <div className="mode-toggle">
        {location.is_active ? (
          <button onClick={() => onAction("deactivate", location)}>Deactivate</button>
        ) : (
          <button onClick={() => onAction("activate", location)}>Reactivate</button>
        )}
      </div>
    </div>
  );
}

function LocationsPanel() {
  const { token } = useAuth();
  const { locations: publicLocations } = useFacility();
  const [locations, setLocations] = useState([]);
  const [error, setError] = useState(null);

  async function refresh() {
    setLocations(await adminApi.listLocations(token));
  }

  useEffect(() => {
    refresh();
  }, [publicLocations.length]);

  async function handleCreate(data) {
    await adminApi.createLocation(token, data);
    await refresh();
  }

  async function handleAction(action, location, count) {
    try {
      if (action === "setCount") {
        if (
          count < location.court_count &&
          !confirm(
            `Reduce ${location.name} to ${count} courts? Any occupied courts above that number will be dropped and those players returned to unsigned.`
          )
        ) {
          return;
        }
        await adminApi.setCourtCount(token, location.id, count);
      } else if (action === "deactivate") {
        if (
          !confirm(
            `Deactivate ${location.name}? Occupied courts will be dropped first, and it will stop accepting new signups.`
          )
        )
          return;
        await adminApi.editLocation(token, location.id, { isActive: false });
      } else if (action === "activate") {
        await adminApi.editLocation(token, location.id, { isActive: true });
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
        <h3>Add Location</h3>
        <AddLocationForm onCreate={handleCreate} />
      </div>
      <div className="card-grid">
        {locations.map((loc) => (
          <LocationCard key={loc.id} location={loc} onAction={handleAction} />
        ))}
      </div>
    </div>
  );
}

function HistoryPanel() {
  const { token } = useAuth();
  const { locations } = useFacility();
  const [logins, setLogins] = useState([]);
  const [activity, setActivity] = useState([]);
  const [locationFilter, setLocationFilter] = useState("");
  const [usernameFilter, setUsernameFilter] = useState("");
  const [eventTypeFilter, setEventTypeFilter] = useState("");

  async function refresh() {
    const filters = { location_id: locationFilter || undefined, username: usernameFilter || undefined };
    setLogins(await adminApi.getLoginHistory(token, filters));
    setActivity(
      await adminApi.getCourtActivityHistory(token, {
        ...filters,
        event_type: eventTypeFilter || undefined,
      })
    );
  }

  useEffect(() => {
    refresh();
  }, [locationFilter, usernameFilter, eventTypeFilter]);

  return (
    <div>
      <div className="form">
        <label>
          Location
          <select value={locationFilter} onChange={(e) => setLocationFilter(e.target.value)}>
            <option value="">All</option>
            {locations.map((loc) => (
              <option key={loc.id} value={loc.id}>
                {loc.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Username
          <input value={usernameFilter} onChange={(e) => setUsernameFilter(e.target.value)} />
        </label>
        <label>
          Event type (court activity only)
          <select value={eventTypeFilter} onChange={(e) => setEventTypeFilter(e.target.value)}>
            <option value="">All</option>
            <option value="pair_queued">Pair queued</option>
            <option value="pair_activated">Pair activated</option>
            <option value="open_slot_joined">Open slot joined</option>
            <option value="pair_ended">Pair ended</option>
            <option value="court_dropped">Court dropped</option>
            <option value="court_deactivated">Court deactivated</option>
            <option value="court_reactivated">Court reactivated</option>
          </select>
        </label>
      </div>

      <h3>Logins</h3>
      <table className="history-table">
        <thead>
          <tr>
            <th>When</th>
            <th>Username</th>
            <th>Location</th>
          </tr>
        </thead>
        <tbody>
          {logins.map((row) => (
            <tr key={row.id}>
              <td>{new Date(row.created_at).toLocaleString()}</td>
              <td>{row.username}</td>
              <td>{row.location_name}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Court Activity</h3>
      <table className="history-table">
        <thead>
          <tr>
            <th>When</th>
            <th>Event</th>
            <th>Location</th>
            <th>Court</th>
            <th>Players</th>
            <th>Actor</th>
          </tr>
        </thead>
        <tbody>
          {activity.map((row) => (
            <tr key={row.id}>
              <td>{new Date(row.created_at).toLocaleString()}</td>
              <td>
                {row.event_type}
                {row.reason ? ` (${row.reason})` : ""}
              </td>
              <td>{row.location_name}</td>
              <td>{row.court_number}</td>
              <td>
                {[row.player_1_username, row.player_2_username].filter(Boolean).join(" & ")}
              </td>
              <td>{row.actor_username || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
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
        <button className={tab === "locations" ? "active" : ""} onClick={() => setTab("locations")}>
          Locations
        </button>
        <button className={tab === "history" ? "active" : ""} onClick={() => setTab("history")}>
          History
        </button>
      </div>
      {tab === "users" && <UsersPanel />}
      {tab === "courts" && <CourtsPanel />}
      {tab === "locations" && <LocationsPanel />}
      {tab === "history" && <HistoryPanel />}
    </div>
  );
}
