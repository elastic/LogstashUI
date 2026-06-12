/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// Credentials Table Management
let allCredentials = [];
let filteredCredentials = [];
let currentPage = 1;
let pageSize = 25;
let totalCredentialsCount = 0;
let sortField = 'name';
let sortDirection = 'asc';

// Fetch all credentials from the API
async function fetchCredentials() {
  try {
    const response = await fetch('/SNMP/GetCredentials/');
    const credentials = await response.json();
    allCredentials = credentials;
    totalCredentialsCount = credentials.length;
    applyFiltersAndRender();
  } catch (error) {
    console.error('Error fetching credentials:', error);
    showToast('Error loading credentials: ' + error.message, 'error');
  }
}

// Update credentials data without full page reload (called after add/edit/delete)
function updateCredentialsData(credentials) {
  allCredentials = credentials;
  totalCredentialsCount = credentials.length;
  applyFiltersAndRender();
  console.log('Credentials table updated with new data');
}

// Apply search and version filters, then render
function applyFiltersAndRender() {
  const searchInput = document.getElementById('searchInput');
  const searchTerm = searchInput ? searchInput.value.toLowerCase() : '';
  const versionFilter = document.getElementById('versionFilter');
  const selectedVersion = versionFilter ? versionFilter.value : '';

  filteredCredentials = allCredentials.filter(credential => {
    const typeLabel = getTypeLabel(credential).toLowerCase();
    const matchesSearch = !searchTerm || (
      credential.name.toLowerCase().includes(searchTerm) ||
      (credential.description && credential.description.toLowerCase().includes(searchTerm)) ||
      typeLabel.includes(searchTerm)
    );
    const matchesVersion = !selectedVersion || credential.version === selectedVersion;
    return matchesSearch && matchesVersion;
  });

  sortCredentials();
  currentPage = 1;
  renderTable();
  updatePagination();
  updateUIState();
}

// Sort credentials based on current sort field and direction
function sortCredentials() {
  filteredCredentials.sort((a, b) => {
    let aVal = a[sortField] !== undefined ? a[sortField] : '';
    let bVal = b[sortField] !== undefined ? b[sortField] : '';

    if (sortField === 'device_count') {
      aVal = a.device_count || 0;
      bVal = b.device_count || 0;
      if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
      return 0;
    }

    if (typeof aVal === 'string') aVal = aVal.toLowerCase();
    if (typeof bVal === 'string') bVal = bVal.toLowerCase();

    if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
    if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
    return 0;
  });
}

// Sort table by column header click
function sortCredentialTable(field) {
  if (sortField === field) {
    sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
  } else {
    sortField = field;
    sortDirection = 'asc';
  }

  document.querySelectorAll('[id^="sort-"]').forEach(el => {
    el.textContent = '';
  });
  const indicator = document.getElementById(`sort-${field}`);
  if (indicator) {
    indicator.textContent = sortDirection === 'asc' ? '▼' : '▲';
  }

  applyFiltersAndRender();
}

// Determine the human-readable type label for a credential
function getTypeLabel(credential) {
  if (credential.version === '1' || credential.version === '2c') {
    return 'Community';
  }
  if (credential.security_level === 'noAuthNoPriv') return 'No Auth/Priv';
  if (credential.security_level === 'authNoPriv') return 'Auth Only';
  return 'Auth + Priv';
}

// Render the table with the current page of filtered/sorted data
function renderTable() {
  const tbody = document.getElementById('credentialsTableBody');
  const loadingState = document.getElementById('loadingState');

  if (loadingState) loadingState.style.display = 'none';
  tbody.innerHTML = '';

  const startIndex = (currentPage - 1) * pageSize;
  const endIndex = Math.min(startIndex + pageSize, filteredCredentials.length);
  const pageCredentials = filteredCredentials.slice(startIndex, endIndex);

  pageCredentials.forEach(credential => {
    tbody.appendChild(createCredentialRow(credential));
  });
}

// Update pagination controls
function updatePagination() {
  const totalPages = Math.ceil(filteredCredentials.length / pageSize);
  const startIndex = (currentPage - 1) * pageSize + 1;
  const endIndex = Math.min(currentPage * pageSize, filteredCredentials.length);

  document.getElementById('showingStart').textContent = filteredCredentials.length > 0 ? startIndex : 0;
  document.getElementById('showingEnd').textContent = endIndex;
  document.getElementById('totalCredentials').textContent = filteredCredentials.length;
  document.getElementById('pageInfo').textContent = `Page ${currentPage} of ${totalPages || 1}`;

  document.getElementById('prevPageBtn').disabled = currentPage === 1;
  document.getElementById('nextPageBtn').disabled = currentPage >= totalPages;
}

// Pagination navigation
function nextPage() {
  const totalPages = Math.ceil(filteredCredentials.length / pageSize);
  if (currentPage < totalPages) {
    currentPage++;
    renderTable();
    updatePagination();
  }
}

function previousPage() {
  if (currentPage > 1) {
    currentPage--;
    renderTable();
    updatePagination();
  }
}

// Build a single table row element for a credential
function createCredentialRow(credential) {
  const tr = document.createElement('tr');
  tr.className = 'hover:bg-gray-700/50 transition-colors';

  const typeLabel = getTypeLabel(credential);
  const deviceCountClass = credential.device_count > 0
    ? 'bg-blue-600 text-white'
    : 'bg-gray-700 text-gray-400';
  const description = credential.description
    ? (credential.description.length > 50
        ? escapeHtml(credential.description.substring(0, 50)) + '…'
        : escapeHtml(credential.description))
    : '-';

  tr.innerHTML = `
    <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-white">${escapeHtml(credential.name)}</td>
    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
      <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
        SNMPv${escapeHtml(String(credential.version))}
      </span>
    </td>
    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${typeLabel}</td>
    <td class="px-6 py-4 text-sm text-gray-300">${description}</td>
    <td class="px-6 py-4 whitespace-nowrap text-center text-sm">
      <span class="inline-flex items-center justify-center px-2 py-0.5 text-xs font-semibold rounded-full ${deviceCountClass}">
        ${credential.device_count || 0}
      </span>
    </td>
    <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
      <div class="action-menu relative">
        <button class="action-menu-button p-1 hover:bg-gray-700 rounded">
          <svg class="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
          </svg>
        </button>
        <div class="action-menu-items hidden fixed z-50 w-48 bg-gray-800 rounded-md shadow-lg py-1" role="menu">
          <div class="px-1 py-1">
            <button onclick="cloneCredential(${credential.id})" class="group flex items-center w-full px-4 py-2 text-sm text-blue-400 hover:bg-gray-700 rounded-md" role="menuitem">
              <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              Clone
            </button>
            <hr class="my-1 border-gray-700">
            <button onclick="editCredential(${credential.id})" class="group flex items-center w-full px-4 py-2 text-sm text-gray-300 hover:bg-gray-700 rounded-md" role="menuitem">
              <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
              Edit
            </button>
            <hr class="my-1 border-gray-700">
            <button onclick="deleteCredential(${credential.id})" class="group flex items-center w-full px-4 py-2 text-sm text-red-400 hover:bg-gray-700 rounded-md" role="menuitem">
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

  return tr;
}

// Show/hide the correct UI sections based on data state
function updateUIState() {
  const initialEmptyState = document.getElementById('initialEmptyState');
  const mainContent = document.getElementById('mainContent');
  const noResultsState = document.getElementById('noResultsState');
  const tableContainer = document.getElementById('credentialsTableContainer');
  const paginationControls = document.getElementById('paginationControls');

  if (totalCredentialsCount === 0) {
    initialEmptyState.classList.remove('hidden');
    mainContent.classList.add('hidden');
  } else if (filteredCredentials.length === 0) {
    initialEmptyState.classList.add('hidden');
    mainContent.classList.remove('hidden');
    noResultsState.classList.remove('hidden');
    tableContainer.classList.add('hidden');
    paginationControls.classList.add('hidden');
  } else {
    initialEmptyState.classList.add('hidden');
    mainContent.classList.remove('hidden');
    noResultsState.classList.add('hidden');
    tableContainer.classList.remove('hidden');
    paginationControls.classList.remove('hidden');
  }
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', async function() {
  await fetchCredentials();

  const searchInput = document.getElementById('searchInput');
  if (searchInput) {
    searchInput.addEventListener('input', applyFiltersAndRender);
  }

  const versionFilter = document.getElementById('versionFilter');
  if (versionFilter) {
    versionFilter.addEventListener('change', applyFiltersAndRender);
  }

  const pageSizeSelect = document.getElementById('pageSizeSelect');
  if (pageSizeSelect) {
    pageSizeSelect.addEventListener('change', function() {
      pageSize = parseInt(this.value);
      currentPage = 1;
      renderTable();
      updatePagination();
    });
  }

  const addCredentialBtnEmpty = document.getElementById('addCredentialBtnEmpty');
  if (addCredentialBtnEmpty) {
    addCredentialBtnEmpty.addEventListener('click', function() {
      openCredentialModal();
    });
  }
});
