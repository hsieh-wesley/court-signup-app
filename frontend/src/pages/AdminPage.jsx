import { useState } from "react";
import { useAuth } from "../AuthContext";
import { useFacility } from "../LocationContext";
import { adminApi } from "../apiClient";
import UsersPanel from "./admin/UsersPanel";
import CourtsPanel from "./admin/CourtsPanel";
import LocationsPanel from "./admin/LocationsPanel";
import MembershipPanel from "./admin/MembershipPanel";
import HistoryPanel from "./admin/HistoryPanel";

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
    <div className="admin-toolbar">
      <button onClick={handleReset} disabled={resetting}>
        {resetting ? "Resetting…" : "Reset Staff Password"}
      </button>
      {newPassword && (
        <span>
          New staff password: <strong>{newPassword}</strong>{" "}
          <button onClick={() => setNewPassword(null)}>Dismiss</button>
        </span>
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
      <h1>Admin</h1>

      {locations.length > 0 && (
        <select
          className="location-switcher admin-facility-select"
          value={selectedLocationId || ""}
          onChange={(e) => setSelectedLocationId(e.target.value)}
        >
          {locations.map((loc) => (
            <option key={loc.id} value={loc.id}>
              {loc.name}
            </option>
          ))}
        </select>
      )}

      {isSuperuser && <StaffAccountControl />}

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
        <button className={tab === "membership" ? "active" : ""} onClick={() => setTab("membership")}>
          Membership
        </button>
        <button className={tab === "history" ? "active" : ""} onClick={() => setTab("history")}>
          History
        </button>
      </div>

      {tab === "users" && <UsersPanel locationId={selectedLocationId} />}
      {tab === "courts" && <CourtsPanel locationId={selectedLocationId} />}
      {tab === "locations" && <LocationsPanel />}
      {tab === "membership" && <MembershipPanel />}
      {tab === "history" && <HistoryPanel locationId={selectedLocationId} />}
    </div>
  );
}
