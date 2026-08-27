/**
 * Service worker: the only place that talks to the local API.
 *
 * Content scripts run on employer pages, so they never hold the API base URL
 * or resume values themselves — they ask for a fill plan and get back only
 * what is about to be typed into the page in front of them.
 */

const DEFAULTS = {
  apiBase: "http://127.0.0.1:5057",
  quickApply: false,
  autoScan: true,
};

async function config() {
  const stored = await chrome.storage.local.get(DEFAULTS);
  return { ...DEFAULTS, ...stored };
}

async function api(path, { method = "GET", body } = {}) {
  const { apiBase } = await config();
  const response = await fetch(`${apiBase}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      detail = (await response.json()).error || detail;
    } catch (_) {
      /* response wasn't JSON; keep the status */
    }
    throw new Error(detail);
  }
  return response.json();
}

const HANDLERS = {
  async ping() {
    const { apiBase } = await config();
    const health = await api("/api/health");
    return { ok: true, apiBase, db: health.db };
  },

  async settings() {
    const local = await config();
    let server = {};
    try {
      server = await api("/api/settings");
    } catch (_) {
      /* dashboard may be offline; local settings still apply */
    }
    return { ...local, server };
  },

  async saveSettings({ values }) {
    const local = {};
    for (const key of Object.keys(DEFAULTS)) {
      if (key in values) local[key] = values[key];
    }
    if (Object.keys(local).length) await chrome.storage.local.set(local);
    const serverKeys = ["quick_apply", "include_eeo_answers", "min_score"];
    const serverValues = {};
    for (const key of serverKeys) if (key in values) serverValues[key] = values[key];
    if (Object.keys(serverValues).length) {
      await api("/api/settings", { method: "PUT", body: serverValues });
    }
    return HANDLERS.settings();
  },

  async analyze({ url, host, fields }) {
    return api("/api/forms/analyze", { method: "POST", body: { url, host, fields } });
  },

  async learn({ signature, canonical, ats, host }) {
    return api("/api/forms/learn", { method: "POST", body: { signature, canonical, ats, host } });
  },

  async logFill({ url, ats, filled, skipped, status, company, title }) {
    return api("/api/forms/log", {
      method: "POST",
      body: { url, ats, filled, skipped, status, company, title },
    });
  },

  async recentApplications() {
    const { applications } = await api("/api/applications");
    return { applications: applications.slice(0, 8) };
  },

  async knownFields() {
    return api("/api/forms/fields");
  },

  async resumeSummary() {
    const { resume } = await api("/api/resume");
    const profile = resume.profile || {};
    return {
      name: [profile.first_name, profile.last_name].filter(Boolean).join(" "),
      email: profile.email,
      skills: (resume.skills || []).length,
    };
  },

  /** Content script reports how many fields it can fill; show it on the icon. */
  async badge({ count }, sender) {
    const tabId = sender?.tab?.id;
    if (tabId == null) return { ok: true };
    await chrome.action.setBadgeBackgroundColor({ tabId, color: "#2563eb" });
    await chrome.action.setBadgeText({ tabId, text: count ? String(count) : "" });
    return { ok: true };
  },
};

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const handler = HANDLERS[message?.type];
  if (!handler) {
    sendResponse({ error: `unknown message type: ${message?.type}` });
    return false;
  }
  handler(message.payload || {}, sender)
    .then((data) => sendResponse({ data }))
    .catch((error) => sendResponse({ error: error.message }));
  return true; // keep the channel open for the async response
});

chrome.runtime.onInstalled.addListener(async () => {
  const current = await chrome.storage.local.get(DEFAULTS);
  await chrome.storage.local.set({ ...DEFAULTS, ...current });
});
