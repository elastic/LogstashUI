/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

(function () {
  'use strict';

  // ── State ─────────────────────────────────────────────────────────────────────

  let _matchedTemplateId   = null;
  let _matchedTemplateName = null;
  let _inMatchFlow         = false; // true when a match was found (uses #wizardTemplateSelect)

  // Set when coming from the Devices table (device_id URL param) or after FindDeviceByHost resolves.
  // Template dropdowns use wizardTemplateMatchValue / wizardTemplateManualValue hidden inputs.
  let _existingDeviceId    = null;

  // ── CSRF ──────────────────────────────────────────────────────────────────────

  function getCsrf() {
    const el = document.querySelector('[name=csrfmiddlewaretoken]');
    return el ? el.value : '';
  }

  // ── Override openAiDeviceTemplateModal for the Onboarding page ────────────────
  // On other pages this opens a modal; here we switch to Tab 3 inline instead.

  window.openAiDeviceTemplateModal = function (prefillWalkData) {
    // Close the SNMP test modal if it's open
    const testModal = document.getElementById('snmpTestModal');
    if (testModal) {
      testModal.classList.add('hidden');
      testModal.classList.remove('flex');
      document.body.style.overflow = '';
    }

    // Switch to the Generate Template & Profiles tab
    const genTab = document.getElementById('generateTemplateTab');
    if (genTab) genTab.click();

    // Pre-fill walk text and nudge button state
    if (prefillWalkData) {
      const walkInput = document.getElementById('aiTemplateWalkInput');
      if (walkInput) {
        walkInput.value = prefillWalkData;
        walkInput.dispatchEvent(new Event('input'));
      }
    }

    // Scroll the generate content into view
    setTimeout(() => {
      const genContent = document.getElementById('generateTemplateContent');
      if (genContent) genContent.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
  };

  // ── Wizard credential dropdown — exact copy of snmp_devices_modal.js pattern ──

  function _setWizardCredentialValue(id, displayText) {
    const hiddenInput = document.getElementById('wizardCredentialValue');
    const text        = document.getElementById('wizardCredentialSelectedText');
    if (hiddenInput) hiddenInput.value = id || '';
    if (text) {
      if (id) {
        text.textContent = displayText;
        text.classList.remove('text-gray-400');
        text.classList.add('text-white');
      } else {
        text.textContent = 'Select a credential...';
        text.classList.add('text-gray-400');
        text.classList.remove('text-white');
      }
    }
  }

  function selectWizardCredentialOption(id, displayText) {
    _setWizardCredentialValue(id, displayText);
    closeWizardCredentialDropdown();
  }

  function toggleWizardCredentialDropdown(event) {
    event.stopPropagation();
    const list = document.getElementById('wizardCredentialDropdownList');
    if (!list) return;
    const isOpening = list.classList.contains('hidden');
    list.classList.toggle('hidden');
    if (isOpening) {
      const currentVal = document.getElementById('wizardCredentialValue')?.value || null;
      loadWizardCredentials(currentVal);
      setTimeout(() => document.getElementById('wizardCredentialSearch')?.focus(), 50);
    }
  }

  function closeWizardCredentialDropdown() {
    const list = document.getElementById('wizardCredentialDropdownList');
    if (list) list.classList.add('hidden');
    const searchInput = document.getElementById('wizardCredentialSearch');
    if (searchInput) {
      searchInput.value = '';
      filterWizardCredentialDropdown('');
    }
  }

  function filterWizardCredentialDropdown(query) {
    const optionsList = document.getElementById('wizardCredentialOptionsList');
    if (!optionsList) return;
    const q = query.toLowerCase();
    optionsList.querySelectorAll('.wizard-credential-option-row').forEach(row => {
      const searchText = row.dataset.searchText || '';
      row.classList.toggle('hidden', searchText !== '' && !searchText.includes(q));
    });
  }

  function loadWizardCredentials(selectedCredentialId = null) {
    fetch('/SNMP/GetCredentials/')
      .then(r => r.json())
      .then(credentials => {
        const optionsList = document.getElementById('wizardCredentialOptionsList');
        if (!optionsList) return;
        optionsList.innerHTML = '';

        // "No selection" row
        const clearRow = document.createElement('div');
        clearRow.className = 'flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:bg-gray-700 cursor-pointer wizard-credential-option-row';
        clearRow.dataset.searchText = '';
        clearRow.textContent = 'Select a credential...';
        clearRow.onclick = () => selectWizardCredentialOption('', '');
        optionsList.appendChild(clearRow);

        // "+ Add Credential" row
        const addRow = document.createElement('div');
        addRow.className = 'flex items-center gap-2 px-3 py-2 text-sm font-bold text-primary hover:bg-gray-700 cursor-pointer wizard-credential-option-row';
        addRow.dataset.searchText = '';
        addRow.textContent = '+ Add Credential';
        addRow.onclick = () => { closeWizardCredentialDropdown(); if (typeof openCredentialModal === 'function') openCredentialModal(); };
        optionsList.appendChild(addRow);

        credentials.forEach(credential => {
          const displayText = `${credential.name} (SNMPv${credential.version})`;
          const row = document.createElement('div');
          row.className = 'flex items-center gap-2 px-3 py-2 text-sm text-white hover:bg-gray-700 cursor-pointer wizard-credential-option-row';
          row.dataset.searchText = displayText.toLowerCase();
          row.innerHTML = `<span class="truncate">${displayText}</span>`;
          row.onclick = () => selectWizardCredentialOption(credential.id, displayText);
          optionsList.appendChild(row);

          if (selectedCredentialId && credential.id == selectedCredentialId) {
            _setWizardCredentialValue(credential.id, displayText);
          }
        });
      })
      .catch(() => {});
  }

  // ── Wizard network dropdown — exact copy of snmp_devices_modal.js pattern ─────

  function _setWizardNetworkValue(id, displayText) {
    const hiddenInput = document.getElementById('wizardNetworkValue');
    const text        = document.getElementById('wizardNetworkSelectedText');
    if (hiddenInput) hiddenInput.value = id || '';
    if (text) {
      if (id) {
        text.textContent = displayText;
        text.classList.remove('text-gray-400');
        text.classList.add('text-white');
      } else {
        text.textContent = 'Select a network...';
        text.classList.add('text-gray-400');
        text.classList.remove('text-white');
      }
    }
  }

  function selectWizardNetworkOption(id, displayText) {
    _setWizardNetworkValue(id, displayText);
    closeWizardNetworkDropdown();
  }

  function toggleWizardNetworkDropdown(event) {
    event.stopPropagation();
    const list = document.getElementById('wizardNetworkDropdownList');
    if (!list) return;
    const isOpening = list.classList.contains('hidden');
    list.classList.toggle('hidden');
    if (isOpening) {
      const currentVal = document.getElementById('wizardNetworkValue')?.value || null;
      loadWizardNetworks(currentVal);
      setTimeout(() => document.getElementById('wizardNetworkSearch')?.focus(), 50);
    }
  }

  function closeWizardNetworkDropdown() {
    const list = document.getElementById('wizardNetworkDropdownList');
    if (list) list.classList.add('hidden');
    const searchInput = document.getElementById('wizardNetworkSearch');
    if (searchInput) {
      searchInput.value = '';
      filterWizardNetworkDropdown('');
    }
  }

  function filterWizardNetworkDropdown(query) {
    const optionsList = document.getElementById('wizardNetworkOptionsList');
    if (!optionsList) return;
    const q = query.toLowerCase();
    optionsList.querySelectorAll('.wizard-network-option-row').forEach(row => {
      const searchText = row.dataset.searchText || '';
      row.classList.toggle('hidden', searchText !== '' && !searchText.includes(q));
    });
  }

  function loadWizardNetworks(selectedNetworkId = null) {
    fetch('/SNMP/GetNetworks/')
      .then(r => r.json())
      .then(networks => {
        const optionsList = document.getElementById('wizardNetworkOptionsList');
        if (!optionsList) return;
        optionsList.innerHTML = '';

        // "No selection" row
        const clearRow = document.createElement('div');
        clearRow.className = 'flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:bg-gray-700 cursor-pointer wizard-network-option-row';
        clearRow.dataset.searchText = '';
        clearRow.textContent = 'Select a network...';
        clearRow.onclick = () => selectWizardNetworkOption('', '');
        optionsList.appendChild(clearRow);

        // "+ Add Network" row
        const addRow = document.createElement('div');
        addRow.className = 'flex items-center gap-2 px-3 py-2 text-sm font-bold text-primary hover:bg-gray-700 cursor-pointer wizard-network-option-row';
        addRow.dataset.searchText = '';
        addRow.textContent = '+ Add Network';
        addRow.onclick = () => { closeWizardNetworkDropdown(); if (typeof openNetworkModal === 'function') openNetworkModal(); };
        optionsList.appendChild(addRow);

        networks.forEach(network => {
          const displayText = network.network_range
            ? `${network.name} (${network.network_range})`
            : network.name;
          const row = document.createElement('div');
          row.className = 'flex items-center gap-2 px-3 py-2 text-sm text-white hover:bg-gray-700 cursor-pointer wizard-network-option-row';
          row.dataset.searchText = displayText.toLowerCase();
          row.innerHTML = `<span class="truncate">${displayText}</span>`;
          row.onclick = () => selectWizardNetworkOption(network.id, displayText);
          optionsList.appendChild(row);

          if (selectedNetworkId && network.id == selectedNetworkId) {
            _setWizardNetworkValue(network.id, displayText);
          }
        });
      })
      .catch(() => {});
  }

  // ── Wizard template dropdown — exact copy of snmp_devices_modal.js pattern ───
  // Accepts suffix 'Match' or 'Manual' so both picker instances share one code path.

  function _setWizardTemplateValue(suffix, id, displayName, vendor) {
    const hiddenInput = document.getElementById(`wizardTemplate${suffix}Value`);
    const img         = document.getElementById(`wizardTemplate${suffix}SelectedImg`);
    const text        = document.getElementById(`wizardTemplate${suffix}SelectedText`);
    const wrapper     = document.getElementById(`wizardTemplate${suffix}DropdownWrapper`);
    const imagesUrl   = wrapper ? wrapper.dataset.imagesUrl : '';

    if (hiddenInput) hiddenInput.value = id || '';

    if (id) {
      if (img) { img.src = imagesUrl + getVendorLogoFilename(vendor); img.alt = vendor || ''; img.classList.remove('hidden'); }
      if (text) { text.textContent = displayName; text.classList.remove('text-gray-400'); text.classList.add('text-white'); }
    } else {
      if (img) { img.src = ''; img.classList.add('hidden'); }
      if (text) { text.textContent = 'Select a template...'; text.classList.add('text-gray-400'); text.classList.remove('text-white'); }
    }
  }

  function selectWizardTemplateOption(suffix, id, displayName, vendor) {
    _setWizardTemplateValue(suffix, id, displayName, vendor);
    closeWizardTemplateDropdown(suffix);
  }

  function toggleWizardTemplateDropdown(suffix, event) {
    event.stopPropagation();
    const list = document.getElementById(`wizardTemplate${suffix}DropdownList`);
    if (!list) return;
    const isOpening = list.classList.contains('hidden');
    list.classList.toggle('hidden');
    if (isOpening) {
      const currentVal = document.getElementById(`wizardTemplate${suffix}Value`)?.value || null;
      loadWizardTemplates(suffix, currentVal);
      setTimeout(() => document.getElementById(`wizardTemplate${suffix}Search`)?.focus(), 50);
    }
  }

  function closeWizardTemplateDropdown(suffix) {
    const list = document.getElementById(`wizardTemplate${suffix}DropdownList`);
    if (list) list.classList.add('hidden');
    const searchInput = document.getElementById(`wizardTemplate${suffix}Search`);
    if (searchInput) { searchInput.value = ''; filterWizardTemplateDropdown(suffix, ''); }
  }

  function filterWizardTemplateDropdown(suffix, query) {
    const optionsList = document.getElementById(`wizardTemplate${suffix}OptionsList`);
    if (!optionsList) return;
    const q = query.toLowerCase();
    optionsList.querySelectorAll('.wizard-template-option-row').forEach(row => {
      const searchText = row.dataset.searchText || '';
      row.classList.toggle('hidden', searchText !== '' && !searchText.includes(q));
    });
  }

  function loadWizardTemplates(suffix, selectedTemplateId = null) {
    const wrapper   = document.getElementById(`wizardTemplate${suffix}DropdownWrapper`);
    const imagesUrl = wrapper ? wrapper.dataset.imagesUrl : '';

    fetch('/SNMP/GetDeviceTemplates/')
      .then(r => r.json())
      .then(data => {
        const optionsList = document.getElementById(`wizardTemplate${suffix}OptionsList`);
        if (!optionsList) return;
        optionsList.innerHTML = '';

        const clearRow = document.createElement('div');
        clearRow.className = 'flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:bg-gray-700 cursor-pointer wizard-template-option-row';
        clearRow.dataset.searchText = '';
        clearRow.textContent = 'Select a template...';
        clearRow.onclick = () => selectWizardTemplateOption(suffix, '', '', '');
        optionsList.appendChild(clearRow);

        const templates = data.templates || [];
        templates.forEach(template => {
          const logoSrc   = imagesUrl + getVendorLogoFilename(template.vendor);
          const displayName = template.display_name || template.name;
          const row = document.createElement('div');
          row.className = 'flex items-center gap-2 px-3 py-2 text-sm text-white hover:bg-gray-700 cursor-pointer wizard-template-option-row';
          row.dataset.searchText = `${displayName} ${template.vendor || ''}`.toLowerCase();
          row.innerHTML = `
            <img src="${logoSrc}" alt="${template.vendor || ''}"
                 class="w-5 h-5 object-contain flex-shrink-0 rounded bg-white p-0.5">
            <span class="truncate">${displayName}</span>
          `;
          row.onclick = () => selectWizardTemplateOption(suffix, template.id, displayName, template.vendor);
          optionsList.appendChild(row);

          if (selectedTemplateId && template.id == selectedTemplateId) {
            _setWizardTemplateValue(suffix, template.id, displayName, template.vendor);
          }
        });
      })
      .catch(() => {});
  }

  // ── DOMContentLoaded ──────────────────────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', function () {

    // Close all custom dropdowns on outside click
    document.addEventListener('click', function (e) {
      if (!document.getElementById('wizardCredentialDropdownWrapper')?.contains(e.target)) {
        closeWizardCredentialDropdown();
      }
      if (!document.getElementById('wizardNetworkDropdownWrapper')?.contains(e.target)) {
        closeWizardNetworkDropdown();
      }
      if (!document.getElementById('wizardTemplateMatchDropdownWrapper')?.contains(e.target)) {
        closeWizardTemplateDropdown('Match');
      }
      if (!document.getElementById('wizardTemplateManualDropdownWrapper')?.contains(e.target)) {
        closeWizardTemplateDropdown('Manual');
      }
    });

    // ── URL param handling: ?tab=wizard[&device_id=X] ──────────────────────
    const params   = new URLSearchParams(window.location.search);
    const tabParam = params.get('tab');
    const devParam = params.get('device_id');

    if (tabParam === 'wizard') {
      const wizTab = document.getElementById('deviceWizardTab');
      if (wizTab) wizTab.click();
      if (devParam) _prefillWizardFromDevice(parseInt(devParam, 10));
    }

    // When a credential is saved, reload dropdown and auto-select it
    document.addEventListener('credentialSaved', function (e) {
      const newId = e.detail && e.detail.id;
      loadWizardCredentials(newId);
    });

    // When a network is saved, reload dropdown and auto-select it
    document.addEventListener('networkSaved', function (e) {
      const newId = e.detail && e.detail.id;
      loadWizardNetworks(newId);
    });
  });

  // ── Pre-fill wizard from an existing device ───────────────────────────────────

  function _prefillWizardFromDevice(deviceId) {
    fetch(`/SNMP/GetDevice/${deviceId}/`)
      .then(r => r.json())
      .then(data => {
        // GetDevice may return the object directly or wrapped
        const d = data.device || data;
        if (!d || !d.id) return;

        _existingDeviceId = d.id;

        // Host: prefer ip_address, fall back to hostname
        const hostInput = document.getElementById('wizardHost');
        if (hostInput) hostInput.value = d.ip_address || d.hostname || d.name || '';

        const portInput = document.getElementById('wizardPort');
        if (portInput && d.port) portInput.value = d.port;

        // GetDevice returns FK ids as 'credential', 'network' (not *_id)
        // Load the dropdowns and auto-select the matching option
        if (d.credential) loadWizardCredentials(d.credential);
        if (d.network)    loadWizardNetworks(d.network);

        // Show an informational banner so the user knows this is an edit
        _showEditBanner(d.name);
      })
      .catch(() => {});
  }

  function _showEditBanner(deviceName) {
    // Inject a small banner above the input card if not already there
    const wizard = document.getElementById('deviceWizardContent');
    if (!wizard || wizard.querySelector('#wizardEditBanner')) return;

    const banner = document.createElement('div');
    banner.id = 'wizardEditBanner';
    banner.className = 'flex items-center gap-2 text-sm text-purple-300 bg-purple-900/20 border border-purple-500/30 rounded-lg px-4 py-3';
    banner.innerHTML = `
      <svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
      </svg>
      <span>Updating <strong>${escapeHtml(deviceName)}</strong> — only the template, credential, network, and port will be changed.</span>
    `;
    wizard.insertBefore(banner, wizard.firstChild);
  }

  // ── UI helpers ────────────────────────────────────────────────────────────────

  function _showResultState(stateId) {
    ['wizardResultMatch', 'wizardResultNoMatch', 'wizardResultUnreachable'].forEach(id => {
      document.getElementById(id)?.classList.add('hidden');
    });
    document.getElementById(stateId)?.classList.remove('hidden');
    document.getElementById('wizardResultCard')?.classList.remove('hidden');
    document.getElementById('wizardManualPicker')?.classList.add('hidden');
  }

  // ── Check Device Type ─────────────────────────────────────────────────────────

  function wizardCheckDevice() {
    const host   = (document.getElementById('wizardHost')?.value || '').trim();
    const credId = document.getElementById('wizardCredentialValue')?.value;
    const port   = parseInt(document.getElementById('wizardPort')?.value || '161', 10);

    if (!host) {
      showToast('Please enter an IP address or hostname.', 'warning');
      return;
    }
    if (!credId) {
      showToast('Please select an SNMP credential.', 'warning');
      return;
    }

    const btn = document.getElementById('wizardCheckBtn');
    if (btn) {
      btn.disabled = true;
      btn.classList.add('opacity-50', 'cursor-not-allowed');
      btn.innerHTML = `<svg class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
      </svg> Checking…`;
    }

    fetch('/SNMP/CheckDeviceType/', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      body:    JSON.stringify({ host, port, credential_id: parseInt(credId, 10) }),
    })
      .then(r => r.json())
      .then(data => {
        _restoreCheckBtn();

        if (!data.success) {
          document.getElementById('wizardUnreachableError').textContent = data.error || 'Unknown error.';
          _showResultState('wizardResultUnreachable');
          return;
        }

        if (data.matched_template) {
          _matchedTemplateId   = data.matched_template.id;
          _matchedTemplateName = data.matched_template.name;
          _inMatchFlow         = true;
          _renderMatchCard(data.matched_template);
          _autoSelectTemplate('Match', _matchedTemplateId, _matchedTemplateName);
          _showResultState('wizardResultMatch');
        } else {
          _inMatchFlow = false;
          const noMatchEl = document.getElementById('wizardNoMatchSysDescr');
          if (noMatchEl) noMatchEl.textContent = data.sys_descr || '(no sysDescr returned)';
          _showResultState('wizardResultNoMatch');
        }
      })
      .catch(err => {
        _restoreCheckBtn();
        document.getElementById('wizardUnreachableError').textContent = `Request failed: ${err.message}`;
        _showResultState('wizardResultUnreachable');
      });
  }

  function _restoreCheckBtn() {
    const btn = document.getElementById('wizardCheckBtn');
    if (!btn) return;
    btn.disabled = false;
    btn.classList.remove('opacity-50', 'cursor-not-allowed');
    btn.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
    </svg> Check Device Type`;
  }

  function _renderMatchCard(tpl) {
    const card = document.getElementById('wizardMatchedTemplateCard');
    if (!card) return;

    const rules = (tpl.matching_rules || []).map(r =>
      `<span class="px-1.5 py-0.5 rounded bg-gray-700 text-xs text-gray-300 font-mono">${escapeHtml(r)}</span>`
    ).join(' ');

    const rawProfileNames = tpl.profile_names || [];
    const profileLabels = tpl.profile_display_names && tpl.profile_display_names.length
      ? tpl.profile_display_names
      : rawProfileNames.map(p => formatDisplayName(p));
    const starSvg = `<svg class="w-3 h-3 text-yellow-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
      </svg>`;
    const profiles = profileLabels.map((p, i) => {
      const isOfficial = (rawProfileNames[i] || '').endsWith('.json');
      return `<span class="px-1.5 py-0.5 rounded bg-purple-900/40 border border-purple-500/20 text-xs text-purple-300 font-mono inline-flex items-center gap-1" ${isOfficial ? 'title="Official profile"' : ''}>${isOfficial ? starSvg : ''}${escapeHtml(p)}</span>`;
    }).join(' ');

    const templateLabel = tpl.display_name || formatDisplayName(tpl.name);

    const row = (label, valueHtml) => `
      <div class="grid grid-cols-[6.5rem_1fr] gap-x-3 py-1 items-start">
        <div class="text-[11px] font-semibold text-gray-500 uppercase tracking-wide pt-0.5">${label}</div>
        <div class="min-w-0">${valueHtml}</div>
      </div>
    `;

    card.innerHTML = `
      <div class="divide-y divide-gray-800/70">
        ${row('Template', `<span class="text-sm font-semibold text-white font-mono">${escapeHtml(templateLabel)}</span>`)}
        ${tpl.vendor ? row('Vendor', `<span class="text-xs text-gray-300">${escapeHtml(tpl.vendor)}</span>`) : ''}
        ${tpl.description ? row('Description', `<span class="text-xs text-gray-300 leading-relaxed">${escapeHtml(tpl.description)}</span>`) : ''}
        ${rules ? row('Matched on', `<div class="flex flex-wrap gap-1">${rules}</div>`) : ''}
        ${profiles ? row('Profiles', `<div class="flex flex-wrap gap-1">${profiles}</div>`) : ''}
      </div>
    `;
  }

  function _autoSelectTemplate(suffix, id, name) {
    // Load the template dropdown and auto-select the given id.
    // Works for both 'Match' and 'Manual' suffix instances.
    loadWizardTemplates(suffix, id);
  }

  // ── Skip check ────────────────────────────────────────────────────────────────

  function wizardSkipCheck() {
    _inMatchFlow = false;
    // Hide the error/result panels but keep the container visible — the manual
    // picker lives inside wizardResultCard, so we can't hide the container.
    ['wizardResultMatch', 'wizardResultNoMatch', 'wizardResultUnreachable'].forEach(id =>
      document.getElementById(id)?.classList.add('hidden')
    );
    document.getElementById('wizardResultCard')?.classList.remove('hidden');
    document.getElementById('wizardManualPicker')?.classList.remove('hidden');
  }

  function wizardBringYourOwnWalk() {
    // Send the user to the Generate Template and Profiles tab.
    document.getElementById('generateTemplateTab')?.click();
  }

  // ── Open walk modal pre-filled ────────────────────────────────────────────────

  function wizardOpenWalkModal() {
    const host   = (document.getElementById('wizardHost')?.value || '').trim();
    const credId = document.getElementById('wizardCredentialValue')?.value || '';
    const port   = document.getElementById('wizardPort')?.value || '161';

    const modal   = document.getElementById('snmpTestModal');
    const walkTab = document.getElementById('snmpTestTabWalk');
    if (!modal || !walkTab) {
      showToast('SNMP Test modal not available.', 'error');
      return;
    }

    // Open modal
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    document.body.style.overflow = 'hidden';

    // Switch to Walk tab (this may trigger resetWalkTab in snmp_test.js)
    walkTab.click();

    // Pre-fill AFTER any reset the tab-click may have triggered
    setTimeout(() => {
      const hostInput = document.getElementById('snmpWalkHostInput');
      if (hostInput) {
        hostInput.value = host;
        hostInput.dispatchEvent(new Event('input')); // triggers updateWalkButton()
      }

      const portInput = document.getElementById('snmpWalkPortInput');
      if (portInput) portInput.value = port;

      const credSel = document.getElementById('snmpWalkCredentialSelect');
      if (credSel && credId) {
        credSel.value = credId;
        credSel.dispatchEvent(new Event('change')); // triggers updateWalkButton()
      }
    }, 50);

    // Set the hook so the imported template auto-selects in the wizard picker
    window.onAITemplateImported = function ({ id, name }) {
      // Show the manual picker with the newly imported template selected
      _inMatchFlow = false;
      _autoSelectTemplate('Manual', id, name);
      document.getElementById('wizardManualPicker')?.classList.remove('hidden');
      document.getElementById('wizardResultCard')?.classList.add('hidden');

      // Switch back to wizard tab
      const wizTab = document.getElementById('deviceWizardTab');
      if (wizTab) wizTab.click();
    };
  }

  // ── Save device ───────────────────────────────────────────────────────────────

  function wizardSaveDevice() {
    const host      = (document.getElementById('wizardHost')?.value || '').trim();
    const credId    = document.getElementById('wizardCredentialValue')?.value || '';
    const networkId = document.getElementById('wizardNetworkValue')?.value || '';
    const port      = document.getElementById('wizardPort')?.value || '161';

    // Get template from whichever picker is active
    const suffix       = _inMatchFlow ? 'Match' : 'Manual';
    const templateId   = document.getElementById(`wizardTemplate${suffix}Value`)?.value || '';
    const templateName = document.getElementById(`wizardTemplate${suffix}SelectedText`)?.textContent?.trim() || templateId;

    if (!host) { showToast('Host is required.', 'warning'); return; }

    _disableSaveBtns();

    // If we already know the device (came from devices table link OR a previous
    // FindDeviceByHost hit), go straight to update. Otherwise look it up first.
    if (_existingDeviceId) {
      _doUpdateDevice(_existingDeviceId, host, credId, networkId, port, templateId, templateName);
    } else {
      fetch(`/SNMP/FindDeviceByHost/?host=${encodeURIComponent(host)}`)
        .then(r => r.json())
        .then(data => {
          if (data.device && data.device.id) {
            _existingDeviceId = data.device.id;
            _doUpdateDevice(data.device.id, host, credId, networkId, port, templateId, templateName);
          } else {
            _doCreateDevice(host, credId, networkId, port, templateId, templateName);
          }
        })
        .catch(() => {
          // If lookup fails, fall back to create — AddDevice handles uniqueness at the DB level
          _doCreateDevice(host, credId, networkId, port, templateId, templateName);
        });
    }
  }

  function _disableSaveBtns() {
    ['wizardSaveBtn', 'wizardSaveBtnManual'].forEach(id => {
      const b = document.getElementById(id);
      if (b) {
        b.disabled = true;
        b.classList.add('opacity-50', 'cursor-not-allowed');
        b.innerHTML = `<svg class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
        </svg> Saving…`;
      }
    });
  }

  function _doUpdateDevice(deviceId, host, credId, networkId, port, templateId, templateName) {
    const isIp = /^[\d.]+$|^[0-9a-fA-F:]+$/.test(host);
    const payload = new URLSearchParams();
    // Only send the wizard-managed fields on update
    if (isIp) payload.append('ip_address', host);
    else      payload.append('hostname',   host);
    payload.append('port', port);
    if (credId)     payload.append('credential',      credId);
    if (networkId)  payload.append('network',         networkId);
    if (templateId) payload.append('device_template', templateId);

    fetch(`/SNMP/UpdateDevice/${deviceId}/`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-CSRFToken': getCsrf() },
      body:    payload.toString(),
    })
      .then(r => {
        if (r.status === 403) throw new Error('Access denied: Admin role required');
        return r.json();
      })
      .then(data => {
        _restoreSaveBtns();
        if (data.id || data.success) {
          _showWizardSuccess(host, templateName, true);
        } else {
          showToast(data.error || 'Failed to update device.', 'error');
        }
      })
      .catch(err => {
        _restoreSaveBtns();
        showToast(`Update failed: ${err.message}`, 'error');
      });
  }

  function _doCreateDevice(host, credId, networkId, port, templateId, templateName) {
    const isIp = /^[\d.]+$|^[0-9a-fA-F:]+$/.test(host);
    const payload = new URLSearchParams();
    payload.append('name', host);
    if (isIp) payload.append('ip_address', host);
    else      payload.append('hostname',   host);
    payload.append('port', port);
    if (credId)     payload.append('credential',      credId);
    if (networkId)  payload.append('network',         networkId);
    if (templateId) payload.append('device_template', templateId);

    fetch('/SNMP/AddDevice/', {
      method:  'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-CSRFToken': getCsrf() },
      body:    payload.toString(),
    })
      .then(r => {
        if (r.status === 403) throw new Error('Access denied: Admin role required');
        return r.json();
      })
      .then(data => {
        _restoreSaveBtns();
        if (data.success || data.id) {
          _showWizardSuccess(host, templateName, false);
        } else {
          showToast(data.error || 'Failed to create device.', 'error');
        }
      })
      .catch(err => {
        _restoreSaveBtns();
        showToast(`Save failed: ${err.message}`, 'error');
      });
  }

  function _showWizardSuccess(host, templateName, wasUpdate) {
    const msgEl = document.getElementById('wizardSuccessMsg');
    if (msgEl) {
      if (wasUpdate) {
        msgEl.textContent = `${host} has been updated`
          + (templateName ? ` with the "${templateName}" template` : '')
          + '. Deploy changes from the header to start polling.';
      } else {
        msgEl.textContent = `${host} has been added`
          + (templateName ? ` with the "${templateName}" template` : '')
          + '. Deploy changes from the header to start polling.';
      }
    }
    document.getElementById('wizardResultCard')?.classList.add('hidden');
    document.getElementById('wizardManualPicker')?.classList.add('hidden');
    document.getElementById('wizardSuccessCard')?.classList.remove('hidden');

    if (typeof window.triggerUndeployedChangesCheck === 'function') {
      window.triggerUndeployedChangesCheck();
    }
  }

  function _restoreSaveBtns() {
    const saveHtml = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
    </svg> Save Device`;
    ['wizardSaveBtn', 'wizardSaveBtnManual'].forEach(id => {
      const b = document.getElementById(id);
      if (b) { b.disabled = false; b.classList.remove('opacity-50', 'cursor-not-allowed'); b.innerHTML = saveHtml; }
    });
  }

  // ── Reset ─────────────────────────────────────────────────────────────────────

  function wizardReset() {
    _matchedTemplateId   = null;
    _matchedTemplateName = null;
    _inMatchFlow         = false;
    _existingDeviceId    = null;
    window.onAITemplateImported = null;

    // Remove the edit banner if present
    document.getElementById('wizardEditBanner')?.remove();

    const hostEl = document.getElementById('wizardHost');
    if (hostEl) hostEl.value = '';
    document.getElementById('wizardPort') && (document.getElementById('wizardPort').value = '161');
    _setWizardCredentialValue('', '');
    _setWizardNetworkValue('', '');
    _setWizardTemplateValue('Match',  '', '', '');
    _setWizardTemplateValue('Manual', '', '', '');

    document.getElementById('wizardResultCard')?.classList.add('hidden');
    document.getElementById('wizardManualPicker')?.classList.add('hidden');
    document.getElementById('wizardSuccessCard')?.classList.add('hidden');

    ['wizardResultMatch', 'wizardResultNoMatch', 'wizardResultUnreachable'].forEach(id =>
      document.getElementById(id)?.classList.add('hidden')
    );

    // Clear stale text so it doesn't flash on next check
    const noMatchDescr = document.getElementById('wizardNoMatchSysDescr');
    if (noMatchDescr) noMatchDescr.textContent = '';
    const unreachableErr = document.getElementById('wizardUnreachableError');
    if (unreachableErr) unreachableErr.textContent = '';
    const matchCard = document.getElementById('wizardMatchedTemplateCard');
    if (matchCard) matchCard.innerHTML = '';
    const successMsg = document.getElementById('wizardSuccessMsg');
    if (successMsg) successMsg.textContent = '';

    _restoreCheckBtn();
    _restoreSaveBtns();
  }

  // ── Global exports ────────────────────────────────────────────────────────────

  window.wizardCheckDevice       = wizardCheckDevice;
  window.wizardSkipCheck         = wizardSkipCheck;
  window.wizardBringYourOwnWalk  = wizardBringYourOwnWalk;
  window.wizardOpenWalkModal     = wizardOpenWalkModal;
  window.wizardSaveDevice        = wizardSaveDevice;
  window.wizardReset             = wizardReset;

  // Custom dropdown functions called from HTML onclick/oninput attributes
  window.toggleWizardCredentialDropdown = toggleWizardCredentialDropdown;
  window.filterWizardCredentialDropdown = filterWizardCredentialDropdown;
  window.toggleWizardNetworkDropdown    = toggleWizardNetworkDropdown;
  window.filterWizardNetworkDropdown    = filterWizardNetworkDropdown;
  window.toggleWizardTemplateDropdown   = toggleWizardTemplateDropdown;
  window.filterWizardTemplateDropdown   = filterWizardTemplateDropdown;

})();
