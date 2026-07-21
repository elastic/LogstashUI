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

  // ── Step icon SVG snippets ────────────────────────────────────────────────────

  const ICON = {
    spinner: `<svg class="animate-spin w-3.5 h-3.5" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
              </svg>`,
    check:   `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
              </svg>`,
    xmark:   `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"/>
              </svg>`,
    link:    `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/>
              </svg>`,
    bulb:    `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
              </svg>`,
    chat:    `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/>
              </svg>`,
    tool:    `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
              </svg>`,
  };

  // ── Inference model helpers ───────────────────────────────────────────────────

  function _isSonnet46(name) {
    const lower = (name || '').toLowerCase();
    return lower.includes('claude') && lower.includes('sonnet') && lower.includes('4.6');
  }

  function _isSonnet(name) {
    const lower = (name || '').toLowerCase();
    return lower.includes('claude') && lower.includes('sonnet');
  }

  function showModelSelector(visible) {
    const container = document.getElementById('aiTemplateModelContainer');
    if (container) container.classList.toggle('hidden', !visible);
  }

  function setModelLoading(loading) {
    const spinner = document.getElementById('aiTemplateModelLoading');
    if (spinner) spinner.classList.toggle('hidden', !loading);
  }

  function fetchAndPopulateModels(connectionId) {
    const select   = document.getElementById('aiTemplateModelSelect');
    const errorEl  = document.getElementById('aiTemplateModelError');
    if (!select) return;

    showModelSelector(true);
    setModelLoading(true);
    if (errorEl) errorEl.classList.add('hidden');

    select.innerHTML = '<option value="" disabled selected>Loading models…</option>';

    fetch(`/AI/IntegrationFactory/models/?connection_id=${connectionId}`)
      .then(r => r.json())
      .then(data => {
        setModelLoading(false);
        const models = data.models || [];

        if (!models.length) {
          select.innerHTML = '<option value="" disabled selected>No models available</option>';
          if (errorEl) errorEl.classList.remove('hidden');
          return;
        }

        select.innerHTML = '';
        let sonnet46Option = null;
        let sonnetFallback = null;

        models.forEach(model => {
          const opt       = document.createElement('option');
          opt.value       = model.inference_id;
          opt.textContent = model.name || model.inference_id;
          select.appendChild(opt);
          if (!sonnet46Option && _isSonnet46(model.name)) {
            sonnet46Option = opt;
          } else if (!sonnetFallback && _isSonnet(model.name)) {
            sonnetFallback = opt;
          }
        });

        // Prefer Claude Sonnet 4.6 → any Sonnet → first model
        const defaultOption = sonnet46Option || sonnetFallback || select.options[0];
        if (defaultOption) defaultOption.selected = true;

        _updateGenerateBtnState();
      })
      .catch(() => {
        setModelLoading(false);
        select.innerHTML = '<option value="" disabled selected>Failed to load models</option>';
        if (errorEl) errorEl.classList.remove('hidden');
      });
  }

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

    // If a connection is already selected (modal re-opened), restore state.
    const connectionSelect = document.getElementById('aiTemplateConnectionSelect');
    if (connectionSelect && connectionSelect.value) {
      updateKibanaUrlVisibility();
      const selected   = connectionSelect.options[connectionSelect.selectedIndex];
      const hasCloudId = selected && selected.dataset.hasCloudId === 'true';
      const connId     = parseInt(connectionSelect.value, 10);

      fetchAndPopulateModels(connId);

      if (hasCloudId) {
        checkAgentBuilderResources(connId, null);
      }
    }
  }

  function closeAiDeviceTemplateModal() {
    const modal = document.getElementById('aiDeviceTemplateModal');
    if (!modal) return;
    modal.classList.add('hidden');
    document.body.style.overflow = '';

    const kibanaUrlContainer = document.getElementById('aiTemplateKibanaUrlContainer');
    if (kibanaUrlContainer) kibanaUrlContainer.classList.add('hidden');
    const kibanaUrlInput = document.getElementById('aiTemplateKibanaUrl');
    if (kibanaUrlInput) kibanaUrlInput.value = '';

    if (_activeReader) {
      _activeReader.cancel();
      _activeReader = null;
    }

    const genPanel = document.getElementById('aiTemplateGenerationPanel');
    if (genPanel) genPanel.classList.add('hidden');

    showModelSelector(false);
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

  let _hasMissingResources = false;

  function setGenerateBtnBlocked(blocked) {
    _hasMissingResources = blocked;
    _updateGenerateBtnState();
  }

  function _updateGenerateBtnState() {
    const btn         = document.getElementById('aiTemplateGenerateBtn');
    const walkInput   = document.getElementById('aiTemplateWalkInput');
    const modelSelect = document.getElementById('aiTemplateModelSelect');
    if (!btn) return;

    const walkEmpty  = !walkInput  || !walkInput.value.trim();
    const noModel    = !modelSelect || !modelSelect.value;
    const blocked    = _hasMissingResources || walkEmpty || noModel;

    btn.disabled = blocked;
    if (blocked) {
      btn.classList.add('opacity-50', 'cursor-not-allowed');
      if (_hasMissingResources) {
        btn.title = 'Install all required Elastic Agent Builder resources before generating';
      } else if (noModel) {
        btn.title = 'Select an inference model before generating';
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
      setGenerateBtnBlocked(false);
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

    const needsAction = hasMissing || hasDiffers;
    setInstallBtnVisible(needsAction, !hasMissing && hasDiffers);
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
      .then(r => {
        if (r.status === 403) throw new Error('Access denied: Admin role required');
        return r.json();
      })
      .then(result => {
        if (btn) btn.disabled = false;
        if (!result.success) {
          const firstError = (result.results || []).find(r => !r.success);
          showToast(firstError ? firstError.error : 'Install failed', 'error');
        }
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

    const openBtn = document.getElementById('generateTemplateBtn');
    if (openBtn) openBtn.addEventListener('click', () => openAiDeviceTemplateModal());

    const closeBtn = document.getElementById('closeAiDeviceTemplateModal');
    if (closeBtn) closeBtn.addEventListener('click', closeAiDeviceTemplateModal);

    const backdrop = document.getElementById('aiDeviceTemplateBackdrop');
    if (backdrop) backdrop.addEventListener('click', closeAiDeviceTemplateModal);

    const connectionSelect = document.getElementById('aiTemplateConnectionSelect');
    if (connectionSelect) {
      connectionSelect.addEventListener('change', function () {
        updateKibanaUrlVisibility();
        hideResourceStatus();
        showModelSelector(false);

        const selected   = this.options[this.selectedIndex];
        const hasCloudId = selected && selected.dataset.hasCloudId === 'true';

        if (selected && selected.value) {
          fetchAndPopulateModels(parseInt(selected.value, 10));
          if (hasCloudId) {
            checkAgentBuilderResources(parseInt(selected.value, 10), null);
          }
        }
      });
    }

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

    const installBtn = document.getElementById('aiTemplateInstallBtn');
    if (installBtn) installBtn.addEventListener('click', installAgentBuilderPackage);

    const walkInput = document.getElementById('aiTemplateWalkInput');
    if (walkInput) {
      walkInput.addEventListener('input', _updateGenerateBtnState);
    }

    const generateBtn = document.getElementById('aiTemplateGenerateBtn');
    if (generateBtn) {
      generateBtn.addEventListener('click', startGeneration);
    }
  });

  // ── Generation pipeline ───────────────────────────────────────────────────────

  let _activeReader = null;

  // ── JSON extraction ───────────────────────────────────────────────────────────
  // Tries to pull a valid JSON object from raw agent text, tolerating markdown fences.

  function _extractJSON(text) {
    if (!text) return null;
    // Direct parse first
    try { return JSON.parse(text.trim()); } catch (_) {}
    // Try stripping a ```json ... ``` or ``` ... ``` fence
    const fenced = text.match(/```(?:json)?\s*([\s\S]+?)```/);
    if (fenced) {
      try { return JSON.parse(fenced[1].trim()); } catch (_) {}
    }
    // Try extracting the outermost {...} block
    const braceStart = text.indexOf('{');
    const braceEnd   = text.lastIndexOf('}');
    if (braceStart !== -1 && braceEnd > braceStart) {
      try { return JSON.parse(text.slice(braceStart, braceEnd + 1)); } catch (_) {}
    }
    return null;
  }

  // ── Import definitions ────────────────────────────────────────────────────────

  function _buildImportResultPanel(result) {
    const success  = result.success;
    const errors   = result.errors   || [];
    const profiles = result.profiles || [];
    const template = result.template || {};

    const ACTION_CFG = {
      created: { bg: 'bg-green-900/30',  border: 'border-green-500/40',  text: 'text-green-300',  dot: 'bg-green-400',  label: 'Created' },
      updated: { bg: 'bg-yellow-900/30', border: 'border-yellow-500/40', text: 'text-yellow-300', dot: 'bg-yellow-400', label: 'Updated' },
      skipped: { bg: 'bg-gray-800/50',   border: 'border-gray-600/40',   text: 'text-gray-400',   dot: 'bg-gray-500',   label: 'Skipped' },
      error:   { bg: 'bg-red-900/30',    border: 'border-red-500/40',    text: 'text-red-300',    dot: 'bg-red-400',    label: 'Error'   },
    };

    function _chip(name, action, reason) {
      const c = ACTION_CFG[action] || ACTION_CFG.error;
      return `<div class="flex items-center gap-2 px-3 py-2 rounded-lg border ${c.bg} ${c.border}">
        <span class="w-1.5 h-1.5 rounded-full ${c.dot} flex-shrink-0"></span>
        <span class="text-xs font-mono ${c.text} font-medium truncate min-w-0">${escapeHtml(name)}</span>
        <span class="text-xs ${c.text} opacity-75 ml-auto flex-shrink-0">${c.label}</span>
        ${reason ? `<span class="text-xs text-gray-500 flex-shrink-0">— ${escapeHtml(reason)}</span>` : ''}
      </div>`;
    }

    let profilesHtml = '';
    if (profiles.length > 0) {
      profilesHtml = `
        <div class="flex flex-col gap-1.5">
          <span class="text-xs text-gray-500 uppercase tracking-wide font-medium">Profiles</span>
          <div class="flex flex-col gap-1.5">${profiles.map(p => _chip(formatDisplayName(p.name), p.action, p.reason)).join('')}</div>
        </div>`;
    }

    let templateHtml = '';
    if (template.name) {
      templateHtml = `
        <div class="flex flex-col gap-1.5">
          <span class="text-xs text-gray-500 uppercase tracking-wide font-medium">Device Template</span>
          ${_chip(formatDisplayName(template.name), template.action, template.reason)}
        </div>`;
    }

    let errorsHtml = '';
    if (errors.length > 0) {
      const items = errors.map(e => `<li class="text-xs text-red-300 leading-relaxed">${escapeHtml(e)}</li>`).join('');
      errorsHtml = `
        <div class="bg-red-900/20 border border-red-500/30 rounded-lg p-3 flex flex-col gap-1.5">
          <span class="text-xs font-semibold text-red-300 uppercase tracking-wide">Warnings / Errors</span>
          <ul class="list-disc list-inside flex flex-col gap-0.5">${items}</ul>
        </div>`;
    }

    let deployHtml = '';
    if (success) {
      const tplName = template.name ? escapeHtml(formatDisplayName(template.name)) : 'the new template';
      deployHtml = `
        <div class="bg-green-900/20 border border-green-500/30 rounded-lg p-3 flex items-center justify-between gap-3">
          <div class="flex items-center gap-2 min-w-0">
            <svg class="w-4 h-4 text-green-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
            </svg>
            <span class="text-sm text-green-300">Import complete! You can now add <strong class="text-white">${tplName}</strong> to your devices.</span>
          </div>
          <a
            href="/SNMP/Devices/"
            class="btn btn-sm border border-green-400 text-green-300 hover:bg-green-400/10 flex-shrink-0 flex items-center gap-1.5">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18"/>
            </svg>
            Devices
          </a>
        </div>`;
    }

    const headerIcon = success
      ? `<svg class="w-4 h-4 text-green-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`
      : `<svg class="w-4 h-4 text-red-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`;

    const panel = document.createElement('div');
    panel.id = 'aiTemplateImportResult';
    panel.className = 'mt-4 flex flex-col gap-3 bg-gray-900/50 border border-gray-700 rounded-lg p-4';
    panel.innerHTML = `
      <div class="flex items-center gap-2 pb-2 border-b border-gray-700">
        ${headerIcon}
        <span class="text-sm font-semibold text-white">Import Results</span>
      </div>
      ${profilesHtml}
      ${templateHtml}
      ${errorsHtml}
      ${deployHtml}
    `;
    return panel;
  }

  function _importDefinitions(parsed) {
    const importBtn = document.getElementById('aiTemplateImportBtn');
    const actionRow = importBtn ? importBtn.closest('div') : null;

    // Remove any previous result panel
    const prev = document.getElementById('aiTemplateImportResult');
    if (prev) prev.remove();

    // Loading state on the button
    if (importBtn) {
      importBtn.disabled = true;
      importBtn.classList.add('opacity-50', 'cursor-not-allowed');
      importBtn.innerHTML = `<svg class="animate-spin w-3.5 h-3.5" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg> Importing…`;
    }

    fetch('/SNMP/ImportAIGeneratedDefinitions/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      body: JSON.stringify({
        profiles:        parsed.profiles        || [],
        device_template: parsed.device_template || {},
      }),
    })
      .then(r => {
        if (r.status === 403) throw new Error('Access denied: Admin role required');
        return r.json();
      })
      .then(result => {
        // Restore button
        if (importBtn) {
          importBtn.disabled = false;
          importBtn.classList.remove('opacity-50', 'cursor-not-allowed');
          importBtn.innerHTML = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/></svg> Import Profiles &amp; Template`;
        }

        const panel = _buildImportResultPanel(result);

        // Insert the result panel immediately after the action row
        if (actionRow && actionRow.parentNode) {
          actionRow.parentNode.insertBefore(panel, actionRow.nextSibling);
        } else {
          const structured = document.getElementById('aiTemplateStructuredResponse');
          if (structured) structured.appendChild(panel);
        }

        panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

        // Notify the Device Wizard (if open) so it can auto-select the template
        if (result.success && result.template && result.template.id) {
          if (typeof window.onAITemplateImported === 'function') {
            window.onAITemplateImported({ id: result.template.id, name: result.template.name });
          }
        }

      })
      .catch(err => {
        if (importBtn) {
          importBtn.disabled = false;
          importBtn.classList.remove('opacity-50', 'cursor-not-allowed');
          importBtn.innerHTML = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/></svg> Import Profiles &amp; Template`;
        }
        showToast(`Import failed: ${err.message}`, 'error');
      });
  }

  // ── Structured response renderer ─────────────────────────────────────────────

  function _oidCount(obj) {
    if (!obj || typeof obj !== 'object') return 0;
    return Object.keys(obj).length;
  }

  function _renderProfileCard(profile) {
    const getCount   = _oidCount(profile.get);
    const walkCount  = _oidCount(profile.walk);
    const tableCount = _oidCount(profile.table);
    const normCount  = Array.isArray(profile.normalizers) ? profile.normalizers.length : 0;

    const oidParts = [
      getCount   && `<span class="text-white font-medium">${getCount}</span> get`,
      walkCount  && `<span class="text-white font-medium">${walkCount}</span> walk`,
      tableCount && `<span class="text-white font-medium">${tableCount}</span> ${tableCount === 1 ? 'table' : 'tables'}`,
      normCount  && `<span class="text-white font-medium">${normCount}</span> ${normCount === 1 ? 'normalizer' : 'normalizers'}`,
    ].filter(Boolean).join('<span class="text-gray-600 mx-1">·</span>');

    const jsonId  = `profile-json-${Math.random().toString(36).slice(2)}`;
    const jsonStr = JSON.stringify(profile, null, 2);

    const card = document.createElement('div');
    card.className = 'bg-gray-900/60 border border-gray-700 rounded-lg overflow-hidden flex flex-col';
    card.innerHTML = `
      <div class="p-3 flex flex-col gap-1.5 flex-1">
        <span class="text-xs font-semibold text-white font-mono truncate" title="${escapeHtml(profile.name || '')}">${escapeHtml(formatDisplayName(profile.name))}</span>
        ${profile.description ? `<span class="text-xs text-gray-400 leading-snug line-clamp-2">${escapeHtml(profile.description)}</span>` : ''}
        ${oidParts ? `<div class="flex items-center gap-0.5 text-xs text-gray-400 flex-wrap mt-0.5">${oidParts}</div>` : ''}
        <button
          type="button"
          onclick="(function(btn){var el=document.getElementById('${jsonId}');if(!el)return;var open=el.classList.toggle('hidden');btn.textContent=open?'View JSON \u25b8':'Hide JSON \u25be';})(this)"
          class="text-xs text-purple-400 hover:text-purple-300 text-left w-fit mt-auto pt-1">
          View JSON &#9658;
        </button>
      </div>
      <div id="${jsonId}" class="hidden border-t border-gray-700">
        <pre class="p-3 text-xs text-gray-300 font-mono overflow-x-auto max-h-56 overflow-y-auto bg-gray-950/60 whitespace-pre">${escapeHtml(jsonStr)}</pre>
      </div>
    `;
    return card;
  }

  function _renderTemplateCard(template, newProfileNames) {
    const matchingRules = Array.isArray(template.matching_rules) ? template.matching_rules : [];
    const profiles      = Array.isArray(template.profiles)       ? template.profiles       : [];
    const knownNewNames = newProfileNames instanceof Set ? newProfileNames : new Set();

    const matchingHtml = matchingRules.length
      ? matchingRules.map(r => `<span class="px-1.5 py-0.5 rounded bg-gray-700 text-xs text-gray-300 font-mono">${escapeHtml(r)}</span>`).join(' ')
      : '<span class="text-xs text-gray-500 italic">none</span>';

    const starSvg = `<svg class="w-3 h-3 text-yellow-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
      </svg>`;
    // A profile referenced by the template that isn't one of the newly-authored
    // profiles in this response is being reused from the existing catalog.
    const profilesHtml = profiles.length
      ? profiles.map(p => {
          const isExisting = !knownNewNames.has(p);
          return `<span class="px-1.5 py-0.5 rounded bg-purple-900/40 border border-purple-500/20 text-xs text-purple-300 font-mono inline-flex items-center gap-1" ${isExisting ? 'title="Reusing an existing profile from the catalog"' : ''}>${isExisting ? starSvg : ''}${escapeHtml(formatDisplayName(p))}</span>`;
        }).join(' ')
      : '<span class="text-xs text-gray-500 italic">none</span>';

    const meta = [template.vendor, template.product, template.model].filter(Boolean).join(' · ');

    const card = document.getElementById('aiTemplateTemplateCard');
    if (!card) return;

    card.innerHTML = `
      <div class="flex flex-col gap-3">
        <div>
          <div class="text-base font-semibold text-white font-mono">${escapeHtml(formatDisplayName(template.name))}</div>
          ${meta ? `<div class="text-xs text-gray-400 mt-0.5">${escapeHtml(meta)}</div>` : ''}
          ${template.description ? `<div class="text-xs text-gray-300 mt-1 leading-relaxed">${escapeHtml(template.description)}</div>` : ''}
        </div>
        <div class="flex flex-col gap-1.5">
          <span class="text-xs text-gray-500 uppercase tracking-wide">Matching Rules</span>
          <div class="flex flex-wrap gap-1.5">${matchingHtml}</div>
        </div>
        <div class="flex flex-col gap-1.5">
          <span class="text-xs text-gray-500 uppercase tracking-wide">Profiles (${profiles.length})</span>
          <div class="flex flex-wrap gap-1.5">${profilesHtml}</div>
        </div>
      </div>
    `;
  }

  function _renderStructuredResponse(parsed, rawJson) {
    const structuredEl = document.getElementById('aiTemplateStructuredResponse');
    if (!structuredEl) return;

    // Explanation
    const explanationText = document.getElementById('aiTemplateExplanationText');
    if (explanationText) {
      explanationText.textContent = parsed.explanation || '';
    }

    // Profiles
    const profilesSection  = document.getElementById('aiTemplateProfilesSection');
    const profilesHeader   = document.getElementById('aiTemplateProfilesHeader');
    const profilesAccordion = document.getElementById('aiTemplateProfilesAccordion');
    const profiles = Array.isArray(parsed.profiles) ? parsed.profiles : [];

    if (profilesSection && profilesAccordion) {
      if (profiles.length > 0) {
        profilesSection.classList.remove('hidden');
        if (profilesHeader) profilesHeader.textContent = `New Profiles (${profiles.length})`;
        profilesAccordion.innerHTML = '';
        profiles.forEach(p => profilesAccordion.appendChild(_renderProfileCard(p)));
      } else {
        profilesSection.classList.remove('hidden');
        profilesAccordion.innerHTML = '<p class="text-xs text-gray-500 italic px-1">No new profiles needed — all required profiles already exist in the catalog.</p>';
      }
    }

    // Device Template
    const templateSection = document.getElementById('aiTemplateTemplateSection');
    if (parsed.device_template && templateSection) {
      templateSection.classList.remove('hidden');
      const newProfileNames = new Set(profiles.map(p => p.name));
      _renderTemplateCard(parsed.device_template, newProfileNames);
    }

    // Show the structured panel
    structuredEl.classList.remove('hidden');

    // Wire up Copy JSON button
    const copyJsonBtn = document.getElementById('aiTemplateCopyJsonBtn');
    if (copyJsonBtn) {
      copyJsonBtn.onclick = function () {
        navigator.clipboard.writeText(rawJson || JSON.stringify(parsed, null, 2)).then(() => {
          const orig = copyJsonBtn.textContent.trim();
          copyJsonBtn.textContent = 'Copied!';
          setTimeout(() => {
            copyJsonBtn.innerHTML = `<svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg> Copy JSON`;
          }, 2000);
        });
      };
    }

    // Wire up the Import button with the current parsed response
    const importBtn = document.getElementById('aiTemplateImportBtn');
    if (importBtn) {
      importBtn.onclick = function () {
        _importDefinitions(parsed);
      };
    }
  }

  // ── Generation start ──────────────────────────────────────────────────────────

  function startGeneration() {
    const connectionSelect = document.getElementById('aiTemplateConnectionSelect');
    const walkInput        = document.getElementById('aiTemplateWalkInput');
    const kibanaUrlInput   = document.getElementById('aiTemplateKibanaUrl');
    const modelSelect      = document.getElementById('aiTemplateModelSelect');

    if (!connectionSelect || !connectionSelect.value || !walkInput || !walkInput.value.trim()) return;

    const connectionId = parseInt(connectionSelect.value, 10);
    const walkText     = walkInput.value;
    const kibanaUrl    = (kibanaUrlInput && kibanaUrlInput.value.trim()) || null;
    const inferenceId  = (modelSelect && modelSelect.value) || null;

    // Reset and show the generation panel
    const panel = document.getElementById('aiTemplateGenerationPanel');
    if (panel) panel.classList.remove('hidden');

    const stepsEl      = document.getElementById('aiTemplateProgressSteps');
    const responseEl   = document.getElementById('aiTemplateResponseContainer');
    const outputEl     = document.getElementById('aiTemplateResponseOutput');
    const structuredEl = document.getElementById('aiTemplateStructuredResponse');

    if (stepsEl)      stepsEl.innerHTML = '';
    if (outputEl)     outputEl.textContent = '';
    if (responseEl)   responseEl.classList.add('hidden');
    if (structuredEl) structuredEl.classList.add('hidden');

    // Clear import result panel from a previous run
    const prevImportResult = document.getElementById('aiTemplateImportResult');
    if (prevImportResult) prevImportResult.remove();

    // Clear structured sub-sections so they don't bleed between runs
    const profilesSection  = document.getElementById('aiTemplateProfilesSection');
    const templateSection  = document.getElementById('aiTemplateTemplateSection');
    const profilesAccordion = document.getElementById('aiTemplateProfilesAccordion');
    const templateCard     = document.getElementById('aiTemplateTemplateCard');
    if (profilesSection)   profilesSection.classList.add('hidden');
    if (templateSection)   templateSection.classList.add('hidden');
    if (profilesAccordion) profilesAccordion.innerHTML = '';
    if (templateCard)      templateCard.innerHTML = '';

    const generateBtn = document.getElementById('aiTemplateGenerateBtn');
    if (generateBtn) {
      generateBtn.disabled = true;
      generateBtn.classList.add('opacity-50', 'cursor-not-allowed');
    }

    // ── Step helpers ──────────────────────────────────────────────────────────

    function _stepRow(icon, message, colorClass) {
      const row = document.createElement('div');
      row.className = `flex items-start gap-2.5 text-xs ${colorClass}`;
      row.innerHTML = `<span class="step-icon flex-shrink-0 mt-0.5">${icon}</span><span class="step-text leading-relaxed">${escapeHtml(message)}</span>`;
      if (stepsEl) {
        stepsEl.appendChild(row);
        stepsEl.scrollTop = stepsEl.scrollHeight;
      }
      return row;
    }

    function _createStep(message) {
      return _stepRow(ICON.spinner, message, 'text-gray-400');
    }

    function _resolveStep(step, success, appendMsg) {
      if (!step) return;
      const iconEl = step.querySelector('.step-icon');
      const textEl = step.querySelector('.step-text');
      if (success) {
        step.className = 'flex items-start gap-2.5 text-xs text-green-400';
        if (iconEl) iconEl.innerHTML = ICON.check;
      } else {
        step.className = 'flex items-start gap-2.5 text-xs text-red-400';
        if (iconEl) iconEl.innerHTML = ICON.xmark;
        if (appendMsg && textEl) textEl.textContent += `: ${appendMsg}`;
      }
    }

    // ── Chunk handler ─────────────────────────────────────────────────────────

    let accumulatedResponse = '';
    let _pendingStep        = null;
    let _streamingStep      = null; // "Receiving response..." indicator

    function handleChunk(event) {
      switch (event.phase) {

        case 'grounding':
          _pendingStep = _createStep(event.message);
          break;

        case 'grounding_done':
          _resolveStep(_pendingStep, true);
          _pendingStep = null;
          break;

        case 'invoking':
          _pendingStep = _createStep(event.message);
          break;

        case 'conversation_link': {
          _resolveStep(_pendingStep, true);
          _pendingStep = _createStep('Agent is preparing response…');
          break;
        }

        case 'conversation_title': {
          if (stepsEl && event.title) {
            const titleRow = document.createElement('div');
            titleRow.className = 'flex items-center gap-2.5 text-xs text-gray-500';
            titleRow.innerHTML = `<span class="flex-shrink-0">${ICON.chat}</span><span class="italic">${escapeHtml(event.title)}</span>`;
            stepsEl.appendChild(titleRow);
            stepsEl.scrollTop = stepsEl.scrollHeight;
          }
          break;
        }

        case 'reasoning': {
          if (stepsEl && event.message) {
            const reasonRow = document.createElement('div');
            reasonRow.className = 'flex items-start gap-2.5 text-xs text-gray-500';
            reasonRow.innerHTML = `<span class="flex-shrink-0 mt-0.5">${ICON.bulb}</span><span class="italic leading-relaxed">${escapeHtml(event.message)}</span>`;
            stepsEl.appendChild(reasonRow);
            stepsEl.scrollTop = stepsEl.scrollHeight;
          }
          break;
        }

        case 'tool_call':
          // Resolve any previous pending step (e.g. "Agent is preparing response…")
          // before starting the tool-call indicator, otherwise it spins forever.
          _resolveStep(_pendingStep, true);
          _pendingStep = document.createElement('div');
          _pendingStep.className = 'flex items-start gap-2.5 text-xs text-gray-400';
          _pendingStep.innerHTML = `<span class="step-icon flex-shrink-0 mt-0.5">${ICON.spinner}</span><span class="step-text leading-relaxed">${escapeHtml(event.message || 'Calling tool…')}</span>`;
          if (stepsEl) { stepsEl.appendChild(_pendingStep); stepsEl.scrollTop = stepsEl.scrollHeight; }
          break;

        case 'tool_done':
          _resolveStep(_pendingStep, true);
          _pendingStep = null;
          break;

        case 'agent_chunk': {
          const text = event.data?.text ?? null;
          if (text) {
            if (!_streamingStep) {
              // Resolve the "preparing" waiting step before starting the streaming indicator
              _resolveStep(_pendingStep, true);
              _pendingStep = null;
              _streamingStep = _createStep('Receiving response…');
            }
            accumulatedResponse += text;
          }
          break;
        }

        case 'done': {
          _resolveStep(_pendingStep, true);
          _pendingStep = null;

          // Resolve the streaming indicator and parse the response
          if (_streamingStep) {
            _resolveStep(_streamingStep, true);
            _streamingStep = null;
          }

          if (generateBtn) {
            generateBtn.disabled = false;
            generateBtn.classList.remove('opacity-50', 'cursor-not-allowed');
          }

          if (accumulatedResponse) {
            const parsed = _extractJSON(accumulatedResponse);
            if (parsed) {
              _renderStructuredResponse(parsed, accumulatedResponse);
            } else {
              // Fallback: show the raw text
              if (responseEl) responseEl.classList.remove('hidden');
              if (outputEl)   outputEl.textContent = accumulatedResponse;
            }
          }
          break;
        }

        case 'error': {
          const errMsg = typeof event.message === 'string'
            ? event.message
            : JSON.stringify(event.message);
          _resolveStep(_pendingStep, false, errMsg);
          _pendingStep = null;
          if (_streamingStep) {
            _resolveStep(_streamingStep, false);
            _streamingStep = null;
          }
          if (generateBtn) {
            generateBtn.disabled = false;
            generateBtn.classList.remove('opacity-50', 'cursor-not-allowed');
          }
          break;
        }
      }
    }

    const body = { connection_id: connectionId, walk_text: walkText };
    if (kibanaUrl)    body.kibana_url    = kibanaUrl;
    if (inferenceId)  body.inference_id  = inferenceId;

    fetch('/SNMP/GenerateTemplateAndProfiles/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      body: JSON.stringify(body),
    })
      .then(response => {
        if (response.status === 403) throw new Error('Access denied: Admin role required');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const reader = response.body.getReader();
        _activeReader = reader;
        const decoder = new TextDecoder();
        let buffer = '';

        function pump() {
          return reader.read().then(({ done, value }) => {
            if (done) { _activeReader = null; return; }
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();
            for (const line of lines) {
              const trimmed = line.trim();
              if (!trimmed.startsWith('data: ')) continue;
              const jsonStr = trimmed.slice(6).trim();
              if (!jsonStr) continue;
              try { handleChunk(JSON.parse(jsonStr)); } catch (_) {}
            }
            return pump();
          });
        }
        return pump();
      })
      .catch(err => {
        if (stepsEl) {
          const errRow = document.createElement('div');
          errRow.className = 'flex items-start gap-2.5 text-xs text-red-400';
          errRow.innerHTML = `<span class="flex-shrink-0">${ICON.xmark}</span><span>Request failed: ${escapeHtml(err.message)}</span>`;
          stepsEl.appendChild(errRow);
        }
        if (generateBtn) {
          generateBtn.disabled = false;
          generateBtn.classList.remove('opacity-50', 'cursor-not-allowed');
        }
      });
  }

  // ── Global exports ─────────────────────────────────────────────────────────────

  window.openAiDeviceTemplateModal  = openAiDeviceTemplateModal;
  window.closeAiDeviceTemplateModal = closeAiDeviceTemplateModal;

})();
