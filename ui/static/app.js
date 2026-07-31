"use strict";

const state = {
  csrf: "",
  bootstrap: null,
  cases: [],
  templates: [],
  selectedMatter: null,
  status: null,
  notifiedJobs: new Set(),
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = String(text);
  return element;
}

function toast(message, isError = false) {
  const item = node("div", `toast${isError ? " error" : ""}`, message);
  $("#toast-region").append(item);
  window.setTimeout(() => item.remove(), 5500);
}

function getAccessToken() {
  return window.sessionStorage.getItem("aimaos_access_token") || "";
}

async function apiFetch(path, options = {}) {
  const request = { ...options };
  request.method = (request.method || "GET").toUpperCase();
  request.headers = new Headers(request.headers || {});
  const token = getAccessToken();
  if (token) request.headers.set("X-AIMAOS-Token", token);
  if (request.method !== "GET") {
    request.headers.set("Content-Type", "application/json");
    request.headers.set("X-AIMAOS-CSRF", state.csrf);
  }

  const response = await fetch(path, request);
  let payload = null;
  if ((response.headers.get("content-type") || "").includes("application/json")) {
    payload = await response.json();
  }
  if (response.status === 401) {
    const dialog = $("#auth-dialog");
    if (!dialog.open) dialog.showModal();
    throw new Error("Authentication required");
  }
  if (!response.ok) {
    const message = payload?.error?.message || `Request failed with status ${response.status}`;
    throw new Error(message);
  }
  return payload;
}

function showView(viewName) {
  $$(".view").forEach((view) => {
    const active = view.id === `view-${viewName}`;
    view.hidden = !active;
    view.classList.toggle("active", active);
  });
  $$(".nav-button").forEach((button) => {
    const active = button.dataset.viewTarget === viewName;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  $("#main-content").focus({ preventScroll: true });
}

function bindNavigation() {
  $$('[data-view-target]').forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.viewTarget));
  });
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

function renderHealth() {
  if (!state.status) return;
  const daemon = state.status.daemon || {};
  const responsive = Boolean(daemon.responsive);
  $("#health-dot").className = `status-dot ${responsive ? "good" : "warn"}`;
  $("#health-label").textContent = responsive ? "Office ready" : "Office service unavailable";
  $("#daemon-metric").textContent = responsive ? "Ready" : "Check service";
  $("#daemon-detail").textContent = daemon.current_task?.title
    ? `${daemon.current_task.agent}: ${daemon.current_task.title}`
    : `State: ${daemon.state || "unknown"}`;
  const activeJobs = (state.status.jobs || []).filter((job) => ["queued", "running"].includes(job.status));
  $("#active-metric").textContent = String((state.status.active_tasks || []).length + activeJobs.length);
  $("#matter-metric").textContent = String(state.cases.length);
  const needsStaff = (state.status.work_items || []).filter((item) => (
    item.requires_human || item.overdue || ["blocked", "failed"].includes(item.status)
  ));
  $("#attention-metric").textContent = String(needsStaff.length);
}

function statusTag(status) {
  return node("span", `status-tag ${status || ""}`, String(status || "queued").replaceAll("_", " "));
}

function tomorrowDate() {
  const value = new Date();
  value.setDate(value.getDate() + 1);
  const pad = (number) => String(number).padStart(2, "0");
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`;
}

async function updateWorkItem(item, action) {
  try {
    const body = { task_id: item.id, action };
    if (action === "snooze") body.due_date = tomorrowDate();
    const payload = await apiFetch("/api/work_item", {
      method: "POST",
      body: JSON.stringify(body),
    });
    toast(payload.message);
    await loadStatus();
  } catch (error) {
    toast(error.message, true);
  }
}

function workstationRow(item, interactive = true) {
  const row = node("article", `work-item priority-${String(item.priority || "normal").toLowerCase()}${item.overdue ? " overdue" : ""}`);
  const copy = node("div", "work-copy");
  copy.append(node("strong", "", item.title || "Untitled work item"));

  const meta = node("div", "work-meta");
  [item.matter, item.owner, item.priority, item.due_date ? `Due ${item.due_date}` : null]
    .filter(Boolean)
    .forEach((value) => meta.append(node("span", "", value)));
  copy.append(meta);
  if (item.blocker) {
    const blocker = node("p", "work-explanation");
    blocker.append(node("strong", "", "Blocked: "), document.createTextNode(item.blocker));
    copy.append(blocker);
  }
  if (item.next_action) {
    const next = node("p", "work-explanation");
    next.append(node("strong", "", "Next: "), document.createTextNode(item.next_action));
    copy.append(next);
  }

  const side = node("div", "work-side");
  const badges = node("div", "work-badges");
  badges.append(statusTag(item.status));
  if (item.overdue) badges.append(statusTag("overdue"));
  side.append(badges);
  if (interactive && (item.can_complete || item.can_snooze)) {
    const actions = node("div", "work-actions");
    if (item.can_complete) {
      const complete = node("button", "primary-button", "Done");
      complete.type = "button";
      complete.addEventListener("click", () => updateWorkItem(item, "complete"));
      actions.append(complete);
    }
    if (item.can_snooze) {
      const snooze = node("button", "secondary-button", "Tomorrow");
      snooze.type = "button";
      snooze.addEventListener("click", () => updateWorkItem(item, "snooze"));
      actions.append(snooze);
    }
    side.append(actions);
  }
  row.append(copy, side);
  return row;
}

function jobRow(job) {
  return workstationRow({
    id: job.job_id,
    title: job.title,
    owner: "Office job",
    priority: "NORMAL",
    status: job.status,
    next_action: job.error || `${job.kind} · started ${formatDate(job.created_at)}`,
  }, false);
}

function notifyFinishedJobs(jobs) {
  jobs.forEach((job) => {
    if (["completed", "failed", "interrupted"].includes(job.status)
        && !state.notifiedJobs.has(job.job_id)) {
      state.notifiedJobs.add(job.job_id);
      if (job.status === "completed") toast(`${job.title} completed.`);
      else toast(`${job.title}: ${job.error || job.status}`, true);
    }
  });
}

function renderWork() {
  const container = $("#work-list");
  container.replaceChildren();
  const workItems = (state.status?.work_items || []).slice(0, 10);
  const jobs = (state.status?.jobs || []).filter((job) => ["queued", "running", "failed"].includes(job.status)).slice(0, 5);
  if (!workItems.length && !jobs.length) {
    const empty = node("div", "empty-state");
    empty.append(node("strong", "", "Nothing needs attention"), node("p", "", "The office queue is clear."));
    container.append(empty);
    return;
  }
  workItems.forEach((item) => container.append(workstationRow(item)));
  jobs.forEach((job) => container.append(jobRow(job)));
  notifyFinishedJobs(state.status?.jobs || []);
}

function renderAgenda() {
  const container = $("#agenda-work-list");
  container.replaceChildren();
  const items = state.status?.work_items || [];
  if (!items.length) {
    const empty = node("div", "empty-state");
    empty.append(node("strong", "", "Agenda clear"), node("p", "", "No open tasks, case blockers, or reminders were found."));
    container.append(empty);
    return;
  }
  items.forEach((item) => container.append(workstationRow(item)));
}

async function loadStatus() {
  try {
    state.status = await apiFetch("/api/status");
    renderHealth();
    renderWork();
    renderAgenda();
  } catch (error) {
    if (error.message !== "Authentication required") {
      $("#health-dot").className = "status-dot warn";
      $("#health-label").textContent = "Status unavailable";
    }
  }
}

function renderMatterOptions() {
  const select = $("#assistant-matter");
  const current = select.value;
  select.replaceChildren(new Option("General office question", ""));
  state.cases.forEach((matter) => select.add(new Option(matter.client_name, matter.client_slug)));
  if (state.cases.some((matter) => matter.client_slug === current)) select.value = current;
}

function renderMatterList() {
  const container = $("#matter-list");
  const query = $("#matter-search").value.trim().toLowerCase();
  container.replaceChildren();
  const visible = state.cases.filter((matter) => {
    const search = `${matter.client_name} ${matter.matter_type || ""} ${matter.status || ""}`.toLowerCase();
    return !query || search.includes(query);
  });
  if (!visible.length) {
    container.append(node("p", "form-help", state.cases.length ? "No matching matters." : "No matters yet. Import a file to begin."));
    return;
  }
  visible.forEach((matter) => {
    const button = node("button", "matter-button");
    button.type = "button";
    if (matter.client_slug === state.selectedMatter) button.classList.add("active");
    button.append(node("strong", "", matter.client_name), node("small", "", matter.matter_type || "Matter"));
    button.addEventListener("click", () => selectMatter(matter.client_slug));
    container.append(button);
  });
}

async function loadCases() {
  const payload = await apiFetch("/api/cases");
  state.cases = payload.cases || [];
  renderMatterList();
  renderMatterOptions();
  renderHealth();
}

function fileAction(label, handler) {
  const button = node("button", "secondary-button", label);
  button.type = "button";
  button.addEventListener("click", handler);
  return button;
}

async function downloadFile(slug, path, filename) {
  try {
    const headers = new Headers();
    const token = getAccessToken();
    if (token) headers.set("X-AIMAOS-Token", token);
    const response = await fetch(`/api/files/download?slug=${encodeURIComponent(slug)}&path=${encodeURIComponent(path)}`, { headers });
    if (!response.ok) throw new Error("Download failed");
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    toast(error.message, true);
  }
}

async function openNativeFile(slug, path) {
  try {
    const payload = await apiFetch("/api/open_file", {
      method: "POST",
      body: JSON.stringify({ slug, path }),
    });
    toast(payload.message);
  } catch (error) {
    toast(error.message, true);
  }
}

async function selectMatter(slug) {
  try {
    const payload = await apiFetch(`/api/case_file?slug=${encodeURIComponent(slug)}`);
    state.selectedMatter = slug;
    renderMatterList();
    $("#matter-empty").hidden = true;
    $("#matter-content").hidden = false;
    $("#matter-detail-title").textContent = payload.case.client_name;
    $("#matter-meta").textContent = `${payload.case.matter_type || "Matter"} · ${payload.case.status || "open"}`;
    $("#matter-summary").textContent = payload.summary_md || "No summary available.";
    $("#upload-client-name").value = payload.case.client_name;

    const files = $("#matter-files");
    files.replaceChildren();
    if (!(payload.files || []).length) files.append(node("p", "form-help", "No files in this matter."));
    (payload.files || []).forEach((file) => {
      const row = node("article", "file-item");
      const copy = node("div");
      copy.append(node("strong", "", file.name), node("small", "", `${formatBytes(file.size)} · ${formatDate(file.modified_at)}`));
      const actions = node("div", "file-actions");
      actions.append(fileAction("Download", () => downloadFile(slug, file.path, file.name)));
      if (state.bootstrap?.native_open_enabled) {
        actions.append(fileAction("Open", () => openNativeFile(slug, file.path)));
      }
      row.append(copy, actions);
      files.append(row);
    });
  } catch (error) {
    toast(error.message, true);
  }
}

function openUpload() {
  $("#upload-form").hidden = false;
  if (state.selectedMatter) {
    const matter = state.cases.find((item) => item.client_slug === state.selectedMatter);
    if (matter) $("#upload-client-name").value = matter.client_name;
  }
  $("#upload-client-name").focus();
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  const chunks = [];
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    chunks.push(String.fromCharCode(...bytes.subarray(offset, offset + 0x8000)));
  }
  return window.btoa(chunks.join(""));
}

async function submitUpload(event) {
  event.preventDefault();
  const file = $("#upload-file").files[0];
  const clientName = $("#upload-client-name").value.trim();
  if (!file || !clientName) return;
  const maxBytes = (state.bootstrap?.max_upload_mb || 25) * 1024 * 1024;
  if (file.size > maxBytes) {
    toast(`File exceeds the ${state.bootstrap?.max_upload_mb || 25} MB limit.`, true);
    return;
  }
  const submit = event.submitter;
  submit.disabled = true;
  submit.textContent = "Saving…";
  try {
    const contentBase64 = arrayBufferToBase64(await file.arrayBuffer());
    const payload = await apiFetch("/api/upload", {
      method: "POST",
      body: JSON.stringify({ client_name: clientName, file_name: file.name, content_base64: contentBase64 }),
    });
    toast(`File saved. Background review queued as ${payload.job_id}.`);
    event.currentTarget.reset();
    event.currentTarget.hidden = true;
    await Promise.all([loadCases(), loadStatus()]);
    if (payload.matter_slug) await selectMatter(payload.matter_slug);
  } catch (error) {
    toast(error.message, true);
  } finally {
    submit.disabled = false;
    submit.textContent = "Save and review";
  }
}

function renderTemplates() {
  const select = $("#template-select");
  select.replaceChildren(new Option("Choose a template", ""));
  state.templates.forEach((template) => select.add(new Option(template.name, template.id)));
}

async function loadTemplates() {
  const payload = await apiFetch("/api/templates");
  state.templates = payload.templates || [];
  renderTemplates();
}

function selectTemplate() {
  const template = state.templates.find((item) => item.id === $("#template-select").value);
  const description = $("#template-description");
  const form = $("#document-form");
  const fields = $("#document-fields");
  description.replaceChildren();
  fields.replaceChildren();
  if (!template) {
    form.hidden = true;
    return;
  }
  description.append(node("p", "", template.description || "No template description is available."));
  if (template.verification_status !== "verified") {
    description.append(node(
      "p",
      "warning-note",
      "Template provenance is incomplete. Verify the form and revision against an official source before use.",
    ));
  }
  const provenance = [template.jurisdiction, template.revision && `Revision ${template.revision}`, template.last_reviewed_at && `Reviewed ${formatDate(template.last_reviewed_at)}`].filter(Boolean);
  if (provenance.length) description.append(node("small", "", provenance.join(" · ")));
  if (template.official_source) {
    try {
      const sourceUrl = new URL(template.official_source);
      if (["http:", "https:"].includes(sourceUrl.protocol)) {
        const link = node("a", "", "Official source");
        link.href = sourceUrl.href;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        description.append(link);
      }
    } catch (_) { /* Invalid metadata URL is intentionally not rendered. */ }
  }
  $("#document-form-title").textContent = template.name;
  (template.fields || []).forEach((field) => {
    const label = node("label", "", `${field.label}${field.required ? " *" : ""}`);
    const input = document.createElement("input");
    input.type = "text";
    input.dataset.fieldName = field.name;
    input.required = Boolean(field.required);
    input.maxLength = 20000;
    if (field.description) input.setAttribute("aria-description", field.description);
    label.append(input);
    if (field.description) label.append(node("small", "form-help", field.description));
    fields.append(label);
  });
  form.hidden = false;
}

async function submitDocument(event) {
  event.preventDefault();
  const templateId = $("#template-select").value;
  const context = {};
  $$("#document-fields input").forEach((input) => { context[input.dataset.fieldName] = input.value; });
  const submit = event.submitter;
  submit.disabled = true;
  submit.textContent = "Queueing…";
  try {
    const payload = await apiFetch("/api/generate_doc", {
      method: "POST",
      body: JSON.stringify({ template: templateId, context }),
    });
    toast(`Draft generation queued as ${payload.job_id}.`);
    showView("home");
    await loadStatus();
  } catch (error) {
    toast(error.message, true);
  } finally {
    submit.disabled = false;
    submit.textContent = "Generate draft";
  }
}

function addMessage(kind, author, text) {
  const item = node("article", `message ${kind === "user" ? "user-message" : "assistant-message"}`);
  item.append(node("strong", "", author), node("p", "", text));
  $("#assistant-messages").append(item);
  item.scrollIntoView({ block: "nearest" });
  return item;
}

async function waitForJob(jobId, placeholder) {
  const deadline = Date.now() + 30 * 60 * 1000;
  while (Date.now() < deadline) {
    const payload = await apiFetch(`/api/jobs?id=${encodeURIComponent(jobId)}`);
    const job = payload.job;
    if (["completed", "failed", "interrupted"].includes(job.status)) {
      if (job.status === "completed") {
        const message = job.result?.message || job.result?.draft_notice || JSON.stringify(job.result, null, 2);
        placeholder.querySelector("p").textContent = message || "The job completed.";
      } else {
        placeholder.querySelector("p").textContent = job.error || `The job ${job.status}.`;
      }
      await Promise.all([loadStatus(), loadCases()]);
      return job;
    }
    placeholder.querySelector("p").textContent = `Working… (${job.status})`;
    await new Promise((resolve) => window.setTimeout(resolve, 1800));
  }
  throw new Error("The job is still running. Check the Home queue for its status.");
}

async function submitAssistant(event) {
  event.preventDefault();
  const input = $("#assistant-input");
  const message = input.value.trim();
  if (!message) return;
  const matterSlug = $("#assistant-matter").value || null;
  addMessage("user", "You", message);
  input.value = "";
  const placeholder = addMessage("assistant", "AIMAOS", "Queueing your request…");
  event.submitter.disabled = true;
  try {
    const payload = await apiFetch("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message, matter_slug: matterSlug }),
    });
    await waitForJob(payload.job_id, placeholder);
  } catch (error) {
    placeholder.querySelector("p").textContent = error.message;
    toast(error.message, true);
  } finally {
    event.submitter.disabled = false;
  }
}

async function attachMatterNote() {
  const matterSlug = $("#assistant-matter").value;
  const note = $("#assistant-input").value.trim();
  if (!matterSlug) {
    toast("Choose a matter before attaching a note.", true);
    return;
  }
  if (!note) {
    toast("Enter the note first.", true);
    return;
  }
  try {
    await apiFetch("/api/voice_scribe", {
      method: "POST",
      body: JSON.stringify({ matter_slug: matterSlug, text: note }),
    });
    $("#assistant-input").value = "";
    toast("Note attached to the matter.");
  } catch (error) {
    toast(error.message, true);
  }
}

async function triggerQuickAction(action) {
  try {
    const payload = await apiFetch("/api/quick_action", {
      method: "POST",
      body: JSON.stringify({ action }),
    });
    toast(payload.message || `Task queued as ${payload.task_id}.`);
    await loadStatus();
  } catch (error) {
    toast(error.message, true);
  }
}

function renderSettings() {
  if (!state.bootstrap) return;
  $("#beta-version").textContent = `Public beta ${state.bootstrap.version}`;
  $("#setting-native-open").textContent = state.bootstrap.native_open_enabled ? "Enabled locally" : "Disabled";
  $("#setting-developer").textContent = state.bootstrap.developer_mode ? "Enabled" : "Disabled";
  $("#setting-raw-logs").textContent = state.bootstrap.privacy.raw_tool_logs ? "Enabled" : "Disabled";
  $("#setting-retention").textContent = `${state.bootstrap.privacy.retention_days} days`;
  $("#clone-form").hidden = !state.bootstrap.developer_mode;
  $("#upload-help").textContent = `Files up to ${state.bootstrap.max_upload_mb} MB are stored locally and reviewed as a background job.`;
}

async function submitClone(event) {
  event.preventDefault();
  try {
    const payload = await apiFetch("/api/clone_agent", {
      method: "POST",
      body: JSON.stringify({ agent_name: $("#clone-name").value, role: $("#clone-role").value }),
    });
    toast(payload.message);
    event.currentTarget.reset();
  } catch (error) {
    toast(error.message, true);
  }
}

async function bootstrap() {
  const payload = await apiFetch("/api/bootstrap");
  state.bootstrap = payload;
  state.csrf = payload.csrf_token;
  renderSettings();
  $("#setup-banner").hidden = payload.setup_complete;
  if (!payload.setup_complete) toast("Setup is incomplete. Follow the setup instructions shown above.", true);
  await Promise.all([loadCases(), loadTemplates(), loadStatus()]);
}

function bindEvents() {
  bindNavigation();
  $("#refresh-status").addEventListener("click", loadStatus);
  $("#matter-search").addEventListener("input", renderMatterList);
  $("#new-intake-button").addEventListener("click", openUpload);
  $("#add-file-button").addEventListener("click", openUpload);
  $("#close-upload").addEventListener("click", () => { $("#upload-form").hidden = true; });
  $("#upload-form").addEventListener("submit", submitUpload);
  $("#template-select").addEventListener("change", selectTemplate);
  $("#document-form").addEventListener("submit", submitDocument);
  $("#assistant-form").addEventListener("submit", submitAssistant);
  $("#attach-note-button").addEventListener("click", attachMatterNote);
  $("#matter-assistant-button").addEventListener("click", () => {
    $("#assistant-matter").value = state.selectedMatter || "";
    showView("assistant");
    $("#assistant-input").focus();
  });
  $$("[data-quick-action]").forEach((button) => {
    button.addEventListener("click", () => triggerQuickAction(button.dataset.quickAction));
  });
  $("#clone-form").addEventListener("submit", submitClone);
  $("#auth-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    window.sessionStorage.setItem("aimaos_access_token", $("#auth-token").value);
    try {
      await bootstrap();
      $("#auth-dialog").close();
      $("#auth-token").value = "";
    } catch (error) {
      toast(error.message, true);
    }
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  bindEvents();
  try {
    await bootstrap();
  } catch (error) {
    if (error.message !== "Authentication required") toast(error.message, true);
  }
  window.setInterval(loadStatus, 4000);
});
