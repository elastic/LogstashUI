/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// SNMP Devices Modal JavaScript

// Open modal for adding new device
document.addEventListener('DOMContentLoaded', function () {
  const addDeviceBtn = document.getElementById('addDeviceBtn');
  if (addDeviceBtn) {
    addDeviceBtn.addEventListener('click', function () {
      openDeviceModal();
    });
  }
});

// Open device modal (for add or edit)
function openDeviceModal(deviceData = null) {
  const modal = document.getElementById('deviceFormModal');
  const form = document.getElementById('deviceForm');
  const modalTitle = document.getElementById('modalTitle');

  deviceModalIsOpen = true;

  // Load location suggestions fresh each time the modal opens
  loadLocationData();

  // Reset form
  form.reset();
  document.getElementById('deviceErrorContainer').innerHTML = '';

  if (deviceData) {
    // Check if this is edit mode (has ID) or clone/add mode (no ID)
    const isEditMode = deviceData.id !== undefined;
    
    if (isEditMode) {
      // Edit mode - existing device
      modalTitle.textContent = 'Edit SNMP Device';
      document.getElementById('deviceId').value = deviceData.id;
    } else {
      // Clone/Add mode - has data but no ID
      modalTitle.textContent = 'Add SNMP Device';
      document.getElementById('deviceId').value = '';
    }
    
    // Fill in the form fields
    document.getElementById('deviceName').value = deviceData.name || '';
    document.getElementById('deviceHostname').value = deviceData.hostname || '';
    document.getElementById('deviceIpAddress').value = deviceData.ip_address || '';
    document.getElementById('devicePort').value = deviceData.port || 161;
    document.getElementById('deviceRetries').value = deviceData.retries !== undefined ? deviceData.retries : 2;
    document.getElementById('deviceTimeout').value = deviceData.timeout || 1000;

    // Location fields — populate all three before updating enabled state
    document.getElementById('deviceSite').value = deviceData.site || '';
    document.getElementById('deviceBuilding').value = deviceData.building || '';
    document.getElementById('deviceRoom').value = deviceData.room || '';
    document.getElementById('deviceLatitude').value = deviceData.latitude !== null && deviceData.latitude !== undefined ? deviceData.latitude : '';
    document.getElementById('deviceLongitude').value = deviceData.longitude !== null && deviceData.longitude !== undefined ? deviceData.longitude : '';
    updateLocationFieldStates();

    // Metadata key-value rows
    populateMetadataRows(deviceData.metadata || {});

    // Device template, credential, and network will be loaded in the dropdowns
  } else {
    // Add mode - completely new device
    modalTitle.textContent = 'Add SNMP Device';
    document.getElementById('deviceForm').reset();
    document.getElementById('devicePort').value = 161;
    document.getElementById('deviceRetries').value = 2;
    document.getElementById('deviceTimeout').value = 1000;
    clearMetadataRows();
  }

  // Load credentials, networks, and device templates into dropdowns
  loadCredentialsForDevice(deviceData ? deviceData.credential : null);
  loadNetworksForDevice(deviceData ? deviceData.network : null);
  loadDeviceTemplatesForDevice(deviceData ? deviceData.device_template : null);

  modal.classList.remove('hidden');
}

// Close device modal
function closeDeviceModal() {
  deviceModalIsOpen = false;
  document.getElementById('deviceFormModal').classList.add('hidden');
  document.getElementById('deviceForm').reset();
  document.getElementById('deviceErrorContainer').innerHTML = '';
  closeTemplateDropdown();
  selectTemplateOption('', '', '');
  closeCredentialDropdown();
  selectCredentialOption('', '');
  closeNetworkDropdown();
  selectNetworkOption('', '');
  clearMetadataRows();
  closeAllLocationDropdowns();
  updateLocationFieldStates();
}

function _setCredentialValue(id, displayText) {
  const hiddenInput = document.getElementById('deviceCredentialSelect');
  const text = document.getElementById('deviceCredentialSelectedText');
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
}

// Apply a selection to the custom credential dropdown
function selectCredentialOption(id, displayText) {
  _setCredentialValue(id, displayText);
  closeCredentialDropdown();
}

function toggleCredentialDropdown(event) {
  event.stopPropagation();
  const list = document.getElementById('deviceCredentialDropdownList');
  if (!list) return;
  const isOpening = list.classList.contains('hidden');
  list.classList.toggle('hidden');
  if (isOpening) {
    const currentVal = document.getElementById('deviceCredentialSelect').value || null;
    loadCredentialsForDevice(currentVal);
    setTimeout(() => document.getElementById('deviceCredentialSearch')?.focus(), 50);
  }
}

function closeCredentialDropdown() {
  const list = document.getElementById('deviceCredentialDropdownList');
  if (list) list.classList.add('hidden');
  const searchInput = document.getElementById('deviceCredentialSearch');
  if (searchInput) {
    searchInput.value = '';
    filterCredentialDropdown('');
  }
}

function filterCredentialDropdown(query) {
  const optionsList = document.getElementById('deviceCredentialOptionsList');
  if (!optionsList) return;
  const q = query.toLowerCase();
  optionsList.querySelectorAll('.credential-option-row').forEach(row => {
    const searchText = row.dataset.searchText || '';
    row.classList.toggle('hidden', searchText !== '' && !searchText.includes(q));
  });
}

// Load credentials into the custom dropdown
function loadCredentialsForDevice(selectedCredentialId = null) {
  fetch('/SNMP/GetCredentials/')
    .then(response => response.json())
    .then(credentials => {
      const optionsList = document.getElementById('deviceCredentialOptionsList');
      if (!optionsList) return;
      optionsList.innerHTML = '';

      // "No selection" row
      const clearRow = document.createElement('div');
      clearRow.className = 'flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:bg-gray-700 cursor-pointer credential-option-row';
      clearRow.dataset.searchText = '';
      clearRow.textContent = 'Select a credential...';
      clearRow.onclick = () => selectCredentialOption('', '');
      optionsList.appendChild(clearRow);

      // "Add Credential" row
      const addRow = document.createElement('div');
      addRow.className = 'flex items-center gap-2 px-3 py-2 text-sm font-bold text-primary hover:bg-gray-700 cursor-pointer credential-option-row';
      addRow.dataset.searchText = '';
      addRow.textContent = '+ Add Credential';
      addRow.onclick = () => { closeCredentialDropdown(); openCredentialModalFromDevice(); };
      optionsList.appendChild(addRow);

      credentials.forEach(credential => {
        const displayText = `${credential.name} (SNMPv${credential.version})`;
        const row = document.createElement('div');
        row.className = 'flex items-center gap-2 px-3 py-2 text-sm text-white hover:bg-gray-700 cursor-pointer credential-option-row';
        row.dataset.searchText = displayText.toLowerCase();
        row.innerHTML = `<span class="truncate">${displayText}</span>`;
        row.onclick = () => selectCredentialOption(credential.id, displayText);
        optionsList.appendChild(row);

        if (selectedCredentialId && credential.id == selectedCredentialId) {
          _setCredentialValue(credential.id, displayText);
        }
      });
    })
    .catch(error => {
      console.error('Error loading credentials:', error);
    });
}

function _setNetworkValue(id, displayText) {
  const hiddenInput = document.getElementById('deviceNetworkSelect');
  const text = document.getElementById('deviceNetworkSelectedText');
  hiddenInput.value = id || '';
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

// Apply a selection to the custom network dropdown
function selectNetworkOption(id, displayText) {
  _setNetworkValue(id, displayText);
  closeNetworkDropdown();
}

function toggleNetworkDropdown(event) {
  event.stopPropagation();
  const list = document.getElementById('deviceNetworkDropdownList');
  if (!list) return;
  const isOpening = list.classList.contains('hidden');
  list.classList.toggle('hidden');
  if (isOpening) {
    const currentVal = document.getElementById('deviceNetworkSelect').value || null;
    loadNetworksForDevice(currentVal);
    setTimeout(() => document.getElementById('deviceNetworkSearch')?.focus(), 50);
  }
}

function closeNetworkDropdown() {
  const list = document.getElementById('deviceNetworkDropdownList');
  if (list) list.classList.add('hidden');
  const searchInput = document.getElementById('deviceNetworkSearch');
  if (searchInput) {
    searchInput.value = '';
    filterNetworkDropdown('');
  }
}

function filterNetworkDropdown(query) {
  const optionsList = document.getElementById('deviceNetworkOptionsList');
  if (!optionsList) return;
  const q = query.toLowerCase();
  optionsList.querySelectorAll('.network-option-row').forEach(row => {
    const searchText = row.dataset.searchText || '';
    row.classList.toggle('hidden', searchText !== '' && !searchText.includes(q));
  });
}

// Load networks into the custom dropdown
function loadNetworksForDevice(selectedNetworkId = null) {
  fetch('/SNMP/GetNetworks/')
    .then(response => response.json())
    .then(networks => {
      const optionsList = document.getElementById('deviceNetworkOptionsList');
      if (!optionsList) return;
      optionsList.innerHTML = '';

      // "No selection" row
      const clearRow = document.createElement('div');
      clearRow.className = 'flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:bg-gray-700 cursor-pointer network-option-row';
      clearRow.dataset.searchText = '';
      clearRow.textContent = 'Select a network...';
      clearRow.onclick = () => selectNetworkOption('', '');
      optionsList.appendChild(clearRow);

      // "Add Network" row
      const addRow = document.createElement('div');
      addRow.className = 'flex items-center gap-2 px-3 py-2 text-sm font-bold text-primary hover:bg-gray-700 cursor-pointer network-option-row';
      addRow.dataset.searchText = '';
      addRow.textContent = '+ Add Network';
      addRow.onclick = () => { closeNetworkDropdown(); openNetworkModalFromDevice(); };
      optionsList.appendChild(addRow);

      networks.forEach(network => {
        const displayText = `${network.name} (${network.network_range})`;
        const row = document.createElement('div');
        row.className = 'flex items-center gap-2 px-3 py-2 text-sm text-white hover:bg-gray-700 cursor-pointer network-option-row';
        row.dataset.searchText = displayText.toLowerCase();
        row.innerHTML = `<span class="truncate">${displayText}</span>`;
        row.onclick = () => selectNetworkOption(network.id, displayText);
        optionsList.appendChild(row);

        if (selectedNetworkId && network.id == selectedNetworkId) {
          _setNetworkValue(network.id, displayText);
        }
      });
    })
    .catch(error => {
      console.error('Error loading networks:', error);
    });
}

// Open credential modal from device modal
function openCredentialModalFromDevice() {
  // Check if openCredentialModal function exists
  if (typeof openCredentialModal === 'function') {
    openCredentialModal();
  } else {
    console.error('openCredentialModal function not found');
  }
}

// Open network modal from device modal
function openNetworkModalFromDevice() {
  // Check if openNetworkModal function exists
  if (typeof openNetworkModal === 'function') {
    openNetworkModal();
  } else {
    console.error('openNetworkModal function not found');
  }
}

// Refresh credentials dropdown
function refreshCredentials() {
  const credentialSelect = document.getElementById('deviceCredentialSelect');
  const currentValue = credentialSelect ? credentialSelect.value : null;
  loadCredentialsForDevice(currentValue);
}

// Refresh networks dropdown
function refreshNetworks() {
  const networkSelect = document.getElementById('deviceNetworkSelect');
  const currentValue = networkSelect ? networkSelect.value : null;
  loadNetworksForDevice(currentValue);
}

// Map vendor name to logo filename (mirrors DeviceTemplates.html logic)
function getVendorLogoFilename(vendor) {
  if (!vendor) return 'unknown.png';
  const v = vendor.toLowerCase();
  if (v === 'cisco') return 'cisco.png';
  if (v === 'dell') return 'dell.png';
  if (v === 'brocade') return 'brocade.png';
  if (v === 'hpe' || v === 'hpe nimble') return 'hpe.png';
  if (v === 'epson') return 'epson.png';
  if (v === 'ubiquiti') return 'ubiquiti.png';
  if (v === 'hp') return 'hp.png';
  if (v === 'mellanox') return 'mellanox.png';
  return 'unknown.png';
}

function _setTemplateValue(id, displayName, vendor) {
  const hiddenInput = document.getElementById('deviceTemplateSelect');
  const img = document.getElementById('deviceTemplateSelectedImg');
  const text = document.getElementById('deviceTemplateSelectedText');
  const wrapper = document.getElementById('deviceTemplateDropdownWrapper');
  const imagesUrl = wrapper ? wrapper.dataset.imagesUrl : '';

  hiddenInput.value = id || '';

  if (id) {
    img.src = imagesUrl + getVendorLogoFilename(vendor);
    img.alt = vendor || '';
    img.classList.remove('hidden');
    text.textContent = displayName;
    text.classList.remove('text-gray-400');
    text.classList.add('text-white');
  } else {
    img.src = '';
    img.classList.add('hidden');
    text.textContent = 'Select a template...';
    text.classList.add('text-gray-400');
    text.classList.remove('text-white');
  }
}

// Apply a selection to the custom template dropdown
function selectTemplateOption(id, displayName, vendor) {
  _setTemplateValue(id, displayName, vendor);
  closeTemplateDropdown();
}

// Open / close the custom template dropdown
function toggleTemplateDropdown(event) {
  event.stopPropagation();
  const list = document.getElementById('deviceTemplateDropdownList');
  if (!list) return;
  const isOpening = list.classList.contains('hidden');
  list.classList.toggle('hidden');
  if (isOpening) {
    const currentVal = document.getElementById('deviceTemplateSelect').value || null;
    loadDeviceTemplatesForDevice(currentVal);
    setTimeout(() => document.getElementById('deviceTemplateSearch')?.focus(), 50);
  }
}

function closeTemplateDropdown() {
  const list = document.getElementById('deviceTemplateDropdownList');
  if (list) list.classList.add('hidden');
  const searchInput = document.getElementById('deviceTemplateSearch');
  if (searchInput) {
    searchInput.value = '';
    filterTemplateDropdown('');
  }
}

// Filter template dropdown rows by substring
function filterTemplateDropdown(query) {
  const optionsList = document.getElementById('deviceTemplateOptionsList');
  if (!optionsList) return;
  const q = query.toLowerCase();
  optionsList.querySelectorAll('.template-option-row').forEach(row => {
    const searchText = row.dataset.searchText || '';
    // The "clear selection" row (empty searchText) always stays visible
    row.classList.toggle('hidden', searchText !== '' && !searchText.includes(q));
  });
}

// Load device templates into the custom dropdown
function loadDeviceTemplatesForDevice(selectedTemplateId = null) {
  const wrapper = document.getElementById('deviceTemplateDropdownWrapper');
  const imagesUrl = wrapper ? wrapper.dataset.imagesUrl : '';

  fetch('/SNMP/GetDeviceTemplates/')
    .then(response => response.json())
    .then(data => {
      const optionsList = document.getElementById('deviceTemplateOptionsList');
      if (!optionsList) return;
      optionsList.innerHTML = '';

      // "No selection" row — searchText left empty so it's always visible
      const clearRow = document.createElement('div');
      clearRow.className = 'flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:bg-gray-700 cursor-pointer template-option-row';
      clearRow.dataset.searchText = '';
      clearRow.textContent = 'Select a template...';
      clearRow.onclick = () => selectTemplateOption('', '', '');
      optionsList.appendChild(clearRow);

      const templates = data.templates || [];
      templates.forEach(template => {
        const logoSrc = imagesUrl + getVendorLogoFilename(template.vendor);
        const displayName = template.display_name || template.name;

        const row = document.createElement('div');
        row.className = 'flex items-center gap-2 px-3 py-2 text-sm text-white hover:bg-gray-700 cursor-pointer template-option-row';
        row.dataset.searchText = `${displayName} ${template.vendor || ''}`.toLowerCase();
        row.innerHTML = `
          <img src="${logoSrc}" alt="${template.vendor || ''}"
               class="w-5 h-5 object-contain flex-shrink-0 rounded bg-white p-0.5">
          <span class="truncate">${displayName}</span>
        `;
        row.onclick = () => selectTemplateOption(template.id, displayName, template.vendor);
        optionsList.appendChild(row);

        if (selectedTemplateId && template.id == selectedTemplateId) {
          _setTemplateValue(template.id, displayName, template.vendor);
        }
      });
    })
    .catch(error => {
      console.error('Error loading device templates:', error);
    });
}

// Refresh device templates dropdown (preserves current selection)
function refreshDeviceTemplates() {
  const currentValue = document.getElementById('deviceTemplateSelect').value;
  loadDeviceTemplatesForDevice(currentValue);
}

// ── Metadata key-value helpers ──────────────────────────────────────────────

function addMetadataRow(key = '', value = '') {
  const container = document.getElementById('deviceMetadataRows');
  if (!container) return;

  const row = document.createElement('div');
  row.className = 'flex gap-2 items-center metadata-row';
  row.innerHTML = `
    <input type="text" placeholder="Key" value="${escapeHtml(key)}"
           class="input input-bordered input-sm flex-1 font-mono meta-key-input">
    <input type="text" placeholder="Value" value="${escapeHtml(value)}"
           class="input input-bordered input-sm flex-1 meta-value-input">
    <button type="button" onclick="this.closest('.metadata-row').remove()"
            class="btn btn-ghost btn-xs text-error">✕</button>
  `;
  container.appendChild(row);
}

function populateMetadataRows(metadata) {
  clearMetadataRows();
  if (metadata && typeof metadata === 'object') {
    Object.entries(metadata).forEach(([k, v]) => addMetadataRow(k, String(v)));
  }
}

function clearMetadataRows() {
  const container = document.getElementById('deviceMetadataRows');
  if (container) container.innerHTML = '';
  const hidden = document.getElementById('deviceMetadataJson');
  if (hidden) hidden.value = '{}';
}

function serializeMetadataToJson() {
  const container = document.getElementById('deviceMetadataRows');
  const hidden = document.getElementById('deviceMetadataJson');
  if (!container || !hidden) return;

  const obj = {};
  container.querySelectorAll('.metadata-row').forEach(row => {
    const key = row.querySelector('.meta-key-input')?.value?.trim();
    const val = row.querySelector('.meta-value-input')?.value ?? '';
    if (key) obj[key] = val;
  });
  hidden.value = JSON.stringify(obj);
}

// Close custom dropdowns when clicking outside
document.addEventListener('click', function (e) {
  if (!e.target.closest('#deviceTemplateDropdownWrapper')) {
    closeTemplateDropdown();
  }
  if (!e.target.closest('#deviceCredentialDropdownWrapper')) {
    closeCredentialDropdown();
  }
  if (!e.target.closest('#deviceNetworkDropdownWrapper')) {
    closeNetworkDropdown();
  }
  if (!e.target.closest('#deviceSiteWrapper')) {
    closeLocationDropdown('deviceSiteDropdown');
  }
  if (!e.target.closest('#deviceBuildingWrapper')) {
    closeLocationDropdown('deviceBuildingDropdown');
  }
  if (!e.target.closest('#deviceRoomWrapper')) {
    closeLocationDropdown('deviceRoomDropdown');
  }
});

// Track if device modal is open
let deviceModalIsOpen = false;

// Refresh credential dropdown when a credential is saved from within this modal
document.addEventListener('credentialSaved', function(e) {
  const deviceModal = document.getElementById('deviceFormModal');
  if (deviceModal && !deviceModal.classList.contains('hidden')) {
    loadCredentialsForDevice(e.detail.id);
  }
});

// Refresh network dropdown when a network is saved from within this modal
document.addEventListener('networkSaved', function(e) {
  const deviceModal = document.getElementById('deviceFormModal');
  if (deviceModal && !deviceModal.classList.contains('hidden')) {
    loadNetworksForDevice(e.detail.id);
  }
});

// Handle form submission
const deviceForm = document.getElementById('deviceForm');
if (deviceForm) {
  deviceForm.addEventListener('submit', function (e) {
    e.preventDefault();

    // Serialize metadata key-value rows into the hidden JSON field before building FormData
    serializeMetadataToJson();

    const formData = new FormData(this);
    const deviceId = document.getElementById('deviceId').value;
    const url = deviceId ? `/SNMP/UpdateDevice/${deviceId}/` : '/SNMP/AddDevice/';

    // Validate at least one identifier is provided
    const hostname = document.getElementById('deviceHostname').value.trim();
    const ipAddress = document.getElementById('deviceIpAddress').value.trim();
    if (!hostname && !ipAddress) {
      const errorContainer = document.getElementById('deviceErrorContainer');
      errorContainer.innerHTML = `
        <div class="p-4 mb-4 text-red-700 bg-red-100 border border-red-300 rounded-lg">
          <h3 class="font-bold mb-2">Validation Error</h3>
          <p class="text-sm">At least one of Hostname or IP Address must be provided.</p>
        </div>
      `;
      errorContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      return;
    }

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
            throw new Error(text || 'Failed to save device');
          });
        }
        return response.text();
      })
      .then(data => {
        showToast(deviceId ? 'Device updated successfully!' : 'Device created successfully!', 'success');
        closeDeviceModal();

        // Trigger check for undeployed changes
        if (typeof window.triggerUndeployedChangesCheck === 'function') {
          window.triggerUndeployedChangesCheck();
        }

        // Reload devices table instead of entire page
        if (typeof window.reloadDevicesTable === 'function') {
          window.reloadDevicesTable();
        } else {
          // Fallback to page reload if table reload function not available
          setTimeout(() => {
            window.location.reload();
          }, 500);
        }
      })
      .catch(error => {
        const errorContainer = document.getElementById('deviceErrorContainer');
        errorContainer.innerHTML = `
      <div class="p-4 mb-4 text-red-700 bg-red-100 border border-red-300 rounded-lg">
        <h3 class="font-bold mb-2">Error</h3>
        <p class="text-sm">${error.message}</p>
      </div>
    `;
        errorContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      });
  });
}

// ── Location combobox system ────────────────────────────────────────────────
//
// All location data is fetched once per modal open and stored in locationData.
// Client-side filtering drives the Site → Building → Room hierarchy.
// When all three match a known record, lat/lon are auto-filled.

let locationData = { sites: [], site_building: [], full: [] };

function loadLocationData() {
  fetch('/SNMP/GetDeviceLocationData/')
    .then(r => r.json())
    .then(data => { locationData = data; })
    .catch(() => { /* silently ignore — comboboxes just won't show suggestions */ });
}

// ── Suggestion derivation ───────────────────────────────────────────────────

function getSiteSuggestions(query) {
  const q = (query || '').toLowerCase();
  return locationData.sites
    .filter(s => !q || s.toLowerCase().includes(q));
}

function getBuildingSuggestions(query) {
  const q = (query || '').toLowerCase();
  const selectedSite = (document.getElementById('deviceSite')?.value || '').trim();
  let pairs = locationData.site_building;
  if (selectedSite) pairs = pairs.filter(p => p.site === selectedSite);
  return [...new Set(pairs.map(p => p.building).filter(Boolean))]
    .filter(b => !q || b.toLowerCase().includes(q))
    .sort();
}

function getRoomSuggestions(query) {
  const q = (query || '').toLowerCase();
  const selectedSite = (document.getElementById('deviceSite')?.value || '').trim();
  const selectedBuilding = (document.getElementById('deviceBuilding')?.value || '').trim();
  let triples = locationData.full;
  if (selectedSite) triples = triples.filter(t => t.site === selectedSite);
  if (selectedBuilding) triples = triples.filter(t => t.building === selectedBuilding);
  return [...new Set(triples.map(t => t.room).filter(Boolean))]
    .filter(r => !q || r.toLowerCase().includes(q))
    .sort();
}

// ── Dropdown rendering ──────────────────────────────────────────────────────

function renderLocationDropdown(dropdownId, suggestions, onSelect) {
  const dropdown = document.getElementById(dropdownId);
  if (!dropdown) return;
  dropdown.innerHTML = '';

  if (!suggestions.length) {
    dropdown.classList.add('hidden');
    return;
  }

  suggestions.forEach(text => {
    const row = document.createElement('div');
    row.className = 'px-3 py-2 text-sm text-white hover:bg-gray-700 cursor-pointer';
    row.textContent = text;
    row.addEventListener('mousedown', (e) => {
      // mousedown fires before blur, preventing the dropdown from closing prematurely
      e.preventDefault();
      onSelect(text);
    });
    dropdown.appendChild(row);
  });

  dropdown.classList.remove('hidden');
}

function closeLocationDropdown(dropdownId) {
  const el = document.getElementById(dropdownId);
  if (el) el.classList.add('hidden');
}

function closeAllLocationDropdowns() {
  closeLocationDropdown('deviceSiteDropdown');
  closeLocationDropdown('deviceBuildingDropdown');
  closeLocationDropdown('deviceRoomDropdown');
}

// ── Auto-fill coordinates ───────────────────────────────────────────────────

function tryAutoFillCoordinates() {
  const site = (document.getElementById('deviceSite')?.value || '').trim();
  const building = (document.getElementById('deviceBuilding')?.value || '').trim();
  const room = (document.getElementById('deviceRoom')?.value || '').trim();
  if (!site || !building || !room) return;

  const match = locationData.full.find(
    t => t.site === site && t.building === building && t.room === room && t.latitude != null
  );
  if (match) {
    document.getElementById('deviceLatitude').value = match.latitude;
    document.getElementById('deviceLongitude').value = match.longitude;
  }
}

// ── Event handlers ──────────────────────────────────────────────────────────

// ── Enable/disable hierarchy enforcement ────────────────────────────────────

function updateLocationFieldStates() {
  const siteVal = (document.getElementById('deviceSite')?.value || '').trim();
  const buildingVal = (document.getElementById('deviceBuilding')?.value || '').trim();

  const buildingInput = document.getElementById('deviceBuilding');
  const roomInput = document.getElementById('deviceRoom');

  if (buildingInput) {
    const buildingEnabled = siteVal.length > 0;
    buildingInput.disabled = !buildingEnabled;
    buildingInput.placeholder = buildingEnabled ? 'e.g., Building A' : 'Select a Site first';
  }

  if (roomInput) {
    const roomEnabled = siteVal.length > 0 && buildingVal.length > 0;
    roomInput.disabled = !roomEnabled;
    roomInput.placeholder = roomEnabled ? 'e.g., Server Room 2 / Rack 4' : 'Select a Building first';
  }
}

// ── Combobox event handlers ─────────────────────────────────────────────────

function onSiteInput(value) {
  updateLocationFieldStates();
  renderLocationDropdown('deviceSiteDropdown', getSiteSuggestions(value), (selected) => {
    document.getElementById('deviceSite').value = selected;
    closeLocationDropdown('deviceSiteDropdown');
    updateLocationFieldStates();
    tryAutoFillCoordinates();
  });
}

function onSiteFocus() {
  const current = document.getElementById('deviceSite')?.value || '';
  renderLocationDropdown('deviceSiteDropdown', getSiteSuggestions(current), (selected) => {
    document.getElementById('deviceSite').value = selected;
    closeLocationDropdown('deviceSiteDropdown');
    updateLocationFieldStates();
    tryAutoFillCoordinates();
  });
}

function onBuildingInput(value) {
  updateLocationFieldStates();
  renderLocationDropdown('deviceBuildingDropdown', getBuildingSuggestions(value), (selected) => {
    document.getElementById('deviceBuilding').value = selected;
    closeLocationDropdown('deviceBuildingDropdown');
    updateLocationFieldStates();
    tryAutoFillCoordinates();
  });
}

function onBuildingFocus() {
  const current = document.getElementById('deviceBuilding')?.value || '';
  renderLocationDropdown('deviceBuildingDropdown', getBuildingSuggestions(current), (selected) => {
    document.getElementById('deviceBuilding').value = selected;
    closeLocationDropdown('deviceBuildingDropdown');
    updateLocationFieldStates();
    tryAutoFillCoordinates();
  });
}

function onRoomInput(value) {
  renderLocationDropdown('deviceRoomDropdown', getRoomSuggestions(value), (selected) => {
    document.getElementById('deviceRoom').value = selected;
    closeLocationDropdown('deviceRoomDropdown');
    tryAutoFillCoordinates();
  });
}

function onRoomFocus() {
  const current = document.getElementById('deviceRoom')?.value || '';
  renderLocationDropdown('deviceRoomDropdown', getRoomSuggestions(current), (selected) => {
    document.getElementById('deviceRoom').value = selected;
    closeLocationDropdown('deviceRoomDropdown');
    tryAutoFillCoordinates();
  });
}

// ── Google Maps lat/lon picker ───────────────────────────────────────────────

function openGmapsModal() {
  const modal = document.getElementById('gmapsLatLonModal');
  if (!modal) return;
  // Reset state
  const urlInput = document.getElementById('gmapsUrlInput');
  if (urlInput) urlInput.value = '';
  document.getElementById('gmapsResult')?.classList.add('hidden');
  document.getElementById('gmapsError')?.classList.add('hidden');
  const applyBtn = document.getElementById('gmapsApplyBtn');
  if (applyBtn) applyBtn.disabled = true;
  modal.classList.remove('hidden');
}

function closeGmapsModal() {
  document.getElementById('gmapsLatLonModal')?.classList.add('hidden');
}

function parseGmapsUrl(url) {
  // Primary: pinned location embedded as !3d<lat>!4d<lon> in the data segment
  const pinMatch = url.match(/!3d(-?\d+\.?\d*)!4d(-?\d+\.?\d*)/);
  if (pinMatch) {
    return { lat: pinMatch[1], lon: pinMatch[2] };
  }

  // Fallback: map centre from the /@<lat>,<lon>, segment
  const centerMatch = url.match('\/@(-?\\d+\\.?\\d*),(-?\\d+\\.?\\d*),');
  if (centerMatch) {
    return { lat: centerMatch[1], lon: centerMatch[2] };
  }

  return null;
}

function onGmapsUrlInput(value) {
  const resultEl = document.getElementById('gmapsResult');
  const errorEl = document.getElementById('gmapsError');
  const applyBtn = document.getElementById('gmapsApplyBtn');
  const latEl = document.getElementById('gmapsResultLat');
  const lonEl = document.getElementById('gmapsResultLon');

  if (!value.trim()) {
    resultEl?.classList.add('hidden');
    errorEl?.classList.add('hidden');
    if (applyBtn) applyBtn.disabled = true;
    return;
  }

  const coords = parseGmapsUrl(value.trim());
  if (coords) {
    if (latEl) latEl.textContent = coords.lat;
    if (lonEl) lonEl.textContent = coords.lon;
    resultEl?.classList.remove('hidden');
    errorEl?.classList.add('hidden');
    if (applyBtn) applyBtn.disabled = false;
  } else {
    resultEl?.classList.add('hidden');
    errorEl?.classList.remove('hidden');
    if (applyBtn) applyBtn.disabled = true;
  }
}

function applyGmapsCoordinates() {
  const lat = document.getElementById('gmapsResultLat')?.textContent;
  const lon = document.getElementById('gmapsResultLon')?.textContent;
  if (!lat || !lon) return;

  const latInput = document.getElementById('deviceLatitude');
  const lonInput = document.getElementById('deviceLongitude');
  if (latInput) latInput.value = lat;
  if (lonInput) lonInput.value = lon;

  closeGmapsModal();
}