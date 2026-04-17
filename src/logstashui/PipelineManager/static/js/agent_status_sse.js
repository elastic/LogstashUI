// Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
// or more contributor license agreements. Licensed under the Elastic License;
// you may not use this file except in compliance with the Elastic License.

/**
 * Real-time agent status via Server-Sent Events.
 *
 * Connects to /PipelineManager/AgentStatusStream/ and updates the status
 * badge for each agent connection without a full page reload.
 *
 * Two surfaces are kept in sync:
 *   1. The list badge — the pill inside .status-container[data-agent-id]
 *   2. The modal summary badge — [data-modal-badge] inside #agentInspectContent,
 *      only updated when the flyout is currently open for that agent.
 */

const BADGE_SVG = `<svg class="w-3 h-3 opacity-60" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122"/></svg>`;

const STATUS_CONFIG = {
  restarting: {
    listClass:   'pulse-badge pulse-blue inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 cursor-pointer',
    listLabel:   'Restarting',
    modalClass:  'flex-shrink-0 inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-blue-900/40 text-blue-300 border border-blue-700/30',
    modalDot:    'w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse',
    modalLabel:  'Restarting',
  },
  unhealthy: {
    listClass:   'pulse-badge pulse-yellow inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 cursor-pointer',
    listLabel:   'Unhealthy',
    modalClass:  'flex-shrink-0 inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-yellow-900/40 text-yellow-300 border border-yellow-700/30',
    modalDot:    'w-1.5 h-1.5 rounded-full bg-yellow-400 animate-pulse',
    modalLabel:  'Degraded',
  },
  healthy: {
    listClass:   'pulse-badge pulse-green inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 cursor-pointer',
    listLabel:   'Healthy',
    modalClass:  'flex-shrink-0 inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-green-900/40 text-green-300 border border-green-700/30',
    modalDot:    'w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse',
    modalLabel:  'Healthy',
  },
  offline: {
    listClass:   'inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 cursor-pointer',
    listLabel:   'Offline',
    modalClass:  'flex-shrink-0 inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-gray-700/60 text-gray-300 border border-gray-600/30',
    modalDot:    'w-1.5 h-1.5 rounded-full bg-gray-400',
    modalLabel:  'Offline',
  },
};

// Tracks which agent's modal is currently open so we can update it too.
let _openAgentId = null;

function _buildListBadge(cfg, agentId, agentName) {
  const span = document.createElement('span');
  span.className = cfg.listClass;
  // Use setAttribute so the string is safely quoted regardless of name content.
  span.setAttribute('onclick', `openAgentInspect(${JSON.stringify(String(agentId))}, ${JSON.stringify(agentName)})`);
  span.innerHTML = cfg.listLabel + ' ' + BADGE_SVG;
  return span;
}

function _buildModalBadge(cfg) {
  const span = document.createElement('span');
  span.className = cfg.modalClass;
  span.setAttribute('data-modal-badge', '');
  span.innerHTML = `<span class="${cfg.modalDot}"></span>${cfg.modalLabel}`;
  return span;
}

function _applyUpdate(id, name, status) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.offline;

  // 1. Update list badge
  const container = document.querySelector(`.status-container[data-agent-id="${id}"]`);
  if (container) {
    container.innerHTML = '';
    container.appendChild(_buildListBadge(cfg, id, name));
  }

  // 2. Update modal badge if this agent's flyout is open
  if (String(_openAgentId) === String(id)) {
    const existing = document.querySelector('#agentInspectContent [data-modal-badge]');
    if (existing) {
      existing.replaceWith(_buildModalBadge(cfg));
    }
  }
}

// ── SSE connection ────────────────────────────────────────────────────────────

function _connect() {
  const source = new EventSource('/ConnectionManager/AgentStatusStream/');

  source.onmessage = function (event) {
    try {
      const updates = JSON.parse(event.data);
      updates.forEach(({ id, name, status }) => _applyUpdate(id, name, status));
    } catch (e) {
      console.error('[AgentSSE] Failed to parse event data:', e);
    }
  };

  source.onerror = function () {
    // EventSource auto-reconnects, but we close and restart manually so we
    // control the backoff and avoid hammering the server.
    source.close();
    setTimeout(_connect, 10000);
  };
}

// ── Patch modal open/close to track the active agent ─────────────────────────
// agent_inspect_modal.js is loaded before this file, so window.openAgentInspect
// and window.closeAgentInspect are already defined here.

(function () {
  const _origOpen  = window.openAgentInspect;
  const _origClose = window.closeAgentInspect;

  window.openAgentInspect = function (connectionId, connectionName) {
    _openAgentId = connectionId;
    _origOpen(connectionId, connectionName);
  };

  window.closeAgentInspect = function () {
    _openAgentId = null;
    _origClose();
  };
})();

// ── Boot ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', _connect);
