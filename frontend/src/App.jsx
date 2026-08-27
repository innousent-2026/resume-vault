import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";

import { api } from "./lib/api.js";
import Applications from "./pages/Applications.jsx";
import JobDetail from "./pages/JobDetail.jsx";
import Jobs from "./pages/Jobs.jsx";
import Settings from "./pages/Settings.jsx";

export default function App() {
  const [stats, setStats] = useState(null);
  const [offline, setOffline] = useState(false);

  const refreshStats = () =>
    api
      .stats()
      .then((data) => {
        setStats(data);
        setOffline(false);
      })
      .catch(() => setOffline(true));

  useEffect(() => {
    refreshStats();
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="mark" aria-hidden="true" />
          <div>
            <h1>Job Search</h1>
            <p>Discover, match, apply, track</p>
          </div>
        </div>
        <nav>
          <NavLink to="/jobs">Jobs</NavLink>
          <NavLink to="/applications">Applications</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
        <div className="counters">
          {offline ? (
            <span className="pill warn">API offline — start backend/app.py</span>
          ) : (
            stats && (
              <>
                <span className="pill">{stats.jobs} jobs</span>
                <span className="pill good">{stats.strong_matches} strong</span>
                <span className="pill">{stats.applications} applications</span>
              </>
            )
          )}
        </div>
      </header>

      <main>
        <Routes>
          <Route path="/" element={<Navigate to="/jobs" replace />} />
          <Route path="/jobs" element={<Jobs onChange={refreshStats} />} />
          <Route path="/jobs/:id" element={<JobDetail onChange={refreshStats} />} />
          <Route path="/applications" element={<Applications onChange={refreshStats} />} />
          <Route path="/settings" element={<Settings onChange={refreshStats} />} />
          <Route path="*" element={<p className="empty">Nothing here.</p>} />
        </Routes>
      </main>
    </div>
  );
}
