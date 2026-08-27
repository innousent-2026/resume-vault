import { useEffect, useState } from "react";

import { api } from "../lib/api.js";

const SOURCE_KINDS = [
  { kind: "greenhouse", field: "token", hint: "board token from boards.greenhouse.io/<token>" },
  { kind: "lever", field: "token", hint: "company slug from jobs.lever.co/<slug>" },
  { kind: "ashby", field: "token", hint: "slug from jobs.ashbyhq.com/<slug>" },
  { kind: "smartrecruiters", field: "token", hint: "company id from careers.smartrecruiters.com/<id>" },
  { kind: "workday", field: "url", hint: "https://<host>/wday/cxs/<tenant>/<site>/jobs" },
  { kind: "generic", field: "url", hint: "any careers page to crawl for job links" },
];

export default function Settings({ onChange }) {
  const [sources, setSources] = useState([]);
  const [settings, setSettings] = useState(null);
  const [resume, setResume] = useState(null);
  const [draft, setDraft] = useState({ kind: "greenhouse", name: "", token: "", url: "" });
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  const load = () => {
    api.sources().then((data) => setSources(data.sources)).catch((err) => setError(err.message));
    api.settings().then(setSettings).catch((err) => setError(err.message));
    api.resume().then((data) => setResume(data.resume)).catch((err) => setError(err.message));
  };

  useEffect(() => {
    load();
  }, []);

  const addSource = async (event) => {
    event.preventDefault();
    setError(null);
    try {
      await api.addSource(draft);
      setDraft({ kind: draft.kind, name: "", token: "", url: "" });
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  const savePreferences = async (event) => {
    event.preventDefault();
    setNotice(null);
    const form = new FormData(event.target);
    const next = {
      ...resume,
      preferences: {
        ...resume.preferences,
        titles: splitList(form.get("titles")),
        keywords: splitList(form.get("keywords")),
        exclude_keywords: splitList(form.get("exclude_keywords")),
        locations: splitList(form.get("locations")),
        min_salary: Number(form.get("min_salary")) || null,
        remote_only: form.get("remote_only") === "on",
      },
    };
    try {
      await api.saveResume(next);
      setResume(next);
      const { scored } = await api.rescore();
      setNotice(`Preferences saved — rescored ${scored} postings.`);
      onChange?.();
    } catch (err) {
      setError(err.message);
    }
  };

  const toggleSetting = async (key, value) => {
    const updated = await api.saveSettings({ [key]: value });
    setSettings(updated);
  };

  const active = SOURCE_KINDS.find((s) => s.kind === draft.kind);

  return (
    <section className="settings">
      <h2>Settings</h2>
      {error && <p className="error">{error}</p>}
      {notice && <p className="notice">{notice}</p>}

      <article className="card">
        <h3>Career sites</h3>
        <p className="muted small">
          Each employer's job board is scraped through its ATS API. Add the companies you're
          targeting.
        </p>
        <ul className="sources">
          {sources.map((source) => (
            <li key={source.id}>
              <span className="tag subtle">{source.kind}</span>
              <strong>{source.name}</strong>
              <span className="muted small">
                {source.last_error
                  ? `error: ${source.last_error}`
                  : source.last_scraped_at
                    ? `last scraped ${source.last_scraped_at.slice(0, 16).replace("T", " ")}`
                    : "never scraped"}
              </span>
              <button
                className="link danger"
                onClick={() => api.deleteSource(source.id).then(load)}
              >
                Remove
              </button>
            </li>
          ))}
          {sources.length === 0 && <li className="muted">No sources yet.</li>}
        </ul>

        <form className="source-form" onSubmit={addSource}>
          <select
            value={draft.kind}
            onChange={(event) => setDraft({ ...draft, kind: event.target.value })}
          >
            {SOURCE_KINDS.map((s) => (
              <option key={s.kind} value={s.kind}>
                {s.kind}
              </option>
            ))}
          </select>
          <input
            placeholder="Company name"
            value={draft.name}
            onChange={(event) => setDraft({ ...draft, name: event.target.value })}
          />
          <input
            placeholder={active.hint}
            value={draft[active.field]}
            onChange={(event) => setDraft({ ...draft, [active.field]: event.target.value })}
            required
          />
          <button className="primary" type="submit">
            Add source
          </button>
        </form>
      </article>

      {resume && (
        <article className="card">
          <h3>Match preferences</h3>
          <p className="muted small">
            These drive the score. Everything else about your resume lives in{" "}
            <code>resume_data.json</code>.
          </p>
          <form className="prefs" onSubmit={savePreferences}>
            <label>
              Target titles
              <input name="titles" defaultValue={(resume.preferences?.titles || []).join(", ")} />
            </label>
            <label>
              Keywords that matter
              <input name="keywords" defaultValue={(resume.preferences?.keywords || []).join(", ")} />
            </label>
            <label>
              Exclude postings containing
              <input
                name="exclude_keywords"
                defaultValue={(resume.preferences?.exclude_keywords || []).join(", ")}
              />
            </label>
            <label>
              Preferred locations
              <input name="locations" defaultValue={(resume.preferences?.locations || []).join(", ")} />
            </label>
            <label>
              Salary floor
              <input name="min_salary" type="number" defaultValue={resume.preferences?.min_salary || ""} />
            </label>
            <label className="checkbox">
              <input name="remote_only" type="checkbox" defaultChecked={resume.preferences?.remote_only} />
              Remote roles only
            </label>
            <button className="primary" type="submit">
              Save and rescore
            </button>
          </form>
        </article>
      )}

      {settings && (
        <article className="card">
          <h3>Autofill</h3>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={Boolean(settings.quick_apply)}
              onChange={(event) => toggleSetting("quick_apply", event.target.checked)}
            />
            Quick apply — fill high-confidence fields as soon as a form is detected
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={Boolean(settings.include_eeo_answers)}
              onChange={(event) => toggleSetting("include_eeo_answers", event.target.checked)}
            />
            Answer EEO / demographic questions using the values in my resume file
          </label>
          <p className="muted small">
            The extension fills fields and stops. Reviewing the page and pressing Submit is always
            yours to do.
          </p>
        </article>
      )}
    </section>
  );
}

function splitList(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}
