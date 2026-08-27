import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import MatchBreakdown from "../components/MatchBreakdown.jsx";
import ScoreBadge from "../components/ScoreBadge.jsx";
import { api } from "../lib/api.js";

export default function JobDetail({ onChange }) {
  const { id } = useParams();
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = () =>
    api
      .job(id)
      .then(setJob)
      .catch((err) => setError(err.message));

  useEffect(() => {
    load();
  }, [id]);

  const track = async (status) => {
    setSaving(true);
    try {
      await api.createApplication({ job_id: Number(id), status, method: "manual" });
      await load();
      onChange?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  if (error) return <p className="error">{error}</p>;
  if (!job) return <p className="muted">Loading…</p>;

  return (
    <section className="detail">
      <Link className="back" to="/jobs">
        ← Back to jobs
      </Link>

      <div className="detail-head">
        <ScoreBadge score={job.score} />
        <div>
          <h2>{job.title}</h2>
          <p className="job-meta">
            <strong>{job.company}</strong>
            {job.location && <span>· {job.location}</span>}
            {job.remote && <span className="tag">Remote</span>}
            {job.posted_at && <span>· posted {String(job.posted_at).slice(0, 10)}</span>}
          </p>
        </div>
        <div className="detail-actions">
          <a className="primary" href={job.url} target="_blank" rel="noreferrer">
            Open and apply ↗
          </a>
          {job.application_status ? (
            <span className={`pill status ${job.application_status}`}>
              tracked · {job.application_status}
            </span>
          ) : (
            <button className="ghost" onClick={() => track("applied")} disabled={saving}>
              Mark as applied
            </button>
          )}
        </div>
      </div>

      <p className="hint">
        Open the posting, then use the extension's panel to review and fill the form. It never
        submits for you.
      </p>

      <div className="detail-grid">
        <article className="card">
          <h3>Why this matched</h3>
          <MatchBreakdown breakdown={job.breakdown} />
        </article>

        <article className="card">
          <h3>Posting</h3>
          <p className="description">{job.description || "No description captured for this posting."}</p>
        </article>
      </div>
    </section>
  );
}
