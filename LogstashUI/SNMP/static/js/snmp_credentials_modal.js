// SNMP Credentials Modal JavaScript

// Open modal for adding new credential
document.getElementById('addCredentialBtn').addEventListener('click', function() {
  openCredentialModal();
});

// Open credential modal (for add or edit)
function openCredentialModal(credentialData = null) {
  const modal = document.getElementById('credentialFormModal');
  const form = document.getElementById('credentialForm');
  const modalTitle = document.getElementById('modalTitle');
  
  // Reset form
  form.reset();
  document.getElementById('credentialErrorContainer').innerHTML = '';
  
  if (credentialData) {
    // Edit mode
    modalTitle.textContent = 'Edit SNMP Credential';
    document.getElementById('credentialId').value = credentialData.id;
    document.getElementById('credentialName').value = credentialData.name;
    document.getElementById('credentialDescription').value = credentialData.description || '';
    
    // Set version
    document.querySelector(`input[name="version"][value="${credentialData.version}"]`).checked = true;
    
    if (credentialData.version === '1' || credentialData.version === '2c') {
      document.getElementById('community').value = credentialData.community || 'public';
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
document.getElementById('credentialForm').addEventListener('submit', function(e) {
  e.preventDefault();
  
  const formData = new FormData(this);
  const credentialId = document.getElementById('credentialId').value;
  const url = credentialId ? `/API/SNMP/UpdateCredential/${credentialId}/` : '/API/SNMP/AddCredential/';
  
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
    return response.text();
  })
  .then(data => {
    showToast(credentialId ? 'Credential updated successfully!' : 'Credential created successfully!', 'success');
    closeCredentialModal();
    
    // Reload page to show updated credentials
    setTimeout(() => {
      window.location.reload();
    }, 500);
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

// Toast notification function
function showToast(message, type = 'success') {
  const container = document.getElementById('toast-container') || createToastContainer();
  const toast = document.createElement('div');
  const colors = {
    success: 'bg-green-500',
    error: 'bg-red-500',
    info: 'bg-blue-500',
    warning: 'bg-yellow-500'
  };

  toast.className = `${colors[type] || 'bg-gray-800'} text-white px-6 py-3 rounded-lg shadow-lg flex items-center justify-between min-w-[300px]`;
  toast.innerHTML = `
    <span>${message}</span>
    <button onclick="this.parentElement.remove()" class="text-white hover:text-gray-200 ml-4">
      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
      </svg>
    </button>
  `;

  container.appendChild(toast);

  // Auto-remove after 5 seconds
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 5000);
}

function createToastContainer() {
  const container = document.createElement('div');
  container.id = 'toast-container';
  container.className = 'fixed top-4 right-4 z-50 flex flex-col gap-2';
  document.body.appendChild(container);
  return container;
}
