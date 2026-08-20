import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useFacility } from "../LocationContext";
import { api } from "../apiClient";

const PASSWORD_VISIBLE_MS = 10000;

// Self-service account creation, or an explicit Check In for a returning
// player. Neither touches AuthContext — nothing here ever signs the public
// kiosk in as that player.
export default function JoinPage() {
  const { selectedLocationId, selectedLocation } = useFacility();
  const navigate = useNavigate();
  const [mode, setMode] = useState("create");
  const [username, setUsername] = useState("");
  const [checking, setChecking] = useState(false);
  const [available, setAvailable] = useState(null);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [createdPassword, setCreatedPassword] = useState(null);
  const [passwordVisible, setPasswordVisible] = useState(true);
  const [checkInPassword, setCheckInPassword] = useState("");
  const [checkedIn, setCheckedIn] = useState(false);
  const [checkedInUsername, setCheckedInUsername] = useState("");

  useEffect(() => {
    if (mode !== "create") return;
    const trimmed = username.trim();
    if (!trimmed) {
      setAvailable(null);
      return;
    }
    setChecking(true);
    const handle = setTimeout(() => {
      api
        .checkUsername(trimmed)
        .then((res) => setAvailable(res.available))
        .catch(() => setAvailable(null))
        .finally(() => setChecking(false));
    }, 400);
    return () => clearTimeout(handle);
  }, [mode, username]);

  function switchMode(next) {
    setMode(next);
    setUsername("");
    setCheckInPassword("");
    setAvailable(null);
    setError(null);
    setCheckedIn(false);
  }

  useEffect(() => {
    if (!createdPassword) return;
    setPasswordVisible(true);
    const timeout = setTimeout(() => setPasswordVisible(false), PASSWORD_VISIBLE_MS);
    return () => clearTimeout(timeout);
  }, [createdPassword]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const data = await api.registerPlayer(username.trim(), selectedLocationId);
      setCreatedPassword(data.password);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCheckIn(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.checkIn(username.trim(), checkInPassword, selectedLocationId);
      setCheckedInUsername(username.trim());
      setCheckedIn(true);
      setUsername("");
      setCheckInPassword("");
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (createdPassword) {
    return (
      <div className="page page-narrow">
        <h1>You're in!</h1>
        <p>Remember your username and password — you'll need them to join a court.</p>
        <div className="card">
          <p>
            Username: <strong>{username}</strong>
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

  if (checkedIn) {
    return (
      <div className="page page-narrow">
        <h1>You're checked in!</h1>
        <p className="success">
          {checkedInUsername} is checked in at{selectedLocation ? ` ${selectedLocation.name}` : ""}{" "}
          for today.
        </p>
        <div className="mode-toggle">
          <button onClick={() => switchMode("checkin")}>Check in someone else</button>
          <button onClick={() => navigate("/overview")}>Go to Overview</button>
        </div>
      </div>
    );
  }

  return (
    <div className="page page-narrow">
      <h1>Join{selectedLocation ? ` ${selectedLocation.name}` : ""}</h1>
      <div className="mode-toggle">
        <button className={mode === "create" ? "active" : ""} onClick={() => switchMode("create")}>
          Create username
        </button>
        <button className={mode === "checkin" ? "active" : ""} onClick={() => switchMode("checkin")}>
          Check In
        </button>
      </div>
      {mode === "checkin" ? (
        <>
          <p className="muted">Already have a username? Check in for today here.</p>
          <form onSubmit={handleCheckIn} className="form">
            <label>
              Username
              <input value={username} onChange={(e) => setUsername(e.target.value)} required />
            </label>
            <label>
              Password
              <input
                type="password"
                value={checkInPassword}
                onChange={(e) => setCheckInPassword(e.target.value)}
                required
              />
            </label>
            {error && <p className="error">{error}</p>}
            <button type="submit" disabled={submitting || !selectedLocationId}>
              {submitting ? "Checking in…" : "Check In"}
            </button>
          </form>
        </>
      ) : (
        <CreateUsernameForm
          username={username}
          setUsername={setUsername}
          checking={checking}
          available={available}
          error={error}
          submitting={submitting}
          selectedLocationId={selectedLocationId}
          onSubmit={handleSubmit}
        />
      )}
    </div>
  );
}

function CreateUsernameForm({
  username,
  setUsername,
  checking,
  available,
  error,
  submitting,
  selectedLocationId,
  onSubmit,
}) {
  return (
    <>
      <p className="muted">Pick a username — no account needed ahead of time.</p>
      <form onSubmit={onSubmit} className="form">
        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} required />
        </label>
        {checking && <p className="muted">Checking availability…</p>}
        {!checking && available === false && <p className="error">That username is taken.</p>}
        {!checking && available === true && <p className="success">Available!</p>}
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={submitting || available === false || !selectedLocationId}>
          {submitting ? "Creating…" : "Create username"}
        </button>
      </form>
    </>
  );
}
