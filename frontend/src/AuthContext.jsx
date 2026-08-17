import { createContext, useContext, useState } from "react";
import { api } from "./apiClient";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem("token"));
  const [username, setUsername] = useState(() => localStorage.getItem("username"));

  async function login(user, password) {
    const data = await api.login(user, password);
    setToken(data.token);
    setUsername(data.username);
    localStorage.setItem("token", data.token);
    localStorage.setItem("username", data.username);
  }

  function logout() {
    if (token) api.logout(token).catch(() => {});
    setToken(null);
    setUsername(null);
    localStorage.removeItem("token");
    localStorage.removeItem("username");
  }

  return (
    <AuthContext.Provider value={{ token, username, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
