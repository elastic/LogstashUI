/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

(function () {
  'use strict';

  // ── Helpers ───────────────────────────────────────────────────────────────────

  function getCsrf() {
    const el = document.querySelector('[name=csrfmiddlewaretoken]');
    return el ? el.value : '';
  }

  function debounce(fn, ms) {
    let t;
    return function (...args) {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(this, args), ms);
    };
  }

  // Current connection context — kept in closure so the install button can use it
  let _connectionId = null;
  let _kibanaUrl    = null;

  // ── Open / Close ──────────────────────────────────────────────────────────────

  function openAiDeviceTemplateModal(prefillWalkData) {
    const modal = document.getElementById('aiDeviceTemplateModal');
    if (!modal) return;

    if (prefillWalkData) {
      const walkInput = document.getElementById('aiTemplateWalkInput');
      if (walkInput) walkInput.value = prefillWalkData;
    }

    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    _updateGenerateBtnState();
  }

  function closeAiDeviceTemplateModal() {
    const modal = document.getElementById('aiDeviceTemplateModal');
    if (!modal) return;
    modal.classList.add('hidden');
    document.body.style.overflow = '';

    // Reset Kibana URL field
    const kibanaUrlContainer = document.getElementById('aiTemplateKibanaUrlContainer');
    if (kibanaUrlContainer) kibanaUrlContainer.classList.add('hidden');
    const kibanaUrlInput = document.getElementById('aiTemplateKibanaUrl');
    if (kibanaUrlInput) kibanaUrlInput.value = '';

    // Reset resource status
    hideResourceStatus();
    _connectionId = null;
    _kibanaUrl    = null;
  }

  // ── Kibana URL visibility ──────────────────────────────────────────────────────

  function updateKibanaUrlVisibility() {
    const connectionSelect   = document.getElementById('aiTemplateConnectionSelect');
    const kibanaUrlContainer = document.getElementById('aiTemplateKibanaUrlContainer');
    if (!connectionSelect || !kibanaUrlContainer) return;

    const selected    = connectionSelect.options[connectionSelect.selectedIndex];
    const hasCloudId  = selected && selected.dataset.hasCloudId === 'true';

    if (selected && selected.value && !hasCloudId) {
      kibanaUrlContainer.classList.remove('hidden');
    } else {
      kibanaUrlContainer.classList.add('hidden');
      const kibanaUrlInput = document.getElementById('aiTemplateKibanaUrl');
      if (kibanaUrlInput) kibanaUrlInput.value = '';
    }
  }

  // ── Resource status panel ─────────────────────────────────────────────────────

  function hideResourceStatus() {
    const panel = document.getElementById('aiTemplateResourceStatus');
    if (panel) panel.classList.add('hidden');

    const list = document.getElementById('aiTemplateResourceList');
    if (list) list.innerHTML = '';

    const unavailable = document.getElementById('aiTemplateApiUnavailable');
    if (unavailable) unavailable.classList.add('hidden');

    setInstallBtnVisible(false);
    setGenerateBtnBlocked(false);
  }

  function setLoading(visible) {
    const spinner = document.getElementById('aiTemplateResourceLoading');
    if (spinner) spinner.classList.toggle('hidden', !visible);

    const panel = document.getElementById('aiTemplateResourceStatus');
    if (panel) panel.classList.remove('hidden');
  }

  // Track whether any resource is missing — updated by renderResourceStatus
  let _hasMissingResources = false;

  function setGenerateBtnBlocked(blocked) {
    _hasMissingResources = blocked;
    _updateGenerateBtnState();
  }

  function _updateGenerateBtnState() {
    const btn      = document.getElementById('aiTemplateGenerateBtn');
    const walkInput = document.getElementById('aiTemplateWalkInput');
    if (!btn) return;

    const walkEmpty = !walkInput || !walkInput.value.trim();
    const blocked   = _hasMissingResources || walkEmpty;

    btn.disabled = blocked;
    if (blocked) {
      btn.classList.add('opacity-50', 'cursor-not-allowed');
      if (_hasMissingResources) {
        btn.title = 'Install all required Elastic Agent Builder resources before generating';
      } else {
        btn.title = 'Paste your SNMP walk output before generating';
      }
    } else {
      btn.classList.remove('opacity-50', 'cursor-not-allowed');
      btn.title = '';
    }
  }

  function setInstallBtnVisible(visible, hasUpdate) {
    const btn   = document.getElementById('aiTemplateInstallBtn');
    const label = document.getElementById('aiTemplateInstallBtnLabel');
    if (!btn) return;

    if (visible) {
      btn.classList.remove('hidden');
      if (label) label.textContent = hasUpdate ? 'Update Package' : 'Install Package';
    } else {
      btn.classList.add('hidden');
    }
  }

  function statusBadge(status) {
    const cfg = {
      matches: { dot: 'bg-green-400',  text: 'text-green-300',  label: 'Up to date'    },
      missing: { dot: 'bg-red-400',    text: 'text-red-300',    label: 'Not installed' },
      differs: { dot: 'bg-yellow-400', text: 'text-yellow-300', label: 'Needs update'  },
      error:   { dot: 'bg-gray-500',   text: 'text-gray-400',   label: 'Check failed'  },
    };
    const c = cfg[status] || cfg.error;
    return `<span class="flex items-center gap-1.5">
              <span class="w-2 h-2 rounded-full ${c.dot} flex-shrink-0"></span>
              <span class="text-xs ${c.text} font-medium">${c.label}</span>
            </span>`;
  }

  function renderResourceStatus(results) {
    const list            = document.getElementById('aiTemplateResourceList');
    const unavailable     = document.getElementById('aiTemplateApiUnavailable');
    const unavailableMsg  = document.getElementById('aiTemplateApiUnavailableMsg');

    if (!list) return;
    list.innerHTML = '';

    if (!results.api_available) {
      if (unavailable) unavailable.classList.remove('hidden');
      if (unavailableMsg) unavailableMsg.textContent =
        results.error || 'Elastic Agent Builder API is not available (requires Kibana ≥ 9.2).';
      setInstallBtnVisible(false);
      setGenerateBtnBlocked(false); // Don't permanently block if we can't check
      return;
    }

    if (unavailable) unavailable.classList.add('hidden');

    const allResources = [
      ...( results.tools  || [] ).map(r => ({ ...r, type: 'tool'  })),
      ...( results.skills || [] ).map(r => ({ ...r, type: 'skill' })),
      ...( results.agents || [] ).map(r => ({ ...r, type: 'agent' })),
    ];

    if (allResources.length === 0) {
      list.innerHTML = '<p class="px-4 py-3 text-xs text-gray-500 italic">No resources defined yet.</p>';
      setInstallBtnVisible(false);
      return;
    }

    let hasMissing = false;
    let hasDiffers = false;

    allResources.forEach(resource => {
      if (resource.status === 'missing') hasMissing = true;
      if (resource.status === 'differs') hasDiffers = true;

      const typeLabel  = resource.type.charAt(0).toUpperCase() + resource.type.slice(1);
      const diffHint   = resource.differences && resource.differences.length
        ? `<span class="text-xs text-gray-500 ml-1">(${resource.differences.join(', ')})</span>`
        : '';

      const row = document.createElement('div');
      row.className = 'flex items-center justify-between px-4 py-2.5 gap-4';
      row.innerHTML = `
        <div class="flex items-center gap-2 min-w-0">
          <span class="text-xs text-gray-500 uppercase tracking-wide w-10 flex-shrink-0">${typeLabel}</span>
          <span class="text-sm text-white truncate">${resource.display_name}</span>
          ${diffHint}
        </div>
        <div class="flex-shrink-0">
          ${statusBadge(resource.status)}
        </div>
      `;
      list.appendChild(row);
    });

    // Show the single package button only when action is needed
    const needsAction = hasMissing || hasDiffers;
    setInstallBtnVisible(needsAction, !hasMissing && hasDiffers);

    // Block the Generate button when any resource is missing
    setGenerateBtnBlocked(hasMissing);
  }

  // ── Check resources API call ───────────────────────────────────────────────────

  function checkAgentBuilderResources(connectionId, kibanaUrl) {
    if (!connectionId) return;

    _connectionId = connectionId;
    _kibanaUrl    = kibanaUrl || null;

    setLoading(true);
    setInstallBtnVisible(false);

    const body = { connection_id: connectionId };
    if (kibanaUrl) body.kibana_url = kibanaUrl;

    fetch('/SNMP/CheckAgentBuilderResources/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      body: JSON.stringify(body),
    })
      .then(r => r.json())
      .then(results => {
        setLoading(false);
        renderResourceStatus(results);
      })
      .catch(err => {
        setLoading(false);
        renderResourceStatus({
          api_available: false,
          error: `Request failed: ${err.message}`,
          tools: [], skills: [], agents: [],
        });
      });
  }

  // ── Install / update entire package ───────────────────────────────────────────

  function installAgentBuilderPackage() {
    if (!_connectionId) return;

    const btn   = document.getElementById('aiTemplateInstallBtn');
    const label = document.getElementById('aiTemplateInstallBtnLabel');

    if (btn) btn.disabled = true;
    if (label) label.textContent = 'Installing…';
    setLoading(true);

    const body = { connection_id: _connectionId };
    if (_kibanaUrl) body.kibana_url = _kibanaUrl;

    fetch('/SNMP/InstallAgentBuilderPackage/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      body: JSON.stringify(body),
    })
      .then(r => r.json())
      .then(result => {
        if (btn) btn.disabled = false;
        if (!result.success) {
          const firstError = (result.results || []).find(r => !r.success);
          showToast(firstError ? firstError.error : 'Install failed', 'error');
        }
        // Re-check so status rows refresh
        checkAgentBuilderResources(_connectionId, _kibanaUrl);
      })
      .catch(err => {
        if (btn) btn.disabled = false;
        setLoading(false);
        showToast(`Install failed: ${err.message}`, 'error');
      });
  }

  // ── Wire up events on DOMContentLoaded ────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', function () {

    // Open button
    const openBtn = document.getElementById('generateTemplateBtn');
    if (openBtn) openBtn.addEventListener('click', () => openAiDeviceTemplateModal());

    // Close button & backdrop
    const closeBtn = document.getElementById('closeAiDeviceTemplateModal');
    if (closeBtn) closeBtn.addEventListener('click', closeAiDeviceTemplateModal);

    const backdrop = document.getElementById('aiDeviceTemplateBackdrop');
    if (backdrop) backdrop.addEventListener('click', closeAiDeviceTemplateModal);

    // Connection select → show/hide Kibana URL + trigger check
    const connectionSelect = document.getElementById('aiTemplateConnectionSelect');
    if (connectionSelect) {
      connectionSelect.addEventListener('change', function () {
        updateKibanaUrlVisibility();
        hideResourceStatus();

        const selected   = this.options[this.selectedIndex];
        const hasCloudId = selected && selected.dataset.hasCloudId === 'true';

        if (selected && selected.value && hasCloudId) {
          checkAgentBuilderResources(parseInt(selected.value, 10), null);
        }
      });
    }

    // Kibana URL input → debounced check
    const kibanaUrlInput = document.getElementById('aiTemplateKibanaUrl');
    if (kibanaUrlInput) {
      const debouncedCheck = debounce(function () {
        const sel          = document.getElementById('aiTemplateConnectionSelect');
        const connectionId = sel && sel.value ? parseInt(sel.value, 10) : null;
        const kibanaUrl    = kibanaUrlInput.value.trim();
        if (connectionId && kibanaUrl) {
          checkAgentBuilderResources(connectionId, kibanaUrl);
        }
      }, 600);

      kibanaUrlInput.addEventListener('input', debouncedCheck);
    }

    // Single install / update package button
    const installBtn = document.getElementById('aiTemplateInstallBtn');
    if (installBtn) installBtn.addEventListener('click', installAgentBuilderPackage);

    // Walk input → re-evaluate generate button on every keystroke
    const walkInput = document.getElementById('aiTemplateWalkInput');
    if (walkInput) {
      walkInput.addEventListener('input', _updateGenerateBtnState);
    }

    // Generate button — not wired yet
    const generateBtn = document.getElementById('aiTemplateGenerateBtn');
    if (generateBtn) {
      generateBtn.addEventListener('click', function () {
        // TODO: wire up generation logic
      });
    }
  });

  // ── Global exports ─────────────────────────────────────────────────────────────

  window.openAiDeviceTemplateModal  = openAiDeviceTemplateModal;
  window.closeAiDeviceTemplateModal = closeAiDeviceTemplateModal;

})();
