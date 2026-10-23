import { useEffect, useState } from "react";
import { api, ApiError, getToken, setToken, type User } from "./api";
import Dashboard from "./components/Dashboard";
import Login from "./components/Login";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(Boolean(getToken()));

  useEffect(() => {
    if (!getToken()) return;
    api
      .me()
      .then(setUser)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) setToken(null);
      })
      .finally(() => setChecking(false));
  }, []);

  const logout = () => {
    setToken(null);
    setUser(null);
  };

  if (checking) return <p className="center muted">Loading…</p>;
  if (!user) return <Login onLogin={setUser} />;
  return <Dashboard user={user} onLogout={logout} />;
}
