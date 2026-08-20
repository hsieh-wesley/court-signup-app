import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import { LogOut, ShieldCheck } from "lucide-react";
import { AuthProvider, useAuth } from "./AuthContext";
import { LocationProvider, useFacility } from "./LocationContext";
import LoginPage from "./pages/LoginPage";
import JoinPage from "./pages/JoinPage";
import OverviewPage from "./pages/OverviewPage";
import BoardPage from "./pages/BoardPage";
import AdminPage from "./pages/AdminPage";

function RequireAdmin({ children }) {
  const { token, isAdmin } = useAuth();
  if (!token || !isAdmin) return <Navigate to="/login" replace />;
  return children;
}

function LocationSwitcher() {
  const { locations, selectedLocationId, setSelectedLocationId } = useFacility();
  if (!locations.length) return null;
  return (
    <select
      className="location-switcher"
      value={selectedLocationId || ""}
      onChange={(e) => setSelectedLocationId(e.target.value)}
      aria-label="Facility"
    >
      {locations.map((loc) => (
        <option key={loc.id} value={loc.id}>
          {loc.name}
        </option>
      ))}
    </select>
  );
}

function Nav() {
  // `token`/`username` here only ever represent an Admin session — regular
  // players never hold one under the public kiosk model. No admin/staff
  // nav element is shown at all while logged out — the only way in is
  // typing "admin"/"staff" on the Join page — so a front-desk or courtside
  // kiosk left logged out shows nothing but the CourtFlow brand and
  // Join/Overview. Each physical kiosk is bound to one facility in
  // practice: an admin/staff signs in once to pick it (LocationSwitcher,
  // below, only renders for them), and the choice persists in that
  // browser (LocationContext -> localStorage) after they log back out —
  // the public never gets a live control to switch facilities themselves.
  const { token, username, isAdmin, logout } = useAuth();
  return (
    <nav className="nav">
      <NavLink to="/overview" className="nav-brand">
        <span className="wordmark">CourtFlow</span>
        <span className="tagline">Court &amp; Queue Management</span>
      </NavLink>
      <div className="nav-links">
        <NavLink to="/join">Join</NavLink>
        <NavLink to="/overview">Overview</NavLink>
      </div>
      <span className="spacer" />
      {token && isAdmin && (
        <div className="nav-account">
          <LocationSwitcher />
          <span className="nav-account-badge">
            <ShieldCheck size={14} />
            {username}
          </span>
          <NavLink to="/admin" className="btn btn-secondary btn-sm">
            Admin
          </NavLink>
          <button className="btn btn-ghost btn-sm" onClick={logout}>
            <LogOut size={14} />
            Log out
          </button>
        </div>
      )}
    </nav>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <LocationProvider>
        <Routes>
          <Route path="/board" element={<BoardPage />} />
          <Route
            path="*"
            element={
              <>
                <Nav />
                <Routes>
                  <Route path="/login" element={<LoginPage />} />
                  <Route path="/join" element={<JoinPage />} />
                  <Route path="/overview" element={<OverviewPage />} />
                  <Route
                    path="/admin"
                    element={
                      <RequireAdmin>
                        <AdminPage />
                      </RequireAdmin>
                    }
                  />
                  <Route path="/" element={<Navigate to="/overview" replace />} />
                </Routes>
              </>
            }
          />
        </Routes>
      </LocationProvider>
    </AuthProvider>
  );
}
