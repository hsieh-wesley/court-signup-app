import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../AuthContext";
import { adminApi } from "../../apiClient";
import Modal from "../../components/Modal";

function formatPhone(digits) {
  if (!digits) return "—";
  const d = digits.padEnd(10, " ");
  return `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6, 10)}`.trim();
}

// Formats-as-you-type: strips non-digits, caps at 10, renders (XXX) XXX-XXXX.
function phoneInputProps(digits, setDigits) {
  return {
    value: formatPhone(digits).replace(/\s+$/, ""),
    onChange: (e) => setDigits(e.target.value.replace(/\D/g, "").slice(0, 10)),
    placeholder: "(555) 010-0001",
  };
}

function dateInputValue(iso) {
  return iso ? new Date(iso).toISOString().slice(0, 10) : "";
}

function AddMemberForm({ onCreate }) {
  const [username, setUsername] = useState("");
  const [phone, setPhone] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
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
      });
      setUsername("");
      setPhone("");
      setExpiresAt("");
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
      <label>
        Expiration (optional)
        <input type="date" value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)} />
      </label>
      {error && <p className="error">{error}</p>}
      <button type="submit" disabled={submitting || phone.length !== 10}>
        {submitting ? "Adding…" : "Add member"}
      </button>
    </form>
  );
}

function ManageMembershipModal({ member, onClose, onEdit, onRenew, history }) {
  const [phone, setPhone] = useState(member.phone_number || "");
  const [expiresAt, setExpiresAt] = useState(dateInputValue(member.expires_at));
  const [renewPhone, setRenewPhone] = useState("");
  const [error, setError] = useState(null);

  async function handleSave(e) {
    e.preventDefault();
    setError(null);
    try {
      await onEdit(member, {
        phoneNumber: phone,
        expiresAt: expiresAt ? new Date(expiresAt).toISOString() : null,
      });
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleRenew(e) {
    e.preventDefault();
    setError(null);
    try {
      await onRenew(member, renewPhone);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <Modal title={`Manage ${member.display_name}`} onClose={onClose}>
      <p className="muted">Status: {member.status === "active" ? "Active" : "Expired"}</p>

      {member.status === "active" ? (
        <form onSubmit={handleSave} className="form">
          <label>
            Phone number
            <input {...phoneInputProps(phone, setPhone)} required />
          </label>
          <label>
            Expiration (blank = none)
            <input type="date" value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)} />
          </label>
          <button type="submit" disabled={phone.length !== 10}>
            Save
          </button>
        </form>
      ) : (
        <form onSubmit={handleRenew} className="form">
          <label>
            Renew with phone number
            <input {...phoneInputProps(renewPhone, setRenewPhone)} required />
          </label>
          <button type="submit" disabled={renewPhone.length !== 10}>
            Renew membership
          </button>
        </form>
      )}
      {error && <p className="error">{error}</p>}

      <h4>Membership periods</h4>
      <ul className="pair-list">
        {member.periods.map((p) => (
          <li key={p.id}>
            <span>
              {formatPhone(p.phone_number)} — {new Date(p.starts_at).toLocaleDateString()} to{" "}
              {p.expires_at ? new Date(p.expires_at).toLocaleDateString() : "no expiration"}
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
  const [members, setMembers] = useState([]);
  const [addOpen, setAddOpen] = useState(false);
  const [managingId, setManagingId] = useState(null);
  const [managingHistory, setManagingHistory] = useState([]);
  const [credential, setCredential] = useState(null);

  async function refresh() {
    const data = await adminApi.listMemberships(token);
    setMembers(data);
  }

  useEffect(() => {
    refresh();
  }, []);

  const sorted = useMemo(() => [...members].sort((a, b) => a.display_name.localeCompare(b.display_name)), [members]);

  async function handleCreate({ username, phoneNumber, expiresAt }) {
    const payload = await adminApi.startMembership(token, { username, phoneNumber, expiresAt });
    if (payload.password) setCredential({ username: payload.username, password: payload.password });
    setAddOpen(false);
    await refresh();
  }

  async function handleEdit(member, { phoneNumber, expiresAt }) {
    await adminApi.editMembership(token, member.id, { phoneNumber, expiresAt });
    await refresh();
  }

  async function handleRenew(member, phoneNumber) {
    const payload = await adminApi.startMembership(token, {
      username: member.username,
      phoneNumber,
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
        <div className="card">
          <h3>Generated credentials</h3>
          <p>
            {credential.username}: <strong>{credential.password}</strong>
          </p>
          <button onClick={() => setCredential(null)}>Dismiss</button>
        </div>
      )}

      <div className="admin-toolbar">
        <button onClick={() => setAddOpen(true)}>+ Add Member</button>
      </div>

      <table className="history-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Phone</th>
            <th>Status</th>
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
              <td>{member.status === "active" ? "Active" : "Expired"}</td>
              <td>{new Date(member.member_since).toLocaleDateString()}</td>
              <td>{member.expires_at ? new Date(member.expires_at).toLocaleDateString() : "No expiration"}</td>
              <td>
                <button onClick={() => openManage(member)}>Manage</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {addOpen && (
        <Modal title="Add Member" onClose={() => setAddOpen(false)}>
          <AddMemberForm onCreate={handleCreate} />
        </Modal>
      )}

      {managingMember && (
        <ManageMembershipModal
          member={managingMember}
          history={managingHistory}
          onClose={() => setManagingId(null)}
          onEdit={handleEdit}
          onRenew={handleRenew}
        />
      )}
    </div>
  );
}
