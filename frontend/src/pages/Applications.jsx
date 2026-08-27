import { Fragment, useEffect, useState } from "react";

import StatusSelect from "../components/StatusSelect.jsx";
import { api } from "../lib/api.js";

export default function Applications({ onChange }) {
  const [applications, setApplications] = useState([]);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = () =>
    api
      .applications()
      .then((data) => setApplications(data.applications))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));

  useEffect(() => {
    load();
  }, []);

  const update = async (id, changes) => {
    setApplications((prev) => prev.map((a) => (a.id === id ? { ...a, ...changes } : a)));
    try {
      await api.updateApplication(id, changes);
      onChange?.();
    } catch (err) {
      setError(err.message);
      load();
    }
  };

  const counts = applications.reduce((acc, a) => ({ ...acc, [a.status]: (acc[a.status] || 0) + 1 }), {});

  if (loading) return <p className="muted">Loading…</p>;

  return (
    <section>
      <div className="page-head">
        <h2>Applications</h2>
        <div className="counters">
          {Object.entries(counts).map(([status, count]) => (
            <span className={`pill status ${status}`} key={status}>
              {count} {status}
            </span>
          ))}
        </div>
      </div>
      {error && <p className="error">{error}</p>}

      {applications.length === 0 && (
        <p className="empty">
          Nothing tracked yet. Applications appear here when you mark a job applied, or when the
          extension logs a filled form.
        </p>
      )}

      <table className="applications">
        <thead>
          <tr>
            <th>Company</th>
            <th>Role</th>
            <th>Status</th>
            <th>Date</th>
            <th>Notes</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {applications.map((application) => (
            <Fragment key={application.id}>
              <tr>
                <td>
                  <strong>{application.company}</strong>
                  <div className="muted small">{application.method || "manual"}</div>
                </td>
                <td>
                  {application.url ? (
                    <a href={application.url} target="_blank" rel="noreferrer">
                      {application.title}
                    </a>
                  ) : (
                    application.title
                  )}
                </td>
                <td>
                  <StatusSelect
                    value={application.status}
                    onChange={(status) => update(application.id, { status })}
                  />
                </td>
                <td className="muted small">
                  {(application.applied_at || application.created_at || "").slice(0, 10)}
                </td>
                <td>
                  <input
                    className="notes"
                    defaultValue={application.notes || ""}
                    placeholder="Add a note"
                    onBlur={(event) => {
                      if (event.target.value !== (application.notes || "")) {
                        update(application.id, { notes: event.target.value });
                      }
                    }}
                  />
                </td>
                <td>
                  {application.submissions?.length > 0 && (
                    <button
                      className="link"
                      onClick={() => setExpanded(expanded === application.id ? null : application.id)}
                    >
                      {expanded === application.id ? "Hide" : "Form log"}
                    </button>
                  )}
                </td>
              </tr>
              {expanded === application.id && (
                <tr className="submission-row">
                  <td colSpan={6}>
                    {application.submissions.map((submission) => (
                      <div className="submission" key={submission.id}>
                        <div className="muted small">
                          {submission.ats || "unknown ATS"} · {submission.created_at.slice(0, 16).replace("T", " ")} ·{" "}
                          {submission.submitted ? "submitted" : "filled, submitted by you"}
                        </div>
                        <ul>
                          {submission.filled.map((field, index) => (
                            <li key={index}>
                              <code>{field.canonical}</code> → {field.value_preview}
                            </li>
                          ))}
                        </ul>
                        {submission.skipped.length > 0 && (
                          <div className="muted small">
                            Left blank: {submission.skipped.map((s) => s.label).filter(Boolean).join(", ")}
                          </div>
                        )}
                      </div>
                    ))}
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </section>
  );
}
