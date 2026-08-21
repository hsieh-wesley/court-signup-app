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
  // 1 or 2 groups of 2 {username,password} credentials — same shape as
  // joinQueue's `pairs`, so Overview's Unsign widget can reuse the same
  // 2-vs-4 toggle. Looks up each group's shared pair directly, no pair_id
  // needed.
  quickUnsign: (pairs) =>
    request("/pairs/unsign/", {
      method: "POST",
      body: { pairs },
    }),
  // Phone-only check-in for a member — no password. A match draws and
  // returns a fresh animal-only password; no session/token is created.
  memberCheckIn: (phoneNumber, locationId) =>
    request("/players/check-in/", {
      method: "POST",
      body: { phone_number: phoneNumber, location_id: locationId },
    }),
};

export const adminApi = {
  listPlayers: (token, locationId) =>
    request(`/admin/players/${qs({ location_id: locationId })}`, { token }),
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
  deletePlayer: (token, playerId) =>
    request(`/admin/players/${playerId}/delete/`, { method: "POST", token }),
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
  deleteLocation: (token, locationId) =>
    request(`/admin/locations/${locationId}/delete/`, { method: "POST", token }),
  getLoginHistory: (token, filters) =>
    request(`/admin/history/logins/${qs(filters)}`, { token }),
  getCourtActivityHistory: (token, filters) =>
    request(`/admin/history/court-activity/${qs(filters)}`, { token }),
  listMemberships: (token) => request("/admin/memberships/", { token }),
  // Also used to renew a lapsed member — pass their existing username and
  // the backend reuses that account rather than creating a duplicate.
  startMembership: (token, { username, phoneNumber, expiresAt, locationId }) =>
    request("/admin/memberships/", {
      method: "POST",
      token,
      body: {
        username,
        phone_number: phoneNumber,
        expires_at: expiresAt,
        location_id: locationId ?? null,
      },
    }),
  // locationId omitted (undefined) leaves the existing scope untouched;
  // locationId: null explicitly sets it to "All Locations" — undefined
  // keys drop out of the JSON body entirely, null does not, so the two
  // are distinguishable on the backend.
  editMembership: (token, playerId, { phoneNumber, expiresAt, locationId }) =>
    request(`/admin/memberships/${playerId}/`, {
      method: "PATCH",
      token,
      body: { phone_number: phoneNumber, expires_at: expiresAt, location_id: locationId },
    }),
  // Admin/superuser-only — staff cannot call this on itself.
  resetStaffPassword: (token) =>
    request("/admin/staff/reset-password/", { method: "POST", token }),
};
