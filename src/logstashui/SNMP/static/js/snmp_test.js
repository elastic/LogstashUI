/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

document.addEventListener('DOMContentLoaded', function() {
    // ─────────────────────────────────────────────────────────────
    // Modal elements
    // ─────────────────────────────────────────────────────────────
    const snmpTestModal = document.getElementById('snmpTestModal');
    const testSnmpBtn = document.getElementById('testSnmpBtn');
    const closeSnmpTestModal = document.getElementById('closeSnmpTestModal');

    // ─────────────────────────────────────────────────────────────
    // Tab elements
    // ─────────────────────────────────────────────────────────────
    const tabProfile = document.getElementById('snmpTestTabProfile');
    const tabWalk    = document.getElementById('snmpTestTabWalk');
    const contentProfile = document.getElementById('snmpTestProfileContent');
    const contentWalk    = document.getElementById('snmpTestWalkContent');

    function activateTab(tab) {
        // Reset both tabs
        [tabProfile, tabWalk].forEach(t => {
            t.classList.remove('border-primary', 'text-primary');
            t.classList.add('border-transparent', 'text-gray-400');
        });
        // Activate selected
        tab.classList.add('border-primary', 'text-primary');
        tab.classList.remove('border-transparent', 'text-gray-400');

        // Show/hide content
        if (tab === tabProfile) {
            contentProfile.classList.remove('hidden');
            contentWalk.classList.add('hidden');
        } else {
            contentWalk.classList.remove('hidden');
            contentProfile.classList.add('hidden');
        }
    }

    if (tabProfile) tabProfile.addEventListener('click', () => activateTab(tabProfile));
    if (tabWalk)    tabWalk.addEventListener('click',    () => activateTab(tabWalk));

    // ─────────────────────────────────────────────────────────────
    // Profile test form elements
    // ─────────────────────────────────────────────────────────────
    const deviceSelect    = document.getElementById('snmpTestDeviceSelect');
    const templateSelect  = document.getElementById('snmpTestTemplateSelect');
    const runTestBtn      = document.getElementById('snmpTestRunTestBtn');
    const runTestBtnText  = document.getElementById('snmpTestRunTestBtnText');
    const deviceInfo      = document.getElementById('snmpTestDeviceInfo');
    const deviceInfoText  = document.getElementById('snmpTestDeviceInfoText');
    const templateInfo    = document.getElementById('snmpTestTemplateInfo');
    const templateInfoText = document.getElementById('snmpTestTemplateInfoText');
    const loadingState    = document.getElementById('snmpTestLoadingState');
    const resultsContainer = document.getElementById('snmpTestResultsContainer');
    const errorState      = document.getElementById('snmpTestErrorState');
    const errorMessage    = document.getElementById('snmpTestErrorMessage');

    // ─────────────────────────────────────────────────────────────
    // Walk form elements
    // ─────────────────────────────────────────────────────────────
    const walkHostInput      = document.getElementById('snmpWalkHostInput');
    const walkCredSelect     = document.getElementById('snmpWalkCredentialSelect');
    const walkPortInput      = document.getElementById('snmpWalkPortInput');
    const walkStartOidInput  = document.getElementById('snmpWalkStartOidInput');
    const walkRunBtn         = document.getElementById('snmpWalkRunBtn');
    const walkRunBtnText     = document.getElementById('snmpWalkRunBtnText');
    const walkLoadingState   = document.getElementById('snmpWalkLoadingState');
    const walkResultsContainer = document.getElementById('snmpWalkResultsContainer');
    const walkErrorState     = document.getElementById('snmpWalkErrorState');
    const walkErrorMessage   = document.getElementById('snmpWalkErrorMessage');
    const walkResultsBody    = document.getElementById('snmpWalkResultsBody');
    const walkSearchInput    = document.getElementById('snmpWalkSearchInput');
    const walkCopyBtn = document.getElementById('snmpWalkCopyBtn');

    // Full walk results data (for filtering)
    let walkAllResults = [];

    // ─────────────────────────────────────────────────────────────
    // Modal controls
    // ─────────────────────────────────────────────────────────────
    if (testSnmpBtn) {
        testSnmpBtn.addEventListener('click', function() {
            snmpTestModal.classList.remove('hidden');
            snmpTestModal.classList.add('flex');
            resetProfileTab();
            resetWalkTab();
            activateTab(tabProfile);
        });
    }

    if (closeSnmpTestModal) {
        closeSnmpTestModal.addEventListener('click', closeModal);
    }

    const snmpTestModalBackdrop = document.getElementById('snmpTestBackdrop');
    if (snmpTestModalBackdrop) {
        snmpTestModalBackdrop.addEventListener('click', closeModal);
    }

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && !snmpTestModal.classList.contains('hidden')) {
            closeModal();
        }
    });

    function closeModal() {
        snmpTestModal.classList.add('hidden');
        snmpTestModal.classList.remove('flex');
        document.body.style.overflow = '';
    }

    // ─────────────────────────────────────────────────────────────
    // Profile tab reset
    // ─────────────────────────────────────────────────────────────
    function resetProfileTab() {
        if (deviceSelect) deviceSelect.value = '';
        if (templateSelect) templateSelect.value = '';
        if (deviceInfo) deviceInfo.classList.add('hidden');
        if (templateInfo) templateInfo.classList.add('hidden');
        if (resultsContainer) resultsContainer.classList.add('hidden');
        if (errorState) errorState.classList.add('hidden');
        if (loadingState) loadingState.classList.add('hidden');
        if (runTestBtn) runTestBtn.disabled = true;
    }

    // ─────────────────────────────────────────────────────────────
    // Walk tab reset
    // ─────────────────────────────────────────────────────────────
    function resetWalkTab() {
        if (walkHostInput) walkHostInput.value = '';
        if (walkCredSelect) walkCredSelect.value = '';
        if (walkPortInput) walkPortInput.value = '161';
        if (walkStartOidInput) walkStartOidInput.value = '1.3.6.1';
        if (walkLoadingState) walkLoadingState.classList.add('hidden');
        if (walkResultsContainer) walkResultsContainer.classList.add('hidden');
        if (walkErrorState) walkErrorState.classList.add('hidden');
        if (walkRunBtn) walkRunBtn.disabled = true;
        walkAllResults = [];
        window._snmpWalkResults = [];
    }

    // ─────────────────────────────────────────────────────────────
    // Profile tab: device & template handlers
    // ─────────────────────────────────────────────────────────────
    if (deviceSelect) {
        deviceSelect.addEventListener('change', function() {
            const opt = this.options[this.selectedIndex];
            if (this.value) {
                const ip = opt.dataset.ip;
                const port = opt.dataset.port;
                const hasCredential = opt.dataset.hasCredential === 'true';
                const templateId = opt.dataset.templateId;

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

                if (templateId && templateSelect.querySelector(`option[value="${templateId}"]`)) {
                    templateSelect.value = templateId;
                    templateSelect.dispatchEvent(new Event('change'));
                }
            } else {
                deviceInfo.classList.add('hidden');
            }
            updateRunButton();
        });
    }

    if (templateSelect) {
        templateSelect.addEventListener('change', function() {
            const opt = this.options[this.selectedIndex];
            if (this.value) {
                const vendor = opt.dataset.vendor;
                const isOfficial = opt.dataset.official === 'True';
                templateInfoText.textContent = `${vendor}${isOfficial ? ' (Official)' : ''}`;
                templateInfo.classList.remove('hidden');
            } else {
                templateInfo.classList.add('hidden');
            }
            updateRunButton();
        });
    }

    function updateRunButton() {
        const deviceSelected = deviceSelect && deviceSelect.value !== '';
        const templateSelected = templateSelect && templateSelect.value !== '';
        const deviceHasCredential = deviceSelected &&
            deviceSelect.options[deviceSelect.selectedIndex].dataset.hasCredential === 'true';
        if (runTestBtn) {
            runTestBtn.disabled = !(deviceSelected && templateSelected && deviceHasCredential);
        }
    }

    // ─────────────────────────────────────────────────────────────
    // Walk tab: enable/disable button
    // ─────────────────────────────────────────────────────────────
    function updateWalkButton() {
        const hostOk = walkHostInput && walkHostInput.value.trim() !== '';
        const credOk = walkCredSelect && walkCredSelect.value !== '';
        if (walkRunBtn) walkRunBtn.disabled = !(hostOk && credOk);
    }

    if (walkHostInput)  walkHostInput.addEventListener('input', updateWalkButton);
    if (walkCredSelect) walkCredSelect.addEventListener('change', updateWalkButton);

    // ─────────────────────────────────────────────────────────────
    // Profile test run handler
    // ─────────────────────────────────────────────────────────────
    if (runTestBtn) {
        runTestBtn.addEventListener('click', async function(event) {
            event.preventDefault();
            event.stopPropagation();

            const deviceId = parseInt(deviceSelect.value);
            const templateId = parseInt(templateSelect.value);
            if (!deviceId || !templateId) return;

            resultsContainer.classList.add('hidden');
            errorState.classList.add('hidden');
            loadingState.classList.remove('hidden');
            runTestBtn.disabled = true;
            runTestBtnText.textContent = 'Running...';

            try {
                const response = await fetch('/SNMP/RunSNMPTest/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken')
                    },
                    body: JSON.stringify({ device_id: deviceId, template_id: templateId })
                });

                const data = await response.json();

                if (data.results) {
                    displayResults(data);
                } else if (data.error) {
                    displayError(data.error);
                } else {
                    displayError('Unknown error occurred');
                }
            } catch (error) {
                displayError(`Network error: ${error.message}`);
            } finally {
                loadingState.classList.add('hidden');
                runTestBtn.disabled = false;
                runTestBtnText.textContent = 'Run Test';
            }
        });
    }

    function displayError(msg) {
        loadingState.classList.add('hidden');
        resultsContainer.classList.add('hidden');
        errorMessage.textContent = msg;
        errorState.classList.remove('hidden');
        errorState.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function displayResults(data) {
        loadingState.classList.add('hidden');
        errorState.classList.add('hidden');

        document.getElementById('snmpTestSummaryDevice').textContent =
            `${data.device.name} (${data.device.ip_address}:${data.device.port})`;
        document.getElementById('snmpTestSummaryTemplate').textContent = data.template.name;

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

        displayGetResults(data.results.get);
        displayTableResults(data.results.table);

        resultsContainer.classList.remove('hidden');
        resultsContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function displayGetResults(getResults) {
        const container = document.getElementById('snmpTestGetResults');
        container.innerHTML = '';
        if (!getResults || Object.keys(getResults).length === 0) {
            container.innerHTML = '<p class="text-gray-400 text-sm col-span-2">No GET results</p>';
            return;
        }
        for (const [fieldName, value] of Object.entries(getResults)) {
            const div = document.createElement('div');
            div.className = 'bg-gray-700/50 rounded p-3';
            if (typeof value === 'object' && value.error) {
                div.innerHTML = `
                    <div class="text-xs text-gray-400 mb-1">${escapeHtml(fieldName)}</div>
                    <div class="text-sm text-red-400">Error: ${escapeHtml(value.error)}</div>`;
            } else {
                div.innerHTML = `
                    <div class="text-xs text-gray-400 mb-1">${escapeHtml(fieldName)}</div>
                    <div class="text-sm text-white font-mono break-all">${escapeHtml(String(value))}</div>`;
            }
            container.appendChild(div);
        }
    }

    function displayTableResults(tableResults) {
        const container = document.getElementById('snmpTestTableResults');
        container.innerHTML = '';
        if (!tableResults || Object.keys(tableResults).length === 0) {
            container.innerHTML = '<p class="text-gray-400 text-sm">No TABLE results</p>';
            return;
        }
        for (const [tableName, rows] of Object.entries(tableResults)) {
            const section = document.createElement('div');
            section.className = 'border border-gray-600 rounded-lg p-4';

            if (typeof rows === 'object' && rows.error) {
                section.innerHTML = `
                    <h4 class="text-base font-semibold text-white mb-2">${escapeHtml(tableName)}</h4>
                    <div class="text-sm text-red-400">Error: ${escapeHtml(rows.error)}</div>`;
            } else if (Array.isArray(rows) && rows.length > 0) {
                const sectionId = `table-${tableName.replace(/[^a-zA-Z0-9]/g, '-')}`;
                let html = `
                    <div class="flex items-center justify-between cursor-pointer mb-4" onclick="document.getElementById('${sectionId}').classList.toggle('hidden')">
                        <h4 class="text-base font-semibold text-white">${escapeHtml(tableName)} (${rows.length} ${rows.length === 1 ? 'row' : 'rows'})</h4>
                        <svg class="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                        </svg>
                    </div>
                    <div id="${sectionId}">`;

                rows.forEach((row, index) => {
                    html += `
                        <div class="bg-gray-700/50 rounded p-4 mb-3">
                            <div class="text-xs text-gray-400 mb-3">Row ${index + 1}</div>
                            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">`;
                    for (const [key, value] of Object.entries(row)) {
                        html += `
                                <div>
                                    <div class="text-xs text-gray-400 mb-1">${escapeHtml(key)}</div>
                                    <div class="text-sm text-white font-mono break-all">${escapeHtml(String(value))}</div>
                                </div>`;
                    }
                    html += `</div></div>`;
                });

                html += `</div>`;
                section.innerHTML = html;
            } else {
                section.innerHTML = `
                    <h4 class="text-base font-semibold text-white mb-2">${escapeHtml(tableName)}</h4>
                    <div class="text-sm text-gray-400">No rows</div>`;
            }
            container.appendChild(section);
        }
    }

    // ─────────────────────────────────────────────────────────────
    // Walk run handler
    // ─────────────────────────────────────────────────────────────
    if (walkRunBtn) {
        walkRunBtn.addEventListener('click', async function(event) {
            event.preventDefault();
            event.stopPropagation();

            const host = walkHostInput.value.trim();
            const credentialId = parseInt(walkCredSelect.value);
            const port = parseInt(walkPortInput.value) || 161;
            const startOid = walkStartOidInput.value.trim() || '1.3.6.1';

            if (!host || !credentialId) return;

            walkResultsContainer.classList.add('hidden');
            walkErrorState.classList.add('hidden');
            walkLoadingState.classList.remove('hidden');
            walkRunBtn.disabled = true;
            walkRunBtnText.textContent = 'Walking...';

            try {
                const response = await fetch('/SNMP/RunSNMPWalk/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken')
                    },
                    body: JSON.stringify({
                        host: host,
                        port: port,
                        credential_id: credentialId,
                        start_oid: startOid
                    })
                });

                const data = await response.json();

                if (data.success && data.results) {
                    displayWalkResults(data);
                } else {
                    displayWalkError(data.error || 'Unknown error occurred');
                }
            } catch (error) {
                displayWalkError(`Network error: ${error.message}`);
            } finally {
                walkLoadingState.classList.add('hidden');
                walkRunBtn.disabled = false;
                walkRunBtnText.textContent = 'Run Walk';
                updateWalkButton();
            }
        });
    }

    function displayWalkError(msg) {
        walkLoadingState.classList.add('hidden');
        walkResultsContainer.classList.add('hidden');
        walkErrorMessage.textContent = msg;
        walkErrorState.classList.remove('hidden');
        walkErrorState.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function displayWalkResults(data) {
        walkLoadingState.classList.add('hidden');
        walkErrorState.classList.add('hidden');

        document.getElementById('snmpWalkSummaryHost').textContent = `${data.host}:${data.port}`;
        document.getElementById('snmpWalkSummaryCredential').textContent = data.credential;
        document.getElementById('snmpWalkSummaryCount').textContent = data.oid_count;
        document.getElementById('snmpWalkSummaryTime').textContent = `${data.execution_time}s`;

        walkAllResults = data.results || [];
        window._snmpWalkResults = walkAllResults;
        renderWalkTable(walkAllResults);

        walkResultsContainer.classList.remove('hidden');
        walkResultsContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function renderWalkTable(rows) {
        walkResultsBody.innerHTML = '';
        if (rows.length === 0) {
            walkResultsBody.innerHTML = `
                <tr>
                  <td colspan="2" class="px-4 py-6 text-center text-gray-400 text-sm">No OIDs found</td>
                </tr>`;
            return;
        }
        rows.forEach(function(row, i) {
            const tr = document.createElement('tr');
            tr.className = i % 2 === 0 ? 'bg-gray-800/30' : 'bg-gray-900/20';
            tr.innerHTML = `
                <td class="px-4 py-2 font-mono text-xs text-blue-300 align-top break-all">${escapeHtml(row.oid)}</td>
                <td class="px-4 py-2 font-mono text-xs text-gray-200 align-top break-all">${escapeHtml(String(row.value))}</td>`;
            walkResultsBody.appendChild(tr);
        });
    }

    // Walk search / filter
    if (walkSearchInput) {
        walkSearchInput.addEventListener('input', function() {
            const q = this.value.toLowerCase();
            if (!q) {
                renderWalkTable(walkAllResults);
                return;
            }
            const filtered = walkAllResults.filter(r =>
                r.oid.toLowerCase().includes(q) || String(r.value).toLowerCase().includes(q)
            );
            renderWalkTable(filtered);
        });
    }

    // Copy all walk results
    if (walkCopyBtn) {
        walkCopyBtn.addEventListener('click', function() {
            if (!walkAllResults.length) return;
            const text = walkAllResults.map(r => `${r.oid}\t${r.value}`).join('\n');
            navigator.clipboard.writeText(text).then(() => {
                const orig = walkCopyBtn.innerHTML;
                walkCopyBtn.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg> Copied!`;
                setTimeout(() => { walkCopyBtn.innerHTML = orig; }, 2000);
            });
        });
    }

    // ─────────────────────────────────────────────────────────────
    // Utility: CSRF cookie
    // ─────────────────────────────────────────────────────────────
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
