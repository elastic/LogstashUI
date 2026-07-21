/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

/**
 * Check for undeployed SNMP changes and update the indicator
 * Uses lightweight timestamp-based check for performance
 */
async function checkForUndeployedSNMPChanges() {
    const indicator = document.getElementById('snmpUndeployedIndicator');
    
    if (!indicator) return;

    try {
        // Use lightweight endpoint that checks timestamps instead of full reconciliation
        const response = await fetch('/SNMP/CheckUndeployedChanges/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            // If there's an error, hide the indicator
            indicator.classList.add('hidden');
            return;
        }

        const data = await response.json();
        const hasChanges = data.has_changes || false;

        // Show or hide the indicator based on whether there are changes
        const deployBtn = document.getElementById('deployChangesBtn') || document.getElementById('commitBtn');
        
        if (hasChanges) {
            indicator.classList.remove('hidden');
            // Add purple glow to Deploy button
            if (deployBtn) {
                deployBtn.classList.add('deploy-button-glow');
            }
        } else {
            indicator.classList.add('hidden');
            // Remove purple glow from Deploy button
            if (deployBtn) {
                deployBtn.classList.remove('deploy-button-glow');
            }
        }

    } catch (error) {
        console.error('Error checking for undeployed SNMP changes:', error);
        // On error, hide the indicator
        indicator.classList.add('hidden');
    }
}

/**
 * Trigger a check for undeployed changes after a CRUD operation
 * This should be called after adding/updating/deleting devices, networks, credentials, templates, or profiles
 */
function triggerUndeployedChangesCheck() {
    // Small delay to allow backend to process the change
    setTimeout(() => {
        checkForUndeployedSNMPChanges();
    }, 500);
}

// Expose function globally so other scripts can call it
window.triggerUndeployedChangesCheck = triggerUndeployedChangesCheck;

// Check for changes when the page loads
document.addEventListener('DOMContentLoaded', function() {
    checkForUndeployedSNMPChanges();
});
