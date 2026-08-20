import { useState } from "react";
import { KeyRound } from "lucide-react";
import { useAuth } from "../AuthContext";
import { useFacility } from "../LocationContext";
import { adminApi } from "../apiClient";
import UsersPanel from "./admin/UsersPanel";
import CourtsPanel from "./admin/CourtsPanel";
import LocationsPanel from "./admin/LocationsPanel";
import MembershipPanel from "./admin/MembershipPanel";
import HistoryPanel from "./admin/HistoryPanel";

const TABS = [
  { id: "users", label: "Users" },
  { id: "courts", label: "Courts" },
  { id: "locations", label: "Locations" },
  { id: "membership", label: "Membership" },
  { id: "history", label: "History" },
];

// Admin-only (staff cannot reset its own password). Resets staff's
// password in place and shows the new one once — it's never retrievable
// again after this.
function StaffAccountControl() {
  const { token } = useAuth();
  const [newPassword, setNewPassword] = useState(null);
  const [error, setError] = useState(null);
  const [resetting, setResetting] = useState(false);

  async function handleReset() {
    if (!window.confirm("Reset the staff account's password? This signs staff out everywhere.")) return;
    setError(null);
    setResetting(true);
    try {
      const data = await adminApi.resetStaffPassword(token);
      setNewPassword(data.password);
    } catch (err) {
      setError(err.message);
    } finally {
      setResetting(false);
    }
  }

  return (
    <div className="admin-toolbar" style={{ marginBottom: "var(--space-5)" }}>
      <button className="btn btn-secondary btn-sm" onClick={handleReset} disabled={resetting}>
        <KeyRound size={14} />
        {resetting ? "Resetting…" : "Reset Staff Password"}
      </button>
      {newPassword && (
        <span className="badge badge-accent">
          New staff password: <strong>{newPassword}</strong>
        </span>
      )}
      {newPassword && (
        <button className="btn btn-ghost btn-sm" onClick={() => setNewPassword(null)}>
          Dismiss
        </button>
      )}
      {error && <span className="error">{error}</span>}
    </div>
  );
}

export default function AdminPage() {
  const [tab, setTab] = useState("users");
  const { isSuperuser } = useAuth();
  const { locations, selectedLocationId, setSelectedLocationId } = useFacility();

  return (
    <div className="page">
      <div className="court-card-header">
        <h1 style={{ margin: 0 }}>Admin</h1>
        {locations.length > 0 && (
          <select
            className="location-switcher"
            value={selectedLocationId || ""}
            onChange={(e) => setSelectedLocationId(e.target.value)}
            aria-label="Facility"
          >
            {locations.map((loc) => (
              <option key={loc.id} value={loc.id}>
                {loc.name}
              </option>
            ))}
          </select>
        )}
      </div>

      {isSuperuser && <StaffAccountControl />}

      <div className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={tab === t.id ? "active" : ""}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "users" && <UsersPanel locationId={selectedLocationId} />}
      {tab === "courts" && <CourtsPanel locationId={selectedLocationId} />}
      {tab === "locations" && <LocationsPanel />}
      {tab === "membership" && <MembershipPanel />}
      {tab === "history" && <HistoryPanel locationId={selectedLocationId} />}
    </div>
  );
}
