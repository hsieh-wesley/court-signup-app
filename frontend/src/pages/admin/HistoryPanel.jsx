import { useEffect, useState } from "react";
import { useAuth } from "../../AuthContext";
import { useFacility } from "../../LocationContext";
import { adminApi } from "../../apiClient";
import Badge from "../../components/Badge";

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
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState(today());
  const [locationFilter, setLocationFilter] = useState(locationId || "");
  const [usernameFilter, setUsernameFilter] = useState("");
  const [eventTypeFilter, setEventTypeFilter] = useState("");
  const [membershipFilter, setMembershipFilter] = useState("");

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
      membership: membershipFilter || undefined,
    };
    const [loginData, activityData] = await Promise.all([
      adminApi.getLoginHistory(token, filters),
      adminApi.getCourtActivityHistory(token, { ...filters, event_type: eventTypeFilter || undefined }),
    ]);
    setLogins(loginData);
    setActivity(activityData);
    setLoading(false);
  }

  useEffect(() => {
    setLoading(true);
    refresh();
  }, [date, locationFilter, usernameFilter, eventTypeFilter, membershipFilter]);

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
        <label>
          Membership
          <select value={membershipFilter} onChange={(e) => setMembershipFilter(e.target.value)}>
            <option value="">All</option>
            <option value="member">Member</option>
            <option value="non_member">Non-Member</option>
          </select>
        </label>
      </div>

      {loading ? (
        <p className="loading-state">Loading history…</p>
      ) : (
        <>
          <h4>Logins</h4>
          {logins.length === 0 ? (
            <p className="empty-state">No login events for these filters.</p>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Username</th>
                    <th>Location</th>
                    <th>Event</th>
                    <th>Membership</th>
                  </tr>
                </thead>
                <tbody>
                  {logins.map((row) => (
                    <tr key={row.id}>
                      <td>{new Date(row.created_at).toLocaleString()}</td>
                      <td>{row.username}</td>
                      <td>{row.location_name}</td>
                      <td>{row.context}</td>
                      <td>
                        {row.membership_status === "member" ? (
                          <Badge status="accent">Member</Badge>
                        ) : (
                          <Badge status="neutral">Non-Member</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <h4>Court Activity</h4>
          {activity.length === 0 ? (
            <p className="empty-state">No court activity for these filters.</p>
          ) : (
            <div className="table-wrap">
              <table className="table">
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
                        <span style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                          {[row.player_1_username, row.player_2_username].filter(Boolean).join(" & ")}
                          {(row.player_1_membership_status === "member" ||
                            row.player_2_membership_status === "member") && (
                            <Badge status="accent">Member</Badge>
                          )}
                        </span>
                      </td>
                      <td>{row.actor_username || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
