/**
 * Content script: find the application form, ask the backend what it would
 * type, show the user, and fill only what they approve.
 *
 * Hard rule enforced here, not just in the UI: this script never clicks a
 * submit button and never dispatches a form submit event. It sets field values
 * and stops. See `fillApproved`.
 */

(() => {
  if (window.__jaaLoaded) {
    window.__jaaRescan?.();
    return;
  }
  window.__jaaLoaded = true;

  const FIELD_SELECTOR =
    'input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=image]):not([type=reset]), select, textarea';
  const MIN_FIELDS_TO_OFFER = 3;

  let fieldElements = new Map(); // jaaId -> element
  let lastAnalysis = null;
  let panel = null;
  let fieldCounter = 0;
  let filledThisPage = [];

  // --- field harvesting ----------------------------------------------------

  const visible = (el) => {
    if (el.disabled || el.readOnly) return false;
    if (el.type === "hidden") return false;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return false;
    const style = getComputedStyle(el);
    return style.visibility !== "hidden" && style.display !== "none" && style.opacity !== "0";
  };

  const clean = (text) => (text || "").replace(/\s+/g, " ").trim().slice(0, 160);

  /** Work out the human-visible label for a control, trying the ways ATSes do it. */
  function labelFor(el) {
    if (el.id) {
      const explicit = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (explicit) return clean(explicit.textContent);
    }
    const labelledBy = el.getAttribute("aria-labelledby");
    if (labelledBy) {
      const text = labelledBy
        .split(/\s+/)
        .map((id) => document.getElementById(id)?.textContent || "")
        .join(" ");
      if (clean(text)) return clean(text);
    }
    const wrapping = el.closest("label");
    if (wrapping) return clean(wrapping.textContent);

    // Workday/SAP style: label sits in a sibling or parent wrapper.
    let node = el.parentElement;
    for (let depth = 0; node && depth < 4; depth += 1, node = node.parentElement) {
      const candidate = node.querySelector(
        "label, legend, .label, [class*='label'], [data-automation-id*='label']"
      );
      if (candidate && !candidate.contains(el)) {
        const text = clean(candidate.textContent);
        if (text) return text;
      }
    }
    return "";
  }

  function sectionHeading(el) {
    const section = el.closest("fieldset, section, [role='group'], div[class*='section']");
    const heading = section?.querySelector("legend, h1, h2, h3, h4, [role='heading']");
    return clean(heading?.textContent);
  }

  function optionsFor(el) {
    if (el.tagName === "SELECT") {
      return [...el.options]
        .filter((o) => o.value !== "" || clean(o.textContent))
        .map((o) => ({ label: clean(o.textContent), value: o.value }));
    }
    if (el.type === "radio" && el.name) {
      const group = document.querySelectorAll(`input[type=radio][name="${CSS.escape(el.name)}"]`);
      return [...group].map((radio) => ({ label: labelFor(radio) || radio.value, value: radio.value }));
    }
    return [];
  }

  function harvestFields() {
    fieldElements = new Map();
    const seenRadioGroups = new Set();
    const fields = [];

    for (const el of document.querySelectorAll(FIELD_SELECTOR)) {
      if (!visible(el)) continue;
      if (el.type === "radio") {
        const key = el.name || el.id;
        if (seenRadioGroups.has(key)) continue;
        seenRadioGroups.add(key);
      }
      const jaaId = `jaa-${(fieldCounter += 1)}`;
      el.dataset.jaaId = jaaId;
      fieldElements.set(jaaId, el);
      fields.push({
        field_id: jaaId,
        selector: el.name ? `[name="${el.name}"]` : el.id ? `#${el.id}` : "",
        name: el.name || "",
        id: el.id || "",
        label: labelFor(el),
        placeholder: el.placeholder || "",
        aria_label: el.getAttribute("aria-label") || "",
        autocomplete: el.getAttribute("autocomplete") || "",
        type: el.tagName === "SELECT" ? "select" : el.tagName === "TEXTAREA" ? "textarea" : el.type || "text",
        required: el.required || el.getAttribute("aria-required") === "true",
        section_heading: sectionHeading(el),
        options: optionsFor(el),
        has_value: Boolean(el.value),
      });
    }
    return fields;
  }

  /** Cheap check so we don't pester the backend on every page with a search box. */
  function looksLikeApplication(fields) {
    if (fields.length < MIN_FIELDS_TO_OFFER) return false;
    const haystack = fields
      .map((f) => `${f.label} ${f.name} ${f.id} ${f.placeholder}`.toLowerCase())
      .join(" ");
    const signals = [
      /resume|cv\b/, /cover letter/, /first name/, /last name/, /email/,
      /linked\s*in/, /work authoriz|sponsorship/, /apply|application/,
    ].filter((re) => re.test(haystack)).length;
    const hasFile = fields.some((f) => f.type === "file");
    return signals >= 2 || (hasFile && signals >= 1);
  }

  // --- backend ------------------------------------------------------------

  function send(type, payload = {}) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({ type, payload }, (response) => {
        if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
        if (!response) return reject(new Error("no response from extension background"));
        if (response.error) return reject(new Error(response.error));
        resolve(response.data);
      });
    });
  }

  // --- filling -------------------------------------------------------------

  /**
   * Set a value the way a user would, so React/Angular-controlled inputs
   * actually register the change.
   */
  function setValue(el, value) {
    if (el.tagName === "SELECT") {
      const match = [...el.options].find((o) => o.value === value || clean(o.textContent) === clean(value));
      if (!match) return false;
      el.value = match.value;
      el.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    }
    if (el.type === "radio") {
      const group = document.querySelectorAll(`input[type=radio][name="${CSS.escape(el.name)}"]`);
      const match = [...group].find(
        (radio) => radio.value === value || clean(labelFor(radio)) === clean(value)
      );
      if (!match) return false;
      match.click();
      return true;
    }
    if (el.type === "checkbox") {
      const wanted = /^(yes|true|1)$/i.test(String(value));
      if (el.checked !== wanted) el.click();
      return true;
    }
    const prototype = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
    el.focus();
    if (setter) setter.call(el, value);
    else el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.blur();
    return true;
  }

  function fillApproved(rows) {
    // Nothing in this function submits: no form.submit(), no click on a submit
    // control. Values go in, the user decides what happens next.
    const filled = [];
    const failed = [];
    for (const row of rows) {
      const el = fieldElements.get(row.field_id);
      if (!el) {
        failed.push({ ...row, reason: "field disappeared from the page" });
        continue;
      }
      let ok = false;
      try {
        ok = setValue(el, row.value);
      } catch (error) {
        failed.push({ ...row, reason: error.message });
        continue;
      }
      if (ok) {
        el.classList.add("jaa-filled");
        el.classList.remove("jaa-candidate", "jaa-review");
        filled.push({
          canonical: row.canonical,
          label: row.label,
          value_preview: String(row.value).slice(0, 40),
        });
      } else {
        failed.push({ ...row, reason: "no matching option" });
      }
    }
    filledThisPage = filledThisPage.concat(filled);
    return { filled, failed };
  }

  function highlight(analysis) {
    document.querySelectorAll(".jaa-candidate, .jaa-review").forEach((el) => {
      el.classList.remove("jaa-candidate", "jaa-review");
    });
    for (const row of analysis.plan) {
      const el = fieldElements.get(row.field_id);
      if (el) el.classList.add(row.autofill ? "jaa-candidate" : "jaa-review");
    }
  }

  // --- panel UI ------------------------------------------------------------

  const PANEL_CSS = `
    :host { all: initial; }
    .wrap {
      position: fixed; top: 16px; right: 16px; width: 380px; max-height: 86vh;
      display: flex; flex-direction: column; z-index: 2147483647;
      font: 13px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      color: #0f172a; background: #fff; border: 1px solid #d7dde5; border-radius: 12px;
      box-shadow: 0 18px 48px rgba(15, 23, 42, .22); overflow: hidden;
    }
    header { display: flex; align-items: center; gap: 8px; padding: 12px 14px;
      background: #0f172a; color: #fff; }
    header h1 { font-size: 13px; margin: 0; font-weight: 600; flex: 1; }
    header .ats { font-size: 11px; opacity: .75; text-transform: uppercase; letter-spacing: .04em; }
    header button { background: transparent; border: 0; color: #cbd5e1; font-size: 16px; cursor: pointer; }
    .summary { padding: 10px 14px; background: #f8fafc; border-bottom: 1px solid #e6ebf1; font-size: 12px; color: #475569; }
    .rows { overflow-y: auto; padding: 4px 0; flex: 1; }
    .row { display: grid; grid-template-columns: 18px 1fr; gap: 8px; padding: 9px 14px; border-bottom: 1px solid #f1f5f9; }
    .row.low { background: #fffbeb; }
    .row .label { font-weight: 600; font-size: 12px; }
    .row .canonical { font-size: 11px; color: #64748b; }
    .row input[type=text], .row textarea { width: 100%; box-sizing: border-box; margin-top: 4px;
      padding: 5px 7px; border: 1px solid #cbd5e1; border-radius: 6px; font: inherit; font-size: 12px; }
    .row textarea { resize: vertical; min-height: 56px; }
    .row .why { font-size: 11px; color: #94a3b8; margin-top: 3px; }
    .row.done .label::after { content: " ✓ filled"; color: #16a34a; font-weight: 600; }
    details { border-top: 1px solid #e6ebf1; }
    summary { padding: 9px 14px; cursor: pointer; font-size: 12px; color: #475569; background: #f8fafc; }
    .skipped { padding: 8px 14px; display: grid; gap: 8px; }
    .skipped .item { font-size: 12px; }
    .skipped .reason { color: #94a3b8; font-size: 11px; }
    .skipped select { width: 65%; margin-top: 4px; font-size: 11px; padding: 3px; }
    .skipped button { font-size: 11px; margin-left: 6px; padding: 3px 8px; cursor: pointer;
      border: 1px solid #cbd5e1; background: #fff; border-radius: 5px; }
    footer { padding: 12px 14px; border-top: 1px solid #e6ebf1; background: #fff; display: grid; gap: 8px; }
    .actions { display: flex; gap: 8px; }
    button.primary { flex: 1; background: #2563eb; color: #fff; border: 0; padding: 9px 12px;
      border-radius: 8px; font-weight: 600; cursor: pointer; font-size: 13px; }
    button.primary:disabled { background: #cbd5e1; cursor: default; }
    button.ghost { background: #fff; border: 1px solid #cbd5e1; border-radius: 8px; padding: 9px 12px; cursor: pointer; font-size: 12px; }
    .note { font-size: 11px; color: #64748b; }
    .note strong { color: #0f172a; }
    .status { font-size: 12px; color: #16a34a; }
    .status.error { color: #dc2626; }
  `;

  function renderPanel(analysis) {
    lastAnalysis = analysis;
    if (!panel) {
      const host = document.createElement("div");
      host.id = "jaa-panel-host";
      document.documentElement.appendChild(host);
      panel = host.attachShadow({ mode: "open" });
    }
    const plan = analysis.plan;
    const needsReview = plan.filter((p) => !p.autofill).length;

    panel.innerHTML = `
      <style>${PANEL_CSS}</style>
      <div class="wrap">
        <header>
          <h1>Application autofill</h1>
          <span class="ats">${analysis.ats}</span>
          <button data-act="close" title="Close">×</button>
        </header>
        <div class="summary">
          ${plan.length} of ${analysis.fields_seen} fields matched your resume${
            needsReview ? ` · <strong>${needsReview} need a look</strong>` : ""
          }${analysis.job ? ` · tracked job: ${escapeHtml(analysis.job.title)}` : ""}
        </div>
        <div class="rows">
          ${plan.map(planRow).join("") || '<div class="row"><span></span><span class="canonical">Nothing matched — map a field below.</span></div>'}
        </div>
        <details>
          <summary>Not filled (${analysis.skipped.length}) — map one if it should be</summary>
          <div class="skipped">${analysis.skipped.map(skippedRow).join("")}</div>
        </details>
        <footer>
          <div class="actions">
            <button class="primary" data-act="fill">Fill selected</button>
            <button class="ghost" data-act="log">Log to dashboard</button>
          </div>
          <div class="note"><strong>You submit.</strong> This extension fills fields and stops — it never clicks Submit.</div>
          <div class="status" data-role="status"></div>
        </footer>
      </div>
    `;

    panel.querySelectorAll("[data-act]").forEach((el) => {
      el.addEventListener("click", () => onAction(el.dataset.act));
    });
    panel.querySelectorAll("[data-map]").forEach((el) => {
      el.addEventListener("click", () => onMap(el.dataset.map));
    });
  }

  function planRow(row) {
    const value = String(row.value);
    const multiline = row.type === "textarea" || value.includes("\n") || value.length > 90;
    const editor = multiline
      ? `<textarea data-value="${row.field_id}" rows="4">${escapeHtml(value)}</textarea>`
      : `<input type="text" data-value="${row.field_id}" value="${escapeHtml(value)}">`;
    return `
      <div class="row ${row.autofill ? "" : "low"}" data-row="${row.field_id}">
        <input type="checkbox" data-check="${row.field_id}" ${row.autofill ? "checked" : ""}>
        <div>
          <div class="label">${escapeHtml(row.label || row.canonical)}${row.required ? " *" : ""}</div>
          <div class="canonical">${row.canonical} · ${Math.round(row.confidence * 100)}% confident</div>
          ${editor}
          <div class="why">${escapeHtml(row.reason)}</div>
        </div>
      </div>`;
  }

  function skippedRow(row, index) {
    const options = (window.__jaaFields || [])
      .map((f) => `<option value="${f}">${f}</option>`)
      .join("");
    return `
      <div class="item">
        <div><strong>${escapeHtml(row.label || row.signature)}</strong></div>
        <div class="reason">${escapeHtml(row.skip_reason)}</div>
        <select data-sig="${index}">${options}</select>
        <button data-map="${index}">Map</button>
      </div>`;
  }

  function escapeHtml(text) {
    return String(text ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  function status(message, isError = false) {
    const el = panel?.querySelector('[data-role="status"]');
    if (el) {
      el.textContent = message;
      el.className = `status${isError ? " error" : ""}`;
    }
  }

  async function onAction(action) {
    if (action === "close") {
      panel.host.remove();
      panel = null;
      return;
    }
    if (action === "fill") {
      const rows = lastAnalysis.plan
        .filter((row) => panel.querySelector(`[data-check="${row.field_id}"]`)?.checked)
        .map((row) => ({ ...row, value: panel.querySelector(`[data-value="${row.field_id}"]`).value }));
      const { filled, failed } = fillApproved(rows);
      const failedIds = new Set(failed.map((f) => f.field_id));
      rows
        .filter((row) => !failedIds.has(row.field_id))
        .forEach((row) => panel.querySelector(`[data-row="${row.field_id}"]`)?.classList.add("done"));
      status(
        `Filled ${filled.length} field${filled.length === 1 ? "" : "s"}` +
          (failed.length ? ` · ${failed.length} couldn't be set` : "") +
          " — review the page, then submit it yourself.",
        false
      );
      return;
    }
    if (action === "log") {
      try {
        const result = await send("logFill", {
          url: location.href,
          ats: lastAnalysis.ats,
          filled: filledThisPage,
          skipped: lastAnalysis.skipped.map((s) => ({ label: s.label, skip_reason: s.skip_reason })),
          status: "draft",
          company: lastAnalysis.job?.company,
          title: lastAnalysis.job?.title || document.title.slice(0, 120),
        });
        status(`Logged to dashboard as application #${result.application_id} (status: draft).`);
      } catch (error) {
        status(`Couldn't reach the dashboard: ${error.message}`, true);
      }
    }
  }

  async function onMap(index) {
    const select = panel.querySelector(`[data-sig="${index}"]`);
    const skipped = lastAnalysis.skipped[Number(index)];
    if (!select || !skipped) return;
    try {
      await send("learn", {
        signature: skipped.signature,
        canonical: select.value,
        ats: lastAnalysis.ats,
        host: location.host,
      });
      status(`Remembered: this field is "${select.value}". Re-scanning…`);
      await scan({ force: true });
    } catch (error) {
      status(error.message, true);
    }
  }

  // --- orchestration -------------------------------------------------------

  async function scan({ force = false, quiet = false } = {}) {
    const fields = harvestFields();
    if (!force && !looksLikeApplication(fields)) {
      send("badge", { count: 0 }).catch(() => {});
      return null;
    }
    let analysis;
    try {
      analysis = await send("analyze", { url: location.href, host: location.host, fields });
    } catch (error) {
      if (!quiet) console.warn("[autofill] backend unreachable:", error.message);
      return null;
    }
    if (!window.__jaaFields) {
      try {
        window.__jaaFields = (await send("knownFields")).fields;
      } catch (_) {
        window.__jaaFields = [];
      }
    }

    highlight(analysis);
    send("badge", { count: analysis.plan.length }).catch(() => {});

    if (analysis.plan.length === 0 && analysis.skipped.length === 0) return analysis;
    renderPanel(analysis);

    if (analysis.quick_apply && analysis.high_confidence) {
      const rows = analysis.plan.filter((row) => row.autofill);
      const { filled } = fillApproved(rows);
      rows.forEach((row) => panel.querySelector(`[data-row="${row.field_id}"]`)?.classList.add("done"));
      status(`Quick apply filled ${filled.length} high-confidence fields. Check them, then submit yourself.`);
    }
    return analysis;
  }

  window.__jaaRescan = () => scan({ force: true });

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === "scanNow") {
      scan({ force: true })
        .then((analysis) => sendResponse({ data: { matched: analysis?.plan?.length || 0 } }))
        .catch((error) => sendResponse({ error: error.message }));
      return true;
    }
    return false;
  });

  // ATS forms render late and re-render on step changes; re-scan on a debounce.
  let debounce = null;
  const observer = new MutationObserver(() => {
    if (panel) return; // don't fight with an open panel
    clearTimeout(debounce);
    debounce = setTimeout(() => scan({ quiet: true }), 1200);
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });

  chrome.storage.local.get({ autoScan: true }, ({ autoScan }) => {
    if (autoScan) setTimeout(() => scan({ quiet: true }), 800);
  });
})();
