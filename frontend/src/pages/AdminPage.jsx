import { useState } from "react";
import { useFacility } from "../LocationContext";
import UsersPanel from "./admin/UsersPanel";
import CourtsPanel from "./admin/CourtsPanel";
import LocationsPanel from "./admin/LocationsPanel";
import MembershipPanel from "./admin/MembershipPanel";
import HistoryPanel from "./admin/HistoryPanel";

export default function AdminPage() {
  const [tab, setTab] = useState("users");
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
