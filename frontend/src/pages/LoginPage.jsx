import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Eye, EyeOff, XCircle } from "lucide-react";
import { useAuth } from "../AuthContext";
import { useFacility } from "../LocationContext";

// Admin sign-in only — reached only by typing "admin"/"staff" on the Join
// page (no nav link is shown while logged out). Regular players never use
// a login page under the public kiosk model (Join creates an account
// without signing the kiosk in; Overview/My Status verify credentials
// inline, per action, with nothing persisted).
export default function LoginPage() {
  const { login } = useAuth();
  const { selectedLocationId } = useFacility();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState(location.state?.prefillUsername || "");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password, selectedLocationId);
      navigate("/admin");
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page page-narrow">
      <h1 style={{ textAlign: "center" }}>Administrator sign in</h1>
      <div className="card">
        <form onSubmit={handleSubmit} className="form">
          <label>
            Username
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
              required
            />
          </label>
          <label>
            Password
            <div className="password-field">
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <button
                type="button"
                className="btn btn-secondary btn-icon"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </label>
          {error && (
            <p className="error">
              <XCircle size={14} /> {error}
            </p>
          )}
          <button type="submit" className="btn btn-primary btn-lg" disabled={submitting}>
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
