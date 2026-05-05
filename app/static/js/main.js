const state = {
  page: 1,
  pageSize: 20,
  total: 0,
  filters: {},
};

const filtersForm = document.querySelector("#account-filters");
const refreshButton = document.querySelector("#refresh-button");
const statusLine = document.querySelector("#status-line");
const accountsBody = document.querySelector("#accounts-body");
const filterKeys = ["platform", "type", "status", "group", "search"];

function getValue(account, keys, fallback = "-") {
  for (const key of keys) {
    const value = key.split(".").reduce((data, part) => {
      if (data === undefined || data === null) {
        return undefined;
      }
      return data[part];
    }, account);

    if (value !== undefined && value !== null && value !== "") {
      return value;
    }
  }
  return fallback;
}

function formatDate(value) {
  if (!value) {
    return "-";
  }

  const date = new Date(typeof value === "number" ? value * 1000 : value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString("zh-CN", { hour12: false });
}

function formatDuration(seconds) {
  if (seconds === undefined || seconds === null || seconds === "" || seconds < 0) {
    return "-";
  }

  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  if (days > 0) {
    return `${days}d ${hours}h`;
  }
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
}

function formatPercent(value) {
  if (value === undefined || value === null || value === "") {
    return "-";
  }
  return `${Number(value).toFixed(0)}%`;
}

function formatBool(value) {
  if (value === true) {
    return "是";
  }
  if (value === false) {
    return "否";
  }
  return "-";
}

function formatGroups(account) {
  const groups = getValue(account, ["groups"], []);
  if (Array.isArray(groups) && groups.length) {
    return groups
      .map((group) => group.name || group.group_name || group.id)
      .filter(Boolean)
      .join("、");
  }

  const groupIds = getValue(account, ["group_ids"], []);
  if (Array.isArray(groupIds) && groupIds.length) {
    return groupIds.join("、");
  }

  return "-";
}

function getQueryParams() {
  const params = new URLSearchParams({
    page: String(state.page),
    page_size: String(state.pageSize),
  });

  for (const [key, value] of Object.entries(state.filters)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, value);
    }
  }

  if (!filtersForm) {
    return params;
  }

  const formData = new FormData(filtersForm);
  for (const [key, value] of formData.entries()) {
    const text = String(value).trim();
    if (text) {
      params.set(key, text);
    }
  }

  return params;
}

function initStateFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const page = Number(params.get("page"));
  const pageSize = Number(params.get("page_size"));

  if (Number.isInteger(page) && page > 0) {
    state.page = page;
  }

  if (Number.isInteger(pageSize) && pageSize > 0) {
    state.pageSize = pageSize;
  }

  for (const key of filterKeys) {
    const value = params.get(key);
    if (value) {
      state.filters[key] = value;
    }
  }
}

function syncUrlParams() {
  const params = getQueryParams();
  const url = `${window.location.pathname}?${params.toString()}`;
  window.history.replaceState(null, "", url);
}

function normalizePayload(payload) {
  const data = payload.data && !Array.isArray(payload.data) ? payload.data : payload;
  const items = data.items || data.accounts || (Array.isArray(payload.data) ? payload.data : []);
  const safeItems = Array.isArray(items) ? items : [];
  const total = data.total || data.count || safeItems.length;

  return { items: safeItems, total };
}

function renderAccounts(accounts) {
  if (!accounts.length) {
    accountsBody.innerHTML = '<div class="empty-state">暂无账号数据</div>';
    return;
  }

  accountsBody.innerHTML = accounts
    .map((account) => {
      const id = getValue(account, ["id", "account_id"]);
      const name = getValue(account, ["name", "account_name", "extra.email", "email"]);
      const notes = getValue(account, ["notes"]);
      const platform = getValue(account, ["platform"]);
      const type = getValue(account, ["type", "account_type"]);
      const status = getValue(account, ["status"]);
      const schedulable = getValue(account, ["schedulable"], null);
      const groups = formatGroups(account);
      const priority = getValue(account, ["priority"]);
      const concurrency = getValue(account, ["concurrency", "max_concurrency"], 0);
      const currentConcurrency = getValue(account, ["current_concurrency"], 0);
      const rateMultiplier = getValue(account, ["rate_multiplier"]);
      const lastError = getValue(account, ["last_error", "error_message"], "");
      const lastUsedAt = formatDate(getValue(account, ["last_used_at"], ""));
      const expiresAt = formatDate(getValue(account, ["expires_at"], ""));
      const autoPause = formatBool(getValue(account, ["auto_pause_on_expired"], null));
      const rateLimitedAt = formatDate(getValue(account, ["rate_limited_at"], ""));
      const rateLimitResetAt = formatDate(getValue(account, ["rate_limit_reset_at"], ""));
      const tempReason = getValue(account, ["temp_unschedulable_reason"], "");
      const sessionStatus = getValue(account, ["session_window_status"]);
      const codex5hPercent = formatPercent(getValue(account, ["extra.codex_5h_used_percent"], ""));
      const codex5hReset = formatDuration(getValue(account, ["extra.codex_5h_reset_after_seconds"], ""));
      const codex7dPercent = formatPercent(getValue(account, ["extra.codex_7d_used_percent"], ""));
      const codex7dReset = formatDuration(getValue(account, ["extra.codex_7d_reset_after_seconds"], ""));
      const updatedAt = formatDate(getValue(account, ["updated_at", "update_time"], ""));
      const createdAt = formatDate(getValue(account, ["created_at"], ""));

      return `
        <article class="account-card">
          <div class="account-main">
            <div>
              <div class="account-name">${escapeHtml(name)}</div>
              <div class="account-sub">ID ${escapeHtml(id)} · ${escapeHtml(platform)} / ${escapeHtml(type)}</div>
            </div>
            <div class="badge-row">
              <span class="badge ${status === "active" ? "success" : "muted"}">${escapeHtml(status)}</span>
              <span class="badge ${schedulable ? "success" : "warning"}">${schedulable ? "可调度" : "不可调度"}</span>
            </div>
          </div>

          <div class="account-grid">
            ${renderMetric("备注", notes)}
            ${renderMetric("分组", groups)}
            ${renderMetric("并发", `${currentConcurrency} / ${concurrency}`)}
            ${renderMetric("优先级", priority)}
            ${renderMetric("倍率", rateMultiplier)}
            ${renderMetric("会话窗口", sessionStatus)}
            ${renderMetric("Codex 5h", `${codex5hPercent} · ${codex5hReset}`)}
            ${renderMetric("Codex 7d", `${codex7dPercent} · ${codex7dReset}`)}
            ${renderMetric("过期时间", expiresAt)}
            ${renderMetric("过期自动暂停", autoPause)}
            ${renderMetric("最后使用", lastUsedAt)}
            ${renderMetric("限流时间", rateLimitedAt)}
            ${renderMetric("限流恢复", rateLimitResetAt)}
            ${renderMetric("创建时间", createdAt)}
            ${renderMetric("更新时间", updatedAt)}
          </div>

          ${lastError || tempReason ? `
            <div class="account-alerts">
              ${lastError ? `<div><strong>错误：</strong>${escapeHtml(lastError)}</div>` : ""}
              ${tempReason ? `<div><strong>不可调度原因：</strong>${escapeHtml(tempReason)}</div>` : ""}
            </div>
          ` : ""}
        </article>
      `;
    })
    .join("");
}

function renderMetric(label, value) {
  return `
    <div class="metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `;
}

async function loadAccounts() {
  if (!accountsBody) {
    return;
  }

  syncUrlParams();
  statusLine.textContent = "正在加载账号信息...";

  try {
    const response = await fetch(`/api/accounts?${getQueryParams().toString()}`);
    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.detail || "账号信息加载失败");
    }

    const { items, total } = normalizePayload(payload);
    state.total = total;

    renderAccounts(items);
    statusLine.textContent = "账号信息已更新";
  } catch (error) {
    accountsBody.innerHTML = '<div class="empty-state">加载失败</div>';
    statusLine.textContent = error.message;
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

filtersForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  state.page = 1;
  loadAccounts();
});

refreshButton?.addEventListener("click", loadAccounts);

initStateFromUrl();
loadAccounts();
