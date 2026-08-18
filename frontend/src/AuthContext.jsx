import { createContext, useContext, useState } from "react";
import { api } from "./apiClient";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem("token"));
  const [username, setUsername] = useState(() => localStorage.getItem("username"));
  const [isAdmin, setIsAdmin] = useState(() => localStorage.getItem("isAdmin") === "true");
  const [sessionLocationId, setSessionLocationId] = useState(
    () => localStorage.getItem("sessionLocationId") || null
  );

  function persist(data) {
    setToken(data.token);
    setUsername(data.username);
    setIsAdmin(data.is_staff);
    setSessionLocationId(data.location_id ? String(data.location_id) : null);
    localStorage.setItem("token", data.token);
    localStorage.setItem("username", data.username);
    localStorage.setItem("isAdmin", String(data.is_staff));
    if (data.location_id) {
      localStorage.setItem("sessionLocationId", String(data.location_id));
    } else {
      localStorage.removeItem("sessionLocationId");
    }
  }

  // A player's session is scoped to exactly one facility (enforced by the
  // backend — it rejects logging in elsewhere while still active/waiting
  // at another facility, and rejects facility-scoped actions whose court
  // doesn't match the session's location). This just logs in for that
  // facility; the caller decides what facility to pass.
  async function login(user, password, locationId) {
    const data = await api.login(user, password, locationId);
    persist(data);
    return data;
  }

  // Create-and-authenticate in one step, for the self-service Join flow.
  // Returns the response (including the one-time plaintext password) so
  // the caller can display it briefly.
  async function register(desiredUsername, locationId) {
    const data = await api.registerPlayer(desiredUsername, locationId);
    persist(data);
    return data;
  }

  function logout() {
    if (token) api.logout(token).catch(() => {});
    clearSession();
    setUsername(null);
    localStorage.removeItem("username");
  }

  // Drops the session without forgetting the username, so switching
  // facilities only requires re-entering a password, not retyping it.
  function clearSession() {
    setToken(null);
    setIsAdmin(false);
    setSessionLocationId(null);
    localStorage.removeItem("token");
    localStorage.removeItem("isAdmin");
    localStorage.removeItem("sessionLocationId");
  }

  return (
    <AuthContext.Provider
      value={{ token, username, isAdmin, sessionLocationId, login, register, logout, clearSession }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
