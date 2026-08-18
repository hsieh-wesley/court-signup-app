const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

async function request(path, { method = "GET", body, token } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Token ${token}`;

  const res = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }

  if (!res.ok) {
    const firstFieldError = data && typeof data === "object"
      ? Object.values(data).find((v) => Array.isArray(v) && v.length)?.[0]
      : null;
    const message = data?.detail || firstFieldError || "Request failed.";
    throw new Error(message);
  }
  return data;
}

export const api = {
  login: (username, password) =>
    request("/auth/login/", { method: "POST", body: { username, password } }),
  logout: (token) => request("/auth/logout/", { method: "POST", token }),
  getCourts: () => request("/courts/"),
  getMyStatus: (token) => request("/me/status/", { token }),
  joinQueue: (token, courtId, pairs) =>
    request("/queue-entries/", {
      method: "POST",
      token,
      body: { court_id: courtId, pairs },
    }),
  joinOpenSlot: (token, entryId, usernames) =>
    request(`/queue-entries/${entryId}/join/`, {
      method: "POST",
      token,
      body: { usernames },
    }),
  unsignPair: (token, entryId, pairId) =>
    request(`/queue-entries/${entryId}/unsign/`, {
      method: "POST",
      token,
      body: { pair_id: pairId },
    }),
};

export const adminApi = {
  listPlayers: (token) => request("/admin/players/", { token }),
  createPlayer: (token, { displayName, username, enableLogin }) =>
    request("/admin/players/", {
      method: "POST",
      token,
      body: { display_name: displayName, username, enable_login: enableLogin },
    }),
  editPlayer: (token, playerId, { displayName, username }) =>
    request(`/admin/players/${playerId}/`, {
      method: "PATCH",
      token,
      body: { display_name: displayName, username },
    }),
  addLogin: (token, playerId, username) =>
    request(`/admin/players/${playerId}/login/`, {
      method: "POST",
      token,
      body: { username },
    }),
  disableLogin: (token, playerId) =>
    request(`/admin/players/${playerId}/disable-login/`, { method: "POST", token }),
  resetPassword: (token, playerId) =>
    request(`/admin/players/${playerId}/reset-password/`, { method: "POST", token }),
  deactivatePlayer: (token, playerId) =>
    request(`/admin/players/${playerId}/deactivate/`, { method: "POST", token }),
  createTestPlayers: (token, count = 8) =>
    request("/admin/players/bulk-test/", { method: "POST", token, body: { count } }),
  createCourt: (token, { name, capacity }) =>
    request("/admin/courts/", { method: "POST", token, body: { name, capacity } }),
  removePlayerFromCourt: (token, courtId, username) =>
    request(`/admin/courts/${courtId}/remove-player/`, {
      method: "POST",
      token,
      body: { username },
    }),
  dropCourt: (token, courtId) =>
    request(`/admin/courts/${courtId}/drop/`, { method: "POST", token }),
  deactivateCourt: (token, courtId) =>
    request(`/admin/courts/${courtId}/deactivate/`, { method: "POST", token }),
};
