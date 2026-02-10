// Devices Table - Pagination, Search, Filter, and Sort
let currentPage = 1;
let pageSize = 25;
let currentSearch = '';
let currentNetworkFilter = '';
let currentSort = '-created_at';

// Load devices with current filters
function loadDevices() {
  const loadingState = document.getElementById('loadingState');
  const tableBody = document.getElementById('devicesTableBody');
  const emptyState = document.getElementById('emptyState');
  const tableContainer = document.getElementById('devicesTableContainer');
  
  // Show loading state
  loadingState.classList.remove('hidden');
  tableBody.innerHTML = '';
  
  // Build query parameters
  const params = new URLSearchParams({
    page: currentPage,
    page_size: pageSize,
    sort_by: currentSort
  });
  
  if (currentSearch) {
    params.append('search', currentSearch);
  }
  
  if (currentNetworkFilter) {
    params.append('network', currentNetworkFilter);
  }
  
  // Fetch devices
  fetch(`/API/SNMP/GetDevices/?${params.toString()}`)
    .then(response => response.json())
    .then(data => {
      loadingState.classList.add('hidden');
      const noResultsState = document.getElementById('noResultsState');
      const initialEmptyState = document.getElementById('initialEmptyState');
      const mainContent = document.getElementById('mainContent');
      
      // Check if empty
      if (data.total === 0) {
        // Determine if this is truly empty or just no results from search/filter
        const hasActiveFilters = currentSearch || currentNetworkFilter;
        
        if (hasActiveFilters) {
          // Show "no results" state within main content
          mainContent.classList.remove('hidden');
          initialEmptyState.classList.add('hidden');
          noResultsState.classList.remove('hidden');
          emptyState.classList.add('hidden');
          tableContainer.classList.add('hidden');
          document.getElementById('paginationControls').classList.add('hidden');
        } else {
          // Show centered "get started" empty state and hide main content
          initialEmptyState.classList.remove('hidden');
          mainContent.classList.add('hidden');
        }
        
        return;
      }
      
      // Hide initial empty state and show main content with table
      initialEmptyState.classList.add('hidden');
      mainContent.classList.remove('hidden');
      emptyState.classList.add('hidden');
      noResultsState.classList.add('hidden');
      tableContainer.classList.remove('hidden');
      document.getElementById('paginationControls').classList.remove('hidden');
      
      // Populate table
      renderDevices(data.devices);
      
      // Update pagination info
      updatePaginationControls(data);
    })
    .catch(error => {
      console.error('Error loading devices:', error);
      loadingState.classList.add('hidden');
      tableBody.innerHTML = `
        <tr>
          <td colspan="6" class="px-6 py-8 text-center text-red-400">
            Error loading devices: ${error.message}
          </td>
        </tr>
      `;
    });
}

// Render devices in table
function renderDevices(devices) {
  const tableBody = document.getElementById('devicesTableBody');
  tableBody.innerHTML = '';
  
  devices.forEach(device => {
    const row = document.createElement('tr');
    row.className = 'hover:bg-gray-700/50 transition-colors';
    row.id = `device-row-${device.id}`;
    
    const createdDate = new Date(device.created_at).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
    
    // Render profile pills
    let profilesHtml = '';
    if (device.profiles && device.profiles.length > 0) {
      profilesHtml = device.profiles.map(profile => 
        `<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800 mr-1 mb-1">${escapeHtml(profile)}</span>`
      ).join('');
    } else {
      profilesHtml = '<span class="text-gray-500 italic">None</span>';
    }
    
    row.innerHTML = `
      <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
        <div class="flex items-center gap-2">
          <button class="expand-button p-1 hover:bg-gray-700 rounded transition-transform" onclick="toggleDevicePreview(${device.id})">
            <svg class="w-5 h-5 transform transition-transform duration-200" id="chevron-${device.id}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          <div class="w-3 h-3 rounded-full bg-gray-500" id="status-circle-${device.id}" title="Device status"></div>
        </div>
      </td>
      <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-white">${escapeHtml(device.name)}</td>
      <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
        <span class="font-mono">${escapeHtml(device.ip_address)}</span>
      </td>
      <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
        ${device.credential_name ? escapeHtml(device.credential_name) : '<span class="text-gray-500 italic">None</span>'}
      </td>
      <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
        ${device.network_name ? `
          <div class="flex items-center gap-2 ${device.network_id ? 'cursor-pointer hover:text-blue-400 group' : ''}" ${device.network_id ? `onclick="copyPipelineName(${device.network_id}, '${escapeHtml(device.network_name)}')"` : ''} title="${device.network_id ? 'Click to copy pipeline name' : ''}">
            <span>${escapeHtml(device.network_name)}</span>
            ${device.network_id ? `
              <svg class="w-4 h-4 text-gray-400 group-hover:text-blue-400 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
            ` : ''}
          </div>
        ` : '<span class="text-gray-500 italic">None</span>'}
      </td>
      <td class="px-6 py-4 text-sm text-gray-300">
        <div class="flex flex-wrap">${profilesHtml}</div>
      </td>
      <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${createdDate}</td>
      <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
        <div class="action-menu relative">
          <button class="action-menu-button p-1 hover:bg-gray-700 rounded">
            <svg class="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
              <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
            </svg>
          </button>
          <div class="action-menu-items hidden fixed z-50 w-32 bg-gray-800 rounded-md shadow-lg py-1" role="menu">
            <div class="px-1 py-1">
              <button onclick="editDevice(${device.id})" class="group flex items-center w-full px-4 py-2 text-sm text-gray-300 hover:bg-gray-700 rounded-md" role="menuitem">
                <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
                Edit
              </button>
              <button onclick="deleteDevice(${device.id}, '${escapeHtml(device.name)}')" class="group flex items-center w-full px-4 py-2 text-sm text-red-400 hover:bg-gray-700 rounded-md" role="menuitem">
                <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
                Delete
              </button>
            </div>
          </div>
        </div>
      </td>
    `;
    
    tableBody.appendChild(row);
    
    // Add expandable row for device preview
    const expandRow = document.createElement('tr');
    expandRow.id = `device-preview-${device.id}`;
    expandRow.className = 'hidden bg-gray-900';
    expandRow.innerHTML = `
      <td colspan="8">
        <div class="p-4">
          <div class="htmx-indicator">
            <div class="flex justify-center items-center py-4">
              <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
            </div>
          </div>
          <div id="device-preview-content-${device.id}"></div>
        </div>
      </td>
    `;
    
    tableBody.appendChild(expandRow);
  });
}

// Update pagination controls
function updatePaginationControls(data) {
  const showingStart = (data.page - 1) * data.page_size + 1;
  const showingEnd = Math.min(data.page * data.page_size, data.total);
  
  document.getElementById('showingStart').textContent = data.total > 0 ? showingStart : 0;
  document.getElementById('showingEnd').textContent = showingEnd;
  document.getElementById('totalDevices').textContent = data.total;
  document.getElementById('pageInfo').textContent = `Page ${data.page} of ${data.total_pages}`;
  
  document.getElementById('prevPageBtn').disabled = !data.has_previous;
  document.getElementById('nextPageBtn').disabled = !data.has_next;
}

// Pagination functions
function nextPage() {
  currentPage++;
  loadDevices();
}

function previousPage() {
  if (currentPage > 1) {
    currentPage--;
    loadDevices();
  }
}

// Sort table
function sortTable(field) {
  // Toggle sort direction
  if (currentSort === field) {
    currentSort = '-' + field;
  } else if (currentSort === '-' + field) {
    currentSort = field;
  } else {
    currentSort = '-' + field;
  }
  
  // Update sort indicators
  document.querySelectorAll('[id^="sort-"]').forEach(el => {
    el.textContent = '';
  });
  
  const indicator = document.getElementById('sort-' + field);
  if (indicator) {
    indicator.textContent = currentSort.startsWith('-') ? '▼' : '▲';
  }
  
  currentPage = 1;
  loadDevices();
}

// Delete device
function deleteDevice(deviceId, deviceName) {
  if (!confirm(`Are you sure you want to delete device "${deviceName}"?`)) {
    return;
  }
  
  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
  
  fetch(`/API/SNMP/DeleteDevice/${deviceId}/`, {
    method: 'POST',
    headers: {
      'X-CSRFToken': csrfToken
    }
  })
  .then(response => {
    if (response.ok) {
      showToast('Device deleted successfully!', 'success');
      loadDevices();
    } else {
      throw new Error('Failed to delete device');
    }
  })
  .catch(error => {
    showToast('Error deleting device: ' + error.message, 'error');
  });
}

// Edit device (defined in snmp_devices_modal.js)
function editDevice(deviceId) {
  fetch(`/API/SNMP/GetDevice/${deviceId}/`)
    .then(response => response.json())
    .then(data => {
      openDeviceModal(data);
    })
    .catch(error => {
      showToast('Error loading device: ' + error.message, 'error');
    });
}

// Load networks for filter dropdown
function loadNetworkFilter() {
  fetch('/API/SNMP/GetNetworks/')
    .then(response => response.json())
    .then(networks => {
      const filterSelect = document.getElementById('networkFilter');
      filterSelect.innerHTML = '<option value="">All Networks</option>';
      
      networks.forEach(network => {
        const option = document.createElement('option');
        option.value = network.id;
        option.textContent = network.name;
        filterSelect.appendChild(option);
      });
    })
    .catch(error => {
      console.error('Error loading networks for filter:', error);
    });
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
  // Load initial data
  loadDevices();
  loadNetworkFilter();
  
  // Search input with debounce
  let searchTimeout;
  document.getElementById('searchInput').addEventListener('input', function(e) {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      currentSearch = e.target.value;
      currentPage = 1;
      loadDevices();
    }, 500);
  });
  
  // Network filter
  document.getElementById('networkFilter').addEventListener('change', function(e) {
    currentNetworkFilter = e.target.value;
    currentPage = 1;
    loadDevices();
  });
  
  // Page size selector
  document.getElementById('pageSizeSelect').addEventListener('change', function(e) {
    pageSize = parseInt(e.target.value);
    currentPage = 1;
    loadDevices();
  });
  
  // Action menu handlers using event delegation (only attach once)
  document.addEventListener('click', function(e) {
    const actionButton = e.target.closest('.action-menu-button');
    
    if (actionButton) {
      e.stopPropagation();
      const menu = actionButton.nextElementSibling;
      const isHidden = menu.classList.contains('hidden');
      
      // Close all other open menus
      document.querySelectorAll('.action-menu-items').forEach(m => {
        if (m !== menu) m.classList.add('hidden');
      });
      
      // Position the menu at the cursor
      if (isHidden) {
        menu.style.left = `${e.clientX}px`;
        menu.style.top = `${e.clientY}px`;
      }
      
      // Toggle current menu
      menu.classList.toggle('hidden', !isHidden);
    } else if (!e.target.closest('.action-menu')) {
      // Close all open action menus when clicking anywhere else
      document.querySelectorAll('.action-menu-items').forEach(menu => {
        menu.classList.add('hidden');
      });
    }
  });
});

// Reload devices after adding/editing (called from modal)
window.reloadDevicesTable = function() {
  loadDevices();
};

// Copy pipeline name to clipboard
function copyPipelineName(networkId, networkName) {
  // Fetch pipeline name from API
  fetch(`/API/SNMP/GetNetworkPipelineName/${networkId}/`)
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        const pipelineName = data.pipeline_name;
        
        // Copy to clipboard
        navigator.clipboard.writeText(pipelineName)
          .then(() => {
            showToast(`Pipeline name copied: ${pipelineName}`, 'success');
          })
          .catch(err => {
            // Fallback for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = pipelineName;
            textArea.style.position = 'fixed';
            textArea.style.left = '-999999px';
            document.body.appendChild(textArea);
            textArea.select();
            try {
              document.execCommand('copy');
              showToast(`Pipeline name copied: ${pipelineName}`, 'success');
            } catch (err) {
              showToast('Failed to copy pipeline name', 'error');
            }
            document.body.removeChild(textArea);
          });
      } else {
        showToast(data.error || 'Failed to fetch pipeline name', 'error');
      }
    })
    .catch(error => {
      showToast('Error fetching pipeline name: ' + error.message, 'error');
    });
}

// Toast notification function (if not already defined)
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
    <span>${escapeHtml(message)}</span>
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

// Add event listener for empty state Add Device button
document.addEventListener('DOMContentLoaded', function() {
  const addDeviceBtnEmpty = document.getElementById('addDeviceBtnEmpty');
  if (addDeviceBtnEmpty) {
    addDeviceBtnEmpty.addEventListener('click', function() {
      openDeviceModal();
    });
  }
});
