//Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
//or more contributor license agreements. Licensed under the Elastic License;
//you may not use this file except in compliance with the Elastic License.

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
    
    console.log('Checking notifications - Global:', logsPathGlobal, 'Setting:', logsPathSetting);
    
    const logsPathMismatchNotification = document.getElementById('logsPathMismatchNotification');
    const logLevelFormatNotification = document.getElementById('logLevelFormatNotification');
    const notificationsContainer = document.getElementById('notificationsContainer');
    
    // Check for logs path mismatch
    if (logsPathGlobal && logsPathSetting && logsPathGlobal !== logsPathSetting) {
        console.log('Mismatch detected - showing notification');
        logsPathMismatchNotification?.classList.remove('hidden');
        notificationsContainer?.classList.remove('hidden');
    } else {
        console.log('No mismatch - hiding notification');
        logsPathMismatchNotification?.classList.add('hidden');
    }
    
    // Check for log level and format - show if either is not set or not optimal for LogstashUI
    // LogstashUI needs log.level to be set (preferably 'info' or 'debug') and log.format to be 'json'
    const needsLogConfig = !logLevel || !logFormat || logFormat !== 'json';
    
    if (needsLogConfig) {
        console.log('Log level/format needs configuration - showing notification');
        logLevelFormatNotification?.classList.remove('hidden');
        notificationsContainer?.classList.remove('hidden');
    } else {
        console.log('Log level/format configured correctly - hiding notification');
        logLevelFormatNotification?.classList.add('hidden');
    }
    
    // Hide container if no notifications are visible
    const hasVisibleNotifications = notificationsContainer?.querySelector('.p-3:not(.hidden)');
    if (!hasVisibleNotifications) {
        notificationsContainer?.classList.add('hidden');
    }
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

// Fix log level and format by setting to optimal values for LogstashUI
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

// Convert form fields to YAML content
function formToYml() {
    console.log('Converting form to YAML...');
    
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
        console.log('Form is empty, preserving original YAML content');
        return window.policyFileContents?.['logstash.yml'] || '';
    }
    
    // Convert to YAML using js-yaml
    const yamlContent = jsyaml.dump(config, {
        indent: 2,
        lineWidth: -1,
        noRefs: true,
        sortKeys: false
    });
    
    console.log('Form converted to YAML successfully');
    return yamlContent;
}

// Parse YAML content and populate form fields
function parseYmlToForm(ymlContent) {
    if (!ymlContent || ymlContent.trim() === '') {
        console.log('No YAML content to parse');
        return;
    }
    
    console.log('Starting YAML parsing...');
    console.log('YAML content length:', ymlContent.length);
    
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
        
        console.log('Parsed YAML config:', config);
        
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
                console.log(`Set field ${fieldName} = ${value}`);
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
        
        console.log('Successfully parsed YAML and populated form fields');
        
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
        
        // Set initial content
        editor.setValue(fileContents[currentFile]);
        
        // Auto-refresh to ensure proper rendering
        setTimeout(() => {
            editor.refresh();
        }, 100);
    }
    
    // Update documentation link based on file
    function updateDocsLink(file) {
        const docsLinkUrl = document.getElementById('docsLinkUrl');
        if (!docsLinkUrl) return;
        
        const docsLinks = {
            'logstash.yml': {
                url: 'https://www.elastic.co/docs/reference/logstash/logstash-settings-file',
                text: 'Logstash Settings File Reference'
            },
            'jvm.options': {
                url: 'https://www.elastic.co/docs/reference/logstash/jvm-settings',
                text: 'JVM Settings Reference'
            },
            'log4j2.properties': {
                url: 'https://www.elastic.co/guide/en/logstash/8.19/logging.html#log4j2',
                text: 'Log4j2 Configuration Reference'
            },
            'enrollment-tokens': {
                url: '#',
                text: 'Enrollment Tokens'
            }
        };
        
        const link = docsLinks[file] || docsLinks['logstash.yml'];
        docsLinkUrl.href = link.url;
        docsLinkUrl.textContent = link.text;
        
        // Hide docs link for enrollment tokens
        const docsLink = document.getElementById('docsLink');
        if (file === 'enrollment-tokens') {
            docsLink.classList.add('hidden');
        } else {
            docsLink.classList.remove('hidden');
        }
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
            
            // Update documentation link
            updateDocsLink(file);
            
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
                
                // Set editor mode for YAML
                if (editor) {
                    editor.setOption('mode', 'text/x-yaml');
                }
            } else {
                modeToggleContainer.classList.add('hidden');
                // Automatically switch to Code mode for jvm.options and log4j2.properties
                switchToCodeMode();
                
                // Update editor mode and content for non-YAML files
                if (editor) {
                    let mode = 'text/plain';
                    if (file.endsWith('.options') || file.endsWith('.properties')) {
                        mode = 'text/x-simplecomment';
                    }
                    editor.setOption('mode', mode);
                    
                    // Load file content - this is already done in switchToCodeMode()
                    // but we do it again to ensure it's correct
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
        
        // Only parse YAML if we're on logstash.yml tab
        // Use fileContents instead of editor.getValue() to avoid parsing wrong file
        if (currentFile === 'logstash.yml' && fileContents['logstash.yml']) {
            parseYmlToForm(fileContents['logstash.yml']);
        }
    }
    
    function switchToCodeMode() {
        currentMode = 'code';
        codeModeBtn.classList.add('active');
        formModeBtn.classList.remove('active');
        codeModeEditor.classList.remove('hidden');
        formModeEditor.classList.add('hidden');
        
        // Convert form to YAML if we're on logstash.yml tab
        if (currentFile === 'logstash.yml') {
            const yamlContent = formToYml();
            fileContents['logstash.yml'] = yamlContent;
            
            // Initialize CodeMirror if not already done
            if (!editor) {
                initCodeMirror();
                // Set the YAML content AFTER initialization
                editor.setValue(yamlContent);
                editor.refresh();
            } else {
                // Load the YAML content we just generated
                editor.setValue(yamlContent);
                editor.refresh();
            }
        } else {
            // For other files, load their content normally
            if (!editor) {
                initCodeMirror();
            } else {
                const contentToLoad = fileContents[currentFile] || '';
                editor.setValue(contentToLoad);
                editor.refresh();
            }
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
                
                // Parse YAML and populate form fields when loading policy
                if (policy.logstash_yml) {
                    parseYmlToForm(policy.logstash_yml);
                }
                
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
        });
        
        // Check notifications on input as well
        input.addEventListener('input', function() {
            checkConfigNotifications();
        });
    });
    
    // Add specific listeners to both logs path fields to ensure real-time detection
    const logsPathGlobalField = document.querySelector('[name="path.logs"]');
    const logsPathSettingField = document.getElementById('logsPath');
    
    if (logsPathGlobalField) {
        logsPathGlobalField.addEventListener('input', checkConfigNotifications);
        logsPathGlobalField.addEventListener('change', checkConfigNotifications);
        console.log('Added event listeners to global logs path field');
    }
    
    if (logsPathSettingField) {
        logsPathSettingField.addEventListener('input', checkConfigNotifications);
        logsPathSettingField.addEventListener('change', checkConfigNotifications);
        console.log('Added event listeners to config logs path field');
    }
    
    // Initial check for notifications
    setTimeout(() => {
        checkConfigNotifications();
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
