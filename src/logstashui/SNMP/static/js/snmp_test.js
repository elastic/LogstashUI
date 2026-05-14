/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

document.addEventListener('DOMContentLoaded', function() {
    // Modal elements
    const snmpTestModal = document.getElementById('snmpTestModal');
    const testSnmpBtn = document.getElementById('testSnmpBtn');
    const closeSnmpTestModal = document.getElementById('closeSnmpTestModal');

    // Form elements
    const deviceSelect = document.getElementById('snmpTestDeviceSelect');
    const templateSelect = document.getElementById('snmpTestTemplateSelect');
    const runTestBtn = document.getElementById('snmpTestRunTestBtn');
    const runTestBtnText = document.getElementById('snmpTestRunTestBtnText');
    const deviceInfo = document.getElementById('snmpTestDeviceInfo');
    const deviceInfoText = document.getElementById('snmpTestDeviceInfoText');
    const templateInfo = document.getElementById('snmpTestTemplateInfo');
    const templateInfoText = document.getElementById('snmpTestTemplateInfoText');
    
    const loadingState = document.getElementById('snmpTestLoadingState');
    const resultsContainer = document.getElementById('snmpTestResultsContainer');
    const errorState = document.getElementById('snmpTestErrorState');
    const errorMessage = document.getElementById('snmpTestErrorMessage');
    
    console.log('SNMP Test elements found:', {
        deviceSelect: !!deviceSelect,
        templateSelect: !!templateSelect,
        runTestBtn: !!runTestBtn,
        loadingState: !!loadingState
    });

    // Tab elements
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');

    // Modal controls
    if (testSnmpBtn) {
        testSnmpBtn.addEventListener('click', function() {
            snmpTestModal.classList.remove('hidden');
            snmpTestModal.classList.add('flex');
            // Reset form when opening
            resetModal();
        });
    }

    if (closeSnmpTestModal) {
        closeSnmpTestModal.addEventListener('click', function() {
            snmpTestModal.classList.add('hidden');
            snmpTestModal.classList.remove('flex');
        });
    }

    // Close modal when clicking backdrop
    const snmpTestModalBackdrop = document.getElementById('snmpTestModalBackdrop');
    if (snmpTestModalBackdrop) {
        snmpTestModalBackdrop.addEventListener('click', function() {
            snmpTestModal.classList.add('hidden');
            snmpTestModal.classList.remove('flex');
        });
    }

    // Close modal on Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && !snmpTestModal.classList.contains('hidden')) {
            snmpTestModal.classList.add('hidden');
            snmpTestModal.classList.remove('flex');
        }
    });

    // Reset modal function
    function resetModal() {
        deviceSelect.value = '';
        templateSelect.value = '';
        deviceInfo.classList.add('hidden');
        templateInfo.classList.add('hidden');
        resultsContainer.classList.add('hidden');
        errorState.classList.add('hidden');
        loadingState.classList.add('hidden');
        runTestBtn.disabled = true;
    }

    // Device selection handler
    deviceSelect.addEventListener('change', function() {
        const selectedOption = this.options[this.selectedIndex];
        
        if (this.value) {
            const ip = selectedOption.dataset.ip;
            const port = selectedOption.dataset.port;
            const hasCredential = selectedOption.dataset.hasCredential === 'true';
            const templateId = selectedOption.dataset.templateId;
            const templateName = selectedOption.dataset.templateName;
            
            if (!hasCredential) {
                deviceInfoText.textContent = '⚠️ This device has no credential assigned';
                deviceInfoText.classList.add('text-yellow-400');
                deviceInfoText.classList.remove('text-gray-400');
            } else {
                deviceInfoText.textContent = `${ip}:${port}`;
                deviceInfoText.classList.remove('text-yellow-400');
                deviceInfoText.classList.add('text-gray-400');
            }
            deviceInfo.classList.remove('hidden');
            
            // Auto-select template if device has one assigned
            if (templateId && templateSelect.querySelector(`option[value="${templateId}"]`)) {
                templateSelect.value = templateId;
                templateSelect.dispatchEvent(new Event('change'));
            }
        } else {
            deviceInfo.classList.add('hidden');
        }
        
        updateRunButton();
    });

    // Template selection handler
    templateSelect.addEventListener('change', function() {
        const selectedOption = this.options[this.selectedIndex];
        
        if (this.value) {
            const vendor = selectedOption.dataset.vendor;
            const isOfficial = selectedOption.dataset.official === 'True';
            
            templateInfoText.textContent = `${vendor}${isOfficial ? ' (Official)' : ''}`;
            templateInfo.classList.remove('hidden');
        } else {
            templateInfo.classList.add('hidden');
        }
        
        updateRunButton();
    });

    // Update run button state
    function updateRunButton() {
        const deviceSelected = deviceSelect.value !== '';
        const templateSelected = templateSelect.value !== '';
        const deviceHasCredential = deviceSelect.value && 
            deviceSelect.options[deviceSelect.selectedIndex].dataset.hasCredential === 'true';
        
        console.log('updateRunButton - Device:', deviceSelected, 'Template:', templateSelected, 'Has Credential:', deviceHasCredential);
        
        runTestBtn.disabled = !(deviceSelected && templateSelected && deviceHasCredential);
        console.log('Run button disabled:', runTestBtn.disabled);
    }

    // Run test handler
    if (runTestBtn) {
        console.log('Run test button found, attaching listener');
        runTestBtn.addEventListener('click', async function(event) {
            event.preventDefault();
            event.stopPropagation();
            
            console.log('=== SNMP TEST RUN BUTTON CLICKED ===');
            console.log('Event target:', event.target);
            console.log('Button ID:', this.id);
        const deviceId = parseInt(deviceSelect.value);
        const templateId = parseInt(templateSelect.value);
        
        console.log('Device ID:', deviceId, 'Template ID:', templateId);
        
        if (!deviceId || !templateId) {
            console.log('Missing device or template, aborting');
            return;
        }

        // Hide previous results/errors
        resultsContainer.classList.add('hidden');
        errorState.classList.add('hidden');
        
        // Show loading state
        loadingState.classList.remove('hidden');
        runTestBtn.disabled = true;
        runTestBtnText.textContent = 'Running...';

        console.log('Making request to /SNMP/RunSNMPTest/ at', new Date().toISOString());
        console.log('CSRF Token:', getCookie('csrftoken'));
        
        try {
            console.log('Calling fetch at', new Date().toISOString());
            const response = await fetch('/SNMP/RunSNMPTest/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({
                    device_id: deviceId,
                    template_id: templateId
                })
            });
            
            console.log('Fetch completed, response:', response);
            console.log('Response status:', response.status);

            const data = await response.json();
            console.log('Response parsed');
            
            console.log('Response status:', response.status);
            console.log('Response data:', data);
            console.log('data.success:', data.success);
            console.log('data.error:', data.error);
            console.log('Full data object:', JSON.stringify(data, null, 2));

            // Show results if we have any data, even with errors
            // Only show error page if there's a top-level error (no results at all)
            if (data.results) {
                displayResults(data);
            } else if (data.error) {
                console.error('Server error:', data);
                displayError(data.error, data);
            } else {
                console.error('Unknown error:', data);
                displayError('Unknown error occurred', data);
            }
        } catch (error) {
            console.error('Request error:', error);
            displayError(`Network error: ${error.message}`, null);
        } finally {
            loadingState.classList.add('hidden');
            runTestBtn.disabled = false;
            runTestBtnText.textContent = 'Run Test';
        }
        });
    } else {
        console.error('Run test button not found!');
    }

    // Display results
    function displayResults(data) {
        // Hide loading and error states
        loadingState.classList.add('hidden');
        errorState.classList.add('hidden');
        
        // Update summary
        document.getElementById('snmpTestSummaryDevice').textContent = 
            `${data.device.name} (${data.device.ip_address}:${data.device.port})`;
        document.getElementById('snmpTestSummaryTemplate').textContent = data.template.name;
        
        // Show status and execution time
        const executionTime = data.execution_time ? `${data.execution_time}s` : 'N/A';
        if (data.has_errors) {
            let statusHtml = `<span class="text-yellow-400">⚠ Partial Success</span><br><span class="text-xs text-gray-400">Completed in ${executionTime}</span>`;
            if (data.error_summary) {
                statusHtml += `<br><span class="text-xs text-red-400 mt-1 block">${escapeHtml(data.error_summary)}</span>`;
            }
            document.getElementById('snmpTestSummaryStatus').innerHTML = statusHtml;
        } else {
            document.getElementById('snmpTestSummaryStatus').innerHTML = 
                `<span class="text-green-400">✓ Success</span><br><span class="text-xs text-gray-400">Completed in ${executionTime}</span>`;
        }

        // Display GET results
        displayGetResults(data.results.get);
        
        // Display WALK results
        displayWalkResults(data.results.walk);
        
        // Display TABLE results
        displayTableResults(data.results.table);

        resultsContainer.classList.remove('hidden');
        
        // Scroll to results
        resultsContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    // Display GET results
    function displayGetResults(getResults) {
        const container = document.getElementById('snmpTestGetResults');
        container.innerHTML = '';

        if (!getResults || Object.keys(getResults).length === 0) {
            container.innerHTML = '<p class="text-gray-400 text-sm col-span-2">No GET results</p>';
            return;
        }

        for (const [fieldName, value] of Object.entries(getResults)) {
            const resultDiv = document.createElement('div');
            resultDiv.className = 'bg-gray-700/50 rounded p-3';
            
            if (typeof value === 'object' && value.error) {
                resultDiv.innerHTML = `
                    <div class="text-xs text-gray-400 mb-1">${escapeHtml(fieldName)}</div>
                    <div class="text-sm text-red-400">Error: ${escapeHtml(value.error)}</div>
                `;
            } else {
                resultDiv.innerHTML = `
                    <div class="text-xs text-gray-400 mb-1">${escapeHtml(fieldName)}</div>
                    <div class="text-sm text-white font-mono break-all">${escapeHtml(String(value))}</div>
                `;
            }
            
            container.appendChild(resultDiv);
        }
    }

    // Display WALK results (not used but kept for compatibility)
    function displayWalkResults(walkResults) {
        // WALK results are not displayed in the simplified UI
    }

    // Display TABLE results
    function displayTableResults(tableResults) {
        const container = document.getElementById('snmpTestTableResults');
        container.innerHTML = '';

        if (!tableResults || Object.keys(tableResults).length === 0) {
            container.innerHTML = '<p class="text-gray-400 text-sm">No TABLE results</p>';
            return;
        }

        for (const [tableName, rows] of Object.entries(tableResults)) {
            const tableSection = document.createElement('div');
            tableSection.className = 'border border-gray-600 rounded-lg p-4';
            
            if (typeof rows === 'object' && rows.error) {
                tableSection.innerHTML = `
                    <h4 class="text-base font-semibold text-white mb-2">${escapeHtml(tableName)}</h4>
                    <div class="text-sm text-red-400">Error: ${escapeHtml(rows.error)}</div>
                `;
            } else if (Array.isArray(rows) && rows.length > 0) {
                const sectionId = `table-${tableName.replace(/[^a-zA-Z0-9]/g, '-')}`;
                let html = `
                    <div class="flex items-center justify-between cursor-pointer mb-4" onclick="document.getElementById('${sectionId}').classList.toggle('hidden')">
                        <h4 class="text-base font-semibold text-white">${escapeHtml(tableName)} (${rows.length} ${rows.length === 1 ? 'row' : 'rows'})</h4>
                        <svg class="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                        </svg>
                    </div>
                    <div id="${sectionId}">
                `;
                
                // Display each row as a card with key-value pairs
                rows.forEach((row, index) => {
                    html += `
                        <div class="bg-gray-700/50 rounded p-4 mb-3">
                            <div class="text-xs text-gray-400 mb-3">Row ${index + 1}</div>
                            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                    `;
                    
                    for (const [key, value] of Object.entries(row)) {
                        html += `
                            <div>
                                <div class="text-xs text-gray-400 mb-1">${escapeHtml(key)}</div>
                                <div class="text-sm text-white font-mono break-all">${escapeHtml(String(value))}</div>
                            </div>
                        `;
                    }
                    
                    html += `
                            </div>
                        </div>
                    `;
                });
                
                html += `</div>`; // Close collapsible div
                
                tableSection.innerHTML = html;
            } else {
                tableSection.innerHTML = `
                    <h4 class="text-base font-semibold text-white mb-2">${escapeHtml(tableName)}</h4>
                    <div class="text-sm text-gray-400">No rows</div>
                `;
            }
            
            container.appendChild(tableSection);
        }
    }

    // Helper function to escape HTML
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Helper function to get CSRF token
    function getCookie(name) {
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
});
