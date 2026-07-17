"use strict";

const state = {
  data: null,
  rows: [],
  selectedRow: null,
  lastFocusedElement: null,
};

const elements = {
  statusBadge: document.querySelector("#status-badge"),
  warningBanner: document.querySelector("#warning-banner"),
  runDate: document.querySelector("#kpi-run-date"),
  status: document.querySelector("#kpi-status"),
  total: document.querySelector("#kpi-total"),
  actionable: document.querySelector("#kpi-actionable"),
  top30: document.querySelector("#kpi-top30"),
  priorityFilter: document.querySelector("#priority-filter"),
  domainFilter: document.querySelector("#domain-filter"),
  searchInput: document.querySelector("#search-input"),
  resultCount: document.querySelector("#result-count"),
  rows: document.querySelector("#opportunity-rows"),
  emptyState: document.querySelector("#empty-state"),
  detailPanel: document.querySelector("#detail-panel"),
  detailBackdrop: document.querySelector("#detail-backdrop"),
  detailClose: document.querySelector("#detail-close"),
  detailTitle: document.querySelector("#detail-title"),
  detailMeta: document.querySelector("#detail-meta"),
  detailContent: document.querySelector("#detail-content"),
};

const statusLabels = {
  OK: "정상",
  PARTIAL: "경고",
  ERROR: "오류",
};

function safeText(value, fallback = "-") {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }
  return String(value);
}

function formatNumber(value) {
  return Number.isFinite(Number(value))
    ? new Intl.NumberFormat("ko-KR").format(Number(value))
    : "-";
}

function setStatus(status) {
  const normalized = ["OK", "PARTIAL", "ERROR"].includes(status) ? status : "ERROR";
  elements.statusBadge.className = `status-badge status-${normalized.toLowerCase()}`;
  elements.statusBadge.textContent = statusLabels[normalized];
  elements.status.textContent = statusLabels[normalized];
}

function showWarning(messages) {
  const values = Array.isArray(messages) ? messages.filter(Boolean) : [messages].filter(Boolean);
  elements.warningBanner.replaceChildren();
  if (values.length === 0) {
    elements.warningBanner.hidden = true;
    return;
  }
  const title = document.createElement("strong");
  title.textContent = "데이터 상태를 확인하세요.";
  elements.warningBanner.append(title);
  const list = document.createElement("ul");
  values.forEach((message) => {
    const item = document.createElement("li");
    item.textContent = safeText(message);
    list.append(item);
  });
  elements.warningBanner.append(list);
  elements.warningBanner.hidden = false;
}

function addOptions(select, values) {
  [...new Set(values.filter(Boolean))]
    .sort((a, b) => String(a).localeCompare(String(b), "ko"))
    .forEach((value) => {
      const option = document.createElement("option");
      option.value = String(value);
      option.textContent = String(value);
      select.append(option);
    });
}

function makeCell(text, className = "") {
  const cell = document.createElement("td");
  cell.textContent = safeText(text);
  if (className) {
    cell.className = className;
  }
  return cell;
}

function makePriorityBadge(priority) {
  const cell = document.createElement("td");
  const badge = document.createElement("span");
  const safePriority = safeText(priority, "UNKNOWN");
  badge.className = "priority-badge";
  badge.dataset.priority = safePriority;
  badge.textContent = safePriority;
  cell.append(badge);
  return cell;
}

function filteredRows() {
  const priority = elements.priorityFilter.value;
  const domain = elements.domainFilter.value;
  const query = elements.searchInput.value.trim().toLocaleLowerCase("ko");
  return state.rows.filter((row) => {
    if (priority && row.priority_band !== priority) {
      return false;
    }
    if (domain && row.domain_type !== domain) {
      return false;
    }
    if (!query) {
      return true;
    }
    const haystack = [
      row.title,
      row.organization,
      row.recommended_next_action,
    ]
      .map((value) => safeText(value, "").toLocaleLowerCase("ko"))
      .join(" ");
    return haystack.includes(query);
  });
}

function renderTable() {
  const rows = filteredRows();
  elements.rows.replaceChildren();
  rows.forEach((row) => {
    const tableRow = document.createElement("tr");
    tableRow.tabIndex = 0;
    tableRow.setAttribute("role", "button");
    tableRow.setAttribute("aria-label", `${safeText(row.title)} 상세 보기`);
    tableRow.append(
      makeCell(row.rank, "rank-cell"),
      makePriorityBadge(row.priority_band),
      makeCell(row.domain_type, "domain-cell"),
      makeCell(row.title, "title-cell"),
      makeCell(row.organization, "organization-cell"),
      makeCell(row.deadline, "date-cell"),
      makeCell(row.unified_priority_score, "score-cell"),
      makeCell(row.recommended_next_action, "action-cell"),
    );
    tableRow.addEventListener("click", () => openDetail(row, tableRow));
    tableRow.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openDetail(row, tableRow);
      }
    });
    elements.rows.append(tableRow);
  });
  elements.resultCount.textContent = `${rows.length}건`;
  elements.emptyState.hidden = rows.length !== 0;
}

function appendDetail(label, value, options = {}) {
  const section = document.createElement("section");
  section.className = "detail-section";
  const heading = document.createElement("h3");
  heading.textContent = label;
  section.append(heading);

  const values = Array.isArray(value) ? value : [value];
  const visibleValues = values.filter(
    (item) => item !== null && item !== undefined && item !== "",
  );
  if (options.links) {
    const linkList = document.createElement("div");
    linkList.className = "source-links";
    visibleValues.forEach((urlValue, index) => {
      try {
        const url = new URL(String(urlValue));
        if (!["http:", "https:"].includes(url.protocol)) {
          return;
        }
        const link = document.createElement("a");
        link.href = url.href;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = `원문 ${index + 1}`;
        linkList.append(link);
      } catch {
        // Invalid URLs are intentionally omitted.
      }
    });
    if (linkList.childElementCount === 0) {
      const empty = document.createElement("p");
      empty.textContent = "공개 원문 링크 없음";
      section.append(empty);
    } else {
      section.append(linkList);
    }
  } else if (visibleValues.length > 1) {
    const list = document.createElement("ul");
    visibleValues.forEach((item) => {
      const listItem = document.createElement("li");
      listItem.textContent = safeText(item);
      list.append(listItem);
    });
    section.append(list);
  } else {
    const paragraph = document.createElement("p");
    paragraph.textContent = safeText(visibleValues[0]);
    section.append(paragraph);
  }
  elements.detailContent.append(section);
}

function openDetail(row, trigger) {
  state.selectedRow = row;
  state.lastFocusedElement = trigger;
  elements.detailTitle.textContent = safeText(row.title);
  elements.detailMeta.textContent = `${safeText(row.priority_band)} · ${safeText(row.domain_type)} · #${safeText(row.rank)}`;
  elements.detailContent.replaceChildren();
  appendDetail("기관", row.organization);
  appendDetail("현재 단계", row.opportunity_stage);
  appendDetail("주경로", row.primary_opportunity_route);
  appendDetail("적합 근거", row.relevance_reasons);
  appendDetail("예상 QRPick 역할", row.expected_qrpick_role);
  appendDetail("권장 다음 행동", row.recommended_next_action);
  appendDetail("미확인 사항", row.blocking_unknowns);
  appendDetail("공개일", row.posted_at);
  appendDetail("마감일", row.deadline);
  appendDetail("원문 링크", row.source_urls, { links: true });
  elements.detailPanel.classList.add("is-open");
  elements.detailPanel.setAttribute("aria-hidden", "false");
  elements.detailBackdrop.hidden = false;
  elements.detailClose.focus();
}

function closeDetail() {
  elements.detailPanel.classList.remove("is-open");
  elements.detailPanel.setAttribute("aria-hidden", "true");
  elements.detailBackdrop.hidden = true;
  state.selectedRow = null;
  if (state.lastFocusedElement) {
    state.lastFocusedElement.focus();
  }
}

function validateData(data) {
  const required = [
    "run_date",
    "run_status",
    "total_count",
    "actionable_count",
    "top30_count",
    "opportunities",
  ];
  required.forEach((key) => {
    if (!(key in data)) {
      throw new Error(`배포 데이터 필드 누락: ${key}`);
    }
  });
  if (!Array.isArray(data.opportunities)) {
    throw new Error("opportunities가 배열이 아닙니다.");
  }
  if (data.opportunities.length === 0 || Number(data.total_count) === 0) {
    throw new Error("정상 산출물이 0건입니다.");
  }
  if (data.opportunities.length !== Number(data.top30_count)) {
    throw new Error("Top 30 건수가 일치하지 않습니다.");
  }
}

function renderDashboard(data) {
  validateData(data);
  state.data = data;
  state.rows = [...data.opportunities].sort((a, b) => Number(a.rank) - Number(b.rank));
  elements.runDate.textContent = safeText(data.run_date);
  elements.total.textContent = formatNumber(data.total_count);
  elements.actionable.textContent = formatNumber(data.actionable_count);
  elements.top30.textContent = formatNumber(data.top30_count);
  setStatus(data.run_status);
  addOptions(elements.priorityFilter, state.rows.map((row) => row.priority_band));
  addOptions(elements.domainFilter, state.rows.map((row) => row.domain_type));

  const warnings = Array.isArray(data.warnings) ? [...data.warnings] : [];
  if (data.run_status !== "OK") {
    warnings.unshift(`실행 상태가 ${safeText(data.run_status)}입니다.`);
  }
  showWarning(warnings);
  renderTable();
}

function renderFailure(error) {
  setStatus("ERROR");
  showWarning(`데이터를 불러오지 못했습니다: ${safeText(error.message)}`);
  elements.rows.replaceChildren();
  elements.resultCount.textContent = "오류";
  elements.emptyState.hidden = true;
}

elements.priorityFilter.addEventListener("change", renderTable);
elements.domainFilter.addEventListener("change", renderTable);
elements.searchInput.addEventListener("input", renderTable);
elements.detailClose.addEventListener("click", closeDetail);
elements.detailBackdrop.addEventListener("click", closeDetail);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.selectedRow) {
    closeDetail();
  }
});

fetch("data/latest.json", { cache: "no-store" })
  .then((response) => {
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return response.json();
  })
  .then(renderDashboard)
  .catch(renderFailure);
