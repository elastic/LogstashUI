// Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
// or more contributor license agreements. Licensed under the Elastic License;
// you may not use this file except in compliance with the Elastic License.

function openAgentInspect(connectionId, connectionName) {
    const tmpl = document.getElementById('agent-data-' + connectionId);
    if (!tmpl) return;

    const contentEl = document.getElementById('agentInspectContent');
    contentEl.innerHTML = '';
    contentEl.appendChild(tmpl.content.cloneNode(true));

    document.getElementById('agentInspectSubtitle').textContent = connectionName || '';
    document.getElementById('agentInspectFlyout').classList.remove('hidden');
}

function closeAgentInspect() {
    document.getElementById('agentInspectFlyout').classList.add('hidden');
}

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeAgentInspect();
});
