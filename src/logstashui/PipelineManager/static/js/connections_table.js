/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// Connections Table — pagination, search, and filtering for the main page.
// Mirrors the pattern used by SNMP/static/js/devices_table.js.

let currentPage = 1;
let pageSize = 50;
let currentSearch = '';
let currentPolicy = '';
let currentState = '';

// ── Shared SVG snippets ───────────────────────────────────────────────────────

const CURSOR_ICON_SVG = `<svg class="w-3 h-3 opacity-60" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122"/></svg>`;

// ── Test connectivity button handlers ─────────────────────────────────────────
// These are called from hx-on attributes. Defining them as named functions
// avoids embedding SVG markup (which contains double-quotes) inside an
// HTML double-quoted attribute value, which would break innerHTML parsing.

window._connTestClick = function (el) {
  el.innerHTML = 'Testing...';
  el.classList.remove('bg-blue-100', 'text-blue-800', 'hover:bg-blue-200');
  el.classList.add('bg-yellow-100', 'text-yellow-800', 'animate-pulse');
};

window._connTestAfterRequest = function (el, event) {
  const result = event.detail.successful
    ? { text: 'Connected',        bg: 'bg-green-100', textColor: 'text-green-800', hover: 'hover:bg-green-200' }
    : { text: 'Connection Failed', bg: 'bg-red-100',   textColor: 'text-red-800',   hover: 'hover:bg-red-200'   };
  el.innerHTML = result.text + ' ' + CURSOR_ICON_SVG;
  el.classList.remove('bg-yellow-100', 'text-yellow-800', 'animate-pulse');
  el.classList.add(result.bg, result.textColor, result.hover);
  const toast = document.querySelector('#toast-container > div');
  if (toast) {
    setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 3000);
  }
};

// ── Main loader ───────────────────────────────────────────────────────────────

function loadConnections() {
  const tbody = document.getElementById('connectionsTableBody');
  // On the empty-state page (has_connections=False) the table chrome is not
  // rendered at all; nothing to do.
  if (!tbody) return;

  const loadingState = document.getElementById('connectionsLoadingState');
  const noResultsState = document.getElementById('connectionsNoResults');
  const tableContainer = document.getElementById('connectionsTableContainer');
  const paginationControls = document.getElementById('paginationControls');

  // Show loading inside the card; hide no-results and pagination
  if (loadingState) loadingState.classList.remove('hidden');
  if (noResultsState) noResultsState.classList.add('hidden');
  if (tableContainer) tableContainer.classList.remove('hidden');
  if (paginationControls) paginationControls.classList.add('hidden');
  tbody.innerHTML = '';

  const params = new URLSearchParams({
    page: currentPage,
    page_size: pageSize,
  });
  if (currentSearch) params.append('search', currentSearch);
  if (currentPolicy) params.append('policy', currentPolicy);
  if (currentState) params.append('state', currentState);

  fetch(`/ConnectionManager/GetConnectionsTable/?${params.toString()}`)
    .then(r => r.json())
    .then(data => {
      if (loadingState) loadingState.classList.add('hidden');

      if (data.total === 0) {
        // If no filters are active this means there are genuinely no connections
        // left. Reload the page so the server renders the "Get Started" shell
        // rather than keeping the filter/table chrome visible.
        if (!currentSearch && !currentPolicy && !currentState) {
          window.location.reload();
          return;
        }
        if (tableContainer) tableContainer.classList.add('hidden');
        if (noResultsState) noResultsState.classList.remove('hidden');
        return;
      }

      renderRows(data.connections);
      updatePaginationControls(data);
      if (paginationControls) paginationControls.classList.remove('hidden');

      // Populate policy dropdown once (first load or after policy list changes)
      populatePolicyFilter(data.policies || []);
    })
    .catch(err => {
      if (loadingState) loadingState.classList.add('hidden');
      console.error('Error loading connections:', err);
      tbody.innerHTML = `
        <tr>
          <td colspan="7" class="px-6 py-8 text-center text-red-400">
            Error loading connections: ${escapeHtml(err.message)}
          </td>
        </tr>`;
    });
}

// ── Row rendering ─────────────────────────────────────────────────────────────

function renderRows(connections) {
  const tbody = document.getElementById('connectionsTableBody');
  tbody.innerHTML = '';

  connections.forEach(conn => {
    // Main row
    const tr = document.createElement('tr');
    tr.className = `hover:bg-gray-700/50 transition-colors border-0 ${borderClass(conn.group_color)}`;
    tr.id = `connection-row-${conn.pk}`;
    tr.innerHTML = buildConnectionRow(conn);
    tbody.appendChild(tr);

    // Expand row (pipeline list)
    const expandTr = document.createElement('tr');
    expandTr.id = `pipelines-${conn.pk}`;
    expandTr.className = 'hidden bg-gray-900';
    expandTr.innerHTML = `<td colspan="7"><div class="p-4"><div class="htmx-fade-in"></div></div></td>`;
    tbody.appendChild(expandTr);
  });

  // Let HTMX know about any newly added hx-* attributes
  if (window.htmx) htmx.process(tbody);
}

function borderClass(color) {
  const map = {
    blue:   'border-l-4 border-blue-500',
    green:  'border-l-4 border-green-500',
    purple: 'border-l-4 border-purple-500',
    pink:   'border-l-4 border-pink-500',
    yellow: 'border-l-4 border-yellow-500',
    cyan:   'border-l-4 border-cyan-500',
  };
  return color ? (map[color] || '') : '';
}

function buildConnectionRow(conn) {
  return `
    <!-- Expand button -->
    <td class="px-2 py-4 whitespace-nowrap text-sm text-gray-300">
      <button class="expand-button p-1 hover:bg-gray-700 rounded transition-transform"
        onclick="
          const target = document.getElementById('pipelines-${conn.pk}');
          if (target.classList.contains('hidden')) {
            target.classList.remove('hidden');
            htmx.ajax('GET', '/ConnectionManager/GetPipelines/${conn.pk}/', {target: '#pipelines-${conn.pk}', swap: 'innerHTML'});
          } else {
            target.classList.add('hidden');
            target.innerHTML = '';
          }
          this.querySelector('svg').classList.toggle('rotate-180');
        ">
        <svg class="w-5 h-5 transform transition-transform duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
    </td>

    <!-- Type icon -->
    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
      ${buildTypeCell(conn)}
    </td>

    <!-- Name + badges -->
    <td class="px-6 py-4 text-sm font-medium text-white">
      ${buildNameCell(conn)}
    </td>

    <!-- Host -->
    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300"
        title="${escapeHtml(conn.host || conn.cloud_id)}">
      ${escapeHtml(conn.host ? conn.host.substring(0, 20) : (conn.cloud_id || '').substring(0, 12))}
    </td>

    <!-- Policy -->
    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
      ${buildPolicyCell(conn)}
    </td>

    <!-- Status -->
    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300 text-center overflow-visible">
      ${buildStatusCell(conn)}
    </td>

    <!-- Actions -->
    <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
      ${buildActionsCell(conn)}
    </td>
  `;
}

function buildTypeCell(conn) {
  if (conn.connection_type === 'CENTRALIZED') {
    return `
      <div class="flex flex-col items-center">
        <div class="rounded-lg p-2" style="background: radial-gradient(circle, rgba(59, 130, 246, 0.15) 0%, rgba(59, 130, 246, 0.05) 70%, transparent 100%);">
          <img src="${window.elasticIconUrl}" alt="Centralized" width="52" height="52" class="inline-block">
        </div>
        <span class="text-xs text-gray-500 mt-1 centralized-type-label-${conn.pk}">Elastic</span>
      </div>`;
  }
  return `
    <div class="flex flex-col items-center">
      <div class="rounded-lg p-2" style="background: radial-gradient(circle, rgba(168, 85, 247, 0.15) 0%, rgba(168, 85, 247, 0.05) 70%, transparent 100%);">
        <img src="${window.logstashIconUrl}" alt="Agent" width="52" height="52" class="inline-block">
      </div>
      <span class="text-xs text-gray-500 mt-1">LogstashAgent</span>
    </div>`;
}

function buildNameCell(conn) {
  let versionLine = '';
  if (conn.connection_type !== 'CENTRALIZED' && conn.agent_version) {
    let upgradeHtml = '';
    if (conn.desired_agent_version && conn.agent_version !== conn.desired_agent_version) {
      upgradeHtml = `<span class="text-xs text-gray-500">Upgrading</span>`;
    } else if (conn.agent_version_relation === 'newer') {
      upgradeHtml = `<span class="text-xs text-amber-300/90">unreleased version</span>`;
    } else if (conn.agent_version_relation === 'older' || conn.agent_version_relation === 'unknown') {
      upgradeHtml = `<button onclick="upgradeAgent(${conn.pk}, ${escapeHtml(JSON.stringify(conn.name))}, ${escapeHtml(JSON.stringify(window.preferredAgentVersion))})"
        class="text-xs px-2 py-0.5 rounded bg-blue-600 hover:bg-blue-700 text-white font-medium transition-colors">
        Upgrade
      </button>`;
    }
    versionLine = `<div class="flex items-center gap-2 mt-0.5">
      <span class="text-xs text-gray-500">v${escapeHtml(conn.agent_version)}</span>
      ${upgradeHtml}
    </div>`;
  }

  const agentBadge = conn.feature_agent
    ? `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-purple-500/15 text-purple-300 border border-purple-500/30">LogstashAgent</span>`
    : '';

  const lsVersionBadge = conn.logstash_version
    ? `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-cyan-500/15 text-cyan-300 border border-cyan-500/30" title="Logstash ${escapeHtml(conn.logstash_version)}">LS ${escapeHtml(conn.logstash_version)}</span>`
    : '';

  const cpmBadge = conn.feature_cpm
    ? `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-500/15 text-blue-300 border border-blue-500/30" title="Centralized Pipeline Management">CPM</span>`
    : '';

  const snmpBadge = conn.feature_snmp
    ? `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/15 text-emerald-300 border border-emerald-500/30" title="Has Agent-mode SNMP pipelines">SNMP</span>`
    : '';

  return `
    <div class="flex flex-col">
      <span>${escapeHtml(conn.name)}</span>
      ${versionLine}
      <div class="flex flex-wrap items-center gap-1 mt-1.5">
        ${agentBadge}
        <span class="ls-version-container inline-flex" data-agent-id="${conn.pk}">
          ${lsVersionBadge}
        </span>
        ${cpmBadge}
        ${snmpBadge}
      </div>
    </div>`;
}

function buildPolicyCell(conn) {
  if (conn.connection_type === 'CENTRALIZED') {
    return `<span class="italic text-gray-400">Centralized</span>`;
  }
  if (conn.policy_id) {
    return `<a href="/ConnectionManager/AgentPolicies?policy_id=${conn.policy_id}"
      class="text-gray-300 hover:text-purple-400 hover:underline transition-colors">
      ${escapeHtml(conn.policy_name)}
    </a>`;
  }
  return `<span class="italic text-gray-500">No Policy</span>`;
}

function buildStatusCell(conn) {
  if (conn.connection_type === 'CENTRALIZED') {
    // Test connectivity button — handlers defined as window._connTest* to avoid
    // embedding SVG double-quotes inside a double-quoted HTML attribute.
    return `<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 cursor-pointer hover:bg-blue-200"
      hx-get="/ConnectionManager/TestConnectivity?test=${conn.pk}"
      hx-trigger="click"
      hx-target="#toast-container"
      hx-indicator=".loading"
      hx-on::click="_connTestClick(this)"
      hx-on::after-request="_connTestAfterRequest(this, event)">
      Test
      ${CURSOR_ICON_SVG}
    </span>`;
  }

  // Agent: status badge inside .status-container for SSE updates
  const badgeHtml = buildAgentStatusBadge(conn);
  return `<div class="status-container relative inline-flex items-center justify-center mx-auto"
    data-agent-id="${conn.pk}"
    data-agent-name="${escapeHtml(conn.name)}">
    ${badgeHtml}
  </div>`;
}

function buildAgentStatusBadge(conn) {
  // JSON.stringify produces double-quoted strings; escapeHtml turns them into
  // &quot; so the browser's HTML parser doesn't end the attribute early.
  const onClickAttr = `onclick="openAgentInspect('${conn.pk}', ${escapeHtml(JSON.stringify(conn.name))})"`;
  switch (conn.status) {
    case 'restarting':
      return `<span class="pulse-badge pulse-blue inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 cursor-pointer" ${onClickAttr}>Restarting ${CURSOR_ICON_SVG}</span>`;
    case 'offline':
      return `<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 cursor-pointer" ${onClickAttr}>Offline ${CURSOR_ICON_SVG}</span>`;
    case 'unhealthy':
      return `<span class="pulse-badge pulse-yellow inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 cursor-pointer" ${onClickAttr}>Unhealthy ${CURSOR_ICON_SVG}</span>`;
    default: // healthy
      return `<span class="pulse-badge pulse-green inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 cursor-pointer" ${onClickAttr}>Healthy ${CURSOR_ICON_SVG}</span>`;
  }
}

function buildActionsCell(conn) {
  let agentActions = '';
  if (conn.connection_type === 'AGENT') {
    agentActions = `
      <a href="#"
         onclick="event.preventDefault(); ChangePolicyModal.open(${conn.pk}, ${conn.policy_id !== null ? conn.policy_id : 'null'}); return false;"
         class="group flex items-center px-4 py-2 text-sm text-gray-300 hover:bg-gray-700 rounded-md" role="menuitem">
        <svg class="w-4 h-4 mr-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
        Change Policy
      </a>
      <a href="#"
         onclick="event.preventDefault(); restartLogstash(${conn.pk}); return false;"
         class="group flex items-center px-4 py-2 text-sm text-gray-300 hover:bg-gray-700 rounded-md" role="menuitem">
        <svg class="w-4 h-4 mr-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        Restart Logstash
      </a>`;
  } else {
    agentActions = `
      <a href="#"
         onclick="event.preventDefault(); openEditConnection(${conn.pk}); return false;"
         class="group flex items-center px-4 py-2 text-sm text-gray-300 hover:bg-gray-700 rounded-md" role="menuitem">
        <svg class="w-4 h-4 mr-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
        </svg>
        Edit
      </a>`;
  }

  return `
    <div class="action-menu relative">
      <button class="action-menu-button p-1 hover:bg-gray-700 rounded">
        <svg class="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
          <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
        </svg>
      </button>
      <div class="action-menu-items hidden fixed z-50 w-44 bg-gray-800 rounded-md shadow-lg py-1" role="menu" style="transform: translate(-50%, 0);">
        <div class="px-1 py-1">
          ${agentActions}
          <a href="#"
             onclick="event.preventDefault(); deleteConnection(${conn.pk}); return false;"
             class="group flex items-center px-4 py-2 text-sm text-red-400 hover:bg-gray-700 rounded-md" role="menuitem">
            <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
            Delete
          </a>
        </div>
      </div>
    </div>`;
}

// ── Pagination controls ───────────────────────────────────────────────────────

function updatePaginationControls(data) {
  const showingStart = data.total > 0 ? (data.page - 1) * data.page_size + 1 : 0;
  const showingEnd = showingStart + data.connections.length - 1;
  document.getElementById('connShowingStart').textContent = showingStart;
  document.getElementById('connShowingEnd').textContent = showingEnd;
  document.getElementById('connTotal').textContent = data.total;
  document.getElementById('connPageInfo').textContent = `Page ${data.page} of ${data.total_pages}`;
  document.getElementById('connPrevBtn').disabled = !data.has_previous;
  document.getElementById('connNextBtn').disabled = !data.has_next;
}

function connNextPage() {
  currentPage++;
  loadConnections();
}

function connPrevPage() {
  if (currentPage > 1) {
    currentPage--;
    loadConnections();
  }
}

// ── Policy filter dropdown population ────────────────────────────────────────

function populatePolicyFilter(policies) {
  const sel = document.getElementById('policyFilter');
  if (!sel) return;

  // Preserve the selected value so it survives the rebuild.
  const current = sel.value;

  // Keep only the first "All Policies" option, replace the rest.
  while (sel.options.length > 1) sel.remove(1);

  // CENTRALIZED pinned first
  const centralizedOpt = document.createElement('option');
  centralizedOpt.value = 'CENTRALIZED';
  centralizedOpt.textContent = 'Elasticsearch (Centralized)';
  sel.appendChild(centralizedOpt);

  if (policies.length > 0) {
    const sep = document.createElement('option');
    sep.disabled = true;
    sep.textContent = '──────────────';
    sel.appendChild(sep);
  }

  policies.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p.id;
    opt.textContent = p.name;
    sel.appendChild(opt);
  });

  // Restore previous selection if it still exists in the rebuilt list.
  if (current) sel.value = current;
}

// ── HTML escaping ─────────────────────────────────────────────────────────────

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function () {
  loadConnections();

  // Search — 500 ms debounce
  let searchTimeout;
  const searchInput = document.getElementById('connSearchInput');
  if (searchInput) {
    searchInput.addEventListener('input', function (e) {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        currentSearch = e.target.value.trim();
        currentPage = 1;
        loadConnections();
      }, 500);
    });
  }

  // Policy filter
  const policyFilter = document.getElementById('policyFilter');
  if (policyFilter) {
    policyFilter.addEventListener('change', function (e) {
      currentPolicy = e.target.value;
      currentPage = 1;
      loadConnections();
    });
  }

  // State filter
  const stateFilter = document.getElementById('stateFilter');
  if (stateFilter) {
    stateFilter.addEventListener('change', function (e) {
      currentState = e.target.value;
      currentPage = 1;
      loadConnections();
    });
  }

  // Page size
  const pageSizeSelect = document.getElementById('connPageSizeSelect');
  if (pageSizeSelect) {
    pageSizeSelect.addEventListener('change', function (e) {
      pageSize = parseInt(e.target.value, 10);
      currentPage = 1;
      loadConnections();
    });
  }
});

// Reload table after add/delete (called from other scripts)
window.reloadConnectionsTable = function () {
  loadConnections();
};
