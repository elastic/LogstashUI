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
        
        // Update Template Coverage Table
        updateDataQualityTable(data.data_quality.templates);
        
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
 * Category badge color mapping — used for both table badges and filter pills.
 */
const CATEGORY_COLORS = {
  'metrics':    'bg-blue-600/20 text-blue-300 border border-blue-600/40',
  'interface':  'bg-purple-600/20 text-purple-300 border border-purple-600/40',
  'routing':    'bg-teal-600/20 text-teal-300 border border-teal-600/40',
  'discovery':  'bg-green-600/20 text-green-300 border border-green-600/40',
  'traps':      'bg-yellow-600/20 text-yellow-300 border border-yellow-600/40',
};

/** Currently active filter category, or null for "all". */
let _activeCategoryFilter = null;

/** Full template data — kept so we can re-render on filter change. */
let _templateData = [];

/**
 * Return a styled badge for a given event.category value.
 */
function categoryBadge(category) {
  const classes = CATEGORY_COLORS[category] || 'bg-gray-600/20 text-gray-300 border border-gray-600/40';
  return `<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${classes}">${escapeHtml(category)}</span>`;
}

/**
 * Render template rows, respecting the active category filter.
 */
function renderTemplateRows() {
  const tableBody = document.getElementById('dataQualityTableBody');
  tableBody.innerHTML = '';

  const visible = _activeCategoryFilter
    ? _templateData.filter(t => t.categories && t.categories.includes(_activeCategoryFilter))
    : _templateData;

  if (visible.length === 0) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td colspan="2" class="px-6 py-8 text-center text-sm text-gray-500 italic">
        No templates match the selected category.
      </td>
    `;
    tableBody.appendChild(tr);
    return;
  }

  visible.forEach(tpl => {
    const row = document.createElement('tr');
    row.className = 'hover:bg-gray-700/50 transition-colors';

    const badges = tpl.categories && tpl.categories.length > 0
      ? tpl.categories.map(categoryBadge).join(' ')
      : '<span class="text-gray-500 italic text-xs">none</span>';

    row.innerHTML = `
      <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-white">${escapeHtml(tpl.template_display_name || formatDisplayName(tpl.template_name))}</td>
      <td class="px-6 py-4 text-sm">
        <div class="flex flex-wrap gap-1.5">${badges}</div>
      </td>
    `;
    tableBody.appendChild(row);
  });
}

/**
 * Populate the category filter custom dropdown from the loaded template data.
 */
function buildCategoryFilter(templates) {
  const wrapper = document.getElementById('templateCategoryFilterWrapper');
  const optionsEl = document.getElementById('templateCategoryOptions');
  if (!wrapper || !optionsEl) return;

  const allCategories = [...new Set(
    templates.flatMap(t => t.categories || [])
  )].sort();

  if (allCategories.length === 0) {
    wrapper.classList.add('hidden');
    return;
  }

  // "All categories" entry + one per category
  const allOption = document.createElement('button');
  allOption.type = 'button';
  allOption.className = 'tpl-cat-option w-full text-left px-3 py-1.5 text-sm text-white hover:bg-gray-700/60 transition-colors';
  allOption.textContent = 'All categories';
  allOption.dataset.value = '';
  allOption.addEventListener('click', () => _selectTplCategory(''));
  optionsEl.appendChild(allOption);

  allCategories.forEach(c => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'tpl-cat-option w-full text-left px-3 py-1.5 text-sm text-white hover:bg-gray-700/60 transition-colors';
    btn.textContent = c;
    btn.dataset.value = c;
    btn.addEventListener('click', () => _selectTplCategory(c));
    optionsEl.appendChild(btn);
  });

  _updateTplCategoryLabel();
  wrapper.classList.remove('hidden');
}

function _selectTplCategory(value) {
  _activeCategoryFilter = value || null;
  _updateTplCategoryLabel();
  // Close the dropdown
  const dd = document.getElementById('templateCategoryDropdown');
  if (dd) dd.classList.add('hidden');
  renderTemplateRows();
}

function _updateTplCategoryLabel() {
  const label = document.getElementById('templateCategoryFilterLabel');
  if (!label) return;
  label.textContent = _activeCategoryFilter || 'All categories';
}

function toggleTplCategoryDropdown(event) {
  event.stopPropagation();
  const dd = document.getElementById('templateCategoryDropdown');
  if (dd) dd.classList.toggle('hidden');
}

// Close when clicking outside
document.addEventListener('click', function(e) {
  const wrapper = document.getElementById('templateCategoryFilterWrapper');
  if (wrapper && !wrapper.contains(e.target)) {
    const dd = document.getElementById('templateCategoryDropdown');
    if (dd) dd.classList.add('hidden');
  }
});

/**
 * Called by the select's onchange handler (kept for compatibility).
 */
function onCategoryFilterChange(value) {
  _selectTplCategory(value);
}

/**
 * Update the template coverage table.
 */
function updateDataQualityTable(templates) {
  const loadingDiv = document.getElementById('dataQualityLoading');
  const tableContainer = document.getElementById('dataQualityTableContainer');
  const emptyState = document.getElementById('dataQualityEmpty');

  loadingDiv.classList.add('hidden');
  _activeCategoryFilter = null;
  _updateTplCategoryLabel();

  if (!templates || templates.length === 0) {
    emptyState.classList.remove('hidden');
    tableContainer.classList.add('hidden');
    return;
  }

  _templateData = templates;
  tableContainer.classList.remove('hidden');
  emptyState.classList.add('hidden');

  buildCategoryFilter(templates);
  renderTemplateRows();
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

