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
    const error = new Error(data?.detail || firstFieldError || "Request failed.");
    error.status = res.status;
    throw error;
  }
  return data;
}

function qs(params) {
  const entries = Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null && v !== "");
  if (!entries.length) return "";
  return "?" + new URLSearchParams(entries).toString();
}

export const api = {
  login: (username, password, locationId) =>
    request("/auth/login/", {
      method: "POST",
      body: { username, password, location_id: locationId },
    }),
  logout: (token) => request("/auth/logout/", { method: "POST", token }),
  getLocations: () => request("/locations/"),
  checkUsername: (username) => request(`/players/check-username/${qs({ username })}`),
  // Creates the account; never returns a session — the kiosk never ends
  // up "logged in" as the new player.
  registerPlayer: (username, locationId) =>
    request("/players/register/", {
      method: "POST",
      body: { username, location_id: locationId },
    }),
  getCourts: (locationId) => request(`/courts/${qs({ location_id: locationId })}`),
  // Public kiosk endpoints below take credentials directly in the body —
  // no token, nothing persisted client-side.
  checkStatus: (username, password, locationId) =>
    request("/me/status/", {
      method: "POST",
      body: { username, password, location_id: locationId },
    }),
  joinQueue: (courtId, pairs) =>
    request("/queue-entries/", {
      method: "POST",
      body: { court_id: courtId, pairs },
    }),
  joinOpenSlot: (entryId, credentials) =>
    request(`/queue-entries/${entryId}/join/`, {
      method: "POST",
      body: { credentials },
    }),
  unsignPair: (entryId, pairId, username, password) =>
    request(`/queue-entries/${entryId}/unsign/`, {
      method: "POST",
      body: { pair_id: pairId, username, password },
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
  createCourt: (token, { locationId, number, capacity }) =>
    request("/admin/courts/", {
      method: "POST",
      token,
      body: { location_id: locationId, number, capacity },
    }),
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
  listLocations: (token) => request("/admin/locations/", { token }),
  createLocation: (token, { name, courtCount }) =>
    request("/admin/locations/", {
      method: "POST",
      token,
      body: { name, court_count: courtCount },
    }),
  editLocation: (token, locationId, { name, isActive }) =>
    request(`/admin/locations/${locationId}/`, {
      method: "PATCH",
      token,
      body: { name, is_active: isActive },
    }),
  setCourtCount: (token, locationId, count) =>
    request(`/admin/locations/${locationId}/court-count/`, {
      method: "POST",
      token,
      body: { count },
    }),
  getLoginHistory: (token, filters) =>
    request(`/admin/history/logins/${qs(filters)}`, { token }),
  getCourtActivityHistory: (token, filters) =>
    request(`/admin/history/court-activity/${qs(filters)}`, { token }),
};
