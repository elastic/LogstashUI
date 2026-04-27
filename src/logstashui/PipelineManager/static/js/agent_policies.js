//Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
//or more contributor license agreements. Licensed under the Elastic License;
//you may not use this file except in compliance with the Elastic License.

// Track original content for change detection
let originalFileContents = {};
let changedFiles = new Set();

// Notification buckets — merged before updating the bell indicator
let logstashNotifications = [];
let jvmNotifications = [];

function refreshBellNotifications() {
    updateNotificationIndicator([...logstashNotifications, ...jvmNotifications]);
}

// Toggle advanced settings sections
function toggleAdvanced(sectionId) {
    const section = document.getElementById(sectionId);
    const icon = document.getElementById(sectionId + '-icon');
    
    if (section.classList.contains('hidden')) {
        section.classList.remove('hidden');
        icon.classList.add('rotate-90');
    } else {
        section.classList.add('hidden');
        icon.classList.remove('rotate-90');
    }
}

// Check for configuration issues and show notifications
function checkConfigNotifications() {
    const logsPathGlobal = document.querySelector('[name="path.logs"]')?.value || '';
    const logsPathSetting = document.getElementById('logsPath')?.value || '';
    const logLevel = document.querySelector('[name="log.level"]')?.value || '';
    const logFormat = document.querySelector('[name="log.format"]')?.value || '';
    const configReloadAutomatic = document.querySelector('[name="config.reload.automatic"]')?.value || '';
    const configReloadInterval = document.querySelector('[name="config.reload.interval"]')?.value || '';
    const apiEnabled = document.querySelector('[name="api.enabled"]')?.value || '';
    const apiHost = document.querySelector('[name="api.http.host"]')?.value || '';
    const apiPort = document.querySelector('[name="api.http.port"]')?.value || '';
    const unsafeShutdown = document.querySelector('[name="pipeline.unsafe_shutdown"]')?.value || '';
    const allowSuperuser = document.querySelector('[name="allow_superuser"]')?.value || '';
    const configDebug = document.querySelector('[name="config.debug"]')?.value || '';
    const batchDelay = document.querySelector('[name="pipeline.batch.delay"]')?.value || '';
    const cpmEnabled = document.querySelector('[name="xpack.management.enabled"]')?.value || '';
    
    // console.log('Checking notifications - Global:', logsPathGlobal, 'Setting:', logsPathSetting);
    
    // Check for CPM enabled - show warning on Pipelines tab if true
    const cpmPipelineWarning = document.getElementById('cpmPipelineWarning');
    if (cpmPipelineWarning) {
        if (cpmEnabled === 'true') {
            cpmPipelineWarning.classList.remove('hidden');
        } else {
            cpmPipelineWarning.classList.add('hidden');
        }
    }
    
    const unsafeShutdownNotification = document.getElementById('unsafeShutdownNotification');
    const allowSuperuserNotification = document.getElementById('allowSuperuserNotification');
    const configDebugNotification = document.getElementById('configDebugNotification');
    const batchDelayNotification = document.getElementById('batchDelayNotification');
    const notificationsContainer = document.getElementById('notificationsContainer');

    // --- Requirements tile (mirrors Default guide validation exactly) ---
    const hasMismatch        = logsPathSetting && logsPathGlobal !== logsPathSetting;
    const needsLogLevel      = logLevel !== 'info';
    const needsLogFormat     = logFormat !== 'json';
    const needsReloadAuto    = configReloadAutomatic !== 'true';
    const needsReloadInterval= !configReloadInterval.trim();
    const needsApiEnabled    = apiEnabled === 'false';
    const needsApiHost       = !apiHost.trim();
    const needsApiPort       = !apiPort.trim();
    const unmetCount = [hasMismatch, needsLogLevel, needsLogFormat, needsReloadAuto,
                        needsReloadInterval, needsApiEnabled, needsApiHost, needsApiPort]
                       .filter(Boolean).length;

    const requirementsTile = document.getElementById('requirementsTile');
    const requirementsBadge = document.getElementById('requirementsBadge');
    const requirementsIcon = document.getElementById('requirementsIcon');
    const requirementsLabel = document.getElementById('requirementsLabel');

    if (requirementsTile) {
        if (unmetCount > 0) {
            requirementsTile.classList.remove('requirement-tile-ok');
            requirementsTile.classList.add('requirement-tile-fail');
            if (requirementsIcon) {
                requirementsIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />';
            }
        } else {
            requirementsTile.classList.remove('requirement-tile-fail');
            requirementsTile.classList.add('requirement-tile-ok');
            if (requirementsIcon) {
                requirementsIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />';
            }
        }
    }
    if (requirementsBadge) {
        if (unmetCount > 0) {
            requirementsBadge.textContent = unmetCount + ' unmet';
            requirementsBadge.classList.remove('hidden');
        } else {
            requirementsBadge.classList.add('hidden');
        }
    }
    
    // Check for unsafe shutdown - show if set to true
    const hasUnsafeShutdown = unsafeShutdown === 'true';
    
    if (hasUnsafeShutdown) {
        // console.log('Unsafe shutdown enabled - showing notification');
        unsafeShutdownNotification?.classList.remove('hidden');
        notificationsContainer?.classList.remove('hidden');
    } else {
        // console.log('Unsafe shutdown not enabled - hiding notification');
        unsafeShutdownNotification?.classList.add('hidden');
    }
    
    // Check for allow superuser - show if set to true
    const hasAllowSuperuser = allowSuperuser === 'true';
    
    if (hasAllowSuperuser) {
        // console.log('Allow superuser enabled - showing notification');
        allowSuperuserNotification?.classList.remove('hidden');
        notificationsContainer?.classList.remove('hidden');
    } else {
        // console.log('Allow superuser not enabled - hiding notification');
        allowSuperuserNotification?.classList.add('hidden');
    }
    
    // Check for config debug - show if set to true
    const hasConfigDebug = configDebug === 'true';
    
    if (hasConfigDebug) {
        // console.log('Config debug enabled - showing notification');
        configDebugNotification?.classList.remove('hidden');
        notificationsContainer?.classList.remove('hidden');
    } else {
        // console.log('Config debug not enabled - hiding notification');
        configDebugNotification?.classList.add('hidden');
    }
    
    // Check for batch delay - show if value is set (not empty/default)
    const hasBatchDelay = batchDelay && batchDelay.trim() !== '';
    
    if (hasBatchDelay) {
        // console.log('Batch delay modified - showing notification');
        batchDelayNotification?.classList.remove('hidden');
        notificationsContainer?.classList.remove('hidden');
    } else {
        // console.log('Batch delay not modified - hiding notification');
        batchDelayNotification?.classList.add('hidden');
    }
    
    // Hide container if no notifications are visible
    const hasVisibleNotifications = notificationsContainer?.querySelector('.p-3:not(.hidden)');
    if (!hasVisibleNotifications) {
        notificationsContainer?.classList.add('hidden');
    }
    
    // Collect active notifications for indicator
    const activeNotifications = [];
    if (unmetCount > 0) {
        activeNotifications.push({
            type: 'warning',
            title: 'Requirements',
            message: unmetCount + ' unmet requirement' + (unmetCount > 1 ? 's' : '')
        });
    }
    if (!unsafeShutdownNotification?.classList.contains('hidden')) {
        activeNotifications.push({
            type: 'error',
            title: 'Unsafe Shutdown Enabled',
            message: 'This could result in data loss'
        });
    }
    if (!allowSuperuserNotification?.classList.contains('hidden')) {
        activeNotifications.push({
            type: 'warning',
            title: 'Allow Superuser Enabled',
            message: 'Not recommended for security purposes'
        });
    }
    if (!configDebugNotification?.classList.contains('hidden')) {
        activeNotifications.push({
            type: 'warning',
            title: 'Config Debug Enabled',
            message: 'Prints compiled pipeline config to logs'
        });
    }
    if (!batchDelayNotification?.classList.contains('hidden')) {
        activeNotifications.push({
            type: 'warning',
            title: 'Batch Delay Modified',
            message: 'Not typically recommended to change'
        });
    }
    
    // Update notification indicator
    logstashNotifications = activeNotifications;
    refreshBellNotifications();
}

// Check and update path permission notifications
function checkPathPermissionNotifications() {
    const settingsPathField = document.getElementById('settingsPath');
    const logsPathField = document.getElementById('logsPath');
    const binaryPathField = document.getElementById('binaryPath');
    const settingsPathNotification = document.getElementById('settingsPathNotification');
    const settingsPathNotificationText = document.getElementById('settingsPathNotificationText');
    const logsPathNotification = document.getElementById('logsPathNotification');
    const logsPathNotificationText = document.getElementById('logsPathNotificationText');
    const binaryPathNotification = document.getElementById('binaryPathNotification');
    const binaryPathNotificationText = document.getElementById('binaryPathNotificationText');
    
    if (settingsPathField && settingsPathNotification && settingsPathNotificationText) {
        const settingsPath = settingsPathField.value.trim();
        if (settingsPath && settingsPath !== '/etc/logstash' && settingsPath !== '/etc/logstash/') {
            settingsPathNotificationText.textContent = `${settingsPath} will need to allow read and write access to the 'logstash' user`;
            settingsPathNotification.classList.remove('hidden');
        } else {
            settingsPathNotification.classList.add('hidden');
        }
    }
    
    if (logsPathField && logsPathNotification && logsPathNotificationText) {
        const logsPath = logsPathField.value.trim();
        if (logsPath && logsPath !== '/var/log/logstash' && logsPath !== '/var/log/logstash/') {
            logsPathNotificationText.textContent = `${logsPath} will need to allow read access to the 'logstash' user`;
            logsPathNotification.classList.remove('hidden');
        } else {
            logsPathNotification.classList.add('hidden');
        }
    }
    
    if (binaryPathField && binaryPathNotification && binaryPathNotificationText) {
        const binaryPath = binaryPathField.value.trim();
        if (binaryPath && binaryPath !== '/usr/share/logstash/bin' && binaryPath !== '/usr/share/logstash/bin/') {
            binaryPathNotificationText.textContent = `${binaryPath} will need to allow the 'logstash' user to execute its binaries`;
            binaryPathNotification.classList.remove('hidden');
        } else {
            binaryPathNotification.classList.add('hidden');
        }
    }
}

// Update the undeployed changes count in the stats strip
function updateUndeployedChangesInStatsStrip(count) {
    const pendingEl = document.getElementById('statPendingChanges');
    if (pendingEl) {
        if (count === 0) {
            pendingEl.textContent = 'None';
        } else {
            pendingEl.textContent = `${count} section${count !== 1 ? 's' : ''}`;
        }
    }
}

// Update deploy button indicator based on undeployed changes count
function updateDeployButtonIndicator(count) {
    const indicator = document.getElementById('deployBtnIndicator');
    const indicatorText = document.getElementById('deployBtnIndicatorText');
    
    if (!indicator || !indicatorText) return;
    
    if (count > 0) {
        indicatorText.textContent = 'Undeployed changes';
        indicator.classList.remove('hidden');
    } else {
        indicator.classList.add('hidden');
    }
    
    // Also update the stats strip
    updateUndeployedChangesInStatsStrip(count);
}

// Fix logs path mismatch by syncing FROM config TO global setting
function fixLogsPathMismatch() {
    const logsPathGlobal = document.querySelector('[name="path.logs"]');
    const logsPathSetting = document.getElementById('logsPath');
    
    if (logsPathGlobal && logsPathSetting) {
        // Copy FROM config (logsPath) TO global setting (path.logs)
        logsPathGlobal.value = logsPathSetting.value;
        
        // Trigger change event to apply any UI effects
        logsPathGlobal.dispatchEvent(new Event('input', { bubbles: true }));
        logsPathGlobal.dispatchEvent(new Event('change', { bubbles: true }));
        
        // Recheck notifications
        checkConfigNotifications();
        
        // Show success toast
        showToast('Global logs path updated to match config', 'success');
    }
}

// Fix log level and format by setting to optimal values for logstashui
function fixLogLevelFormat() {
    const logLevelField = document.querySelector('[name="log.level"]');
    const logFormatField = document.querySelector('[name="log.format"]');
    
    if (logLevelField) {
        logLevelField.value = 'info';
        logLevelField.dispatchEvent(new Event('input', { bubbles: true }));
        logLevelField.dispatchEvent(new Event('change', { bubbles: true }));
    }
    
    if (logFormatField) {
        logFormatField.value = 'json';
        logFormatField.dispatchEvent(new Event('input', { bubbles: true }));
        logFormatField.dispatchEvent(new Event('change', { bubbles: true }));
    }
    
    // Recheck notifications
    checkConfigNotifications();
    
    // Show success toast
    showToast('Log level set to Info and format set to JSON', 'success');
}

// Fix unsafe shutdown by setting it back to default (false)
function fixUnsafeShutdown() {
    const unsafeShutdownField = document.querySelector('[name="pipeline.unsafe_shutdown"]');
    
    if (unsafeShutdownField) {
        unsafeShutdownField.value = '';
        unsafeShutdownField.dispatchEvent(new Event('input', { bubbles: true }));
        unsafeShutdownField.dispatchEvent(new Event('change', { bubbles: true }));
    }
    
    // Recheck notifications
    checkConfigNotifications();
    
    // Show success toast
    showToast('Unsafe shutdown set to default (false)', 'success');
}

// Fix allow superuser by setting it back to default (false)
function fixAllowSuperuser() {
    const allowSuperuserField = document.querySelector('[name="allow_superuser"]');
    
    if (allowSuperuserField) {
        allowSuperuserField.value = '';
        allowSuperuserField.dispatchEvent(new Event('input', { bubbles: true }));
        allowSuperuserField.dispatchEvent(new Event('change', { bubbles: true }));
    }
    
    // Recheck notifications
    checkConfigNotifications();
    
    // Show success toast
    showToast('Allow superuser set to default (false)', 'success');
}

// Fix config debug by setting it back to default (false)
function fixConfigDebug() {
    const configDebugField = document.querySelector('[name="config.debug"]');
    
    if (configDebugField) {
        configDebugField.value = '';
        configDebugField.dispatchEvent(new Event('input', { bubbles: true }));
        configDebugField.dispatchEvent(new Event('change', { bubbles: true }));
    }
    
    // Recheck notifications
    checkConfigNotifications();
    
    // Show success toast
    showToast('Config debug set to default (false)', 'success');
}

// Fix batch delay by clearing it to use the default
function fixBatchDelay() {
    const batchDelayField = document.querySelector('[name="pipeline.batch.delay"]');
    
    if (batchDelayField) {
        batchDelayField.value = '';
        batchDelayField.dispatchEvent(new Event('input', { bubbles: true }));
        batchDelayField.dispatchEvent(new Event('change', { bubbles: true }));
    }
    
    // Recheck notifications
    checkConfigNotifications();
    
    // Show success toast
    showToast('Batch delay set to default (50ms)', 'success');
}

// Convert form fields to YAML content
function formToYml() {
    // console.log('Converting form to YAML...');
    
    const config = {};
    
    // Helper function to set nested property value
    function setNestedValue(obj, path, value) {
        const keys = path.split('.');
        const lastKey = keys.pop();
        const target = keys.reduce((current, key) => {
            if (!current[key]) current[key] = {};
            return current[key];
        }, obj);
        target[lastKey] = value;
    }
    
    // Helper function to get all form field values
    function getFormFieldValue(fieldName) {
        const field = document.querySelector(`[name="${fieldName}"]`);
        if (!field) return null;
        
        // For select/dropdown fields, check if value is empty or default placeholder
        if (field.tagName === 'SELECT') {
            const value = field.value.trim();
            // Skip if empty or starts with "Default"
            if (!value || value === '' || value.startsWith('Default')) return null;
            
            // Parse boolean values
            if (value === 'true') return true;
            if (value === 'false') return false;
            
            // Return the actual value
            return value;
        }
        
        // For other fields, skip if empty
        if (!field.value || field.value.trim() === '') return null;
        
        // Handle different field types
        if (field.type === 'number') {
            return parseInt(field.value, 10);
        } else if (field.type === 'checkbox') {
            return field.checked;
        } else if (field.type === 'text' || field.type === 'password') {
            const value = field.value.trim();
            // Try to parse as boolean
            if (value === 'true') return true;
            if (value === 'false') return false;
            // Try to parse as number
            if (!isNaN(value) && value !== '') {
                const num = parseFloat(value);
                if (num.toString() === value) return num;
            }
            return value;
        }
        return field.value.trim();
    }
    
    // Helper function to parse comma-separated values into array
    function parseArrayField(value) {
        if (!value) return null;
        return value.split(',').map(v => v.trim()).filter(v => v !== '');
    }
    
    // Collect all form fields and their values
    const fieldMappings = [
        // Node Identity
        'node.name',
        // Data Path
        'path.data',
        // Pipeline Settings
        'pipeline.id',
        'pipeline.workers',
        'pipeline.batch.size',
        'pipeline.batch.delay',
        'pipeline.batch.output_chunking.growth_threshold_factor',
        'pipeline.batch.metrics.sampling_mode',
        'pipeline.unsafe_shutdown',
        'pipeline.ordered',
        'pipeline.ecs_compatibility',
        'pipeline.separate_logs',
        'pipeline.buffer.type',
        // API Settings
        'api.enabled',
        'api.http.host',
        'api.http.port',
        'api.environment',
        'api.ssl.enabled',
        'api.ssl.keystore.path',
        'api.ssl.keystore.password',
        'api.auth.type',
        'api.auth.basic.username',
        'api.auth.basic.password',
        'api.auth.basic.password_policy.mode',
        // Queue Settings
        'queue.type',
        'path.queue',
        'queue.page_capacity',
        'queue.max_events',
        'queue.max_bytes',
        'queue.checkpoint.acks',
        'queue.checkpoint.writes',
        'queue.compression',
        // Dead Letter Queue
        'dead_letter_queue.enable',
        'dead_letter_queue.max_bytes',
        'path.dead_letter_queue',
        'dead_letter_queue.flush_interval',
        'dead_letter_queue.storage_policy',
        'dead_letter_queue.retain.age',
        // Pipeline Configuration
        'path.config',
        'config.string',
        'config.test_and_exit',
        'config.reload.automatic',
        'config.reload.interval',
        'config.debug',
        'config.support_escapes',
        // Logging Settings
        'log.level',
        'log.format',
        'log.format.json.fix_duplicate_message_fields',
        'path.logs',
        // Other Settings
        'allow_superuser',
        // X-Pack Monitoring
        'xpack.monitoring.enabled',
        'xpack.monitoring.collection.interval',
        'xpack.monitoring.elasticsearch.cloud_id',
        'xpack.monitoring.elasticsearch.api_key',
        'xpack.monitoring.elasticsearch.username',
        'xpack.monitoring.elasticsearch.password',
        'xpack.monitoring.elasticsearch.cloud_auth',
        'xpack.monitoring.elasticsearch.ssl.certificate_authority',
        'xpack.monitoring.elasticsearch.ssl.ca_trusted_fingerprint',
        'xpack.monitoring.elasticsearch.ssl.truststore.path',
        'xpack.monitoring.elasticsearch.ssl.truststore.password',
        'xpack.monitoring.elasticsearch.ssl.keystore.path',
        'xpack.monitoring.elasticsearch.ssl.keystore.password',
        'xpack.monitoring.elasticsearch.ssl.certificate',
        'xpack.monitoring.elasticsearch.ssl.key',
        'xpack.monitoring.elasticsearch.ssl.verification_mode',
        'xpack.monitoring.elasticsearch.sniffing',
        'xpack.monitoring.allow_legacy_collection',
        'xpack.monitoring.collection.pipeline.details.enabled',
        // X-Pack Management
        'xpack.management.enabled',
        'xpack.management.logstash.poll_interval',
        'xpack.management.elasticsearch.cloud_id',
        'xpack.management.elasticsearch.api_key',
        'xpack.management.elasticsearch.username',
        'xpack.management.elasticsearch.password',
        'xpack.management.elasticsearch.cloud_auth',
        'xpack.management.elasticsearch.ssl.certificate_authority',
        'xpack.management.elasticsearch.ssl.ca_trusted_fingerprint',
        'xpack.management.elasticsearch.ssl.truststore.path',
        'xpack.management.elasticsearch.ssl.truststore.password',
        'xpack.management.elasticsearch.ssl.keystore.path',
        'xpack.management.elasticsearch.ssl.keystore.password',
        'xpack.management.elasticsearch.ssl.certificate',
        'xpack.management.elasticsearch.ssl.key',
        'xpack.management.elasticsearch.ssl.verification_mode',
        'xpack.management.elasticsearch.sniffing',
        // X-Pack GeoIP
        'xpack.geoip.downloader.enabled',
        'xpack.geoip.downloader.endpoint'
    ];
    
    // Process each field
    fieldMappings.forEach(fieldName => {
        const value = getFormFieldValue(fieldName);
        if (value !== null) {
            setNestedValue(config, fieldName, value);
        }
    });
    
    // Handle array fields separately
    const arrayFields = [
        { name: 'api.ssl.supported_protocols', path: 'api.ssl.supported_protocols' },
        { name: 'path.plugins', path: 'path.plugins' },
        { name: 'xpack.monitoring.elasticsearch.hosts', path: 'xpack.monitoring.elasticsearch.hosts' },
        { name: 'xpack.monitoring.elasticsearch.proxy', path: 'xpack.monitoring.elasticsearch.proxy' },
        { name: 'xpack.monitoring.elasticsearch.ssl.cipher_suites', path: 'xpack.monitoring.elasticsearch.ssl.cipher_suites' },
        { name: 'xpack.management.pipeline.id', path: 'xpack.management.pipeline.id' },
        { name: 'xpack.management.elasticsearch.hosts', path: 'xpack.management.elasticsearch.hosts' },
        { name: 'xpack.management.elasticsearch.proxy', path: 'xpack.management.elasticsearch.proxy' },
        { name: 'xpack.management.elasticsearch.ssl.cipher_suites', path: 'xpack.management.elasticsearch.ssl.cipher_suites' }
    ];
    
    arrayFields.forEach(({ name, path }) => {
        const field = document.querySelector(`[name="${name}"]`);
        if (field && field.value && field.value.trim() !== '') {
            const arrayValue = parseArrayField(field.value);
            if (arrayValue && arrayValue.length > 0) {
                setNestedValue(config, path, arrayValue);
            }
        }
    });
    
    // Check if config is empty (no fields were populated)
    const isEmpty = Object.keys(config).length === 0;
    
    if (isEmpty) {
        // If form is empty, preserve the original YAML content instead of replacing with {}
        // console.log('Form is empty, preserving original YAML content');
        return window.policyFileContents?.['logstash.yml'] || '';
    }
    
    // Convert to YAML using js-yaml
    const yamlContent = jsyaml.dump(config, {
        indent: 2,
        lineWidth: -1,
        noRefs: true,
        sortKeys: false
    });
    
    // console.log('Form converted to YAML successfully');
    return yamlContent;
}

// Parse YAML content and populate form fields
function parseYmlToForm(ymlContent) {
    if (!ymlContent || ymlContent.trim() === '') {
        // console.log('No YAML content to parse');
        return;
    }
    
    // console.log('Starting YAML parsing...');
    // console.log('YAML content length:', ymlContent.length);
    
    // Clear all form fields first to ensure commented-out values are removed
    const allFormFields = document.querySelectorAll('#formModeEditor input, #formModeEditor select, #formModeEditor textarea');
    allFormFields.forEach(field => {
        field.value = '';
        // Reset original value to prevent purple glow on empty fields
        field.dataset.originalValue = '';
        field.classList.remove('field-modified');
    });
    
    try {
        // Parse YAML using js-yaml library
        const config = jsyaml.load(ymlContent);
        
        // console.log('Parsed YAML config:', config);
        
        if (!config || typeof config !== 'object') {
            console.warn('Invalid YAML configuration - not an object');
            return;
        }
        
        // Helper function to safely get nested property value
        // First try direct key access (for flat YAML with dot notation keys)
        // Then try nested path traversal (for hierarchical YAML)
        function getNestedValue(obj, path) {
            // Try direct key access first (e.g., obj['node.name'])
            if (obj.hasOwnProperty(path)) {
                return obj[path];
            }
            // Fall back to nested traversal (e.g., obj.node.name)
            return path.split('.').reduce((current, key) => current?.[key], obj);
        }
        
        // Helper function to set form field value
        function setFormField(fieldName, value) {
            if (value === null || value === undefined) return;
            
            const field = document.querySelector(`[name="${fieldName}"]`);
            if (field) {
                field.value = value;
                // console.log(`Set field ${fieldName} = ${value}`);
                // Trigger change event to apply modified styling
                field.dispatchEvent(new Event('input', { bubbles: true }));
                field.dispatchEvent(new Event('change', { bubbles: true }));
            } else {
                console.warn(`Field not found: ${fieldName}`);
            }
        }
        
        // Node Identity
        setFormField('node.name', getNestedValue(config, 'node.name'));
        
        // Data Path
        setFormField('path.data', getNestedValue(config, 'path.data'));
        
        // Pipeline Settings
        setFormField('pipeline.id', getNestedValue(config, 'pipeline.id'));
        setFormField('pipeline.workers', getNestedValue(config, 'pipeline.workers'));
        setFormField('pipeline.batch.size', getNestedValue(config, 'pipeline.batch.size'));
        setFormField('pipeline.batch.delay', getNestedValue(config, 'pipeline.batch.delay'));
        setFormField('pipeline.batch.output_chunking.growth_threshold_factor', getNestedValue(config, 'pipeline.batch.output_chunking.growth_threshold_factor'));
        setFormField('pipeline.batch.metrics.sampling_mode', getNestedValue(config, 'pipeline.batch.metrics.sampling_mode'));
        setFormField('pipeline.unsafe_shutdown', getNestedValue(config, 'pipeline.unsafe_shutdown'));
        setFormField('pipeline.ordered', getNestedValue(config, 'pipeline.ordered'));
        setFormField('pipeline.ecs_compatibility', getNestedValue(config, 'pipeline.ecs_compatibility'));
        setFormField('pipeline.separate_logs', getNestedValue(config, 'pipeline.separate_logs'));
        setFormField('pipeline.buffer.type', getNestedValue(config, 'pipeline.buffer.type'));
        
        // API Settings
        setFormField('api.enabled', getNestedValue(config, 'api.enabled'));
        setFormField('api.http.host', getNestedValue(config, 'api.http.host'));
        setFormField('api.http.port', getNestedValue(config, 'api.http.port'));
        setFormField('api.environment', getNestedValue(config, 'api.environment'));
        setFormField('api.ssl.enabled', getNestedValue(config, 'api.ssl.enabled'));
        setFormField('api.ssl.keystore.path', getNestedValue(config, 'api.ssl.keystore.path'));
        setFormField('api.ssl.keystore.password', getNestedValue(config, 'api.ssl.keystore.password'));
        
        // Handle api.ssl.supported_protocols array
        const sslProtocols = getNestedValue(config, 'api.ssl.supported_protocols');
        if (Array.isArray(sslProtocols)) {
            setFormField('api.ssl.supported_protocols', sslProtocols.join(', '));
        }
        
        setFormField('api.auth.type', getNestedValue(config, 'api.auth.type'));
        setFormField('api.auth.basic.username', getNestedValue(config, 'api.auth.basic.username'));
        setFormField('api.auth.basic.password', getNestedValue(config, 'api.auth.basic.password'));
        setFormField('api.auth.basic.password_policy.mode', getNestedValue(config, 'api.auth.basic.password_policy.mode'));
        
        // Queue Settings
        setFormField('queue.type', getNestedValue(config, 'queue.type'));
        setFormField('path.queue', getNestedValue(config, 'path.queue'));
        setFormField('queue.page_capacity', getNestedValue(config, 'queue.page_capacity'));
        setFormField('queue.max_events', getNestedValue(config, 'queue.max_events'));
        setFormField('queue.max_bytes', getNestedValue(config, 'queue.max_bytes'));
        setFormField('queue.checkpoint.acks', getNestedValue(config, 'queue.checkpoint.acks'));
        setFormField('queue.checkpoint.writes', getNestedValue(config, 'queue.checkpoint.writes'));
        setFormField('queue.compression', getNestedValue(config, 'queue.compression'));
        
        // Dead Letter Queue
        setFormField('dead_letter_queue.enable', getNestedValue(config, 'dead_letter_queue.enable'));
        setFormField('dead_letter_queue.max_bytes', getNestedValue(config, 'dead_letter_queue.max_bytes'));
        setFormField('path.dead_letter_queue', getNestedValue(config, 'path.dead_letter_queue'));
        setFormField('dead_letter_queue.flush_interval', getNestedValue(config, 'dead_letter_queue.flush_interval'));
        setFormField('dead_letter_queue.storage_policy', getNestedValue(config, 'dead_letter_queue.storage_policy'));
        setFormField('dead_letter_queue.retain.age', getNestedValue(config, 'dead_letter_queue.retain.age'));
        
        // Pipeline Configuration
        setFormField('path.config', getNestedValue(config, 'path.config'));
        setFormField('config.string', getNestedValue(config, 'config.string'));
        setFormField('config.test_and_exit', getNestedValue(config, 'config.test_and_exit'));
        setFormField('config.reload.automatic', getNestedValue(config, 'config.reload.automatic'));
        setFormField('config.reload.interval', getNestedValue(config, 'config.reload.interval'));
        setFormField('config.debug', getNestedValue(config, 'config.debug'));
        setFormField('config.support_escapes', getNestedValue(config, 'config.support_escapes'));
        
        // Logging Settings
        setFormField('log.level', getNestedValue(config, 'log.level'));
        setFormField('log.format', getNestedValue(config, 'log.format'));
        setFormField('log.format.json.fix_duplicate_message_fields', getNestedValue(config, 'log.format.json.fix_duplicate_message_fields'));
        setFormField('path.logs', getNestedValue(config, 'path.logs'));
        
        // Other Settings
        setFormField('allow_superuser', getNestedValue(config, 'allow_superuser'));
        
        // Handle path.plugins array
        const pathPlugins = getNestedValue(config, 'path.plugins');
        if (Array.isArray(pathPlugins)) {
            setFormField('path.plugins', pathPlugins.join(', '));
        }
        
        // X-Pack Monitoring
        setFormField('xpack.monitoring.enabled', getNestedValue(config, 'xpack.monitoring.enabled'));
        setFormField('xpack.monitoring.collection.interval', getNestedValue(config, 'xpack.monitoring.collection.interval'));
        setFormField('xpack.monitoring.elasticsearch.hosts', 
            Array.isArray(config?.xpack?.monitoring?.elasticsearch?.hosts) 
                ? config.xpack.monitoring.elasticsearch.hosts.join(', ') 
                : getNestedValue(config, 'xpack.monitoring.elasticsearch.hosts'));
        setFormField('xpack.monitoring.elasticsearch.cloud_id', getNestedValue(config, 'xpack.monitoring.elasticsearch.cloud_id'));
        setFormField('xpack.monitoring.elasticsearch.api_key', getNestedValue(config, 'xpack.monitoring.elasticsearch.api_key'));
        setFormField('xpack.monitoring.elasticsearch.username', getNestedValue(config, 'xpack.monitoring.elasticsearch.username'));
        setFormField('xpack.monitoring.elasticsearch.password', getNestedValue(config, 'xpack.monitoring.elasticsearch.password'));
        setFormField('xpack.monitoring.elasticsearch.cloud_auth', getNestedValue(config, 'xpack.monitoring.elasticsearch.cloud_auth'));
        
        // Handle proxy array
        const monitoringProxy = getNestedValue(config, 'xpack.monitoring.elasticsearch.proxy');
        if (Array.isArray(monitoringProxy)) {
            setFormField('xpack.monitoring.elasticsearch.proxy', monitoringProxy.join(', '));
        }
        
        setFormField('xpack.monitoring.elasticsearch.ssl.certificate_authority', getNestedValue(config, 'xpack.monitoring.elasticsearch.ssl.certificate_authority'));
        setFormField('xpack.monitoring.elasticsearch.ssl.ca_trusted_fingerprint', getNestedValue(config, 'xpack.monitoring.elasticsearch.ssl.ca_trusted_fingerprint'));
        setFormField('xpack.monitoring.elasticsearch.ssl.truststore.path', getNestedValue(config, 'xpack.monitoring.elasticsearch.ssl.truststore.path'));
        setFormField('xpack.monitoring.elasticsearch.ssl.truststore.password', getNestedValue(config, 'xpack.monitoring.elasticsearch.ssl.truststore.password'));
        setFormField('xpack.monitoring.elasticsearch.ssl.keystore.path', getNestedValue(config, 'xpack.monitoring.elasticsearch.ssl.keystore.path'));
        setFormField('xpack.monitoring.elasticsearch.ssl.keystore.password', getNestedValue(config, 'xpack.monitoring.elasticsearch.ssl.keystore.password'));
        setFormField('xpack.monitoring.elasticsearch.ssl.certificate', getNestedValue(config, 'xpack.monitoring.elasticsearch.ssl.certificate'));
        setFormField('xpack.monitoring.elasticsearch.ssl.key', getNestedValue(config, 'xpack.monitoring.elasticsearch.ssl.key'));
        setFormField('xpack.monitoring.elasticsearch.ssl.verification_mode', getNestedValue(config, 'xpack.monitoring.elasticsearch.ssl.verification_mode'));
        
        // Handle cipher_suites array
        const monitoringCipherSuites = getNestedValue(config, 'xpack.monitoring.elasticsearch.ssl.cipher_suites');
        if (Array.isArray(monitoringCipherSuites)) {
            setFormField('xpack.monitoring.elasticsearch.ssl.cipher_suites', monitoringCipherSuites.join(', '));
        }
        
        setFormField('xpack.monitoring.elasticsearch.sniffing', getNestedValue(config, 'xpack.monitoring.elasticsearch.sniffing'));
        setFormField('xpack.monitoring.allow_legacy_collection', getNestedValue(config, 'xpack.monitoring.allow_legacy_collection'));
        setFormField('xpack.monitoring.collection.pipeline.details.enabled', getNestedValue(config, 'xpack.monitoring.collection.pipeline.details.enabled'));
        
        // X-Pack Management
        setFormField('xpack.management.enabled', getNestedValue(config, 'xpack.management.enabled'));
        setFormField('xpack.management.logstash.poll_interval', getNestedValue(config, 'xpack.management.logstash.poll_interval'));
        
        // Handle pipeline.id array
        const pipelineIds = getNestedValue(config, 'xpack.management.pipeline.id');
        if (Array.isArray(pipelineIds)) {
            setFormField('xpack.management.pipeline.id', pipelineIds.join(', '));
        }
        
        setFormField('xpack.management.elasticsearch.hosts', 
            Array.isArray(config?.xpack?.management?.elasticsearch?.hosts) 
                ? config.xpack.management.elasticsearch.hosts.join(', ') 
                : getNestedValue(config, 'xpack.management.elasticsearch.hosts'));
        setFormField('xpack.management.elasticsearch.cloud_id', getNestedValue(config, 'xpack.management.elasticsearch.cloud_id'));
        setFormField('xpack.management.elasticsearch.api_key', getNestedValue(config, 'xpack.management.elasticsearch.api_key'));
        setFormField('xpack.management.elasticsearch.username', getNestedValue(config, 'xpack.management.elasticsearch.username'));
        setFormField('xpack.management.elasticsearch.password', getNestedValue(config, 'xpack.management.elasticsearch.password'));
        setFormField('xpack.management.elasticsearch.cloud_auth', getNestedValue(config, 'xpack.management.elasticsearch.cloud_auth'));
        
        // Handle proxy array
        const managementProxy = getNestedValue(config, 'xpack.management.elasticsearch.proxy');
        if (Array.isArray(managementProxy)) {
            setFormField('xpack.management.elasticsearch.proxy', managementProxy.join(', '));
        }
        
        setFormField('xpack.management.elasticsearch.ssl.certificate_authority', getNestedValue(config, 'xpack.management.elasticsearch.ssl.certificate_authority'));
        setFormField('xpack.management.elasticsearch.ssl.ca_trusted_fingerprint', getNestedValue(config, 'xpack.management.elasticsearch.ssl.ca_trusted_fingerprint'));
        setFormField('xpack.management.elasticsearch.ssl.truststore.path', getNestedValue(config, 'xpack.management.elasticsearch.ssl.truststore.path'));
        setFormField('xpack.management.elasticsearch.ssl.truststore.password', getNestedValue(config, 'xpack.management.elasticsearch.ssl.truststore.password'));
        setFormField('xpack.management.elasticsearch.ssl.keystore.path', getNestedValue(config, 'xpack.management.elasticsearch.ssl.keystore.path'));
        setFormField('xpack.management.elasticsearch.ssl.keystore.password', getNestedValue(config, 'xpack.management.elasticsearch.ssl.keystore.password'));
        setFormField('xpack.management.elasticsearch.ssl.certificate', getNestedValue(config, 'xpack.management.elasticsearch.ssl.certificate'));
        setFormField('xpack.management.elasticsearch.ssl.key', getNestedValue(config, 'xpack.management.elasticsearch.ssl.key'));
        
        // Handle cipher_suites array
        const managementCipherSuites = getNestedValue(config, 'xpack.management.elasticsearch.ssl.cipher_suites');
        if (Array.isArray(managementCipherSuites)) {
            setFormField('xpack.management.elasticsearch.ssl.cipher_suites', managementCipherSuites.join(', '));
        }
        
        setFormField('xpack.management.elasticsearch.ssl.verification_mode', getNestedValue(config, 'xpack.management.elasticsearch.ssl.verification_mode'));
        setFormField('xpack.management.elasticsearch.sniffing', getNestedValue(config, 'xpack.management.elasticsearch.sniffing'));
        
        // X-Pack GeoIP
        setFormField('xpack.geoip.downloader.enabled', getNestedValue(config, 'xpack.geoip.downloader.enabled'));
        setFormField('xpack.geoip.downloader.endpoint', getNestedValue(config, 'xpack.geoip.downloader.endpoint'));
        
        // console.log('Successfully parsed YAML and populated form fields');
        
    } catch (error) {
        console.error('Error parsing YAML:', error);
        console.error('YAML content that failed to parse:', ymlContent?.substring(0, 200));
        // Don't show toast for parsing errors - they might be expected during initialization
        // showToast('Error parsing YAML configuration: ' + error.message, 'error');
    }
}

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
            viewportMargin: Infinity,
            extraKeys: {
                "Tab": function(cm) {
                    cm.replaceSelection("  ", "end");
                }
            }
        });
        
        // Set CodeMirror to fill container
        editor.setSize('100%', '100%');
        
        // Make editor globally accessible
        window.policyEditor = editor;
        
        // Setup change detection after editor is ready
        setTimeout(() => {
            setupChangeDetection();
        }, 500);
        
        // Set initial content
        editor.setValue(fileContents[currentFile]);
        
        // Auto-refresh to ensure proper rendering
        setTimeout(() => {
            editor.refresh();
        }, 100);
    }
    
    // Update documentation link based on file
    function updateDocsLink(file) {
        const bannerRow = document.getElementById('bannerRow');
        const docsLink = document.getElementById('docsLink');
        const requirementsTile = document.getElementById('requirementsTile');
        const quickSetupRow = document.getElementById('quickSetupRow');
        if (!docsLink || !bannerRow) return;

        const tipTile = document.getElementById('tipTile');
        const tipText = document.getElementById('tipText');

        // Hide all optional tiles first, then selectively show
        requirementsTile?.classList.add('hidden');
        quickSetupRow?.classList.add('hidden');
        tipTile?.classList.add('hidden');

        // No banner row for enrollment tokens
        if (file === 'enrollment-tokens') {
            bannerRow.classList.add('hidden');
            return;
        }

        bannerRow.classList.remove('hidden');

        if (file === 'logstash.yml') {
            // 6col guided setup | 3col requirements | 1col docs
            bannerRow.style.gridTemplateColumns = '6fr 3fr 1fr';
            quickSetupRow?.classList.remove('hidden');
            requirementsTile?.classList.remove('hidden');
        } else if (file === 'pipelines' || file === 'keystore') {
            // 1col tip | 1col docs
            bannerRow.style.gridTemplateColumns = '1fr 1fr';
            if (tipTile && tipText) {
                tipText.textContent = file === 'pipelines'
                    ? 'Your pipelines are saved when you create or edit them.'
                    : 'Your keystore keys are saved when you create or edit them.';
                tipTile.classList.remove('hidden');
            }
        } else {
            // jvm.options, log4j2.properties — docs only
            bannerRow.style.gridTemplateColumns = '1fr';
        }

        const docsLinks = {
            'logstash.yml':       'https://www.elastic.co/docs/reference/logstash/logstash-settings-file',
            'jvm.options':        'https://www.elastic.co/docs/reference/logstash/jvm-settings',
            'log4j2.properties':  'https://www.elastic.co/guide/en/logstash/8.19/logging.html#log4j2',
            'pipelines':          'https://www.elastic.co/docs/reference/logstash/configuration-file-structure',
            'keystore':           'https://www.elastic.co/docs/reference/logstash/keystore',
        };
        docsLink.href = docsLinks[file] || docsLinks['logstash.yml'];
    }
    
    // File tab switching
    document.querySelectorAll('.file-tab').forEach(tab => {
        tab.addEventListener('click', function() {
            const file = this.dataset.file;
            
            // Update active tab
            document.querySelectorAll('.file-tab').forEach(t => {
                t.classList.remove('active');
                const span = t.querySelector('span');
                const svg = t.querySelector('svg');
                if (span) {
                    span.classList.remove('text-white', 'font-semibold');
                    span.classList.add('text-gray-500');
                }
                if (svg) {
                    svg.classList.remove('opacity-60');
                    svg.classList.add('opacity-40');
                }
            });
            this.classList.add('active');
            const span = this.querySelector('span');
            const svg = this.querySelector('svg');
            if (span) {
                span.classList.remove('text-gray-500');
                span.classList.add('text-white', 'font-semibold');
            }
            if (svg) {
                svg.classList.remove('opacity-40');
                svg.classList.add('opacity-60');
            }
            
            // Update documentation link
            updateDocsLink(file);
            
            // Store current file before switching
            const previousFile = currentFile;
            
            // Save current content BEFORE switching
            if (previousFile && previousFile !== 'enrollment-tokens' && previousFile !== 'pipelines' && previousFile !== 'keystore') {
                if (currentMode === 'code' && editor) {
                    // Save code mode content
                    const currentContent = editor.getValue();
                    if (currentContent !== undefined && currentContent !== null) {
                        fileContents[previousFile] = currentContent;
                    }
                } else if (currentMode === 'form' && previousFile === 'jvm.options') {
                    applyJvmHeapToContent();
                    fileContents['jvm.options'] = window.policyFileContents['jvm.options'] || '';
                } else if (currentMode === 'form' && previousFile === 'logstash.yml') {
                    // Save form mode content by converting form to YAML
                    try {
                        const yamlContent = formToYml();
                        if (yamlContent) {
                            fileContents[previousFile] = yamlContent;
                        }
                    } catch (error) {
                        console.error('Error saving form data:', error);
                    }
                }
            }
            
            // Now update to the new file
            currentFile = file;

            // Update global currentFile reference
            window.policyCurrentFile = file;

            // Persist active tab
            localStorage.setItem('agentPolicies_lastTab', file);
            
            // Handle pipelines tab
            if (file === 'pipelines') {
                const modeToggleContainer = document.getElementById('modeToggleContainer');
                modeToggleContainer.classList.add('hidden');
                
                // Hide notifications container
                const notificationsContainer = document.getElementById('notificationsContainer');
                if (notificationsContainer) {
                    notificationsContainer.classList.add('hidden');
                }
                
                // Hide other views
                const formModeEditor = document.getElementById('formModeEditor');
                const codeModeEditor = document.getElementById('codeModeEditor');
                const enrollmentTokensView = document.getElementById('enrollmentTokensView');
                const pipelinesView = document.getElementById('pipelinesView');
                const keystoreView = document.getElementById('keystoreView');
                const nodesView = document.getElementById('nodesView');
                
                if (formModeEditor) formModeEditor.classList.add('hidden');
                if (codeModeEditor) codeModeEditor.classList.add('hidden');
                document.getElementById('jvmFormView')?.classList.add('hidden');
                if (enrollmentTokensView) enrollmentTokensView.classList.add('hidden');
                if (keystoreView) keystoreView.classList.add('hidden');
                if (nodesView) nodesView.classList.add('hidden');
                if (pipelinesView) {
                    pipelinesView.classList.remove('hidden');
                    // Load pipelines for current policy
                    loadPolicyPipelines();
                }
                return;
            }
            
            // Handle keystore tab
            if (file === 'keystore') {
                const modeToggleContainer = document.getElementById('modeToggleContainer');
                modeToggleContainer.classList.add('hidden');
                
                // Hide notifications container
                const notificationsContainer = document.getElementById('notificationsContainer');
                if (notificationsContainer) {
                    notificationsContainer.classList.add('hidden');
                }
                
                // Hide other views
                const formModeEditor = document.getElementById('formModeEditor');
                const codeModeEditor = document.getElementById('codeModeEditor');
                const enrollmentTokensView = document.getElementById('enrollmentTokensView');
                const pipelinesView = document.getElementById('pipelinesView');
                const keystoreView = document.getElementById('keystoreView');
                const nodesView = document.getElementById('nodesView');
                
                if (formModeEditor) formModeEditor.classList.add('hidden');
                if (codeModeEditor) codeModeEditor.classList.add('hidden');
                document.getElementById('jvmFormView')?.classList.add('hidden');
                if (enrollmentTokensView) enrollmentTokensView.classList.add('hidden');
                if (pipelinesView) pipelinesView.classList.add('hidden');
                if (nodesView) nodesView.classList.add('hidden');
                if (keystoreView) {
                    keystoreView.classList.remove('hidden');
                    // Load keystore for current policy
                    loadPolicyKeystore();
                }
                return;
            }
            
            // Handle nodes tab
            if (file === 'nodes') {
                const modeToggleContainer = document.getElementById('modeToggleContainer');
                modeToggleContainer.classList.add('hidden');
                
                // Hide notifications container
                const notificationsContainer = document.getElementById('notificationsContainer');
                if (notificationsContainer) {
                    notificationsContainer.classList.add('hidden');
                }
                
                // Hide other views
                const formModeEditor = document.getElementById('formModeEditor');
                const codeModeEditor = document.getElementById('codeModeEditor');
                const enrollmentTokensView = document.getElementById('enrollmentTokensView');
                const pipelinesView = document.getElementById('pipelinesView');
                const keystoreView = document.getElementById('keystoreView');
                const nodesView = document.getElementById('nodesView');
                
                if (formModeEditor) formModeEditor.classList.add('hidden');
                if (codeModeEditor) codeModeEditor.classList.add('hidden');
                document.getElementById('jvmFormView')?.classList.add('hidden');
                if (enrollmentTokensView) enrollmentTokensView.classList.add('hidden');
                if (pipelinesView) pipelinesView.classList.add('hidden');
                if (keystoreView) keystoreView.classList.add('hidden');
                if (nodesView) {
                    nodesView.classList.remove('hidden');
                    // Load nodes for current policy
                    loadPolicyNodes();
                }
                return;
            }
            
            // Handle enrollment tokens tab
            if (file === 'enrollment-tokens') {
                // Hide mode toggle for enrollment tokens
                const modeToggleContainer = document.getElementById('modeToggleContainer');
                modeToggleContainer.classList.add('hidden');
                
                // Hide notifications container
                const notificationsContainer = document.getElementById('notificationsContainer');
                if (notificationsContainer) {
                    notificationsContainer.classList.add('hidden');
                }
                
                // Hide other views
                const formModeEditor = document.getElementById('formModeEditor');
                const codeModeEditor = document.getElementById('codeModeEditor');
                const enrollmentTokensView = document.getElementById('enrollmentTokensView');
                const pipelinesView = document.getElementById('pipelinesView');
                const keystoreView = document.getElementById('keystoreView');
                const nodesView = document.getElementById('nodesView');
                
                if (formModeEditor) formModeEditor.classList.add('hidden');
                if (codeModeEditor) codeModeEditor.classList.add('hidden');
                document.getElementById('jvmFormView')?.classList.add('hidden');
                if (pipelinesView) pipelinesView.classList.add('hidden');
                if (keystoreView) keystoreView.classList.add('hidden');
                if (nodesView) nodesView.classList.add('hidden');
                if (enrollmentTokensView) {
                    enrollmentTokensView.classList.remove('hidden');
                    // Load enrollment tokens for current policy
                    loadEnrollmentTokens();
                }
                return; // Exit early for enrollment tokens tab
            }
            
            // Show/hide mode toggle based on file type
            const modeToggleContainer = document.getElementById('modeToggleContainer');
            const enrollmentTokensView = document.getElementById('enrollmentTokensView');
            const pipelinesView = document.getElementById('pipelinesView');
            const keystoreView = document.getElementById('keystoreView');
            const nodesView = document.getElementById('nodesView');

            if (enrollmentTokensView) enrollmentTokensView.classList.add('hidden');
            if (pipelinesView) pipelinesView.classList.add('hidden');
            if (keystoreView) keystoreView.classList.add('hidden');
            if (nodesView) nodesView.classList.add('hidden');

            if (file === 'logstash.yml') {
                modeToggleContainer.classList.remove('hidden');
                codeModeBtn.textContent = 'YML';
                switchToFormMode();
                if (editor) editor.setOption('mode', 'text/x-yaml');
            } else if (file === 'jvm.options') {
                modeToggleContainer.classList.remove('hidden');
                codeModeBtn.textContent = 'Text';
                switchToJvmFormMode();
            } else {
                modeToggleContainer.classList.add('hidden');

                // Hide notifications container when switching away from logstash.yml
                const notificationsContainer = document.getElementById('notificationsContainer');
                if (notificationsContainer) notificationsContainer.classList.add('hidden');

                switchToCodeMode();

                if (editor) {
                    let mode = 'text/plain';
                    if (file.endsWith('.options') || file.endsWith('.properties')) {
                        mode = 'text/x-simplecomment';
                    }
                    editor.setOption('mode', mode);
                    const contentToLoad = fileContents[file] || '';
                    editor.setValue(contentToLoad);
                    editor.refresh();
                }
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
        document.getElementById('jvmFormView')?.classList.add('hidden');

        const actualCurrentFile = window.policyCurrentFile || currentFile;
        if (actualCurrentFile === 'logstash.yml' && fileContents['logstash.yml']) {
            parseYmlToForm(fileContents['logstash.yml']);
            checkConfigNotifications();
        }
    }

    function switchToJvmFormMode() {
        currentMode = 'form';
        formModeBtn.classList.add('active');
        codeModeBtn.classList.remove('active');
        formModeEditor.classList.add('hidden');
        codeModeEditor.classList.add('hidden');
        const jvmFormView = document.getElementById('jvmFormView');
        jvmFormView?.classList.remove('hidden');
        // Parse current Xms / Xmx values from jvm.options content
        const content = fileContents['jvm.options'] || '';
        const xmsMatch = content.match(/^-Xms(\d+)g/m);
        const xmxMatch = content.match(/^-Xmx(\d+)g/m);
        const xmsInput = document.getElementById('jvmXmsInput');
        const xmxInput = document.getElementById('jvmXmxInput');
        if (xmsInput) xmsInput.value = xmsMatch ? xmsMatch[1] : '';
        if (xmxInput) xmxInput.value = xmxMatch ? xmxMatch[1] : '';
        updateJvmHeapMismatchWarning();
    }

    function switchToCodeMode() {
        currentMode = 'code';
        codeModeBtn.classList.add('active');
        formModeBtn.classList.remove('active');
        codeModeEditor.classList.remove('hidden');
        formModeEditor.classList.add('hidden');
        document.getElementById('jvmFormView')?.classList.add('hidden');

        // Hide notifications container when switching to Code mode
        const notificationsContainer = document.getElementById('notificationsContainer');
        if (notificationsContainer) notificationsContainer.classList.add('hidden');

        // If switching away from jvm form, write heap back to content first
        const actualCurrentFile = window.policyCurrentFile || currentFile;
        if (actualCurrentFile === 'jvm.options') {
            applyJvmHeapToContent();
        }

        // Convert form to YAML if we're on logstash.yml tab
        if (currentFile === 'logstash.yml') {
            const yamlContent = formToYml();
            fileContents['logstash.yml'] = yamlContent;
            if (!editor) {
                initCodeMirror();
                editor.setValue(yamlContent);
                editor.refresh();
            } else {
                editor.setValue(yamlContent);
                editor.refresh();
            }
        } else {
            if (!editor) {
                initCodeMirror();
            } else {
                const contentToLoad = fileContents[currentFile] || '';
                editor.setValue(contentToLoad);
                editor.refresh();
            }
        }
    }
    
    formModeBtn.addEventListener('click', () => {
        const activeFile = window.policyCurrentFile || currentFile;
        if (activeFile === 'jvm.options') {
            // Sync editor content back before switching to form (only when already on jvm.options tab)
            if (currentMode === 'code' && window.policyEditor) {
                const editorContent = window.policyEditor.getValue();
                fileContents['jvm.options'] = editorContent;
                window.policyFileContents['jvm.options'] = editorContent;
            }
            switchToJvmFormMode();
        } else {
            switchToFormMode();
        }
    });
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
    
    // JVM heap inputs — update content live as user types
    const jvmInputHandler = () => {
        validateJvmHeapSettings();
        applyJvmHeapToContent();
        updateJvmHeapMismatchWarning();
        detectChanges();
    };
    document.getElementById('jvmXmsInput')?.addEventListener('input', jvmInputHandler);
    document.getElementById('jvmXmxInput')?.addEventListener('input', jvmInputHandler);

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

        // Persist selected policy to localStorage (skip the add_new pseudo-option)
        if (selectedValue !== 'add_new') {
            const selectedOpt = this.options[this.selectedIndex];
            const policyId = selectedOpt?.dataset.policyId;
            if (policyId) {
                localStorage.setItem('agentPolicies_lastPolicyId', policyId);
            }
        }

        if (selectedValue === 'add_new') {
            // Reset to default values for new policy
            document.getElementById('settingsPath').value = '/etc/logstash/';
            document.getElementById('logsPath').value = '/var/log/logstash';
            document.getElementById('binaryPath').value = '/usr/share/logstash/bin';
            
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
                            settings_path: '/etc/logstash/',
                            logs_path: '/var/log/logstash',
                            binary_path: '/usr/share/logstash/bin'
                        })
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        showToast(data.message, 'success');
                        
                        // Reload policies to refresh the UI and show main content
                        // Pass the newly created policy name so it gets selected
                        await loadPolicies(trimmedName);
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

            // Update UI - all policies are now editable
            updatePolicyUI(false);

            // Fetch fresh policy data from database
            loadPolicyData(selectedValue);
        }
    });
    
    // Function to update UI based on policy type
    function updatePolicyUI(isDefaultPolicy) {
        const deletePolicyBtn = document.getElementById('deletePolicyBtn');
        const settingsPathInput = document.getElementById('settingsPath');
        const logsPathInput = document.getElementById('logsPath');
        const binaryPathInput = document.getElementById('binaryPath');
        
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
        
        if (binaryPathInput) {
            binaryPathInput.disabled = false;
            binaryPathInput.classList.remove('opacity-50', 'cursor-not-allowed');
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
    
    // Load policies on page load, auto-selecting a policy if policy_id is in the URL
    const _urlParams = new URLSearchParams(window.location.search);
    const _urlPolicyId = _urlParams.get('policy_id');
    if (_urlPolicyId) {
        // URL param takes priority — also update localStorage so next visit restores this policy
        localStorage.setItem('agentPolicies_lastPolicyId', _urlPolicyId);
    }
    const _savedPolicyId = !_urlPolicyId ? localStorage.getItem('agentPolicies_lastPolicyId') : null;

    // Capture saved tab NOW before loadPolicies triggers logstashTab.click() which would overwrite it
    window._pendingTabRestore = localStorage.getItem('agentPolicies_lastTab');

    loadPolicies(null, _urlPolicyId ? parseInt(_urlPolicyId) : (_savedPolicyId ? parseInt(_savedPolicyId) : null));
    
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
                document.getElementById('binaryPath').value = policy.binary_path || '/usr/share/logstash/bin';
                
                // Update file contents with fresh data from database
                window.policyFileContents['logstash.yml'] = policy.logstash_yml;
                window.policyFileContents['jvm.options'] = policy.jvm_options;
                window.policyFileContents['log4j2.properties'] = policy.log4j2_properties;
                
                // Parse YAML and populate form fields ONLY for logstash.yml and ONLY if we're currently viewing it
                if (policy.logstash_yml && window.policyCurrentFile === 'logstash.yml') {
                    const currentMode = document.getElementById('formModeBtn')?.classList.contains('active') ? 'form' : 'code';
                    if (currentMode === 'form') {
                        parseYmlToForm(policy.logstash_yml);
                    }
                }
                
                // Update editor if it's initialized and showing current file
                if (window.policyEditor && window.policyCurrentFile) {
                    window.policyEditor.setValue(window.policyFileContents[window.policyCurrentFile] || '');
                    window.policyEditor.refresh();
                }
                
                // Store original content for change detection
                storeOriginalContent();

                // Restore last active tab — use the value captured before page-load
                const _tabToRestore = window._pendingTabRestore || 'logstash.yml';
                window._pendingTabRestore = null; // consume it — only applies to initial load
                const _tabEl = document.querySelector(`.file-tab[data-file="${_tabToRestore}"]`);
                if (_tabEl) {
                    _tabEl.click();
                } else {
                    // Fallback: ensure banner row is initialized for logstash.yml
                    updateDocsLink('logstash.yml');
                }

                // Pulse the Default guide button if this policy has never been deployed
                const quickSetupRowEl = document.getElementById('quickSetupRow');
                if (quickSetupRowEl) {
                    if (policy.current_revision_number === 0) {
                        quickSetupRowEl.classList.add('guide-btn-highlight');
                    } else {
                        quickSetupRowEl.classList.remove('guide-btn-highlight');
                    }
                }

                // Update policy stats cards
                updatePolicyStats(policy);

                // Refresh DB-backed tabs if one of them is currently active
                const activeTab = window.policyCurrentFile;
                if (activeTab === 'pipelines') {
                    loadPolicyPipelines();
                } else if (activeTab === 'keystore') {
                    loadPolicyKeystore();
                } else if (activeTab === 'enrollment-tokens') {
                    loadEnrollmentTokens();
                }

                // Check for configuration notifications after loading policy data
                // Use setTimeout to ensure DOM has updated
                setTimeout(() => {
                    checkConfigNotifications();
                    checkPathPermissionNotifications();
                }, 100);
            }
        }
    } catch (error) {
        console.error('Error loading policy data:', error);
        showToast('Failed to load policy data: ' + error.message, 'error');
    }
}

async function updatePolicyStats(policy) {
    // Revision
    const revEl = document.getElementById('statRevision');
    if (revEl) {
        revEl.textContent = `#${policy.current_revision_number}`;
    }

    // Managed instances
    const instEl = document.getElementById('statInstances');
    if (instEl) {
        instEl.textContent = policy.connection_count ?? '—';
    }

    // Last deployed
    const deployedEl = document.getElementById('statLastDeployed');
    if (deployedEl) {
        if (policy.last_deployed_at) {
            const d = new Date(policy.last_deployed_at);
            deployedEl.textContent = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
                + ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
        } else {
            deployedEl.textContent = 'Never';
        }
    }

    // Undeployed changes — read from sectionsWithChanges after the diff modal loads
    // Set a placeholder now; it'll be updated once loadPolicyDiff populates sectionsWithChanges
    const pendingEl = document.getElementById('statPendingChanges');
    if (pendingEl) {
        pendingEl.textContent = '…';
        // Load the diff silently to populate sectionsWithChanges, then update the stat
        if (policy.id) {
            fetch(`/ConnectionManager/GetPolicyDiff/?policy_id=${policy.id}`, {
                headers: { 'X-CSRFToken': getCsrfToken() }
            }).then(r => r.json()).then(data => {
                if (!data.success) { pendingEl.textContent = '—'; return; }
                // Mirror the same logic as policy_deploy_modal.js renderSideBySideTextDiff / renderPipelinesDiff etc.
                const prev = data.previous;
                const curr = data.current;
                let count = 0;
                if ((prev.logstash_yml || '') !== (curr.logstash_yml || '')) count++;
                if ((prev.jvm_options || '') !== (curr.jvm_options || '')) count++;
                if ((prev.log4j2_properties || '') !== (curr.log4j2_properties || '')) count++;
                // Pipelines: compare JSON representation
                const prevPipes = JSON.stringify((prev.pipelines || []).map(p => p.name).sort());
                const currPipes = JSON.stringify((curr.pipelines || []).map(p => p.name).sort());
                if (prevPipes !== currPipes) count++;
                else {
                    const prevLscl = JSON.stringify((prev.pipelines || []).sort((a,b) => a.name > b.name ? 1 : -1).map(p => p.lscl));
                    const currLscl = JSON.stringify((curr.pipelines || []).sort((a,b) => a.name > b.name ? 1 : -1).map(p => p.lscl));
                    if (prevLscl !== currLscl) count++;
                }
                // Keystore: compare key names
                const prevKeys = JSON.stringify((prev.keystore || []).map(k => k.key_name).sort());
                const currKeys = JSON.stringify((curr.keystore || []).map(k => k.key_name).sort());
                if (prevKeys !== currKeys) count++;
                // Keystore password: compare hash
                if ((prev.keystore_password_hash || '') !== (curr.keystore_password_hash || '')) count++;
                // Global settings
                if (prev.settings_path !== curr.settings_path || prev.logs_path !== curr.logs_path) count++;
                
                // Update deploy button indicator (which also updates the stats strip)
                updateDeployButtonIndicator(count);
            }).catch(() => { 
                pendingEl.textContent = '—'; 
                updateDeployButtonIndicator(0);
            });
        }
    }
}

// Load all policies from the server
// If newPolicyName is provided, select that policy after loading
async function loadPolicies(newPolicyName = null, selectPolicyId = null) {
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
                option.dataset.binaryPath = policy.binary_path;
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
            
            // Auto-select the appropriate policy
            if (data.policies.length > 0) {
                let policyToSelect;

                // If a policy ID was provided (e.g. via URL param), select by ID first
                if (selectPolicyId) {
                    policyToSelect = data.policies.find(p => p.id === selectPolicyId);
                }

                // Then fall back to name match (e.g. after creating a new policy)
                if (!policyToSelect && newPolicyName) {
                    policyToSelect = data.policies.find(p => p.name === newPolicyName);
                }

                // Fall back to first policy if nothing matched
                if (!policyToSelect) {
                    policyToSelect = data.policies[0];
                }
                
                policySelect.value = policyToSelect.name.toLowerCase().replace(/\s+/g, '_');
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
    
    // Get the current editor instance and save current content to fileContents
    const settingsPath = document.getElementById('settingsPath').value;
    const logsPath = document.getElementById('logsPath').value;
    const binaryPath = document.getElementById('binaryPath').value;
    
    // Update fileContents with current editor/form state
    if (window.policyFileContents) {
        const currentFile = window.policyCurrentFile || 'logstash.yml';
        const isFormMode = document.getElementById('formModeBtn')?.classList.contains('active');

        if (currentFile === 'logstash.yml') {
            if (isFormMode) {
                // Convert form data to YAML
                try {
                    const yamlContent = formToYml();
                    window.policyFileContents['logstash.yml'] = yamlContent;
                } catch (error) {
                    console.error('Error converting form to YAML:', error);
                    showToast('Error converting form to YAML: ' + error.message, 'error');
                    return;
                }
            } else if (window.policyEditor) {
                window.policyFileContents['logstash.yml'] = window.policyEditor.getValue();
            }
        } else if (currentFile === 'jvm.options') {
            if (isFormMode) {
                // Form mode: write Xms/Xmx inputs into content — never touch the editor
                applyJvmHeapToContent();
            } else if (window.policyEditor) {
                // Text mode: editor holds the authoritative content
                window.policyFileContents['jvm.options'] = window.policyEditor.getValue();
            }
        } else if (window.policyEditor) {
            // All other file tabs are always in code/text mode
            window.policyFileContents[currentFile] = window.policyEditor.getValue();
        }
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
                binary_path: binaryPath,
                logstash_yml: window.policyFileContents ? window.policyFileContents['logstash.yml'] : '',
                jvm_options: window.policyFileContents ? window.policyFileContents['jvm.options'] : '',
                log4j2_properties: window.policyFileContents ? window.policyFileContents['log4j2.properties'] : ''
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast(data.message, 'success');
            // Reset change tracking after successful save
            resetChangeTracking();
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

// Clone current policy
async function cloneCurrentPolicy() {
    const policySelect = document.getElementById('policySelect');
    const selectedOption = policySelect.options[policySelect.selectedIndex];
    const policyName = selectedOption.dataset.policyName || selectedOption.textContent;
    const policyId = selectedOption.dataset.policyId;
    
    if (!policyId) {
        showToast('No policy selected', 'error');
        return;
    }
    
    // Prompt for new policy name
    const newPolicyName = await ConfirmationModal.prompt(
        `Enter a name for the cloned policy:`,
        `${policyName} (Copy)`,
        'Clone Policy',
        'New policy name'
    );
    
    if (!newPolicyName) {
        return;
    }
    
    try {
        const response = await fetch('/ConnectionManager/ClonePolicy/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                source_policy_id: policyId,
                new_policy_name: newPolicyName
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast(data.message, 'success');
            
            // Reload policies and switch to the new policy
            await loadPolicies();
            
            // Select the newly cloned policy
            const policySelect = document.getElementById('policySelect');
            const newOption = Array.from(policySelect.options).find(
                opt => opt.dataset.policyId == data.policy_id
            );
            if (newOption) {
                policySelect.value = newOption.value;
                await loadPolicyData();
            }
        } else {
            showToast(data.error || 'Failed to clone policy', 'error');
        }
    } catch (error) {
        console.error('Error cloning policy:', error);
        showToast('Failed to clone policy: ' + error.message, 'error');
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
        
        if (data.success && data.tokens && data.tokens.length > 0) {
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
                        <span class="font-mono text-xs break-all">${token.encoded_token}</span>
                    </td>
                    <td class="px-4 py-3 text-sm text-right">
                        <div class="action-menu relative inline-block">
                            <button class="action-menu-button p-1 hover:bg-gray-700 rounded" onclick="toggleEnrollmentTokenMenu(${token.id})">
                                <svg class="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                                    <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
                                </svg>
                            </button>
                            <div id="token-menu-${token.id}" class="action-menu-items hidden absolute right-0 bottom-full mb-1 z-50 w-32 bg-gray-800 rounded-md shadow-lg py-1" role="menu">
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
            // Show empty state in table
            tableBody.innerHTML = `
                <tr>
                    <td colspan="3" class="px-4 py-8 text-center text-gray-400">
                        <div class="flex flex-col items-center gap-2">
                            <svg class="w-12 h-12 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                            </svg>
                            <p>No enrollment tokens found</p>
                            <p class="text-sm">Tokens will be created automatically when you save this policy</p>
                        </div>
                    </td>
                </tr>
            `;
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

// Track modified form fields with subtle purple glow
document.addEventListener('DOMContentLoaded', function() {
    const formInputs = document.querySelectorAll('#formModeEditor input, #formModeEditor select, #formModeEditor textarea');
    
    formInputs.forEach(input => {
        // Store original value
        input.dataset.originalValue = input.value || '';
        
        // Add event listener for changes
        input.addEventListener('input', function() {
            if (this.value !== this.dataset.originalValue && this.value !== '') {
                this.classList.add('field-modified');
            } else {
                this.classList.remove('field-modified');
            }
            
            // Check notifications and detect changes
            checkConfigNotifications();
            detectChanges();
        });
        
        // Also handle select changes
        input.addEventListener('change', function() {
            if (this.value !== this.dataset.originalValue && this.value !== '') {
                this.classList.add('field-modified');
            } else {
                this.classList.remove('field-modified');
            }
            
            // Check for configuration notifications when fields change
            checkConfigNotifications();
            detectChanges();
        });
    });
    
    // Add specific listeners to both logs path fields to ensure real-time detection
    const logsPathGlobalField = document.querySelector('[name="path.logs"]');
    const logsPathSettingField = document.getElementById('logsPath');
    
    if (logsPathGlobalField) {
        logsPathGlobalField.addEventListener('input', () => {
            checkConfigNotifications();
            detectChanges();
        });
        logsPathGlobalField.addEventListener('change', () => {
            checkConfigNotifications();
            detectChanges();
        });
        // console.log('Added event listeners to global logs path field');
    }
    
    if (logsPathSettingField) {
        logsPathSettingField.addEventListener('input', () => {
            checkConfigNotifications();
            detectChanges();
            checkPathPermissionNotifications();
        });
        logsPathSettingField.addEventListener('change', () => {
            checkConfigNotifications();
            detectChanges();
            checkPathPermissionNotifications();
        });
        // console.log('Added event listeners to config logs path field');
    }
    
    // Also monitor settings path and binary path for changes
    const settingsPathField = document.getElementById('settingsPath');
    if (settingsPathField) {
        settingsPathField.addEventListener('input', () => { 
            detectChanges(); 
            checkPathPermissionNotifications();
        });
        settingsPathField.addEventListener('change', () => { 
            detectChanges(); 
            checkPathPermissionNotifications();
        });
    }

    const binaryPathField = document.getElementById('binaryPath');
    if (binaryPathField) {
        binaryPathField.addEventListener('input', () => { 
            detectChanges(); 
            checkPathPermissionNotifications();
        });
        binaryPathField.addEventListener('change', () => { 
            detectChanges(); 
            checkPathPermissionNotifications();
        });
        // console.log('Added event listeners to binary path field');
    }
    
    // Initial check for notifications
    setTimeout(() => {
        checkConfigNotifications();
        checkPathPermissionNotifications();
    }, 500);
});

// Close menus when clicking outside
document.addEventListener('click', function(event) {
    if (!event.target.closest('.action-menu')) {
        document.querySelectorAll('.action-menu-items').forEach(menu => {
            menu.classList.add('hidden');
        });
    }
});

// Update notification indicator in top bar
function updateNotificationIndicator(notifications) {
    const indicator = document.getElementById('notificationIndicator');
    const badge = document.getElementById('notificationBadge');
    const tooltipContent = document.getElementById('notificationTooltipContent');
    
    if (!indicator || !badge || !tooltipContent) return;
    
    if (notifications.length > 0) {
        indicator.classList.remove('hidden');
        
        const hasError = notifications.some(n => n.type === 'error');
        const severity = hasError ? 'error' : 'warning';
        
        badge.className = `absolute top-0 right-0 block h-2 w-2 rounded-full ring-2 ring-gray-900 notification-badge-${severity} notification-glow-${severity}`;
        
        tooltipContent.innerHTML = notifications.map(n => `
            <div class="flex items-start gap-2 p-2 bg-gray-700/50 rounded">
                <svg class="w-4 h-4 flex-shrink-0 mt-0.5 ${n.type === 'error' ? 'text-red-400' : 'text-yellow-400'}" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
                </svg>
                <div>
                    <div class="font-semibold ${n.type === 'error' ? 'text-red-300' : 'text-yellow-300'}">${n.title}</div>
                    <div class="text-gray-400">${n.message}</div>
                </div>
            </div>
        `).join('');
    } else {
        indicator.classList.add('hidden');
    }
}

// Notification indicator click handler
document.addEventListener('DOMContentLoaded', function() {
    const notificationIndicatorBtn = document.getElementById('notificationIndicatorBtn');
    if (notificationIndicatorBtn) {
        notificationIndicatorBtn.addEventListener('click', function() {
            // Navigate to jvm.options when that's the only active notification source
            if (jvmNotifications.length > 0 && logstashNotifications.length === 0) {
                const jvmTab = document.querySelector('[data-file="jvm.options"]');
                if (jvmTab) {
                    jvmTab.click();
                    setTimeout(() => {
                        const formModeBtn = document.getElementById('formModeBtn');
                        if (formModeBtn && !formModeBtn.classList.contains('active')) {
                            formModeBtn.click();
                        }
                    }, 100);
                }
            } else {
                const logstashTab = document.querySelector('[data-file="logstash.yml"]');
                if (logstashTab) {
                    logstashTab.click();
                    setTimeout(() => {
                        const formModeBtn = document.getElementById('formModeBtn');
                        if (formModeBtn && !formModeBtn.classList.contains('active')) {
                            formModeBtn.click();
                        }
                    }, 100);
                }
            }
        });
    }
});

// Load pipelines for the current policy
async function loadPolicyPipelines() {
    if (!currentPolicy) {
        // console.log('No policy selected');
        return;
    }
    
    const policySelect = document.getElementById('policySelect');
    const selectedOption = policySelect?.options[policySelect.selectedIndex];
    const policyId = selectedOption?.dataset.policyId;
    
    if (!policyId) {
        // console.log('No policy ID found');
        return;
    }
    
    try {
        // Fetch pipelines for this policy from the backend
        const response = await fetch(`/ConnectionManager/GetPolicyPipelines/?policy_id=${policyId}`, {
            method: 'GET',
            headers: {
                'X-CSRFToken': getCsrfToken()
            }
        });
        
        const data = await response.json();
        
        if (data.success && data.pipelines) {
            // Initialize the pipeline list with the fetched data
            // Use 'policy' as the identifier since we're using default IDs in the template
            if (typeof initPipelineList === 'function') {
                initPipelineList('policy', data.pipelines);
            }
            
            // Store the policy_id globally so the create modal can use it
            window.currentPolicyId = policyId;
        } else {
            // Show empty state
            const tableBody = document.getElementById('pipelineTableBody-policy');
            if (tableBody) {
                tableBody.innerHTML = `
                    <tr>
                        <td colspan="4" class="px-4 py-8 text-center text-gray-400">
                            <div class="flex flex-col items-center gap-2">
                                <svg class="w-12 h-12 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                                </svg>
                                <p>No pipelines found for this policy</p>
                            </div>
                        </td>
                    </tr>
                `;
            }
        }
    } catch (error) {
        console.error('Error loading pipelines:', error);
        showToast('Failed to load pipelines: ' + error.message, 'error');
    }
}

// Load keystore entries for the current policy
async function loadPolicyKeystore() {
    const policySelect = document.getElementById('policySelect');
    const selectedOption = policySelect?.options[policySelect.selectedIndex];
    const policyId = selectedOption?.dataset.policyId;
    
    if (!policyId) {
        // console.log('No policy selected');
        return;
    }
    
    try {
        const response = await fetch(`/ConnectionManager/GetKeystoreEntries/?policy_id=${policyId}`, {
            method: 'GET',
            headers: {
                'X-CSRFToken': getCsrfToken()
            }
        });
        
        const data = await response.json();
        const tableBody = document.getElementById('keystoreTableBody');

        if (data.success && tableBody) {
            // Toggle UI based on whether a keystore password is set
            const noPasswordBanner = document.getElementById('keystoreNoPasswordBanner');
            const passwordedControls = document.getElementById('keystorePasswordedControls');
            const tableContainer = document.getElementById('keystoreTableContainer');

            if (data.has_keystore_password) {
                noPasswordBanner?.classList.add('hidden');
                passwordedControls?.classList.remove('hidden');
                tableContainer?.classList.remove('hidden');
            } else {
                noPasswordBanner?.classList.remove('hidden');
                passwordedControls?.classList.add('hidden');
                tableContainer?.classList.add('hidden');
                return;
            }

            if (data.entries && data.entries.length > 0) {
                tableBody.innerHTML = data.entries.map(entry => `
                    <tr class="hover:bg-gray-800/50">
                        <td class="px-4 py-3 text-gray-300">${escapeHtml(entry.key_name)}</td>
                        <td class="px-4 py-3 text-gray-400 font-mono text-sm">••••••••</td>
                        <td class="px-4 py-3 text-gray-400 text-xs">${new Date(entry.last_updated).toLocaleString()}</td>
                        <td class="text-right px-4 py-3">
                            <div class="action-menu relative inline-block">
                                <button class="action-menu-button p-1 hover:bg-gray-700 rounded">
                                    <svg class="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                                        <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
                                    </svg>
                                </button>
                                <div class="action-menu-items hidden fixed z-50 w-32 bg-gray-800 rounded-md shadow-lg py-1" role="menu">
                                    <div class="px-1 py-1">
                                        <button onclick="editKeystoreEntry(${entry.id}, '${escapeHtml(entry.key_name)}')" class="w-full group flex items-center px-4 py-2 text-sm text-blue-400 hover:bg-gray-700 rounded-md" role="menuitem" type="button">
                                            <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                                            </svg>
                                            Edit
                                        </button>
                                        <button onclick="deleteKeystoreEntry(${entry.id}, '${escapeHtml(entry.key_name)}')" class="w-full group flex items-center px-4 py-2 text-sm text-red-400 hover:bg-gray-700 rounded-md" role="menuitem" type="button">
                                            <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                            </svg>
                                            Delete
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </td>
                    </tr>
                `).join('');
                
                // Setup action menu functionality after rendering
                setupKeystoreActionMenus();
            } else {
                tableBody.innerHTML = `
                    <tr>
                        <td colspan="4" class="px-4 py-8 text-center text-gray-400">
                            <div class="flex flex-col items-center gap-2">
                                <svg class="w-12 h-12 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                                </svg>
                                <p>No keystore entries found</p>
                            </div>
                        </td>
                    </tr>
                `;
            }
        }
    } catch (error) {
        console.error('Error loading keystore:', error);
        showToast('Failed to load keystore entries', 'error');
    }
}

async function showSetKeystorePasswordModal() {
    const policySelect = document.getElementById('policySelect');
    const selectedOption = policySelect?.options[policySelect.selectedIndex];
    const policyId = selectedOption?.dataset.policyId;

    if (!policyId) {
        showToast('Please select a policy first', 'error');
        return;
    }

    const password = await ConfirmationModal.prompt(
        'Please input a keystore password.',
        '',
        'Set Keystore Password',
        'Enter password...',
        true
    );

    if (!password) return;

    try {
        const response = await fetch('/ConnectionManager/SetKeystorePassword/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ policy_id: policyId, password: password })
        });

        const data = await response.json();

        if (data.success) {
            showToast(data.message, 'success');
            loadPolicyKeystore();
        } else {
            showToast(data.error || 'Failed to set keystore password', 'error');
        }
    } catch (error) {
        console.error('Error setting keystore password:', error);
        showToast('Failed to set keystore password', 'error');
    }
}

async function showChangeKeystorePasswordModal() {
    const policySelect = document.getElementById('policySelect');
    const selectedOption = policySelect?.options[policySelect.selectedIndex];
    const policyId = selectedOption?.dataset.policyId;

    if (!policyId) {
        showToast('Please select a policy first', 'error');
        return;
    }

    const confirmed = await ConfirmationModal.show(
        'WARNING: If you change the keystore password, the keystore will be destroyed and recreated. All existing keystore entries will be re-applied automatically.',
        'Change Keystore Password',
        'Continue'
    );

    if (!confirmed) return;

    const password = await ConfirmationModal.prompt(
        'Enter new keystore password:',
        '',
        'New Keystore Password',
        'Enter new password...',
        true
    );

    if (!password) return;

    try {
        const response = await fetch('/ConnectionManager/SetKeystorePassword/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ policy_id: policyId, password: password })
        });

        const data = await response.json();

        if (data.success) {
            showToast(data.message, 'success');
            loadPolicyKeystore();
        } else {
            showToast(data.error || 'Failed to change keystore password', 'error');
        }
    } catch (error) {
        console.error('Error changing keystore password:', error);
        showToast('Failed to change keystore password', 'error');
    }
}

// Keystore CRUD operations
async function showCreateKeystoreModal() {
    const policySelect = document.getElementById('policySelect');
    const selectedOption = policySelect?.options[policySelect.selectedIndex];
    const policyId = selectedOption?.dataset.policyId;
    
    if (!policyId) {
        showToast('Please select a policy first', 'error');
        return;
    }
    
    const result = await KeystoreModal.showCreate();
    if (!result) return;
    
    try {
        const response = await fetch('/ConnectionManager/CreateKeystoreEntry/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                policy_id: policyId,
                key_name: result.keyName,
                key_value: result.keyValue
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast(data.message, 'success');
            loadPolicyKeystore(); // Reload the table
        } else {
            showToast(data.error || 'Failed to create keystore entry', 'error');
        }
    } catch (error) {
        console.error('Error creating keystore entry:', error);
        showToast('Failed to create keystore entry', 'error');
    }
}

async function editKeystoreEntry(entryId, keyName) {
    // Close any open action menus
    document.querySelectorAll('.action-menu-items').forEach(menu => {
        menu.classList.add('hidden');
    });
    
    const newValue = await KeystoreModal.showEdit(keyName);
    if (!newValue) return;
    
    try {
        const response = await fetch('/ConnectionManager/UpdateKeystoreEntry/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                entry_id: entryId,
                key_value: newValue
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast(data.message, 'success');
            loadPolicyKeystore(); // Reload the table
        } else {
            showToast(data.error || 'Failed to update keystore entry', 'error');
        }
    } catch (error) {
        console.error('Error updating keystore entry:', error);
        showToast('Failed to update keystore entry', 'error');
    }
}

async function deleteKeystoreEntry(entryId, keyName) {
    // Close any open action menus
    document.querySelectorAll('.action-menu-items').forEach(menu => {
        menu.classList.add('hidden');
    });
    
    const confirmed = await ConfirmationModal.show(
        `Are you sure you want to delete the keystore entry "${keyName}"?\n\nThis action cannot be undone.`,
        'Delete Keystore Entry',
        'Delete',
        null,
        false
    );
    
    if (!confirmed) return;
    
    try {
        const response = await fetch('/ConnectionManager/DeleteKeystoreEntry/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                entry_id: entryId
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast(data.message, 'success');
            loadPolicyKeystore(); // Reload the table
        } else {
            showToast(data.error || 'Failed to delete keystore entry', 'error');
        }
    } catch (error) {
        console.error('Error deleting keystore entry:', error);
        showToast('Failed to delete keystore entry', 'error');
    }
}

function previousKeystorePage() {
    // console.log('Previous keystore page');
}

function nextKeystorePage() {
    // console.log('Next keystore page');
}

// Handle action menu (3-dot icon) functionality for keystore table
document.addEventListener('click', function(e) {
    // Close all open action menus when clicking anywhere
    if (!e.target.closest('.action-menu')) {
        document.querySelectorAll('.action-menu-items').forEach(menu => {
            menu.classList.add('hidden');
        });
    }
});

// Setup action menu toggle functionality
function setupKeystoreActionMenus() {
    document.querySelectorAll('.action-menu-button').forEach(button => {
        // Remove existing listeners to avoid duplicates
        const newButton = button.cloneNode(true);
        button.parentNode.replaceChild(newButton, button);
        
        newButton.addEventListener('click', function(e) {
            e.stopPropagation();
            const menu = this.nextElementSibling;
            const isHidden = menu.classList.contains('hidden');
            
            // Close all other open menus
            document.querySelectorAll('.action-menu-items').forEach(m => {
                if (m !== menu) m.classList.add('hidden');
            });
            
            // Position the menu at the cursor
            if (isHidden) {
                const rect = this.getBoundingClientRect();
                menu.style.left = `${e.clientX}px`;
                menu.style.top = `${e.clientY}px`;
            }
            
            // Toggle current menu
            menu.classList.toggle('hidden', !isHidden);
        });
    });
}

// Close menu when scrolling
window.addEventListener('scroll', function() {
    document.querySelectorAll('.action-menu-items').forEach(menu => {
        menu.classList.add('hidden');
    });
}, true);

// Store original content when policy loads
function storeOriginalContent() {
    originalFileContents = {};
    changedFiles.clear();
    
    // Store original file contents
    originalFileContents['logstash.yml'] = window.policyFileContents['logstash.yml'] || '';
    originalFileContents['jvm.options'] = window.policyFileContents['jvm.options'] || '';
    originalFileContents['log4j2.properties'] = window.policyFileContents['log4j2.properties'] || '';
    
    // Store original settings, logs, and binary paths
    originalFileContents['settingsPath'] = document.getElementById('settingsPath')?.value || '';
    originalFileContents['logsPath'] = document.getElementById('logsPath')?.value || '';
    originalFileContents['binaryPath'] = document.getElementById('binaryPath')?.value || '';
    
    // Reset all visual indicators
    updateChangeIndicators();
}

// Get current content for a file
function getCurrentContent(file) {
    // Check if this file is currently being edited in the code editor
    const isCurrentlyEditing = window.policyCurrentFile === file;
    
    if (file === 'logstash.yml' && isCurrentlyEditing) {
        // For logstash.yml, check current mode
        const currentMode = document.getElementById('formModeBtn')?.classList.contains('active') ? 'form' : 'code';
        
        if (currentMode === 'form') {
            // Convert form to YAML
            try {
                return formToYml() || '';
            } catch (error) {
                console.error('Error converting form to YAML:', error);
                return '';
            }
        } else {
            // Get from code editor
            return window.policyEditor ? window.policyEditor.getValue() : '';
        }
    } else if (isCurrentlyEditing && file === 'jvm.options') {
        // Use DOM to check mode (currentMode is a closure variable, not in scope here)
        const jvmMode = document.getElementById('formModeBtn')?.classList.contains('active') ? 'form' : 'code';
        if (jvmMode === 'code' && window.policyEditor) {
            return window.policyEditor.getValue();
        }
        return window.policyFileContents['jvm.options'] || '';
    } else if (isCurrentlyEditing && window.policyEditor) {
        // For other files currently being edited, get from editor
        return window.policyEditor.getValue();
    } else {
        // For files not currently being edited, get from stored contents
        return window.policyFileContents[file] || '';
    }
}

// Check if a file has changes
function hasFileChanged(file) {
    const original = originalFileContents[file] || '';
    const current = getCurrentContent(file);
    return original !== current;
}

// Detect changes and update indicators
function detectChanges() {
    const files = ['logstash.yml', 'jvm.options', 'log4j2.properties'];
    changedFiles.clear();
    
    files.forEach(file => {
        if (hasFileChanged(file)) {
            changedFiles.add(file);
        }
    });
    
    // Check settings path, logs path, and binary path changes
    const currentSettingsPath = document.getElementById('settingsPath')?.value || '';
    const currentLogsPath = document.getElementById('logsPath')?.value || '';
    const currentBinaryPath = document.getElementById('binaryPath')?.value || '';
    const originalSettingsPath = originalFileContents['settingsPath'] || '';
    const originalLogsPath = originalFileContents['logsPath'] || '';
    const originalBinaryPath = originalFileContents['binaryPath'] || '';

    if (currentSettingsPath !== originalSettingsPath || currentLogsPath !== originalLogsPath || currentBinaryPath !== originalBinaryPath) {
        changedFiles.add('settings');
    }
    
    updateChangeIndicators();
}

// Update all visual indicators
function updateChangeIndicators() {
    const hasChanges = changedFiles.size > 0;
    const saveBtn = document.getElementById('saveBtn');
    const unsavedIndicator = document.getElementById('unsavedChangesIndicator');
    const policyConfigIndicator = document.getElementById('policyConfigChangedIndicator');
    
    // Update Save button glow
    if (hasChanges) {
        saveBtn?.classList.add('save-button-glow');
        unsavedIndicator?.classList.remove('hidden');
    } else {
        saveBtn?.classList.remove('save-button-glow');
        unsavedIndicator?.classList.add('hidden');
    }
    
    // Update policy config indicator
    if (changedFiles.has('settings')) {
        policyConfigIndicator?.classList.remove('hidden');
    } else {
        policyConfigIndicator?.classList.add('hidden');
    }
    
    // Update tab indicators
    updateTabIndicators();
}

// Update tab change indicators
function updateTabIndicators() {
    const tabs = {
        'logstash.yml': document.querySelector('[data-file="logstash.yml"]'),
        'jvm.options': document.querySelector('[data-file="jvm.options"]'),
        'log4j2.properties': document.querySelector('[data-file="log4j2.properties"]')
    };
    
    Object.keys(tabs).forEach(file => {
        const tab = tabs[file];
        if (tab) {
            if (changedFiles.has(file)) {
                tab.classList.add('tab-changed');
            } else {
                tab.classList.remove('tab-changed');
            }
        }
    });
}

// Hook up change detection to form inputs
function setupChangeDetection() {
    // Monitor form inputs for logstash.yml
    const formInputs = document.querySelectorAll('#formModeEditor input, #formModeEditor select, #formModeEditor textarea');
    formInputs.forEach(input => {
        input.addEventListener('input', () => {
            detectChanges();
        });
        input.addEventListener('change', () => {
            detectChanges();
        });
    });
    
    // Monitor settings path and logs path changes
    const settingsPath = document.getElementById('settingsPath');
    const logsPath = document.getElementById('logsPath');
    
    if (settingsPath) {
        // console.log('Added event listeners to settings path field');
        settingsPath.addEventListener('input', () => {
            // console.log('Settings path input event fired');
            detectChanges();
        });
        settingsPath.addEventListener('change', () => {
            // console.log('Settings path change event fired');
            detectChanges();
        });
    } else {
        console.warn('Settings path field not found');
    }
    
    if (logsPath) {
        // console.log('Added event listeners to logs path field');
        logsPath.addEventListener('input', () => {
            // console.log('Logs path input event fired');
            checkConfigNotifications();
            detectChanges();
        });
        logsPath.addEventListener('change', () => {
            // console.log('Logs path change event fired');
            checkConfigNotifications();
            detectChanges();
        });
    } else {
        console.warn('Logs path field not found');
    }
    
    // Monitor code editor changes
    if (window.policyEditor) {
        window.policyEditor.on('change', () => {
            detectChanges();
        });
    }
}

// Reset change tracking after save
function resetChangeTracking() {
    storeOriginalContent();
}

// Write the JVM Xms/Xmx input values back into the jvm.options file content
function applyJvmHeapToContent() {
    const xmsInput = document.getElementById('jvmXmsInput');
    const xmxInput = document.getElementById('jvmXmxInput');
    const xms = parseInt(xmsInput?.value, 10);
    const xmx = parseInt(xmxInput?.value, 10);

    let content = window.policyFileContents['jvm.options'] || '';

    if (xms >= 1) {
        const hasXms = /-Xms\d+[gGmM]/m.test(content);
        if (hasXms) { content = content.replace(/-Xms\d+[gGmM]/gm, `-Xms${xms}g`); }
        else { content = `-Xms${xms}g\n` + content; }
    }

    if (xmx >= 1) {
        const hasXmx = /-Xmx\d+[gGmM]/m.test(content);
        if (hasXmx) { content = content.replace(/-Xmx\d+[gGmM]/gm, `-Xmx${xmx}g`); }
        else { content = `-Xmx${xmx}g\n` + content; }
    }

    window.policyFileContents['jvm.options'] = content;
}

// Show or hide the heap mismatch banner and update the bell
function updateJvmHeapMismatchWarning() {
    const xmsVal = document.getElementById('jvmXmsInput')?.value;
    const xmxVal = document.getElementById('jvmXmxInput')?.value;
    const banner = document.getElementById('jvmMismatchBanner');
    const mismatch = xmsVal && xmxVal && xmsVal !== xmxVal;

    if (banner) {
        if (mismatch) { banner.classList.remove('hidden'); }
        else { banner.classList.add('hidden'); }
    }

    jvmNotifications = mismatch ? [{
        type: 'warning',
        title: 'Heap Size Mismatch',
        message: '-Xms and -Xmx should be equal to avoid performance issues'
    }] : [];
    refreshBellNotifications();
}

// Validate JVM heap settings - ensure Initial Space doesn't exceed Total Space
function validateJvmHeapSettings() {
    const xmsInput = document.getElementById('jvmXmsInput');
    const xmxInput = document.getElementById('jvmXmxInput');
    
    if (!xmsInput || !xmxInput) return;
    
    const xms = parseInt(xmsInput.value, 10);
    const xmx = parseInt(xmxInput.value, 10);
    
    // If both values are set and Initial Space is larger than Total Space
    if (xms && xmx && xms > xmx) {
        // Set Initial Space to match Total Space
        xmsInput.value = xmx;
        
        // Show toast notification
        showToast('Initial space cannot be larger than total space. Setting initial to be the same as total.', 'warning');
        
        // Update the mismatch warning after adjustment
        updateJvmHeapMismatchWarning();
    }
}

// Note: All guide-related functions have been moved to logstashyml_guides.js

// Load nodes for the current policy
function loadPolicyNodes() {
    const policySelect = document.getElementById('policySelect');
    const selectedOption = policySelect.options[policySelect.selectedIndex];
    const policyId = selectedOption.dataset.policyId;
    
    if (!policyId) {
        console.error('No policy ID available');
        return;
    }

    fetch(`/ConnectionManager/GetPolicyNodes/?policy_id=${policyId}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                renderPolicyNodes(data.nodes);
            } else {
                console.error('Error loading nodes:', data.error);
                showToast(data.error || 'Failed to load nodes', 'error');
            }
        })
        .catch(error => {
            console.error('Error loading nodes:', error);
            showToast('Failed to load nodes', 'error');
        });
}

// Render nodes in the table
function renderPolicyNodes(nodes) {
    const tbody = document.getElementById('nodesTableBody');
    if (!tbody) return;

    if (!nodes || nodes.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="4" class="px-4 py-8 text-center text-gray-400">
                    <div class="flex flex-col items-center gap-2">
                        <svg class="w-12 h-12 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
                        </svg>
                        <p>No nodes found</p>
                        <p class="text-sm">Nodes will appear here when agents enroll with this policy</p>
                    </div>
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = nodes.map(node => `
        <tr class="hover:bg-gray-700/50 transition-colors">
            <td class="px-4 py-4 whitespace-nowrap text-sm text-gray-300">
                <div class="flex flex-col items-center">
                    <div class="rounded-lg p-2" style="background: radial-gradient(circle, rgba(168, 85, 247, 0.15) 0%, rgba(168, 85, 247, 0.05) 70%, transparent 100%);">
                        <img src="/static/images/LogstashIcon.png" alt="Agent" width="52" height="52" class="inline-block">
                    </div>
                    <span class="text-xs text-gray-500 mt-1">LogstashAgent</span>
                </div>
            </td>
            <td class="px-4 py-4 text-sm font-medium text-white">
                <div class="flex flex-col">
                    <span>${node.name}</span>
                    ${node.agent_version ? `
                        <div class="flex items-center gap-2 mt-0.5">
                            <span class="text-xs text-gray-500">v${node.agent_version}</span>
                        </div>
                    ` : ''}
                </div>
            </td>
            <td class="px-4 py-4 whitespace-nowrap text-sm text-gray-300">${node.host || '—'}</td>
            <td class="px-4 py-4 whitespace-nowrap text-sm text-gray-300">
                <span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium ${node.status_class}">
                    ${node.status.charAt(0).toUpperCase() + node.status.slice(1)}
                    
                </span>
            </td>
        </tr>
    `).join('');
}

// ---------------------------------------------------------------------------
// Unsaved-changes navigation guard
// ---------------------------------------------------------------------------

// In-app link clicks → custom modal
document.addEventListener('click', function(e) {
    if (changedFiles.size === 0) return;

    const link = e.target.closest('a[href]');
    if (!link) return;

    const href = link.getAttribute('href');
    // Skip anchors, javascript: pseudo-links, and new-tab links
    if (!href || href.startsWith('#') || href.startsWith('javascript:') || link.target === '_blank') return;

    e.preventDefault();

    ConfirmationModal.show(
        'You have unsaved changes that will be lost if you leave this page.',
        'Unsaved Changes',
        'Leave Page',
        null,
        false,
        'Stay'
    ).then(confirmed => {
        if (confirmed) {
            // Bypass guard on the way out
            changedFiles.clear();
            window.location.href = href;
        }
    });
}, true); // capture phase so we intercept before any other handlers

// Browser close / refresh / address-bar navigation → native dialog
window.addEventListener('beforeunload', function(e) {
    if (changedFiles.size > 0) {
        e.preventDefault();
        e.returnValue = '';
    }
});

