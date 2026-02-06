// Open commit modal and generate preview
function openCommitModal() {
  const modal = document.getElementById('commitModal');
  modal.classList.remove('hidden');
  document.body.style.overflow = 'hidden';
  
  // Show loading state and generate preview
  const previewContainer = document.getElementById('configPreview');
  const confirmBtn = document.getElementById('commitConfirmBtn');
  
  previewContainer.innerHTML = `
    <div class="flex items-center justify-center p-8">
      <svg class="animate-spin h-8 w-8 mr-3 text-blue-500" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
      </svg>
      <span class="text-gray-300">Generating configuration preview...</span>
    </div>
  `;
  
  // Disable confirm button while loading
  confirmBtn.disabled = true;
  
  // Generate the preview
  generatePreview();
}

// Close commit modal
function closeCommitModal() {
  const modal = document.getElementById('commitModal');
  modal.classList.add('hidden');
  document.body.style.overflow = 'auto';
}

// Generate configuration preview
function generatePreview() {
  const previewContainer = document.getElementById('configPreview');
  const confirmBtn = document.getElementById('commitConfirmBtn');
  
  fetch('/API/SNMP/GenerateCommitConfiguration/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrfToken()
    }
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      // Display the preview
      previewContainer.innerHTML = `
        <div class="bg-gray-700 rounded-lg p-4">
          <h3 class="font-semibold text-white mb-3">Configuration Preview</h3>
          <div class="text-sm text-gray-300 space-y-2">
            <p><strong>Networks:</strong> ${data.networks_count || 0}</p>
            <p><strong>Devices:</strong> ${data.devices_count || 0}</p>
            <p class="text-gray-400 mt-3">${data.message || 'Configuration ready to commit.'}</p>
          </div>
          ${data.preview ? `<pre class="mt-4 p-3 bg-gray-900 rounded text-xs text-gray-300 overflow-auto max-h-64">${JSON.stringify(data.preview, null, 2)}</pre>` : ''}
        </div>
      `;
      
      // Enable confirm button
      confirmBtn.disabled = false;
    } else {
      previewContainer.innerHTML = `
        <div class="p-4 text-sm text-red-700 bg-red-100 rounded-lg">
          <strong>Error:</strong> ${data.error || 'Failed to generate preview.'}
        </div>
      `;
      confirmBtn.disabled = true;
    }
  })
  .catch(error => {
    previewContainer.innerHTML = `
      <div class="p-4 text-sm text-red-700 bg-red-100 rounded-lg">
        <strong>Error:</strong> ${error.message || 'An unexpected error occurred.'}
      </div>
    `;
    confirmBtn.disabled = true;
  });
}

// Confirm and execute the actual commit
function confirmCommit() {
  const confirmBtn = document.getElementById('commitConfirmBtn');
  const responseMsg = document.getElementById('commitResponseMessage');
  
  // Disable button and show loading state
  confirmBtn.disabled = true;
  confirmBtn.innerHTML = `
    <svg class="animate-spin h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24">
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
    </svg>
    Committing...
  `;
  
  // Call the actual commit endpoint
  fetch('/API/SNMP/CommitConfiguration/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrfToken()
    }
  })
  .then(response => response.json())
  .then(data => {
    responseMsg.classList.remove('hidden');
    
    if (data.success) {
      responseMsg.innerHTML = `
        <div class="p-4 mb-4 text-sm text-green-700 bg-green-100 rounded-lg">
          <strong>Success!</strong> ${data.message || 'Configuration committed successfully.'}
        </div>
      `;
      
      // Close modal after 2 seconds
      setTimeout(() => {
        closeCommitModal();
        // Optionally reload the page to reflect changes
        // window.location.reload();
      }, 2000);
    } else {
      responseMsg.innerHTML = `
        <div class="p-4 mb-4 text-sm text-red-700 bg-red-100 rounded-lg">
          <strong>Error:</strong> ${data.error || 'Failed to commit configuration.'}
        </div>
      `;
      
      // Re-enable button on error
      confirmBtn.disabled = false;
      confirmBtn.innerHTML = `
        <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
        </svg>
        Commit Configuration
      `;
    }
  })
  .catch(error => {
    responseMsg.classList.remove('hidden');
    responseMsg.innerHTML = `
      <div class="p-4 mb-4 text-sm text-red-700 bg-red-100 rounded-lg">
        <strong>Error:</strong> ${error.message || 'An unexpected error occurred while committing.'}
      </div>
    `;
    
    // Re-enable button on error
    confirmBtn.disabled = false;
    confirmBtn.innerHTML = `
      <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
      </svg>
      Commit Configuration
    `;
  });
}

// Get CSRF token from cookies
function getCsrfToken() {
  const name = 'csrftoken';
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

// Attach event listener to commit button
document.addEventListener('DOMContentLoaded', function() {
  const commitBtn = document.getElementById('commitBtn');
  if (commitBtn) {
    commitBtn.addEventListener('click', openCommitModal);
  }
});
