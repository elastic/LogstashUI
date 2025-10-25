// Plugin Configuration Modal Controller
window.PluginConfigModal = (function () {
    let currentComponent = null;
    let pluginData = {};

    // Initialize the modal with plugin data
    function init(data) {
        pluginData = data;
    }

    // Show the configuration modal for a component
    function show(component) {
        currentComponent = component;
        const modal = document.getElementById('configModal');
        const configForm = document.getElementById('configForm');
        const pluginInfo = pluginData[component.type]?.[component.plugin] || {};

        // Set modal title with plugin type badge
        modal.querySelector('h3').innerHTML = `
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

            // Sort each group alphabetically
            importantOptions.sort((a, b) => a[0].localeCompare(b[0]));
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
                } else if (inputType.includes('boolean') || inputType === 'bool') {
                    inputField = `
            <select id="${fieldId}" name="${key}" class="${inputClasses}">
              <option value="true" ${value === true || value === 'true' ? 'selected' : ''}>true</option>
              <option value="false" ${value === false || value === 'false' ? 'selected' : ''}>false</option>
              <option value="" ${value === '' ? 'selected' : ''}></option>
            </select>
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
            <div id="${containerId}" class="space-y-2">
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
                        class="px-3 py-2 bg-red-600 text-white rounded hover:bg-red-700 text-sm"
                        onclick="removeHashPair('${containerId}', this)">
                  Remove
                </button>
              </div>
              <button type="button"
                      class="mt-2 px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm"
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
            <div id="${containerId}" class="space-y-2">
              <div class="flex items-center space-x-2">
                <input type="text"
                       class="flex-1 p-2 bg-gray-700 border border-gray-600 rounded text-white"
                       placeholder="Value"
                       onchange="updateArrayItem('${containerId}', '${fieldId}', this, 0)">
                <button type="button"
                        class="px-3 py-2 bg-red-600 text-white rounded hover:bg-red-700 text-sm"
                        onclick="removeArrayItem('${containerId}', this)">
                  Remove
                </button>
              </div>
              <button type="button"
                      class="mt-2 px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm"
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
                    if (content.classList.contains('hidden')) {
                        content.classList.remove('hidden');
                        icon.textContent = '▼';
                    } else {
                        content.classList.add('hidden');
                        icon.textContent = '▶';
                    }
                };
                
                advancedHeader.innerHTML = `
                    <h4 class="text-sm font-semibold text-gray-300">Advanced Settings</h4>
                    <span class="toggle-icon text-gray-400 text-xs">▶</span>
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
                    } else if (inputType.includes('boolean') || inputType === 'bool') {
                        inputField = `
            <select id="${fieldId}" name="${key}" class="${inputClasses}">
              <option value="true" ${value === true || value === 'true' ? 'selected' : ''}>true</option>
              <option value="false" ${value === false || value === 'false' ? 'selected' : ''}>false</option>
              <option value="" ${value === '' ? 'selected' : ''}></option>
            </select>
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
            <div id="${containerId}" class="space-y-2">
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
                        class="px-3 py-2 bg-red-600 text-white rounded hover:bg-red-700 text-sm"
                        onclick="removeHashPair('${containerId}', this)">
                  Remove
                </button>
              </div>
              <button type="button"
                      class="mt-2 px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm"
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
            <div id="${containerId}" class="space-y-2">
              <div class="flex items-center space-x-2">
                <input type="text"
                       class="flex-1 p-2 bg-gray-700 border border-gray-600 rounded text-white"
                       placeholder="Value"
                       onchange="updateArrayItem('${containerId}', '${fieldId}', this, 0)">
                <button type="button"
                        class="px-3 py-2 bg-red-600 text-white rounded hover:bg-red-700 text-sm"
                        onclick="removeArrayItem('${containerId}', this)">
                  Remove
                </button>
              </div>
              <button type="button"
                      class="mt-2 px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm"
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

        // Add save and cancel buttons
        const actions = document.createElement('div');
        actions.className = 'flex justify-end space-x-2 mt-6 pt-4 border-t border-gray-700';
        actions.innerHTML = `
      <button type="button" onclick="PluginConfigModal.hide()"
              class="px-4 py-2 text-sm font-medium text-gray-300 bg-gray-700 rounded hover:bg-gray-600">
        Cancel
      </button>
      <button type="button" onclick="PluginConfigModal.saveConfig()"
              class="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded hover:bg-blue-700">
        Save Configuration
      </button>
    `;
        configForm.appendChild(actions);

        // Show the modal
        modal.classList.remove('hidden');

        // Populate existing hash, array, and codec values after rendering
        setTimeout(() => {
            populateExistingValues(component);
            populateCodecValues(component);
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
                      class="px-3 py-2 bg-red-600 text-white rounded hover:bg-red-700 text-sm"
                      onclick="removeHashPair('${container.id}', this)">
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
                      class="px-3 py-2 bg-red-600 text-white rounded hover:bg-red-700 text-sm"
                      onclick="removeArrayItem('${container.id}', this)">
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

        // Trigger pending animation if there is one
        if (typeof window.triggerPendingAnimation === 'function') {
            window.triggerPendingAnimation();
        }
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
                } else if (fieldType === 'hash' || fieldType === 'array') {
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
            } else if (fieldType === 'hash' || fieldType === 'object') {
                const hiddenInput = fieldGroup.querySelector('input[type="hidden"]');
                if (hiddenInput) {
                    try {
                        const value = JSON.parse(hiddenInput.value);
                        isEmpty = Object.keys(value).length === 0;
                    } catch (e) {
                        isEmpty = true;
                    }
                }
            } else if (fieldType === 'array' || fieldType === 'list') {
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

    // Helper function to escape HTML
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

    // Public API
    return {
        init,
        show,
        hide,
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
            class="px-3 py-2 bg-red-600 text-white rounded hover:bg-red-700 text-sm"
            onclick="removeHashPair('${containerId}', this)">
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
            class="px-3 py-2 bg-red-600 text-white rounded hover:bg-red-700 text-sm"
            onclick="removeArrayItem('${containerId}', this)">
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

// Initialize when the DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializePluginConfigModal);
} else {
    initializePluginConfigModal();
}