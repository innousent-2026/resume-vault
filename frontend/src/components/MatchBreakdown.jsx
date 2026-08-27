const LABELS = {
  content: "Posting overlap",
  skills: "Your skills",
  title: "Title fit",
  keywords: "Your keywords",
};

/** Shows why a job scored what it did — the number alone isn't actionable. */
export default function MatchBreakdown({ breakdown }) {
  if (!breakdown) return <p className="muted">Not scored yet.</p>;
  const { components, multipliers, matched_skills: matched, missing_skills: missing } = breakdown;

  return (
    <div className="breakdown">
      <p className="summary">{breakdown.summary}</p>

      <div className="bars">
        {Object.entries(components).map(([key, value]) => (
          <div className="bar-row" key={key}>
            <span className="bar-label">{LABELS[key] || key}</span>
            <span className="bar-track">
              <span className="bar-fill" style={{ width: `${Math.round(value * 100)}%` }} />
            </span>
            <span className="bar-value">{Math.round(value * 100)}%</span>
          </div>
        ))}
      </div>

      {breakdown.notes?.length > 0 && (
        <ul className="notes">
          {breakdown.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}

      {Object.entries(multipliers).some(([, v]) => v < 1) && (
        <p className="muted small">
          Adjusted for{" "}
          {Object.entries(multipliers)
            .filter(([, v]) => v < 1)
            .map(([k, v]) => `${k} (×${v})`)
            .join(", ")}
        </p>
      )}

      {matched?.length > 0 && (
        <p className="chips">
          {matched.map((skill) => (
            <span className="chip good" key={skill}>
              {skill}
            </span>
          ))}
        </p>
      )}
      {missing?.length > 0 && (
        <p className="chips">
          <span className="muted small">Not mentioned:</span>
          {missing.map((skill) => (
            <span className="chip" key={skill}>
              {skill}
            </span>
          ))}
        </p>
      )}
    </div>
  );
}
