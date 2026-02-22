// Helper function to escape HTML (used by populate functions)
function escapeHtml(unsafe) {
    if (unsafe === undefined || unsafe === null) return '';
    return unsafe
        .toString()
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Plugin Configuration Modal Controller
window.PluginConfigModal = (function () {
    let currentComponent = null;
    let pluginData = {};
    let isNewComponent = false; // Track if this is a newly added component

    // Initialize the modal with plugin data
    function init(data) {
        pluginData = data;
    }

    // Show the configuration modal for a component
    function show(component, isNew = false) {
        currentComponent = component;
        isNewComponent = isNew;
        const modal = document.getElementById('configModal');
        const configForm = document.getElementById('configForm');
        const pluginInfo = pluginData[component.type]?.[component.plugin] || {};

        // Set plugin icon (only for input and output plugins)
        const iconImg = modal.querySelector('#pluginIconImg');
        if (component.type === 'input' || component.type === 'output') {
            iconImg.style.display = ''; // Reset display style
            const iconPath = `/static/images/${component.plugin}.png`;
            iconImg.src = iconPath;
            iconImg.onerror = () => {
                // Hide the icon if the plugin-specific one doesn't exist
                iconImg.style.display = 'none';
            };
        } else {
            // Hide icon for filter plugins
            iconImg.style.display = 'none';
        }

        // Set modal title with plugin type badge
        const titleElement = modal.querySelector('h3');
        titleElement.innerHTML = `
      <div class="flex items-center">
        <span>${component.plugin}</span>
        <span class="ml-2 px-1.5 py-0.5 text-xs rounded-full ${getPluginTypeColor(component.type)}">
          ${component.type.charAt(0).toUpperCase() + component.type.slice(1)}
        </span>
        ${pluginInfo.deprecated ?
            '<span class="ml-1 px-1.5 py-0.5 text-xs rounded-full bg-red-600/50 text-red-100">Deprecated</span>' : ''}
      </div>
    `;

        // Clear previous configuration
        configForm.innerHTML = '';

        // Add plugin description if available
        if (pluginInfo.description) {
            const desc = document.createElement('p');
            desc.className = 'text-sm text-gray-300 mb-4 pb-4 border-b border-gray-700';
            desc.textContent = pluginInfo.description;
            configForm.appendChild(desc);
        }

        // Add configuration fields based on plugin options
        if (pluginInfo.options && Object.keys(pluginInfo.options).length > 0) {
            // Convert options to array and separate into important and advanced
            const allOptions = Object.entries(pluginInfo.options)
                .filter(([key]) => !key.startsWith('_'));  // Skip internal fields

            // Separate fields into important (required or important) and advanced
            const importantOptions = [];
            const advancedOptions = [];

            allOptions.forEach(([key, option]) => {
                const isRequired = option.required === 'Yes';
                const isImportant = option.important === 'Yes';
                const isExplicitlyNotImportant = option.important === 'No';
                
                // A field is "advanced" only if it's explicitly marked as not important AND not required
                // If the important field is missing (undefined), treat it as important by default
                if (isRequired || isImportant || !isExplicitlyNotImportant) {
                    importantOptions.push([key, option]);
                } else {
                    advancedOptions.push([key, option]);
                }
            });

            // Keep important fields in their original order (as defined in the JSON)
            // Sort advanced fields alphabetically
            advancedOptions.sort((a, b) => a[0].localeCompare(b[0]));

            // Render important fields first
            importantOptions.forEach(([key, option]) => {
                const fieldId = `config-${key}`;
                const value = component.config[key] !== undefined ? component.config[key] : '';
                const inputType = (option.input_type || 'text').toLowerCase();

                const fieldGroup = document.createElement('div');
                fieldGroup.className = 'mb-4';
                fieldGroup.dataset.required = option.required === 'Yes' ? 'true' : 'false';
                fieldGroup.dataset.fieldName = key;
                fieldGroup.dataset.fieldType = inputType;

                let inputField = '';
                const inputClasses = 'w-full p-2 bg-gray-700 border border-gray-600 rounded text-white';

                // Create appropriate input based on type
                if (inputType === 'codec') {
                    // Special handling for codec field
                    const codecData = pluginData.codec || {};
                    const codecNames = Object.keys(codecData).sort();

                    // Get current codec value
                    let currentCodecName = '';
                    let currentCodecConfig = {};
                    if (value && typeof value === 'object') {
                        // value is like {"cef": {"ecs_compatibility": "v1"}}
                        const entries = Object.entries(value);
                        if (entries.length > 0) {
                            [currentCodecName, currentCodecConfig] = entries[0];
                        }
                    }

                    const codecContainerId = `codec-container-${Date.now()}`;
                    const codecSelectId = `codec-select-${Date.now()}`;
                    const codecConfigId = `codec-config-${Date.now()}`;

                    inputField = `
            <div id="${codecContainerId}" class="space-y-3">
              <select id="${codecSelectId}" 
                      class="${inputClasses}"
                      onchange="handleCodecChange('${codecContainerId}', '${fieldId}', this.value)">
                <option value="">-- Select Codec --</option>
                ${codecNames.map(name => `
                  <option value="${name}" ${name === currentCodecName ? 'selected' : ''}>${name}</option>
                `).join('')}
              </select>
              <div id="${codecConfigId}" class="ml-4 space-y-2 border-l-2 border-gray-600 pl-4">
                <!-- Codec configuration fields will be inserted here -->
              </div>
              <input type="hidden" id="${fieldId}" name="${key}" data-field-type="codec" value='${escapeHtml(JSON.stringify(value || {}))}'>
            </div>
          `;
                } else if (inputType === 'dropdown') {
                    // Handle dropdown input type
                    const dropdownOptions = option.options || [];
                    inputField = `
            <select id="${fieldId}" name="${key}" class="${inputClasses}">
              <option value="">-- Select an option --</option>
              ${dropdownOptions.map(opt => `
                <option value="${escapeHtml(opt)}" ${value === opt ? 'selected' : ''}>${escapeHtml(opt)}</option>
              `).join('')}
            </select>
          `;
                } else if (inputType.includes('boolean') || inputType === 'bool') {
                    inputField = `
            <select id="${fieldId}" name="${key}" class="${inputClasses}">
              <option value="true" ${value === true || value === 'true' ? 'selected' : ''}>true</option>
              <option value="false" ${value === false || value === 'false' ? 'selected' : ''}>false</option>
              <option value="" ${value === '' ? 'selected' : ''}></option>
            </select>
          `;
                } else if (inputType === 'array_of_hashes') {
                    // Handle array of hashes input type (e.g., SNMP hosts)
                    let arrayValue = [];
                    if (Array.isArray(value)) {
                        arrayValue = [...value];
                    } else if (typeof value === 'string' && value.trim() !== '') {
                        try {
                            const parsed = JSON.parse(value);
                            arrayValue = Array.isArray(parsed) ? parsed : [parsed];
                        } catch (e) {
                            arrayValue = [];
                        }
                    }

                    const containerId = `array-hash-container-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
                    const hashOptions = option.options || {};
                    const optionsJson = escapeHtml(JSON.stringify(hashOptions));
                    
                    inputField = `
            <div id="${containerId}" class="space-y-3" data-hash-options='${optionsJson}'>
              <div class="p-3 bg-gray-900/50 border border-gray-600 rounded">
                <div class="text-xs text-gray-400 mb-2">No entries yet. Click "+ Add Entry" to add one.</div>
              </div>
              <button type="button"
                      class="mt-2 px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm"
                      onclick="addArrayOfHashesItem('${containerId}', '${fieldId}')">
                + Add Entry
              </button>
              <input type="hidden" id="${fieldId}" name="${key}" data-field-type="array_of_hashes" value='${escapeHtml(JSON.stringify(arrayValue))}'>
            </div>
          `;
                } else if (inputType === 'key_list_hash') {
                    // Handle key_list_hash input type (e.g., grok match field)
                    let keyListHashValue = {};
                    try {
                        if (typeof value === 'string' && value.trim() !== '') {
                            keyListHashValue = JSON.parse(value);
                        } else if (typeof value === 'object' && value !== null) {
                            keyListHashValue = {...value};
                        }
                    } catch (e) {
                        console.error('Error parsing key_list_hash value:', e);
                    }

                    const containerId = `key-list-hash-container-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
                    const sectionId = `key-list-hash-section-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
                    
                    inputField = `
            <div id="${containerId}" class="space-y-2">
              <div class="p-3 bg-gray-800/30 border border-gray-600/50 rounded space-y-3" data-section-id="${sectionId}">
                <div class="flex items-center gap-2">
                  <input type="text"
                         class="flex-1 p-2 bg-gray-700/50 border border-gray-600/50 rounded text-white text-sm section-key focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50"
                         placeholder="Key (e.g., message, field1)"
                         onchange="updateKeyListHashField('${containerId}', '${fieldId}')">
                  <button type="button"
                          class="px-3 py-2 text-red-400 hover:bg-gray-700 rounded text-sm transition-colors flex items-center gap-1"
                          onclick="removeKeyListHashSection('${containerId}', '${fieldId}', this)">
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                      Remove Section
                  </button>
                </div>
                <div class="ml-4 space-y-2 section-values">
                  <div class="flex items-center gap-2">
                    <span class="text-gray-400 text-sm">=></span>
                    <input type="text"
                           class="flex-1 p-2 bg-gray-700/50 border border-gray-600/50 rounded text-white text-sm focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50"
                           placeholder="Value (e.g., pattern1)"
                           onchange="updateKeyListHashField('${containerId}', '${fieldId}')">
                    <button type="button"
                            class="px-3 py-1 text-red-400 hover:bg-gray-700 rounded text-xs transition-colors flex items-center gap-1"
                            onclick="removeKeyListHashValue('${containerId}', '${fieldId}', this)">
                        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                        Remove
                    </button>
                  </div>
                </div>
                <button type="button"
                        class="ml-4 px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700 text-xs transition-colors"
                        onclick="addKeyListHashValue('${containerId}', '${fieldId}', this)">
                    + Add Value
                </button>
              </div>
              <button type="button"
                      class="px-3 py-1.5 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm transition-colors"
                      onclick="addKeyListHashSection('${containerId}', '${fieldId}')">
                + Add Section
              </button>
              <input type="hidden" id="${fieldId}" name="${key}" data-field-type="key_list_hash" value='${escapeHtml(JSON.stringify(keyListHashValue))}'>
            </div>
          `;
                } else if (inputType.includes('hash') || inputType === 'object') {
                    // Handle hash/object input type
                    let hashValue = {};
                    try {
                        if (typeof value === 'string' && value.trim() !== '') {
                            hashValue = JSON.parse(value);
                        } else if (typeof value === 'object' && value !== null) {
                            hashValue = {...value};
                        }
                    } catch (e) {
                        console.error('Error parsing hash value:', e);
                    }

                    const containerId = `hash-container-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
                    inputField = `
            <div id="${containerId}" class="p-3 bg-gray-800/30 border border-gray-600/50 rounded space-y-2">
              <div class="flex items-center space-x-2">
                <input type="text"
                       class="flex-1 p-2 bg-gray-700 border border-gray-600 rounded text-white"
                       placeholder="Key"
                       onchange="updateHashPair('${containerId}', '${fieldId}', this, 'key')">
                <span class="text-gray-400">=></span>
                <input type="text"
                       class="flex-1 p-2 bg-gray-700 border border-gray-600 rounded text-white"
                       placeholder="Value"
                       onchange="updateHashPair('${containerId}', '${fieldId}', this, 'value')">
                <button type="button"
                        class="px-3 py-2 text-red-400 hover:bg-gray-700 rounded text-sm transition-colors flex items-center gap-1"
                        onclick="removeHashPair('${containerId}', this)">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                  Remove
                </button>
              </div>
              <button type="button"
                      class="mt-2 px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700 text-sm"
                      onclick="addHashPair('${containerId}', '${fieldId}')">
                + Add More
              </button>
              <input type="hidden" id="${fieldId}" name="${key}" data-field-type="hash" value='${escapeHtml(JSON.stringify(hashValue))}'>
            </div>
          `;
                } else if (inputType.includes('array') || inputType === 'list') {
                    // Handle array input type
                    let arrayValue = [];
                    if (Array.isArray(value)) {
                        arrayValue = [...value];
                    } else if (typeof value === 'string' && value.trim() !== '') {
                        // Try to parse as JSON first
                        try {
                            const parsed = JSON.parse(value);
                            arrayValue = Array.isArray(parsed) ? parsed : [parsed];
                        } catch (e) {
                            // If not valid JSON, treat as a single string value
                            arrayValue = [value];
                        }
                    } else if (value !== undefined && value !== null && value !== '') {
                        // For any other non-empty value, wrap it in an array
                        arrayValue = [value];
                    }

                    const containerId = `array-container-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
                    inputField = `
            <div id="${containerId}" class="p-3 bg-gray-800/30 border border-gray-600/50 rounded space-y-2">
              <div class="flex items-center space-x-2">
                <input type="text"
                       class="flex-1 p-2 bg-gray-700 border border-gray-600 rounded text-white"
                       placeholder="Value"
                       onchange="updateArrayItem('${containerId}', '${fieldId}', this, 0)">
                <button type="button"
                        class="px-3 py-2 text-red-400 hover:bg-gray-700 rounded text-sm transition-colors flex items-center gap-1"
                        onclick="removeArrayItem('${containerId}', this)">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                  Remove
                </button>
              </div>
              <button type="button"
                      class="mt-2 px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700 text-sm"
                      onclick="addArrayItem('${containerId}', '${fieldId}')">
                + Add More
              </button>
              <input type="hidden" id="${fieldId}" name="${key}" data-field-type="array" value='${escapeHtml(JSON.stringify(arrayValue))}'>
            </div>
          `;
                } else if (inputType.includes('number') || inputType === 'int' || inputType === 'float') {
                    inputField = `
            <input type="number" id="${fieldId}" name="${key}"
                   value="${escapeHtml(value)}"
                   step="${inputType === 'float' ? '0.1' : '1'}"
                   class="${inputClasses}">
          `;
                } else if (key.toLowerCase() === 'code') {
                    // Special handling for "code" field - use textarea with preserved whitespace
                    inputField = `
            <textarea id="${fieldId}" name="${key}"
                      rows="10"
                      class="${inputClasses} font-mono text-sm whitespace-pre"
                      style="resize: vertical; min-height: 200px;">${escapeHtml(value)}</textarea>
          `;
                } else if (component.plugin === 'comment' && (key === 'string' || key.toLowerCase() === 'message' || key.toLowerCase() === 'text')) {
                    // Special handling for comment plugin - use textarea for multiline comments
                    inputField = `
            <textarea id="${fieldId}" name="${key}"
                      rows="5"
                      class="${inputClasses} font-mono text-sm"
                      style="resize: vertical; min-height: 100px;"
                      placeholder="Enter your comment here...">${escapeHtml(value)}</textarea>
          `;
                } else if (inputType === 'password') {
                    // Handle password input type with show/hide functionality
                    inputField = `
            <div class="relative">
              <input type="password" id="${fieldId}" name="${key}"
                     value="${escapeHtml(value)}"
                     class="${inputClasses} pr-10">
              <button type="button" 
                      class="absolute right-2 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-200"
                      onclick="togglePasswordVisibility('${fieldId}', this)"
                      title="Show/Hide">
                <svg class="w-5 h-5 eye-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
              </button>
            </div>
          `;
                } else if (inputType === 'fs_path') {
                    // Handle filesystem path input type with file picker button
                    inputField = `
            <div class="flex items-center space-x-2">
              <input type="text" id="${fieldId}" name="${key}"
                     value="${escapeHtml(value)}"
                     class="${inputClasses} flex-1"
                     placeholder="Enter file path or click Browse...">
              <button type="button" 
                      class="px-3 py-2 bg-gray-600 text-white rounded hover:bg-gray-500 text-sm whitespace-nowrap"
                      onclick="browseFilePath('${fieldId}')"
                      title="Browse for file">
                <svg class="w-5 h-5 inline-block mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                </svg>
                Browse...
              </button>
            </div>
          `;
                } else {
                    // Default to text input
                    inputField = `
            <input type="text" id="${fieldId}" name="${key}"
                   value="${escapeHtml(value)}"
                   class="${inputClasses}">
          `;
                }

                fieldGroup.innerHTML = `
          <div class="flex items-start justify-between">
            <label for="${fieldId}" class="block text-sm font-medium text-gray-300 mb-1">
              ${key}
              <span class="text-xs font-normal">
                (Required:
                  <span class="${option.required === 'Yes' ? 'text-green-400' : 'text-red-400'}">
                    ${option.required || 'No'}
                  </span>
                  , Type: ${option.input_type || 'string'}
                )
              </span>
            </label>
            ${pluginInfo.link && option.setting_link ? `
              <a href="${pluginInfo.link}${option.setting_link}" target="_blank"
                 class="text-gray-400 hover:text-blue-400 ml-2"
                 title="Documentation for ${key}">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </a>
            ` : ''}
          </div>
          ${option.description ? `<p class="text-xs text-gray-400 mb-1">${option.description}</p>` : ''}
          ${inputField}
          ${option.default_value !== undefined ?
                    `<p class="text-xs text-gray-400 mt-1">Default: <code class="bg-gray-900 px-1 rounded">${escapeHtml(option.default_value)}</code></p>` : ''}
        `;

                configForm.appendChild(fieldGroup);
            });

            // Add Advanced Settings section if there are advanced options
            if (advancedOptions.length > 0) {
                const advancedSection = document.createElement('div');
                advancedSection.className = 'mt-6 border-t border-gray-700 pt-4';
                
                const advancedHeader = document.createElement('div');
                advancedHeader.className = 'flex items-center justify-between cursor-pointer mb-4';
                advancedHeader.onclick = function() {
                    const content = advancedSection.querySelector('.advanced-content');
                    const icon = advancedSection.querySelector('.toggle-icon');
                    content.classList.toggle('hidden');
                    icon.classList.toggle('rotate-180');
                };
                
                advancedHeader.innerHTML = `
                    <h4 class="text-sm font-semibold text-gray-300">Advanced Settings</h4>
                    <svg class="toggle-icon w-5 h-5 text-gray-400 transform transition-transform duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                    </svg>
                `;
                
                advancedSection.appendChild(advancedHeader);
                
                const advancedContent = document.createElement('div');
                advancedContent.className = 'advanced-content hidden space-y-4';
                
                // Render advanced fields
                advancedOptions.forEach(([key, option]) => {
                    const fieldId = `config-${key}`;
                    const value = component.config[key] !== undefined ? component.config[key] : '';
                    const inputType = (option.input_type || 'text').toLowerCase();

                    const fieldGroup = document.createElement('div');
                    fieldGroup.className = 'mb-4';
                    fieldGroup.dataset.required = option.required === 'Yes' ? 'true' : 'false';
                    fieldGroup.dataset.fieldName = key;
                    fieldGroup.dataset.fieldType = inputType;

                    let inputField = '';
                    const inputClasses = 'w-full p-2 bg-gray-700 border border-gray-600 rounded text-white';

                    // Create appropriate input based on type (same logic as above)
                    if (inputType === 'codec') {
                        // Special handling for codec field
                        const codecData = pluginData.codec || {};
                        const codecNames = Object.keys(codecData).sort();

                        // Get current codec value
                        let currentCodecName = '';
                        let currentCodecConfig = {};
                        if (value && typeof value === 'object') {
                            // value is like {"cef": {"ecs_compatibility": "v1"}}
                            const entries = Object.entries(value);
                            if (entries.length > 0) {
                                [currentCodecName, currentCodecConfig] = entries[0];
                            }
                        }

                        const codecContainerId = `codec-container-${Date.now()}`;
                        const codecSelectId = `codec-select-${Date.now()}`;
                        const codecConfigId = `codec-config-${Date.now()}`;

                        inputField = `
            <div id="${codecContainerId}" class="space-y-3">
              <select id="${codecSelectId}" 
                      class="${inputClasses}"
                      onchange="handleCodecChange('${codecContainerId}', '${fieldId}', this.value)">
                <option value="">-- Select Codec --</option>
                ${codecNames.map(name => `
                  <option value="${name}" ${name === currentCodecName ? 'selected' : ''}>${name}</option>
                `).join('')}
              </select>
              <div id="${codecConfigId}" class="ml-4 space-y-2 border-l-2 border-gray-600 pl-4">
                <!-- Codec configuration fields will be inserted here -->
              </div>
              <input type="hidden" id="${fieldId}" name="${key}" data-field-type="codec" value='${escapeHtml(JSON.stringify(value || {}))}'>
            </div>
          `;
                    } else if (inputType === 'dropdown') {
                        // Handle dropdown input type
                        const dropdownOptions = option.options || [];
                        inputField = `
            <select id="${fieldId}" name="${key}" class="${inputClasses}">
              <option value="">-- Select an option --</option>
              ${dropdownOptions.map(opt => `
                <option value="${escapeHtml(opt)}" ${value === opt ? 'selected' : ''}>${escapeHtml(opt)}</option>
              `).join('')}
            </select>
          `;
                    } else if (inputType.includes('boolean') || inputType === 'bool') {
                        inputField = `
            <select id="${fieldId}" name="${key}" class="${inputClasses}">
              <option value="true" ${value === true || value === 'true' ? 'selected' : ''}>true</option>
              <option value="false" ${value === false || value === 'false' ? 'selected' : ''}>false</option>
              <option value="" ${value === '' ? 'selected' : ''}></option>
            </select>
          `;
                    } else if (inputType === 'array_of_hashes') {
                        // Handle array of hashes input type (e.g., SNMP hosts)
                        let arrayValue = [];
                        if (Array.isArray(value)) {
                            arrayValue = [...value];
                        } else if (typeof value === 'string' && value.trim() !== '') {
                            try {
                                const parsed = JSON.parse(value);
                                arrayValue = Array.isArray(parsed) ? parsed : [parsed];
                            } catch (e) {
                                arrayValue = [];
                            }
                        }

                        const containerId = `array-hash-container-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
                        const hashOptions = option.options || {};
                        const optionsJson = escapeHtml(JSON.stringify(hashOptions));
                        
                        inputField = `
            <div id="${containerId}" class="space-y-3" data-hash-options='${optionsJson}'>
              <div class="p-3 bg-gray-900/50 border border-gray-600 rounded">
                <div class="text-xs text-gray-400 mb-2">No entries yet. Click "+ Add Entry" to add one.</div>
              </div>
              <button type="button"
                      class="mt-2 px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm"
                      onclick="addArrayOfHashesItem('${containerId}', '${fieldId}')">
                + Add Entry
              </button>
              <input type="hidden" id="${fieldId}" name="${key}" data-field-type="array_of_hashes" value='${escapeHtml(JSON.stringify(arrayValue))}'>
            </div>
          `;
                    } else if (inputType === 'key_list_hash') {
                        // Handle key_list_hash input type (e.g., grok match field)
                        let keyListHashValue = {};
                        try {
                            if (typeof value === 'string' && value.trim() !== '') {
                                keyListHashValue = JSON.parse(value);
                            } else if (typeof value === 'object' && value !== null) {
                                keyListHashValue = {...value};
                            }
                        } catch (e) {
                            console.error('Error parsing key_list_hash value:', e);
                        }

                        const containerId = `key-list-hash-container-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
                        const sectionId = `key-list-hash-section-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
                        
                        inputField = `
            <div id="${containerId}" class="space-y-2">
              <div class="p-3 bg-gray-800/30 border border-gray-600/50 rounded space-y-3" data-section-id="${sectionId}">
                <div class="flex items-center gap-2">
                  <input type="text"
                         class="flex-1 p-2 bg-gray-700/50 border border-gray-600/50 rounded text-white text-sm section-key focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50"
                         placeholder="Key (e.g., message, field1)"
                         onchange="updateKeyListHashField('${containerId}', '${fieldId}')">
                  <button type="button"
                          class="px-3 py-2 text-red-400 hover:bg-gray-700 rounded text-sm transition-colors flex items-center gap-1"
                          onclick="removeKeyListHashSection('${containerId}', '${fieldId}', this)">
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                      Remove Section
                  </button>
                </div>
                <div class="ml-4 space-y-2 section-values">
                  <div class="flex items-center gap-2">
                    <span class="text-gray-400 text-sm">=></span>
                    <input type="text"
                           class="flex-1 p-2 bg-gray-700/50 border border-gray-600/50 rounded text-white text-sm focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50"
                           placeholder="Value (e.g., pattern1)"
                           onchange="updateKeyListHashField('${containerId}', '${fieldId}')">
                    <button type="button"
                            class="px-3 py-1 text-red-400 hover:bg-gray-700 rounded text-xs transition-colors flex items-center gap-1"
                            onclick="removeKeyListHashValue('${containerId}', '${fieldId}', this)">
                        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                        Remove
                    </button>
                  </div>
                </div>
                <button type="button"
                        class="ml-4 px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700 text-xs transition-colors"
                        onclick="addKeyListHashValue('${containerId}', '${fieldId}', this)">
                    + Add Value
                </button>
              </div>
              <button type="button"
                      class="px-3 py-1.5 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm transition-colors"
                      onclick="addKeyListHashSection('${containerId}', '${fieldId}')">
                + Add Section
              </button>
              <input type="hidden" id="${fieldId}" name="${key}" data-field-type="key_list_hash" value='${escapeHtml(JSON.stringify(keyListHashValue))}'>
            </div>
          `;
                    } else if (inputType.includes('hash') || inputType === 'object') {
                        // Handle hash/object input type
                        let hashValue = {};
                        try {
                            if (typeof value === 'string' && value.trim() !== '') {
                                hashValue = JSON.parse(value);
                            } else if (typeof value === 'object' && value !== null) {
                                hashValue = {...value};
                            }
                        } catch (e) {
                            console.error('Error parsing hash value:', e);
                        }

                        const containerId = `hash-container-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
                        inputField = `
            <div id="${containerId}" class="p-3 bg-gray-800/30 border border-gray-600/50 rounded space-y-2">
              <div class="flex items-center space-x-2">
                <input type="text"
                       class="flex-1 p-2 bg-gray-700 border border-gray-600 rounded text-white"
                       placeholder="Key"
                       onchange="updateHashPair('${containerId}', '${fieldId}', this, 'key')">
                <span class="text-gray-400">=></span>
                <input type="text"
                       class="flex-1 p-2 bg-gray-700 border border-gray-600 rounded text-white"
                       placeholder="Value"
                       onchange="updateHashPair('${containerId}', '${fieldId}', this, 'value')">
                <button type="button"
                        class="px-3 py-2 text-red-400 hover:bg-gray-700 rounded text-sm transition-colors flex items-center gap-1"
                        onclick="removeHashPair('${containerId}', this)">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                  Remove
                </button>
              </div>
              <button type="button"
                      class="mt-2 px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700 text-sm"
                      onclick="addHashPair('${containerId}', '${fieldId}')">
                + Add More
              </button>
              <input type="hidden" id="${fieldId}" name="${key}" data-field-type="hash" value='${escapeHtml(JSON.stringify(hashValue))}'>
            </div>
          `;
                    } else if (inputType.includes('array') || inputType === 'list') {
                        // Handle array input type
                        let arrayValue = [];
                        if (Array.isArray(value)) {
                            arrayValue = [...value];
                        } else if (typeof value === 'string' && value.trim() !== '') {
                            // Try to parse as JSON first
                            try {
                                const parsed = JSON.parse(value);
                                arrayValue = Array.isArray(parsed) ? parsed : [parsed];
                            } catch (e) {
                                // If not valid JSON, treat as a single string value
                                arrayValue = [value];
                            }
                        } else if (value !== undefined && value !== null && value !== '') {
                            // For any other non-empty value, wrap it in an array
                            arrayValue = [value];
                        }

                        const containerId = `array-container-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
                        inputField = `
            <div id="${containerId}" class="p-3 bg-gray-800/30 border border-gray-600/50 rounded space-y-2">
              <div class="flex items-center space-x-2">
                <input type="text"
                       class="flex-1 p-2 bg-gray-700 border border-gray-600 rounded text-white"
                       placeholder="Value"
                       onchange="updateArrayItem('${containerId}', '${fieldId}', this, 0)">
                <button type="button"
                        class="px-3 py-2 text-red-400 hover:bg-gray-700 rounded text-sm transition-colors flex items-center gap-1"
                        onclick="removeArrayItem('${containerId}', this)">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                  Remove
                </button>
              </div>
              <button type="button"
                      class="mt-2 px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700 text-sm"
                      onclick="addArrayItem('${containerId}', '${fieldId}')">
                + Add More
              </button>
              <input type="hidden" id="${fieldId}" name="${key}" data-field-type="array" value='${escapeHtml(JSON.stringify(arrayValue))}'>
            </div>
          `;
                    } else if (inputType.includes('number') || inputType === 'int' || inputType === 'float') {
                        inputField = `
            <input type="number" id="${fieldId}" name="${key}"
                   value="${escapeHtml(value)}"
                   step="${inputType === 'float' ? '0.1' : '1'}"
                   class="${inputClasses}">
          `;
                    } else if (key.toLowerCase() === 'code') {
                        // Special handling for "code" field - use textarea with preserved whitespace
                        inputField = `
            <textarea id="${fieldId}" name="${key}"
                      rows="10"
                      class="${inputClasses} font-mono text-sm whitespace-pre"
                      style="resize: vertical; min-height: 200px;">${escapeHtml(value)}</textarea>
          `;
                    } else if (component.plugin === 'comment' && (key === 'string' || key.toLowerCase() === 'message' || key.toLowerCase() === 'text')) {
                        // Special handling for comment plugin - use textarea for multiline comments
                        inputField = `
            <textarea id="${fieldId}" name="${key}"
                      rows="5"
                      class="${inputClasses} font-mono text-sm"
                      style="resize: vertical; min-height: 100px;"
                      placeholder="Enter your comment here...">${escapeHtml(value)}</textarea>
          `;
    } else if (inputType === 'password') {
        // Handle password input type with show/hide functionality
        inputField = `
            <div class="relative">
              <input type="password" id="${fieldId}" name="${key}"
                     value="${escapeHtml(value)}"
                     class="${inputClasses} pr-10">
              <button type="button" 
                      class="absolute right-2 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-200"
                      onclick="togglePasswordVisibility('${fieldId}', this)"
                      title="Show/Hide">
                <svg class="w-5 h-5 eye-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
              </button>
            </div>
          `;
    } else if (inputType === 'fs_path') {
        // Handle filesystem path input type with file picker button
        inputField = `
            <div class="flex items-center space-x-2">
              <input type="text" id="${fieldId}" name="${key}"
                     value="${escapeHtml(value)}"
                     class="${inputClasses} flex-1"
                     placeholder="Enter file path or click Browse...">
              <button type="button" 
                      class="px-3 py-2 bg-gray-600 text-white rounded hover:bg-gray-500 text-sm whitespace-nowrap"
                      onclick="browseFilePath('${fieldId}')"
                      title="Browse for file">
                <svg class="w-5 h-5 inline-block mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                </svg>
                Browse...
              </button>
            </div>
          `;
                    } else {
                        // Default to text input
                        inputField = `
            <input type="text" id="${fieldId}" name="${key}"
                   value="${escapeHtml(value)}"
                   class="${inputClasses}">
          `;
                    }

                    fieldGroup.innerHTML = `
          <div class="flex items-start justify-between">
            <label for="${fieldId}" class="block text-sm font-medium text-gray-300 mb-1">
              ${key}
              <span class="text-xs font-normal">
                (Required:
                  <span class="${option.required === 'Yes' ? 'text-green-400' : 'text-red-400'}">
                    ${option.required || 'No'}
                  </span>
                  , Type: ${option.input_type || 'string'}
                )
              </span>
            </label>
            ${pluginInfo.link && option.setting_link ? `
              <a href="${pluginInfo.link}${option.setting_link}" target="_blank"
                 class="text-gray-400 hover:text-blue-400 ml-2"
                 title="Documentation for ${key}">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </a>
            ` : ''}
          </div>
          ${option.description ? `<p class="text-xs text-gray-400 mb-1">${option.description}</p>` : ''}
          ${inputField}
          ${option.default_value !== undefined ?
                        `<p class="text-xs text-gray-400 mt-1">Default: <code class="bg-gray-900 px-1 rounded">${escapeHtml(option.default_value)}</code></p>` : ''}
        `;

                    advancedContent.appendChild(fieldGroup);
                });
                
                advancedSection.appendChild(advancedContent);
                configForm.appendChild(advancedSection);
            }
        } else {
            const noOptions = document.createElement('p');
            noOptions.className = 'text-gray-400 italic';
            noOptions.textContent = 'No configuration options available for this plugin.';
            configForm.appendChild(noOptions);
        }

        // Show the modal
        modal.classList.remove('hidden');

        // Check if we're in simulation mode and show event data panel
        const eventDataPanel = document.getElementById('eventDataPanel');
        const eventDataBefore = document.getElementById('eventDataBefore');
        const eventDataAfter = document.getElementById('eventDataAfter');
        const modalContainer = document.getElementById('configModalContainer');
        
        // Check if simulation mode is active by looking for simulation badges
        const isSimulationMode = document.querySelector('.simulation-executed-badge') !== null;
        
        if (isSimulationMode && eventDataPanel && eventDataBefore && eventDataAfter) {
            // Find the component element for this plugin
            const componentElement = document.querySelector(`[data-id="${component.id}"]`);
            
            if (componentElement) {
                // Find all "Original Event" or "View Full Event" elements
                const allDataFlows = document.querySelectorAll('.simulation-data-flow');
                
                // Find the data flow elements that come BEFORE and AFTER this component in the DOM
                let beforeDataFlow = null;
                let afterDataFlow = null;
                
                for (let i = 0; i < allDataFlows.length; i++) {
                    const dataFlow = allDataFlows[i];
                    
                    // Check if this data flow comes before the component element in the DOM
                    const position = componentElement.compareDocumentPosition(dataFlow);
                    
                    // If dataFlow comes before componentElement (position & 2 means PRECEDING)
                    if (position & Node.DOCUMENT_POSITION_PRECEDING) {
                        beforeDataFlow = dataFlow;
                    } else if (position & Node.DOCUMENT_POSITION_FOLLOWING) {
                        // If dataFlow comes after componentElement and we haven't found one yet
                        if (!afterDataFlow) {
                            afterDataFlow = dataFlow;
                        }
                    }
                }
                
                // Populate before section
                if (beforeDataFlow && beforeDataFlow.dataset.eventJson) {
                    // Use highlightJSON if available (from simulation_results.js)
                    if (typeof highlightJSON === 'function') {
                        const beforeChanges = beforeDataFlow.dataset.changes ? JSON.parse(beforeDataFlow.dataset.changes) : null;
                        eventDataBefore.innerHTML = highlightJSON(beforeDataFlow.dataset.eventJson, beforeChanges);
                    } else {
                        eventDataBefore.textContent = beforeDataFlow.dataset.eventJson;
                    }
                } else {
                    eventDataBefore.textContent = 'No event data available';
                }
                
                // Populate after section
                if (afterDataFlow && afterDataFlow.dataset.eventJson) {
                    // Use highlightJSON if available (from simulation_results.js)
                    if (typeof highlightJSON === 'function') {
                        const afterChanges = afterDataFlow.dataset.changes ? JSON.parse(afterDataFlow.dataset.changes) : null;
                        eventDataAfter.innerHTML = highlightJSON(afterDataFlow.dataset.eventJson, afterChanges);
                    } else {
                        eventDataAfter.textContent = afterDataFlow.dataset.eventJson;
                    }
                } else {
                    eventDataAfter.textContent = 'No event data available (plugin may be last in pipeline)';
                }
                
                // Show the panel
                eventDataPanel.classList.remove('hidden');
                modalContainer.style.maxWidth = '1400px';
            } else {
                eventDataPanel.classList.add('hidden');
                modalContainer.style.maxWidth = '600px';
            }
        } else {
            // Not in simulation mode, hide the event data panel
            if (eventDataPanel) {
                eventDataPanel.classList.add('hidden');
            }
            if (modalContainer) {
                modalContainer.style.maxWidth = '600px';
            }
        }

        // Populate existing hash, array, array_of_hashes, and key_list_hash values
        setTimeout(() => {
            populateExistingValues(component);
            populateCodecValues(component);
            populateArrayOfHashesValues(component);
            populateKeyListHashValues(component);
        }, 10);

        // Focus the first input field
        const firstInput = configForm.querySelector('input, select, textarea');
        if (firstInput) firstInput.focus();
    }

    // Populate existing hash and array values
    function populateExistingValues(component) {
        const configForm = document.getElementById('configForm');
        if (!configForm) return;

        // Find all hash containers and populate them
        configForm.querySelectorAll('[id^="hash-container-"]').forEach(container => {
            const hiddenField = container.querySelector('input[type="hidden"]');
            if (!hiddenField) return;

            try {
                const hashValue = JSON.parse(hiddenField.value);
                const entries = Object.entries(hashValue);

                if (entries.length > 0) {
                    // Remove the default empty pair
                    const defaultPair = container.querySelector('.flex.items-center.space-x-2');
                    if (defaultPair) {
                        const inputs = defaultPair.querySelectorAll('input[type="text"]');
                        if (inputs.length === 2 && !inputs[0].value && !inputs[1].value) {
                            defaultPair.remove();
                        }
                    }

                    // Add all existing pairs
                    const addButton = container.querySelector('button[onclick*="addHashPair"]');
                    entries.forEach(([key, value]) => {
                        const newPair = document.createElement('div');
                        newPair.className = 'flex items-center space-x-2';
                        newPair.innerHTML = `
              <input type="text"
                     class="flex-1 p-2 bg-gray-700 border border-gray-600 rounded text-white"
                     placeholder="Key"
                     value="${escapeHtml(key)}"
                     onchange="updateHashPair('${container.id}', '${hiddenField.id}', this, 'key')">
              <span class="text-gray-400">=></span>
              <input type="text"
                     class="flex-1 p-2 bg-gray-700 border border-gray-600 rounded text-white"
                     placeholder="Value"
                     value="${escapeHtml(value)}"
                     onchange="updateHashPair('${container.id}', '${hiddenField.id}', this, 'value')">
              <button type="button"
                      class="px-3 py-2 text-red-400 hover:bg-gray-700 rounded text-sm transition-colors flex items-center gap-1"
                      onclick="removeHashPair('${container.id}', this)">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
                Remove
              </button>
            `;
                        addButton.parentNode.insertBefore(newPair, addButton);
                    });
                }
            } catch (e) {
                console.error('Error populating hash values:', e);
            }
        });

        // Find all array containers and populate them
        configForm.querySelectorAll('[id^="array-container-"]').forEach(container => {
            const hiddenField = container.querySelector('input[type="hidden"]');
            if (!hiddenField) return;

            try {
                const arrayValue = JSON.parse(hiddenField.value);

                if (Array.isArray(arrayValue) && arrayValue.length > 0) {
                    // Remove the default empty item
                    const defaultItem = container.querySelector('.flex.items-center.space-x-2');
                    if (defaultItem) {
                        const input = defaultItem.querySelector('input[type="text"]');
                        if (input && !input.value) {
                            defaultItem.remove();
                        }
                    }

                    // Add all existing items
                    const addButton = container.querySelector('button[onclick*="addArrayItem"]');
                    arrayValue.forEach((value, index) => {
                        const newItem = document.createElement('div');
                        newItem.className = 'flex items-center space-x-2';
                        newItem.innerHTML = `
              <input type="text"
                     class="flex-1 p-2 bg-gray-700 border border-gray-600 rounded text-white"
                     placeholder="Value"
                     value="${escapeHtml(value)}"
                     onchange="updateArrayItem('${container.id}', '${hiddenField.id}', this, ${index})">
              <button type="button"
                      class="px-3 py-2 text-red-400 hover:bg-gray-700 rounded text-sm transition-colors flex items-center gap-1"
                      onclick="removeArrayItem('${container.id}', this)">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
                Remove
              </button>
            `;
                        addButton.parentNode.insertBefore(newItem, addButton);
                    });
                }
            } catch (e) {
                console.error('Error populating array values:', e);
            }
        });
    }

    // Populate codec values
    function populateCodecValues(component) {
        const configForm = document.getElementById('configForm');
        if (!configForm) return;

        // Find all codec containers
        configForm.querySelectorAll('[id^="codec-container-"]').forEach(container => {
            const selectElement = container.querySelector('select[id^="codec-select-"]');
            const hiddenField = container.querySelector('input[type="hidden"]');

            if (!selectElement || !hiddenField) return;

            try {
                const codecValue = JSON.parse(hiddenField.value);
                const entries = Object.entries(codecValue);

                if (entries.length > 0) {
                    const [codecName, codecConfig] = entries[0];

                    // Set the select value
                    selectElement.value = codecName;

                    // Trigger the codec change to populate fields
                    window.handleCodecChange(container.id, hiddenField.id, codecName);
                }
            } catch (e) {
                console.error('Error populating codec values:', e);
            }
        });
    }

    // Hide the configuration modal
    function hide() {
        document.getElementById('configModal').classList.add('hidden');
        isNewComponent = false; // Reset flag

        // Trigger pending animation if there is one
        if (typeof window.triggerPendingAnimation === 'function') {
            window.triggerPendingAnimation();
        }
    }

    // Cancel and remove component if it's new
    function cancel() {
        if (isNewComponent && currentComponent) {
            // Remove the component from the components array
            removeComponentById(currentComponent.id);
            // Refresh the UI
            if (typeof loadExistingComponents === 'function') {
                loadExistingComponents();
            }
        }
        hide();
    }

    // Helper function to remove a component by ID
    function removeComponentById(componentId) {
        // Search through all component types
        for (const type in components) {
            const index = components[type].findIndex(c => c.id === componentId);
            if (index !== -1) {
                components[type].splice(index, 1);
                return true;
            }
            // Also check nested components in conditionals
            for (const component of components[type]) {
                if (component.plugin === 'if') {
                    // Check if block
                    if (component.config.plugins) {
                        const ifIndex = component.config.plugins.findIndex(c => c.id === componentId);
                        if (ifIndex !== -1) {
                            component.config.plugins.splice(ifIndex, 1);
                            return true;
                        }
                    }
                    // Check else-if blocks
                    if (component.config.else_ifs) {
                        for (const elseIf of component.config.else_ifs) {
                            if (elseIf.plugins) {
                                const elseIfIndex = elseIf.plugins.findIndex(c => c.id === componentId);
                                if (elseIfIndex !== -1) {
                                    elseIf.plugins.splice(elseIfIndex, 1);
                                    return true;
                                }
                            }
                        }
                    }
                    // Check else block
                    if (component.config.else && component.config.else.plugins) {
                        const elseIndex = component.config.else.plugins.findIndex(c => c.id === componentId);
                        if (elseIndex !== -1) {
                            component.config.else.plugins.splice(elseIndex, 1);
                            return true;
                        }
                    }
                }
            }
        }
        return false;
    }

    // Save the configuration
    function saveConfig() {
        if (!currentComponent) return;

        const form = document.getElementById('configForm');

        // Validate required fields
        const firstEmptyField = validateRequiredFields();
        if (firstEmptyField) {
            // Focus the first empty required field
            firstEmptyField.focus();
            return;
        }
        
        const formData = new FormData(form);
        const config = {};

        // Process form data
        for (const [key, value] of formData.entries()) {
            const input = form.querySelector(`[name="${key}"]`);
            const fieldType = input ? input.dataset.fieldType : null;

            // Skip if the value is empty and not explicitly set
            if (value === '') {
                continue;
            }

            try {
                // Handle different field types
                if (fieldType === 'codec') {
                    const parsedValue = JSON.parse(value);
                    // Only add if codec is selected
                    if (Object.keys(parsedValue).length > 0) {
                        config[key] = parsedValue;
                    }
                } else if (fieldType === 'hash' || fieldType === 'array' || fieldType === 'array_of_hashes' || fieldType === 'key_list_hash') {
                    const parsedValue = JSON.parse(value);
                    // Only add if the hash/array is not empty
                    if (Object.keys(parsedValue).length > 0 || (Array.isArray(parsedValue) && parsedValue.length > 0)) {
                        config[key] = parsedValue;
                    }
                } else if (value === 'true') {
                    // Only add boolean if it's different from default
                    if (pluginData[currentComponent.type]?.[currentComponent.plugin]?.options?.[key]?.default !== true) {
                        config[key] = true;
                    }
                } else if (value === 'false') {
                    // Only add boolean if it's different from default
                    if (pluginData[currentComponent.type]?.[currentComponent.plugin]?.options?.[key]?.default !== false) {
                        config[key] = false;
                    }
                } else if (!isNaN(value)) {
                    // Only add number if it's different from default
                    const defaultValue = pluginData[currentComponent.type]?.[currentComponent.plugin]?.options?.[key]?.default;
                    if (defaultValue === undefined || Number(value) !== defaultValue) {
                        config[key] = Number(value);
                    }
                } else {
                    // Only add string if it's different from default
                    const defaultValue = pluginData[currentComponent.type]?.[currentComponent.plugin]?.options?.[key]?.default;
                    if (defaultValue === undefined || value !== defaultValue.toString()) {
                        config[key] = value;
                    }
                }
            } catch (e) {
                console.error(`Error processing field ${key}:`, e);
                // Only add if there was an error and the value is not empty
                if (value !== '') {
                    config[key] = value;
                }
            }
        }

        // Update the component's configuration
        currentComponent.config = config;

        // Store the pending animation ID before updating (in case it gets cleared)
        const savedPendingId = typeof pendingAnimationPluginId !== 'undefined' ? pendingAnimationPluginId : null;

        // If there's a global update function, call it
        if (window.updateComponent) {
            window.updateComponent(currentComponent);
        }

        // Restore the pending animation ID if it was cleared
        if (savedPendingId && typeof pendingAnimationPluginId !== 'undefined') {
            pendingAnimationPluginId = savedPendingId;
        }

        // Hide the modal (this will trigger the animation)
        hide();
    }

    // Validate required fields
    function validateRequiredFields() {
        const form = document.getElementById('configForm');
        const requiredFields = form.querySelectorAll('[data-required="true"]');
        
        for (const fieldGroup of requiredFields) {
            const fieldName = fieldGroup.dataset.fieldName;
            const fieldType = fieldGroup.dataset.fieldType;
            const input = fieldGroup.querySelector('input:not([type="hidden"]), select, textarea');
            
            if (!input) continue;
            
            let isEmpty = false;
            
            // Check based on field type
            if (fieldType === 'codec') {
                const hiddenInput = fieldGroup.querySelector('input[type="hidden"]');
                if (hiddenInput) {
                    try {
                        const value = JSON.parse(hiddenInput.value);
                        isEmpty = Object.keys(value).length === 0;
                    } catch (e) {
                        isEmpty = true;
                    }
                }
            } else if (fieldType === 'hash' || fieldType === 'object' || fieldType === 'key_list_hash') {
                const hiddenInput = fieldGroup.querySelector('input[type="hidden"]');
                if (hiddenInput) {
                    try {
                        const value = JSON.parse(hiddenInput.value);
                        isEmpty = Object.keys(value).length === 0;
                    } catch (e) {
                        isEmpty = true;
                    }
                }
            } else if (fieldType === 'array' || fieldType === 'list' || fieldType === 'array_of_hashes') {
                const hiddenInput = fieldGroup.querySelector('input[type="hidden"]');
                if (hiddenInput) {
                    try {
                        const value = JSON.parse(hiddenInput.value);
                        isEmpty = !Array.isArray(value) || value.length === 0;
                    } catch (e) {
                        isEmpty = true;
                    }
                }
            } else {
                // Regular input field
                isEmpty = !input.value || input.value.trim() === '';
            }
            
            if (isEmpty) {
                // Return the first visible input to focus
                return input;
            }
        }
        
        return null;
    }

    // Helper function to get color based on plugin type
    function getPluginTypeColor(type) {
        switch (type) {
            case 'input':
                return 'bg-green-600/20 text-green-400';
            case 'filter':
                return 'bg-blue-600/20 text-blue-400';
            case 'output':
                return 'bg-purple-600/20 text-purple-400';
            default:
                return 'bg-gray-600/20 text-gray-400';
        }
    }

    // Helper function to check if a field is sensitive (password/api_key)
    function isSensitiveField(fieldName) {
        const lowerFieldName = fieldName.toLowerCase();
        return lowerFieldName.includes('password') || 
               lowerFieldName.includes('api_key') || 
               lowerFieldName.includes('apikey') ||
               lowerFieldName === 'token' ||
               lowerFieldName.includes('secret');
    }

    // Public API
    return {
        init,
        show,
        hide,
        cancel,
        saveConfig,
        getPluginData: () => pluginData
    };
})();

// Hash/Dictionary helper functions
window.addHashPair = function (containerId, fieldId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const addButton = container.querySelector('button[onclick*="addHashPair"]');
    if (!addButton) return;

    const newPair = document.createElement('div');
    newPair.className = 'flex items-center space-x-2';
    newPair.innerHTML = `
    <input type="text"
           class="flex-1 p-2 bg-gray-700 border border-gray-600 rounded text-white"
           placeholder="Key"
           onchange="updateHashPair('${containerId}', '${fieldId}', this, 'key')">
    <span class="text-gray-400">=></span>
    <input type="text"
           class="flex-1 p-2 bg-gray-700 border border-gray-600 rounded text-white"
           placeholder="Value"
           onchange="updateHashPair('${containerId}', '${fieldId}', this, 'value')">
    <button type="button"
            class="px-3 py-2 text-red-400 hover:bg-gray-700 rounded text-sm transition-colors flex items-center gap-1"
            onclick="removeHashPair('${containerId}', this)">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
      </svg>
      Remove
    </button>
  `;

    // Insert before the add button
    addButton.parentNode.insertBefore(newPair, addButton);
};

window.removeHashPair = function (containerId, button) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const pairDiv = button.closest('.flex.items-center.space-x-2');
    if (pairDiv) {
        pairDiv.remove();
        // Update the hidden field after removal
        const fieldId = container.querySelector('input[type="hidden"]').id;
        updateHashField(containerId, fieldId);
    }
};

window.updateHashPair = function (containerId, fieldId, input, type) {
    updateHashField(containerId, fieldId);
};

function updateHashField(containerId, fieldId) {
    const container = document.getElementById(containerId);
    const hiddenField = document.getElementById(fieldId);
    if (!container || !hiddenField) return;

    const pairs = container.querySelectorAll('.flex.items-center.space-x-2');
    const hashObj = {};

    pairs.forEach(pair => {
        const inputs = pair.querySelectorAll('input[type="text"]');
        if (inputs.length === 2) {
            const key = inputs[0].value.trim();
            const value = inputs[1].value.trim();
            if (key !== '') {
                hashObj[key] = value;
            }
        }
    });

    hiddenField.value = JSON.stringify(hashObj);
}

// Array/List helper functions
window.addArrayItem = function (containerId, fieldId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const addButton = container.querySelector('button[onclick*="addArrayItem"]');
    if (!addButton) return;

    const existingItems = container.querySelectorAll('.flex.items-center.space-x-2');
    const newIndex = existingItems.length;

    const newItem = document.createElement('div');
    newItem.className = 'flex items-center space-x-2';
    newItem.innerHTML = `
    <input type="text"
           class="flex-1 p-2 bg-gray-700 border border-gray-600 rounded text-white"
           placeholder="Value"
           onchange="updateArrayItem('${containerId}', '${fieldId}', this, ${newIndex})">
    <button type="button"
            class="px-3 py-2 text-red-400 hover:bg-gray-700 rounded text-sm transition-colors flex items-center gap-1"
            onclick="removeArrayItem('${containerId}', this)">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
      </svg>
      Remove
    </button>
  `;

    // Insert before the add button
    addButton.parentNode.insertBefore(newItem, addButton);
};

window.removeArrayItem = function (containerId, button) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const itemDiv = button.closest('.flex.items-center.space-x-2');
    if (itemDiv) {
        itemDiv.remove();
        // Update the hidden field after removal
        const fieldId = container.querySelector('input[type="hidden"]').id;
        updateArrayField(containerId, fieldId);
    }
};

window.updateArrayItem = function (containerId, fieldId, input, index) {
    updateArrayField(containerId, fieldId);
};

function updateArrayField(containerId, fieldId) {
    const container = document.getElementById(containerId);
    const hiddenField = document.getElementById(fieldId);
    if (!container || !hiddenField) return;

    const items = container.querySelectorAll('.flex.items-center.space-x-2');
    const arrayValues = [];

    items.forEach(item => {
        const input = item.querySelector('input[type="text"]');
        if (input) {
            const value = input.value.trim();
            if (value !== '') {
                arrayValues.push(value);
            }
        }
    });

    hiddenField.value = JSON.stringify(arrayValues);
}

// Array of Hashes helper functions
window.addArrayOfHashesItem = function (containerId, fieldId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const addButton = container.querySelector('button[onclick*="addArrayOfHashesItem"]');
    if (!addButton) return;

    // Get hash options from container data attribute
    const hashOptionsJson = container.dataset.hashOptions;
    let hashOptions = {};
    try {
        hashOptions = JSON.parse(hashOptionsJson);
    } catch (e) {
        console.error('Error parsing hash options:', e);
        return;
    }

    // Remove the "no entries" placeholder if it exists (but not actual entries)
    // The placeholder doesn't have a data-entry-id attribute
    const allDivs = container.querySelectorAll('.bg-gray-900\\/50, [class*="bg-gray-900/50"]');
    allDivs.forEach(div => {
        if (!div.dataset.entryId && div.textContent.includes('No entries yet')) {
            div.remove();
        }
    });

    // Create unique ID for this hash entry
    const entryId = `hash-entry-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    // Build the hash entry with fields based on options
    const entryDiv = document.createElement('div');
    entryDiv.className = 'p-3 bg-gray-900/50 border border-gray-600 rounded space-y-2';
    entryDiv.dataset.entryId = entryId;

    let fieldsHtml = '';
    for (const [optKey, optInfo] of Object.entries(hashOptions)) {
        const optType = (optInfo.type || 'string').toLowerCase();
        const inputClass = 'w-full p-2 bg-gray-700 border border-gray-600 rounded text-white text-sm';
        
        let inputHtml = '';
        if (optType === 'number') {
            inputHtml = `<input type="number" class="${inputClass}" placeholder="${optKey}" data-field="${optKey}" onchange="updateArrayOfHashesField('${containerId}', '${fieldId}')">`;
        } else if (optType === 'boolean') {
            inputHtml = `
                <select class="${inputClass}" data-field="${optKey}" onchange="updateArrayOfHashesField('${containerId}', '${fieldId}')">
                    <option value="">-- Not Set --</option>
                    <option value="true">true</option>
                    <option value="false">false</option>
                </select>
            `;
        } else {
            inputHtml = `<input type="text" class="${inputClass}" placeholder="${optKey}" data-field="${optKey}" onchange="updateArrayOfHashesField('${containerId}', '${fieldId}')">`;
        }

        fieldsHtml += `
            <div>
                <label class="block text-xs font-medium text-gray-300 mb-1">${optKey}</label>
                ${inputHtml}
            </div>
        `;
    }

    entryDiv.innerHTML = `
        ${fieldsHtml}
        <button type="button"
                class="mt-2 px-3 py-1 bg-red-600 text-white rounded hover:bg-red-700 text-sm w-full"
                onclick="removeArrayOfHashesItem('${containerId}', '${fieldId}', this)">
            Remove Entry
        </button>
    `;

    // Insert before the add button
    addButton.parentNode.insertBefore(entryDiv, addButton);
    
    // Update the hidden field
    updateArrayOfHashesField(containerId, fieldId);
};

window.removeArrayOfHashesItem = function (containerId, fieldId, button) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const entryDiv = button.closest('[data-entry-id]');
    if (entryDiv) {
        entryDiv.remove();
        
        // Check if there are any entries left
        const remainingEntries = container.querySelectorAll('[data-entry-id]');
        if (remainingEntries.length === 0) {
            // Add back the placeholder
            const addButton = container.querySelector('button[onclick*="addArrayOfHashesItem"]');
            if (addButton) {
                const placeholder = document.createElement('div');
                placeholder.className = 'p-3 bg-gray-900/50 border border-gray-600 rounded';
                placeholder.innerHTML = '<div class="text-xs text-gray-400 mb-2">No entries yet. Click "+ Add Entry" to add one.</div>';
                addButton.parentNode.insertBefore(placeholder, addButton);
            }
        }
        
        // Update the hidden field
        updateArrayOfHashesField(containerId, fieldId);
    }
};

window.updateArrayOfHashesField = function (containerId, fieldId) {
    const container = document.getElementById(containerId);
    const hiddenField = document.getElementById(fieldId);
    if (!container || !hiddenField) return;

    const entries = container.querySelectorAll('[data-entry-id]');
    const arrayValue = [];

    entries.forEach(entry => {
        const hashObj = {};
        const inputs = entry.querySelectorAll('[data-field]');
        
        inputs.forEach(input => {
            const fieldName = input.dataset.field;
            let value = input.value.trim();
            
            if (value !== '') {
                // Convert boolean strings to actual booleans
                if (value === 'true') value = true;
                else if (value === 'false') value = false;
                // Convert numbers
                else if (input.type === 'number' && !isNaN(value)) value = Number(value);
                
                hashObj[fieldName] = value;
            }
        });

        // Only add the hash if it has at least one field
        if (Object.keys(hashObj).length > 0) {
            arrayValue.push(hashObj);
        }
    });

    hiddenField.value = JSON.stringify(arrayValue);
};

// Populate existing array_of_hashes values
function populateArrayOfHashesValues(component) {
    const configForm = document.getElementById('configForm');
    if (!configForm) return;

    // Find all array-hash containers and populate them
    configForm.querySelectorAll('[id^="array-hash-container-"]').forEach(container => {
        const hiddenField = container.querySelector('input[type="hidden"]');
        if (!hiddenField) return;

        try {
            const arrayValue = JSON.parse(hiddenField.value);

            if (Array.isArray(arrayValue) && arrayValue.length > 0) {
                // Remove the placeholder (but not actual entries)
                const allDivs = container.querySelectorAll('.bg-gray-900\\/50, [class*="bg-gray-900/50"]');
                allDivs.forEach(div => {
                    if (!div.dataset.entryId && div.textContent.includes('No entries yet')) {
                        div.remove();
                    }
                });

                // Get hash options
                const hashOptionsJson = container.dataset.hashOptions;
                let hashOptions = {};
                try {
                    hashOptions = JSON.parse(hashOptionsJson);
                } catch (e) {
                    console.error('Error parsing hash options:', e);
                    return;
                }

                // Add all existing entries
                const addButton = container.querySelector('button[onclick*="addArrayOfHashesItem"]');
                arrayValue.forEach((hashObj, index) => {
                    const entryId = `hash-entry-${Date.now()}-${index}`;
                    const entryDiv = document.createElement('div');
                    entryDiv.className = 'p-3 bg-gray-900/50 border border-gray-600 rounded space-y-2';
                    entryDiv.dataset.entryId = entryId;

                    let fieldsHtml = '';
                    for (const [optKey, optInfo] of Object.entries(hashOptions)) {
                        const optType = (optInfo.type || 'string').toLowerCase();
                        const inputClass = 'w-full p-2 bg-gray-700 border border-gray-600 rounded text-white text-sm';
                        const existingValue = hashObj[optKey] || '';
                        
                        let inputHtml = '';
                        if (optType === 'number') {
                            inputHtml = `<input type="number" class="${inputClass}" placeholder="${optKey}" data-field="${optKey}" value="${existingValue}" onchange="updateArrayOfHashesField('${container.id}', '${hiddenField.id}')">`;
                        } else if (optType === 'boolean') {
                            inputHtml = `
                                <select class="${inputClass}" data-field="${optKey}" onchange="updateArrayOfHashesField('${container.id}', '${hiddenField.id}')">
                                    <option value="">-- Not Set --</option>
                                    <option value="true" ${existingValue === true || existingValue === 'true' ? 'selected' : ''}>true</option>
                                    <option value="false" ${existingValue === false || existingValue === 'false' ? 'selected' : ''}>false</option>
                                </select>
                            `;
                        } else {
                            const escapedValue = String(existingValue).replace(/"/g, '&quot;');
                            inputHtml = `<input type="text" class="${inputClass}" placeholder="${optKey}" data-field="${optKey}" value="${escapedValue}" onchange="updateArrayOfHashesField('${container.id}', '${hiddenField.id}')">`;
                        }

                        fieldsHtml += `
                            <div>
                                <label class="block text-xs font-medium text-gray-300 mb-1">${optKey}</label>
                                ${inputHtml}
                            </div>
                        `;
                    }

                    entryDiv.innerHTML = `
                        ${fieldsHtml}
                        <button type="button"
                                class="mt-2 px-3 py-1 bg-red-600 text-white rounded hover:bg-red-700 text-sm w-full"
                                onclick="removeArrayOfHashesItem('${container.id}', '${hiddenField.id}', this)">
                            Remove Entry
                        </button>
                    `;

                    addButton.parentNode.insertBefore(entryDiv, addButton);
                });
            }
        } catch (e) {
            console.error('Error populating array_of_hashes values:', e);
        }
    });
}

// Key List Hash helper functions (for fields like grok match)
window.addKeyListHashSection = function (containerId, fieldId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const addButton = container.querySelector('button[onclick*="addKeyListHashSection"]');
    if (!addButton) return;

    // Create unique ID for this section
    const sectionId = `key-list-hash-section-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    const sectionDiv = document.createElement('div');
    sectionDiv.className = 'p-3 bg-gray-800/30 border border-gray-600/50 rounded space-y-3';
    sectionDiv.dataset.sectionId = sectionId;
    
    sectionDiv.innerHTML = `
        <div class="flex items-center gap-2">
            <input type="text"
                   class="flex-1 p-2 bg-gray-700/50 border border-gray-600/50 rounded text-white text-sm section-key focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50"
                   placeholder="Key (e.g., message, field1)"
                   onchange="updateKeyListHashField('${containerId}', '${fieldId}')">
            <button type="button"
                    class="px-3 py-2 text-red-400 hover:bg-gray-700 rounded text-sm transition-colors flex items-center gap-1"
                    onclick="removeKeyListHashSection('${containerId}', '${fieldId}', this)">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
                Remove Section
            </button>
        </div>
        <div class="ml-4 space-y-2 section-values">
            <div class="flex items-center gap-2">
                <span class="text-gray-400 text-sm">=></span>
                <input type="text"
                       class="flex-1 p-2 bg-gray-700/50 border border-gray-600/50 rounded text-white text-sm focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50"
                       placeholder="Value (e.g., pattern1)"
                       onchange="updateKeyListHashField('${containerId}', '${fieldId}')">
                <button type="button"
                        class="px-3 py-1 text-red-400 hover:bg-gray-700 rounded text-xs transition-colors flex items-center gap-1"
                        onclick="removeKeyListHashValue('${containerId}', '${fieldId}', this)">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                    Remove
                </button>
            </div>
        </div>
        <button type="button"
                class="ml-4 px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700 text-xs transition-colors"
                onclick="addKeyListHashValue('${containerId}', '${fieldId}', this)">
            + Add Value
        </button>
    `;
    
    addButton.parentNode.insertBefore(sectionDiv, addButton);
    updateKeyListHashField(containerId, fieldId);
};

window.removeKeyListHashSection = function (containerId, fieldId, button) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const sectionDiv = button.closest('[data-section-id]');
    if (sectionDiv) {
        // Check if there are any sections left
        const remainingSections = container.querySelectorAll('[data-section-id]');
        
        // Only remove if there's more than one section (keep at least one)
        if (remainingSections.length > 1) {
            sectionDiv.remove();
            updateKeyListHashField(containerId, fieldId);
        } else {
            // Clear the inputs instead of removing the last section
            const keyInput = sectionDiv.querySelector('.section-key');
            const valueInputs = sectionDiv.querySelectorAll('.section-values input[type="text"]');
            
            if (keyInput) keyInput.value = '';
            valueInputs.forEach(input => input.value = '');
            
            updateKeyListHashField(containerId, fieldId);
        }
    }
};

window.addKeyListHashValue = function (containerId, fieldId, button) {
    const sectionDiv = button.closest('[data-section-id]');
    if (!sectionDiv) return;

    const valuesContainer = sectionDiv.querySelector('.section-values');
    if (!valuesContainer) return;

    const newValue = document.createElement('div');
    newValue.className = 'flex items-center gap-2';
    newValue.innerHTML = `
        <span class="text-gray-400 text-sm">=></span>
        <input type="text"
               class="flex-1 p-2 bg-gray-700/50 border border-gray-600/50 rounded text-white text-sm focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50"
               placeholder="Value"
               onchange="updateKeyListHashField('${containerId}', '${fieldId}')">
        <button type="button"
                class="px-3 py-1 text-red-400 hover:bg-gray-700 rounded text-xs transition-colors flex items-center gap-1"
                onclick="removeKeyListHashValue('${containerId}', '${fieldId}', this)">
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
            Remove
        </button>
    `;
    
    valuesContainer.appendChild(newValue);
    updateKeyListHashField(containerId, fieldId);
};

window.removeKeyListHashValue = function (containerId, fieldId, button) {
    const valueDiv = button.closest('.flex.items-center.space-x-2');
    if (valueDiv) {
        valueDiv.remove();
        updateKeyListHashField(containerId, fieldId);
    }
};

window.updateKeyListHashField = function (containerId, fieldId) {
    const container = document.getElementById(containerId);
    const hiddenField = document.getElementById(fieldId);
    if (!container || !hiddenField) return;

    const sections = container.querySelectorAll('[data-section-id]');
    const result = {};

    sections.forEach(section => {
        const keyInput = section.querySelector('.section-key');
        if (!keyInput) return;

        const key = keyInput.value.trim();
        if (!key) return;

        const valueInputs = section.querySelectorAll('.section-values input[type="text"]');
        const values = [];
        
        valueInputs.forEach(input => {
            const value = input.value.trim();
            if (value) {
                values.push(value);
            }
        });

        // Store as single value if only one, or array if multiple
        if (values.length === 1) {
            result[key] = values[0];
        } else if (values.length > 1) {
            result[key] = values;
        }
    });

    hiddenField.value = JSON.stringify(result);
};

// Populate existing key_list_hash values
function populateKeyListHashValues(component) {
    const configForm = document.getElementById('configForm');
    if (!configForm) return;

    configForm.querySelectorAll('[id^="key-list-hash-container-"]').forEach(container => {
        const hiddenField = container.querySelector('input[type="hidden"]');
        if (!hiddenField) return;

        try {
            const keyListHashValue = JSON.parse(hiddenField.value);
            const entries = Object.entries(keyListHashValue);

            if (entries.length > 0) {
                // Remove the default empty section first
                const defaultSection = container.querySelector('[data-section-id]');
                if (defaultSection) {
                    const keyInput = defaultSection.querySelector('.section-key');
                    if (keyInput && !keyInput.value) {
                        defaultSection.remove();
                    }
                }

                const addButton = container.querySelector('button[onclick*="addKeyListHashSection"]');
                
                entries.forEach(([key, value]) => {
                    const sectionId = `key-list-hash-section-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
                    const sectionDiv = document.createElement('div');
                    sectionDiv.className = 'p-3 bg-gray-800/30 border border-gray-600/50 rounded space-y-3';
                    sectionDiv.dataset.sectionId = sectionId;
                    
                    // Normalize value to array
                    const values = Array.isArray(value) ? value : [value];
                    
                    let valuesHtml = '';
                    values.forEach(val => {
                        valuesHtml += `
                            <div class="flex items-center gap-2">
                                <span class="text-gray-400 text-sm">=></span>
                                <input type="text"
                                       class="flex-1 p-2 bg-gray-700/50 border border-gray-600/50 rounded text-white text-sm focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50"
                                       placeholder="Value"
                                       value="${escapeHtml(val)}"
                                       onchange="updateKeyListHashField('${container.id}', '${hiddenField.id}')">
                                <button type="button"
                                        class="px-3 py-1 text-red-400 hover:bg-gray-700 rounded text-xs transition-colors flex items-center gap-1"
                                        onclick="removeKeyListHashValue('${container.id}', '${hiddenField.id}', this)">
                                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                    </svg>
                                    Remove
                                </button>
                            </div>
                        `;
                    });
                    
                    sectionDiv.innerHTML = `
                        <div class="flex items-center gap-2">
                            <input type="text"
                                   class="flex-1 p-2 bg-gray-700/50 border border-gray-600/50 rounded text-white text-sm section-key focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50"
                                   placeholder="Key (e.g., message, field1)"
                                   value="${escapeHtml(key)}"
                                   onchange="updateKeyListHashField('${container.id}', '${hiddenField.id}')">
                            <button type="button"
                                    class="px-3 py-2 text-red-400 hover:bg-gray-700 rounded text-sm transition-colors flex items-center gap-1"
                                    onclick="removeKeyListHashSection('${container.id}', '${hiddenField.id}', this)">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                </svg>
                                Remove Section
                            </button>
                        </div>
                        <div class="ml-4 space-y-2 section-values">
                            ${valuesHtml}
                        </div>
                        <button type="button"
                                class="ml-4 px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700 text-xs transition-colors"
                                onclick="addKeyListHashValue('${container.id}', '${hiddenField.id}', this)">
                            + Add Value
                        </button>
                    `;
                    
                    addButton.parentNode.insertBefore(sectionDiv, addButton);
                });
            }
        } catch (e) {
            console.error('Error populating key_list_hash values:', e);
        }
    });
}

// Codec helper functions
window.handleCodecChange = function (containerId, fieldId, codecName) {
    const container = document.getElementById(containerId);
    const hiddenField = document.getElementById(fieldId);
    if (!container || !hiddenField) return;

    // Find the codec config container
    const codecConfigContainer = container.querySelector('[id^="codec-config-"]');
    if (!codecConfigContainer) return;

    // Clear previous codec config
    codecConfigContainer.innerHTML = '';

    if (!codecName) {
        // No codec selected, clear the hidden field
        hiddenField.value = JSON.stringify({});
        return;
    }

    // Get codec options from pluginData
    const codecData = window.PluginConfigModal.getPluginData();
    const codecInfo = codecData.codec?.[codecName];

    if (!codecInfo || !codecInfo.options) {
        // Codec has no options, just store the codec name with empty config
        hiddenField.value = JSON.stringify({[codecName]: {}});
        return;
    }

    // Add codec description
    if (codecInfo.description) {
        const desc = document.createElement('p');
        desc.className = 'text-xs text-gray-400 mb-2 italic';
        desc.textContent = codecInfo.description;
        codecConfigContainer.appendChild(desc);
    }

    // Get existing codec config
    let existingConfig = {};
    try {
        const currentValue = JSON.parse(hiddenField.value);
        if (currentValue[codecName]) {
            existingConfig = currentValue[codecName];
        }
    } catch (e) {
        console.error('Error parsing codec value:', e);
    }

    // Create fields for codec options
    Object.entries(codecInfo.options).forEach(([optKey, optInfo]) => {
        const codecFieldId = `codec-field-${codecName}-${optKey}-${Date.now()}`;
        const optValue = existingConfig[optKey] || '';
        const optType = (optInfo.input_type || 'text').toLowerCase();

        const fieldDiv = document.createElement('div');
        fieldDiv.className = 'mb-3';

        let inputHtml = '';
        const inputClasses = 'w-full p-2 bg-gray-700 border border-gray-600 rounded text-white text-sm';

        if (optType.includes('boolean') || optType === 'bool') {
            inputHtml = `
        <select id="${codecFieldId}" class="${inputClasses}"
                onchange="updateCodecField('${containerId}', '${fieldId}', '${codecName}', '${optKey}', this.value)">
          <option value="">-- Not Set --</option>
          <option value="true" ${optValue === true || optValue === 'true' ? 'selected' : ''}>true</option>
          <option value="false" ${optValue === false || optValue === 'false' ? 'selected' : ''}>false</option>
        </select>
      `;
        } else if (optType.includes('number') || optType === 'int' || optType === 'float') {
            inputHtml = `
        <input type="number" id="${codecFieldId}" class="${inputClasses}"
               value="${optValue}"
               step="${optType === 'float' ? '0.1' : '1'}"
               onchange="updateCodecField('${containerId}', '${fieldId}', '${codecName}', '${optKey}', this.value)">
      `;
        } else if (optType.includes('array')) {
            inputHtml = `
        <input type="text" id="${codecFieldId}" class="${inputClasses}"
               value="${Array.isArray(optValue) ? optValue.join(', ') : optValue}"
               placeholder="Comma-separated values"
               onchange="updateCodecField('${containerId}', '${fieldId}', '${codecName}', '${optKey}', this.value.split(',').map(v => v.trim()).filter(v => v))">
      `;
        } else {
            inputHtml = `
        <input type="text" id="${codecFieldId}" class="${inputClasses}"
               value="${optValue}"
               onchange="updateCodecField('${containerId}', '${fieldId}', '${codecName}', '${optKey}', this.value)">
      `;
        }

        fieldDiv.innerHTML = `
      <label for="${codecFieldId}" class="block text-xs font-medium text-gray-300 mb-1">
        ${optKey}
        <span class="text-xs font-normal text-gray-400">
          (${optInfo.required || 'No'})
        </span>
      </label>
      ${optInfo.description ? `<p class="text-xs text-gray-400 mb-1">${optInfo.description}</p>` : ''}
      ${inputHtml}
    `;

        codecConfigContainer.appendChild(fieldDiv);
    });

    // Initialize with empty config for the selected codec
    const currentValue = {[codecName]: existingConfig};
    hiddenField.value = JSON.stringify(currentValue);
};

window.updateCodecField = function (containerId, fieldId, codecName, optKey, value) {
    const hiddenField = document.getElementById(fieldId);
    if (!hiddenField) return;

    try {
        const currentValue = JSON.parse(hiddenField.value);

        // Ensure codec object exists
        if (!currentValue[codecName]) {
            currentValue[codecName] = {};
        }

        // Update or remove the field
        if (value === '' || value === null || value === undefined) {
            delete currentValue[codecName][optKey];
        } else {
            // Handle boolean conversion
            if (value === 'true') value = true;
            else if (value === 'false') value = false;
            // Handle number conversion
            else if (!isNaN(value) && value !== '') value = Number(value);

            currentValue[codecName][optKey] = value;
        }

        hiddenField.value = JSON.stringify(currentValue);
    } catch (e) {
        console.error('Error updating codec field:', e);
    }
};

// Make it globally available
window.PluginConfigModal = PluginConfigModal;

// Initialize when the document is ready
function initializePluginConfigModal() {
    // No need to initialize here as we'll do it from pipeline_editor.html
}

// Make sure the modal is available globally
window.showConfigModal = function (component) {
    if (typeof PluginConfigModal !== 'undefined') {
        PluginConfigModal.show(component);
    }
};

// Toggle password visibility function
window.togglePasswordVisibility = function(fieldId, button) {
    const input = document.getElementById(fieldId);
    if (!input) return;
    
    if (input.type === 'password') {
        input.type = 'text';
        // Change icon to eye-slash (hidden)
        button.innerHTML = `
            <svg class="w-5 h-5 eye-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
            </svg>
        `;
    } else {
        input.type = 'password';
        // Change icon back to eye (visible)
        button.innerHTML = `
            <svg class="w-5 h-5 eye-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
        `;
    }
};

// Browse file path function for fs_path input type
window.browseFilePath = function(fieldId) {
    const targetInput = document.getElementById(fieldId);
    if (!targetInput) return;
    
    // Create a hidden file input element
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.style.display = 'none';
    
    // Handle file selection
    fileInput.addEventListener('change', function(e) {
        if (e.target.files && e.target.files.length > 0) {
            const file = e.target.files[0];
            // Get the file path (webkitRelativePath or name)
            // Note: For security reasons, browsers don't expose the full file system path
            // We'll use the file name as a placeholder
            const filePath = file.webkitRelativePath || file.name;
            targetInput.value = filePath;
        }
        // Clean up the temporary file input
        document.body.removeChild(fileInput);
    });
    
    // Add to DOM and trigger click
    document.body.appendChild(fileInput);
    fileInput.click();
};

// Initialize when the DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializePluginConfigModal);
} else {
    initializePluginConfigModal();
}