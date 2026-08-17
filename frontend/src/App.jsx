import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./AuthContext";
import LoginPage from "./pages/LoginPage";
import JoinPage from "./pages/JoinPage";
import StatusPage from "./pages/StatusPage";
import BoardPage from "./pages/BoardPage";

function RequireAuth({ children }) {
  const { token } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  return children;
}

function Nav() {
  const { token, username, logout } = useAuth();
  return (
    <nav className="nav">
      <span className="brand">Court Signup</span>
      <NavLink to="/join">Join</NavLink>
      <NavLink to="/status">My Status</NavLink>
      <NavLink to="/board">Board</NavLink>
      <span className="spacer" />
      {token ? (
        <>
          <span className="muted">{username}</span>
          <button onClick={logout}>Log out</button>
        </>
      ) : (
        <NavLink to="/login">Sign in</NavLink>
      )}
    </nav>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/board" element={<BoardPage />} />
        <Route
          path="*"
          element={
            <>
              <Nav />
              <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route
                  path="/join"
                  element={
                    <RequireAuth>
                      <JoinPage />
                    </RequireAuth>
                  }
                />
                <Route
                  path="/status"
                  element={
                    <RequireAuth>
                      <StatusPage />
                    </RequireAuth>
                  }
                />
                <Route path="/" element={<Navigate to="/join" replace />} />
              </Routes>
            </>
          }
        />
      </Routes>
    </AuthProvider>
  );
}
