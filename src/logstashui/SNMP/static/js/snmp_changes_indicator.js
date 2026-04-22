/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

/**
 * Check for undeployed SNMP changes and update the indicator
 * This function fetches the diff data and determines if there are any changes
 */
async function checkForUndeployedSNMPChanges() {
    const indicator = document.getElementById('snmpUndeployedIndicator');
    
    if (!indicator) return;

    try {
        // Fetch diff data from the server (same endpoint used by the deploy modal)
        const response = await fetch('/SNMP/GetDeployDiff/', {
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

        const diffData = await response.json();

        // Check if there are any changes
        let hasChanges = false;

        if (diffData.networks && diffData.networks.length > 0) {
            for (const network of diffData.networks) {
                // Check main pipeline
                if (network.pipeline_name !== null) {
                    const currentLines = network.current ? network.current.split('\n') : [];
                    const newLines = network.new ? network.new.split('\n') : [];
                    const isNewPipeline = !network.current || network.current.trim() === '';

                    if (isNewPipeline) {
                        hasChanges = true;
                        break;
                    }

                    // Simple check: if current and new are different, there are changes
                    if (network.current !== network.new) {
                        hasChanges = true;
                        break;
                    }
                }

                // Check trap pipeline
                if (network.trap_pipeline) {
                    const trapPipeline = network.trap_pipeline;
                    if (trapPipeline.action === 'create' || trapPipeline.action === 'delete') {
                        hasChanges = true;
                        break;
                    } else if (trapPipeline.action === 'update') {
                        if (trapPipeline.current !== trapPipeline.new) {
                            hasChanges = true;
                            break;
                        }
                    }
                }

                // Check discovery pipeline
                if (network.discovery_pipeline) {
                    const discoveryPipeline = network.discovery_pipeline;
                    if (discoveryPipeline.action === 'create' || discoveryPipeline.action === 'delete') {
                        hasChanges = true;
                        break;
                    } else if (discoveryPipeline.action === 'update') {
                        if (discoveryPipeline.current !== discoveryPipeline.new) {
                            hasChanges = true;
                            break;
                        }
                    }
                }
            }
        }

        // Show or hide the indicator based on whether there are changes
        if (hasChanges) {
            indicator.classList.remove('hidden');
        } else {
            indicator.classList.add('hidden');
        }

    } catch (error) {
        console.error('Error checking for undeployed SNMP changes:', error);
        // On error, hide the indicator
        indicator.classList.add('hidden');
    }
}

// Check for changes when the page loads
document.addEventListener('DOMContentLoaded', function() {
    checkForUndeployedSNMPChanges();
});
