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
    const message = data?.detail || data?.usernames?.[0] || "Request failed.";
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
  joinQueue: (token, courtId, usernames) =>
    request("/queue-entries/", {
      method: "POST",
      token,
      body: { court_id: courtId, usernames },
    }),
  unsign: (token, entryId, usernames) =>
    request(`/queue-entries/${entryId}/unsign/`, {
      method: "POST",
      token,
      body: { usernames },
    }),
};
