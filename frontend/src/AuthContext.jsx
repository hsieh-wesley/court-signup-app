import { createContext, useContext, useState } from "react";
import { api } from "./apiClient";

const AuthContext = createContext(null);

// Admin-only. Under the public kiosk model, regular players never hold a
// persistent session — every Join/Overview action verifies credentials
// fresh instead (see apiClient's joinQueue/joinOpenSlot/quickUnsign, none
// of which take a token). This context only ever represents the Admin
// corner's authenticated session.
export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem("token"));
  const [username, setUsername] = useState(() => localStorage.getItem("username"));
  const [isAdmin, setIsAdmin] = useState(() => localStorage.getItem("isAdmin") === "true");
  const [isSuperuser, setIsSuperuser] = useState(
    () => localStorage.getItem("isSuperuser") === "true"
  );

  async function login(user, password, locationId) {
    const data = await api.login(user, password, locationId);
    setToken(data.token);
    setUsername(data.username);
    setIsAdmin(data.is_staff);
    setIsSuperuser(data.is_superuser);
    localStorage.setItem("token", data.token);
    localStorage.setItem("username", data.username);
    localStorage.setItem("isAdmin", String(data.is_staff));
    localStorage.setItem("isSuperuser", String(data.is_superuser));
    return data;
  }

  function logout() {
    if (token) api.logout(token).catch(() => {});
    setToken(null);
    setUsername(null);
    setIsAdmin(false);
    setIsSuperuser(false);
    localStorage.removeItem("token");
    localStorage.removeItem("username");
    localStorage.removeItem("isAdmin");
    localStorage.removeItem("isSuperuser");
  }

  return (
    <AuthContext.Provider value={{ token, username, isAdmin, isSuperuser, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
