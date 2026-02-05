// SNMP Devices Modal JavaScript

// Open modal for adding new device
document.addEventListener('DOMContentLoaded', function() {
  const addDeviceBtn = document.getElementById('addDeviceBtn');
  if (addDeviceBtn) {
    addDeviceBtn.addEventListener('click', function() {
      openDeviceModal();
    });
  }
});

// Open device modal (for add or edit)
function openDeviceModal(deviceData = null) {
  console.log('openDeviceModal called with data:', deviceData);
  const modal = document.getElementById('deviceFormModal');
  console.log('Device modal element:', modal);
  const form = document.getElementById('deviceForm');
  const modalTitle = document.getElementById('modalTitle');
  
  deviceModalIsOpen = true;
  
  // Reset form
  form.reset();
  document.getElementById('deviceErrorContainer').innerHTML = '';
  
  if (deviceData) {
    // Edit mode
    modalTitle.textContent = 'Edit SNMP Device';
    document.getElementById('deviceId').value = deviceData.id;
    document.getElementById('deviceName').value = deviceData.name;
    document.getElementById('deviceIpAddress').value = deviceData.ip_address;
    
    // Set selected profiles BEFORE loading dropdowns
    if (deviceData.profiles && Array.isArray(deviceData.profiles)) {
      selectedProfiles = [...deviceData.profiles];
    } else {
      selectedProfiles = [];
    }
  } else {
    // Add mode
    modalTitle.textContent = 'Add SNMP Device';
    document.getElementById('deviceId').value = '';
    selectedProfiles = [];
  }
  
  // Render selected profiles
  renderSelectedProfiles();
  
  // Load credentials, networks, and profiles into dropdowns
  loadCredentialsForDevice(deviceData ? deviceData.credential : null);
  loadNetworksForDevice(deviceData ? deviceData.network : null);
  loadProfilesForDevice();
  
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
  
  fetch('/API/SNMP/GetCredentials/')
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
  
  fetch('/API/SNMP/GetNetworks/')
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

// Track selected profiles
let selectedProfiles = [];

// Load profiles into dropdown
function loadProfilesForDevice() {
  const profileSelect = document.getElementById('deviceProfilesSelect');
  
  fetch('/API/SNMP/GetAllProfiles/')
    .then(response => response.json())
    .then(data => {
      // Clear existing options
      profileSelect.innerHTML = '<option value="">Select a profile to add...</option>';
      
      // Add profiles to dropdown (exclude already selected ones)
      data.profiles.forEach(profile => {
        if (!selectedProfiles.includes(profile.name)) {
          const option = document.createElement('option');
          option.value = profile.name;
          option.textContent = profile.display_name;
          profileSelect.appendChild(option);
        }
      });
    })
    .catch(error => {
      console.error('Error loading profiles:', error);
    });
}

// Refresh profiles dropdown
function refreshProfiles() {
  loadProfilesForDevice();
}

// Add profile when selected from dropdown
document.addEventListener('DOMContentLoaded', function() {
  const profileSelect = document.getElementById('deviceProfilesSelect');
  if (profileSelect) {
    profileSelect.addEventListener('change', function() {
      const selectedProfile = this.value;
      if (selectedProfile && !selectedProfiles.includes(selectedProfile)) {
        selectedProfiles.push(selectedProfile);
        renderSelectedProfiles();
        loadProfilesForDevice(); // Refresh dropdown to remove selected profile
      }
      this.value = ''; // Reset dropdown
    });
  }
});

// Render selected profiles as pills
function renderSelectedProfiles() {
  const container = document.getElementById('selectedProfilesContainer');
  container.innerHTML = '';
  
  selectedProfiles.forEach(profileName => {
    const pill = document.createElement('div');
    pill.className = 'inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-blue-600 text-white';
    pill.innerHTML = `
      <span>${profileName.replace('_', ' ')}</span>
      <button type="button" onclick="removeProfile('${profileName}')" class="ml-2 inline-flex items-center justify-center w-4 h-4 rounded-full hover:bg-blue-700 focus:outline-none">
        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    `;
    container.appendChild(pill);
  });
}

// Remove profile from selection
function removeProfile(profileName) {
  selectedProfiles = selectedProfiles.filter(p => p !== profileName);
  renderSelectedProfiles();
  loadProfilesForDevice(); // Refresh dropdown to add profile back
}

// Track if device modal is open to prevent it from closing
let deviceModalIsOpen = false;
window.lastCreatedCredentialId = null;
window.lastCreatedNetworkId = null;

// Override closeCredentialModal to refresh credentials dropdown in device modal
const originalCloseCredentialModalForDevice = window.closeCredentialModal;
window.closeCredentialModal = function() {
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
window.closeNetworkModal = function() {
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
document.addEventListener('DOMContentLoaded', function() {
  const credentialSelect = document.getElementById('deviceCredentialSelect');
  if (credentialSelect) {
    credentialSelect.addEventListener('change', handleDeviceCredentialSelection);
    // Refresh dropdown when clicked/focused, preserving current selection
    credentialSelect.addEventListener('focus', function() {
      const currentValue = this.value;
      loadCredentialsForDevice(currentValue);
    });
  }
  
  const networkSelect = document.getElementById('deviceNetworkSelect');
  if (networkSelect) {
    networkSelect.addEventListener('change', handleDeviceNetworkSelection);
    // Refresh dropdown when clicked/focused, preserving current selection
    networkSelect.addEventListener('focus', function() {
      const currentValue = this.value;
      loadNetworksForDevice(currentValue);
    });
  }
});

// Handle form submission
const deviceForm = document.getElementById('deviceForm');
if (deviceForm) {
  deviceForm.addEventListener('submit', function(e) {
  e.preventDefault();
  
  const formData = new FormData(this);
  const deviceId = document.getElementById('deviceId').value;
  const url = deviceId ? `/API/SNMP/UpdateDevice/${deviceId}/` : '/API/SNMP/AddDevice/';
  
  // Add selected profiles to form data
  selectedProfiles.forEach(profile => {
    formData.append('profiles', profile);
  });
  
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

// Toast notification function
function showToast(message, type = 'success') {
  const container = document.getElementById('toast-container') || createToastContainer();
  const toast = document.createElement('div');
  const colors = {
    success: 'bg-green-500',
    error: 'bg-red-500',
    info: 'bg-blue-500',
    warning: 'bg-yellow-500'
  };

  toast.className = `${colors[type] || 'bg-gray-800'} text-white px-6 py-3 rounded-lg shadow-lg flex items-center justify-between min-w-[300px]`;
  toast.innerHTML = `
    <span>${message}</span>
    <button onclick="this.parentElement.remove()" class="text-white hover:text-gray-200 ml-4">
      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
      </svg>
    </button>
  `;

  container.appendChild(toast);

  // Auto-remove after 5 seconds
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 5000);
}

function createToastContainer() {
  const container = document.createElement('div');
  container.id = 'toast-container';
  container.className = 'fixed top-4 right-4 z-50 flex flex-col gap-2';
  document.body.appendChild(container);
  return container;
}
