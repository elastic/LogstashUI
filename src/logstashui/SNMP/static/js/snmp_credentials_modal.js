/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// SNMP Credentials Modal JavaScript

// Toggle password visibility for credential fields (mirrors pipeline editor behaviour)
function togglePasswordVisibility(fieldId, button) {
  const input = document.getElementById(fieldId);
  if (!input) return;

  if (input.type === 'password') {
    input.type = 'text';
    button.innerHTML = `
      <svg class="w-5 h-5 eye-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
      </svg>`;
  } else {
    input.type = 'password';
    button.innerHTML = `
      <svg class="w-5 h-5 eye-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
      </svg>`;
  }
}

// Open modal for adding new credential
const addCredentialBtn = document.getElementById('addCredentialBtn');
if (addCredentialBtn) {
  addCredentialBtn.addEventListener('click', function () {
    openCredentialModal();
  });
}

// Open credential modal (for add or edit)
function openCredentialModal(credentialData = null) {
  const modal = document.getElementById('credentialFormModal');
  const form = document.getElementById('credentialForm');
  const modalTitle = document.getElementById('credentialModalTitle');

  // Reset form
  form.reset();
  document.getElementById('credentialErrorContainer').innerHTML = '';

  if (credentialData) {
    // Check if this is edit mode (has ID) or clone mode (no ID)
    const isEditMode = credentialData.id !== undefined;
    
    if (isEditMode) {
      // Edit mode
      modalTitle.textContent = 'Edit SNMP Credential';
      document.getElementById('credentialId').value = credentialData.id;
    } else {
      // Clone mode - has data but no ID
      modalTitle.textContent = 'Add SNMP Credential';
      document.getElementById('credentialId').value = '';
    }
    
    // Fill in the form fields
    document.getElementById('credentialName').value = credentialData.name;
    document.getElementById('credentialDescription').value = credentialData.description || '';

    // Set version
    document.querySelector(`input[name="version"][value="${credentialData.version}"]`).checked = true;

    if (credentialData.version === '1' || credentialData.version === '2c') {
      // Don't pre-fill the community string — server never sends the real value.
      // Leave empty; the backend keeps the existing value when nothing is posted.
      document.getElementById('community').value = '';
      if (isEditMode) {
        document.getElementById('communityHint').textContent = 'Leave blank to keep the existing community string.';
      }
    } else if (credentialData.version === '3') {
      document.getElementById('securityName').value = credentialData.security_name || '';
      document.getElementById('securityLevel').value = credentialData.security_level || '';

      if (credentialData.auth_protocol) {
        document.getElementById('authProtocol').value = credentialData.auth_protocol;
        // Don't populate password fields for security reasons
      }

      if (credentialData.priv_protocol) {
        document.getElementById('privProtocol').value = credentialData.priv_protocol;
        // Don't populate password fields for security reasons
      }
    }

    updateVersionFields();
    updateSecurityFields();
  } else {
    // Add mode
    modalTitle.textContent = 'Add SNMP Credential';
    document.getElementById('credentialId').value = '';
    document.querySelector('input[name="version"][value="2c"]').checked = true;
    updateVersionFields();
  }

  modal.classList.remove('hidden');
}

// Close credential modal
function closeCredentialModal() {
  document.getElementById('credentialFormModal').classList.add('hidden');
  document.getElementById('credentialForm').reset();
  document.getElementById('credentialErrorContainer').innerHTML = '';
  document.getElementById('communityHint').textContent = 'Default: public';
}

// Update form fields based on SNMP version
function updateVersionFields() {
  const version = document.querySelector('input[name="version"]:checked').value;
  const communityFields = document.getElementById('communityFields');
  const snmpv3Fields = document.getElementById('snmpv3Fields');

  if (version === '1' || version === '2c') {
    communityFields.classList.remove('hidden');
    snmpv3Fields.classList.add('hidden');

    // Clear SNMPv3 fields
    document.getElementById('securityName').value = '';
    document.getElementById('securityLevel').value = '';
    document.getElementById('authProtocol').value = '';
    document.getElementById('authPass').value = '';
    document.getElementById('privProtocol').value = '';
    document.getElementById('privPass').value = '';
  } else {
    communityFields.classList.add('hidden');
    snmpv3Fields.classList.remove('hidden');

    // Clear community field
    document.getElementById('community').value = 'public';
  }
}

// Update security fields based on security level
function updateSecurityFields() {
  const securityLevel = document.getElementById('securityLevel').value;
  const authFields = document.getElementById('authFields');
  const privFields = document.getElementById('privFields');

  if (securityLevel === 'noAuthNoPriv') {
    authFields.classList.add('hidden');
    privFields.classList.add('hidden');

    // Clear auth and priv fields
    document.getElementById('authProtocol').value = '';
    document.getElementById('authPass').value = '';
    document.getElementById('privProtocol').value = '';
    document.getElementById('privPass').value = '';
  } else if (securityLevel === 'authNoPriv') {
    authFields.classList.remove('hidden');
    privFields.classList.add('hidden');

    // Clear priv fields
    document.getElementById('privProtocol').value = '';
    document.getElementById('privPass').value = '';
  } else if (securityLevel === 'authPriv') {
    authFields.classList.remove('hidden');
    privFields.classList.remove('hidden');
  } else {
    authFields.classList.add('hidden');
    privFields.classList.add('hidden');
  }
}

// Handle form submission
document.getElementById('credentialForm').addEventListener('submit', function (e) {
  e.preventDefault();

  const formData = new FormData(this);
  const credentialId = document.getElementById('credentialId').value;
  const url = credentialId ? `/SNMP/UpdateCredential/${credentialId}/` : '/SNMP/AddCredential/';

  // Get CSRF token
  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

  fetch(url, {
    method: 'POST',
    headers: {
      'X-CSRFToken': csrfToken
    },
    body: formData
  })
    .then(response => {
      if (!response.ok) {
        return response.text().then(text => {
          throw new Error(text || 'Failed to save credential');
        });
      }
      return response.json();
    })
    .then(data => {
      const newCredentialId = data.id || data.credential_id || null;
      showToast(credentialId ? 'Credential updated successfully!' : 'Credential created successfully!', 'success');
      document.dispatchEvent(new CustomEvent('credentialSaved', { detail: { id: newCredentialId } }));
      closeCredentialModal();
      if (typeof refreshCredentialsData === 'function') {
        refreshCredentialsData();
      }
      if (typeof triggerUndeployedChangesCheck === 'function') {
        triggerUndeployedChangesCheck();
      }
    })
    .catch(error => {
      const errorContainer = document.getElementById('credentialErrorContainer');
      errorContainer.innerHTML = `
      <div class="p-4 mb-4 text-red-700 bg-red-100 border border-red-300 rounded-lg">
        <h3 class="font-bold mb-2">Error</h3>
        <p class="text-sm">${error.message}</p>
      </div>
    `;
      errorContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
});