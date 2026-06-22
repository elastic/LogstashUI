/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// SNMP Network Modal JavaScript

// Open modal for adding new network
const addNetworkBtn = document.getElementById('addNetworkBtn');
if (addNetworkBtn) {
  addNetworkBtn.addEventListener('click', function () {
    openNetworkModal();
  });
}

// Open network modal (for add or edit)
function openNetworkModal(networkData = null) {
  const modal = document.getElementById('networkFormModal');
  const form = document.getElementById('networkForm');
  const modalTitle = document.getElementById('modalTitle');

  networkModalIsOpen = true;

  // Reset form
  form.reset();
  document.getElementById('networkErrorContainer').innerHTML = '';

  // Load connections into dropdown
  loadConnections(networkData ? networkData.connection : null);

  // Load credentials into dropdowns
  loadDiscoveryCredentials(networkData ? networkData.discovery_credential : null);
  loadNetworkCredentials(networkData ? networkData.credential : null);

  if (networkData) {
    // Check if this is edit mode (has ID) or clone mode (no ID)
    const isEditMode = networkData.id !== undefined;
    
    if (isEditMode) {
      // Edit mode
      modalTitle.textContent = 'Edit SNMP Network';
      document.getElementById('networkId').value = networkData.id;
    } else {
      // Clone mode - has data but no ID
      modalTitle.textContent = 'Add SNMP Network';
      document.getElementById('networkId').value = '';
    }
    
    // Fill in the form fields
    console.log('Network data:', networkData);
    console.log('Namespace value:', networkData.namespace);
    document.getElementById('networkName').value = networkData.name;
    document.getElementById('networkRange').value = networkData.network_range;
    document.getElementById('networkNamespace').value = networkData.namespace || 'default';

    // Restore namespace-from-template toggle
    const useTemplate = !!networkData.namespace_from_device_template;
    document.getElementById('namespaceFromTemplate').checked = useTemplate;
    toggleNamespaceFromTemplate(useTemplate);

    // Set polling interval if present
    if (networkData.interval !== undefined) {
      document.getElementById('pollingInterval').value = networkData.interval;
    }

    // Set discovery enabled radio
    const discoveryValue = networkData.discovery_enabled ? 'true' : 'false';
    document.querySelector(`input[name="discovery_enabled"][value="${discoveryValue}"]`).checked = true;

    // Set traps enabled radio
    const trapsValue = networkData.traps_enabled ? 'true' : 'false';
    document.querySelector(`input[name="traps_enabled"][value="${trapsValue}"]`).checked = true;

    // Show/hide credential sections based on enabled states
    toggleDiscoveryCredential();
    toggleTrapsCredential();
  } else {
    // Add mode — reset toggle to off
    modalTitle.textContent = 'Add SNMP Network';
    document.getElementById('networkId').value = '';
    document.getElementById('namespaceFromTemplate').checked = false;
    toggleNamespaceFromTemplate(false);
    document.querySelector('input[name="discovery_enabled"][value="true"]').checked = true;
    document.querySelector('input[name="traps_enabled"][value="false"]').checked = true;

    // Show/hide credential sections by default
    toggleDiscoveryCredential();
    toggleTrapsCredential();
  }

  modal.classList.remove('hidden');
}

/**
 * Enable or disable the Namespace input based on the
 * "Use device template name as namespace" toggle.
 */
function toggleNamespaceFromTemplate(enabled) {
  const namespaceInput = document.getElementById('networkNamespace');
  const hint = document.getElementById('namespaceFromTemplateHint');

  if (enabled) {
    namespaceInput.disabled = true;
    namespaceInput.classList.add('opacity-40', 'cursor-not-allowed');
    hint.classList.remove('hidden');
  } else {
    namespaceInput.disabled = false;
    namespaceInput.classList.remove('opacity-40', 'cursor-not-allowed');
    hint.classList.add('hidden');
  }
}

// ── Connection custom dropdown ────────────────────────────────────────────────

function selectConnectionOption(id, displayText) {
  const hiddenInput = document.getElementById('networkConnection');
  const text = document.getElementById('networkConnectionSelectedText');
  hiddenInput.value = id || '';
  if (id) {
    text.textContent = displayText;
    text.classList.remove('text-gray-400');
    text.classList.add('text-white');
  } else {
    text.textContent = 'Select a connection...';
    text.classList.add('text-gray-400');
    text.classList.remove('text-white');
  }
  closeConnectionDropdown();
}

function toggleConnectionDropdown(event) {
  event.stopPropagation();
  const list = document.getElementById('networkConnectionDropdownList');
  if (!list) return;
  const isOpening = list.classList.contains('hidden');
  list.classList.toggle('hidden');
  if (isOpening) {
    const currentVal = document.getElementById('networkConnection').value || null;
    loadConnections(currentVal);
    setTimeout(() => document.getElementById('networkConnectionSearch')?.focus(), 50);
  }
}

function closeConnectionDropdown() {
  const list = document.getElementById('networkConnectionDropdownList');
  if (list) list.classList.add('hidden');
  const search = document.getElementById('networkConnectionSearch');
  if (search) { search.value = ''; filterConnectionDropdown(''); }
}

function filterConnectionDropdown(query) {
  const optionsList = document.getElementById('networkConnectionOptionsList');
  if (!optionsList) return;
  const q = query.toLowerCase();
  optionsList.querySelectorAll('.connection-option-row').forEach(row => {
    const searchText = row.dataset.searchText || '';
    row.classList.toggle('hidden', searchText !== '' && !searchText.includes(q));
  });
}

// Load connections into the custom dropdown
function loadConnections(selectedConnectionId = null) {
  fetch('/ConnectionManager/GetConnections/')
    .then(response => response.json())
    .then(connections => {
      const optionsList = document.getElementById('networkConnectionOptionsList');
      if (!optionsList) return;
      optionsList.innerHTML = '';

      const clearRow = document.createElement('div');
      clearRow.className = 'flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:bg-gray-700 cursor-pointer connection-option-row';
      clearRow.dataset.searchText = '';
      clearRow.textContent = 'Select a connection...';
      clearRow.onclick = () => selectConnectionOption('', '');
      optionsList.appendChild(clearRow);

      const addRow = document.createElement('div');
      addRow.className = 'flex items-center gap-2 px-3 py-2 text-sm font-bold text-primary hover:bg-gray-700 cursor-pointer connection-option-row';
      addRow.dataset.searchText = '';
      addRow.textContent = '+ Add Connection';
      addRow.onclick = () => { closeConnectionDropdown(); openConnectionModalFromNetwork(); };
      optionsList.appendChild(addRow);

      const centralizedConnections = connections.filter(c => c.connection_type === 'CENTRALIZED');
      centralizedConnections.forEach(connection => {
        const displayText = `${connection.name} (${connection.connection_type})`;
        const row = document.createElement('div');
        row.className = 'flex items-center gap-2 px-3 py-2 text-sm text-white hover:bg-gray-700 cursor-pointer connection-option-row';
        row.dataset.searchText = displayText.toLowerCase();
        row.innerHTML = `<span class="truncate">${displayText}</span>`;
        row.onclick = () => selectConnectionOption(connection.id, displayText);
        optionsList.appendChild(row);
        if (selectedConnectionId && connection.id == selectedConnectionId) {
          selectConnectionOption(connection.id, displayText);
        }
      });
    })
    .catch(error => console.error('Error loading connections:', error));
}

// Open connection modal from network modal
function openConnectionModalFromNetwork() {
  if (typeof openFlyout === 'function') {
    openFlyout();
  } else {
    console.error('openFlyout function not found');
  }
}

// Refresh connections dropdown
function refreshConnections() {
  const currentValue = document.getElementById('networkConnection')?.value || null;
  loadConnections(currentValue);
}

// Toggle discovery credential section visibility
function toggleDiscoveryCredential() {
  const discoveryEnabled = document.querySelector('input[name="discovery_enabled"]:checked')?.value === 'true';
  const credentialSection = document.getElementById('discoveryCredentialSection');

  if (credentialSection) {
    if (discoveryEnabled) {
      credentialSection.classList.remove('hidden');
    } else {
      credentialSection.classList.add('hidden');
    }
  }
}

// Toggle traps credential section visibility
function toggleTrapsCredential() {
  const trapsEnabled = document.querySelector('input[name="traps_enabled"]:checked')?.value === 'true';
  const credentialSection = document.getElementById('trapsCredentialSection');

  if (credentialSection) {
    if (trapsEnabled) {
      credentialSection.classList.remove('hidden');
    } else {
      credentialSection.classList.add('hidden');
    }
  }
}

// ── Discovery credential custom dropdown ──────────────────────────────────────

function selectDiscoveryCredentialOption(id, displayText) {
  const hiddenInput = document.getElementById('discoveryCredentialSelect');
  const text = document.getElementById('discoveryCredentialSelectedText');
  hiddenInput.value = id || '';
  if (id) {
    text.textContent = displayText;
    text.classList.remove('text-gray-400');
    text.classList.add('text-white');
  } else {
    text.textContent = 'Select a credential...';
    text.classList.add('text-gray-400');
    text.classList.remove('text-white');
  }
  closeDiscoveryCredentialDropdown();
}

function toggleDiscoveryCredentialDropdown(event) {
  event.stopPropagation();
  const list = document.getElementById('discoveryCredentialDropdownList');
  if (!list) return;
  const isOpening = list.classList.contains('hidden');
  list.classList.toggle('hidden');
  if (isOpening) {
    const currentVal = document.getElementById('discoveryCredentialSelect').value || null;
    loadDiscoveryCredentials(currentVal);
    setTimeout(() => document.getElementById('discoveryCredentialSearch')?.focus(), 50);
  }
}

function closeDiscoveryCredentialDropdown() {
  const list = document.getElementById('discoveryCredentialDropdownList');
  if (list) list.classList.add('hidden');
  const search = document.getElementById('discoveryCredentialSearch');
  if (search) { search.value = ''; filterDiscoveryCredentialDropdown(''); }
}

function filterDiscoveryCredentialDropdown(query) {
  const optionsList = document.getElementById('discoveryCredentialOptionsList');
  if (!optionsList) return;
  const q = query.toLowerCase();
  optionsList.querySelectorAll('.discovery-credential-option-row').forEach(row => {
    const searchText = row.dataset.searchText || '';
    row.classList.toggle('hidden', searchText !== '' && !searchText.includes(q));
  });
}

// Load discovery credentials into the custom dropdown
function loadDiscoveryCredentials(selectedCredentialId = null) {
  fetch('/SNMP/GetCredentials/')
    .then(response => response.json())
    .then(credentials => {
      const optionsList = document.getElementById('discoveryCredentialOptionsList');
      if (!optionsList) return;
      optionsList.innerHTML = '';

      const clearRow = document.createElement('div');
      clearRow.className = 'flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:bg-gray-700 cursor-pointer discovery-credential-option-row';
      clearRow.dataset.searchText = '';
      clearRow.textContent = 'Select a credential...';
      clearRow.onclick = () => selectDiscoveryCredentialOption('', '');
      optionsList.appendChild(clearRow);

      const addRow = document.createElement('div');
      addRow.className = 'flex items-center gap-2 px-3 py-2 text-sm font-bold text-primary hover:bg-gray-700 cursor-pointer discovery-credential-option-row';
      addRow.dataset.searchText = '';
      addRow.textContent = '+ Add Credential';
      addRow.onclick = () => { closeDiscoveryCredentialDropdown(); openCredentialModalFromNetwork(); };
      optionsList.appendChild(addRow);

      credentials.forEach(credential => {
        const displayText = `${credential.name} (SNMPv${credential.version})`;
        const row = document.createElement('div');
        row.className = 'flex items-center gap-2 px-3 py-2 text-sm text-white hover:bg-gray-700 cursor-pointer discovery-credential-option-row';
        row.dataset.searchText = displayText.toLowerCase();
        row.innerHTML = `<span class="truncate">${displayText}</span>`;
        row.onclick = () => selectDiscoveryCredentialOption(credential.id, displayText);
        optionsList.appendChild(row);
        if (selectedCredentialId && credential.id == selectedCredentialId) {
          selectDiscoveryCredentialOption(credential.id, displayText);
        }
      });
    })
    .catch(error => console.error('Error loading discovery credentials:', error));
}

// Refresh discovery credentials dropdown
function refreshDiscoveryCredentials() {
  const currentValue = document.getElementById('discoveryCredentialSelect')?.value || null;
  loadDiscoveryCredentials(currentValue);
}

// ── Trap credential custom dropdown ───────────────────────────────────────────

function selectTrapCredentialOption(id, displayText) {
  const hiddenInput = document.getElementById('networkCredentialSelect');
  const text = document.getElementById('trapCredentialSelectedText');
  hiddenInput.value = id || '';
  if (id) {
    text.textContent = displayText;
    text.classList.remove('text-gray-400');
    text.classList.add('text-white');
  } else {
    text.textContent = 'Select a credential...';
    text.classList.add('text-gray-400');
    text.classList.remove('text-white');
  }
  closeTrapCredentialDropdown();
}

function toggleTrapCredentialDropdown(event) {
  event.stopPropagation();
  const list = document.getElementById('trapCredentialDropdownList');
  if (!list) return;
  const isOpening = list.classList.contains('hidden');
  list.classList.toggle('hidden');
  if (isOpening) {
    const currentVal = document.getElementById('networkCredentialSelect').value || null;
    loadNetworkCredentials(currentVal);
    setTimeout(() => document.getElementById('trapCredentialSearch')?.focus(), 50);
  }
}

function closeTrapCredentialDropdown() {
  const list = document.getElementById('trapCredentialDropdownList');
  if (list) list.classList.add('hidden');
  const search = document.getElementById('trapCredentialSearch');
  if (search) { search.value = ''; filterTrapCredentialDropdown(''); }
}

function filterTrapCredentialDropdown(query) {
  const optionsList = document.getElementById('trapCredentialOptionsList');
  if (!optionsList) return;
  const q = query.toLowerCase();
  optionsList.querySelectorAll('.trap-credential-option-row').forEach(row => {
    const searchText = row.dataset.searchText || '';
    row.classList.toggle('hidden', searchText !== '' && !searchText.includes(q));
  });
}

// Load trap credentials into the custom dropdown
function loadNetworkCredentials(selectedCredentialId = null) {
  fetch('/SNMP/GetCredentials/')
    .then(response => response.json())
    .then(credentials => {
      const optionsList = document.getElementById('trapCredentialOptionsList');
      if (!optionsList) return;
      optionsList.innerHTML = '';

      const clearRow = document.createElement('div');
      clearRow.className = 'flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:bg-gray-700 cursor-pointer trap-credential-option-row';
      clearRow.dataset.searchText = '';
      clearRow.textContent = 'Select a credential...';
      clearRow.onclick = () => selectTrapCredentialOption('', '');
      optionsList.appendChild(clearRow);

      const addRow = document.createElement('div');
      addRow.className = 'flex items-center gap-2 px-3 py-2 text-sm font-bold text-primary hover:bg-gray-700 cursor-pointer trap-credential-option-row';
      addRow.dataset.searchText = '';
      addRow.textContent = '+ Add Credential';
      addRow.onclick = () => { closeTrapCredentialDropdown(); openCredentialModalFromNetwork(); };
      optionsList.appendChild(addRow);

      credentials.forEach(credential => {
        const displayText = `${credential.name} (SNMPv${credential.version})`;
        const row = document.createElement('div');
        row.className = 'flex items-center gap-2 px-3 py-2 text-sm text-white hover:bg-gray-700 cursor-pointer trap-credential-option-row';
        row.dataset.searchText = displayText.toLowerCase();
        row.innerHTML = `<span class="truncate">${displayText}</span>`;
        row.onclick = () => selectTrapCredentialOption(credential.id, displayText);
        optionsList.appendChild(row);
        if (selectedCredentialId && credential.id == selectedCredentialId) {
          selectTrapCredentialOption(credential.id, displayText);
        }
      });
    })
    .catch(error => console.error('Error loading trap credentials:', error));
}

// Refresh trap credentials dropdown
function refreshNetworkCredentials() {
  const currentValue = document.getElementById('networkCredentialSelect')?.value || null;
  loadNetworkCredentials(currentValue);
}

// Open credential modal from network modal
function openCredentialModalFromNetwork() {
  if (typeof openCredentialModal === 'function') {
    openCredentialModal();
  } else {
    console.error('openCredentialModal function not found');
  }
}

// Track if network modal is open
let networkModalIsOpen = false;

// Refresh credential dropdowns when a credential is saved from within this modal
document.addEventListener('credentialSaved', function(e) {
  const networkModal = document.getElementById('networkFormModal');
  if (networkModal && !networkModal.classList.contains('hidden')) {
    loadDiscoveryCredentials(e.detail.id);
    loadNetworkCredentials(e.detail.id);
  }
});

// Close network modal
function closeNetworkModal() {
  networkModalIsOpen = false;
  document.getElementById('networkFormModal').classList.add('hidden');
  document.getElementById('networkForm').reset();
  document.getElementById('networkErrorContainer').innerHTML = '';
  closeConnectionDropdown();
  selectConnectionOption('', '');
  closeDiscoveryCredentialDropdown();
  selectDiscoveryCredentialOption('', '');
  closeTrapCredentialDropdown();
  selectTrapCredentialOption('', '');
}

// Close custom dropdowns when clicking outside
document.addEventListener('click', function (e) {
  if (!e.target.closest('#networkConnectionDropdownWrapper')) {
    closeConnectionDropdown();
  }
  if (!e.target.closest('#discoveryCredentialDropdownWrapper')) {
    closeDiscoveryCredentialDropdown();
  }
  if (!e.target.closest('#trapCredentialDropdownWrapper')) {
    closeTrapCredentialDropdown();
  }
});

// Validate CIDR and show warning for large networks
function validateNetworkSize() {
  const networkRange = document.getElementById('networkRange').value.trim();
  const errorContainer = document.getElementById('networkErrorContainer');

  // Clear any existing warnings
  const existingWarning = errorContainer.querySelector('.warning-message');
  if (existingWarning) {
    existingWarning.remove();
  }

  // Check if input matches CIDR format
  const cidrMatch = networkRange.match(/\/(\d+)$/);
  if (cidrMatch) {
    const prefix = parseInt(cidrMatch[1]);

    // If prefix is less than 24, it's a large network
    if (prefix < 24) {
      const warningDiv = document.createElement('div');
      warningDiv.className = 'warning-message p-4 mb-4 text-yellow-700 bg-yellow-100 border border-yellow-300 rounded-lg';
      warningDiv.innerHTML = `
        <div class="flex items-start">
          <svg class="w-5 h-5 mr-2 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
          </svg>
          <div>
            <h3 class="font-bold mb-1">Woooah, that's a big network!</h3>
            <p class="text-sm">Consider using a /24 or smaller for optimal results.</p>
          </div>
        </div>
      `;
      errorContainer.appendChild(warningDiv);
    }
  }
}

// Add event listener for network range input
document.addEventListener('DOMContentLoaded', function () {
  const networkRangeInput = document.getElementById('networkRange');
  if (networkRangeInput) {
    networkRangeInput.addEventListener('blur', validateNetworkSize);
    networkRangeInput.addEventListener('input', validateNetworkSize);
  }
});

// Handle form submission
document.getElementById('networkForm').addEventListener('submit', function (e) {
  e.preventDefault();

  const errorContainer = document.getElementById('networkErrorContainer');

  // Validate that a connection is selected
  const connectionValue = document.getElementById('networkConnection')?.value;
  if (!connectionValue) {
    errorContainer.innerHTML = `
      <div class="p-4 mb-4 text-red-700 bg-red-100 border border-red-300 rounded-lg">
        <h3 class="font-bold mb-2">Validation Error</h3>
        <p class="text-sm">Please select a connection.</p>
      </div>
    `;
    errorContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    return;
  }

  // Validate that discovery credential is selected if discovery is enabled
  const discoveryEnabled = document.querySelector('input[name="discovery_enabled"]:checked')?.value === 'true';
  const discoveryCredentialValue = document.getElementById('discoveryCredentialSelect')?.value;

  if (discoveryEnabled && !discoveryCredentialValue) {
    errorContainer.innerHTML = `
      <div class="p-4 mb-4 text-red-700 bg-red-100 border border-red-300 rounded-lg">
        <h3 class="font-bold mb-2">Validation Error</h3>
        <p class="text-sm">Please select a credential for device discovery when discovery is enabled.</p>
      </div>
    `;
    errorContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    return;
  }

  // Validate that credential is selected if traps are enabled
  const trapsEnabled = document.querySelector('input[name="traps_enabled"]:checked')?.value === 'true';
  const trapCredentialValue = document.getElementById('networkCredentialSelect')?.value;

  if (trapsEnabled && !trapCredentialValue) {
    errorContainer.innerHTML = `
      <div class="p-4 mb-4 text-red-700 bg-red-100 border border-red-300 rounded-lg">
        <h3 class="font-bold mb-2">Validation Error</h3>
        <p class="text-sm">Please select a credential for SNMP trap reception when traps are enabled.</p>
      </div>
    `;
    errorContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    return;
  }

  const formData = new FormData(this);
  const networkId = document.getElementById('networkId').value;
  const url = networkId ? `/SNMP/UpdateNetwork/${networkId}/` : '/SNMP/AddNetwork/';

  // Get CSRF token
  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

  fetch(url, {
    method: 'POST',
    headers: {
      'X-CSRFToken': csrfToken
    },
    body: formData
  })
    .then(response => {
      if (!response.ok) {
        return response.text().then(text => {
          throw new Error(text || 'Failed to save network');
        });
      }
      return response.json();
    })
    .then(data => {
      const newNetworkId = data.id || data.network_id || null;
      showToast(networkId ? 'Network updated successfully!' : 'Network created successfully!', 'success');
      if (typeof window.triggerUndeployedChangesCheck === 'function') {
        window.triggerUndeployedChangesCheck();
      }
      document.dispatchEvent(new CustomEvent('networkSaved', { detail: { id: newNetworkId } }));
      closeNetworkModal();
      if (typeof refreshNetworksData === 'function') {
        refreshNetworksData();
      }
    })
    .catch(error => {
      const errorContainer = document.getElementById('networkErrorContainer');
      errorContainer.innerHTML = `
      <div class="p-4 mb-4 text-red-700 bg-red-100 border border-red-300 rounded-lg">
        <h3 class="font-bold mb-2">Error</h3>
        <p class="text-sm">${error.message}</p>
      </div>
    `;
      errorContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
});

