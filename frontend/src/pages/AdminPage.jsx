import { useEffect, useState } from "react";
import { Eye, EyeOff, KeyRound } from "lucide-react";
import { useAuth } from "../AuthContext";
import { ALL_LOCATIONS, useFacility } from "../LocationContext";
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

// Viewing the staff account's current password is available to staff
// (their own account) and admin alike; only admin/superuser can reset
// it. There's no equivalent for the admin/superuser account itself —
// that password is never generated/tracked by this app.
function StaffAccountControl() {
  const { token, isSuperuser } = useAuth();
  const [password, setPassword] = useState(null);
  const [revealed, setRevealed] = useState(false);
  const [newPassword, setNewPassword] = useState(null);
  const [error, setError] = useState(null);
  const [resetting, setResetting] = useState(false);

  useEffect(() => {
    adminApi.getStaffCredential(token).then((data) => setPassword(data.password));
  }, [token]);

  async function handleReset() {
    if (!window.confirm("Reset the staff account's password? This signs staff out everywhere.")) return;
    setError(null);
    setResetting(true);
    try {
      const data = await adminApi.resetStaffPassword(token);
      setNewPassword(data.password);
      setPassword(data.password);
      setRevealed(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setResetting(false);
    }
  }

  return (
    <div className="admin-toolbar" style={{ marginBottom: "var(--space-5)" }}>
      <span className="muted">
        Staff password:{" "}
        {password ? (
          <span style={{ display: "inline-flex", alignItems: "center", gap: "var(--space-2)" }}>
            <code>{revealed ? password : "••••••••"}</code>
            <button
              type="button"
              className="btn btn-ghost btn-icon btn-sm"
              aria-label={revealed ? "Hide password" : "Show password"}
              onClick={() => setRevealed((r) => !r)}
            >
              {revealed ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </span>
        ) : (
          "—"
        )}
      </span>
      {isSuperuser && (
        <button className="btn btn-secondary btn-sm" onClick={handleReset} disabled={resetting}>
          <KeyRound size={14} />
          {resetting ? "Resetting…" : "Reset Staff Password"}
        </button>
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
  const { locations, selectedLocationId, setSelectedLocationId } = useFacility();
  // Child panels only ever understand "a real location" or "no location
  // filter" (undefined) — none of them know about the "All Locations"
  // sentinel, so translate it here once rather than in every panel.
  const panelLocationId = selectedLocationId === ALL_LOCATIONS ? undefined : selectedLocationId;

  return (
    <div className="page">
      <div className="court-card-header">
        <h1 style={{ margin: 0 }}>Admin</h1>
        {locations.length > 0 && (
          // Also controls which facility Overview/Join show on this
          // browser/kiosk — see LocationContext.ALL_LOCATIONS. Customers
          // on-site should only see/sign up for courts they can actually
          // walk to, so leave this on a specific facility for a real
          // front-desk kiosk; "All Locations" is for admin's own general
          // overview, not the normal per-site default. The visible label
          // exists because this control's effect (what the public
          // Overview/Join screens on this browser show) isn't otherwise
          // obvious from inside the Admin console.
          <label
            style={{
              flexDirection: "row",
              alignItems: "center",
              gap: "var(--space-2)",
              fontSize: "var(--text-sm)",
              color: "var(--color-text-secondary)",
            }}
          >
            Overview/Join shows:
            <select
              className="location-switcher"
              value={selectedLocationId}
              onChange={(e) => setSelectedLocationId(e.target.value)}
              aria-label="Facility shown on Overview and Join"
              title="Sets which facility the public Overview and Join screens show on this browser/kiosk"
            >
              <option value={ALL_LOCATIONS}>All Locations</option>
              {locations.map((loc) => (
                <option key={loc.id} value={loc.id}>
                  {loc.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <StaffAccountControl />

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

      {tab === "users" && <UsersPanel locationId={panelLocationId} />}
      {tab === "courts" && <CourtsPanel locationId={panelLocationId} />}
      {tab === "locations" && <LocationsPanel />}
      {tab === "membership" && <MembershipPanel locationId={panelLocationId} />}
      {tab === "history" && <HistoryPanel locationId={panelLocationId} />}
    </div>
  );
}
