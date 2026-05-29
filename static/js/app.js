const state = {
  currentView: "followup",
  items: [],
  personSchedules: [],
  assignees: [],
  detailItemId: null,
  chatOpen: false,
  weeklyWeekKey: null,
  weeklyLog: null,
  collapsedItemIds: new Set(),
};

const STATUS_LABELS = {
  todo: "待办",
  in_progress: "进行中",
  blocked: "阻塞",
  done: "已完成",
  cancelled: "已取消",
};

const TYPE_LABELS = {
  planned: "计划",
  ad_hoc: "临时",
};

const PRIORITY_LABELS = {
  low: "低",
  medium: "中",
  high: "高",
  urgent: "紧急",
};

const ACTION_LABELS = {
  create: "创建",
  update: "更新",
  delete: "删除",
  chat: "对话",
  agent: "Agent",
};

const chatPanel = document.getElementById("chatPanel");
const chatMessages = document.getElementById("chatMessages");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const mentionMenu = document.getElementById("mentionMenu");
const viewContent = document.getElementById("viewContent");
const detailDrawer = document.getElementById("detailDrawer");
const detailTitle = document.getElementById("detailTitle");
const detailBody = document.getElementById("detailBody");
const drawerToast = document.getElementById("drawerToast");
const subtaskModal = document.getElementById("subtaskModal");
const createTaskModal = document.getElementById("createTaskModal");
const appToast = document.getElementById("appToast");
const assigneeOptions = document.getElementById("assigneeOptions");
const toggleChatBtn = document.getElementById("toggleChatBtn");

const mentionState = {
  open: false,
  trigger: null,
  start: 0,
  end: 0,
  query: "",
  selectedIndex: 0,
  items: [],
};

function flattenWorkItems(items, acc = []) {
  for (const item of items) {
    acc.push(item);
    if (item.children?.length) {
      flattenWorkItems(item.children, acc);
    }
  }
  return acc;
}

function getMentionContext(textarea) {
  const value = textarea.value;
  const cursor = textarea.selectionStart ?? value.length;
  const before = value.slice(0, cursor);

  const atMatch = before.match(/(?:^|[\s\n])@([^\s@#]*)$/);
  if (atMatch) {
    return {
      trigger: "@",
      query: atMatch[1],
      start: before.lastIndexOf("@"),
      end: cursor,
    };
  }

  const hashMatch = before.match(/(?:^|[\s\n])#([^\s@#]*)$/);
  if (hashMatch) {
    return {
      trigger: "#",
      query: hashMatch[1],
      start: before.lastIndexOf("#"),
      end: cursor,
    };
  }

  return null;
}

function buildMentionSuggestions(query, trigger) {
  const q = query.trim().toLowerCase();

  if (trigger === "@") {
    return state.assignees
      .filter((name) => !q || name.toLowerCase().includes(q))
      .slice(0, 12)
      .map((name) => ({
        type: "person",
        label: name,
        meta: "负责人",
        insert: `@${name} `,
      }));
  }

  return flattenWorkItems(state.items)
    .filter((item) => {
      if (!q) return true;
      return item.title.toLowerCase().includes(q) || String(item.id).includes(q);
    })
    .slice(0, 12)
    .map((item) => ({
      type: "task",
      label: item.title,
      meta: `#${item.id} · ${item.assignee || "未分配"}`,
      insert: `#${item.id}「${item.title}」 `,
    }));
}

function closeMentionMenu() {
  mentionState.open = false;
  mentionState.trigger = null;
  mentionState.items = [];
  mentionState.selectedIndex = 0;
  mentionMenu.classList.add("hidden");
  mentionMenu.innerHTML = "";
}

function renderMentionMenu() {
  const items = mentionState.items;
  if (!items.length) {
    closeMentionMenu();
    return;
  }

  if (mentionState.selectedIndex >= items.length) {
    mentionState.selectedIndex = items.length - 1;
  }
  if (mentionState.selectedIndex < 0) {
    mentionState.selectedIndex = 0;
  }

  const sectionTitle = mentionState.trigger === "@" ? "负责人" : "任务";
  let html = `<div class="mention-section-title">${sectionTitle}</div>`;
  items.forEach((item, index) => {
    html += `
      <button
        type="button"
        class="mention-option${index === mentionState.selectedIndex ? " active" : ""}"
        data-mention-index="${index}"
        role="option"
        aria-selected="${index === mentionState.selectedIndex}"
      >
        <span class="mention-kind ${item.type}">${item.type === "person" ? "@" : "#"}</span>
        <span class="mention-label">${escapeHtml(item.label)}</span>
        <span class="mention-meta">${escapeHtml(item.meta)}</span>
      </button>
    `;
  });

  mentionMenu.innerHTML = html;
  mentionMenu.classList.remove("hidden");
  const active = mentionMenu.querySelector(".mention-option.active");
  active?.scrollIntoView({ block: "nearest" });
}

function openMentionMenu(context) {
  const items = buildMentionSuggestions(context.query, context.trigger);
  if (!items.length) {
    closeMentionMenu();
    return;
  }

  mentionState.open = true;
  mentionState.trigger = context.trigger;
  mentionState.start = context.start;
  mentionState.end = context.end;
  mentionState.query = context.query;
  mentionState.selectedIndex = 0;
  mentionState.items = items;
  renderMentionMenu();
}

function applyMention(item) {
  const before = chatInput.value.slice(0, mentionState.start);
  const after = chatInput.value.slice(mentionState.end);
  chatInput.value = `${before}${item.insert}${after}`;
  const cursor = before.length + item.insert.length;
  chatInput.setSelectionRange(cursor, cursor);
  closeMentionMenu();
  chatInput.focus();
}

function updateMentionMenuFromInput() {
  const context = getMentionContext(chatInput);
  if (!context) {
    closeMentionMenu();
    return;
  }

  if (
    mentionState.open &&
    mentionState.trigger === context.trigger &&
    mentionState.start === context.start &&
    mentionState.query === context.query
  ) {
    return;
  }

  openMentionMenu(context);
}

function formatChatMessage(text) {
  let html = escapeHtml(text);
  html = html.replace(
    /#(\d+)「([^」]+)」/g,
    '<span class="mention mention-task" title="任务 ID $1">#$1「$2」</span>'
  );
  html = html.replace(/#(\d+)(?!「)/g, '<span class="mention mention-task" title="任务 ID $1">#$1</span>');
  html = html.replace(/@([\u4e00-\u9fa5A-Za-z0-9_.-]+)/g, '<span class="mention mention-person">@$1</span>');
  return html;
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatDateShort(value) {
  if (!value) return "-";
  return value.length >= 10 ? value.slice(5) : value;
}

function parseDateOnly(value) {
  if (!value) return null;
  const text = value.length >= 10 ? value.slice(0, 10) : value;
  const [year, month, day] = text.split("-").map(Number);
  if (!year || !month || !day) return null;
  return new Date(year, month - 1, day);
}

function daysBetween(fromDate, toDate) {
  return Math.round((toDate - fromDate) / 86400000);
}

function getTimeProgressInfo(item) {
  const today = parseDateOnly(todayDateString());
  let start = parseDateOnly(item.start_date);
  const due = parseDateOnly(item.due_date);
  const dateRange = `${formatDateShort(item.start_date)}~${formatDateShort(item.due_date)}`;
  const isClosed = item.status === "done" || item.status === "cancelled";

  if (!start && !due) {
    return {
      kind: "none",
      percent: 0,
      label: "未设时间",
      title: "未设置开始或截止日期",
      dateRange,
    };
  }

  if (!start && due) {
    start = today <= due ? today : due;
  }

  const rangeStart = start || due;
  const rangeEnd = due || start;

  if (isClosed) {
    const percent =
      rangeEnd > rangeStart
        ? Math.max(0, Math.min(100, Math.round((daysBetween(rangeStart, today) / daysBetween(rangeStart, rangeEnd)) * 100)))
        : 100;
    return {
      kind: "done",
      percent,
      label: item.status === "done" ? "已完成" : "已取消",
      title: `${dateRange} · ${item.status === "done" ? "已完成" : "已取消"}`,
      dateRange,
    };
  }

  if (today < rangeStart) {
    const daysUntil = daysBetween(today, rangeStart);
    return {
      kind: "upcoming",
      percent: 0,
      label: `${daysUntil}天后开始`,
      title: `${dateRange} · 计划 ${daysUntil} 天后开始`,
      dateRange,
    };
  }

  if (today > rangeEnd) {
    const overdueDays = daysBetween(rangeEnd, today);
    return {
      kind: "overdue",
      percent: 100,
      label: `超期${overdueDays}天`,
      title: `${dateRange} · 已超期 ${overdueDays} 天`,
      dateRange,
    };
  }

  const totalDays = Math.max(daysBetween(rangeStart, rangeEnd), 1);
  const elapsedDays = daysBetween(rangeStart, today);
  const percent = Math.max(0, Math.min(100, Math.round((elapsedDays / totalDays) * 100)));
  const daysRemaining = daysBetween(today, rangeEnd);
  const label = daysRemaining === 0 ? "今天到期" : `剩余${daysRemaining}天`;
  const timeLeftRatio = 100 - percent;
  const kind = daysRemaining <= 3 || timeLeftRatio <= 20 ? "warning" : "normal";

  return {
    kind,
    percent,
    label,
    title: `${dateRange} · 已用 ${percent}% · ${label}`,
    dateRange,
  };
}

function renderTimeProgressBar(item) {
  const info = getTimeProgressInfo(item);
  if (info.kind === "none") {
    return `<div class="task-time-progress muted" title="${escapeHtml(info.title)}"><span class="time-status">${escapeHtml(info.label)}</span></div>`;
  }

  return `
    <div class="task-time-progress" title="${escapeHtml(info.title)}">
      <span class="time-track time-track--${info.kind}">
        <span class="time-fill" style="width: ${info.percent}%"></span>
      </span>
      <span class="time-status time-status--${info.kind}">${escapeHtml(info.label)}</span>
    </div>
  `;
}

function renderTitleCell(item, { inTree = false } = {}) {
  const titleClass = item.status === "done" ? "task-title task-title--done" : "task-title";
  const title = `<span class="${titleClass}" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</span>`;
  const main = inTree
    ? `<div class="task-title-main">${renderTreeToggle(item)}${title}</div>`
    : `<div class="task-title-main">${title}</div>`;
  return `<div class="task-title-cell">${main}${renderTimeProgressBar(item)}</div>`;
}

function todayDateString() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function clampProgress(value) {
  const number = Number(value);
  if (Number.isNaN(number)) return 0;
  return Math.min(100, Math.max(0, Math.round(number)));
}

function badge(text, className = "") {
  return `<span class="badge ${className}">${escapeHtml(text)}</span>`;
}

function renderProgressBar(progress) {
  const value = clampProgress(progress);
  return `
    <div class="progress-row">
      <div class="progress-track">
        <div class="progress-fill" style="width: ${value}%"></div>
      </div>
      <span class="progress-value">${value}%</span>
    </div>
  `;
}

function formatLogTime(value) {
  if (!value) return "";
  return value.replace("T", " ").slice(0, 16);
}

function shiftWeekKey(weekKey, offset) {
  const match = weekKey.match(/^(\d{4})-W(\d{2})$/);
  if (!match) return weekKey;
  const year = Number(match[1]);
  const week = Number(match[2]);
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const day = jan4.getUTCDay() || 7;
  const week1Monday = new Date(jan4);
  week1Monday.setUTCDate(jan4.getUTCDate() - day + 1);
  const targetMonday = new Date(week1Monday);
  targetMonday.setUTCDate(week1Monday.getUTCDate() + (week - 1 + offset) * 7);
  const targetYear = targetMonday.getUTCFullYear();
  const targetWeek = getIsoWeek(targetMonday);
  return `${targetYear}-W${String(targetWeek).padStart(2, "0")}`;
}

function getIsoWeek(date) {
  const tmp = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
  const day = tmp.getUTCDay() || 7;
  tmp.setUTCDate(tmp.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(tmp.getUTCFullYear(), 0, 1));
  return Math.ceil(((tmp - yearStart) / 86400000 + 1) / 7);
}

function renderTableHead() {
  return `
    <div class="task-table-head">
      <span>任务</span>
      <span>状态</span>
      <span>进度</span>
      <span>负责人</span>
      <span>时间</span>
    </div>
  `;
}

function isItemCollapsed(itemId) {
  return state.collapsedItemIds.has(itemId);
}

function toggleItemCollapsed(itemId) {
  if (state.collapsedItemIds.has(itemId)) {
    state.collapsedItemIds.delete(itemId);
  } else {
    state.collapsedItemIds.add(itemId);
  }
  renderCurrentView();
}

function renderTreeToggle(item) {
  const hasChildren = item.children?.length > 0;
  if (!hasChildren) {
    return `<span class="tree-toggle spacer" aria-hidden="true"></span>`;
  }
  const collapsed = isItemCollapsed(item.id);
  return `
    <button
      type="button"
      class="tree-toggle"
      data-toggle-item-id="${item.id}"
      aria-label="${collapsed ? "展开子任务" : "折叠子任务"}"
      aria-expanded="${!collapsed}"
    >${collapsed ? "▸" : "▾"}</button>
  `;
}

function getFollowUpScore(item) {
  const timeInfo = getTimeProgressInfo(item);
  let score = 0;
  if (timeInfo.kind === "overdue") score += 1000;
  else if (timeInfo.kind === "warning") score += 500;
  if (item.status === "blocked") score += 300;
  if (item.status === "in_progress") score += 200;
  if (item.status === "todo") score += 100;
  score += timeInfo.percent || 0;
  return score;
}

function getFollowUpReason(item) {
  const timeInfo = getTimeProgressInfo(item);
  if (timeInfo.kind === "overdue") return "超期";
  if (timeInfo.kind === "warning") return "临期";
  if (item.status === "blocked") return "阻塞";
  if (item.status === "in_progress") return "进行中";
  return "待更新";
}

function needsDailyFollowUp(item) {
  if (item.status === "done" || item.status === "cancelled") {
    return false;
  }
  const timeInfo = getTimeProgressInfo(item);
  if (timeInfo.kind === "overdue" || timeInfo.kind === "warning") {
    return true;
  }
  if (item.status === "in_progress" || item.status === "blocked") {
    return true;
  }
  if (item.status === "todo" && timeInfo.kind !== "upcoming") {
    return true;
  }
  return false;
}

function getFollowUpItems() {
  return flattenWorkItems(state.items)
    .filter(needsDailyFollowUp)
    .sort((a, b) => getFollowUpScore(b) - getFollowUpScore(a) || a.id - b.id);
}

function renderCompactRow(item, { inTree = false, showFollowReason = false } = {}) {
  const progress = clampProgress(item.progress ?? 0);
  const dateRange = `${formatDateShort(item.start_date)}~${formatDateShort(item.due_date)}`;
  const timeInfo = getTimeProgressInfo(item);
  const isDone = item.status === "done";
  const followReason = showFollowReason ? getFollowUpReason(item) : "";

  return `
    <div class="task-row clickable${isDone ? " task-row--done" : ""}" data-item-id="${item.id}" data-item-title="${escapeHtml(item.title)}">
      ${renderTitleCell(item, { inTree })}
      <span class="task-badges">
        ${showFollowReason ? badge(followReason, `follow-${followReason === "超期" ? "overdue" : followReason === "临期" ? "warning" : "active"}`) : ""}
        ${badge(STATUS_LABELS[item.status] || item.status, `status-${item.status}`)}
        ${item.type === "ad_hoc" ? badge(TYPE_LABELS.ad_hoc, "type-ad_hoc") : ""}
        ${!showFollowReason && timeInfo.kind === "warning" ? badge("临期", "time-warning") : ""}
        ${!showFollowReason && timeInfo.kind === "overdue" ? badge("超期", "time-overdue") : ""}
      </span>
      <span class="task-progress-cell">
        <span class="mini-track"><span class="mini-fill" style="width: ${progress}%"></span></span>
        <span class="task-progress-text">${progress}%</span>
      </span>
      <span class="task-assignee" title="${escapeHtml(item.assignee || "未分配")}">${escapeHtml(item.assignee || "未分配")}</span>
      <span class="task-dates" title="${escapeHtml(timeInfo.title)}">${escapeHtml(dateRange)}</span>
    </div>
  `;
}

function renderTreeItem(item) {
  const hasChildren = item.children?.length > 0;
  const collapsed = hasChildren && isItemCollapsed(item.id);
  const children = (item.children || []).map((child) => renderTreeItem(child)).join("");
  return `
    <div class="tree-node${collapsed ? " collapsed" : ""}">
      ${renderCompactRow(item, { inTree: true })}
      ${children ? `<div class="children${collapsed ? " hidden" : ""}">${children}</div>` : ""}
    </div>
  `;
}

function appendMessage(role, content, meta = "") {
  const div = document.createElement("div");
  div.className = `message ${role}`;
  div.innerHTML = `${formatChatMessage(content)}${meta ? `<div class="meta">${escapeHtml(meta)}</div>` : ""}`;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  if (response.status === 204) return null;
  return response.json();
}

function updateAssigneeDatalist() {
  assigneeOptions.innerHTML = state.assignees
    .map((name) => `<option value="${escapeHtml(name)}"></option>`)
    .join("");
}

function validateDates(startDate, dueDate) {
  if (startDate && dueDate && startDate > dueDate) {
    throw new Error("开始日期不能晚于截止日期");
  }
}

async function updateWorkItemFields(itemId, fields) {
  validateDates(fields.start_date, fields.due_date);
  await fetchJson(`/api/work-items/${itemId}`, {
    method: "PATCH",
    body: JSON.stringify(fields),
  });
  await loadData();
  if (state.detailItemId === itemId) {
    await openDetail(itemId);
  }
}

async function createSubtask(parentId, form) {
  const title = (form.title || "").trim();
  if (!title) {
    throw new Error("请输入子任务名称");
  }
  validateDates(form.start_date, form.due_date);
  const created = await fetchJson("/api/work-items", {
    method: "POST",
    body: JSON.stringify({
      title,
      parent_id: parentId,
      assignee: form.assignee,
      start_date: form.start_date,
      due_date: form.due_date,
      description: (form.description || "").trim(),
      type: "planned",
      status: "todo",
    }),
  });
  await loadData();
  if (state.detailItemId === parentId) {
    await openDetail(parentId);
    showDrawerToast(`已创建子任务「${created.title}」`, "success");
  }
  return created;
}

function showDrawerToast(message, type = "error") {
  drawerToast.textContent = message;
  drawerToast.className = `drawer-toast ${type}`;
  drawerToast.classList.remove("hidden");
  if (type === "success") {
    window.setTimeout(() => drawerToast.classList.add("hidden"), 3000);
  }
}

function hideDrawerToast() {
  drawerToast.classList.add("hidden");
}

function showAppToast(message, type = "error") {
  appToast.textContent = message;
  appToast.className = `app-toast ${type}`;
  appToast.classList.remove("hidden");
  if (type === "success") {
    window.setTimeout(() => appToast.classList.add("hidden"), 3000);
  }
}

function populateCreateTaskParentSelect() {
  const select = document.getElementById("createTaskParent");
  const current = select.value;
  select.innerHTML = `<option value="">无（顶层任务）</option>${flattenWorkItems(state.items)
    .map((item) => `<option value="${item.id}">${escapeHtml(item.title)} (#${item.id})</option>`)
    .join("")}`;
  if (current) {
    select.value = current;
  }
}

function initCreateTaskSelects() {
  document.getElementById("createTaskStatus").innerHTML = renderSelectOptions(STATUS_LABELS, "todo");
  document.getElementById("createTaskType").innerHTML = renderSelectOptions(TYPE_LABELS, "planned");
  document.getElementById("createTaskPriority").innerHTML = renderSelectOptions(PRIORITY_LABELS, "medium");
}

function resetCreateTaskForm() {
  const today = todayDateString();
  document.getElementById("createTaskTitle").value = "";
  document.getElementById("createTaskDescription").value = "";
  document.getElementById("createTaskParent").value = "";
  document.getElementById("createTaskAssignee").value = "";
  document.getElementById("createTaskStart").value = today;
  document.getElementById("createTaskDue").value = today;
  document.getElementById("createTaskStatus").value = "todo";
  document.getElementById("createTaskType").value = "planned";
  document.getElementById("createTaskPriority").value = "medium";
}

function openCreateTaskModal() {
  populateCreateTaskParentSelect();
  resetCreateTaskForm();
  createTaskModal.classList.remove("hidden");
  document.getElementById("createTaskTitle").focus();
}

function closeCreateTaskModal() {
  createTaskModal.classList.add("hidden");
}

async function createTask(form) {
  const title = (form.title || "").trim();
  if (!title) {
    throw new Error("请输入任务名称");
  }
  validateDates(form.start_date, form.due_date);
  const created = await fetchJson("/api/work-items", {
    method: "POST",
    body: JSON.stringify({
      title,
      description: (form.description || "").trim(),
      parent_id: form.parent_id ? Number(form.parent_id) : null,
      assignee: form.assignee,
      start_date: form.start_date,
      due_date: form.due_date,
      status: form.status,
      type: form.type,
      priority: form.priority,
    }),
  });
  await loadData();
  return created;
}

function resetSubtaskForm() {
  const today = todayDateString();
  document.getElementById("detailSubtaskTitle").value = "";
  document.getElementById("detailSubtaskDescription").value = "";
  document.getElementById("detailSubtaskAssignee").value = "";
  document.getElementById("detailSubtaskStart").value = today;
  document.getElementById("detailSubtaskDue").value = today;
}

function openSubtaskModal() {
  resetSubtaskForm();
  subtaskModal.classList.remove("hidden");
  document.getElementById("detailSubtaskTitle").focus();
}

function closeSubtaskModal() {
  subtaskModal.classList.add("hidden");
}

function findItemInTree(items, itemId) {
  for (const item of items) {
    if (item.id === itemId) return item;
    if (item.children?.length) {
      const found = findItemInTree(item.children, itemId);
      if (found) return found;
    }
  }
  return null;
}

function renderSubtaskList(children) {
  if (!children?.length) {
    return `<div class="empty" style="padding:12px">暂无子任务，可在下方添加。</div>`;
  }
  return `<ul class="subtask-list">${children
    .map(
      (child) => `
        <li>
          <a href="#" class="subtask-link" data-open-item-id="${child.id}">
            ${escapeHtml(child.title)} · ${clampProgress(child.progress ?? 0)}% · ${escapeHtml(STATUS_LABELS[child.status] || child.status)}
          </a>
        </li>
      `
    )
    .join("")}</ul>`;
}

async function deleteWorkItem(itemId, title) {
  const label = title || "该任务";
  if (!window.confirm(`确定删除「${label}」吗？子任务也会一并删除。`)) {
    return;
  }
  await fetchJson(`/api/work-items/${itemId}`, { method: "DELETE" });
  if (state.detailItemId === itemId) {
    detailDrawer.classList.add("hidden");
    state.detailItemId = null;
  }
  await loadData();
}

function renderFollowUpView() {
  const items = getFollowUpItems();
  const todayLabel = todayDateString();
  const overdueCount = items.filter((item) => getTimeProgressInfo(item).kind === "overdue").length;
  const warningCount = items.filter((item) => getTimeProgressInfo(item).kind === "warning").length;
  const activeCount = items.filter((item) => item.status === "in_progress").length;

  if (!items.length) {
    viewContent.innerHTML = `
      <section class="followup-section">
        <div class="followup-header">
          <h3>今日跟进 · ${escapeHtml(todayLabel)}</h3>
          <p>今天没有需要跟进的任务。可以在「列表」查看全部，或通过 Agent 汇报新进展。</p>
        </div>
        <div class="empty">暂无待跟进任务</div>
      </section>
    `;
    return;
  }

  viewContent.innerHTML = `
    <section class="followup-section">
      <div class="followup-header">
        <h3>今日跟进 · ${escapeHtml(todayLabel)}</h3>
        <p>建议每天更新这些任务的进展，优先处理超期、临期与进行中的工作。</p>
        <div class="followup-summary">
          <span class="followup-stat">共 ${items.length} 项</span>
          ${overdueCount ? `<span class="followup-stat danger">${overdueCount} 超期</span>` : ""}
          ${warningCount ? `<span class="followup-stat warning">${warningCount} 临期</span>` : ""}
          ${activeCount ? `<span class="followup-stat active">${activeCount} 进行中</span>` : ""}
        </div>
      </div>
      ${renderTableHead()}
      ${items.map((item) => `<div class="tree-node">${renderCompactRow(item, { showFollowReason: true })}</div>`).join("")}
    </section>
  `;
}

function renderListView() {
  if (!state.items.length) {
    viewContent.innerHTML = `<div class="empty">还没有工作项。点击右上角「Agent 对话」创建工作，或让 Agent 帮你整理。</div>`;
    return;
  }
  viewContent.innerHTML = renderTableHead() + state.items.map((item) => renderTreeItem(item)).join("");
}

function renderPersonView() {
  if (!state.personSchedules.length) {
    viewContent.innerHTML = `<div class="empty">暂无按人排期。在任务详情里分配负责人后会出现在这里。</div>`;
    return;
  }

  viewContent.innerHTML = state.personSchedules
    .map(
      (person) => `
        <section class="schedule-section">
          <h3>${escapeHtml(person.assignee)}</h3>
          ${
            person.items.length
              ? renderTableHead() + person.items.map((item) => `<div class="tree-node">${renderCompactRow(item)}</div>`).join("")
              : ""
          }
          ${
            person.ad_hoc_items.length
              ? `<h4>临时跟进</h4>${renderTableHead()}${person.ad_hoc_items
                  .map((item) => `<div class="tree-node">${renderCompactRow({ ...item, type: "ad_hoc" })}</div>`)
                  .join("")}`
              : person.items.length
                ? ""
                : `<div class="empty">暂无任务</div>`
          }
        </section>
      `
    )
    .join("");
}

function renderWeeklyView() {
  const data = state.weeklyLog;
  if (!data) {
    viewContent.innerHTML = `<div class="empty">加载周报中...</div>`;
    return;
  }

  const report = data.report;
  viewContent.innerHTML = `
    <div class="weekly-toolbar">
      <button type="button" class="btn secondary btn-sm" data-week-nav="-1">上一周</button>
      <span class="week-label">${escapeHtml(data.week_label)}</span>
      <button type="button" class="btn secondary btn-sm" data-week-nav="1">下一周</button>
      <button type="button" class="btn primary btn-sm" id="generateWeeklyBtn">生成周报</button>
    </div>
    <section class="weekly-section">
      <h3>本周工作</h3>
      <div class="report-box">${escapeHtml(report?.this_week_summary || "尚未生成。点击「生成周报」基于下方操作记录自动总结。")}</div>
    </section>
    <section class="weekly-section">
      <h3>下周计划</h3>
      <div class="report-box">${escapeHtml(report?.next_week_plan || "生成周报后将根据未完成任务与截止日给出建议。")}</div>
    </section>
    <section class="weekly-section">
      <h3>本周操作记录（${data.entries.length} 条）</h3>
      ${
        data.entries.length
          ? `<div class="report-box" style="padding:0">${data.entries
              .map(
                (entry) => `
                  <div class="log-entry">
                    <span class="log-time">${escapeHtml(formatLogTime(entry.created_at))}</span>
                    <span class="log-action">${escapeHtml(ACTION_LABELS[entry.action] || entry.action)}</span>
                    <span class="log-message">${escapeHtml(entry.message)}</span>
                  </div>
                `
              )
              .join("")}</div>`
          : `<div class="empty">本周还没有操作记录。编辑任务、与 Agent 对话后会自动记录在这里。</div>`
      }
    </section>
  `;

  document.getElementById("generateWeeklyBtn").addEventListener("click", generateWeeklyReport);
  document.querySelectorAll("[data-week-nav]").forEach((button) => {
    button.addEventListener("click", () => {
      const offset = Number(button.dataset.weekNav);
      loadWeeklyLog(shiftWeekKey(data.week_key, offset));
    });
  });
}

async function loadWeeklyLog(weekKey = null) {
  const url = weekKey ? `/api/weekly-log?week=${encodeURIComponent(weekKey)}` : "/api/weekly-log";
  state.weeklyLog = await fetchJson(url);
  state.weeklyWeekKey = state.weeklyLog.week_key;
  if (state.currentView === "weekly") {
    renderWeeklyView();
  }
}

async function generateWeeklyReport() {
  const button = document.getElementById("generateWeeklyBtn");
  if (button) {
    button.disabled = true;
    button.textContent = "生成中...";
  }
  try {
    const week = state.weeklyWeekKey || state.weeklyLog?.week_key;
    const url = week ? `/api/weekly-log/generate?week=${encodeURIComponent(week)}` : "/api/weekly-log/generate";
    await fetchJson(url, { method: "POST" });
    await loadWeeklyLog(week);
  } catch (error) {
    window.alert(`生成失败：${error.message}`);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "生成周报";
    }
  }
}

function renderProjectView() {
  if (!state.items.length) {
    viewContent.innerHTML = `<div class="empty">暂无项目。先创建一个顶层大工作。</div>`;
    return;
  }

  viewContent.innerHTML = state.items
    .map(
      (project) => `
        <section class="project-section">
          ${renderTableHead()}
          ${renderTreeItem(project)}
        </section>
      `
    )
    .join("");
}

function renderCurrentView() {
  if (state.currentView === "followup") renderFollowUpView();
  if (state.currentView === "list") renderListView();
  if (state.currentView === "person") renderPersonView();
  if (state.currentView === "project") renderProjectView();
  if (state.currentView === "weekly") {
    if (state.weeklyLog) renderWeeklyView();
    else loadWeeklyLog(state.weeklyWeekKey);
  }
}

async function loadData() {
  const [items, personSchedules, assignees] = await Promise.all([
    fetchJson("/api/work-items"),
    fetchJson("/api/work-items/schedules/by-person"),
    fetchJson("/api/work-items/meta/assignees"),
  ]);
  state.items = items;
  state.personSchedules = personSchedules;
  state.assignees = assignees;
  updateAssigneeDatalist();
  renderCurrentView();
}

function renderSelectOptions(labels, selectedValue) {
  return Object.entries(labels)
    .map(
      ([value, label]) =>
        `<option value="${escapeHtml(value)}"${value === selectedValue ? " selected" : ""}>${escapeHtml(label)}</option>`
    )
    .join("");
}

function bindProgressInputs(rangeInput, numberInput, labelEl) {
  if (!rangeInput || !numberInput) return;
  const sync = (value) => {
    const progress = clampProgress(value);
    rangeInput.value = String(progress);
    numberInput.value = String(progress);
    if (labelEl) labelEl.textContent = `${progress}%`;
  };
  rangeInput.addEventListener("input", () => sync(rangeInput.value));
  numberInput.addEventListener("input", () => sync(numberInput.value));
}

async function openDetail(itemId) {
  hideDrawerToast();
  const [item, activities] = await Promise.all([
    fetchJson(`/api/work-items/${itemId}`),
    fetchJson(`/api/work-items/${itemId}/activities`),
  ]);
  const treeItem = findItemInTree(state.items, itemId);
  const children = treeItem?.children || [];

  state.detailItemId = itemId;
  detailTitle.textContent = item.title;
  detailBody.innerHTML = `
    <div class="detail-form">
      <label for="detailAssignee">负责人</label>
      <input id="detailAssignee" list="assigneeOptions" value="${escapeHtml(item.assignee || "")}" placeholder="输入或选择负责人" />
      <label for="detailStartDate">开始日期</label>
      <input id="detailStartDate" type="date" value="${escapeHtml(item.start_date || "")}" />
      <label for="detailDueDate">截止日期</label>
      <input id="detailDueDate" type="date" value="${escapeHtml(item.due_date || "")}" />
      <label for="detailProgress">进度 (%)</label>
      <div class="progress-editor-inline">
        <input id="detailProgressRange" type="range" min="0" max="100" value="${clampProgress(item.progress ?? 0)}" />
        <input id="detailProgress" class="progress-number" type="number" min="0" max="100" value="${clampProgress(item.progress ?? 0)}" />
        <span id="detailProgressLabel" class="progress-value">${clampProgress(item.progress ?? 0)}%</span>
      </div>
      ${renderProgressBar(item.progress ?? 0)}
      <label for="detailStatus">状态</label>
      <select id="detailStatus">${renderSelectOptions(STATUS_LABELS, item.status)}</select>
      <label for="detailType">类型</label>
      <select id="detailType">${renderSelectOptions(TYPE_LABELS, item.type)}</select>
      <label for="detailPriority">优先级</label>
      <select id="detailPriority">${renderSelectOptions(PRIORITY_LABELS, item.priority)}</select>
      <label for="detailDescription">描述</label>
      <textarea id="detailDescription" rows="3" placeholder="可选">${escapeHtml(item.description || "")}</textarea>
      <div class="detail-actions">
        <button type="button" class="btn secondary" id="saveDetailItem">保存修改</button>
        <button type="button" class="btn danger" id="deleteDetailItem">删除任务</button>
        <button type="button" class="btn secondary" id="openSubtaskFormBtn">+ 添加子任务</button>
      </div>
    </div>
    <section class="weekly-section">
      <h4>子任务（${children.length}）</h4>
      ${renderSubtaskList(children)}
    </section>
    <h4>进展记录</h4>
    ${
      activities.length
        ? activities
            .map(
              (log) => `
                <div class="activity">
                  <div>${escapeHtml(log.content)}</div>
                  <div class="task-dates">${escapeHtml(log.created_at)} · ${escapeHtml(log.source)}</div>
                </div>
              `
            )
            .join("")
        : `<div class="empty">暂无进展记录</div>`
    }
  `;

  bindProgressInputs(
    document.getElementById("detailProgressRange"),
    document.getElementById("detailProgress"),
    document.getElementById("detailProgressLabel")
  );

  closeSubtaskModal();
  detailDrawer.classList.remove("hidden");
}

detailBody.addEventListener("click", async (event) => {
  const subtaskLink = event.target.closest("[data-open-item-id]");
  if (subtaskLink) {
    event.preventDefault();
    await openDetail(Number(subtaskLink.dataset.openItemId));
    return;
  }

  const itemId = state.detailItemId;
  if (!itemId) return;

  if (event.target.id === "openSubtaskFormBtn") {
    openSubtaskModal();
    return;
  }

  if (event.target.id === "saveDetailItem") {
    try {
      await updateWorkItemFields(itemId, {
        assignee: document.getElementById("detailAssignee").value.trim() || null,
        start_date: document.getElementById("detailStartDate").value || null,
        due_date: document.getElementById("detailDueDate").value || null,
        progress: clampProgress(document.getElementById("detailProgress").value),
        status: document.getElementById("detailStatus").value,
        type: document.getElementById("detailType").value,
        priority: document.getElementById("detailPriority").value,
        description: document.getElementById("detailDescription").value.trim(),
      });
      showDrawerToast("已保存修改", "success");
    } catch (error) {
      showDrawerToast(`保存失败：${error.message}`, "error");
    }
    return;
  }

  if (event.target.id === "deleteDetailItem") {
    const title = detailTitle.textContent;
    await deleteWorkItem(itemId, title);
  }
});

detailDrawer.addEventListener("click", async (event) => {
  const itemId = state.detailItemId;
  if (!itemId) return;

  if (event.target.id === "closeSubtaskModal") {
    closeSubtaskModal();
    return;
  }

  if (event.target.id === "subtaskModal" && event.target === subtaskModal) {
    closeSubtaskModal();
    return;
  }

  if (event.target.id === "createDetailSubtask") {
    const button = event.target;
    const titleInput = document.getElementById("detailSubtaskTitle");
    const title = titleInput.value.trim();
    if (!title) {
      showDrawerToast("请先填写子任务名称", "error");
      titleInput.focus();
      return;
    }
    button.disabled = true;
    const oldText = button.textContent;
    button.textContent = "创建中...";
    try {
      await createSubtask(itemId, {
        title,
        description: document.getElementById("detailSubtaskDescription").value.trim(),
        assignee: document.getElementById("detailSubtaskAssignee").value.trim() || null,
        start_date: document.getElementById("detailSubtaskStart").value || null,
        due_date: document.getElementById("detailSubtaskDue").value || null,
      });
      closeSubtaskModal();
    } catch (error) {
      showDrawerToast(`创建失败：${error.message}`, "error");
    } finally {
      button.disabled = false;
      button.textContent = oldText;
    }
  }
});

function setChatOpen(open) {
  state.chatOpen = open;
  chatPanel.classList.toggle("collapsed", !open);
  toggleChatBtn.textContent = open ? "收起对话" : "Agent 对话";
  if (open) {
    chatInput.focus();
  }
}

viewContent.addEventListener("click", async (event) => {
  const toggle = event.target.closest("[data-toggle-item-id]");
  if (toggle) {
    event.preventDefault();
    event.stopPropagation();
    toggleItemCollapsed(Number(toggle.dataset.toggleItemId));
    return;
  }

  const row = event.target.closest(".task-row");
  if (row) {
    await openDetail(Number(row.dataset.itemId));
  }
});

toggleChatBtn.addEventListener("click", () => {
  setChatOpen(!state.chatOpen);
});

chatInput.addEventListener("input", updateMentionMenuFromInput);

chatInput.addEventListener("keydown", (event) => {
  if (!mentionState.open || !mentionState.items.length) return;

  if (event.key === "ArrowDown") {
    event.preventDefault();
    mentionState.selectedIndex = Math.min(mentionState.selectedIndex + 1, mentionState.items.length - 1);
    renderMentionMenu();
    return;
  }

  if (event.key === "ArrowUp") {
    event.preventDefault();
    mentionState.selectedIndex = Math.max(mentionState.selectedIndex - 1, 0);
    renderMentionMenu();
    return;
  }

  if (event.key === "Enter" || event.key === "Tab") {
    event.preventDefault();
    applyMention(mentionState.items[mentionState.selectedIndex]);
    return;
  }

  if (event.key === "Escape") {
    event.preventDefault();
    closeMentionMenu();
  }
});

mentionMenu.addEventListener("mousedown", (event) => {
  event.preventDefault();
});

mentionMenu.addEventListener("click", (event) => {
  const option = event.target.closest("[data-mention-index]");
  if (!option) return;
  const index = Number(option.dataset.mentionIndex);
  const item = mentionState.items[index];
  if (item) applyMention(item);
});

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  closeMentionMenu();
  const message = chatInput.value.trim();
  if (!message) return;

  setChatOpen(true);
  appendMessage("user", message);
  chatInput.value = "";
  chatInput.disabled = true;

  let thinkingMsg = appendMessage("assistant", "⏳ 正在分析...");
  let streamingEl = null;

  try {
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });

    if (!response.ok) {
      throw new Error("服务器返回错误：" + response.status);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";

      for (const part of parts) {
        const lines = part.split("\n");
        let eventType = "";
        let data = "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            data = line.slice(6);
          }
        }

        if (!data) continue;

        try {
          const payload = JSON.parse(data);

          if (eventType === "status") {
            if (thinkingMsg && thinkingMsg.parentNode) {
              thinkingMsg.innerHTML = "⏳ " + escapeHtml(payload.text);
            }
          } else if (eventType === "text") {
            if (thinkingMsg && thinkingMsg.parentNode) {
              thinkingMsg.remove();
              thinkingMsg = null;
            }
            if (!streamingEl) {
              streamingEl = appendMessage("assistant", "");
            }
            streamingEl.innerHTML += formatChatMessage(payload.text);
            chatMessages.scrollTop = chatMessages.scrollHeight;
          } else if (eventType === "tool_start") {
            if (thinkingMsg && thinkingMsg.parentNode) {
              thinkingMsg.remove();
              thinkingMsg = null;
            }
            streamingEl = null;
            const toolEl = appendMessage("assistant", "🔧 " + escapeHtml(payload.label || payload.tool) + "...");
            toolEl.dataset.tool = payload.tool;
          } else if (eventType === "tool_end") {
            const prevTool = chatMessages.querySelector('[data-tool="' + payload.tool + '"]:last-child');
            if (prevTool) {
              prevTool.innerHTML = "✅ " + escapeHtml(payload.label || payload.tool);
            }
          } else if (eventType === "done") {
            streamingEl = null;
          }
        } catch (e) {
          // skip malformed events
        }
      }
    }
  } catch (error) {
    if (thinkingMsg && thinkingMsg.parentNode) {
      thinkingMsg.remove();
      thinkingMsg = null;
    }
    streamingEl = null;
    appendMessage("assistant", "出错了：" + (error.message || String(error)));
  } finally {
    chatInput.disabled = false;
    chatInput.focus();
    try { await loadData(); } catch (e) { /* ignore */ }
  }
});

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((el) => el.classList.remove("active"));
    tab.classList.add("active");
    state.currentView = tab.dataset.view;
    renderCurrentView();
  });
});

document.getElementById("refreshBtn").addEventListener("click", async () => {
  await loadData();
  if (state.currentView === "weekly") {
    await loadWeeklyLog(state.weeklyWeekKey);
  }
});
document.getElementById("closeDrawer").addEventListener("click", () => {
  closeSubtaskModal();
  detailDrawer.classList.add("hidden");
  state.detailItemId = null;
});

document.getElementById("openCreateTaskBtn").addEventListener("click", openCreateTaskModal);
document.getElementById("closeCreateTaskModal").addEventListener("click", closeCreateTaskModal);
createTaskModal.addEventListener("click", (event) => {
  if (event.target === createTaskModal) {
    closeCreateTaskModal();
  }
});
document.getElementById("submitCreateTask").addEventListener("click", async () => {
  const button = document.getElementById("submitCreateTask");
  const titleInput = document.getElementById("createTaskTitle");
  const title = titleInput.value.trim();
  if (!title) {
    showAppToast("请先填写任务名称", "error");
    titleInput.focus();
    return;
  }

  button.disabled = true;
  const oldText = button.textContent;
  button.textContent = "创建中...";
  try {
    const created = await createTask({
      title,
      description: document.getElementById("createTaskDescription").value.trim(),
      parent_id: document.getElementById("createTaskParent").value,
      assignee: document.getElementById("createTaskAssignee").value.trim() || null,
      start_date: document.getElementById("createTaskStart").value || null,
      due_date: document.getElementById("createTaskDue").value || null,
      status: document.getElementById("createTaskStatus").value,
      type: document.getElementById("createTaskType").value,
      priority: document.getElementById("createTaskPriority").value,
    });
    closeCreateTaskModal();
    showAppToast(`已创建任务「${created.title}」`, "success");
    await openDetail(created.id);
  } catch (error) {
    showAppToast(`创建失败：${error.message}`, "error");
  } finally {
    button.disabled = false;
    button.textContent = oldText;
  }
});

initCreateTaskSelects();

appendMessage(
  "assistant",
  "你好。输入 @ 提及负责人，# 提及任务；点击任务行可编辑详情、进度和子任务。"
);

loadData().catch((error) => {
  viewContent.innerHTML = `<div class="empty">加载失败：${escapeHtml(error.message)}</div>`;
});
