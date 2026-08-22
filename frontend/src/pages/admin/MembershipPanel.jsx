import { useEffect, useMemo, useState } from "react";
import { Eye, EyeOff, MoreHorizontal, Plus } from "lucide-react";
import { useAuth } from "../../AuthContext";
import { useFacility } from "../../LocationContext";
import { adminApi } from "../../apiClient";
import Modal from "../../components/Modal";
import Badge from "../../components/Badge";

// Membership status (active/expired) — whether their current period is
// still valid. Separate from CourtStatus below (physical presence
// today), which is a different concept even though both used to be
// called "Status" in this panel.
const MEMBERSHIP_BADGE = {
  active: "success",
  expired: "neutral",
};

function membershipStatusText(member) {
  return member.status === "active" ? "Active" : "Expired";
}

// Physical court presence today — matches UsersPanel's Status column
// exactly (same field names/values from the backend).
const COURT_STATUS_LABELS = {
  on_court: "On Court",
  in_queue: "In Queue",
  waiting_room: "Waiting Room",
  not_checked_in: "Not Checked In",
};

const COURT_STATUS_BADGE = {
  on_court: "accent",
  in_queue: "warning",
  waiting_room: "success",
  not_checked_in: "neutral",
};

function courtStatusText(member) {
  const label = COURT_STATUS_LABELS[member.court_status] || member.court_status;
  if (member.court_status === "on_court" && member.court_number != null) {
    return `On Court ${member.court_number}`;
  }
  if (member.court_status === "in_queue" && member.court_number != null) {
    return `In Queue · Court ${member.court_number}`;
  }
  return label;
}

function formatPhone(digits) {
  if (!digits) return "—";
  const d = digits.padEnd(10, " ");
  return `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6, 10)}`.trim();
}

// The editable input's own value is always exactly the raw digits the
// admin typed — never reformatted with inserted parens/spaces/dashes.
// Reformatting the live value on every keystroke fights the browser's
// own cursor tracking: deleting from the middle, or anywhere but the
// very end, becomes unreliable once the displayed text no longer
// matches 1:1 with what was actually typed/deleted. A separate,
// non-editable preview below shows the pretty (XXX) XXX-XXXX form instead.
function phoneInputProps(digits, setDigits) {
  return {
    value: digits,
    onChange: (e) => setDigits(e.target.value.replace(/\D/g, "").slice(0, 10)),
    placeholder: "5550100001",
    inputMode: "numeric",
  };
}

function PhonePreview({ digits }) {
  if (!digits) return null;
  return <p className="muted" style={{ marginTop: "calc(-1 * var(--space-2))" }}>{formatPhone(digits)}</p>;
}

// A membership can be valid everywhere ("All Locations", value=null) or
// scoped to one specific facility — member check-in at any other
// facility is rejected when scoped.
function LocationSelect({ label = "Valid at", value, onChange, locations }) {
  return (
    <label>
      {label}
      <select value={value ?? ""} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">All Locations</option>
        {locations.map((loc) => (
          <option key={loc.id} value={loc.id}>
            {loc.name}
          </option>
        ))}
      </select>
    </label>
  );
}

// Hidden by default (a front-desk kiosk screen is often visible to
// whoever's standing at the counter) — click to reveal without needing
// Reset Password, which would invalidate the member's actual credential.
function PasswordCell({ password }) {
  const [revealed, setRevealed] = useState(false);
  if (!password) return <span className="muted">—</span>;
  return (
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
  );
}

function dateInputValue(iso) {
  return iso ? new Date(iso).toISOString().slice(0, 10) : "";
}

function CredentialBanner({ credentials, onDismiss }) {
  if (!credentials.length) return null;
  return (
    <div className="credential-reveal" style={{ marginBottom: "var(--space-4)" }}>
      <h3>Generated credentials</h3>
      <ul className="pair-list">
        {credentials.map((c) => (
          <li key={c.username}>
            <span>
              {c.username}: <strong>{c.password}</strong>
            </span>
          </li>
        ))}
      </ul>
      <button className="btn btn-secondary btn-sm" onClick={onDismiss}>
        Dismiss
      </button>
    </div>
  );
}

function AddMemberForm({ onCreate, locations }) {
  const [username, setUsername] = useState("");
  const [phone, setPhone] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [locationId, setLocationId] = useState(null);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await onCreate({
        username,
        phoneNumber: phone,
        expiresAt: expiresAt ? new Date(expiresAt).toISOString() : null,
        locationId,
      });
      setUsername("");
      setPhone("");
      setExpiresAt("");
      setLocationId(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="form">
      <label>
        Username
        <input value={username} onChange={(e) => setUsername(e.target.value)} required />
      </label>
      <label>
        Phone number
        <input {...phoneInputProps(phone, setPhone)} required />
      </label>
      <PhonePreview digits={phone} />
      <LocationSelect value={locationId} onChange={setLocationId} locations={locations} />
      <label>
        Expiration (optional)
        <input type="date" value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)} />
      </label>
      {error && <p className="error">{error}</p>}
      <button type="submit" className="btn btn-primary" disabled={submitting || phone.length !== 10}>
        {submitting ? "Adding…" : "Add member"}
      </button>
    </form>
  );
}

function EditMemberForm({ member, locations, onSave, onCancel }) {
  const [phone, setPhone] = useState(member.phone_number || "");
  const [expiresAt, setExpiresAt] = useState(dateInputValue(member.expires_at));
  const [locationId, setLocationId] = useState(member.location_id);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    try {
      await onSave(member.id, {
        phoneNumber: phone,
        expiresAt: expiresAt ? new Date(expiresAt).toISOString() : null,
        locationId,
      });
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="form">
      <label>
        Phone number
        <input {...phoneInputProps(phone, setPhone)} required />
      </label>
      <PhonePreview digits={phone} />
      <LocationSelect value={locationId} onChange={setLocationId} locations={locations} />
      <label>
        Expiration (blank = none)
        <input type="date" value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)} />
      </label>
      {error && <p className="error">{error}</p>}
      <div className="button-row">
        <button type="submit" className="btn btn-primary btn-sm" disabled={phone.length !== 10}>
          Save
        </button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function RenewMemberModal({ member, locations, onClose, onRenew }) {
  const [phone, setPhone] = useState("");
  const [locationId, setLocationId] = useState(member.location_id);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await onRenew(member, phone, locationId);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal title={`Renew @${member.username}`} onClose={onClose}>
      <form onSubmit={handleSubmit} className="form">
        <label>
          Phone number
          <input {...phoneInputProps(phone, setPhone)} required />
        </label>
        <PhonePreview digits={phone} />
        <LocationSelect value={locationId} onChange={setLocationId} locations={locations} />
        {error && <p className="error">{error}</p>}
        <button type="submit" className="btn btn-primary" disabled={submitting || phone.length !== 10}>
          {submitting ? "Renewing…" : "Renew membership"}
        </button>
      </form>
    </Modal>
  );
}

function HistoryModal({ member, history, onClose }) {
  return (
    <Modal title={`@${member.username} — History`} onClose={onClose}>
      <h4>Membership periods</h4>
      <ul className="pair-list">
        {member.periods.map((p) => (
          <li key={p.id}>
            <span>
              {formatPhone(p.phone_number)} — {new Date(p.starts_at).toLocaleDateString()} to{" "}
              {p.expires_at ? new Date(p.expires_at).toLocaleDateString() : "no expiration"}
              {" — "}
              {p.location_name}
            </span>
          </li>
        ))}
      </ul>

      <h4>Check-in history</h4>
      {history.length === 0 ? (
        <p className="muted">No check-ins yet.</p>
      ) : (
        <ul className="pair-list">
          {history.map((row) => (
            <li key={row.id}>
              <span>{new Date(row.created_at).toLocaleString()}</span>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}

function MemberRow({ member, locations, onAction, onSave }) {
  const [editing, setEditing] = useState(false);

  if (editing) {
    return (
      <tr>
        <td colSpan={8}>
          <EditMemberForm
            member={member}
            locations={locations}
            onSave={async (id, data) => {
              await onSave(id, data);
              setEditing(false);
            }}
            onCancel={() => setEditing(false)}
          />
        </td>
      </tr>
    );
  }

  return (
    <tr>
      <td>@{member.username}</td>
      <td>{formatPhone(member.phone_number)}</td>
      <td>
        <Badge status={COURT_STATUS_BADGE[member.court_status]}>{courtStatusText(member)}</Badge>
      </td>
      <td>
        <Badge status={MEMBERSHIP_BADGE[member.status]}>{membershipStatusText(member)}</Badge>
      </td>
      <td>
        <PasswordCell password={member.password} />
      </td>
      <td>{member.location_name || "All Locations"}</td>
      <td>{new Date(member.member_since).toLocaleDateString()}</td>
      <td>{member.expires_at ? new Date(member.expires_at).toLocaleDateString() : "No expiration"}</td>
      <td>
        <div className="row-actions">
          {member.status === "active" ? (
            <button className="btn btn-secondary btn-sm" onClick={() => setEditing(true)}>
              Edit
            </button>
          ) : (
            <button className="btn btn-secondary btn-sm" onClick={() => onAction("renew", member)}>
              Renew
            </button>
          )}
          <details className="actions-menu">
            <summary aria-label="More actions">
              <MoreHorizontal size={16} />
            </summary>
            <div className="actions-menu-list">
              <button className="btn btn-ghost btn-sm" onClick={() => onAction("resetPassword", member)}>
                Reset Password
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => onAction("history", member)}>
                View History
              </button>
            </div>
          </details>
        </div>
      </td>
    </tr>
  );
}

const SORTERS = {
  name: (a, b) => a.display_name.localeCompare(b.display_name),
  status: (a, b) => (a.status > b.status ? 1 : a.status < b.status ? -1 : 0),
  since: (a, b) => new Date(b.member_since) - new Date(a.member_since),
  expires: (a, b) => new Date(a.expires_at || 0) - new Date(b.expires_at || 0),
};

export default function MembershipPanel({ locationId }) {
  const { token } = useAuth();
  const { locations } = useFacility();
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [credentials, setCredentials] = useState([]);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortBy, setSortBy] = useState("name");
  const [addOpen, setAddOpen] = useState(false);
  const [renewingId, setRenewingId] = useState(null);
  const [historyId, setHistoryId] = useState(null);
  const [historyRows, setHistoryRows] = useState([]);

  async function refresh() {
    const data = await adminApi.listMemberships(token, locationId);
    setMembers(data);
    setLoading(false);
  }

  useEffect(() => {
    setLoading(true);
    refresh();
  }, [locationId]);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return members
      .filter((m) => {
        if (statusFilter !== "all" && m.status !== statusFilter) return false;
        if (!term) return true;
        return (
          m.display_name.toLowerCase().includes(term) ||
          (m.username || "").toLowerCase().includes(term) ||
          (m.phone_number || "").includes(term)
        );
      })
      .sort(SORTERS[sortBy]);
  }, [members, search, statusFilter, sortBy]);

  async function handleCreate({ username, phoneNumber, expiresAt, locationId }) {
    const payload = await adminApi.startMembership(token, { username, phoneNumber, expiresAt, locationId });
    if (payload.password) {
      setCredentials((c) => [...c, { username: payload.username, password: payload.password }]);
    }
    setAddOpen(false);
    await refresh();
  }

  async function handleSave(memberId, data) {
    await adminApi.editMembership(token, memberId, data);
    await refresh();
  }

  async function handleRenew(member, phoneNumber, locationId) {
    const payload = await adminApi.startMembership(token, {
      username: member.username,
      phoneNumber,
      locationId,
    });
    if (payload.password) {
      setCredentials((c) => [...c, { username: payload.username, password: payload.password }]);
    }
    await refresh();
  }

  async function handleAction(action, member) {
    setError(null);
    try {
      if (action === "resetPassword") {
        if (!window.confirm(`Reset @${member.username}'s password?`)) return;
        const payload = await adminApi.resetPassword(token, member.id);
        setCredentials((c) => [...c, { username: payload.username, password: payload.password }]);
        await refresh();
      } else if (action === "renew") {
        setRenewingId(member.id);
      } else if (action === "history") {
        setHistoryId(member.id);
        const rows = await adminApi.getLoginHistory(token, { username: member.username });
        setHistoryRows(rows.filter((r) => r.context === "member_check_in"));
      }
    } catch (err) {
      setError(err.message);
    }
  }

  const renewingMember = members.find((m) => m.id === renewingId);
  const historyMember = members.find((m) => m.id === historyId);

  return (
    <div>
      <CredentialBanner credentials={credentials} onDismiss={() => setCredentials([])} />
      {error && <p className="error">{error}</p>}

      <div className="admin-toolbar">
        <label>
          Search
          <input
            placeholder="Name, username, or phone"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <label>
          Status
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="all">All</option>
            <option value="active">Active</option>
            <option value="expired">Expired</option>
          </select>
        </label>
        <label>
          Sort
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
            <option value="name">Name</option>
            <option value="status">Status</option>
            <option value="since">Member Since</option>
            <option value="expires">Expires</option>
          </select>
        </label>
        <span className="spacer" />
        <button className="btn btn-primary" onClick={() => setAddOpen(true)}>
          <Plus size={15} />
          Add Member
        </button>
      </div>

      {loading ? (
        <p className="loading-state">Loading members…</p>
      ) : visible.length === 0 ? (
        <p className="empty-state">No members match these filters.</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Username</th>
                <th>Phone</th>
                <th>Status</th>
                <th>Membership</th>
                <th>Password</th>
                <th>Location</th>
                <th>Member Since</th>
                <th>Expires</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((member) => (
                <MemberRow
                  key={member.id}
                  member={member}
                  locations={locations}
                  onAction={handleAction}
                  onSave={handleSave}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {addOpen && (
        <Modal title="Add Member" onClose={() => setAddOpen(false)}>
          <AddMemberForm onCreate={handleCreate} locations={locations} />
        </Modal>
      )}

      {renewingMember && (
        <RenewMemberModal
          member={renewingMember}
          locations={locations}
          onClose={() => setRenewingId(null)}
          onRenew={handleRenew}
        />
      )}

      {historyMember && (
        <HistoryModal
          member={historyMember}
          history={historyRows}
          onClose={() => setHistoryId(null)}
        />
      )}
    </div>
  );
}
