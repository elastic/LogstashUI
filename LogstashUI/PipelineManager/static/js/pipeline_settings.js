// ============================================================================
// Pipeline Settings Functions
// ============================================================================

// Global object to store pipeline settings
let pipelineSettings = {
    description: '',
    pipeline_workers: null,
    pipeline_batch_size: null,
    pipeline_batch_delay: null,
    queue_type: 'memory',
    queue_max_bytes: null,
    queue_max_bytes_unit: 'gigabytes',
    queue_checkpoint_writes: null
};

/**
 * Toggle the pipeline settings collapsible section
 */
function togglePipelineSettings() {
    const content = document.getElementById('pipelineSettingsContent');
    const icon = document.getElementById('toggleIcon');
    
    if (content.classList.contains('hidden')) {
        content.classList.remove('hidden');
        icon.classList.add('rotate-90');
    } else {
        content.classList.add('hidden');
        icon.classList.remove('rotate-90');
    }
}

/**
 * Load pipeline settings - now handled by Django template rendering
 * This function is kept for backward compatibility but is no longer needed
 */
function loadPipelineSettings() {
    // Settings are now loaded directly from Django context in the HTML template
    // No need to load from localStorage or make additional API calls
}


/**
 * Save pipeline settings (no longer needed - form submission handled by HTMX)
 * Kept for backward compatibility
 */
function savePipelineSettings() {
    // This function is now handled by the form's HTMX submission
    // Just trigger the form submit
    const form = document.getElementById('pipelineSettingsForm');
    if (form) {
        // Populate hidden fields with URL parameters
        const urlParams = new URLSearchParams(window.location.search);
        const pipelineId = urlParams.get('pipeline');
        const esId = urlParams.get('es_id');
        
        if (!pipelineId || !esId) {
            showSettingsErrorNotification('Error: Pipeline ID or ES ID not found');
            return;
        }
        
        document.getElementById('hiddenEsId').value = esId;
        document.getElementById('hiddenPipelineName').value = pipelineId;
        
        // Trigger HTMX form submission
        htmx.trigger(form, 'submit');
    }
}


/**
 * Show a temporary notification that settings were saved
 */
function showSettingsSavedNotification(message = 'Pipeline settings saved successfully') {
    const notification = document.createElement('div');
    notification.className = 'fixed top-4 right-4 bg-green-600 text-white px-6 py-3 rounded-lg shadow-lg z-50 flex items-center';
    notification.innerHTML = `
        <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
        </svg>
        ${message}
    `;
    
    document.body.appendChild(notification);
    
    // Remove notification after 3 seconds
    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transition = 'opacity 0.3s ease';
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 300);
    }, 3000);
}

/**
 * Show a temporary error notification
 */
function showSettingsErrorNotification(message = 'Failed to save pipeline settings') {
    const notification = document.createElement('div');
    notification.className = 'fixed top-4 right-4 bg-red-600 text-white px-6 py-3 rounded-lg shadow-lg z-50 flex items-center';
    notification.innerHTML = `
        <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
        ${message}
    `;
    
    document.body.appendChild(notification);
    
    // Remove notification after 5 seconds
    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transition = 'opacity 0.3s ease';
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 300);
    }, 5000);
}

/**
 * Get current pipeline settings (for use when saving the entire pipeline)
 */
window.getPipelineSettings = function() {
    return pipelineSettings;
};

// Initialize pipeline settings on page load
document.addEventListener('DOMContentLoaded', function() {
    loadPipelineSettings();
    
    // Populate hidden fields with URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    const pipelineId = urlParams.get('pipeline');
    const esId = urlParams.get('es_id');
    
    if (pipelineId && esId) {
        document.getElementById('hiddenEsId').value = esId;
        document.getElementById('hiddenPipelineName').value = pipelineId;
    }
    
    // Handle form submission with regular fetch (no HTMX)
    const form = document.getElementById('pipelineSettingsForm');
    if (form) {
        form.addEventListener('submit', async function(event) {
            event.preventDefault(); // Prevent default form submission
            
            const btn = document.getElementById('applySettingsBtn');
            
            // Show loading state
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = `
                    <svg class="animate-spin h-5 w-5 inline-block mr-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Saving...
                `;
            }
            
            try {
                // Get form data
                const formData = new FormData(form);
                
                // Send request
                const response = await fetch('/API/UpdatePipelineSettings/', {
                    method: 'POST',
                    body: formData
                });
                
                // Reset button state
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = 'Apply Settings';
                }
                
                // Check response status
                if (response.ok) {
                    showSettingsSavedNotification();
                } else {
                    // Get error message from response
                    const errorText = await response.text();
                    showSettingsErrorNotification(errorText || 'Failed to save pipeline settings');
                }
            } catch (error) {
                // Reset button state
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = 'Apply Settings';
                }
                
                // Show error notification
                showSettingsErrorNotification('Network error: ' + error.message);
            }
        });
    }
});
