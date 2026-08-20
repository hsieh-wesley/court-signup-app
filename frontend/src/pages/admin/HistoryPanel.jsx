import { useEffect, useState } from "react";
import { useAuth } from "../../AuthContext";
import { useFacility } from "../../LocationContext";
import { adminApi } from "../../apiClient";

const EVENT_TYPES = [
  "pair_queued",
  "pair_activated",
  "open_slot_joined",
  "pair_ended",
  "court_dropped",
  "court_deactivated",
  "court_reactivated",
];

function today() {
  return new Date().toISOString().slice(0, 10);
}

export default function HistoryPanel({ locationId }) {
  const { token } = useAuth();
  const { locations } = useFacility();
  const [logins, setLogins] = useState([]);
  const [activity, setActivity] = useState([]);
  const [date, setDate] = useState(today());
  const [locationFilter, setLocationFilter] = useState(locationId || "");
  const [usernameFilter, setUsernameFilter] = useState("");
  const [eventTypeFilter, setEventTypeFilter] = useState("");

  // Follow the global facility selector until the admin picks their own
  // override in this panel (including explicit "All Locations").
  useEffect(() => {
    setLocationFilter(locationId || "");
  }, [locationId]);

  async function refresh() {
    const filters = {
      location_id: locationFilter || undefined,
      username: usernameFilter || undefined,
      date: date || undefined,
    };
    const [loginData, activityData] = await Promise.all([
      adminApi.getLoginHistory(token, filters),
      adminApi.getCourtActivityHistory(token, { ...filters, event_type: eventTypeFilter || undefined }),
    ]);
    setLogins(loginData);
    setActivity(activityData);
  }

  useEffect(() => {
    refresh();
  }, [date, locationFilter, usernameFilter, eventTypeFilter]);

  return (
    <div>
      <div className="admin-toolbar">
        <label>
          Date
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label>
          Location
          <select value={locationFilter} onChange={(e) => setLocationFilter(e.target.value)}>
            <option value="">All Locations</option>
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
          Event type
          <select value={eventTypeFilter} onChange={(e) => setEventTypeFilter(e.target.value)}>
            <option value="">All</option>
            {EVENT_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
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
            <th>Event</th>
          </tr>
        </thead>
        <tbody>
          {logins.map((row) => (
            <tr key={row.id}>
              <td>{new Date(row.created_at).toLocaleString()}</td>
              <td>{row.username}</td>
              <td>{row.location_name}</td>
              <td>{row.context}</td>
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
              <td>{[row.player_1_username, row.player_2_username].filter(Boolean).join(" & ")}</td>
              <td>{row.actor_username || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
