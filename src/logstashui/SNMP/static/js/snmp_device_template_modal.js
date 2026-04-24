/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// SNMP Device Template Modal JavaScript

// Track if device template modal is open
let deviceTemplateModalIsOpen = false;

// Track selected profiles
let selectedTemplateProfiles = [];

// Temporary selection for the profile selector modal
let tempSelectedProfiles = [];

// Open device template modal (for add, edit, or view)
function openDeviceTemplateModal(templateId = null, viewMode = false) {
  const modal = document.getElementById('deviceTemplateFormModal');
  const form = document.getElementById('deviceTemplateForm');
  const modalTitle = document.getElementById('deviceTemplateModalTitle');
  const saveBtn = document.getElementById('deviceTemplateSaveBtn');
  const viewModeInput = document.getElementById('deviceTemplateViewMode');

  deviceTemplateModalIsOpen = true;

  // Reset form
  form.reset();
  document.getElementById('deviceTemplateErrorContainer').innerHTML = '';
  document.getElementById('matchingRulesContainer').innerHTML = '';
  selectedTemplateProfiles = [];
  renderSelectedProfileChips();
  
  // Set view mode
  viewModeInput.value = viewMode ? 'true' : 'false';

  if (templateId) {
    // Fetch template data
    fetch(`/SNMP/GetDeviceTemplate/${templateId}/`)
      .then(response => response.json())
      .then(data => {
        if (viewMode) {
          modalTitle.textContent = 'View Device Template';
          saveBtn.classList.add('hidden');
          // Disable all form inputs
          disableFormInputs(true);
        } else {
          modalTitle.textContent = 'Edit Device Template';
          saveBtn.classList.remove('hidden');
          saveBtn.textContent = 'Update Template';
          // Enable form inputs unless it's official
          disableFormInputs(data.official);
        }

        // Populate form
        document.getElementById('deviceTemplateId').value = data.id;
        document.getElementById('deviceTemplateName').value = data.name;
        document.getElementById('deviceTemplateDescription').value = data.description || '';
        document.getElementById('deviceTemplateVendor').value = data.vendor || '';
        document.getElementById('deviceTemplateModel').value = data.model || '';
        document.getElementById('deviceTemplateProduct').value = data.product || '';

        // Load matching rules
        if (data.matching_rules && data.matching_rules.length > 0) {
          data.matching_rules.forEach(rule => {
            addMatchingRule(rule);
          });
        } else {
          addMatchingRule(); // Add one empty rule
        }

        // Load and select profiles
        if (data.profiles && data.profiles.length > 0) {
          // Profiles now come as objects with {id, name, display_name}
          // Populate the profile cache
          data.profiles.forEach(profile => {
            profileDataCache[profile.id] = profile;
          });
          
          // Extract profile IDs for selection
          selectedTemplateProfiles = data.profiles.map(p => String(p.id));
          renderSelectedProfileChips();
        }
      })
      .catch(error => {
        console.error('Error loading template:', error);
        showToast('Error loading template data', 'error');
      });
  } else {
    // Add mode
    modalTitle.textContent = 'Add Device Template';
    saveBtn.classList.remove('hidden');
    saveBtn.textContent = 'Save Template';
    document.getElementById('deviceTemplateId').value = '';
    disableFormInputs(false);
    
    // Add one empty matching rule by default
    addMatchingRule();
  }

  modal.classList.remove('hidden');
}

// Disable/enable form inputs
function disableFormInputs(disabled) {
  const form = document.getElementById('deviceTemplateForm');
  const inputs = form.querySelectorAll('input:not([type="hidden"]), textarea, select');
  inputs.forEach(input => {
    input.disabled = disabled;
  });

  // Also disable add/remove buttons for matching rules
  const addRuleBtn = form.querySelector('button[onclick="addMatchingRule()"]');
  if (addRuleBtn) {
    addRuleBtn.disabled = disabled;
    if (disabled) {
      addRuleBtn.classList.add('btn-disabled');
    } else {
      addRuleBtn.classList.remove('btn-disabled');
    }
  }
  
  // Disable remove buttons for matching rules
  const matchingRulesContainer = document.getElementById('matchingRulesContainer');
  if (matchingRulesContainer) {
    const removeButtons = matchingRulesContainer.querySelectorAll('button');
    removeButtons.forEach(btn => {
      btn.disabled = disabled;
      if (disabled) {
        btn.classList.add('btn-disabled', 'opacity-50', 'cursor-not-allowed');
      } else {
        btn.classList.remove('btn-disabled', 'opacity-50', 'cursor-not-allowed');
      }
    });
  }
}

// Add a matching rule input field
function addMatchingRule(value = '') {
  const container = document.getElementById('matchingRulesContainer');
  const ruleDiv = document.createElement('div');
  ruleDiv.className = 'flex gap-2';
  
  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'input input-bordered w-full font-mono';
  input.placeholder = 'e.g., Cisco IOS, Catalyst';
  input.value = value;
  input.name = 'matching_rule';
  
  const removeBtn = document.createElement('button');
  removeBtn.type = 'button';
  removeBtn.className = 'btn btn-square btn-ghost btn-sm';
  removeBtn.innerHTML = `
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
    </svg>
  `;
  removeBtn.onclick = function() {
    ruleDiv.remove();
  };
  
  ruleDiv.appendChild(input);
  ruleDiv.appendChild(removeBtn);
  container.appendChild(ruleDiv);
}

// Open profile selector modal
function openProfileSelectorModal() {
  const modal = document.getElementById('deviceTemplateProfileSelectorModal');
  
  // Copy current selection to temp
  tempSelectedProfiles = [...selectedTemplateProfiles];
  
  // Load profiles
  loadProfilesForSelector();
  
  // Render chips in selector modal
  renderProfileSelectorChips();
  
  modal.classList.remove('hidden');
}

// Close profile selector modal
function closeProfileSelectorModal() {
  const modal = document.getElementById('deviceTemplateProfileSelectorModal');
  modal.classList.add('hidden');
  
  // Reset temp selection
  tempSelectedProfiles = [];
  
  // Clear search input
  const searchInput = document.getElementById('profileSelectorSearchInput');
  if (searchInput) {
    searchInput.value = '';
  }
}

// Apply profile selection from modal
function applyProfileSelection() {
  // Copy temp selection to actual selection
  selectedTemplateProfiles = [...tempSelectedProfiles];
  
  // Render chips in main modal
  renderSelectedProfileChips();
  
  // Close selector modal
  closeProfileSelectorModal();
}

// Store all profiles for filtering
let allProfilesData = [];

// Load profiles for selector modal
function loadProfilesForSelector() {
  const container = document.getElementById('profileSelectorContainer');
  
  fetch('/SNMP/GetAllProfiles/')
    .then(response => response.json())
    .then(data => {
      const profiles = data.profiles || [];
      
      // Store profiles globally for filtering
      allProfilesData = profiles;
      
      // Populate cache
      profiles.forEach(profile => {
        profileDataCache[profile.id] = profile;
      });
      
      if (profiles.length === 0) {
        container.innerHTML = '<div class="text-gray-400 text-sm">No profiles available</div>';
        return;
      }

      // Render profiles
      renderProfilesByVendor(profiles);
    })
    .catch(error => {
      console.error('Error loading profiles:', error);
      container.innerHTML = '<div class="text-red-400 text-sm">Error loading profiles</div>';
    });
}

// Render profiles organized by vendor
function renderProfilesByVendor(profiles) {
  const container = document.getElementById('profileSelectorContainer');
  container.innerHTML = '';
  
  if (profiles.length === 0) {
    container.innerHTML = '<div class="text-gray-400 text-sm">No profiles found</div>';
    return;
  }
  
  // Group profiles by vendor
  const profilesByVendor = {};
  profiles.forEach(profile => {
    const vendor = profile.vendor || 'Unknown';
    if (!profilesByVendor[vendor]) {
      profilesByVendor[vendor] = [];
    }
    profilesByVendor[vendor].push(profile);
  });
  
  // Sort vendors alphabetically
  const sortedVendors = Object.keys(profilesByVendor).sort();
  
  // Render each vendor section
  sortedVendors.forEach((vendor, index) => {
    // Add divider between sections (except before first)
    if (index > 0) {
      const divider = document.createElement('div');
      divider.className = 'border-t border-gray-600 my-4';
      container.appendChild(divider);
    }
    
    // Vendor header
    const vendorHeader = document.createElement('div');
    vendorHeader.className = 'text-sm font-semibold text-gray-300 mb-2 px-2';
    vendorHeader.textContent = vendor;
    container.appendChild(vendorHeader);
    
    // Render profiles for this vendor
    profilesByVendor[vendor].forEach(profile => {
      const label = createProfileCheckbox(profile);
      container.appendChild(label);
    });
  });
}

// Filter profiles based on search
function filterProfiles(searchTerm) {
  const term = searchTerm.toLowerCase();
  
  if (!term) {
    // No search term, show all profiles
    renderProfilesByVendor(allProfilesData);
    return;
  }
  
  // Filter profiles
  const filtered = allProfilesData.filter(profile => {
    const name = (profile.display_name || profile.name || '').toLowerCase();
    const description = (profile.description || '').toLowerCase();
    const vendor = (profile.vendor || '').toLowerCase();
    const product = (profile.product || '').toLowerCase();
    const model = (profile.model || '').toLowerCase();
    
    return name.includes(term) || 
           description.includes(term) || 
           vendor.includes(term) || 
           product.includes(term) ||
           model.includes(term);
  });
  
  renderProfilesByVendor(filtered);
}

// Store profile data for display
let profileDataCache = {};

// Render selected profiles as chips
function renderSelectedProfileChips() {
  const container = document.getElementById('selectedProfilesChipsContainer');
  container.innerHTML = '';

  if (selectedTemplateProfiles.length === 0) {
    container.innerHTML = '<div class="text-gray-400 text-sm italic">No profiles selected</div>';
    return;
  }

  // If we don't have profile data cached, fetch it
  if (Object.keys(profileDataCache).length === 0) {
    fetch('/SNMP/GetAllProfiles/')
      .then(response => response.json())
      .then(data => {
        const profiles = data.profiles || [];
        profiles.forEach(profile => {
          profileDataCache[profile.id] = profile;
        });
        renderSelectedProfileChipsWithData();
      })
      .catch(error => {
        console.error('Error loading profile data:', error);
        renderSelectedProfileChipsWithData();
      });
  } else {
    renderSelectedProfileChipsWithData();
  }
}

function renderSelectedProfileChipsWithData() {
  const container = document.getElementById('selectedProfilesChipsContainer');
  container.innerHTML = '';

  if (selectedTemplateProfiles.length === 0) {
    container.innerHTML = '<div class="text-gray-400 text-sm italic">No profiles selected</div>';
    return;
  }

  selectedTemplateProfiles.forEach(profileId => {
    const profile = profileDataCache[profileId];
    
    // Get display name and check if official
    let displayName = profileId;
    let isOfficial = false;
    
    if (profile) {
      const rawName = profile.name || '';
      isOfficial = rawName.endsWith('.json');
      
      if (isOfficial) {
        // Remove .json and convert to title case
        displayName = rawName.slice(0, -5).replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
      } else {
        displayName = profile.display_name || profile.name || profileId;
      }
    }
    
    // Star badge for official profiles
    const starBadge = isOfficial ? `
      <svg class="w-3 h-3 text-yellow-400 mr-1.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
      </svg>
    ` : '';
    
    const chip = document.createElement('div');
    chip.className = 'inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-blue-600 text-white';
    chip.innerHTML = `
      ${starBadge}
      <span>${displayName}</span>
      <button type="button" onclick="removeTemplateProfile('${profileId}')" class="ml-2 inline-flex items-center justify-center w-4 h-4 rounded-full hover:bg-blue-700 focus:outline-none">
        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    `;
    container.appendChild(chip);
  });
}

// Render selected profiles as chips in selector modal
function renderProfileSelectorChips() {
  const container = document.getElementById('profileSelectorChipsContainer');
  container.innerHTML = '';

  if (tempSelectedProfiles.length === 0) {
    container.innerHTML = '<div class="text-gray-400 text-sm italic">No profiles selected</div>';
    return;
  }

  tempSelectedProfiles.forEach(profileId => {
    // Find the checkbox to get the display name
    const checkbox = document.querySelector(`input[name="profiles"][value="${profileId}"]`);
    const displayName = checkbox ? checkbox.closest('label').querySelector('.text-sm.font-medium').textContent : profileId;
    
    const chip = document.createElement('div');
    chip.className = 'inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-blue-600 text-white';
    chip.innerHTML = `
      <span>${displayName}</span>
      <button type="button" onclick="removeSelectorProfile('${profileId}')" class="ml-2 inline-flex items-center justify-center w-4 h-4 rounded-full hover:bg-blue-700 focus:outline-none">
        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    `;
    container.appendChild(chip);
  });
}

// Remove profile from selector modal
function removeSelectorProfile(profileId) {
  tempSelectedProfiles = tempSelectedProfiles.filter(p => p !== profileId);
  
  // Uncheck the checkbox
  const checkbox = document.querySelector(`input[name="profiles"][value="${profileId}"]`);
  if (checkbox) {
    checkbox.checked = false;
  }
  
  renderProfileSelectorChips();
}

// Remove profile from main modal chips
function removeTemplateProfile(profileId) {
  selectedTemplateProfiles = selectedTemplateProfiles.filter(p => p !== profileId);
  renderSelectedProfileChips();
}

// Create a profile checkbox element for selector modal
function createProfileCheckbox(profile) {
  const label = document.createElement('label');
  label.className = 'flex items-start gap-2 p-2 hover:bg-gray-700 rounded cursor-pointer';
  
  const checkbox = document.createElement('input');
  checkbox.type = 'checkbox';
  checkbox.className = 'checkbox checkbox-primary mt-0.5';
  checkbox.name = 'profiles';
  checkbox.value = String(profile.id); // Always use ID as string
  
  // Check if already selected
  if (tempSelectedProfiles.includes(checkbox.value)) {
    checkbox.checked = true;
  }
  
  // Add change event listener
  checkbox.addEventListener('change', function() {
    const profileId = this.value;
    if (this.checked) {
      if (!tempSelectedProfiles.includes(profileId)) {
        tempSelectedProfiles.push(profileId);
      }
    } else {
      tempSelectedProfiles = tempSelectedProfiles.filter(p => p !== profileId);
    }
    renderProfileSelectorChips();
  });
  
  const textDiv = document.createElement('div');
  textDiv.className = 'flex-1';
  
  // Name row with official badge
  const nameRow = document.createElement('div');
  nameRow.className = 'flex items-center gap-2';
  
  // Official star badge
  if (profile.is_official) {
    const starBadge = document.createElement('div');
    starBadge.className = 'flex items-center gap-1 px-1.5 py-0.5 bg-yellow-500/20 border border-yellow-500/40 rounded-full flex-shrink-0';
    starBadge.title = 'Official Profile';
    starBadge.innerHTML = `
      <svg class="w-3 h-3 text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
      </svg>
    `;
    nameRow.appendChild(starBadge);
  }
  
  const nameSpan = document.createElement('span');
  nameSpan.className = 'text-sm font-medium text-gray-200';
  nameSpan.textContent = profile.display_name || profile.name;
  nameRow.appendChild(nameSpan);
  
  // Metadata row
  const metadataRow = document.createElement('div');
  metadataRow.className = 'text-xs text-gray-400 mt-1';
  
  const metadataParts = [];
  if (profile.vendor) metadataParts.push(profile.vendor);
  if (profile.product) metadataParts.push(profile.product);
  if (profile.model) metadataParts.push(`Model: ${profile.model}`);
  
  metadataRow.textContent = metadataParts.length > 0 ? metadataParts.join(' • ') : 'No metadata';
  
  textDiv.appendChild(nameRow);
  textDiv.appendChild(metadataRow);
  
  label.appendChild(checkbox);
  label.appendChild(textDiv);
  
  return label;
}

// Close device template modal
function closeDeviceTemplateModal() {
  deviceTemplateModalIsOpen = false;
  document.getElementById('deviceTemplateFormModal').classList.add('hidden');
  document.getElementById('deviceTemplateForm').reset();
  document.getElementById('deviceTemplateErrorContainer').innerHTML = '';
  document.getElementById('matchingRulesContainer').innerHTML = '';
  selectedTemplateProfiles = [];
  document.getElementById('selectedProfilesChipsContainer').innerHTML = '';
}

// Handle form submission
document.addEventListener('DOMContentLoaded', function() {
  const form = document.getElementById('deviceTemplateForm');
  if (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();

      const errorContainer = document.getElementById('deviceTemplateErrorContainer');
      const templateId = document.getElementById('deviceTemplateId').value;
      const url = templateId ? `/SNMP/UpdateDeviceTemplate/${templateId}/` : '/SNMP/AddDeviceTemplate/';

      // Collect matching rules
      const matchingRuleInputs = document.querySelectorAll('input[name="matching_rule"]');
      const matchingRules = Array.from(matchingRuleInputs)
        .map(input => input.value.trim())
        .filter(value => value !== '');

      // Use the tracked selected profiles array
      const selectedProfiles = selectedTemplateProfiles;
      
      // Debug logging
      console.log('Submitting device template with profiles:', selectedProfiles);

      // Build form data
      const formData = new FormData(this);
      
      // Remove individual matching_rule entries (we'll send as JSON)
      formData.delete('matching_rule');
      
      // Remove individual profile entries (we'll send as JSON)
      formData.delete('profiles');
      
      // Add matching rules as JSON
      formData.append('matching_rules', JSON.stringify(matchingRules));
      
      // Add profiles as JSON
      formData.append('profiles', JSON.stringify(selectedProfiles));
      
      console.log('Profiles JSON:', JSON.stringify(selectedProfiles));

      // Get CSRF token
      const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

      console.log('Sending request to:', url);
      
      fetch(url, {
        method: 'POST',
        headers: {
          'X-CSRFToken': csrfToken
        },
        body: formData
      })
        .then(response => {
          console.log('Response status:', response.status);
          if (!response.ok) {
            return response.text().then(text => {
              console.error('Error response:', text);
              throw new Error(text || 'Failed to save device template');
            });
          }
          return response.json();
        })
        .then(data => {
          console.log('Success response:', data);
          showToast(templateId ? 'Device template updated successfully!' : 'Device template created successfully!', 'success');
          closeDeviceTemplateModal();
          
          // Refresh templates data without page reload
          if (typeof refreshDeviceTemplatesData === 'function') {
            refreshDeviceTemplatesData();
          }
        })
        .catch(error => {
          console.error('Fetch error:', error);
          errorContainer.innerHTML = `
            <div class="p-4 mb-4 text-red-700 bg-red-100 border border-red-300 rounded-lg">
              <h3 class="font-bold mb-2">Error</h3>
              <p class="text-sm">${error.message}</p>
            </div>
          `;
          errorContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        });
    });
  }
});
