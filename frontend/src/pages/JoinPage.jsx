import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CheckCircle2, XCircle } from "lucide-react";
import { ALL_LOCATIONS, useFacility } from "../LocationContext";
import { api } from "../apiClient";

const PASSWORD_VISIBLE_MS = 10000;

// "admin"/"staff" are hidden-in-plain-sight words, not credentials — typing
// either one here (exactly, case-insensitive) only navigates to the real
// login form; it never authenticates anyone by itself. Checked before the
// letter-vs-phone classification below, since both words are made of
// letters and would otherwise be treated as a desired username.
const ADMIN_WORDS = new Set(["admin", "staff"]);

// One field classified by content, not length: any letter means "this is a
// desired username" (self-registration); digits/phone-formatting only
// means "this is a member's phone number" (check-in). A phone-shaped input
// that doesn't normalize to exactly 10 digits is rejected right there —
// it never falls through to try registering it as a username.
function classifyInput(raw) {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  if (ADMIN_WORDS.has(trimmed.toLowerCase())) return "adminRedirect";
  if (/[a-zA-Z]/.test(trimmed)) return "username";
  return "phone";
}

// Always renders the same single <p> — its text/icon/class change, but the
// element itself is never added to or removed from the DOM, so it can
// never cause a layout/focus side effect near the input above it.
function StatusLine({ kind, checking, available, error }) {
  let className = "muted";
  let icon = null;
  let text = " "; // non-breaking space — keeps the line's height reserved even when empty

  if (error) {
    className = "error";
    icon = <XCircle size={14} />;
    text = error;
  } else if (kind === "username" && checking) {
    text = "Checking availability…";
  } else if (kind === "username" && available === false) {
    className = "error";
    icon = <XCircle size={14} />;
    text = "That username is taken.";
  } else if (kind === "username" && available === true) {
    className = "success";
    icon = <CheckCircle2 size={14} />;
    text = "Available!";
  }

  return (
    <p className={className}>
      {icon}
      {text}
    </p>
  );
}

// Self-service account creation, or a member's phone-based Check In.
// Neither touches AuthContext — nothing here ever signs the public kiosk
// in as that player.
export default function JoinPage() {
  const { selectedLocationId, selectedLocation } = useFacility();
  const noFacilitySelected = selectedLocationId === ALL_LOCATIONS;
  const navigate = useNavigate();
  const [input, setInput] = useState("");
  const [checking, setChecking] = useState(false);
  const [available, setAvailable] = useState(null);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [createdPassword, setCreatedPassword] = useState(null);
  const [createdUsername, setCreatedUsername] = useState("");
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

  // Either success screen shows the password for exactly 10s, then the
  // kiosk auto-returns to a blank Join screen — ready for the next person
  // without staff having to intervene.
  useEffect(() => {
    if (!createdPassword && !checkedInMember) return;
    const timeout = setTimeout(() => {
      setCreatedPassword(null);
      setCreatedUsername("");
      setCheckedInMember(null);
    }, PASSWORD_VISIBLE_MS);
    return () => clearTimeout(timeout);
  }, [createdPassword, checkedInMember]);

  function reset() {
    setInput("");
    setError(null);
    setAvailable(null);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    if (kind === "adminRedirect") {
      const prefillUsername = input.trim().toLowerCase();
      reset();
      navigate("/login", { state: { prefillUsername } });
      return;
    }

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
        <div className="avatar-placeholder">
          <CheckCircle2 size={28} />
        </div>
        <h1 style={{ textAlign: "center" }}>You're in!</h1>
        <p className="muted" style={{ textAlign: "center" }}>
          Remember your username and password — you'll need them to join a court.
        </p>
        <div className="credential-reveal">
          <p style={{ marginBottom: "var(--space-2)" }}>
            Username: <strong>{createdUsername}</strong>
          </p>
          <p style={{ marginBottom: 0 }}>
            Password: <strong>{createdPassword}</strong>
          </p>
        </div>
        <p className="muted" style={{ textAlign: "center", marginTop: "var(--space-4)" }}>
          Returning to Join in 10 seconds…
        </p>
        <button className="btn btn-secondary btn-lg" onClick={() => navigate("/overview")}>
          Go to Overview
        </button>
      </div>
    );
  }

  if (checkedInMember) {
    return (
      <div className="page page-narrow">
        <div className="avatar-placeholder">
          <CheckCircle2 size={28} />
        </div>
        <h1 style={{ textAlign: "center" }}>Welcome, {checkedInMember.display_name}!</h1>
        <div className="credential-reveal">
          <p style={{ marginBottom: "var(--space-2)" }}>
            Username: <strong>{checkedInMember.username}</strong>
          </p>
          <p style={{ marginBottom: 0 }}>
            Password: <strong>{checkedInMember.password}</strong>
          </p>
        </div>
        <p className="muted" style={{ textAlign: "center", marginTop: "var(--space-4)" }}>
          Returning to Join in 10 seconds…
        </p>
        <div className="button-row">
          <button className="btn btn-secondary" onClick={() => setCheckedInMember(null)}>
            Check in someone else
          </button>
          <button className="btn btn-secondary" onClick={() => navigate("/overview")}>
            Go to Overview
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="page page-narrow">
      <h1 style={{ textAlign: "center" }}>Check In</h1>
      {selectedLocation && (
        <p className="muted" style={{ textAlign: "center", marginTop: "calc(-1 * var(--space-2))" }}>
          {selectedLocation.name}
        </p>
      )}
      {noFacilitySelected ? (
        <p className="error" style={{ textAlign: "center" }}>
          This kiosk isn't set to a specific facility yet — ask staff to pick one in Admin.
        </p>
      ) : (
        <p className="muted" style={{ textAlign: "center" }}>
          Members can check in with their phone number.
          <br />
          Guests can create a username to get started.
        </p>
      )}
      <form onSubmit={handleSubmit} className="form">
        <label>
          Phone number or desired username
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="(555) 010-0001 or a username"
            autoComplete="off"
            required
          />
        </label>
        {/* One stable status node that only ever changes its own text/class,
            instead of four separately-conditioned <p> elements that mount
            and unmount as `checking`/`available`/`error` change — nothing
            near the input is ever added to or removed from the DOM after
            it renders. */}
        <StatusLine kind={kind} checking={checking} available={available} error={error} />
        <button
          type="submit"
          className="btn btn-primary btn-lg"
          disabled={
            submitting ||
            (kind !== "adminRedirect" && noFacilitySelected) ||
            (kind === "username" && available === false)
          }
        >
          {submitting
            ? "Working…"
            : kind === "adminRedirect"
              ? "Continue"
              : kind === "phone"
                ? "Check In"
                : "Create username"}
        </button>
      </form>
    </div>
  );
}
