"use strict";

const state = {
  csrf: "",
  bootstrap: null,
  cases: [],
  templates: [],
  documentsCatalog: [],
  selectedMatter: null,
  reviewDocument: null,
  selectedReviewLine: null,
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
  if (viewName === "documents") {
    loadDocumentsCatalog();
  }
  $("#main-content").focus({ preventScroll: true });
}

function bindNavigation() {
  $$('[data-view-target]').forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.viewTarget));
  });
  $("#btn-toggle-daemon")?.addEventListener("click", toggleDaemonPause);
  $("#documents-refresh-button")?.addEventListener("click", loadDocumentsCatalog);
  $("#documents-search")?.addEventListener("input", renderDocumentsCatalog);
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
  const pauseRequested = Boolean(daemon.pause_requested);
  const isPaused = daemon.state === "paused";

  const dot = $("#health-dot");
  const label = $("#health-label");
  const daemonBtn = $("#btn-toggle-daemon");

  if (!responsive) {
    dot.className = "status-dot warn";
    label.textContent = "Office service unavailable";
    if (daemonBtn) {
      daemonBtn.textContent = "Start Agents";
      daemonBtn.className = "mini-daemon-button action-resume";
    }
  } else if (pauseRequested || isPaused) {
    dot.className = "status-dot pause";
    label.textContent = isPaused ? "Office paused" : "Pausing (Finish task)";
    if (daemonBtn) {
      daemonBtn.textContent = "Resume Agents";
      daemonBtn.className = "mini-daemon-button action-resume";
      daemonBtn.title = "Click to resume autonomous agent pulse";
    }
  } else {
    dot.className = "status-dot good";
    label.textContent = "Office ready";
    if (daemonBtn) {
      daemonBtn.textContent = "Pause Agents";
      daemonBtn.className = "mini-daemon-button action-pause";
      daemonBtn.title = "Pause agents safely after current task completes";
    }
  }

  $("#daemon-metric").textContent = isPaused ? "Paused" : (pauseRequested ? "Pausing…" : (responsive ? "Ready" : "Check service"));
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

async function toggleDaemonPause() {
  try {
    const daemon = state.status?.daemon || {};
    const shouldResume = !daemon.responsive || daemon.pause_requested || daemon.state === "paused";
    const endpoint = shouldResume ? "/api/daemon/resume" : "/api/daemon/pause";
    const payload = await apiFetch(endpoint, { method: "POST", body: "{}" });
    toast(payload.message);
    await loadStatus();
  } catch (error) {
    toast(error.message, true);
  }
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

function findCaseSlug(matterName) {
  if (!matterName || !state.cases || !state.cases.length) return null;
  const lower = String(matterName).trim().toLowerCase();
  const found = state.cases.find((c) =>
    (c.client_name && c.client_name.toLowerCase() === lower) ||
    (c.client_slug && c.client_slug.toLowerCase() === lower) ||
    (c.matter_type && c.matter_type.toLowerCase() === lower) ||
    (c.client_name && c.client_name.toLowerCase().includes(lower))
  );
  return found ? found.client_slug : null;
}

async function openMatterFromWorkItem(slug, matterName, filePath = null) {
  const targetSlug = slug || findCaseSlug(matterName);
  if (!targetSlug) {
    toast(`No matter files found matching "${matterName || "this item"}".`, true);
    return;
  }
  showView("matters");
  const matter = await selectMatter(targetSlug);
  if (!matter) return;
  if (filePath) {
    await openDocumentReview(targetSlug, filePath);
  } else {
    toast(`Opened matter details and files for ${matterName || targetSlug}.`);
  }
}

function workstationRow(item, interactive = true) {
  const reviewTarget = item.review_target || {};
  const targetSlug = reviewTarget.client_slug || item.client_slug || findCaseSlug(item.matter);
  const targetFile = reviewTarget.file_path || null;
  const row = node("article", `work-item priority-${String(item.priority || "normal").toLowerCase()}${item.overdue ? " overdue" : ""}${targetSlug ? " clickable-item" : ""}`);
  const copy = node("div", "work-copy");

  const titleText = item.title || "Untitled work item";
  if (targetSlug) {
    const titleBtn = node("button", "work-title-link", titleText);
    titleBtn.type = "button";
    titleBtn.title = `Click to view matter files for ${item.matter || targetSlug}`;
    titleBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      openMatterFromWorkItem(targetSlug, item.matter, targetFile);
    });
    copy.append(titleBtn);
  } else {
    copy.append(node("strong", "", titleText));
  }

  const meta = node("div", "work-meta");
  if (item.matter) {
    if (targetSlug) {
      const matterBadge = node("button", "matter-tag clickable", item.matter);
      matterBadge.type = "button";
      matterBadge.title = `Open matter: ${item.matter}`;
      matterBadge.addEventListener("click", (e) => {
        e.stopPropagation();
        openMatterFromWorkItem(targetSlug, item.matter, targetFile);
      });
      meta.append(matterBadge);
    } else {
      meta.append(node("span", "status-tag", item.matter));
    }
  }

  [item.owner, item.priority, item.due_date ? `Due ${item.due_date}` : null]
    .filter(Boolean)
    .forEach((value) => meta.append(node("span", "", value)));
  copy.append(meta);

  if (item.blocker) {
    const blocker = node("p", "work-explanation");
    blocker.append(node("strong", "", "Blocked: "), document.createTextNode(item.blocker));
    if (targetSlug) {
      blocker.title = "Click to open matter files and resolve blocker";
      blocker.classList.add("clickable-text");
      blocker.addEventListener("click", (e) => {
        e.stopPropagation();
        openMatterFromWorkItem(targetSlug, item.matter, targetFile);
      });
    }
    copy.append(blocker);
    }
  if (item.next_action) {
    const next = node("p", "work-explanation");
    next.append(node("strong", "", "Next: "), document.createTextNode(item.next_action));
    copy.append(next);
  }

  if (item.interactive_form) {
    const formCard = renderInteractiveForm(item.interactive_form, item.id);
    if (formCard) copy.append(formCard);
  }
  if (item.user_responses) {
    const respSummary = node("div", "work-user-responses");
    respSummary.append(node("span", "status-tag success", "Responses Submitted"));
    copy.append(respSummary);
  }

  const side = node("div", "work-side");
  const badges = node("div", "work-badges");
  badges.append(statusTag(item.status));
  if (item.overdue) badges.append(statusTag("overdue"));
  side.append(badges);

  if (interactive) {
    const actions = node("div", "work-actions");
    if (targetSlug) {
      const viewMatterBtn = node(
        "button", "secondary-button", targetFile ? "Review file" : "View Matter & Files"
      );
      viewMatterBtn.type = "button";
      viewMatterBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        openMatterFromWorkItem(targetSlug, item.matter, targetFile);
      });
      actions.append(viewMatterBtn);
    }
    if (item.can_complete) {
      const complete = node("button", "primary-button", "Done");
      complete.type = "button";
      complete.addEventListener("click", (e) => {
        e.stopPropagation();
        updateWorkItem(item, "complete");
      });
      actions.append(complete);
    }
    if (item.can_snooze) {
      const snooze = node("button", "secondary-button", "Tomorrow");
      snooze.type = "button";
      snooze.addEventListener("click", (e) => {
        e.stopPropagation();
        updateWorkItem(item, "snooze");
      });
      actions.append(snooze);
    }
    if (actions.children.length > 0) side.append(actions);
  }
  row.append(copy, side);
  return row;
}

function renderAlertBanners(workItems) {
  const container = $("#agent-banner-container");
  if (!container) return;
  container.replaceChildren();
  const banners = [];
  (workItems || []).forEach((item) => {
    if (item.alert_banner) {
      banners.push({ ...item.alert_banner, matter: item.matter, client_slug: item.client_slug });
    }
  });
  if (!banners.length) return;

  banners.forEach((banner) => {
    const bannerEl = node("aside", `agent-banner ${banner.level || "warning"}`);
    bannerEl.setAttribute("role", "alert");

    const iconStr = banner.level === "urgent" ? "🚨" : banner.level === "warning" ? "⚠️" : "ℹ️";
    const icon = node("span", "agent-banner-icon", iconStr);
    const body = node("div", "agent-banner-body");
    body.append(node("strong", "agent-banner-title", banner.title || "Agent Alert"));
    if (banner.message) body.append(node("p", "agent-banner-message", banner.message));

    const actions = node("div", "agent-banner-actions");
    if (banner.action_label) {
      const actBtn = node("button", "primary-button mini", banner.action_label);
      actBtn.type = "button";
      actBtn.addEventListener("click", () => {
        if (banner.action_target) showView(banner.action_target);
        else if (banner.client_slug) openMatterFromWorkItem(banner.client_slug, banner.matter);
        else showView("requests");
      });
      actions.append(actBtn);
    }
    const dismissBtn = node("button", "icon-button mini", "✕");
    dismissBtn.type = "button";
    dismissBtn.title = "Dismiss alert";
    dismissBtn.addEventListener("click", () => bannerEl.remove());
    actions.append(dismissBtn);

    bannerEl.append(icon, body, actions);
    container.append(bannerEl);
  });
}

function renderInteractiveForm(formSpec, taskId) {
  if (!formSpec || !formSpec.fields || !formSpec.fields.length) return null;
  const card = node("div", "agent-form-card");

  const header = node("div", "agent-form-header");
  header.append(
    node("span", "agent-form-pill", "Agent Request"),
    node("h4", "agent-form-title", formSpec.title || "Required Information")
  );
  card.append(header);

  if (formSpec.instructions) {
    card.append(node("p", "agent-form-instructions", formSpec.instructions));
  }

  const form = node("form", "agent-form-body");
  form.dataset.taskId = taskId;

  formSpec.fields.forEach((field) => {
    const fieldGroup = node("div", "agent-field-group");
    const fieldId = `form-field-${taskId}-${field.id}`;
    const labelEl = node("label", "agent-field-label");
    labelEl.htmlFor = fieldId;
    labelEl.append(document.createTextNode(field.label));
    if (field.required) {
      labelEl.append(node("span", "required-star", " *"));
    }
    fieldGroup.append(labelEl);

    if (field.description) {
      fieldGroup.append(node("small", "agent-field-desc", field.description));
    }

    let inputEl;
    if (field.type === "textarea") {
      inputEl = node("textarea", "agent-input agent-textarea");
      inputEl.id = fieldId;
      inputEl.name = field.id;
      if (field.placeholder) inputEl.placeholder = field.placeholder;
      if (field.default_value) inputEl.value = field.default_value;
      if (field.required) inputEl.required = true;
      fieldGroup.append(inputEl);
    } else if (field.type === "select") {
      inputEl = node("select", "agent-input agent-select");
      inputEl.id = fieldId;
      inputEl.name = field.id;
      if (field.required) inputEl.required = true;
      inputEl.add(new Option(field.placeholder || "-- Select an option --", ""));
      (field.options || []).forEach((opt) => {
        inputEl.add(new Option(opt.label, opt.value));
      });
      if (field.default_value) inputEl.value = field.default_value;
      fieldGroup.append(inputEl);
    } else if (field.type === "checkbox") {
      const checkWrapper = node("div", "agent-checkbox-wrapper");
      if (field.options && field.options.length) {
        field.options.forEach((opt) => {
          const checkLbl = node("label", "checkbox-item-label");
          const chk = node("input", "agent-checkbox");
          chk.type = "checkbox";
          chk.name = field.id;
          chk.value = opt.value;
          checkLbl.append(chk, document.createTextNode(` ${opt.label}`));
          checkWrapper.append(checkLbl);
        });
      } else {
        inputEl = node("input", "agent-checkbox");
        inputEl.type = "checkbox";
        inputEl.id = fieldId;
        inputEl.name = field.id;
        inputEl.value = "true";
        const singleLbl = node("label", "checkbox-item-label");
        singleLbl.htmlFor = fieldId;
        singleLbl.append(inputEl, document.createTextNode(` ${field.label}`));
        checkWrapper.append(singleLbl);
      }
      fieldGroup.append(checkWrapper);
    } else {
      inputEl = node("input", "agent-input");
      inputEl.type = field.type === "date" ? "date" : field.type === "file" ? "file" : "text";
      inputEl.id = fieldId;
      inputEl.name = field.id;
      if (field.placeholder) inputEl.placeholder = field.placeholder;
      if (field.default_value) inputEl.value = field.default_value;
      if (field.required) inputEl.required = true;
      fieldGroup.append(inputEl);
    }

    form.append(fieldGroup);
  });

  const actions = node("div", "agent-form-actions");
  const submitBtn = node("button", "primary-button", formSpec.submit_label || "Submit to Agent");
  submitBtn.type = "submit";
  actions.append(submitBtn);
  form.append(actions);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    e.stopPropagation();
    await submitAgentForm(taskId, form, submitBtn);
  });

  card.append(form);
  return card;
}

async function submitAgentForm(taskId, formElement, submitBtn) {
  const formData = new FormData(formElement);
  const responses = {};
  for (const [key, value] of formData.entries()) {
    if (responses[key] !== undefined) {
      if (Array.isArray(responses[key])) {
        responses[key].push(value);
      } else {
        responses[key] = [responses[key], value];
      }
    } else {
      responses[key] = value;
    }
  }

  submitBtn.disabled = true;
  submitBtn.textContent = "Submitting…";

  try {
    const payload = await apiFetch("/api/agenda/respond", {
      method: "POST",
      body: JSON.stringify({ task_id: taskId, responses }),
    });
    toast(payload.message || "Form responses submitted successfully!");
    await loadStatus();
  } catch (error) {
    toast(error.message, true);
    submitBtn.disabled = false;
    submitBtn.textContent = "Submit to Agent";
  }
}

function renderRequests() {
  const container = $("#requests-work-list");
  if (!container) return;
  container.replaceChildren();
  const allItems = state.status?.work_items || [];
  const requestItems = allItems.filter((item) => item.interactive_form || item.requires_human);
  if (!requestItems.length) {
    const empty = node("div", "empty-state");
    empty.append(node("strong", "", "No pending agent requests"), node("p", "", "When Alix, Finn, Kai, Zoe, or Marley need information or approvals, fillable forms will appear here."));
    container.append(empty);
    return;
  }
  requestItems.forEach((item) => container.append(workstationRow(item)));
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
    renderRequests();
    renderAlertBanners(state.status?.work_items || []);
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

function isReviewableFile(path) {
  const extension = String(path || "").toLowerCase().match(/\.[a-z0-9]+$/)?.[0] || "";
  return [".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".rtf", ".docx", ".pdf"].includes(extension);
}

function selectReviewLine(lineNumber) {
  state.selectedReviewLine = Number(lineNumber);
  $$(".document-line").forEach((line) => {
    const selected = Number(line.dataset.lineNumber) === state.selectedReviewLine;
    line.classList.toggle("selected", selected);
    line.setAttribute("aria-pressed", selected ? "true" : "false");
    if (selected) {
      line.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  });
  const line = (state.reviewDocument?.lines || []).find((item) => item.number === state.selectedReviewLine);
  const textExcerpt = line?.text ? (line.text.length > 70 ? line.text.slice(0, 70) + "…" : line.text) : "(blank line)";
  $("#document-review-selection").textContent = line
    ? `Line ${line.number}: "${textExcerpt}"`
    : "Choose a line in the document.";
  if (line) {
    const commentBox = $("#document-review-comment");
    if (commentBox) commentBox.focus();
  }
}

async function updateReviewNote(noteId, action) {
  const review = state.reviewDocument;
  if (!review) return;
  try {
    const payload = await apiFetch("/api/document_review_note", {
      method: "POST",
      body: JSON.stringify({
        slug: review.slug,
        path: review.file.path,
        note_id: noteId,
        action,
      }),
    });
    toast(payload.message);
    await openDocumentReview(review.slug, review.file.path, { preserveSelection: true });
  } catch (error) {
    toast(error.message, true);
  }
}

function renderReviewNotes() {
  const container = $("#document-review-notes");
  container.replaceChildren();
  const notes = state.reviewDocument?.notes || [];
  const openCount = notes.filter((note) => note.status !== "resolved").length;
  $("#document-review-note-count").textContent = `${openCount} open`;
  $("#document-review-submit").disabled = openCount === 0;
  if (!notes.length) {
    container.append(node("p", "form-help", "No notes yet. Click a document line to begin."));
    return;
  }
  notes.forEach((note) => {
    const card = node("article", `review-note-card${note.status === "resolved" ? " resolved" : ""}`);
    const heading = node("div", "section-row");
    const lineButton = node("button", "text-button", `${note.kind || "note"} · line ${note.line_number}`);
    lineButton.type = "button";
    lineButton.addEventListener("click", () => {
      selectReviewLine(note.line_number);
      const target = $(`.document-line[data-line-number="${note.line_number}"]`);
      target?.scrollIntoView({ block: "center" });
    });
    heading.append(lineButton, statusTag(note.status || "open"));
    card.append(heading);
    if (note.stale) card.append(node("p", "warning-note", "The document changed after this note was added."));
    card.append(node("p", "review-note-excerpt", note.line_text || "(blank line)"));
    card.append(node("p", "", note.comment));
    const action = node(
      "button", "secondary-button", note.status === "resolved" ? "Reopen" : "Resolve"
    );
    action.type = "button";
    action.addEventListener("click", () => updateReviewNote(
      note.id, note.status === "resolved" ? "reopen" : "resolve"
    ));
    card.append(action);
    container.append(card);
  });
}

function renderDocumentReview() {
  const review = state.reviewDocument;
  if (!review) return;
  $("#document-review-title").textContent = review.file.name;
  $("#document-review-meta").textContent = `${formatBytes(review.file.size)} · ${formatDate(review.file.modified_at)}`;
  $("#document-review-status").textContent = review.extraction.detail;
  $("#document-review-status").classList.toggle(
    "warning-note", review.extraction.status !== "extracted"
  );
  $("#document-review-native").hidden = !state.bootstrap?.native_open_enabled;

  const lines = $("#document-review-lines");
  lines.replaceChildren();
  const notesByLine = new Map();
  (review.notes || []).forEach((note) => {
    if (!notesByLine.has(note.line_number)) notesByLine.set(note.line_number, []);
    notesByLine.get(note.line_number).push(note);
  });
  if (!(review.lines || []).length) {
    const empty = node("div", "empty-state compact-empty");
    empty.append(
      node("strong", "", "No text preview available"),
      node("p", "", "Open the document in its system application for review.")
    );
    lines.append(empty);
  } else {
    review.lines.forEach((line) => {
      const lineBtn = node("button", "document-line");
      lineBtn.type = "button";
      lineBtn.dataset.lineNumber = String(line.number);
      lineBtn.setAttribute("aria-pressed", "false");

      const numSpan = node("span", "document-line-number", line.number);
      const textSpan = node("span", "document-line-text", line.text || " ");

      const addNoteBtn = node("button", "document-line-add-note", "+ Add note");
      addNoteBtn.type = "button";
      addNoteBtn.title = `Add note for agent to line ${line.number}`;
      addNoteBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        selectReviewLine(line.number);
      });

      lineBtn.append(numSpan, textSpan, addNoteBtn);

      const lineNotes = notesByLine.get(line.number) || [];
      if (lineNotes.length) {
        lineBtn.classList.add("has-notes");
        lineBtn.append(node("span", "line-note-count", `${lineNotes.length} note${lineNotes.length > 1 ? "s" : ""}`));
      }
      lineBtn.addEventListener("click", () => selectReviewLine(line.number));
      lines.append(lineBtn);
    });
  }
  renderReviewNotes();
  selectReviewLine(state.selectedReviewLine);

  const viewerTitle = $("#documents-viewer-title");
  if (viewerTitle) viewerTitle.textContent = `${review.file.name} (${review.slug})`;
  const viewerActions = $("#documents-viewer-actions");
  if (viewerActions) viewerActions.hidden = false;
}

async function loadDocumentsCatalog() {
  try {
    const payload = await apiFetch("/api/documents/list");
    state.documentsCatalog = payload.documents || [];
    renderDocumentsCatalog();
  } catch (error) {
    console.error("Failed to load documents catalog:", error);
  }
}

function renderDocumentsCatalog() {
  const container = $("#documents-catalog-list");
  if (!container) return;
  const query = ($("#documents-search")?.value || "").trim().toLowerCase();
  container.replaceChildren();

  const visible = (state.documentsCatalog || []).filter((doc) => {
    const search = `${doc.file_name} ${doc.client_name} ${doc.relative_path}`.toLowerCase();
    return !query || search.includes(query);
  });

  if (!visible.length) {
    container.append(node("p", "form-help", state.documentsCatalog?.length ? "No matching files." : "No matter documents available."));
    return;
  }

  visible.forEach((doc) => {
    const card = node("div", "document-catalog-item");
    const meta = node("div", "doc-cat-meta");
    meta.append(node("strong", "doc-cat-name", doc.file_name), node("small", "doc-cat-matter", `${doc.client_name} · ${formatBytes(doc.size)}`));
    card.append(meta);

    if (doc.open_notes > 0) {
      card.append(node("span", "draft-pill warning", `${doc.open_notes} note${doc.open_notes > 1 ? "s" : ""}`));
    }

    const readBtn = node("button", "primary-button mini", "Read & Note");
    readBtn.type = "button";
    readBtn.addEventListener("click", () => {
      openDocumentReview(doc.client_slug, doc.relative_path);
    });
    card.append(readBtn);

    container.append(card);
  });
}

async function openDocumentReview(slug, path, options = {}) {
  try {
    const selected = options.preserveSelection ? state.selectedReviewLine : null;
    const payload = await apiFetch(
      `/api/document_review?slug=${encodeURIComponent(slug)}&path=${encodeURIComponent(path)}`
    );
    state.reviewDocument = { ...payload, slug };
    state.selectedReviewLine = selected;
    renderDocumentReview();
    const dialog = $("#document-review-dialog");
    if (!dialog.open) dialog.showModal();
  } catch (error) {
    toast(error.message, true);
  }
}

async function saveReviewNote(event) {
  event.preventDefault();
  const review = state.reviewDocument;
  if (!review || !state.selectedReviewLine) {
    toast("Choose a document line before adding a note.", true);
    return;
  }
  const submitter = event.submitter || event.currentTarget.querySelector('button[type="submit"]');
  submitter.disabled = true;
  try {
    const payload = await apiFetch("/api/document_review_note", {
      method: "POST",
      body: JSON.stringify({
        slug: review.slug,
        path: review.file.path,
        line_number: state.selectedReviewLine,
        kind: $("#document-review-kind").value,
        comment: $("#document-review-comment").value,
        action: "create",
      }),
    });
    $("#document-review-comment").value = "";
    toast(payload.message);
    await openDocumentReview(review.slug, review.file.path, { preserveSelection: true });
  } catch (error) {
    toast(error.message, true);
  } finally {
    submitter.disabled = false;
  }
}

async function submitDocumentFeedback() {
  const review = state.reviewDocument;
  if (!review) return;
  try {
    const payload = await apiFetch("/api/document_review_submit", {
      method: "POST",
      body: JSON.stringify({ slug: review.slug, path: review.file.path }),
    });
    toast(payload.message);
    await loadStatus();
  } catch (error) {
    toast(error.message, true);
  }
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
      if (isReviewableFile(file.path)) {
        actions.append(fileAction("Review & comment", () => openDocumentReview(slug, file.path)));
      }
      actions.append(fileAction("Download", () => downloadFile(slug, file.path, file.name)));
      if (state.bootstrap?.native_open_enabled) {
        actions.append(fileAction("Open", () => openNativeFile(slug, file.path)));
      }
      row.append(copy, actions);
      files.append(row);
    });
    return payload;
  } catch (error) {
    toast(error.message, true);
    return null;
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
  $("#document-review-close").addEventListener("click", () => {
    $("#document-review-dialog").close();
  });
  $("#document-review-download").addEventListener("click", () => {
    const review = state.reviewDocument;
    if (review) downloadFile(review.slug, review.file.path, review.file.name);
  });
  $("#document-review-native").addEventListener("click", () => {
    const review = state.reviewDocument;
    if (review) openNativeFile(review.slug, review.file.path);
  });
  $("#document-review-note-form").addEventListener("submit", saveReviewNote);
  $("#document-review-submit").addEventListener("click", submitDocumentFeedback);
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
