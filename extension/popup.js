/** Popup: connection status, the three switches that matter, and recent activity. */

const $ = (id) => document.getElementById(id);

function send(type, payload = {}) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type, payload }, (response) => {
      if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
      if (!response) return reject(new Error("no response from background"));
      if (response.error) return reject(new Error(response.error));
      resolve(response.data);
    });
  });
}

async function refresh() {
  let settings;
  try {
    settings = await send("settings");
  } catch (error) {
    settings = { apiBase: "http://127.0.0.1:5057", server: {} };
  }
  $("api-base").value = settings.apiBase;
  $("auto-scan").checked = Boolean(settings.autoScan);
  $("quick-apply").checked = Boolean(settings.server?.quick_apply ?? settings.quickApply);
  $("eeo").checked = Boolean(settings.server?.include_eeo_answers);
  $("open-dashboard").href = "http://127.0.0.1:5173";

  try {
    await send("ping");
    $("status-dot").className = "dot ok";
    $("status-text").textContent = "Connected";
    const resume = await send("resumeSummary");
    $("resume-line").textContent = `${resume.name} · ${resume.email} · ${resume.skills} skills on file`;
  } catch (error) {
    $("status-dot").className = "dot bad";
    $("status-text").textContent = "Backend offline";
    $("resume-line").textContent = "Start it with: python backend/app.py";
    return;
  }

  try {
    const { applications } = await send("recentApplications");
    $("recent").innerHTML = applications.length
      ? applications
          .map(
            (a) =>
              `<li><span class="co">${escapeHtml(a.company)}</span> — ${escapeHtml(a.title)}<br>
               <span class="muted">${a.status} · ${(a.applied_at || a.created_at || "").slice(0, 10)}</span></li>`
          )
          .join("")
      : '<li class="muted">Nothing logged yet.</li>';
  } catch (error) {
    $("recent").innerHTML = `<li class="muted">${escapeHtml(error.message)}</li>`;
  }
}

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

$("scan").addEventListener("click", async () => {
  $("scan-result").textContent = "Scanning…";
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) return;
  try {
    // activeTab lets us inject here even on sites the manifest doesn't list.
    await chrome.scripting.insertCSS({ target: { tabId: tab.id }, files: ["styles.css"] });
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
    const response = await chrome.tabs.sendMessage(tab.id, { type: "scanNow" });
    const matched = response?.data?.matched ?? 0;
    $("scan-result").textContent = matched
      ? `${matched} fields ready — see the panel on the page.`
      : "No application fields matched on this page.";
  } catch (error) {
    $("scan-result").textContent = `Couldn't scan: ${error.message}`;
  }
});

$("save-api").addEventListener("click", async () => {
  await send("saveSettings", { values: { apiBase: $("api-base").value.replace(/\/$/, "") } });
  refresh();
});

$("auto-scan").addEventListener("change", (event) =>
  send("saveSettings", { values: { autoScan: event.target.checked } })
);
$("quick-apply").addEventListener("change", (event) =>
  send("saveSettings", { values: { quickApply: event.target.checked, quick_apply: event.target.checked } })
);
$("eeo").addEventListener("change", (event) =>
  send("saveSettings", { values: { include_eeo_answers: event.target.checked } })
);

refresh();
