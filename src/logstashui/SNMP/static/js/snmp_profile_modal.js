/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// SNMP Profile Modal JavaScript

// Global variable to store normalizer definitions
let normalizerDefinitions = {};
let normalizerDefinitionsLoaded = false;

// Load normalizer definitions on page load
document.addEventListener('DOMContentLoaded', function() {
  loadNormalizerDefinitions();
});

// Function to load normalizer definitions
async function loadNormalizerDefinitions() {
  try {
    const response = await fetch('/SNMP/GetNormalizerDefinitions/');
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = await response.json();
    if (data.success) {
      normalizerDefinitions = data.normalizers;
      normalizerDefinitionsLoaded = true;
      console.log('Normalizer definitions loaded:', normalizerDefinitions);
    } else {
      throw new Error(data.message || 'Failed to load normalizer definitions');
    }
  } catch (error) {
    console.error('Error loading normalizer definitions:', error);
    normalizerDefinitionsLoaded = false;
    // Show error to user
    if (typeof showToast === 'function') {
      showToast('Failed to load normalizer definitions', 'error');
    }
  }
}

// Ensure normalizer definitions are loaded before using them
async function ensureNormalizerDefinitionsLoaded() {
  if (!normalizerDefinitionsLoaded) {
    await loadNormalizerDefinitions();
  }
}

// Open modal for adding new profile
document.addEventListener('DOMContentLoaded', function() {
  const addProfileBtn = document.getElementById('addProfileBtn');
  if (addProfileBtn) {
    addProfileBtn.addEventListener('click', function() {
      openProfileModal();
    });
  }
});

// Open profile modal with pre-filled data (for cloning)
function openProfileModalWithData(data) {
  const modal = document.getElementById('profileFormModal');
  const form = document.getElementById('profileForm');
  const modalTitle = document.getElementById('profileModalTitle');
  const saveBtn = document.getElementById('profileSaveBtn');
  
  // Reset form
  form.reset();
  document.getElementById('profileErrorContainer').innerHTML = '';
  
  // Clear all containers including tables and normalizers
  clearKVContainer('get');
  clearKVContainer('walk');
  clearTableContainer();
  clearNormalizersContainer();
  
  // Set to add mode
  modalTitle.textContent = 'Add SNMP Profile';
  document.getElementById('profileOriginalName').value = '';
  document.getElementById('profileIsOfficial').value = 'false';
  
  // Enable all fields
  document.getElementById('profileName').readOnly = false;
  document.getElementById('profileDescription').readOnly = false;
  document.getElementById('profileVendor').readOnly = false;
  document.getElementById('profileProduct').readOnly = false;
  saveBtn.style.display = '';
  
  // Enable add buttons
  const addButtons = modal.querySelectorAll('button[onclick^="addKVPair"]');
  addButtons.forEach(btn => {
    btn.disabled = false;
    btn.style.display = '';
  });
  
  // Show Add Table button
  const addTableBtn = modal.querySelector('button[onclick="addTable()"]');
  if (addTableBtn) {
    addTableBtn.disabled = false;
    addTableBtn.style.display = '';
  }
  
  // Fill in the data
  document.getElementById('profileName').value = data.name || '';
  document.getElementById('profileDescription').value = data.description || '';
  document.getElementById('profileVendor').value = data.vendor || '';
  document.getElementById('profileProduct').value = data.product || '';
  
  // Load Get section
  if (data.profile_data && data.profile_data.get) {
    Object.entries(data.profile_data.get).forEach(([key, value]) => {
      addKVPair('get', key, value, false);
    });
  }
  
  // Load Walk section
  if (data.profile_data && data.profile_data.walk && Object.keys(data.profile_data.walk).length > 0) {
    Object.entries(data.profile_data.walk).forEach(([key, value]) => {
      addKVPair('walk', key, value, false);
    });
  }
  
  // Load Table section
  if (data.profile_data && data.profile_data.table) {
    Object.entries(data.profile_data.table).forEach(([tableName, tableData]) => {
      if (tableData && tableData.columns && Object.keys(tableData.columns).length > 0) {
        addTable(tableName, tableData.columns, false);
      }
    });
  }
  
  // Load Normalizers section
  if (data.normalizers && Array.isArray(data.normalizers) && data.normalizers.length > 0) {
    data.normalizers.forEach(normalizerData => {
      addNormalizer(normalizerData, false);
    });
  }
  
  modal.classList.remove('hidden');
}

// Open profile modal (for add, edit, or view)
function openProfileModal(profileName = null, isOfficial = false, viewMode = false) {
  const modal = document.getElementById('profileFormModal');
  const form = document.getElementById('profileForm');
  const modalTitle = document.getElementById('profileModalTitle');
  const saveBtn = document.getElementById('profileSaveBtn');
  
  // Reset form
  form.reset();
  document.getElementById('profileErrorContainer').innerHTML = '';
  
  // Clear all containers including tables and normalizers
  clearKVContainer('get');
  clearKVContainer('walk');
  clearTableContainer();
  clearNormalizersContainer();
  
  if (profileName) {
    // Load existing profile
    modalTitle.textContent = viewMode ? 'View Profile' : 'Edit Profile';
    document.getElementById('profileOriginalName').value = profileName;
    document.getElementById('profileIsOfficial').value = isOfficial ? 'true' : 'false';
    
    // Disable fields for official profiles or view mode
    const isReadOnly = isOfficial || viewMode;
    document.getElementById('profileName').readOnly = isReadOnly;
    document.getElementById('profileDescription').readOnly = isReadOnly;
    document.getElementById('profileVendor').readOnly = isReadOnly;
    document.getElementById('profileProduct').readOnly = isReadOnly;
    
    // Hide/disable save button for official profiles or view mode
    if (isReadOnly) {
      saveBtn.style.display = 'none';
    } else {
      saveBtn.style.display = '';
    }
    
    // Disable add buttons for official profiles or view mode
    const addButtons = modal.querySelectorAll('button[onclick^="addKVPair"]');
    addButtons.forEach(btn => {
      btn.disabled = isReadOnly;
      btn.style.display = isReadOnly ? 'none' : '';
    });
    
    // Hide Add Table button for official profiles or view mode
    const addTableBtn = modal.querySelector('button[onclick="addTable()"]');
    if (addTableBtn) {
      addTableBtn.disabled = isReadOnly;
      addTableBtn.style.display = isReadOnly ? 'none' : '';
    }
    
    // Load profile data
    loadProfileData(profileName, isOfficial, isReadOnly);
  } else {
    // New profile
    modalTitle.textContent = 'Add SNMP Profile';
    document.getElementById('profileName').readOnly = false;
    document.getElementById('profileDescription').readOnly = false;
    document.getElementById('profileVendor').readOnly = false;
    document.getElementById('profileProduct').readOnly = false;
    saveBtn.style.display = '';
    
    // Enable add buttons
    const addButtons = modal.querySelectorAll('button[onclick^="addKVPair"]');
    addButtons.forEach(btn => {
      btn.disabled = false;
      btn.style.display = '';
    });
    
    // Show Add Table button
    const addTableBtn = modal.querySelector('button[onclick="addTable()"]');
    if (addTableBtn) {
      addTableBtn.disabled = false;
      addTableBtn.style.display = '';
    }
  }
  
  modal.classList.remove('hidden');
}

// Close profile modal
function closeProfileModal() {
  document.getElementById('profileFormModal').classList.add('hidden');
  document.getElementById('profileForm').reset();
  document.getElementById('profileErrorContainer').innerHTML = '';
}

// Load profile data from server
function loadProfileData(profileName, isOfficial, isReadOnly) {
  const endpoint = isOfficial 
    ? `/SNMP/GetOfficialProfile/${profileName}/`
    : `/SNMP/GetProfile/${profileName}/`;
  
  fetch(endpoint)
    .then(response => response.json())
    .then(data => {
      // Set basic fields
      document.getElementById('profileName').value = data.name || profileName;
      document.getElementById('profileDescription').value = data.description || '';
      document.getElementById('profileVendor').value = data.vendor || '';
      document.getElementById('profileProduct').value = data.product || '';
      
      // Load Get section
      if (data.profile_data && data.profile_data.get) {
        Object.entries(data.profile_data.get).forEach(([key, value]) => {
          addKVPair('get', key, value, isReadOnly);
        });
      }
      
      // Load Walk section
      if (data.profile_data && data.profile_data.walk && Object.keys(data.profile_data.walk).length > 0) {
        Object.entries(data.profile_data.walk).forEach(([key, value]) => {
          addKVPair('walk', key, value, isReadOnly);
        });
      }
      
      // Load Table section
      if (data.profile_data && data.profile_data.table) {
        Object.entries(data.profile_data.table).forEach(([tableName, tableData]) => {
          // Only add table if it has actual columns with data
          if (tableData && tableData.columns && Object.keys(tableData.columns).length > 0) {
            addTable(tableName, tableData.columns, isReadOnly);
          }
        });
      }
      
      // Load Normalizers section
      if (data.normalizers && Array.isArray(data.normalizers) && data.normalizers.length > 0) {
        data.normalizers.forEach(normalizerData => {
          addNormalizer(normalizerData, isReadOnly);
        });
      }
    })
    .catch(error => {
      console.error('Error loading profile:', error);
      showToast('Error loading profile: ' + error, 'error');
    });
}

// Add a KV pair to a section (for get and walk)
function addKVPair(section, key = '', value = '', isReadOnly = false) {
  const container = document.getElementById(`${section}Container`);
  const emptyMessage = document.getElementById(`${section}EmptyMessage`);
  
  // Hide empty message
  if (emptyMessage) {
    emptyMessage.style.display = 'none';
  }
  
  // Show walk warning if adding to walk section
  if (section === 'walk') {
    showWalkWarning();
  }
  
  // Create KV pair element
  const kvPair = document.createElement('div');
  kvPair.className = 'flex gap-2 items-start kv-pair';
  kvPair.innerHTML = `
    <div class="flex-1">
      <input type="text" 
             class="input input-bordered input-sm w-full kv-key" 
             placeholder="Field name (e.g., sysName)" 
             value="${key}"
             ${isReadOnly ? 'readonly' : ''}
             ${section === 'get' && !isReadOnly ? 'onchange="refreshNormalizerFieldDropdowns()"' : ''}>
    </div>
    <div class="flex-1">
      <input type="text" 
             class="input input-bordered input-sm w-full font-mono kv-value" 
             placeholder="OID (e.g., 1.3.6.1.2.1.1.5.0)" 
             value="${value}"
             ${isReadOnly ? 'readonly' : ''}>
    </div>
    <button type="button" 
            onclick="removeKVPair(this, '${section}')" 
            class="btn btn-ghost btn-sm btn-circle text-red-400 hover:bg-red-900/20"
            ${isReadOnly ? 'disabled style="display:none;"' : ''}>
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
      </svg>
    </button>
  `;
  
  container.appendChild(kvPair);
}

// Show walk warning
function showWalkWarning() {
  const walkContainer = document.getElementById('walkContainer');
  let warning = document.getElementById('walkWarning');
  
  if (!warning) {
    warning = document.createElement('div');
    warning.id = 'walkWarning';
    warning.className = 'mb-3 p-3 bg-yellow-900/30 border border-yellow-600/50 rounded-lg flex items-start gap-2';
    warning.innerHTML = `
      <svg class="w-5 h-5 text-yellow-500 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
        <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
      </svg>
      <div class="text-sm text-yellow-200">
        Walk queries are best for discovery, not ongoing monitoring. For production polling, use Get or Table queries to avoid noisy data and mapping growth.
      </div>
    `;
    walkContainer.parentElement.insertBefore(warning, walkContainer);
  }
}

// Hide walk warning
function hideWalkWarning() {
  const warning = document.getElementById('walkWarning');
  if (warning) {
    warning.remove();
  }
}

// Remove a KV pair
function removeKVPair(button, section) {
  const kvPair = button.closest('.kv-pair');
  const container = document.getElementById(`${section}Container`);
  const emptyMessage = document.getElementById(`${section}EmptyMessage`);
  
  kvPair.remove();
  
  // Show empty message if no more pairs
  const remainingPairs = container.querySelectorAll('.kv-pair');
  if (remainingPairs.length === 0 && emptyMessage) {
    emptyMessage.style.display = '';
    
    // Hide walk warning if no more walk items
    if (section === 'walk') {
      hideWalkWarning();
    }
  }
  
  // Refresh normalizer field dropdowns if Get section changed
  if (section === 'get') {
    refreshNormalizerFieldDropdowns();
  }
}

// Clear a KV container
function clearKVContainer(section) {
  const container = document.getElementById(`${section}Container`);
  const emptyMessage = document.getElementById(`${section}EmptyMessage`);
  
  // Remove all KV pairs
  const kvPairs = container.querySelectorAll('.kv-pair');
  kvPairs.forEach(pair => pair.remove());
  
  // Show empty message
  if (emptyMessage) {
    emptyMessage.style.display = '';
  }
}

// Clear table container
function clearTableContainer() {
  const container = document.getElementById('tableContainer');
  const emptyMessage = document.getElementById('tableEmptyMessage');
  
  // Remove all tables
  const tables = container.querySelectorAll('.table-group');
  tables.forEach(table => table.remove());
  
  // Show empty message
  if (emptyMessage) {
    emptyMessage.style.display = '';
  }
}

// Add a table with columns
function addTable(tableName = '', columns = {}, isReadOnly = false) {
  const container = document.getElementById('tableContainer');
  const emptyMessage = document.getElementById('tableEmptyMessage');
  
  // Hide empty message
  if (emptyMessage) {
    emptyMessage.style.display = 'none';
  }
  
  // Create unique ID for this table
  const tableId = 'table_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
  
  // Create table element
  const tableElement = document.createElement('div');
  tableElement.className = 'table-group border border-gray-600 rounded-lg p-4 mb-3';
  tableElement.dataset.tableId = tableId;
  tableElement.innerHTML = `
    <div class="flex justify-between items-center mb-3">
      <input type="text" 
             class="input input-bordered input-sm w-64 table-name" 
             placeholder="Table name (e.g., ifTable)" 
             value="${tableName}"
             ${isReadOnly ? 'readonly' : ''}
             ${!isReadOnly ? 'onchange="refreshNormalizerFieldDropdowns()"' : ''}>
      <button type="button" 
              onclick="removeTable(this)" 
              class="btn btn-ghost btn-sm text-red-400 hover:bg-red-900/20"
              ${isReadOnly ? 'disabled style="display:none;"' : ''}>
        <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
        </svg>
        Remove Table
      </button>
    </div>
    <div class="ml-4">
      <div class="flex justify-between items-center mb-2">
        <label class="text-xs text-gray-400">Columns (Field Name → OID)</label>
        <button type="button" 
                onclick="addTableColumn(this)" 
                class="btn btn-xs btn-ghost text-primary"
                ${isReadOnly ? 'disabled style="display:none;"' : ''}>
          <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
          </svg>
          Add Column
        </button>
      </div>
      <div class="table-columns space-y-2">
        <!-- Columns will be added here -->
      </div>
    </div>
  `;
  
  container.appendChild(tableElement);
  
  // Add existing columns if provided
  if (columns && Object.keys(columns).length > 0) {
    const columnsContainer = tableElement.querySelector('.table-columns');
    Object.entries(columns).forEach(([columnName, oid]) => {
      addTableColumnToContainer(columnsContainer, columnName, oid, isReadOnly);
    });
  } else {
    // Show empty message for read-only tables with no columns
    const columnsContainer = tableElement.querySelector('.table-columns');
    if (isReadOnly) {
      columnsContainer.innerHTML = '<p class="text-gray-500 text-sm text-center py-2">No columns defined</p>';
    } else {
      // Add one empty column for new tables
      addTableColumnToContainer(columnsContainer, '', '', false);
    }
  }
}

// Add a column to a table
function addTableColumn(button) {
  const tableElement = button.closest('.table-group');
  const columnsContainer = tableElement.querySelector('.table-columns');
  
  // Remove empty message if it exists
  const emptyMessage = columnsContainer.querySelector('p');
  if (emptyMessage) {
    emptyMessage.remove();
  }
  
  addTableColumnToContainer(columnsContainer, '', '', false);
}

// Add a column to a specific container
function addTableColumnToContainer(container, columnName = '', oid = '', isReadOnly = false) {
  // Create wrapper div
  const column = document.createElement('div');
  column.className = 'flex gap-2 items-start table-column';
  column.style.display = 'flex';
  column.style.visibility = 'visible';
  
  // Create first input wrapper
  const wrapper1 = document.createElement('div');
  wrapper1.className = 'flex-1';
  const input1 = document.createElement('input');
  input1.type = 'text';
  input1.className = 'input input-bordered input-sm w-full column-name';
  input1.placeholder = 'Column name (e.g., ifIndex)';
  input1.value = columnName;
  if (isReadOnly) input1.readOnly = true;
  if (!isReadOnly) input1.onchange = refreshNormalizerFieldDropdowns;
  wrapper1.appendChild(input1);
  
  // Create second input wrapper
  const wrapper2 = document.createElement('div');
  wrapper2.className = 'flex-1';
  const input2 = document.createElement('input');
  input2.type = 'text';
  input2.className = 'input input-bordered input-sm w-full font-mono column-oid';
  input2.placeholder = 'OID (e.g., 1.3.6.1.2.1.2.2.1.1)';
  input2.value = oid;
  if (isReadOnly) input2.readOnly = true;
  wrapper2.appendChild(input2);
  
  // Create remove button
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'btn btn-ghost btn-sm btn-circle text-red-400 hover:bg-red-900/20';
  button.onclick = function() { removeTableColumn(this); };
  if (isReadOnly) {
    button.disabled = true;
    button.style.display = 'none';
  }
  button.innerHTML = '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>';
  
  // Append all elements
  column.appendChild(wrapper1);
  column.appendChild(wrapper2);
  column.appendChild(button);
  
  container.appendChild(column);
}

// Remove a table column
function removeTableColumn(button) {
  const column = button.closest('.table-column');
  column.remove();
  
  // Refresh normalizer field dropdowns
  refreshNormalizerFieldDropdowns();
}

// Remove an entire table
function removeTable(button) {
  const tableElement = button.closest('.table-group');
  const container = document.getElementById('tableContainer');
  const emptyMessage = document.getElementById('tableEmptyMessage');
  
  tableElement.remove();
  
  // Show empty message if no more tables
  const remainingTables = container.querySelectorAll('.table-group');
  if (remainingTables.length === 0 && emptyMessage) {
    emptyMessage.style.display = '';
  }
  
  // Refresh normalizer field dropdowns
  refreshNormalizerFieldDropdowns();
}

// Serialize KV pairs from a section (for get and walk)
function serializeKVSection(section) {
  const container = document.getElementById(`${section}Container`);
  const kvPairs = container.querySelectorAll('.kv-pair');
  const result = {};
  
  kvPairs.forEach(pair => {
    const key = pair.querySelector('.kv-key').value.trim();
    const value = pair.querySelector('.kv-value').value.trim();
    
    if (key && value) {
      result[key] = value;
    }
  });
  
  return Object.keys(result).length > 0 ? result : null;
}

// Serialize tables
function serializeTableSection() {
  const container = document.getElementById('tableContainer');
  const tables = container.querySelectorAll('.table-group');
  const result = {};
  
  tables.forEach(table => {
    const tableName = table.querySelector('.table-name').value.trim();
    if (!tableName) return;
    
    const columns = {};
    const columnElements = table.querySelectorAll('.table-column');
    
    columnElements.forEach(col => {
      const columnName = col.querySelector('.column-name').value.trim();
      const oid = col.querySelector('.column-oid').value.trim();
      
      if (columnName && oid) {
        columns[columnName] = oid;
      }
    });
    
    if (Object.keys(columns).length > 0) {
      result[tableName] = { columns: columns };
    }
  });
  
  return Object.keys(result).length > 0 ? result : null;
}

// Add a normalizer
async function addNormalizer(normalizerData = null, isReadOnly = false) {
  // Ensure normalizer definitions are loaded
  await ensureNormalizerDefinitionsLoaded();
  
  const container = document.getElementById('normalizersContainer');
  const emptyMessage = document.getElementById('normalizersEmptyMessage');
  
  if (emptyMessage) {
    emptyMessage.style.display = 'none';
  }
  
  const normalizerId = 'normalizer_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
  
  const normalizerElement = document.createElement('div');
  normalizerElement.className = 'normalizer-item border border-gray-600 rounded-lg p-4 mb-3';
  normalizerElement.dataset.normalizerId = normalizerId;
  
  const operation = normalizerData?.operation || '';
  
  // Build operation options
  const operationOptions = Object.keys(normalizerDefinitions).map(op => 
    `<option value="${op}" ${op === operation ? 'selected' : ''}>${normalizerDefinitions[op].label}</option>`
  ).join('');
  
  normalizerElement.innerHTML = `
    <div class="flex justify-between items-start mb-3">
      <h4 class="text-sm font-medium text-gray-300">Normalizer Configuration</h4>
      <button type="button" 
              onclick="removeNormalizer(this)" 
              class="btn btn-ghost btn-sm text-red-400 hover:bg-red-900/20"
              ${isReadOnly ? 'disabled style="display:none;"' : ''}>
        <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
        </svg>
        Remove
      </button>
    </div>
    
    <div class="space-y-3">
      <div>
        <label class="block text-xs text-gray-400 mb-1">Operation</label>
        <select class="select select-bordered select-sm w-full normalizer-operation" 
                onchange="onNormalizerOperationChange(this)"
                ${isReadOnly ? 'disabled' : ''}>
          <option value="">Select operation...</option>
          ${operationOptions}
        </select>
      </div>
      
      <div class="normalizer-dynamic-fields">
        <!-- Dynamic fields will be inserted here -->
      </div>
    </div>
  `;
  
  container.appendChild(normalizerElement);
  
  // If loading existing data, populate the fields
  if (operation && normalizerData) {
    const selectElement = normalizerElement.querySelector('.normalizer-operation');
    onNormalizerOperationChange(selectElement, normalizerData, isReadOnly);
  }
}

// Generate HTML for normalizer parameters based on operation
function generateNormalizerParamsHTML(operation, params = {}, isReadOnly = false) {
  if (!normalizerDefinitions[operation]) {
    return '<p class="text-gray-500 text-xs">Unknown operation</p>';
  }
  
  const opDef = normalizerDefinitions[operation];
  const inputs = opDef.inputs || {};
  
  if (Object.keys(inputs).length === 0) {
    return '<p class="text-gray-500 text-xs">No parameters required</p>';
  }
  
  let html = '<div class="space-y-2">';
  
  for (const [paramName, paramDef] of Object.entries(inputs)) {
    const value = params[paramName] !== undefined ? params[paramName] : (paramDef.default || '');
    
    html += `
      <div>
        <label class="block text-xs text-gray-400 mb-1">${paramDef.description || paramName}</label>
        <input type="${paramDef.type === 'float' ? 'number' : 'text'}" 
               class="input input-bordered input-sm w-full normalizer-param" 
               data-param-name="${paramName}"
               placeholder="${paramDef.default || ''}"
               value="${value}"
               ${paramDef.type === 'float' ? 'step="any"' : ''}
               ${isReadOnly ? 'readonly' : ''}>
      </div>
    `;
  }
  
  html += '</div>';
  return html;
}

// Get available fields from current profile data based on scope
function getAvailableFieldsForScope(scope) {
  const fields = [];
  
  if (scope === 'get') {
    // Get fields from Get section
    const getContainer = document.getElementById('getContainer');
    const kvPairs = getContainer.querySelectorAll('.kv-pair');
    kvPairs.forEach(pair => {
      const key = pair.querySelector('.kv-key').value.trim();
      if (key) {
        fields.push(key);
      }
    });
  } else if (scope === 'table') {
    // Get fields from Table columns
    const tableContainer = document.getElementById('tableContainer');
    const tables = tableContainer.querySelectorAll('.table-group');
    tables.forEach(table => {
      const tableName = table.querySelector('.table-name').value.trim();
      if (tableName) {
        const columns = table.querySelectorAll('.table-column');
        columns.forEach(col => {
          const columnName = col.querySelector('.column-name').value.trim();
          if (columnName) {
            fields.push(`${tableName}.${columnName}`);
          }
        });
      }
    });
  }
  
  return fields;
}

// Handle normalizer operation change - show appropriate fields based on operation
function onNormalizerOperationChange(selectElement, existingData = null, isReadOnly = false) {
  const normalizerItem = selectElement.closest('.normalizer-item');
  const dynamicFieldsContainer = normalizerItem.querySelector('.normalizer-dynamic-fields');
  const operation = selectElement.value;
  
  if (!operation) {
    dynamicFieldsContainer.innerHTML = '';
    return;
  }
  
  const opDef = normalizerDefinitions[operation];
  if (!opDef) {
    dynamicFieldsContainer.innerHTML = '<p class="text-gray-500 text-xs">Unknown operation</p>';
    return;
  }
  
  // Get applicable scopes
  const appliesTo = opDef.applies_to || [];
  const existingScope = existingData?.target?.scope || '';
  
  // Determine initial scope
  let scope = existingScope;
  if (!scope || !appliesTo.includes(scope === 'table' ? 'table_column' : scope)) {
    // Default to first applicable scope
    if (appliesTo.includes('get')) {
      scope = 'get';
    } else if (appliesTo.includes('table_column')) {
      scope = 'table';
    }
  }
  
  // Get existing values if provided
  const selectedField = existingData?.target?.field || '';
  const params = existingData?.params || {};
  
  let html = '';
  
  // Add scope selector if multiple scopes are available
  if (appliesTo.length > 1) {
    html += `
      <div>
        <label class="block text-xs text-gray-400 mb-1">Scope</label>
        <select class="select select-bordered select-sm w-full normalizer-scope" 
                onchange="onNormalizerScopeChange(this)"
                ${isReadOnly ? 'disabled' : ''}>
          ${appliesTo.map(scopeType => {
            const scopeValue = scopeType === 'table_column' ? 'table' : scopeType;
            const scopeLabel = scopeType === 'table_column' ? 'Table Column' : 'Get';
            return `<option value="${scopeValue}" ${scopeValue === scope ? 'selected' : ''}>${scopeLabel}</option>`;
          }).join('')}
        </select>
      </div>
    `;
  }
  
  // Add target field selector only if operation has a target field
  const hasTargetField = opDef.has_target_field !== false; // Default to true if not specified
  if (hasTargetField) {
    html += renderNormalizerFieldSelector(scope, selectedField, isReadOnly);
  }
  
  // Add parameter inputs
  const inputs = opDef.inputs || {};
  if (Object.keys(inputs).length > 0) {
    html += '<div class="space-y-2">';
    for (const [paramName, paramDef] of Object.entries(inputs)) {
      const value = params[paramName] !== undefined ? params[paramName] : (paramDef.default || '');
      
      // Check if this input is a field selector
      if (paramDef.type === 'field_selector') {
        const availableFields = getAvailableFieldsForScope(scope);
        html += `
          <div>
            <label class="block text-xs text-gray-400 mb-1">${paramDef.description || paramName}</label>
            <select class="select select-bordered select-sm w-full normalizer-param" 
                    data-param-name="${paramName}"
                    ${isReadOnly ? 'disabled' : ''}>
              <option value="">Select field...</option>
              ${availableFields.map(field => 
                `<option value="${field}" ${field === value ? 'selected' : ''}>${field}</option>`
              ).join('')}
            </select>
          </div>
        `;
      } else {
        // Regular input field
        html += `
          <div>
            <label class="block text-xs text-gray-400 mb-1">${paramDef.description || paramName}</label>
            <input type="${paramDef.type === 'float' ? 'number' : 'text'}" 
                   class="input input-bordered input-sm w-full normalizer-param" 
                   data-param-name="${paramName}"
                   placeholder="${paramDef.default || ''}"
                   value="${value}"
                   ${paramDef.type === 'float' ? 'step="any"' : ''}
                   ${isReadOnly ? 'readonly' : ''}>
          </div>
        `;
      }
    }
    html += '</div>';
  }
  
  dynamicFieldsContainer.innerHTML = html;
}

// Render field selector for a given scope
function renderNormalizerFieldSelector(scope, selectedField = '', isReadOnly = false) {
  const availableFields = getAvailableFieldsForScope(scope);
  
  const placeholderText = availableFields.length === 0 
    ? `No ${scope === 'get' ? 'Get' : 'Table'} fields defined yet...`
    : 'Select field...';
  
  return `
    <div>
      <label class="block text-xs text-gray-400 mb-1">Target Field</label>
      <select class="select select-bordered select-sm w-full normalizer-field" 
              data-scope="${scope}"
              ${isReadOnly ? 'disabled' : ''}>
        <option value="">${placeholderText}</option>
        ${availableFields.map(field => 
          `<option value="${field}" ${field === selectedField ? 'selected' : ''}>${field}</option>`
        ).join('')}
      </select>
    </div>
  `;
}

// Handle scope change - refresh field dropdown
function onNormalizerScopeChange(selectElement) {
  const normalizerItem = selectElement.closest('.normalizer-item');
  const dynamicFieldsContainer = normalizerItem.querySelector('.normalizer-dynamic-fields');
  const scope = selectElement.value;
  
  // Find and replace the field selector
  const fieldSelectorContainer = dynamicFieldsContainer.querySelector('.normalizer-field')?.closest('div');
  if (fieldSelectorContainer) {
    const newFieldSelector = document.createElement('div');
    newFieldSelector.innerHTML = renderNormalizerFieldSelector(scope, '', false);
    fieldSelectorContainer.replaceWith(newFieldSelector.firstElementChild);
  }
}

// Refresh all normalizer field dropdowns (called when Get/Table fields change)
function refreshNormalizerFieldDropdowns() {
  const normalizers = document.querySelectorAll('.normalizer-item');
  normalizers.forEach(normalizerItem => {
    const fieldSelect = normalizerItem.querySelector('.normalizer-field');
    if (fieldSelect) {
      const scope = fieldSelect.dataset.scope;
      const currentValue = fieldSelect.value;
      const availableFields = getAvailableFieldsForScope(scope);
      
      // Rebuild options
      fieldSelect.innerHTML = '<option value="">Select field...</option>' +
        availableFields.map(field => 
          `<option value="${field}" ${field === currentValue ? 'selected' : ''}>${field}</option>`
        ).join('');
    }
  });
}

// Remove a normalizer
function removeNormalizer(button) {
  const normalizerItem = button.closest('.normalizer-item');
  const container = document.getElementById('normalizersContainer');
  const emptyMessage = document.getElementById('normalizersEmptyMessage');
  
  normalizerItem.remove();
  
  const remainingNormalizers = container.querySelectorAll('.normalizer-item');
  if (remainingNormalizers.length === 0 && emptyMessage) {
    emptyMessage.style.display = '';
  }
}

// Clear normalizers container
function clearNormalizersContainer() {
  const container = document.getElementById('normalizersContainer');
  const emptyMessage = document.getElementById('normalizersEmptyMessage');
  
  const normalizers = container.querySelectorAll('.normalizer-item');
  normalizers.forEach(normalizer => normalizer.remove());
  
  if (emptyMessage) {
    emptyMessage.style.display = '';
  }
}

// Serialize normalizers
function serializeNormalizers() {
  const container = document.getElementById('normalizersContainer');
  const normalizers = container.querySelectorAll('.normalizer-item');
  const result = [];
  
  normalizers.forEach(normalizerItem => {
    const operation = normalizerItem.querySelector('.normalizer-operation').value;
    if (!operation) return;
    
    const fieldSelect = normalizerItem.querySelector('.normalizer-field');
    const scopeSelect = normalizerItem.querySelector('.normalizer-scope');
    
    // Get scope - either from scope selector or from field selector's data attribute
    let scope = 'get';
    if (scopeSelect) {
      scope = scopeSelect.value;
    } else if (fieldSelect) {
      scope = fieldSelect.dataset.scope || 'get';
    }
    
    // Build target object
    const target = { scope: scope };
    
    // Add field to target only if there's a field selector
    if (fieldSelect) {
      const field = fieldSelect.value.trim();
      if (!field) return; // Skip if required field is empty
      target.field = field;
    }
    
    // Collect parameters
    const params = {};
    const paramInputs = normalizerItem.querySelectorAll('.normalizer-param');
    paramInputs.forEach(input => {
      const paramName = input.dataset.paramName;
      let value = input.value.trim();
      
      if (value) {
        if (input.type === 'number') {
          value = parseFloat(value);
        }
        params[paramName] = value;
      }
    });
    
    result.push({
      operation: operation,
      target: target,
      params: params
    });
  });
  
  return result.length > 0 ? result : null;
}

// Handle form submission
document.addEventListener('DOMContentLoaded', function() {
  const form = document.getElementById('profileForm');
  if (form) {
    form.addEventListener('submit', function(e) {
      e.preventDefault();
      
      const formData = new FormData(form);
      const profileName = formData.get('name');
      const originalName = formData.get('original_name');
      const isOfficial = formData.get('is_official') === 'true';
      
      // Don't allow saving official profiles
      if (isOfficial) {
        showToast('Official profiles cannot be edited', 'error');
        return;
      }
      
      // Serialize profile data
      const profileData = {
        name: profileName,
        description: formData.get('description'),
        vendor: formData.get('vendor'),
        product: formData.get('product'),
        profile_data: {}
      };
      
      // Add Get section
      const getSection = serializeKVSection('get');
      if (getSection) {
        profileData.profile_data.get = getSection;
      }
      
      // Add Walk section
      const walkSection = serializeKVSection('walk');
      if (walkSection) {
        profileData.profile_data.walk = walkSection;
      }
      
      // Add Table section
      const tableSection = serializeTableSection();
      if (tableSection) {
        profileData.profile_data.table = tableSection;
      }
      
      // Add Normalizers section
      const normalizers = serializeNormalizers();
      if (normalizers) {
        profileData.normalizers = normalizers;
      }
      
      // Validate that at least one section has data
      if (!getSection && !walkSection && !tableSection) {
        showErrorInModal('Please add at least one OID mapping (Get, Walk, or Table)');
        return;
      }
      
      // Determine endpoint
      const isEdit = originalName && originalName !== '';
      const endpoint = isEdit 
        ? `/SNMP/UpdateProfile/${originalName}/`
        : '/SNMP/AddProfile/';
      
      // Submit profile
      fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
        },
        body: JSON.stringify(profileData)
      })
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          if (typeof showToast === 'function') {
            showToast(isEdit ? 'Profile updated successfully!' : 'Profile created successfully!', 'success');
          }
          closeProfileModal();
          
          // Refresh profiles data without page reload
          if (typeof refreshProfilesData === 'function') {
            refreshProfilesData();
          }
        } else {
          showErrorInModal(data.message || 'Failed to save profile');
        }
      })
      .catch(error => {
        showErrorInModal(error.message || 'An error occurred while saving the profile');
      });
    });
  }
});
