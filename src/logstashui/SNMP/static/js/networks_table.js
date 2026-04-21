/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// Networks Table Management
let allNetworks = [];
let filteredNetworks = [];
let currentPage = 1;
let pageSize = 25;
let sortField = 'name';
let sortDirection = 'asc';
let totalNetworksCount = 0;

// Fetch all networks from the API
async function fetchNetworks() {
  try {
    const response = await fetch('/SNMP/GetNetworks/');
    const networks = await response.json();
    allNetworks = networks;
    totalNetworksCount = networks.length;
    
    // Populate filter dropdowns
    populateFilters();
    
    // Apply filters and render
    applyFiltersAndRender();
    
    // Show/hide appropriate states
    updateUIState();
  } catch (error) {
    console.error('Error fetching networks:', error);
    showToast('Error loading networks: ' + error.message, 'error');
  }
}

// Populate filter dropdowns with unique values
function populateFilters() {
  // Get unique logstash nodes
  const logstashNodes = [...new Set(allNetworks.map(n => n.logstash_name).filter(Boolean))].sort();
  const logstashFilter = document.getElementById('logstashFilter');
  logstashFilter.innerHTML = '<option value="">All Nodes</option>';
  logstashNodes.forEach(node => {
    const option = document.createElement('option');
    option.value = node;
    option.textContent = node;
    logstashFilter.appendChild(option);
  });
  
  // Get unique connections from network data
  const connectionMap = new Map();
  allNetworks.forEach(n => {
    if (n.connection && n.connection_name) {
      connectionMap.set(n.connection, n.connection_name);
    }
  });
  
  const connectionFilter = document.getElementById('connectionFilter');
  connectionFilter.innerHTML = '<option value="">All Connections</option>';
  
  // Sort by connection name
  const sortedConnections = Array.from(connectionMap.entries()).sort((a, b) => 
    a[1].localeCompare(b[1])
  );
  
  sortedConnections.forEach(([id, name]) => {
    const option = document.createElement('option');
    option.value = id;
    option.textContent = name;
    connectionFilter.appendChild(option);
  });
}


// Apply search and filters
function applyFiltersAndRender() {
  const searchTerm = document.getElementById('searchInput').value.toLowerCase();
  const logstashFilter = document.getElementById('logstashFilter').value;
  const connectionFilter = document.getElementById('connectionFilter').value;
  
  filteredNetworks = allNetworks.filter(network => {
    // Search filter (name or network range)
    const matchesSearch = !searchTerm || 
      network.name.toLowerCase().includes(searchTerm) ||
      network.network_range.toLowerCase().includes(searchTerm);
    
    // Logstash node filter
    const matchesLogstash = !logstashFilter || network.logstash_name === logstashFilter;
    
    // Connection filter
    const matchesConnection = !connectionFilter || 
      (network.connection && network.connection.toString() === connectionFilter);
    
    return matchesSearch && matchesLogstash && matchesConnection;
  });
  
  // Sort the filtered results
  sortNetworks();
  
  // Reset to page 1 when filters change
  currentPage = 1;
  
  // Render the table
  renderTable();
  updatePagination();
  updateUIState();
}

// Sort networks based on current sort field and direction
function sortNetworks() {
  filteredNetworks.sort((a, b) => {
    let aVal = a[sortField] || '';
    let bVal = b[sortField] || '';
    
    // Handle connection object
    if (sortField === 'connection') {
      aVal = a.connection ? a.connection.name : '';
      bVal = b.connection ? b.connection.name : '';
    }
    
    // Handle numeric fields (device_count)
    if (sortField === 'device_count') {
      aVal = a[sortField] || 0;
      bVal = b[sortField] || 0;
      // Numeric comparison
      if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
      return 0;
    }
    
    // Convert to lowercase for case-insensitive sorting
    if (typeof aVal === 'string') aVal = aVal.toLowerCase();
    if (typeof bVal === 'string') bVal = bVal.toLowerCase();
    
    if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
    if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
    return 0;
  });
}

// Sort table by column
function sortTable(field) {
  if (sortField === field) {
    // Toggle direction if same field
    sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
  } else {
    // New field, default to ascending
    sortField = field;
    sortDirection = 'asc';
  }
  
  // Update sort indicators
  document.querySelectorAll('[id^="sort-"]').forEach(el => {
    el.textContent = '';
  });
  document.getElementById(`sort-${field}`).textContent = sortDirection === 'asc' ? '▼' : '▲';
  
  applyFiltersAndRender();
}

// Render the table with current page of data
function renderTable() {
  const tbody = document.getElementById('networksTableBody');
  const loadingState = document.getElementById('loadingState');
  
  // Hide loading state
  loadingState.style.display = 'none';
  
  // Calculate pagination
  const startIndex = (currentPage - 1) * pageSize;
  const endIndex = Math.min(startIndex + pageSize, filteredNetworks.length);
  const pageNetworks = filteredNetworks.slice(startIndex, endIndex);
  
  // Clear existing rows
  tbody.innerHTML = '';
  
  // Render rows
  pageNetworks.forEach(network => {
    const row = createNetworkRow(network);
    tbody.appendChild(row);
  });
}

// Create a table row for a network
function createNetworkRow(network) {
  const tr = document.createElement('tr');
  tr.className = 'hover:bg-gray-700/50 transition-colors';
  
  tr.innerHTML = `
    <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-white">
      <div class="flex items-center gap-2 cursor-pointer hover:text-blue-400 group" onclick="copyPipelineName(${network.id}, '${escapeHtml(network.name)}')" title="Click to copy pipeline name">
        <span>${escapeHtml(network.name)}</span>
        <svg class="w-4 h-4 text-gray-400 group-hover:text-blue-400 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
        </svg>
      </div>
    </td>
    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
      <span class="font-mono">${escapeHtml(network.network_range)}</span>
    </td>
    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300 text-center">
      <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${network.device_count > 0 ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-800'}">${network.device_count || 0}</span>
    </td>
    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${escapeHtml(network.logstash_name || '')}</td>
    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
      ${network.discovery_enabled ? 
        '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">Enabled</span>' :
        '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">Disabled</span>'
      }
    </td>
    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
      ${network.traps_enabled ? 
        '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">Enabled</span>' :
        '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">Disabled</span>'
      }
    </td>
    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
      ${network.connection_name ? escapeHtml(network.connection_name) : '<span class="text-gray-500 italic">None</span>'}
    </td>
    <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
      <div class="action-menu relative">
        <button class="action-menu-button p-1 hover:bg-gray-700 rounded">
          <svg class="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
          </svg>
        </button>
        <div class="action-menu-items hidden fixed z-50 w-32 bg-gray-800 rounded-md shadow-lg py-1" role="menu">
          <div class="px-1 py-1">
            <button onclick="editNetwork(${network.id})" class="group flex items-center w-full px-4 py-2 text-sm text-gray-300 hover:bg-gray-700 rounded-md" role="menuitem">
              <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
              Edit
            </button>
            <button onclick="deleteNetwork(${network.id}, '${escapeHtml(network.name)}')" class="group flex items-center w-full px-4 py-2 text-sm text-red-400 hover:bg-gray-700 rounded-md" role="menuitem">
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


// Update pagination controls
function updatePagination() {
  const totalPages = Math.ceil(filteredNetworks.length / pageSize);
  const startIndex = (currentPage - 1) * pageSize + 1;
  const endIndex = Math.min(currentPage * pageSize, filteredNetworks.length);
  
  document.getElementById('showingStart').textContent = filteredNetworks.length > 0 ? startIndex : 0;
  document.getElementById('showingEnd').textContent = endIndex;
  document.getElementById('totalNetworks').textContent = filteredNetworks.length;
  document.getElementById('pageInfo').textContent = `Page ${currentPage} of ${totalPages || 1}`;
  
  // Enable/disable pagination buttons
  document.getElementById('prevPageBtn').disabled = currentPage === 1;
  document.getElementById('nextPageBtn').disabled = currentPage >= totalPages;
}

// Update UI state (show/hide empty states)
function updateUIState() {
  const initialEmptyState = document.getElementById('initialEmptyState');
  const mainContent = document.getElementById('mainContent');
  const noResultsState = document.getElementById('noResultsState');
  const tableContainer = document.getElementById('networksTableContainer');
  const paginationControls = document.getElementById('paginationControls');
  
  if (totalNetworksCount === 0) {
    // No networks at all
    initialEmptyState.classList.remove('hidden');
    mainContent.classList.add('hidden');
  } else if (filteredNetworks.length === 0) {
    // Networks exist but filters returned nothing
    initialEmptyState.classList.add('hidden');
    mainContent.classList.remove('hidden');
    noResultsState.classList.remove('hidden');
    tableContainer.classList.add('hidden');
    paginationControls.classList.add('hidden');
  } else {
    // Show table
    initialEmptyState.classList.add('hidden');
    mainContent.classList.remove('hidden');
    noResultsState.classList.add('hidden');
    tableContainer.classList.remove('hidden');
    paginationControls.classList.remove('hidden');
  }
}

// Pagination functions
function nextPage() {
  const totalPages = Math.ceil(filteredNetworks.length / pageSize);
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


// Initialize on page load
document.addEventListener('DOMContentLoaded', async function() {
  // Fetch and render networks
  await fetchNetworks();
  
  // Set up event listeners
  document.getElementById('searchInput').addEventListener('input', applyFiltersAndRender);
  document.getElementById('logstashFilter').addEventListener('change', applyFiltersAndRender);
  document.getElementById('connectionFilter').addEventListener('change', applyFiltersAndRender);
  document.getElementById('pageSizeSelect').addEventListener('change', function() {
    pageSize = parseInt(this.value);
    currentPage = 1;
    renderTable();
    updatePagination();
  });
  
  // Add event listener for empty state button
  const addNetworkBtnEmpty = document.getElementById('addNetworkBtnEmpty');
  if (addNetworkBtnEmpty) {
    addNetworkBtnEmpty.addEventListener('click', function() {
      openNetworkModal();
    });
  }
});
