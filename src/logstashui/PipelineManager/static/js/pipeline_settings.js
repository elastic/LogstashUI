/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

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
 * Get current pipeline settings (for use when saving the entire pipeline)
 */
window.getPipelineSettings = function () {
    return pipelineSettings;
};

// Initialize pipeline settings on page load
document.addEventListener('DOMContentLoaded', function () {
    // Populate hidden fields with URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    const pipelineId = urlParams.get('pipeline');
    const esId = urlParams.get('es_id');
    const lsId = urlParams.get('ls_id');

    if (pipelineId) {
        document.getElementById('hiddenPipelineName').value = pipelineId;
    }
    if (esId) {
        document.getElementById('hiddenEsId').value = esId;
    }
    if (lsId) {
        document.getElementById('hiddenLsId').value = lsId;
    }

    // Handle form submission with regular fetch (no HTMX)
    const form = document.getElementById('pipelineSettingsForm');
    if (form) {
        form.addEventListener('submit', async function (event) {
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
                const response = await fetch('/ConnectionManager/UpdatePipelineSettings/', {
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
                    showToast('Pipeline settings saved successfully', 'success');
                } else {
                    // Get error message from response
                    const errorText = await response.text();
                    showToast(errorText || 'Failed to save pipeline settings', 'error');
                }
            } catch (error) {
                // Reset button state
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = 'Apply Settings';
                }

                // Show error notification
                showToast('Network error: ' + error.message, 'error');
            }
        });
    }
});
