// Network Config - Devices Table (pagination, search, filter, sort)

let currentPage = 1;
let pageSize = 25;
let currentSearch = '';
let currentVendorFilter = '';
let currentSort = '-created_at';

const STATUS_BADGE = {
  reachable:   '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">Reachable</span>',
  unreachable: '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">Unreachable</span>',
  error:       '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">Error</span>',
  unknown:     '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">Unknown</span>',
};

function loadDevices() {
  const loadingState = document.getElementById('loadingState');
  const tableBody = document.getElementById('devicesTableBody');
  const tableContainer = document.getElementById('devicesTableContainer');

  if (loadingState) loadingState.classList.remove('hidden');
  if (tableBody) tableBody.innerHTML = '';

  const params = new URLSearchParams({
    page: currentPage,
    page_size: pageSize,
    sort_by: currentSort,
  });
  if (currentSearch) params.append('search', currentSearch);
  if (currentVendorFilter) params.append('vendor', currentVendorFilter);

  fetch(`/NetworkConfig/GetDevices/?${params.toString()}`)
    .then(r => r.json())
    .then(data => {
      if (loadingState) loadingState.classList.add('hidden');

      const initialEmptyState = document.getElementById('initialEmptyState');
      const mainContent = document.getElementById('mainContent');
      const emptyState = document.getElementById('emptyState');
      const noResultsState = document.getElementById('noResultsState');
      const pagination = document.getElementById('paginationControls');

      if (data.total === 0) {
        const hasFilters = currentSearch || currentVendorFilter;
        if (hasFilters) {
          mainContent.classList.remove('hidden');
          initialEmptyState.classList.add('hidden');
          noResultsState.classList.remove('hidden');
          emptyState.classList.add('hidden');
          tableContainer.classList.add('hidden');
          pagination.classList.add('hidden');
        } else {
          initialEmptyState.classList.remove('hidden');
          mainContent.classList.add('hidden');
        }
        return;
      }

      initialEmptyState.classList.add('hidden');
      mainContent.classList.remove('hidden');
      emptyState.classList.add('hidden');
      noResultsState.classList.add('hidden');
      tableContainer.classList.remove('hidden');
      pagination.classList.remove('hidden');

      renderDevices(data.devices);
      updatePaginationControls(data);
    })
    .catch(error => {
      if (loadingState) loadingState.classList.add('hidden');
      if (tableBody) tableBody.innerHTML = `
        <tr><td colspan="9" class="px-6 py-8 text-center text-red-400">
          Error loading devices: ${error.message}
        </td></tr>`;
    });
}

function renderDevices(devices) {
  const tableBody = document.getElementById('devicesTableBody');
  tableBody.innerHTML = '';

  devices.forEach(device => {
    const statusBadge = STATUS_BADGE[device.last_status] || STATUS_BADGE.unknown;
    const protocols = [];
    if (device.use_restconf) protocols.push('RESTCONF');
    if (device.use_netconf) protocols.push('NETCONF');

    const row = document.createElement('tr');
    row.className = 'hover:bg-gray-700/50 transition-colors';
    row.innerHTML = `
      <td class="px-6 py-4 whitespace-nowrap text-sm" id="status-${device.id}">${statusBadge}</td>
      <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-white">${escapeHtml(device.name)}</td>
      <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${escapeHtml(device.hostname)}</td>
      <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${escapeHtml(device.vendor_display || device.vendor)}</td>
      <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${protocols.join(', ') || '-'}</td>
      <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${device.credential_name ? escapeHtml(device.credential_name) : '<span class="text-gray-500">None</span>'}</td>
      <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${device.profile_name ? escapeHtml(device.profile_name) : '<span class="text-gray-500">None</span>'}</td>
      <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${formatDate(device.created_at)}</td>
      <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
        <div class="flex items-center justify-end gap-2">
          <button onclick="testDevice(${device.id}, this)" class="btn btn-xs btn-outline" title="Test connection">Test</button>
          <div class="action-menu relative">
            <button class="action-menu-button p-1 hover:bg-gray-700 rounded">
              <svg class="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
              </svg>
            </button>
            <div class="action-menu-items hidden fixed z-50 w-32 bg-gray-800 rounded-md shadow-lg py-1" role="menu" style="transform: translate(-50%, 0);">
              <div class="px-1 py-1">
                <button onclick="editDevice(${device.id})" class="group flex items-center w-full px-4 py-2 text-sm text-gray-300 hover:bg-gray-700 rounded-md">
                  <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                  Edit
                </button>
                <button onclick="deleteDevice(${device.id})" class="group flex items-center w-full px-4 py-2 text-sm text-red-400 hover:bg-gray-700 rounded-md">
                  <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                  Delete
                </button>
              </div>
            </div>
          </div>
        </div>
      </td>`;
    tableBody.appendChild(row);
  });
}

function updatePaginationControls(data) {
  const start = (data.page - 1) * data.page_size + 1;
  const end = Math.min(data.page * data.page_size, data.total);
  document.getElementById('showingStart').textContent = start;
  document.getElementById('showingEnd').textContent = end;
  document.getElementById('totalDevices').textContent = data.total;
  document.getElementById('pageInfo').textContent = `Page ${data.page} of ${data.total_pages}`;
  document.getElementById('prevPageBtn').disabled = !data.has_previous;
  document.getElementById('nextPageBtn').disabled = !data.has_next;
}

function previousPage() {
  if (currentPage > 1) { currentPage--; loadDevices(); }
}

function nextPage() {
  currentPage++;
  loadDevices();
}

function sortTable(field) {
  if (currentSort === field) {
    currentSort = `-${field}`;
  } else if (currentSort === `-${field}`) {
    currentSort = field;
  } else {
    currentSort = `-${field}`;
  }
  currentPage = 1;
  loadDevices();
}

function editDevice(deviceId) {
  fetch(`/NetworkConfig/GetDevice/${deviceId}/`)
    .then(r => r.json())
    .then(data => openDeviceModal(data))
    .catch(err => showToast('Error loading device: ' + err, 'error'));
}

function deleteDevice(deviceId) {
  if (!confirm('Are you sure you want to delete this device?')) return;
  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
  fetch(`/NetworkConfig/DeleteDevice/${deviceId}/`, {
    method: 'POST',
    headers: { 'X-CSRFToken': csrfToken },
  })
    .then(r => {
      if (!r.ok) return r.text().then(t => { throw new Error(t); });
      return r.json();
    })
    .then(() => {
      showToast('Device deleted!', 'success');
      loadDevices();
    })
    .catch(err => showToast('Error deleting device: ' + err.message, 'error'));
}

function testDevice(deviceId, btn) {
  const originalText = btn.textContent;
  btn.textContent = 'Testing...';
  btn.disabled = true;

  fetch(`/NetworkConfig/TestDevice/${deviceId}/`)
    .then(r => r.json())
    .then(data => {
      btn.textContent = originalText;
      btn.disabled = false;

      const statusCell = document.getElementById(`status-${deviceId}`);
      if (statusCell) {
        statusCell.innerHTML = STATUS_BADGE[data.status] || STATUS_BADGE.unknown;
      }

      const toastType = data.status === 'reachable' ? 'success' : 'error';
      showToast(`${data.status}: ${data.message}`, toastType);
    })
    .catch(err => {
      btn.textContent = originalText;
      btn.disabled = false;
      showToast('Test failed: ' + err.message, 'error');
    });
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatDate(isoString) {
  if (!isoString) return '-';
  const d = new Date(isoString);
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

// Action menu (3-dot)
document.addEventListener('click', function (e) {
  const actionButton = e.target.closest('.action-menu-button');
  if (actionButton) {
    e.stopPropagation();
    const menu = actionButton.nextElementSibling;
    const isHidden = menu.classList.contains('hidden');
    document.querySelectorAll('.action-menu-items').forEach(m => { if (m !== menu) m.classList.add('hidden'); });
    if (isHidden) {
      menu.style.left = `${e.clientX}px`;
      menu.style.top = `${e.clientY}px`;
    }
    menu.classList.toggle('hidden', !isHidden);
  } else if (!e.target.closest('.action-menu')) {
    document.querySelectorAll('.action-menu-items').forEach(m => m.classList.add('hidden'));
  }
});

window.addEventListener('scroll', function () {
  document.querySelectorAll('.action-menu-items').forEach(m => m.classList.add('hidden'));
}, true);

// Search & filter event listeners
document.addEventListener('DOMContentLoaded', function () {
  const searchInput = document.getElementById('searchInput');
  if (searchInput) {
    let searchTimer;
    searchInput.addEventListener('input', function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        currentSearch = this.value.trim();
        currentPage = 1;
        loadDevices();
      }, 300);
    });
  }

  const vendorFilter = document.getElementById('vendorFilter');
  if (vendorFilter) {
    vendorFilter.addEventListener('change', function () {
      currentVendorFilter = this.value;
      currentPage = 1;
      loadDevices();
    });
  }

  const pageSizeSelect = document.getElementById('pageSizeSelect');
  if (pageSizeSelect) {
    pageSizeSelect.addEventListener('change', function () {
      pageSize = parseInt(this.value);
      currentPage = 1;
      loadDevices();
    });
  }

  loadDevices();
});
