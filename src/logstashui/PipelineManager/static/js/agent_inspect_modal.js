// Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
// or more contributor license agreements. Licensed under the Elastic License;
// you may not use this file except in compliance with the Elastic License.

// ── Loading skeleton shown while the fetch is in flight ──────────────────────
const LOADING_SKELETON = `
  <div class="rounded-xl bg-gray-800 border border-gray-700/60 p-5 animate-pulse">
    <div class="flex items-start justify-between gap-3 mb-4">
      <div class="space-y-2 flex-1">
        <div class="h-5 bg-gray-700 rounded w-2/3"></div>
        <div class="h-3 bg-gray-700/60 rounded w-1/3"></div>
      </div>
      <div class="h-6 w-20 bg-gray-700 rounded-full flex-shrink-0"></div>
    </div>
    <div class="grid grid-cols-3 gap-4 pt-4 border-t border-gray-700/50">
      <div class="space-y-1"><div class="h-2.5 bg-gray-700/60 rounded w-3/4"></div><div class="h-4 bg-gray-700 rounded w-full"></div></div>
      <div class="space-y-1"><div class="h-2.5 bg-gray-700/60 rounded w-3/4"></div><div class="h-4 bg-gray-700 rounded w-full"></div></div>
      <div class="space-y-1"><div class="h-2.5 bg-gray-700/60 rounded w-3/4"></div><div class="h-4 bg-gray-700 rounded w-full"></div></div>
    </div>
  </div>
  <div class="rounded-xl bg-gray-800/50 border border-gray-700/50 p-4 animate-pulse space-y-2">
    <div class="h-2.5 bg-gray-700/60 rounded w-1/4"></div>
    <div class="h-4 bg-gray-700 rounded w-3/4"></div>
    <div class="h-4 bg-gray-700 rounded w-1/2"></div>
  </div>
`;

// ── Public API ────────────────────────────────────────────────────────────────

function openAgentInspect(connectionId, connectionName) {
    const contentEl = document.getElementById('agentInspectContent');

    // Show the flyout immediately with a loading skeleton.
    contentEl.innerHTML = LOADING_SKELETON;
    document.getElementById('agentInspectSubtitle').textContent = connectionName || '';
    document.getElementById('agentInspectFlyout').classList.remove('hidden');

    // Fetch fresh rendered HTML from the server.
    fetch(`/ConnectionManager/AgentInspect/${connectionId}/`, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin',
    })
    .then(function (response) {
        if (!response.ok) {
            throw new Error('Server returned ' + response.status);
        }
        return response.text();
    })
    .then(function (html) {
        // Only update if this flyout is still open for the same agent.
        // (The user may have closed it while the fetch was in flight.)
        if (!document.getElementById('agentInspectFlyout').classList.contains('hidden')) {
            contentEl.innerHTML = html;
            // Initialize collapsible cards after content is injected
            setTimeout(initializeAgentCards, 100);
        }
    })
    .catch(function (err) {
        console.warn('[AgentInspect] fetch failed, falling back to cached template:', err);
        // Graceful fallback: clone the static <template> that was server-rendered
        // at page-load time (may be slightly stale but better than an error state).
        const tmpl = document.getElementById('agent-data-' + connectionId);
        if (tmpl) {
            contentEl.innerHTML = '';
            contentEl.appendChild(tmpl.content.cloneNode(true));
        } else {
            contentEl.innerHTML = '<p class="text-sm text-gray-400 p-4">Unable to load agent data.</p>';
        }
    });
}

function closeAgentInspect() {
    document.getElementById('agentInspectFlyout').classList.add('hidden');
}

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeAgentInspect();
});

// ── Collapsible Card Functionality ──────────────────────────────────────────

function toggleAgentCard(headerElement) {
    const card = headerElement.closest('.agent-inspect-card');
    const content = card.querySelector('.card-content');
    const chevron = card.querySelector('.card-chevron');
    
    if (content.style.maxHeight && content.style.maxHeight !== '0px') {
        // Collapse
        content.style.maxHeight = '0px';
        content.style.opacity = '0';
        chevron.style.transform = 'rotate(-90deg)';
    } else {
        // Expand
        content.style.maxHeight = content.scrollHeight + 'px';
        content.style.opacity = '1';
        chevron.style.transform = 'rotate(0deg)';
    }
}

function initializeAgentCards() {
    // Initialize all cards based on their data-card-green attribute
    const cards = document.querySelectorAll('.agent-inspect-card');
    
    cards.forEach(card => {
        const content = card.querySelector('.card-content');
        const chevron = card.querySelector('.card-chevron');
        const isGreen = card.getAttribute('data-card-green') === 'true';
        
        if (!content || !chevron) return;
        
        // Add transition styles
        content.style.transition = 'max-height 0.3s ease, opacity 0.3s ease';
        content.style.overflow = 'hidden';
        
        if (isGreen) {
            // Green cards start collapsed
            content.style.maxHeight = '0px';
            content.style.opacity = '0';
            chevron.style.transform = 'rotate(-90deg)';
        } else {
            // Non-green cards start expanded
            content.style.maxHeight = content.scrollHeight + 'px';
            content.style.opacity = '1';
            chevron.style.transform = 'rotate(0deg)';
        }
    });
}
