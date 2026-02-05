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
  
  // Clear all KV containers
  clearKVContainer('get');
  clearKVContainer('walk');
  clearKVContainer('table');
  
  if (profileName) {
    // Load existing profile
    modalTitle.textContent = viewMode ? 'View Profile' : 'Edit Profile';
    document.getElementById('profileOriginalName').value = profileName;
    document.getElementById('profileIsOfficial').value = isOfficial ? 'true' : 'false';
    
    // Disable fields for official profiles or view mode
    const isReadOnly = isOfficial || viewMode;
    document.getElementById('profileName').disabled = isReadOnly;
    document.getElementById('profileDescription').disabled = isReadOnly;
    
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
    
    // Load profile data
    loadProfileData(profileName, isOfficial, isReadOnly);
  } else {
    // New profile
    modalTitle.textContent = 'Add SNMP Profile';
    document.getElementById('profileName').disabled = false;
    document.getElementById('profileDescription').disabled = false;
    saveBtn.style.display = '';
    
    // Enable add buttons
    const addButtons = modal.querySelectorAll('button[onclick^="addKVPair"]');
    addButtons.forEach(btn => {
      btn.disabled = false;
      btn.style.display = '';
    });
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
      
      // Load Get section
      if (data.profile_data && data.profile_data.get) {
        Object.entries(data.profile_data.get).forEach(([key, value]) => {
          addKVPair('get', key, value, isReadOnly);
        });
      }
      
      // Load Walk section
      if (data.profile_data && data.profile_data.walk) {
        Object.entries(data.profile_data.walk).forEach(([key, value]) => {
          addKVPair('walk', key, value, isReadOnly);
        });
      }
      
      // Load Table section
      if (data.profile_data && data.profile_data.table) {
        Object.entries(data.profile_data.table).forEach(([key, value]) => {
          addKVPair('table', key, value, isReadOnly);
        });
      }
    })
    .catch(error => {
      console.error('Error loading profile:', error);
      showToast('Error loading profile: ' + error, 'error');
    });
}

// Add a KV pair to a section
function addKVPair(section, key = '', value = '', isReadOnly = false) {
  const container = document.getElementById(`${section}Container`);
  const emptyMessage = document.getElementById(`${section}EmptyMessage`);
  
  // Hide empty message
  if (emptyMessage) {
    emptyMessage.style.display = 'none';
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
             ${isReadOnly ? 'disabled' : ''}>
    </div>
    <div class="flex-1">
      <input type="text" 
             class="input input-bordered input-sm w-full font-mono kv-value" 
             placeholder="OID (e.g., 1.3.6.1.2.1.1.5.0)" 
             value="${value}"
             ${isReadOnly ? 'disabled' : ''}>
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

// Serialize KV pairs from a section
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
      const tableSection = serializeKVSection('table');
      if (tableSection) {
        profileData.profile_data.table = tableSection;
      }
      
      // Validate that at least one section has data
      if (!getSection && !walkSection && !tableSection) {
        showToast('Please add at least one OID mapping (Get, Walk, or Table)', 'error');
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
          showToast(isEdit ? 'Profile updated successfully!' : 'Profile created successfully!', 'success');
          closeProfileModal();
          setTimeout(() => window.location.reload(), 500);
        } else {
          const errorContainer = document.getElementById('profileErrorContainer');
          errorContainer.innerHTML = `
            <div class="p-4 mb-4 text-red-700 bg-red-100 border border-red-300 rounded-lg">
              <h3 class="font-bold mb-2">Error</h3>
              <p class="text-sm">${data.message || 'Failed to save profile'}</p>
            </div>
          `;
        }
      })
      .catch(error => {
        const errorContainer = document.getElementById('profileErrorContainer');
        errorContainer.innerHTML = `
          <div class="p-4 mb-4 text-red-700 bg-red-100 border border-red-300 rounded-lg">
            <h3 class="font-bold mb-2">Error</h3>
            <p class="text-sm">${error.message || 'An error occurred while saving the profile'}</p>
          </div>
        `;
      });
    });
  }
});
