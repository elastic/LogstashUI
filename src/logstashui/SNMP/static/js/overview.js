/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// Load overview metrics on page load
document.addEventListener('DOMContentLoaded', function() {
  loadOverviewMetrics();
});

/**
 * Load overview metrics from the API
 */
function loadOverviewMetrics() {
  fetch('/SNMP/GetOverviewMetrics/')
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        // Update Total Devices
        updateMetricCard('totalDevicesValue', data.metrics.total_devices, 'text-blue-400');
        
        // Update Discovered Devices
        updateMetricCard('discoveredDevicesValue', data.metrics.discovered_devices, 'text-green-400');
        
        // Update High Resource Usage Tables
        updateHighCpuTable(data.high_usage.high_cpu);
        updateHighMemoryTable(data.high_usage.high_memory);
        
        // Update Data Quality Table
        updateDataQualityTable(data.data_quality.devices);
        
        // Show errors if any (but don't fail the whole page)
        if (data.errors && data.errors.length > 0) {
          showWarnings(data.errors);
        }
      } else {
        // Show error state
        showError(data.error || 'Failed to load metrics');
        
        // Set cards to error state
        setMetricError('totalDevicesValue');
        setMetricError('discoveredDevicesValue');
        
        // Hide data quality loading
        document.getElementById('dataQualityLoading').classList.add('hidden');
      }
    })
    .catch(error => {
      console.error('Error loading overview metrics:', error);
      showError('Failed to connect to server: ' + error.message);
      
      // Set cards to error state
      setMetricError('totalDevicesValue');
      setMetricError('discoveredDevicesValue');
      
      // Hide data quality loading
      document.getElementById('dataQualityLoading').classList.add('hidden');
    });
}

/**
 * Update a metric card with the value
 */
function updateMetricCard(elementId, value, colorClass) {
  const element = document.getElementById(elementId);
  if (element) {
    element.innerHTML = `<p class="text-3xl font-bold ${colorClass}">${formatNumber(value)}</p>`;
  }
}

/**
 * Set a metric card to error state
 */
function setMetricError(elementId) {
  const element = document.getElementById(elementId);
  if (element) {
    element.innerHTML = `
      <div class="flex items-center gap-2">
        <svg class="w-5 h-5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span class="text-sm text-red-400">Error</span>
      </div>
    `;
  }
}

/**
 * Show error message
 */
function showError(message) {
  const errorContainer = document.getElementById('errorContainer');
  const errorMessage = document.getElementById('errorMessage');
  
  if (errorContainer && errorMessage) {
    errorMessage.textContent = message;
    errorContainer.classList.remove('hidden');
  }
}

/**
 * Show warnings for partial failures (e.g., some ES clusters failed)
 */
function showWarnings(errors) {
  const errorContainer = document.getElementById('errorContainer');
  const errorMessage = document.getElementById('errorMessage');
  
  if (errorContainer && errorMessage) {
    let warningText = 'Some Elasticsearch connections had errors:\n';
    errors.forEach(err => {
      warningText += `\n• ${err.connection}: ${err.error}`;
    });
    
    errorMessage.textContent = warningText;
    errorContainer.classList.remove('hidden');
    
    // Change styling to warning instead of error
    errorContainer.classList.remove('bg-red-900/20', 'border-red-500/50');
    errorContainer.classList.add('bg-yellow-900/20', 'border-yellow-500/50');
    
    const icon = errorContainer.querySelector('svg');
    if (icon) {
      icon.classList.remove('text-red-400');
      icon.classList.add('text-yellow-400');
    }
    
    const title = errorContainer.querySelector('h3');
    if (title) {
      title.textContent = 'Partial Data Available';
      title.classList.remove('text-red-300');
      title.classList.add('text-yellow-300');
    }
    
    const message = errorContainer.querySelector('#errorMessage');
    if (message) {
      message.classList.remove('text-red-200');
      message.classList.add('text-yellow-200');
    }
  }
}

/**
 * Format number with commas
 */
function formatNumber(num) {
  if (num === null || num === undefined) {
    return '0';
  }
  return num.toLocaleString();
}

/**
 * Update the data quality table with device information
 */
function updateDataQualityTable(devices) {
  const loadingDiv = document.getElementById('dataQualityLoading');
  const tableContainer = document.getElementById('dataQualityTableContainer');
  const emptyState = document.getElementById('dataQualityEmpty');
  const tableBody = document.getElementById('dataQualityTableBody');
  
  // Hide loading
  loadingDiv.classList.add('hidden');
  
  // Check if there are any devices with issues
  if (!devices || devices.length === 0) {
    // Show empty state (all devices have complete data)
    emptyState.classList.remove('hidden');
    tableContainer.classList.add('hidden');
    return;
  }
  
  // Show table and populate it
  tableContainer.classList.remove('hidden');
  emptyState.classList.add('hidden');
  
  // Clear existing rows
  tableBody.innerHTML = '';
  
  // Add rows for each device with issues
  devices.forEach(device => {
    const row = document.createElement('tr');
    row.className = 'hover:bg-gray-700/50 transition-colors';
    
    // Status icons
    const cpuIcon = device.has_cpu 
      ? '<svg class="w-5 h-5 text-green-400 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>'
      : '<svg class="w-5 h-5 text-red-400 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>';
    
    const memoryIcon = device.has_memory
      ? '<svg class="w-5 h-5 text-green-400 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>'
      : '<svg class="w-5 h-5 text-red-400 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>';
    
    const uptimeIcon = device.has_uptime
      ? '<svg class="w-5 h-5 text-green-400 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>'
      : '<svg class="w-5 h-5 text-red-400 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>';
    
    const interfacesIcon = device.has_interfaces
      ? '<svg class="w-5 h-5 text-green-400 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>'
      : '<svg class="w-5 h-5 text-red-400 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>';
    
    row.innerHTML = `
      <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-white">${escapeHtml(device.name)}</td>
      <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
        <span class="font-mono">${escapeHtml(device.ip_address)}</span>
      </td>
      <td class="px-6 py-4 whitespace-nowrap text-sm text-center">${cpuIcon}</td>
      <td class="px-6 py-4 whitespace-nowrap text-sm text-center">${memoryIcon}</td>
      <td class="px-6 py-4 whitespace-nowrap text-sm text-center">${uptimeIcon}</td>
      <td class="px-6 py-4 whitespace-nowrap text-sm text-center">${interfacesIcon}</td>
      <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
        ${device.network_name ? escapeHtml(device.network_name) : '<span class="text-gray-500 italic">None</span>'}
      </td>
    `;
    
    tableBody.appendChild(row);
  });
}

/**
 * Update the high CPU usage table
 */
function updateHighCpuTable(devices) {
  const loadingDiv = document.getElementById('highCpuLoading');
  const tableContainer = document.getElementById('highCpuTableContainer');
  const emptyState = document.getElementById('highCpuEmpty');
  const tableBody = document.getElementById('highCpuTableBody');
  
  // Hide loading
  loadingDiv.classList.add('hidden');
  
  // Check if there are any devices with high CPU
  if (!devices || devices.length === 0) {
    emptyState.classList.remove('hidden');
    tableContainer.classList.add('hidden');
    return;
  }
  
  // Show table and populate it
  tableContainer.classList.remove('hidden');
  emptyState.classList.add('hidden');
  
  // Clear existing rows
  tableBody.innerHTML = '';
  
  // Add rows for each device
  devices.forEach(device => {
    const row = document.createElement('tr');
    row.className = 'hover:bg-gray-700/50 transition-colors';
    
    // Color code based on severity
    let percentClass = 'text-orange-400';
    if (device.cpu_pct >= 95) {
      percentClass = 'text-red-400 font-bold';
    } else if (device.cpu_pct >= 90) {
      percentClass = 'text-orange-400 font-semibold';
    }
    
    row.innerHTML = `
      <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-white">${escapeHtml(device.name)}</td>
      <td class="px-6 py-4 whitespace-nowrap text-sm text-right ${percentClass}">${device.cpu_pct}%</td>
    `;
    
    tableBody.appendChild(row);
  });
}

/**
 * Update the high memory usage table
 */
function updateHighMemoryTable(devices) {
  const loadingDiv = document.getElementById('highMemoryLoading');
  const tableContainer = document.getElementById('highMemoryTableContainer');
  const emptyState = document.getElementById('highMemoryEmpty');
  const tableBody = document.getElementById('highMemoryTableBody');
  
  // Hide loading
  loadingDiv.classList.add('hidden');
  
  // Check if there are any devices with high memory
  if (!devices || devices.length === 0) {
    emptyState.classList.remove('hidden');
    tableContainer.classList.add('hidden');
    return;
  }
  
  // Show table and populate it
  tableContainer.classList.remove('hidden');
  emptyState.classList.add('hidden');
  
  // Clear existing rows
  tableBody.innerHTML = '';
  
  // Add rows for each device
  devices.forEach(device => {
    const row = document.createElement('tr');
    row.className = 'hover:bg-gray-700/50 transition-colors';
    
    // Color code based on severity
    let percentClass = 'text-orange-400';
    if (device.memory_pct >= 95) {
      percentClass = 'text-red-400 font-bold';
    } else if (device.memory_pct >= 90) {
      percentClass = 'text-orange-400 font-semibold';
    }
    
    row.innerHTML = `
      <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-white">${escapeHtml(device.name)}</td>
      <td class="px-6 py-4 whitespace-nowrap text-sm text-right ${percentClass}">${device.memory_pct}%</td>
    `;
    
    tableBody.appendChild(row);
  });
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}
