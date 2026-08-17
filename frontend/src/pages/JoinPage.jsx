import { useEffect, useState } from "react";
import { useAuth } from "../AuthContext";
import { api } from "../apiClient";

export default function JoinPage() {
  const { token, username } = useAuth();
  const [courts, setCourts] = useState([]);
  const [courtId, setCourtId] = useState("");
  const [groupSize, setGroupSize] = useState(2);
  const [otherNames, setOtherNames] = useState(["", "", ""]);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.getCourts().then((data) => {
      setCourts(data);
      if (data.length && !courtId) setCourtId(String(data[0].id));
    });
  }, []);

  const neededOthers = groupSize - 1;

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    const usernames = [username, ...otherNames.slice(0, neededOthers).map((n) => n.trim())];
    if (usernames.some((n) => !n)) {
      setError("Please fill in all group member usernames.");
      return;
    }
    setSubmitting(true);
    try {
      const entry = await api.joinQueue(token, Number(courtId), usernames);
      setSuccess(
        entry.status === "active"
          ? "You're on the court now!"
          : "You're in the queue — check My Status for your position."
      );
      setOtherNames(["", "", ""]);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page page-narrow">
      <h1>Join a queue</h1>
      <form onSubmit={handleSubmit} className="form">
        <label>
          Court
          <select value={courtId} onChange={(e) => setCourtId(e.target.value)}>
            {courts.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          Group size
          <select value={groupSize} onChange={(e) => setGroupSize(Number(e.target.value))}>
            <option value={2}>2</option>
            <option value={4}>4</option>
          </select>
        </label>

        <label>
          You
          <input value={username} disabled />
        </label>

        {Array.from({ length: neededOthers }).map((_, i) => (
          <label key={i}>
            Player {i + 2}
            <input
              value={otherNames[i]}
              onChange={(e) => {
                const next = [...otherNames];
                next[i] = e.target.value;
                setOtherNames(next);
              }}
              required
            />
          </label>
        ))}

        {error && <p className="error">{error}</p>}
        {success && <p className="success">{success}</p>}
        <button type="submit" disabled={submitting || !courtId}>
          {submitting ? "Joining…" : "Join queue"}
        </button>
      </form>
    </div>
  );
}
