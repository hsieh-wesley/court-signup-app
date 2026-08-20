import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useFacility } from "../LocationContext";
import { api } from "../apiClient";

const PASSWORD_VISIBLE_MS = 10000;

// One field classified by content, not length: any letter means "this is a
// desired username" (self-registration); digits/phone-formatting only
// means "this is a member's phone number" (check-in). A phone-shaped input
// that doesn't normalize to exactly 10 digits is rejected right there —
// it never falls through to try registering it as a username.
function classifyInput(raw) {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  if (/[a-zA-Z]/.test(trimmed)) return "username";
  return "phone";
}

// Self-service account creation, or a member's phone-based Check In.
// Neither touches AuthContext — nothing here ever signs the public kiosk
// in as that player.
export default function JoinPage() {
  const { selectedLocationId, selectedLocation } = useFacility();
  const navigate = useNavigate();
  const [input, setInput] = useState("");
  const [checking, setChecking] = useState(false);
  const [available, setAvailable] = useState(null);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [createdPassword, setCreatedPassword] = useState(null);
  const [createdUsername, setCreatedUsername] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(true);
  const [checkedInMember, setCheckedInMember] = useState(null);

  const kind = classifyInput(input);

  useEffect(() => {
    if (kind !== "username") {
      setAvailable(null);
      return;
    }
    const trimmed = input.trim();
    setChecking(true);
    const handle = setTimeout(() => {
      api
        .checkUsername(trimmed)
        .then((res) => setAvailable(res.available))
        .catch(() => setAvailable(null))
        .finally(() => setChecking(false));
    }, 400);
    return () => clearTimeout(handle);
  }, [kind, input]);

  useEffect(() => {
    if (!createdPassword) return;
    setPasswordVisible(true);
    const timeout = setTimeout(() => setPasswordVisible(false), PASSWORD_VISIBLE_MS);
    return () => clearTimeout(timeout);
  }, [createdPassword]);

  function reset() {
    setInput("");
    setError(null);
    setAvailable(null);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    if (kind === "phone") {
      const digits = input.replace(/\D/g, "");
      if (digits.length !== 10) {
        setError("Enter a valid 10-digit phone number.");
        return;
      }
      setSubmitting(true);
      try {
        const data = await api.memberCheckIn(digits, selectedLocationId);
        setCheckedInMember(data);
        reset();
      } catch (err) {
        setError(err.message);
      } finally {
        setSubmitting(false);
      }
      return;
    }

    if (kind === "username") {
      setSubmitting(true);
      try {
        const trimmed = input.trim();
        const data = await api.registerPlayer(trimmed, selectedLocationId);
        setCreatedUsername(trimmed);
        setCreatedPassword(data.password);
        reset();
      } catch (err) {
        setError(err.message);
      } finally {
        setSubmitting(false);
      }
    }
  }

  if (createdPassword) {
    return (
      <div className="page page-narrow">
        <h1>You're in!</h1>
        <p>Remember your username and password — you'll need them to join a court.</p>
        <div className="card">
          <p>
            Username: <strong>{createdUsername}</strong>
          </p>
          {passwordVisible ? (
            <p>
              Password: <strong>{createdPassword}</strong>
            </p>
          ) : (
            <p className="muted">Password hidden now — hope you wrote it down!</p>
          )}
        </div>
        <button onClick={() => navigate("/overview")}>Go to Overview</button>
      </div>
    );
  }

  if (checkedInMember) {
    return (
      <div className="page page-narrow">
        <div className="avatar-placeholder">👤</div>
        <h1>Welcome to the club, {checkedInMember.display_name}!</h1>
        <div className="card">
          <p>
            Username: <strong>{checkedInMember.username}</strong>
          </p>
          <p>
            Password: <strong>{checkedInMember.password}</strong>
          </p>
        </div>
        <div className="mode-toggle">
          <button onClick={() => setCheckedInMember(null)}>Check in someone else</button>
          <button onClick={() => navigate("/overview")}>Go to Overview</button>
        </div>
      </div>
    );
  }

  return (
    <div className="page page-narrow">
      <h1>Join{selectedLocation ? ` ${selectedLocation.name}` : ""}</h1>
      <p className="muted">
        Members: type your 10-digit phone number to check in. Everyone else: type your desired
        username to get started.
      </p>
      <form onSubmit={handleSubmit} className="form">
        <label>
          Phone number or desired username
          <input value={input} onChange={(e) => setInput(e.target.value)} required />
        </label>
        {kind === "username" && checking && <p className="muted">Checking availability…</p>}
        {kind === "username" && !checking && available === false && (
          <p className="error">That username is taken.</p>
        )}
        {kind === "username" && !checking && available === true && (
          <p className="success">Available!</p>
        )}
        {error && <p className="error">{error}</p>}
        <button
          type="submit"
          disabled={submitting || !selectedLocationId || (kind === "username" && available === false)}
        >
          {submitting ? "Working…" : kind === "phone" ? "Check In" : "Create username"}
        </button>
      </form>
    </div>
  );
}
