const state = {
  page: 1,
  pageSize: 20,
  total: 0,
};

const filtersForm = document.querySelector("#account-filters");
const refreshButton = document.querySelector("#refresh-button");
const prevButton = document.querySelector("#prev-page");
const nextButton = document.querySelector("#next-page");
const statusLine = document.querySelector("#status-line");
const accountsBody = document.querySelector("#accounts-body");
const pageInfo = document.querySelector("#page-info");

function getValue(account, keys, fallback = "-") {
  for (const key of keys) {
    const value = account[key];
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

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString("zh-CN", { hour12: false });
}

function getQueryParams() {
  const params = new URLSearchParams({
    page: String(state.page),
    page_size: String(state.pageSize),
  });

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

function normalizePayload(payload) {
  const items = payload.items || payload.data || payload.accounts || [];
  const total = payload.total || payload.count || items.length;

  return { items, total };
}

function renderAccounts(accounts) {
  if (!accounts.length) {
    accountsBody.innerHTML = '<tr><td colspan="10">暂无账号数据</td></tr>';
    return;
  }

  accountsBody.innerHTML = accounts
    .map((account) => {
      const id = getValue(account, ["id", "account_id"]);
      const name = getValue(account, ["name", "account_name", "email"]);
      const platform = getValue(account, ["platform"]);
      const type = getValue(account, ["type", "account_type"]);
      const status = getValue(account, ["status"]);
      const group = getValue(account, ["group", "group_name"]);
      const priority = getValue(account, ["priority"]);
      const concurrency = getValue(account, ["concurrency", "max_concurrency"]);
      const lastError = getValue(account, ["last_error", "error_message"]);
      const updatedAt = formatDate(getValue(account, ["updated_at", "update_time"], ""));

      return `
        <tr>
          <td>${escapeHtml(id)}</td>
          <td>${escapeHtml(name)}</td>
          <td>${escapeHtml(platform)}</td>
          <td>${escapeHtml(type)}</td>
          <td><span class="badge">${escapeHtml(status)}</span></td>
          <td>${escapeHtml(group)}</td>
          <td>${escapeHtml(priority)}</td>
          <td>${escapeHtml(concurrency)}</td>
          <td class="error-cell">${escapeHtml(lastError)}</td>
          <td>${escapeHtml(updatedAt)}</td>
        </tr>
      `;
    })
    .join("");
}

function renderPagination() {
  const pageCount = Math.max(1, Math.ceil(state.total / state.pageSize));
  pageInfo.textContent = `第 ${state.page} / ${pageCount} 页，共 ${state.total} 条`;
  prevButton.disabled = state.page <= 1;
  nextButton.disabled = state.page >= pageCount;
}

async function loadAccounts() {
  if (!accountsBody) {
    return;
  }

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
    renderPagination();
    statusLine.textContent = "账号信息已更新";
  } catch (error) {
    accountsBody.innerHTML = '<tr><td colspan="10">加载失败</td></tr>';
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

prevButton?.addEventListener("click", () => {
  if (state.page > 1) {
    state.page -= 1;
    loadAccounts();
  }
});

nextButton?.addEventListener("click", () => {
  state.page += 1;
  loadAccounts();
});

loadAccounts();
