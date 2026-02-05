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
      const searchFilterBar = document.getElementById('searchFilterBar');
      
      // Check if empty
      if (data.total === 0) {
        // Determine if this is truly empty or just no results from search/filter
        const hasActiveFilters = currentSearch || currentNetworkFilter;
        
        if (hasActiveFilters) {
          // Show "no results" state
          noResultsState.classList.remove('hidden');
          emptyState.classList.add('hidden');
          searchFilterBar.classList.remove('hidden');
        } else {
          // Show "get started" empty state and hide search bar
          emptyState.classList.remove('hidden');
          noResultsState.classList.add('hidden');
          searchFilterBar.classList.add('hidden');
        }
        
        tableContainer.classList.add('hidden');
        document.getElementById('paginationControls').classList.add('hidden');
        return;
      }
      
      // Hide all empty states and show table
      emptyState.classList.add('hidden');
      noResultsState.classList.add('hidden');
      searchFilterBar.classList.remove('hidden');
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
    
    const createdDate = new Date(device.created_at).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
    
    row.innerHTML = `
      <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-white">${escapeHtml(device.name)}</td>
      <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
        <span class="font-mono">${escapeHtml(device.ip_address)}</span>
      </td>
      <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
        ${device.credential_name ? escapeHtml(device.credential_name) : '<span class="text-gray-500 italic">None</span>'}
      </td>
      <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
        ${device.network_name ? escapeHtml(device.network_name) : '<span class="text-gray-500 italic">None</span>'}
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
  });
  
  // Reattach action menu handlers
  attachActionMenuHandlers();
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

// Attach action menu handlers
function attachActionMenuHandlers() {
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
});

// Reload devices after adding/editing (called from modal)
window.reloadDevicesTable = function() {
  loadDevices();
};
