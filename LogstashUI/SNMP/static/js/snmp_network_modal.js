// SNMP Network Modal JavaScript

// Open modal for adding new network
const addNetworkBtn = document.getElementById('addNetworkBtn');
if (addNetworkBtn) {
  addNetworkBtn.addEventListener('click', function() {
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
  
  if (networkData) {
    // Edit mode
    modalTitle.textContent = 'Edit SNMP Network';
    document.getElementById('networkId').value = networkData.id;
    document.getElementById('networkName').value = networkData.name;
    document.getElementById('networkRange').value = networkData.network_range;
    document.getElementById('logstashName').value = networkData.logstash_name || '';
    
    // Set discovery enabled radio
    const discoveryValue = networkData.discovery_enabled ? 'true' : 'false';
    document.querySelector(`input[name="discovery_enabled"][value="${discoveryValue}"]`).checked = true;
  } else {
    // Add mode
    modalTitle.textContent = 'Add SNMP Network';
    document.getElementById('networkId').value = '';
    document.querySelector('input[name="discovery_enabled"][value="true"]').checked = true;
  }
  
  modal.classList.remove('hidden');
}

// Load connections into dropdown
function loadConnections(selectedConnectionId = null) {
  const connectionSelect = document.getElementById('networkConnection');
  
  fetch('/API/GetConnections/')
    .then(response => response.json())
    .then(connections => {
      connectionSelect.innerHTML = '<option value="">Select a connection...</option>';
      connectionSelect.innerHTML += '<option value="add_new" class="font-bold text-primary">+ Add Connection</option>';
      
      connections.forEach(connection => {
        const option = document.createElement('option');
        option.value = connection.id;
        option.textContent = `${connection.name} (${connection.connection_type})`;
        if (selectedConnectionId && connection.id == selectedConnectionId) {
          option.selected = true;
        }
        connectionSelect.appendChild(option);
      });
    })
    .catch(error => {
      console.error('Error loading connections:', error);
    });
}

// Handle connection selection change
function handleNetworkConnectionSelection(event) {
  if (event.target.value === 'add_new') {
    // Open connection modal
    openConnectionModalFromNetwork();
    // Reset selection to empty
    event.target.value = '';
  }
}

// Open connection modal from network modal
function openConnectionModalFromNetwork() {
  // Check if openFlyout function exists (from connection modal)
  if (typeof openFlyout === 'function') {
    openFlyout();
  } else {
    console.error('openFlyout function not found');
  }
}

// Refresh connections dropdown
function refreshConnections() {
  const connectionSelect = document.getElementById('networkConnection');
  const currentValue = connectionSelect ? connectionSelect.value : null;
  loadConnections(currentValue);
}

// Track if network modal is open
let networkModalIsOpen = false;

// Store original closeFlyout function
let originalCloseFlyoutForNetwork = null;

// Override closeFlyout to keep network modal open
if (typeof closeFlyout !== 'undefined') {
  originalCloseFlyoutForNetwork = closeFlyout;
}

window.closeFlyout = function() {
  const connectionModal = document.getElementById('connectionFormFlyout');
  const networkModal = document.getElementById('networkFormModal');
  const wasNetworkModalOpen = networkModalIsOpen;
  
  // Close connection modal
  if (connectionModal) {
    connectionModal.classList.add('hidden');
  }
  
  // Call original close function if it exists
  if (originalCloseFlyoutForNetwork && typeof originalCloseFlyoutForNetwork === 'function') {
    originalCloseFlyoutForNetwork();
  }
  
  // If network modal was open, reopen it and refresh connections
  if (wasNetworkModalOpen) {
    networkModal.classList.remove('hidden');
    loadConnections(window.lastCreatedConnectionId);
    window.lastCreatedConnectionId = null;
  }
};

// Close network modal
function closeNetworkModal() {
  networkModalIsOpen = false;
  document.getElementById('networkFormModal').classList.add('hidden');
  document.getElementById('networkForm').reset();
  document.getElementById('networkErrorContainer').innerHTML = '';
}

// Add event listeners for connection selection
document.addEventListener('DOMContentLoaded', function() {
  const connectionSelect = document.getElementById('networkConnection');
  if (connectionSelect) {
    connectionSelect.addEventListener('change', handleNetworkConnectionSelection);
    // Refresh dropdown when clicked/focused, preserving current selection
    connectionSelect.addEventListener('focus', function() {
      const currentValue = this.value;
      loadConnections(currentValue);
    });
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
document.addEventListener('DOMContentLoaded', function() {
  const networkRangeInput = document.getElementById('networkRange');
  if (networkRangeInput) {
    networkRangeInput.addEventListener('blur', validateNetworkSize);
    networkRangeInput.addEventListener('input', validateNetworkSize);
  }
});

// Handle form submission
document.getElementById('networkForm').addEventListener('submit', function(e) {
  e.preventDefault();
  
  const formData = new FormData(this);
  const networkId = document.getElementById('networkId').value;
  const url = networkId ? `/API/SNMP/UpdateNetwork/${networkId}/` : '/API/SNMP/AddNetwork/';
  
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
    // Get the new network ID from response
    const newNetworkId = data.id || data.network_id || null;
    
    showToast(networkId ? 'Network updated successfully!' : 'Network created successfully!', 'success');
    
    // Check if device modal is open (called from device modal)
    const deviceModal = document.getElementById('deviceFormModal');
    const isCalledFromDeviceModal = deviceModal && !deviceModal.classList.contains('hidden');
    
    if (isCalledFromDeviceModal) {
      // Store the new network ID for device modal to use (if we got one)
      if (newNetworkId) {
        window.lastCreatedNetworkId = newNetworkId;
      }
      closeNetworkModal();
      // Don't reload - let device modal handle the refresh
    } else {
      closeNetworkModal();
      // Reload page to show updated networks
      setTimeout(() => {
        window.location.reload();
      }, 500);
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
