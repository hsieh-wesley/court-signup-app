import { useEffect, useMemo, useState } from "react";
import { Plus } from "lucide-react";
import { useAuth } from "../../AuthContext";
import { useFacility } from "../../LocationContext";
import { adminApi } from "../../apiClient";
import Modal from "../../components/Modal";
import Badge from "../../components/Badge";

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
      <button type="submit" className="btn btn-primary" disabled={submitting}>
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
        <button type="submit" className="btn btn-secondary btn-sm">
          Rename
        </button>
      </form>
      <form onSubmit={handleSetCount} className="form" style={{ marginTop: "var(--space-4)" }}>
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
        <button type="submit" className="btn btn-secondary btn-sm">
          Set court count
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      <div className="button-row">
        {location.is_active ? (
          <button className="btn btn-danger" onClick={() => onAction("deactivate", location)}>
            Deactivate
          </button>
        ) : (
          <button className="btn btn-primary" onClick={() => onAction("activate", location)}>
            Reactivate
          </button>
        )}
      </div>
    </Modal>
  );
}

export default function LocationsPanel() {
  const { token, isSuperuser } = useAuth();
  const { refreshLocations } = useFacility();
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [addOpen, setAddOpen] = useState(false);
  const [managingId, setManagingId] = useState(null);

  async function refresh() {
    const data = await adminApi.listLocations(token);
    setLocations(data);
    setLoading(false);
  }

  useEffect(() => {
    refresh();
  }, []);

  const sorted = useMemo(() => [...locations].sort((a, b) => a.name.localeCompare(b.name)), [locations]);

  async function handleCreate(data) {
    await adminApi.createLocation(token, data);
    setAddOpen(false);
    await Promise.all([refresh(), refreshLocations()]);
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
      // The global facility selector (and any kiosk showing it) reads from
      // its own fetch — refresh it too so a rename/activation shows up
      // there immediately instead of only in this admin table.
      await Promise.all([refresh(), refreshLocations()]);
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
          <button className="btn btn-primary" onClick={() => setAddOpen(true)}>
            <Plus size={15} />
            Add Location
          </button>
        </div>
      )}

      {loading ? (
        <p className="loading-state">Loading facilities…</p>
      ) : sorted.length === 0 ? (
        <p className="empty-state">No facilities yet.</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
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
                    {location.is_active ? (
                      <Badge status="success">Active</Badge>
                    ) : (
                      <Badge status="neutral">Deactivated</Badge>
                    )}
                  </td>
                  <td>
                    <button className="btn btn-secondary btn-sm" onClick={() => setManagingId(location.id)}>
                      Manage
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

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
