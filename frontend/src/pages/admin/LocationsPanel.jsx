import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../AuthContext";
import { adminApi } from "../../apiClient";
import Modal from "../../components/Modal";

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
          type="number"
          min="1"
          max="100"
          value={courtCount}
          onChange={(e) => setCourtCount(e.target.value)}
        />
      </label>
      {error && <p className="error">{error}</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? "Creating…" : "Create location"}
      </button>
    </form>
  );
}

function LocationManageModal({ location, onClose, onAction }) {
  const [name, setName] = useState(location.name);
  const [countInput, setCountInput] = useState(String(location.court_count));
  const [error, setError] = useState(null);

  async function handleRename(e) {
    e.preventDefault();
    setError(null);
    try {
      await onAction("rename", location, name);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleSetCount(e) {
    e.preventDefault();
    setError(null);
    try {
      await onAction("setCount", location, Number(countInput));
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <Modal title={`Manage ${location.name}`} onClose={onClose}>
      <form onSubmit={handleRename} className="form">
        <label>
          Facility name
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <button type="submit">Rename</button>
      </form>
      <form onSubmit={handleSetCount} className="form">
        <label>
          Court count
          <input
            type="number"
            min="1"
            max="100"
            value={countInput}
            onChange={(e) => setCountInput(e.target.value)}
          />
        </label>
        <button type="submit">Set court count</button>
      </form>
      {error && <p className="error">{error}</p>}
      <div className="mode-toggle">
        {location.is_active ? (
          <button onClick={() => onAction("deactivate", location)}>Deactivate</button>
        ) : (
          <button onClick={() => onAction("activate", location)}>Reactivate</button>
        )}
      </div>
    </Modal>
  );
}

export default function LocationsPanel() {
  const { token, isSuperuser } = useAuth();
  const [locations, setLocations] = useState([]);
  const [error, setError] = useState(null);
  const [addOpen, setAddOpen] = useState(false);
  const [managingId, setManagingId] = useState(null);

  async function refresh() {
    const data = await adminApi.listLocations(token);
    setLocations(data);
  }

  useEffect(() => {
    refresh();
  }, []);

  const sorted = useMemo(() => [...locations].sort((a, b) => a.name.localeCompare(b.name)), [locations]);

  async function handleCreate(data) {
    await adminApi.createLocation(token, data);
    setAddOpen(false);
    await refresh();
  }

  async function handleAction(action, location, arg) {
    setError(null);
    try {
      if (action === "rename") {
        await adminApi.editLocation(token, location.id, { name: arg });
      } else if (action === "setCount") {
        if (arg < location.court_count) {
          if (!window.confirm(`Reduce ${location.name} to ${arg} courts? Occupied courts above that number will be dropped.`)) return;
        }
        await adminApi.setCourtCount(token, location.id, arg);
      } else if (action === "deactivate") {
        if (!window.confirm(`Deactivate ${location.name}? This drops any currently occupied courts.`)) return;
        await adminApi.editLocation(token, location.id, { isActive: false });
        setManagingId(null);
      } else if (action === "activate") {
        await adminApi.editLocation(token, location.id, { isActive: true });
      }
      await refresh();
    } catch (err) {
      setError(err.message);
      throw err;
    }
  }

  const managingLocation = locations.find((l) => l.id === managingId);

  return (
    <div>
      {error && <p className="error">{error}</p>}

      {isSuperuser && (
        <div className="admin-toolbar">
          <button onClick={() => setAddOpen(true)}>+ Add Location</button>
        </div>
      )}

      <table className="history-table">
        <thead>
          <tr>
            <th>Facility</th>
            <th>Courts</th>
            <th>Waiting Room</th>
            <th>In Queue</th>
            <th>On Court</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((location) => (
            <tr key={location.id}>
              <td>{location.name}</td>
              <td>
                {location.active_court_count}/{location.court_count}
              </td>
              <td>{location.waiting_room_count}</td>
              <td>{location.in_queue_count}</td>
              <td>{location.on_court_count}</td>
              <td>
                {location.is_active ? "Active" : <span className="badge">Deactivated</span>}
              </td>
              <td>
                <button onClick={() => setManagingId(location.id)}>Manage</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {addOpen && (
        <Modal title="Add Location" onClose={() => setAddOpen(false)}>
          <AddLocationForm onCreate={handleCreate} />
        </Modal>
      )}

      {managingLocation && (
        <LocationManageModal
          location={managingLocation}
          onClose={() => setManagingId(null)}
          onAction={handleAction}
        />
      )}
    </div>
  );
}
