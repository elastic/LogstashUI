// SNMP Profile Modal JavaScript

// Open modal for adding new profile
document.addEventListener('DOMContentLoaded', function() {
  const addProfileBtn = document.getElementById('addProfileBtn');
  if (addProfileBtn) {
    addProfileBtn.addEventListener('click', function() {
      openProfileModal();
    });
  }
});

// Open profile modal (for add, edit, or view)
function openProfileModal(profileName = null, isOfficial = false, viewMode = false) {
  const modal = document.getElementById('profileFormModal');
  const form = document.getElementById('profileForm');
  const modalTitle = document.getElementById('profileModalTitle');
  const saveBtn = document.getElementById('profileSaveBtn');
  
  // Reset form
  form.reset();
  document.getElementById('profileErrorContainer').innerHTML = '';
  
  // Clear all containers including tables
  clearKVContainer('get');
  clearKVContainer('walk');
  clearTableContainer();
  
  if (profileName) {
    // Load existing profile
    modalTitle.textContent = viewMode ? 'View Profile' : 'Edit Profile';
    document.getElementById('profileOriginalName').value = profileName;
    document.getElementById('profileIsOfficial').value = isOfficial ? 'true' : 'false';
    
    // Disable fields for official profiles or view mode
    const isReadOnly = isOfficial || viewMode;
    document.getElementById('profileName').readOnly = isReadOnly;
    document.getElementById('profileDescription').readOnly = isReadOnly;
    document.getElementById('profileType').disabled = isReadOnly;
    document.getElementById('profileVendor').readOnly = isReadOnly;
    
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
    document.getElementById('profileType').disabled = false;
    document.getElementById('profileVendor').readOnly = false;
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
    ? `/API/SNMP/GetOfficialProfile/${profileName}/`
    : `/API/SNMP/GetProfile/${profileName}/`;
  
  fetch(endpoint)
    .then(response => response.json())
    .then(data => {
      // Set basic fields
      document.getElementById('profileName').value = data.name || profileName;
      document.getElementById('profileDescription').value = data.description || '';
      document.getElementById('profileType').value = data.type || '';
      document.getElementById('profileVendor').value = data.vendor || '';
      
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
  
  // Show walk warning if adding to walk section AND we have actual content
  if (section === 'walk' && (key || value)) {
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
             ${isReadOnly ? 'readonly' : ''}>
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
        <strong>CAUTION:</strong> You may get better results by using a table instead of walk queries.
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
             ${isReadOnly ? 'readonly' : ''}>
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
        type: formData.get('type'),
        vendor: formData.get('vendor'),
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
      
      // Validate that at least one section has data
      if (!getSection && !walkSection && !tableSection) {
        showErrorInModal('Please add at least one OID mapping (Get, Walk, or Table)');
        return;
      }
      
      // Determine endpoint
      const isEdit = originalName && originalName !== '';
      const endpoint = isEdit 
        ? `/API/SNMP/UpdateProfile/${originalName}/`
        : '/API/SNMP/AddProfile/';
      
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
          setTimeout(() => window.location.reload(), 500);
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
