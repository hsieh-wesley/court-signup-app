import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./AuthContext";
import { LocationProvider, useFacility } from "./LocationContext";
import LoginPage from "./pages/LoginPage";
import JoinPage from "./pages/JoinPage";
import OverviewPage from "./pages/OverviewPage";
import StatusPage from "./pages/StatusPage";
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
    >
      {locations.map((loc) => (
        <option key={loc.id} value={loc.id}>
          {loc.name}
        </option>
      ))}
    </select>
  );
}

function FacilityHeader() {
  const { selectedLocation } = useFacility();
  return <h1 className="facility-header">{selectedLocation ? selectedLocation.name : " "}</h1>;
}

function Nav() {
  // `token`/`username` here only ever represent an Admin session — regular
  // players never hold one under the public kiosk model.
  const { token, username, isAdmin, logout } = useAuth();
  return (
    <nav className="nav">
      <span className="brand">Court Signup</span>
      <NavLink to="/join">Join</NavLink>
      <NavLink to="/overview">Overview</NavLink>
      <NavLink to="/status">My Status</NavLink>
      <LocationSwitcher />
      <span className="spacer" />
      {token && isAdmin ? (
        <>
          <span className="muted">Admin: {username}</span>
          <button onClick={logout}>Log out</button>
        </>
      ) : null}
      <NavLink to="/admin" className="admin-corner-link">
        {isAdmin ? "Admin" : "Admin sign in"}
      </NavLink>
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
                <FacilityHeader />
                <Nav />
                <Routes>
                  <Route path="/login" element={<LoginPage />} />
                  <Route path="/join" element={<JoinPage />} />
                  <Route path="/overview" element={<OverviewPage />} />
                  <Route path="/status" element={<StatusPage />} />
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
