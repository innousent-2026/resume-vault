const BASE = import.meta.env.VITE_API_BASE || "";

async function request(path, { method = "GET", body } = {}) {
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

export const api = {
  health: () => request("/api/health"),
  stats: () => request("/api/stats"),

  jobs: (params = {}) => {
    const query = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== "" && v != null && v !== "any")
    );
    return request(`/api/jobs?${query}`);
  },
  job: (id) => request(`/api/jobs/${id}`),

  applications: () => request("/api/applications"),
  createApplication: (body) => request("/api/applications", { method: "POST", body }),
  updateApplication: (id, body) => request(`/api/applications/${id}`, { method: "PATCH", body }),

  sources: () => request("/api/sources"),
  addSource: (body) => request("/api/sources", { method: "POST", body }),
  deleteSource: (id) => request(`/api/sources/${id}`, { method: "DELETE" }),
  scrape: (body = {}) => request("/api/scrape", { method: "POST", body }),
  rescore: () => request("/api/rescore", { method: "POST" }),

  resume: () => request("/api/resume"),
  saveResume: (body) => request("/api/resume", { method: "PUT", body }),

  settings: () => request("/api/settings"),
  saveSettings: (body) => request("/api/settings", { method: "PUT", body }),
};

export const APPLICATION_STATUSES = [
  "draft", "applied", "interviewing", "offer", "rejected", "withdrawn",
];
