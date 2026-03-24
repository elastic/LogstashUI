//Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
//or more contributor license agreements. Licensed under the Elastic License;
//you may not use this file except in compliance with the Elastic License.

document.addEventListener('DOMContentLoaded', function() {
    let editor = null;
    let currentFile = 'logstash.yml';
    let currentMode = 'form'; // 'form' or 'code'
    let currentPolicy = null;
    let customPolicies = []; // Store custom policy names
    
    // Make currentFile globally accessible for save function
    window.policyCurrentFile = currentFile;
    
    // File contents will be loaded from the backend when a policy is selected
    // Initialize empty fileContents object
    const fileContents = {
        'logstash.yml': '',
        'jvm.options': '',
        'log4j2.properties': ''
    };
    
    // Make fileContents globally accessible for save function
    window.policyFileContents = fileContents;
    
    // Initialize CodeMirror
    function initCodeMirror() {
        const textarea = document.getElementById('codeEditor');
        if (!textarea) return;
        
        editor = CodeMirror.fromTextArea(textarea, {
            lineNumbers: true,
            mode: 'text/x-yaml',
            indentUnit: 2,
            tabSize: 2,
            indentWithTabs: false,
            lineWrapping: true,
            matchBrackets: true,
            autoCloseBrackets: true,
            extraKeys: {
                "Tab": function(cm) {
                    cm.replaceSelection("  ", "end");
                }
            }
        });
        
        // Make editor globally accessible
        window.policyEditor = editor;
        
        // Set initial content
        editor.setValue(fileContents[currentFile]);
        
        // Auto-refresh to ensure proper rendering
        setTimeout(() => {
            editor.refresh();
        }, 100);
    }
    
    // File tab switching
    document.querySelectorAll('.file-tab').forEach(tab => {
        tab.addEventListener('click', function() {
            const file = this.dataset.file;
            
            // Update active tab
            document.querySelectorAll('.file-tab').forEach(t => {
                t.classList.remove('active');
                const span = t.querySelector('span');
                if (span) {
                    span.classList.remove('text-white');
                    span.classList.add('text-gray-400');
                }
            });
            this.classList.add('active');
            const span = this.querySelector('span');
            if (span) {
                span.classList.remove('text-gray-400');
                span.classList.add('text-white');
            }
            
            // Store current file before switching
            const previousFile = currentFile;
            
            // Save current editor content BEFORE switching (if in code mode and editor exists)
            if (editor && previousFile && previousFile !== 'enrollment-tokens' && currentMode === 'code') {
                const currentContent = editor.getValue();
                if (currentContent !== undefined && currentContent !== null) {
                    fileContents[previousFile] = currentContent;
                }
            }
            
            // Now update to the new file
            currentFile = file;
            
            // Update global currentFile reference
            window.policyCurrentFile = file;
            
            // Handle enrollment tokens tab
            if (file === 'enrollment-tokens') {
                // Hide mode toggle for enrollment tokens
                const modeToggleContainer = document.getElementById('modeToggleContainer');
                modeToggleContainer.classList.add('hidden');
                
                // Hide form and code editors
                const formModeEditor = document.getElementById('formModeEditor');
                const codeModeEditor = document.getElementById('codeModeEditor');
                const enrollmentTokensView = document.getElementById('enrollmentTokensView');
                
                if (formModeEditor) formModeEditor.classList.add('hidden');
                if (codeModeEditor) codeModeEditor.classList.add('hidden');
                if (enrollmentTokensView) {
                    enrollmentTokensView.classList.remove('hidden');
                    // Load enrollment tokens for current policy
                    loadEnrollmentTokens();
                }
                return; // Exit early for enrollment tokens tab
            }
            
            // Show/hide mode toggle based on file type (only for logstash.yml)
            const modeToggleContainer = document.getElementById('modeToggleContainer');
            const enrollmentTokensView = document.getElementById('enrollmentTokensView');
            if (enrollmentTokensView) enrollmentTokensView.classList.add('hidden');
            
            if (file === 'logstash.yml') {
                modeToggleContainer.classList.remove('hidden');
                // Automatically switch to Form mode for logstash.yml
                switchToFormMode();
            } else {
                modeToggleContainer.classList.add('hidden');
                // Automatically switch to Code mode for jvm.options and log4j2.properties
                switchToCodeMode();
            }
            
            if (editor) {
                // Update mode based on file type
                let mode = 'text/plain';
                if (file.endsWith('.yml')) {
                    mode = 'text/x-yaml';
                } else if (file.endsWith('.options') || file.endsWith('.properties')) {
                    // Use simple comment mode for jvm.options and log4j2.properties
                    mode = 'text/x-simplecomment';
                }
                editor.setOption('mode', mode);
                
                // Load new file content - ALWAYS use stored content from fileContents
                const contentToLoad = fileContents[file] || '';
                editor.setValue(contentToLoad);
                editor.refresh();
            }
        });
    });
    
    // Mode toggle (Form/Code)
    const formModeBtn = document.getElementById('formModeBtn');
    const codeModeBtn = document.getElementById('codeModeBtn');
    const formModeEditor = document.getElementById('formModeEditor');
    const codeModeEditor = document.getElementById('codeModeEditor');
    
    function switchToFormMode() {
        currentMode = 'form';
        formModeBtn.classList.add('active');
        codeModeBtn.classList.remove('active');
        formModeEditor.classList.remove('hidden');
        codeModeEditor.classList.add('hidden');
    }
    
    function switchToCodeMode() {
        currentMode = 'code';
        codeModeBtn.classList.add('active');
        formModeBtn.classList.remove('active');
        codeModeEditor.classList.remove('hidden');
        formModeEditor.classList.add('hidden');
        
        // Initialize CodeMirror if not already done
        if (!editor) {
            initCodeMirror();
        } else {
            // Reload current file content from fileContents to ensure it's correct
            const contentToLoad = fileContents[currentFile] || '';
            editor.setValue(contentToLoad);
            editor.refresh();
        }
    }
    
    formModeBtn.addEventListener('click', switchToFormMode);
    codeModeBtn.addEventListener('click', switchToCodeMode);
    
    // Global Config toggle
    const globalConfigToggle = document.getElementById('globalConfigToggle');
    const globalConfigContent = document.getElementById('globalConfigContent');
    const globalConfigChevron = document.getElementById('globalConfigChevron');
    
    globalConfigToggle.addEventListener('click', function() {
        globalConfigContent.classList.toggle('hidden');
        globalConfigChevron.classList.toggle('rotate-180');
    });
    
    // Save button
    document.getElementById('saveBtn').addEventListener('click', savePolicyChanges);
    
    // Deploy button
    document.getElementById('deployBtn').addEventListener('click', function() {
        const policySelect = document.getElementById('policySelect');
        const selectedOption = policySelect.options[policySelect.selectedIndex];
        const policyId = selectedOption.dataset.policyId;
        const policyName = selectedOption.dataset.policyName || selectedOption.textContent;
        
        if (!policyId) {
            showToast('No policy selected', 'error');
            return;
        }
        
        // Show modal and load diff
        showDeployDiffModal();
        loadPolicyDiff(policyId, policyName);
    });
    
    // Policy dropdown change handler
    const policySelect = document.getElementById('policySelect');
    const defaultPolicyIndicator = document.getElementById('defaultPolicyIndicator');
    const saveBtn = document.getElementById('saveBtn');
    const deployBtn = document.getElementById('deployBtn');
    
    policySelect.addEventListener('change', async function() {
        const selectedValue = this.value;
        
        if (selectedValue === 'add_new') {
            // Reset to default values for new policy
            document.getElementById('settingsPath').value = '/etc/logstash/';
            document.getElementById('logsPath').value = '/var/log/logstash';
            
            // Show popup to add new policy
            const policyName = await ConfirmationModal.prompt(
                'Enter a name for the new policy:',
                '',
                'Add New Policy',
                'e.g., Production Policy'
            );
            
            if (policyName && policyName.trim()) {
                const trimmedName = policyName.trim();
                
                // Check if policy already exists
                if (customPolicies.includes(trimmedName) || trimmedName.toLowerCase() === 'default policy') {
                    await ConfirmationModal.show(
                        'A policy with this name already exists. Please choose a different name.',
                        'Duplicate Policy Name',
                        'OK',
                        null,
                        true
                    );
                    // Reset to current policy
                    this.value = currentPolicy;
                    return;
                }
                
                // Make HTMX call to add policy
                try {
                    const response = await fetch('/ConnectionManager/AddPolicy/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken()
                        },
                        body: JSON.stringify({
                            name: trimmedName,
                            settings_path: document.getElementById('settingsPath').value,
                            logs_path: document.getElementById('logsPath').value,
                            logstash_yml: fileContents['logstash.yml'],
                            jvm_options: fileContents['jvm.options'],
                            log4j2_properties: fileContents['log4j2.properties']
                        })
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        showToast(data.message, 'success');
                        
                        // Reload policies to refresh the UI and show main content
                        await loadPolicies();
                    } else {
                        showToast(data.error || 'Failed to create policy', 'error');
                        this.value = currentPolicy;
                    }
                } catch (error) {
                    console.error('Error creating policy:', error);
                    showToast('Failed to create policy: ' + error.message, 'error');
                    this.value = currentPolicy;
                }
            } else {
                // User cancelled or entered empty name, reset to current policy
                this.value = currentPolicy;
            }
        } else {
            // Regular policy selection
            currentPolicy = selectedValue;
            
            // Update UI based on whether it's the default policy
            const isDefaultPolicy = selectedValue === 'default';
            updatePolicyUI(isDefaultPolicy);
            
            // Load policy data into form if it's a custom policy
            if (!isDefaultPolicy) {
                // Fetch fresh policy data from database
                loadPolicyData(selectedValue);
            }
        }
    });
    
    // Function to update UI based on policy type
    function updatePolicyUI(isDefaultPolicy) {
        const deletePolicyBtn = document.getElementById('deletePolicyBtn');
        const settingsPathInput = document.getElementById('settingsPath');
        const logsPathInput = document.getElementById('logsPath');
        
        // All policies are now editable (no default policy)
        // Just ensure everything is enabled
        if (deletePolicyBtn) {
            deletePolicyBtn.classList.remove('hidden');
        }
        
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.classList.remove('opacity-50', 'cursor-not-allowed');
            saveBtn.title = '';
        }
        
        if (settingsPathInput) {
            settingsPathInput.disabled = false;
            settingsPathInput.classList.remove('opacity-50', 'cursor-not-allowed');
        }
        
        if (logsPathInput) {
            logsPathInput.disabled = false;
            logsPathInput.classList.remove('opacity-50', 'cursor-not-allowed');
        }
        
        if (editor) {
            editor.setOption('readOnly', false);
            editor.getWrapperElement().style.opacity = '1';
            editor.getWrapperElement().style.cursor = 'text';
        }
        
        if (deployBtn) {
            deployBtn.disabled = false;
            deployBtn.classList.remove('opacity-50', 'cursor-not-allowed');
        }
    }
    
    // Load policies on page load
    loadPolicies();
    
    // Add click handler for empty state Add Policy button
    const emptyStateAddPolicyBtn = document.getElementById('emptyStateAddPolicyBtn');
    if (emptyStateAddPolicyBtn) {
        emptyStateAddPolicyBtn.addEventListener('click', function() {
            // Trigger the same flow as selecting "+ Add Policy" from dropdown
            const policySelect = document.getElementById('policySelect');
            policySelect.value = 'add_new';
            policySelect.dispatchEvent(new Event('change'));
        });
    }
    
    // Initialize in Form mode by default
    // (Form mode is already active by default in HTML)
});

// Load specific policy data from the server
async function loadPolicyData(policyValue) {
    try {
        const response = await fetch('/ConnectionManager/GetPolicies/', {
            method: 'GET',
            headers: {
                'X-CSRFToken': getCsrfToken()
            }
        });
        
        const data = await response.json();
        
        if (data.success && data.policies) {
            // Find the policy by matching the value
            const policySelect = document.getElementById('policySelect');
            const selectedOption = policySelect.options[policySelect.selectedIndex];
            const policyName = selectedOption.dataset.policyName || selectedOption.textContent;
            
            const policy = data.policies.find(p => p.name === policyName);
            
            if (policy) {
                // Update form fields
                document.getElementById('settingsPath').value = policy.settings_path;
                document.getElementById('logsPath').value = policy.logs_path;
                
                // Update file contents with fresh data from database
                window.policyFileContents['logstash.yml'] = policy.logstash_yml;
                window.policyFileContents['jvm.options'] = policy.jvm_options;
                window.policyFileContents['log4j2.properties'] = policy.log4j2_properties;
                
                // Update editor if it's initialized and showing current file
                if (window.policyEditor && window.policyCurrentFile) {
                    window.policyEditor.setValue(window.policyFileContents[window.policyCurrentFile] || '');
                    window.policyEditor.refresh();
                }
            }
        }
    } catch (error) {
        console.error('Error loading policy data:', error);
        showToast('Failed to load policy data: ' + error.message, 'error');
    }
}

// Load all policies from the server
async function loadPolicies() {
    try {
        const response = await fetch('/ConnectionManager/GetPolicies/', {
            method: 'GET',
            headers: {
                'X-CSRFToken': getCsrfToken()
            }
        });
        
        const data = await response.json();
        
        if (data.success && data.policies) {
            const policySelect = document.getElementById('policySelect');
            const addNewOption = policySelect.querySelector('option[value="add_new"]');
            const emptyState = document.getElementById('emptyState');
            const mainContent = document.getElementById('mainContent');
            
            // Clear existing policies (keep only + Add Policy)
            const options = Array.from(policySelect.options);
            options.forEach(option => {
                if (option.value !== 'add_new') {
                    option.remove();
                }
            });
            
            // Check if we have any policies
            if (data.policies.length === 0) {
                // Show empty state, hide main content
                emptyState.classList.remove('hidden');
                mainContent.classList.add('hidden');
                return;
            }
            
            // Hide empty state, show main content
            emptyState.classList.add('hidden');
            mainContent.classList.remove('hidden');
            
            // Add policies from server
            data.policies.forEach(policy => {
                const option = document.createElement('option');
                option.value = policy.name.toLowerCase().replace(/\s+/g, '_');
                option.textContent = policy.name;
                option.dataset.policyName = policy.name;
                option.dataset.policyId = policy.id;
                
                // Store policy data for later use
                option.dataset.settingsPath = policy.settings_path;
                option.dataset.logsPath = policy.logs_path;
                option.dataset.logstashYml = policy.logstash_yml;
                option.dataset.jvmOptions = policy.jvm_options;
                option.dataset.log4j2Properties = policy.log4j2_properties;
                
                // Insert before "+ Add Policy" option
                policySelect.insertBefore(option, addNewOption);
                
                // Add to customPolicies array
                if (!window.customPolicies) {
                    window.customPolicies = [];
                }
                window.customPolicies.push(policy.name);
            });
            
            // Auto-select first policy if policies exist
            if (data.policies.length > 0) {
                const firstPolicy = data.policies[0];
                policySelect.value = firstPolicy.name.toLowerCase().replace(/\s+/g, '_');
                window.currentPolicy = policySelect.value;
                
                // Trigger change event to load the policy data
                policySelect.dispatchEvent(new Event('change'));
            }
        }
    } catch (error) {
        console.error('Error loading policies:', error);
        showToast('Failed to load policies: ' + error.message, 'error');
    }
}

// Get CSRF token from cookie
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

// Save policy changes
async function savePolicyChanges() {
    const policySelect = document.getElementById('policySelect');
    const selectedOption = policySelect.options[policySelect.selectedIndex];
    const policyName = selectedOption.dataset.policyName || selectedOption.textContent;
    
    if (policySelect.value === 'default') {
        showToast('Cannot save changes to Default Policy', 'error');
        return;
    }
    
    // Get the current editor instance and save current content to fileContents
    const settingsPath = document.getElementById('settingsPath').value;
    const logsPath = document.getElementById('logsPath').value;
    
    // If editor is active, save current editor content to fileContents
    if (window.policyEditor && window.policyFileContents) {
        // Get the current file being edited
        const currentFile = window.policyCurrentFile || 'logstash.yml';
        // Save current editor content to fileContents
        window.policyFileContents[currentFile] = window.policyEditor.getValue();
    }
    
    try {
        const response = await fetch('/ConnectionManager/UpdatePolicy/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                policy_name: policyName,
                settings_path: settingsPath,
                logs_path: logsPath,
                logstash_yml: window.policyFileContents ? window.policyFileContents['logstash.yml'] : '',
                jvm_options: window.policyFileContents ? window.policyFileContents['jvm.options'] : '',
                log4j2_properties: window.policyFileContents ? window.policyFileContents['log4j2.properties'] : ''
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast(data.message, 'success');
        } else {
            showToast(data.error || 'Failed to update policy', 'error');
        }
    } catch (error) {
        console.error('Error updating policy:', error);
        showToast('Failed to update policy: ' + error.message, 'error');
    }
}

// Delete current policy
async function deleteCurrentPolicy() {
    const policySelect = document.getElementById('policySelect');
    const selectedOption = policySelect.options[policySelect.selectedIndex];
    const policyName = selectedOption.dataset.policyName || selectedOption.textContent;
    
    if (policySelect.value === 'default') {
        showToast('Cannot delete Default Policy', 'error');
        return;
    }
    
    const confirmed = await ConfirmationModal.show(
        `Are you sure you want to delete the policy "${policyName}"?\n\nThis action cannot be undone.`,
        'Delete Policy',
        'Delete',
        null,
        false
    );
    
    if (!confirmed) {
        return;
    }
    
    try {
        const response = await fetch('/ConnectionManager/DeletePolicy/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                policy_name: policyName
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast(data.message, 'success');
            
            // Reload policies to refresh the UI
            // This will show empty state if no policies remain
            await loadPolicies();
        } else {
            showToast(data.error || 'Failed to delete policy', 'error');
        }
    } catch (error) {
        console.error('Error deleting policy:', error);
        showToast('Failed to delete policy: ' + error.message, 'error');
    }
}

// Load enrollment tokens for the current policy
async function loadEnrollmentTokens() {
    const policySelect = document.getElementById('policySelect');
    const selectedOption = policySelect.options[policySelect.selectedIndex];
    const policyId = selectedOption.dataset.policyId;
    
    if (!policyId) {
        console.error('No policy ID found');
        return;
    }
    
    try {
        const response = await fetch(`/ConnectionManager/GetEnrollmentTokens/?policy_id=${policyId}`, {
            method: 'GET',
            headers: {
                'X-CSRFToken': getCsrfToken()
            }
        });
        
        const data = await response.json();
        
        const tableBody = document.getElementById('enrollmentTokensTableBody');
        const noTokensMessage = document.getElementById('noTokensMessage');
        
        if (data.success && data.tokens && data.tokens.length > 0) {
            // Hide no tokens message, show table
            noTokensMessage.classList.add('hidden');
            tableBody.parentElement.parentElement.classList.remove('hidden');
            
            // Clear existing rows
            tableBody.innerHTML = '';
            
            // Add token rows
            data.tokens.forEach(token => {
                const row = document.createElement('tr');
                row.className = 'hover:bg-gray-700';
                row.innerHTML = `
                    <td class="px-4 py-3 text-sm text-gray-300">
                        <span class="font-medium">${escapeHtml(token.name)}</span>
                    </td>
                    <td class="px-4 py-3 text-sm text-gray-300">
                        <div class="flex items-center gap-2">
                            <button onclick="toggleTokenDisplay(${token.id}, '${escapeHtml(token.raw_token)}', '${escapeHtml(token.encoded_token)}')" class="text-yellow-400 hover:text-yellow-300 text-xs mr-2">
                                <span id="toggle-btn-${token.id}">Reveal Raw</span>
                            </button>
                            <span class="font-mono text-xs break-all" id="token-display-${token.id}">${token.encoded_token}</span>
                        </div>
                    </td>
                    <td class="px-4 py-3 text-sm text-left">
                        <div class="action-menu relative inline-block">
                            <button class="action-menu-button p-1 hover:bg-gray-700 rounded" onclick="toggleEnrollmentTokenMenu(${token.id})">
                                <svg class="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                                    <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
                                </svg>
                            </button>
                            <div id="token-menu-${token.id}" class="action-menu-items hidden absolute right-0 z-50 w-32 bg-gray-800 rounded-md shadow-lg py-1" role="menu">
                                <div class="px-1 py-1">
                                    <a href="#" onclick="event.preventDefault(); copyTokenToClipboard('${escapeHtml(token.encoded_token)}'); toggleEnrollmentTokenMenu(${token.id}); return false;" class="group flex items-center px-4 py-2 text-sm text-blue-400 hover:bg-gray-700 rounded-md" role="menuitem">
                                        <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                                        </svg>
                                        Copy
                                    </a>
                                    <a href="#" onclick="event.preventDefault(); deleteEnrollmentToken(${token.id}); return false;" class="group flex items-center px-4 py-2 text-sm text-red-400 hover:bg-gray-700 rounded-md" role="menuitem">
                                        <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                        </svg>
                                        Delete
                                    </a>
                                </div>
                            </div>
                        </div>
                    </td>
                `;
                tableBody.appendChild(row);
            });
        } else {
            // Show no tokens message, hide table
            noTokensMessage.classList.remove('hidden');
            tableBody.parentElement.parentElement.classList.add('hidden');
        }
    } catch (error) {
        console.error('Error loading enrollment tokens:', error);
        showToast('Failed to load enrollment tokens: ' + error.message, 'error');
    }
}

// Toggle between encoded and raw token display
function toggleTokenDisplay(tokenId, rawToken, encodedToken) {
    const displayElement = document.getElementById(`token-display-${tokenId}`);
    const toggleButton = document.getElementById(`toggle-btn-${tokenId}`);
    
    if (displayElement.textContent === encodedToken) {
        // Show raw token
        displayElement.textContent = rawToken;
        toggleButton.textContent = 'Hide Raw';
    } else {
        // Show encoded token
        displayElement.textContent = encodedToken;
        toggleButton.textContent = 'Reveal Raw';
    }
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Toggle enrollment token menu dropdown
function toggleEnrollmentTokenMenu(tokenId) {
    const menu = document.getElementById(`token-menu-${tokenId}`);
    
    // Close all other menus
    document.querySelectorAll('.action-menu-items').forEach(m => {
        if (m.id !== `token-menu-${tokenId}`) {
            m.classList.add('hidden');
        }
    });
    
    // Toggle this menu
    menu.classList.toggle('hidden');
}

// Delete enrollment token
async function deleteEnrollmentToken(tokenId) {
    const confirmed = await ConfirmationModal.show(
        'Are you sure you want to delete this enrollment token? This action cannot be undone.',
        'Delete Enrollment Token',
        'Delete',
        null,
        false
    );
    
    if (!confirmed) {
        return;
    }
    
    try {
        const response = await fetch('/ConnectionManager/DeleteEnrollmentToken/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                token_id: tokenId
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast(data.message || 'Enrollment token deleted successfully', 'success');
            // Reload enrollment tokens
            loadEnrollmentTokens();
        } else {
            showToast(data.error || 'Failed to delete enrollment token', 'error');
        }
    } catch (error) {
        console.error('Error deleting enrollment token:', error);
        showToast('Failed to delete enrollment token: ' + error.message, 'error');
    }
}

// Copy token to clipboard
function copyTokenToClipboard(token) {
    navigator.clipboard.writeText(token).then(() => {
        showToast('Token copied to clipboard', 'success');
    }).catch(err => {
        console.error('Failed to copy token:', err);
        showToast('Failed to copy token', 'error');
    });
}

// Add new enrollment token
async function addEnrollmentToken() {
    const policySelect = document.getElementById('policySelect');
    const selectedOption = policySelect.options[policySelect.selectedIndex];
    const policyId = selectedOption.dataset.policyId;
    
    if (!policyId) {
        showToast('No policy selected', 'error');
        return;
    }
    
    // Show prompt to name the enrollment token
    const tokenName = await ConfirmationModal.prompt(
        'Enter a name for the enrollment token:',
        '',
        'Add Enrollment Token',
        'e.g., Production Token'
    );
    
    if (!tokenName || !tokenName.trim()) {
        // User cancelled or entered empty name
        return;
    }
    
    const trimmedName = tokenName.trim();
    
    try {
        const response = await fetch('/ConnectionManager/AddEnrollmentToken/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                policy_id: policyId,
                name: trimmedName
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast(data.message || 'Enrollment token created successfully', 'success');
            // Reload enrollment tokens
            loadEnrollmentTokens();
        } else {
            showToast(data.error || 'Failed to create enrollment token', 'error');
        }
    } catch (error) {
        console.error('Error creating enrollment token:', error);
        showToast('Failed to create enrollment token: ' + error.message, 'error');
    }
}

// Close menus when clicking outside
document.addEventListener('click', function(event) {
    if (!event.target.closest('.action-menu')) {
        document.querySelectorAll('.action-menu-items').forEach(menu => {
            menu.classList.add('hidden');
        });
    }
});
