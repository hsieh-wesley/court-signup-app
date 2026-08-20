import { useEffect, useMemo, useState } from "react";
import { Eye, EyeOff, Plus } from "lucide-react";
import { useAuth } from "../../AuthContext";
import { useFacility } from "../../LocationContext";
import { adminApi } from "../../apiClient";
import Modal from "../../components/Modal";
import Badge from "../../components/Badge";

function formatPhone(digits) {
  if (!digits) return "—";
  const d = digits.padEnd(10, " ");
  return `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6, 10)}`.trim();
}

// The editable input's own value is always exactly the raw digits the
// admin typed — never reformatted with inserted parens/spaces/dashes.
// Reformatting the live value on every keystroke (the previous approach)
// fights the browser's own cursor tracking: deleting from the middle, or
// anywhere but the very end, becomes unreliable once the displayed text
// no longer matches 1:1 with what was actually typed/deleted. A separate,
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

// Hidden by default, same reasoning as UsersPanel's PasswordCell — a
// front-desk screen is often visible to whoever's standing at the
// counter. A member's password is invalidated on every check-in, so
// this is the only way to view their *current* one without checking
// them in again.
function PasswordReveal({ password }) {
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

function dateInputValue(iso) {
  return iso ? new Date(iso).toISOString().slice(0, 10) : "";
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

function ManageMembershipModal({ member, onClose, onEdit, onRenew, history, locations }) {
  const [phone, setPhone] = useState(member.phone_number || "");
  const [expiresAt, setExpiresAt] = useState(dateInputValue(member.expires_at));
  const [locationId, setLocationId] = useState(member.location_id);
  const [renewPhone, setRenewPhone] = useState("");
  const [renewLocationId, setRenewLocationId] = useState(member.location_id);
  const [error, setError] = useState(null);

  async function handleSave(e) {
    e.preventDefault();
    setError(null);
    try {
      await onEdit(member, {
        phoneNumber: phone,
        expiresAt: expiresAt ? new Date(expiresAt).toISOString() : null,
        locationId,
      });
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleRenew(e) {
    e.preventDefault();
    setError(null);
    try {
      await onRenew(member, renewPhone, renewLocationId);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <Modal title={`Manage ${member.display_name}`} onClose={onClose}>
      <p>
        Status:{" "}
        {member.status === "active" ? (
          <Badge status="success">Active</Badge>
        ) : (
          <Badge status="neutral">Expired</Badge>
        )}
      </p>
      <p>
        Password: <PasswordReveal password={member.password} />
      </p>
      <p>Valid at: {member.location_name || "All Locations"}</p>

      {member.status === "active" ? (
        <form onSubmit={handleSave} className="form">
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
          <button type="submit" className="btn btn-primary btn-sm" disabled={phone.length !== 10}>
            Save
          </button>
        </form>
      ) : (
        <form onSubmit={handleRenew} className="form">
          <label>
            Renew with phone number
            <input {...phoneInputProps(renewPhone, setRenewPhone)} required />
          </label>
          <PhonePreview digits={renewPhone} />
          <LocationSelect value={renewLocationId} onChange={setRenewLocationId} locations={locations} />
          <button type="submit" className="btn btn-primary btn-sm" disabled={renewPhone.length !== 10}>
            Renew membership
          </button>
        </form>
      )}
      {error && <p className="error">{error}</p>}

      <h4 style={{ marginTop: "var(--space-5)" }}>Membership periods</h4>
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

export default function MembershipPanel() {
  const { token } = useAuth();
  const { locations } = useFacility();
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [managingId, setManagingId] = useState(null);
  const [managingHistory, setManagingHistory] = useState([]);
  const [credential, setCredential] = useState(null);

  async function refresh() {
    const data = await adminApi.listMemberships(token);
    setMembers(data);
    setLoading(false);
  }

  useEffect(() => {
    refresh();
  }, []);

  const sorted = useMemo(() => [...members].sort((a, b) => a.display_name.localeCompare(b.display_name)), [members]);

  async function handleCreate({ username, phoneNumber, expiresAt, locationId }) {
    const payload = await adminApi.startMembership(token, { username, phoneNumber, expiresAt, locationId });
    if (payload.password) setCredential({ username: payload.username, password: payload.password });
    setAddOpen(false);
    await refresh();
  }

  async function handleEdit(member, { phoneNumber, expiresAt, locationId }) {
    await adminApi.editMembership(token, member.id, { phoneNumber, expiresAt, locationId });
    await refresh();
  }

  async function handleRenew(member, phoneNumber, locationId) {
    const payload = await adminApi.startMembership(token, {
      username: member.username,
      phoneNumber,
      locationId,
    });
    if (payload.password) setCredential({ username: payload.username, password: payload.password });
    await refresh();
  }

  async function openManage(member) {
    setManagingId(member.id);
    const rows = await adminApi.getLoginHistory(token, { username: member.username });
    setManagingHistory(rows.filter((r) => r.context === "member_check_in"));
  }

  const managingMember = members.find((m) => m.id === managingId);

  return (
    <div>
      {credential && (
        <div className="credential-reveal" style={{ marginBottom: "var(--space-4)" }}>
          <h3>Generated credentials</h3>
          <p>
            {credential.username}: <strong>{credential.password}</strong>
          </p>
          <button className="btn btn-secondary btn-sm" onClick={() => setCredential(null)}>
            Dismiss
          </button>
        </div>
      )}

      <div className="admin-toolbar">
        <button className="btn btn-primary" onClick={() => setAddOpen(true)}>
          <Plus size={15} />
          Add Member
        </button>
      </div>

      {loading ? (
        <p className="loading-state">Loading members…</p>
      ) : sorted.length === 0 ? (
        <p className="empty-state">No members yet.</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Phone</th>
                <th>Status</th>
                <th>Password</th>
                <th>Location</th>
                <th>Member Since</th>
                <th>Expires</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((member) => (
                <tr key={member.id}>
                  <td>{member.display_name}</td>
                  <td>{formatPhone(member.phone_number)}</td>
                  <td>
                    {member.status === "active" ? (
                      <Badge status="success">Active</Badge>
                    ) : (
                      <Badge status="neutral">Expired</Badge>
                    )}
                  </td>
                  <td>
                    <PasswordReveal password={member.password} />
                  </td>
                  <td>{member.location_name || "All Locations"}</td>
                  <td>{new Date(member.member_since).toLocaleDateString()}</td>
                  <td>{member.expires_at ? new Date(member.expires_at).toLocaleDateString() : "No expiration"}</td>
                  <td>
                    <button className="btn btn-secondary btn-sm" onClick={() => openManage(member)}>
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
        <Modal title="Add Member" onClose={() => setAddOpen(false)}>
          <AddMemberForm onCreate={handleCreate} locations={locations} />
        </Modal>
      )}

      {managingMember && (
        <ManageMembershipModal
          member={managingMember}
          history={managingHistory}
          onClose={() => setManagingId(null)}
          onEdit={handleEdit}
          onRenew={handleRenew}
          locations={locations}
        />
      )}
    </div>
  );
}
