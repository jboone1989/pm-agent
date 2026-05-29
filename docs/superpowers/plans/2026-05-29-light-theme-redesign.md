# Light Theme UI Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `static/css/app.css` from dark theme to light modern-minimal design while preserving all existing class names, selectors, and JS compatibility.

**Architecture:** Single CSS file rewrite. All color values replaced via CSS custom properties; shadows softened; borders lightened; backgrounds flipped from dark to light. Zero JS changes. Zero HTML changes.

**Tech Stack:** Plain CSS (no preprocessor), CSS custom properties for theming, no new dependencies.

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `static/css/app.css` | Rewrite | All styles — ~1100 lines → ~900 lines |

---

### Task 1: Root variables, reset, and base element styles

**Files:**
- Rewrite: `static/css/app.css`

- [ ] **Step 1: Write the full CSS root variables, reset, body, and base text rules**

Replace the entire file content with the new light-theme CSS. Write all sections in one pass since this is a single-file CSS rewrite with no risk of partial states breaking functionality.

```css
:root {
  --bg: #f8f9fa;
  --surface: #ffffff;
  --surface-hover: #eff6ff;
  --border: #e2e8f0;
  --border-light: #f1f5f9;
  --text: #1e293b;
  --text-secondary: #64748b;
  --primary: #2563eb;
  --primary-hover: #1d4ed8;
  --primary-light: #dbeafe;
  --success: #16a34a;
  --success-light: #dcfce7;
  --warning: #d97706;
  --warning-light: #fef3c7;
  --danger: #dc2626;
  --danger-light: #fee2e2;
  --ad-hoc: #9333ea;
  --ad-hoc-light: #f3e8ff;
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
  --shadow: 0 1px 3px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.04);
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.07), 0 2px 4px rgba(0, 0, 0, 0.04);
  --shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.08), 0 4px 6px rgba(0, 0, 0, 0.04);
  --radius-sm: 6px;
  --radius: 8px;
  --radius-lg: 12px;
  --radius-full: 999px;
  --row-h: 36px;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
}

.app {
  max-width: 100%;
  margin: 0 auto;
  padding: 16px 20px;
  height: 100vh;
  display: flex;
  flex-direction: column;
}
```

- [ ] **Step 2: Commit**

```bash
git add static/css/app.css
git commit -m "feat: rewrite CSS root variables and base styles for light theme"
```

---

### Task 2: Header, layout, panels, and tabs

**Files:**
- Rewrite: `static/css/app.css` (append to existing)

- [ ] **Step 1: Append header, layout, panel, and tab styles**

```css
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
  padding: 12px 16px;
  background: var(--surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  flex-shrink: 0;
}

.header h1 {
  margin: 0 0 2px;
  font-size: 20px;
  font-weight: 700;
  color: var(--text);
}

.header p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.layout {
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex: 1;
  min-height: 0;
}

.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.view-panel {
  flex: 1;
  min-height: 0;
}

.chat-panel {
  flex-shrink: 0;
  max-height: 280px;
  transition: max-height 0.25s ease, opacity 0.2s ease;
  border: 1px solid var(--border);
}

.chat-panel.collapsed {
  max-height: 0;
  border: none;
  opacity: 0;
  pointer-events: none;
}

.panel-header {
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-light);
  background: var(--surface);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.tabs {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  min-width: 0;
}

.tab {
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid transparent;
  border-radius: var(--radius-full);
  padding: 6px 14px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.15s ease;
}

.tab:hover {
  color: var(--text);
  background: var(--border-light);
}

.tab.active {
  color: var(--primary);
  background: var(--primary-light);
  border-color: transparent;
}

.view-content {
  padding: 8px 10px;
  overflow: auto;
  flex: 1;
  background: var(--surface);
}
```

- [ ] **Step 2: Commit**

```bash
git add static/css/app.css
git commit -m "feat: header, layout, panel, and tab styles for light theme"
```

---

### Task 3: Task rows, progress bars, time tracks, and badges

**Files:**
- Rewrite: `static/css/app.css` (append to existing)

- [ ] **Step 1: Append task table, row, progress, time track, and badge styles**

```css
.task-table-head,
.task-row {
  display: grid;
  grid-template-columns: minmax(180px, 2.2fr) 108px 92px 72px 118px;
  gap: 8px;
  align-items: center;
  min-height: calc(var(--row-h) + 12px);
  padding: 4px 10px;
}

.task-table-head {
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 4px;
  min-height: 30px;
}

.task-row {
  border-radius: var(--radius);
  font-size: 13px;
  border: 1px solid transparent;
  transition: background 0.12s ease;
}

.task-row:hover {
  background: var(--surface-hover);
  border-color: var(--primary-light);
}

.task-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
  min-width: 0;
  color: var(--text);
}

.task-title--done {
  text-decoration: line-through;
  color: var(--text-secondary);
  font-weight: 400;
}

.task-row--done {
  opacity: 0.6;
}

.task-row--done:hover {
  opacity: 0.75;
}

.task-title-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.task-title-main {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

/* Time progress bar */
.task-time-progress {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.task-time-progress.muted .time-status {
  font-size: 10px;
  color: var(--text-secondary);
}

.time-track {
  flex: 1;
  height: 4px;
  background: var(--border);
  border-radius: var(--radius-full);
  overflow: hidden;
  min-width: 56px;
}

.time-fill {
  display: block;
  height: 100%;
  border-radius: var(--radius-full);
  background: linear-gradient(90deg, #3b82f6, #2563eb);
}

.time-track--warning .time-fill {
  background: linear-gradient(90deg, #f59e0b, #d97706);
}

.time-track--overdue .time-fill {
  background: linear-gradient(90deg, #ef4444, #dc2626);
}

.time-track--done .time-fill,
.time-track--upcoming .time-fill {
  background: linear-gradient(90deg, #22c55e, #16a34a);
}

.time-status {
  font-size: 10px;
  color: var(--text-secondary);
  white-space: nowrap;
  flex-shrink: 0;
}

.time-status--warning {
  color: var(--warning);
  font-weight: 600;
}

.time-status--overdue {
  color: var(--danger);
  font-weight: 600;
}

.time-status--done {
  color: var(--success);
}

/* Badges */
.badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
}

.badge.status-todo {
  color: var(--text-secondary);
  background: var(--border-light);
}

.badge.status-in_progress {
  color: var(--primary);
  background: var(--primary-light);
}

.badge.status-blocked {
  color: var(--danger);
  background: var(--danger-light);
}

.badge.status-done {
  color: var(--success);
  background: var(--success-light);
}

.badge.status-cancelled {
  color: var(--text-secondary);
  background: var(--border-light);
}

.badge.type-ad_hoc {
  color: var(--ad-hoc);
  background: var(--ad-hoc-light);
}

.badge.time-warning,
.badge.follow-warning {
  color: var(--warning);
  background: var(--warning-light);
}

.badge.time-overdue,
.badge.follow-overdue {
  color: var(--danger);
  background: var(--danger-light);
}

.badge.follow-active {
  color: var(--primary);
  background: var(--primary-light);
}

/* Mini progress in row */
.task-progress-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.mini-track {
  flex: 1;
  height: 6px;
  background: var(--border);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.mini-fill {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #22c55e, #16a34a);
  border-radius: var(--radius-full);
  transition: width 0.3s ease;
}

.task-progress-text {
  font-size: 12px;
  color: var(--text-secondary);
  min-width: 32px;
  text-align: right;
}

.task-assignee,
.task-dates {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-secondary);
  font-size: 12px;
}

/* Detail progress bar */
.progress-row,
.progress-editor-inline {
  display: flex;
  align-items: center;
  gap: 10px;
}

.progress-row {
  margin-top: 4px;
}

.progress-track {
  flex: 1;
  height: 8px;
  background: var(--border);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #22c55e, #16a34a);
  border-radius: var(--radius-full);
  transition: width 0.3s ease;
}

.progress-value {
  min-width: 42px;
  font-size: 12px;
  color: var(--text-secondary);
}
```

- [ ] **Step 2: Commit**

```bash
git add static/css/app.css
git commit -m "feat: task rows, progress bars, time tracks, and badges for light theme"
```

---

### Task 4: Follow-up, schedule, project, and tree sections

**Files:**
- Rewrite: `static/css/app.css` (append to existing)

- [ ] **Step 1: Append follow-up, schedule, project, and tree styles**

```css
.followup-section {
  margin-bottom: 8px;
}

.followup-header {
  margin-bottom: 12px;
}

.followup-header h3 {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 600;
}

.followup-header p {
  margin: 0 0 8px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.followup-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.followup-stat {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  background: var(--border-light);
}

.followup-stat.danger {
  color: var(--danger);
  background: var(--danger-light);
}

.followup-stat.warning {
  color: var(--warning);
  background: var(--warning-light);
}

.followup-stat.active {
  color: var(--primary);
  background: var(--primary-light);
}

/* Tree */
.tree-toggle {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-sm);
  font-size: 12px;
  line-height: 20px;
  text-align: center;
  transition: background 0.1s ease;
}

.tree-toggle:hover {
  background: var(--border-light);
  color: var(--text);
}

.tree-toggle.spacer {
  visibility: hidden;
  pointer-events: none;
}

.children {
  margin-left: 14px;
  border-left: 2px solid var(--border);
  padding-left: 6px;
}

.children.hidden {
  display: none;
}

.tree-node + .tree-node {
  margin-top: 2px;
}

/* Schedule sections */
.project-section {
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}

.project-section:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.schedule-section {
  margin-bottom: 16px;
}

.schedule-section h3 {
  margin: 0 0 6px;
  font-size: 15px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.schedule-section h3::before {
  content: "";
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--primary);
  flex-shrink: 0;
}

.schedule-section h4 {
  margin: 10px 0 4px;
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}
```

- [ ] **Step 2: Commit**

```bash
git add static/css/app.css
git commit -m "feat: follow-up, schedule, project, and tree section styles for light theme"
```

---

### Task 5: Chat panel, messages, mention menu, and input

**Files:**
- Rewrite: `static/css/app.css` (append to existing)

- [ ] **Step 1: Append chat, message, mention, and input styles**

```css
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 80px;
  background: var(--border-light);
}

.message {
  max-width: 85%;
  padding: 8px 12px;
  border-radius: var(--radius);
  line-height: 1.5;
  white-space: pre-wrap;
  font-size: 13px;
}

.message.user {
  align-self: flex-end;
  background: var(--primary);
  color: #ffffff;
}

.message.assistant {
  align-self: flex-start;
  background: var(--surface);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
}

.message .meta {
  margin-top: 6px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.7);
}

.message.assistant .meta {
  color: var(--text-secondary);
}

.mention-menu {
  position: absolute;
  left: 0;
  right: 0;
  bottom: calc(100% + 6px);
  max-height: 220px;
  overflow-y: auto;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  z-index: 30;
}

.mention-menu.hidden {
  display: none;
}

.mention-section-title {
  padding: 6px 10px 4px;
  font-size: 11px;
  color: var(--text-secondary);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.mention-option {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  background: transparent;
  color: var(--text);
  text-align: left;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.08s ease;
}

.mention-option:hover,
.mention-option.active {
  background: var(--surface-hover);
}

.mention-option .mention-kind {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: var(--radius-full);
}

.mention-option .mention-kind.person {
  color: var(--primary);
  background: var(--primary-light);
}

.mention-option .mention-kind.task {
  color: var(--success);
  background: var(--success-light);
}

.mention-option .mention-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mention-option .mention-meta {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-secondary);
}

.message .mention {
  font-weight: 600;
}

.message .mention-person {
  color: #bfdbfe;
}

.message.user .mention-task {
  color: #bbf7d0;
}

.message.assistant .mention-task {
  color: var(--success);
}

.message.assistant .mention-person {
  color: var(--primary);
}

/* Chat form */
.chat-form {
  padding: 10px 12px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: row;
  align-items: flex-end;
  gap: 8px;
  flex-shrink: 0;
  background: var(--surface);
}

.chat-input-wrap {
  position: relative;
  flex: 1;
  min-width: 0;
}

.chat-form textarea {
  display: block;
  width: 100%;
  box-sizing: border-box;
  resize: none;
  min-height: 44px;
  max-height: 88px;
  padding: 10px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--border-light);
  color: var(--text);
  font-size: 13px;
  font-family: inherit;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
  outline: none;
}

.chat-form textarea:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
  background: var(--surface);
}
```

- [ ] **Step 2: Commit**

```bash
git add static/css/app.css
git commit -m "feat: chat panel, messages, mention menu, and input styles for light theme"
```

---

### Task 6: Buttons, forms, detail drawer, and modals

**Files:**
- Rewrite: `static/css/app.css` (append to existing)

- [ ] **Step 1: Append button, form, drawer, and modal styles**

```css
.btn {
  border: none;
  border-radius: var(--radius);
  padding: 8px 14px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  transition: all 0.12s ease;
  font-family: inherit;
}

.btn.primary {
  background: var(--primary);
  color: #ffffff;
}

.btn.primary:hover {
  background: var(--primary-hover);
}

.btn.secondary {
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border);
}

.btn.secondary:hover {
  background: var(--border-light);
  border-color: #cbd5e1;
}

.btn.danger {
  background: var(--danger-light);
  color: var(--danger);
  border: 1px solid #fecaca;
}

.btn.danger:hover {
  background: #fecaca;
}

.btn.sm {
  padding: 5px 10px;
  font-size: 12px;
}

/* Detail form inputs */
.detail-form input,
.detail-form textarea,
.detail-form select {
  width: 100%;
  padding: 8px 10px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font-family: inherit;
  font-size: 13px;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
  outline: none;
}

.detail-form input:focus,
.detail-form textarea:focus,
.detail-form select:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

.detail-form select {
  cursor: pointer;
}

.detail-form textarea {
  resize: vertical;
  min-height: 72px;
  font-family: inherit;
}

.detail-form input.progress-number {
  max-width: 80px;
}

.detail-form {
  display: grid;
  gap: 8px;
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
}

.detail-form label {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}

.detail-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.detail-meta {
  font-size: 13px;
  line-height: 1.6;
  margin: 0 0 8px;
}

.subtask-create-form h4 {
  margin: 0;
  font-size: 14px;
}

.progress-editor-inline {
  width: 100%;
}

.progress-editor-inline input[type="range"] {
  flex: 1;
  accent-color: var(--primary);
}

.empty {
  color: var(--text-secondary);
  padding: 20px;
  text-align: center;
  font-size: 13px;
}

/* Drawer */
.drawer {
  position: fixed;
  top: 0;
  right: 0;
  width: 400px;
  height: 100vh;
  background: var(--surface);
  border-left: 1px solid var(--border);
  box-shadow: var(--shadow-lg);
  z-index: 20;
  display: flex;
  flex-direction: column;
}

.drawer.hidden {
  display: none;
}

.drawer-header,
.drawer-body {
  padding: 14px 16px;
}

.drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--border);
}

.drawer-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.drawer-body {
  overflow: auto;
}

/* Drawer toast */
.drawer-toast {
  margin: 0 16px 12px;
  padding: 10px 12px;
  border-radius: var(--radius);
  font-size: 13px;
}

.drawer-toast.hidden {
  display: none;
}

.drawer-toast.success {
  background: var(--success-light);
  color: #15803d;
}

.drawer-toast.error {
  background: var(--danger-light);
  color: #b91c1c;
}

/* Subtask list */
.subtask-list {
  margin: 0 0 12px;
  padding: 0;
  list-style: none;
}

.subtask-list li {
  margin-bottom: 6px;
}

.subtask-link {
  display: block;
  padding: 8px 12px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--border-light);
  font-size: 13px;
  color: var(--text);
  text-decoration: none;
  transition: all 0.1s ease;
}

.subtask-link:hover {
  border-color: var(--primary);
  color: var(--primary);
  background: var(--primary-light);
}

/* Subtask modal inside drawer */
.subtask-modal {
  position: absolute;
  inset: 0;
  background: rgba(15, 23, 42, 0.3);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  z-index: 5;
}

.subtask-modal.hidden {
  display: none;
}

.subtask-modal-card {
  width: 100%;
  max-height: calc(100vh - 48px);
  overflow: auto;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  padding: 14px 16px;
  display: grid;
  gap: 8px;
}

.subtask-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.subtask-modal-header h4 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.subtask-modal-card label {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}

.subtask-modal-card input,
.subtask-modal-card textarea {
  width: 100%;
  padding: 8px 10px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font-family: inherit;
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.subtask-modal-card input:focus,
.subtask-modal-card textarea:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

.subtask-modal-card textarea {
  resize: vertical;
  min-height: 72px;
  font-family: inherit;
}

/* App modal (create task) */
.app-modal {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.3);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  z-index: 40;
}

.app-modal.hidden {
  display: none;
}

.app-modal-card {
  width: min(420px, 100%);
  max-height: calc(100vh - 48px);
  overflow: auto;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  padding: 14px 16px;
  display: grid;
  gap: 8px;
}

.app-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.app-modal-header h4 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.app-modal-card label {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}

.app-modal-card input,
.app-modal-card textarea,
.app-modal-card select {
  width: 100%;
  padding: 8px 10px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font-family: inherit;
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.app-modal-card input:focus,
.app-modal-card textarea:focus,
.app-modal-card select:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

.app-modal-card select {
  cursor: pointer;
}

.app-modal-card textarea {
  resize: vertical;
  min-height: 72px;
  font-family: inherit;
}

/* App toast */
.app-toast {
  position: fixed;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 50;
  padding: 10px 16px;
  border-radius: var(--radius);
  font-size: 13px;
  font-weight: 500;
  background: var(--surface);
  box-shadow: var(--shadow-md);
}

.app-toast.hidden {
  display: none;
}

.app-toast.success {
  color: #15803d;
  border: 1px solid #bbf7d0;
}

.app-toast.error {
  color: #b91c1c;
  border: 1px solid #fecaca;
}
```

- [ ] **Step 2: Commit**

```bash
git add static/css/app.css
git commit -m "feat: buttons, forms, drawer, and modal styles for light theme"
```

---

### Task 7: Activity log, weekly report, and responsive styles

**Files:**
- Rewrite: `static/css/app.css` (append to existing)

- [ ] **Step 1: Append activity, weekly, and responsive styles**

```css
.activity {
  border-left: 3px solid var(--primary);
  padding: 10px 12px;
  margin-bottom: 8px;
  background: var(--border-light);
  border-radius: 0 var(--radius) var(--radius) 0;
  font-size: 13px;
  line-height: 1.5;
}

.weekly-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}

.weekly-toolbar .week-label {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  min-width: 180px;
}

.weekly-section {
  margin-bottom: 16px;
}

.weekly-section h3 {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
}

.log-entry {
  display: grid;
  grid-template-columns: 110px 64px 1fr;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border-light);
  font-size: 12px;
  align-items: start;
}

.log-entry:last-child {
  border-bottom: none;
}

.log-time {
  color: var(--text-secondary);
}

.log-action {
  color: var(--primary);
  font-weight: 500;
}

.log-message {
  color: var(--text);
  line-height: 1.45;
  word-break: break-word;
}

.report-box {
  background: var(--border-light);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 14px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.clickable {
  cursor: pointer;
}

/* Responsive */
@media (max-width: 900px) {
  .task-table-head,
  .task-row {
    grid-template-columns: minmax(100px, 1.5fr) 72px 80px 64px;
  }

  .task-dates {
    display: none;
  }

  .task-table-head span:last-child {
    display: none;
  }

  .drawer {
    width: 100%;
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add static/css/app.css
git commit -m "feat: activity log, weekly report, and responsive styles for light theme"
```

---

### Task 8: Verification — run the app and check visual result

**Files:** None (verification only)

- [ ] **Step 1: Start the dev server**

```powershell
cd D:\code\pm-agent
.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 2: Open http://127.0.0.1:8000 in a browser**

Verify:
- All tabs render correctly (今日跟进, 列表, 按人, 按项目, 周报)
- Task rows show with proper light theme colors
- Hover states work on rows
- Chat panel opens/closes correctly
- Detail drawer slides in with correct styling
- Create task modal renders properly
- Toasts appear with correct colors
- Responsive breakpoint at 900px works

- [ ] **Step 3: Fix any visual issues found during verification**

- [ ] **Step 4: Final commit if any fixes were made**

```bash
git add static/css/app.css
git commit -m "fix: visual tweaks after light theme verification"
```
