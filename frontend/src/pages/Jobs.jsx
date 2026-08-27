import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import ScoreBadge from "../components/ScoreBadge.jsx";
import { api } from "../lib/api.js";

const DEFAULT_FILTERS = { q: "", min_score: 45, remote: "any", applied: "false", sort: "score" };

export default function Jobs({ onChange }) {
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [scraping, setScraping] = useState(false);
  const [notice, setNotice] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    api
      .jobs({ ...filters, limit: 100 })
      .then((data) => {
        setJobs(data.jobs);
        setError(null);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [filters]);

  useEffect(() => {
    const timer = setTimeout(load, 200); // debounce the search box
    return () => clearTimeout(timer);
  }, [load]);

  const set = (key) => (event) => {
    const value = event.target.type === "checkbox" ? event.target.checked : event.target.value;
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const runScrape = async () => {
    setScraping(true);
    setNotice(null);
    try {
      const report = await api.scrape();
      const failures = report.sources.filter((s) => s.error);
      setNotice(
        `${report.new} new, ${report.updated} refreshed, ${report.scored} scored` +
          (failures.length ? ` · ${failures.length} source(s) failed: ${failures.map((f) => f.name).join(", ")}` : "")
      );
      load();
      onChange?.();
    } catch (err) {
      setNotice(`Scrape failed: ${err.message}`);
    } finally {
      setScraping(false);
    }
  };

  return (
    <section>
      <div className="page-head">
        <h2>Matched jobs</h2>
        <button className="primary" onClick={runScrape} disabled={scraping}>
          {scraping ? "Scraping…" : "Scrape career sites"}
        </button>
      </div>
      {notice && <p className="notice">{notice}</p>}

      <div className="filters">
        <input
          type="search"
          placeholder="Search title, company or description"
          value={filters.q}
          onChange={set("q")}
        />
        <label>
          Min score
          <input
            type="range"
            min="0"
            max="100"
            step="5"
            value={filters.min_score}
            onChange={set("min_score")}
          />
          <b>{filters.min_score}</b>
        </label>
        <label>
          Remote
          <select value={filters.remote} onChange={set("remote")}>
            <option value="any">Any</option>
            <option value="true">Remote only</option>
            <option value="false">On-site</option>
          </select>
        </label>
        <label>
          Show
          <select value={filters.applied} onChange={set("applied")}>
            <option value="false">Not yet applied</option>
            <option value="true">Applied</option>
            <option value="any">All</option>
          </select>
        </label>
        <label>
          Sort
          <select value={filters.sort} onChange={set("sort")}>
            <option value="score">Best match</option>
            <option value="date">Newest</option>
            <option value="company">Company</option>
          </select>
        </label>
      </div>

      {error && <p className="error">{error}</p>}
      {loading && <p className="muted">Loading…</p>}
      {!loading && !error && jobs.length === 0 && (
        <p className="empty">
          No jobs match these filters. Add career sites in <Link to="/settings">Settings</Link>, then
          scrape.
        </p>
      )}

      <ul className="job-list">
        {jobs.map((job) => (
          <li key={job.id} className="job-card">
            <ScoreBadge score={job.score} />
            <div className="job-main">
              <Link className="job-title" to={`/jobs/${job.id}`}>
                {job.title}
              </Link>
              <div className="job-meta">
                <strong>{job.company}</strong>
                {job.location && <span>· {job.location}</span>}
                {job.remote && <span className="tag">Remote</span>}
                {job.salary_max && (
                  <span>
                    · ${(job.salary_min || job.salary_max).toLocaleString()}–$
                    {job.salary_max.toLocaleString()}
                  </span>
                )}
                <span className="tag subtle">{job.source_kind}</span>
              </div>
              {job.breakdown?.summary && <p className="job-why">{job.breakdown.summary}</p>}
            </div>
            <div className="job-actions">
              {job.application_status ? (
                <span className={`pill status ${job.application_status}`}>{job.application_status}</span>
              ) : (
                <a className="ghost" href={job.url} target="_blank" rel="noreferrer">
                  Open posting ↗
                </a>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
