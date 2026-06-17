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
    document.getElementById('deviceIpAddress').value = deviceData.ip_address || '';
    document.getElementById('devicePort').value = deviceData.port || 161;
    document.getElementById('deviceRetries').value = deviceData.retries !== undefined ? deviceData.retries : 2;
    document.getElementById('deviceTimeout').value = deviceData.timeout || 1000;

    // Device template, credential, and network will be loaded in the dropdowns
  } else {
    // Add mode - completely new device
    modalTitle.textContent = 'Add SNMP Device';
    document.getElementById('deviceForm').reset();
    document.getElementById('devicePort').value = 161;
    document.getElementById('deviceRetries').value = 2;
    document.getElementById('deviceTimeout').value = 1000;
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
}

// Apply a selection to the custom credential dropdown
function selectCredentialOption(id, displayText) {
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

  closeCredentialDropdown();
}

function toggleCredentialDropdown(event) {
  event.stopPropagation();
  const list = document.getElementById('deviceCredentialDropdownList');
  if (!list) return;
  list.classList.toggle('hidden');
  if (!list.classList.contains('hidden')) {
    const searchInput = document.getElementById('deviceCredentialSearch');
    if (searchInput) setTimeout(() => searchInput.focus(), 50);
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
      addRow.dataset.searchText = 'add credential';
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
          selectCredentialOption(credential.id, displayText);
        }
      });
    })
    .catch(error => {
      console.error('Error loading credentials:', error);
    });
}

// Apply a selection to the custom network dropdown
function selectNetworkOption(id, displayText) {
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

  closeNetworkDropdown();
}

function toggleNetworkDropdown(event) {
  event.stopPropagation();
  const list = document.getElementById('deviceNetworkDropdownList');
  if (!list) return;
  list.classList.toggle('hidden');
  if (!list.classList.contains('hidden')) {
    const searchInput = document.getElementById('deviceNetworkSearch');
    if (searchInput) setTimeout(() => searchInput.focus(), 50);
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
      addRow.dataset.searchText = 'add network';
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
          selectNetworkOption(network.id, displayText);
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

// Apply a selection to the custom template dropdown
function selectTemplateOption(id, displayName, vendor) {
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

  closeTemplateDropdown();
}

// Open / close the custom template dropdown
function toggleTemplateDropdown(event) {
  event.stopPropagation();
  const list = document.getElementById('deviceTemplateDropdownList');
  if (!list) return;
  list.classList.toggle('hidden');
  if (!list.classList.contains('hidden')) {
    const searchInput = document.getElementById('deviceTemplateSearch');
    if (searchInput) setTimeout(() => searchInput.focus(), 50);
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
          selectTemplateOption(template.id, displayName, template.vendor);
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
});

// Track if device modal is open to prevent it from closing
let deviceModalIsOpen = false;
window.lastCreatedCredentialId = null;
window.lastCreatedNetworkId = null;

// Override closeCredentialModal to refresh credentials dropdown in device modal
const originalCloseCredentialModalForDevice = window.closeCredentialModal;
window.closeCredentialModal = function () {
  const deviceModal = document.getElementById('deviceFormModal');
  const wasDeviceModalOpen = deviceModal && !deviceModal.classList.contains('hidden');

  if (originalCloseCredentialModalForDevice) {
    originalCloseCredentialModalForDevice();
  }

  // If device modal was open, reopen it and refresh credentials
  if (wasDeviceModalOpen) {
    deviceModal.classList.remove('hidden');
    loadCredentialsForDevice(window.lastCreatedCredentialId);
    window.lastCreatedCredentialId = null;
  }
};

// Override closeNetworkModal to refresh networks dropdown in device modal
const originalCloseNetworkModalForDevice = window.closeNetworkModal;
window.closeNetworkModal = function () {
  const deviceModal = document.getElementById('deviceFormModal');
  const wasDeviceModalOpen = deviceModal && !deviceModal.classList.contains('hidden');

  if (originalCloseNetworkModalForDevice) {
    originalCloseNetworkModalForDevice();
  }

  // If device modal was open, reopen it and refresh networks
  if (wasDeviceModalOpen) {
    deviceModal.classList.remove('hidden');
    loadNetworksForDevice(window.lastCreatedNetworkId);
    window.lastCreatedNetworkId = null;
  }
};

// Handle form submission
const deviceForm = document.getElementById('deviceForm');
if (deviceForm) {
  deviceForm.addEventListener('submit', function (e) {
    e.preventDefault();

    const formData = new FormData(this);
    const deviceId = document.getElementById('deviceId').value;
    const url = deviceId ? `/SNMP/UpdateDevice/${deviceId}/` : '/SNMP/AddDevice/';

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