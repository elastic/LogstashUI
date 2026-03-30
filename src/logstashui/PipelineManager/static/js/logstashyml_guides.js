/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// ===========================
// Shared Guide Modal Functions
// ===========================

// Guide Modal Functions
function openDefaultGuideModal() {
    const modal = document.getElementById('defaultGuideModal');
    if (modal) {
        // Sync current values from main form to guide
        syncMainToGuide();
        modal.classList.remove('hidden');
        // Validate fields after syncing
        setTimeout(() => validateDefaultGuide(), 100);
    }
}

function closeDefaultGuideModal() {
    const modal = document.getElementById('defaultGuideModal');
    if (modal) {
        modal.classList.add('hidden');
    }
}

function openCentralizedPipelineManagementModal() {
    const modal = document.getElementById('centralizedPipelineManagementModal');
    if (modal) {
        // Sync current values from main form to guide
        syncMainToCpmGuide();
        modal.classList.remove('hidden');
        // Validate fields after syncing
        setTimeout(() => {
            console.log('Running CPM validation on modal open');
            validateCpmGuide();
        }, 100);
    }
}

function closeCentralizedPipelineManagementModal() {
    const modal = document.getElementById('centralizedPipelineManagementModal');
    if (modal) {
        modal.classList.add('hidden');
    }
}

// ===========================
// Default Guide Functions
// ===========================

// Sync guide inputs to main form
function syncGuideToMain(fieldName, value) {
    const mainField = document.querySelector(`[name="${fieldName}"]`);
    if (mainField) {
        mainField.value = value;
        // Trigger change detection
        detectChanges();
        checkConfigNotifications();
    }
}

// Sync main form values to guide inputs when opening modal
function syncMainToGuide() {
    // Log Level
    const logLevel = document.querySelector('[name="log.level"]');
    const guideLogLevel = document.getElementById('guideLogLevel');
    if (logLevel && guideLogLevel) {
        guideLogLevel.value = logLevel.value;
    }
    
    // Log Format
    const logFormat = document.querySelector('[name="log.format"]');
    const guideLogFormat = document.getElementById('guideLogFormat');
    if (logFormat && guideLogFormat) {
        guideLogFormat.value = logFormat.value;
    }
    
    // Logs Path
    const logsPath = document.querySelector('[name="path.logs"]');
    const guideLogsPath = document.getElementById('guideLogsPath');
    if (logsPath && guideLogsPath) {
        guideLogsPath.value = logsPath.value;
    }
}

// Validate Default guide fields and apply red/green highlighting
function validateDefaultGuide() {
    const guideLogLevel = document.getElementById('guideLogLevel');
    const guideLogFormat = document.getElementById('guideLogFormat');
    const guideLogsPath = document.getElementById('guideLogsPath');
    const policyLogsPath = document.getElementById('logsPath');
    
    let redCount = 0;
    let greenCount = 0;
    
    // Validate Log Level (should be 'info')
    if (guideLogLevel) {
        if (guideLogLevel.value === 'info') {
            guideLogLevel.classList.remove('border-red-500', 'border-red-600');
            guideLogLevel.classList.add('border-green-500', 'border-green-600');
            greenCount++;
        } else {
            guideLogLevel.classList.remove('border-green-500', 'border-green-600');
            guideLogLevel.classList.add('border-red-500', 'border-red-600');
            redCount++;
        }
    }
    
    // Validate Log Format (should be 'json')
    if (guideLogFormat) {
        if (guideLogFormat.value === 'json') {
            guideLogFormat.classList.remove('border-red-500', 'border-red-600');
            guideLogFormat.classList.add('border-green-500', 'border-green-600');
            greenCount++;
        } else {
            guideLogFormat.classList.remove('border-green-500', 'border-green-600');
            guideLogFormat.classList.add('border-red-500', 'border-red-600');
            redCount++;
        }
    }
    
    // Validate Logs Path (should match policy config)
    if (guideLogsPath && policyLogsPath) {
        const policyValue = policyLogsPath.value;
        if (guideLogsPath.value && guideLogsPath.value === policyValue) {
            guideLogsPath.classList.remove('border-red-500', 'border-red-600');
            guideLogsPath.classList.add('border-green-500', 'border-green-600');
            greenCount++;
        } else {
            guideLogsPath.classList.remove('border-green-500', 'border-green-600');
            guideLogsPath.classList.add('border-red-500', 'border-red-600');
            redCount++;
        }
    }
    
    // Update status tracker
    const statusTracker = document.getElementById('guideStatusTracker');
    const statusIcon = document.getElementById('guideStatusIcon');
    const statusText = document.getElementById('guideStatusText');
    
    if (statusTracker && statusIcon && statusText) {
        if (redCount === 0 && greenCount === 3) {
            // All green - success state
            statusTracker.classList.remove('bg-orange-900/20', 'border', 'border-orange-500/40');
            statusTracker.classList.add('bg-green-900/20', 'border', 'border-green-500/40');
            
            statusIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />';
            statusIcon.classList.remove('text-orange-400');
            statusIcon.classList.add('text-green-400');
            
            statusText.classList.remove('text-orange-300');
            statusText.classList.add('text-green-300');
            statusText.textContent = "You're good to go! Click Close to proceed.";
        } else {
            // Has red fields - warning state
            statusTracker.classList.remove('bg-green-900/20', 'border', 'border-green-500/40');
            statusTracker.classList.add('bg-orange-900/20', 'border', 'border-orange-500/40');
            
            statusIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />';
            statusIcon.classList.remove('text-green-400');
            statusIcon.classList.add('text-orange-400');
            
            statusText.classList.remove('text-green-300');
            statusText.classList.add('text-orange-300');
            statusText.textContent = `${redCount} ${redCount === 1 ? 'field needs' : 'fields need'} attention`;
        }
    }
}

// Click-to-set functions for Default guide
function setGuideLogLevel(value) {
    const guideLogLevel = document.getElementById('guideLogLevel');
    const mainLogLevel = document.querySelector('[name="log.level"]');
    
    if (guideLogLevel) {
        guideLogLevel.value = value;
    }
    if (mainLogLevel) {
        mainLogLevel.value = value;
    }
    
    // Trigger change detection and validation
    detectChanges();
    checkConfigNotifications();
    validateDefaultGuide();
}

function setGuideLogFormat(value) {
    const guideLogFormat = document.getElementById('guideLogFormat');
    const mainLogFormat = document.querySelector('[name="log.format"]');
    
    if (guideLogFormat) {
        guideLogFormat.value = value;
    }
    if (mainLogFormat) {
        mainLogFormat.value = value;
    }
    
    // Trigger change detection and validation
    detectChanges();
    checkConfigNotifications();
    validateDefaultGuide();
}

function setGuideLogsPathFromPolicy() {
    const policyLogsPath = document.getElementById('logsPath');
    const guideLogsPath = document.getElementById('guideLogsPath');
    const mainLogsPath = document.querySelector('[name="path.logs"]');
    
    if (policyLogsPath && policyLogsPath.value) {
        const policyValue = policyLogsPath.value;
        
        if (guideLogsPath) {
            guideLogsPath.value = policyValue;
        }
        if (mainLogsPath) {
            mainLogsPath.value = policyValue;
        }
        
        // Trigger change detection and validation
        detectChanges();
        checkConfigNotifications();
        validateDefaultGuide();
    }
}

// ===========================
// Centralized Pipeline Management Guide Functions
// ===========================

function syncCpmGuideToMain(fieldName, value) {
    const mainField = document.querySelector(`[name="${fieldName}"]`);
    if (mainField) {
        mainField.value = value;
        // Trigger change detection
        detectChanges();
        checkConfigNotifications();
    }
}

function syncMainToCpmGuide() {
    // Management Enabled
    const enabled = document.querySelector('[name="xpack.management.enabled"]');
    const guideEnabled = document.getElementById('guideCpmEnabled');
    if (enabled && guideEnabled) {
        guideEnabled.value = enabled.value;
    }
    
    // Pipeline ID
    const pipelineId = document.querySelector('[name="xpack.management.pipeline.id"]');
    const guidePipelineId = document.getElementById('guideCpmPipelineId');
    if (pipelineId && guidePipelineId) {
        guidePipelineId.value = pipelineId.value;
    }
    
    // Cloud ID
    const cloudId = document.querySelector('[name="xpack.management.elasticsearch.cloud_id"]');
    const guideCloudId = document.getElementById('guideCpmCloudId');
    if (cloudId && guideCloudId) {
        guideCloudId.value = cloudId.value;
    }
    
    // Hosts
    const hosts = document.querySelector('[name="xpack.management.elasticsearch.hosts"]');
    const guideHosts = document.getElementById('guideCpmHosts');
    if (hosts && guideHosts) {
        guideHosts.value = hosts.value;
    }
    
    // API Key
    const apiKey = document.querySelector('[name="xpack.management.elasticsearch.api_key"]');
    const guideApiKey = document.getElementById('guideCpmApiKey');
    if (apiKey && guideApiKey) {
        guideApiKey.value = apiKey.value;
    }
    
    // Username
    const username = document.querySelector('[name="xpack.management.elasticsearch.username"]');
    const guideUsername = document.getElementById('guideCpmUsername');
    if (username && guideUsername) {
        guideUsername.value = username.value;
    }
    
    // Password
    const password = document.querySelector('[name="xpack.management.elasticsearch.password"]');
    const guidePassword = document.getElementById('guideCpmPassword');
    if (password && guidePassword) {
        guidePassword.value = password.value;
    }
}

function toggleConnectionMethod(method) {
    const cloudIdSection = document.getElementById('cloudIdSection');
    const hostsUrlSection = document.getElementById('hostsUrlSection');
    const btnCloudId = document.getElementById('btnCloudId');
    const btnHostsUrl = document.getElementById('btnHostsUrl');
    
    if (method === 'cloud') {
        // Show Cloud ID, hide Hosts
        cloudIdSection?.classList.remove('hidden');
        hostsUrlSection?.classList.add('hidden');
        
        // Update button styles
        btnCloudId?.classList.remove('bg-gray-700', 'text-gray-300');
        btnCloudId?.classList.add('bg-blue-600', 'text-white');
        btnHostsUrl?.classList.remove('bg-blue-600', 'text-white');
        btnHostsUrl?.classList.add('bg-gray-700', 'text-gray-300');
        
        // Clear hosts field in main form and guide
        const hostsField = document.querySelector('[name="xpack.management.elasticsearch.hosts"]');
        const guideHostsField = document.getElementById('guideCpmHosts');
        if (hostsField) {
            hostsField.value = '';
        }
        if (guideHostsField) {
            guideHostsField.value = '';
            guideHostsField.classList.remove('border-red-500', 'border-red-600', 'border-green-500', 'border-green-600');
        }
    } else {
        // Show Hosts, hide Cloud ID
        hostsUrlSection?.classList.remove('hidden');
        cloudIdSection?.classList.add('hidden');
        
        // Update button styles
        btnHostsUrl?.classList.remove('bg-gray-700', 'text-gray-300');
        btnHostsUrl?.classList.add('bg-blue-600', 'text-white');
        btnCloudId?.classList.remove('bg-blue-600', 'text-white');
        btnCloudId?.classList.add('bg-gray-700', 'text-gray-300');
        
        // Clear cloud ID field in main form and guide
        const cloudIdField = document.querySelector('[name="xpack.management.elasticsearch.cloud_id"]');
        const guideCloudIdField = document.getElementById('guideCpmCloudId');
        if (cloudIdField) {
            cloudIdField.value = '';
        }
        if (guideCloudIdField) {
            guideCloudIdField.value = '';
            guideCloudIdField.classList.remove('border-red-500', 'border-red-600', 'border-green-500', 'border-green-600');
        }
    }
    
    // Trigger validation
    validateCpmGuide();
}

function toggleAuthMethod(method) {
    const apiKeySection = document.getElementById('apiKeySection');
    const userPassSection = document.getElementById('userPassSection');
    const btnApiKey = document.getElementById('btnApiKey');
    const btnUserPass = document.getElementById('btnUserPass');
    
    if (method === 'apikey') {
        // Show API Key, hide Username/Password
        apiKeySection?.classList.remove('hidden');
        userPassSection?.classList.add('hidden');
        
        // Update button styles
        btnApiKey?.classList.remove('bg-gray-700', 'text-gray-300');
        btnApiKey?.classList.add('bg-blue-600', 'text-white');
        btnUserPass?.classList.remove('bg-blue-600', 'text-white');
        btnUserPass?.classList.add('bg-gray-700', 'text-gray-300');
        
        // Clear username/password fields in main form and guide
        const usernameField = document.querySelector('[name="xpack.management.elasticsearch.username"]');
        const passwordField = document.querySelector('[name="xpack.management.elasticsearch.password"]');
        const guideUsernameField = document.getElementById('guideCpmUsername');
        const guidePasswordField = document.getElementById('guideCpmPassword');
        
        if (usernameField) usernameField.value = '';
        if (passwordField) passwordField.value = '';
        if (guideUsernameField) {
            guideUsernameField.value = '';
            guideUsernameField.classList.remove('border-red-500', 'border-red-600', 'border-green-500', 'border-green-600');
        }
        if (guidePasswordField) {
            guidePasswordField.value = '';
            guidePasswordField.classList.remove('border-red-500', 'border-red-600', 'border-green-500', 'border-green-600');
        }
    } else {
        // Show Username/Password, hide API Key
        userPassSection?.classList.remove('hidden');
        apiKeySection?.classList.add('hidden');
        
        // Update button styles
        btnUserPass?.classList.remove('bg-gray-700', 'text-gray-300');
        btnUserPass?.classList.add('bg-blue-600', 'text-white');
        btnApiKey?.classList.remove('bg-blue-600', 'text-white');
        btnApiKey?.classList.add('bg-gray-700', 'text-gray-300');
        
        // Clear API key field in main form and guide
        const apiKeyField = document.querySelector('[name="xpack.management.elasticsearch.api_key"]');
        const guideApiKeyField = document.getElementById('guideCpmApiKey');
        
        if (apiKeyField) apiKeyField.value = '';
        if (guideApiKeyField) {
            guideApiKeyField.value = '';
            guideApiKeyField.classList.remove('border-red-500', 'border-red-600', 'border-green-500', 'border-green-600');
        }
    }
    
    // Trigger validation
    validateCpmGuide();
}

// Validate CPM guide fields and apply red/green highlighting
function validateCpmGuide() {
    console.log('validateCpmGuide called');
    const guideCpmEnabled = document.getElementById('guideCpmEnabled');
    const guideCpmPipelineId = document.getElementById('guideCpmPipelineId');
    const guideCpmCloudId = document.getElementById('guideCpmCloudId');
    const guideCpmHosts = document.getElementById('guideCpmHosts');
    const guideCpmApiKey = document.getElementById('guideCpmApiKey');
    const guideCpmUsername = document.getElementById('guideCpmUsername');
    const guideCpmPassword = document.getElementById('guideCpmPassword');
    
    const cloudIdSection = document.getElementById('cloudIdSection');
    const hostsUrlSection = document.getElementById('hostsUrlSection');
    const apiKeySection = document.getElementById('apiKeySection');
    const userPassSection = document.getElementById('userPassSection');
    
    console.log('Sections visibility:', {
        cloudIdHidden: cloudIdSection?.classList.contains('hidden'),
        hostsUrlHidden: hostsUrlSection?.classList.contains('hidden'),
        apiKeyHidden: apiKeySection?.classList.contains('hidden'),
        userPassHidden: userPassSection?.classList.contains('hidden')
    });
    
    let redCount = 0;
    let greenCount = 0;
    let totalFields = 0;
    
    // Validate Management Enabled (should be 'true')
    if (guideCpmEnabled) {
        totalFields++;
        console.log('Management Enabled value:', guideCpmEnabled.value);
        if (guideCpmEnabled.value === 'true') {
            guideCpmEnabled.classList.remove('border-red-500', 'border-red-600');
            guideCpmEnabled.classList.add('border-green-500', 'border-green-600');
            console.log('Applied GREEN to Management Enabled');
            greenCount++;
        } else {
            guideCpmEnabled.classList.remove('border-green-500', 'border-green-600');
            guideCpmEnabled.classList.add('border-red-500', 'border-red-600');
            console.log('Applied RED to Management Enabled');
            redCount++;
        }
    }
    
    // Validate Pipeline ID (should have a value)
    if (guideCpmPipelineId) {
        totalFields++;
        if (guideCpmPipelineId.value && guideCpmPipelineId.value.trim() !== '') {
            guideCpmPipelineId.classList.remove('border-red-500', 'border-red-600');
            guideCpmPipelineId.classList.add('border-green-500', 'border-green-600');
            greenCount++;
        } else {
            guideCpmPipelineId.classList.remove('border-green-500', 'border-green-600');
            guideCpmPipelineId.classList.add('border-red-500', 'border-red-600');
            redCount++;
        }
    }
    
    // Validate Connection (Cloud ID OR Hosts - only validate the visible one)
    if (!cloudIdSection?.classList.contains('hidden') && guideCpmCloudId) {
        totalFields++;
        if (guideCpmCloudId.value && guideCpmCloudId.value.trim() !== '') {
            guideCpmCloudId.classList.remove('border-red-500', 'border-red-600');
            guideCpmCloudId.classList.add('border-green-500', 'border-green-600');
            greenCount++;
        } else {
            guideCpmCloudId.classList.remove('border-green-500', 'border-green-600');
            guideCpmCloudId.classList.add('border-red-500', 'border-red-600');
            redCount++;
        }
    } else if (!hostsUrlSection?.classList.contains('hidden') && guideCpmHosts) {
        totalFields++;
        if (guideCpmHosts.value && guideCpmHosts.value.trim() !== '') {
            guideCpmHosts.classList.remove('border-red-500', 'border-red-600');
            guideCpmHosts.classList.add('border-green-500', 'border-green-600');
            greenCount++;
        } else {
            guideCpmHosts.classList.remove('border-green-500', 'border-green-600');
            guideCpmHosts.classList.add('border-red-500', 'border-red-600');
            redCount++;
        }
    }
    
    // Validate Authentication (API Key OR Username/Password - only validate the visible one)
    if (!apiKeySection?.classList.contains('hidden') && guideCpmApiKey) {
        totalFields++;
        if (guideCpmApiKey.value && guideCpmApiKey.value.trim() !== '') {
            guideCpmApiKey.classList.remove('border-red-500', 'border-red-600');
            guideCpmApiKey.classList.add('border-green-500', 'border-green-600');
            greenCount++;
        } else {
            guideCpmApiKey.classList.remove('border-green-500', 'border-green-600');
            guideCpmApiKey.classList.add('border-red-500', 'border-red-600');
            redCount++;
        }
    } else if (!userPassSection?.classList.contains('hidden')) {
        // Validate both username and password
        if (guideCpmUsername) {
            totalFields++;
            if (guideCpmUsername.value && guideCpmUsername.value.trim() !== '') {
                guideCpmUsername.classList.remove('border-red-500', 'border-red-600');
                guideCpmUsername.classList.add('border-green-500', 'border-green-600');
                greenCount++;
            } else {
                guideCpmUsername.classList.remove('border-green-500', 'border-green-600');
                guideCpmUsername.classList.add('border-red-500', 'border-red-600');
                redCount++;
            }
        }
        
        if (guideCpmPassword) {
            totalFields++;
            if (guideCpmPassword.value && guideCpmPassword.value.trim() !== '') {
                guideCpmPassword.classList.remove('border-red-500', 'border-red-600');
                guideCpmPassword.classList.add('border-green-500', 'border-green-600');
                greenCount++;
            } else {
                guideCpmPassword.classList.remove('border-green-500', 'border-green-600');
                guideCpmPassword.classList.add('border-red-500', 'border-red-600');
                redCount++;
            }
        }
    }
    
    console.log('Validation complete - Red:', redCount, 'Green:', greenCount, 'Total:', totalFields);
    
    // Update status tracker
    const statusTracker = document.getElementById('guideCpmStatusTracker');
    const statusIcon = document.getElementById('guideCpmStatusIcon');
    const statusText = document.getElementById('guideCpmStatusText');
    
    if (statusTracker && statusIcon && statusText) {
        if (redCount === 0 && greenCount === totalFields && totalFields > 0) {
            // All green - success state
            statusTracker.classList.remove('bg-orange-900/20', 'border', 'border-orange-500/40');
            statusTracker.classList.add('bg-green-900/20', 'border', 'border-green-500/40');
            
            statusIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />';
            statusIcon.classList.remove('text-orange-400');
            statusIcon.classList.add('text-green-400');
            
            statusText.classList.remove('text-orange-300');
            statusText.classList.add('text-green-300');
            statusText.textContent = "You're good to go! Click Close to proceed.";
        } else {
            // Has red fields - warning state
            statusTracker.classList.remove('bg-green-900/20', 'border', 'border-green-500/40');
            statusTracker.classList.add('bg-orange-900/20', 'border', 'border-orange-500/40');
            
            statusIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />';
            statusIcon.classList.remove('text-green-400');
            statusIcon.classList.add('text-orange-400');
            
            statusText.classList.remove('text-green-300');
            statusText.classList.add('text-orange-300');
            statusText.textContent = `${redCount} ${redCount === 1 ? 'field needs' : 'fields need'} attention`;
        }
    }
}

// Click-to-set functions for CPM guide
function setCpmEnabled(value) {
    const guideCpmEnabled = document.getElementById('guideCpmEnabled');
    const mainCpmEnabled = document.querySelector('[name="xpack.management.enabled"]');
    
    if (guideCpmEnabled) {
        guideCpmEnabled.value = value;
    }
    if (mainCpmEnabled) {
        mainCpmEnabled.value = value;
    }
    
    // Trigger change detection and validation
    detectChanges();
    checkConfigNotifications();
    validateCpmGuide();
}

function setCpmPipelineId(value) {
    const guideCpmPipelineId = document.getElementById('guideCpmPipelineId');
    const mainCpmPipelineId = document.querySelector('[name="xpack.management.pipeline.id"]');
    
    if (guideCpmPipelineId) {
        guideCpmPipelineId.value = value;
    }
    if (mainCpmPipelineId) {
        mainCpmPipelineId.value = value;
    }
    
    // Trigger change detection and validation
    detectChanges();
    checkConfigNotifications();
    validateCpmGuide();
}
