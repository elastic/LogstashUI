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
}

// Load credentials into dropdown
function loadCredentialsForDevice(selectedCredentialId = null) {
  const credentialSelect = document.getElementById('deviceCredentialSelect');

  fetch('/SNMP/GetCredentials/')
    .then(response => response.json())
    .then(credentials => {
      // Clear existing options except the first two (placeholder and "Add Credential")
      credentialSelect.innerHTML = `
        <option value="">Select a credential...</option>
        <option value="add_new" class="font-bold text-primary">+ Add Credential</option>
      `;

      // Add credentials to dropdown
      credentials.forEach(credential => {
        const option = document.createElement('option');
        option.value = credential.id;
        option.textContent = `${credential.name} (SNMPv${credential.version})`;
        if (selectedCredentialId && credential.id == selectedCredentialId) {
          option.selected = true;
        }
        credentialSelect.appendChild(option);
      });
    })
    .catch(error => {
      console.error('Error loading credentials:', error);
    });
}

// Load networks into dropdown
function loadNetworksForDevice(selectedNetworkId = null) {
  const networkSelect = document.getElementById('deviceNetworkSelect');

  fetch('/SNMP/GetNetworks/')
    .then(response => response.json())
    .then(networks => {
      // Clear existing options except the first two (placeholder and "Add Network")
      networkSelect.innerHTML = `
        <option value="">Select a network...</option>
        <option value="add_new" class="font-bold text-primary">+ Add Network</option>
      `;

      // Add networks to dropdown
      networks.forEach(network => {
        const option = document.createElement('option');
        option.value = network.id;
        option.textContent = `${network.name} (${network.network_range})`;
        if (selectedNetworkId && network.id == selectedNetworkId) {
          option.selected = true;
        }
        networkSelect.appendChild(option);
      });
    })
    .catch(error => {
      console.error('Error loading networks:', error);
    });
}

// Handle credential selection change
function handleDeviceCredentialSelection(event) {
  if (event.target.value === 'add_new') {
    // Open credential modal
    openCredentialModalFromDevice();
    // Reset selection to empty
    event.target.value = '';
  }
}

// Handle network selection change
function handleDeviceNetworkSelection(event) {
  if (event.target.value === 'add_new') {
    // Open network modal
    openNetworkModalFromDevice();
    // Reset selection to empty
    event.target.value = '';
  }
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

// Load device templates into dropdown
function loadDeviceTemplatesForDevice(selectedTemplateId = null) {
  const templateSelect = document.getElementById('deviceTemplateSelect');

  fetch('/SNMP/GetDeviceTemplates/')
    .then(response => response.json())
    .then(data => {
      // Clear existing options except placeholder
      templateSelect.innerHTML = '<option value="">Select a template...</option>';

      // Add templates to dropdown
      const templates = data.templates || [];
      templates.forEach(template => {
        const option = document.createElement('option');
        option.value = template.id;
        option.textContent = template.name;
        if (selectedTemplateId && template.id == selectedTemplateId) {
          option.selected = true;
        }
        templateSelect.appendChild(option);
      });
    })
    .catch(error => {
      console.error('Error loading device templates:', error);
    });
}

// Refresh device templates dropdown
function refreshDeviceTemplates() {
  const currentValue = document.getElementById('deviceTemplateSelect').value;
  loadDeviceTemplatesForDevice(currentValue);
}

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

// Add event listeners for credential and network selection
document.addEventListener('DOMContentLoaded', function () {
  const credentialSelect = document.getElementById('deviceCredentialSelect');
  if (credentialSelect) {
    credentialSelect.addEventListener('change', handleDeviceCredentialSelection);
    // Refresh dropdown when clicked/focused, preserving current selection
    credentialSelect.addEventListener('focus', function () {
      const currentValue = this.value;
      loadCredentialsForDevice(currentValue);
    });
  }

  const networkSelect = document.getElementById('deviceNetworkSelect');
  if (networkSelect) {
    networkSelect.addEventListener('change', handleDeviceNetworkSelection);
    // Refresh dropdown when clicked/focused, preserving current selection
    networkSelect.addEventListener('focus', function () {
      const currentValue = this.value;
      loadNetworksForDevice(currentValue);
    });
  }
});

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