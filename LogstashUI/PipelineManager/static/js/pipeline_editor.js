// Track newly added plugin IDs for animation
let newlyAddedPluginId = null;
let pendingAnimationPluginId = null; // Plugin waiting for config modal to close

// Note: moveMode is now defined in move_mode.js as window.moveMode

function createInsertionPoint(type, index = 0, isConditional = false, parentId = null) {
    const insertionPoint = document.createElement('div');
    insertionPoint.className = 'insertion-point';

    const buttons = document.createElement('div');
    buttons.className = 'insertion-buttons';

    // Always show Add Plugin button
    const addPluginBtn = document.createElement('button');
    addPluginBtn.className = 'insertion-button add-plugin';
    addPluginBtn.innerHTML = `
        <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
        </svg>
        Add Plugin
    `;
    addPluginBtn.onclick = (e) => {
        e.stopPropagation();
        // Handle adding a new plugin at this position
        showPluginModal(type, index, isConditional, parentId);
    };

    buttons.appendChild(addPluginBtn);

    // Show Add Condition button for filter and output sections, or inside conditionals
    if ((type === 'filter' || type === 'output' || isConditional) && !parentId) {
        const addConditionBtn = document.createElement('button');
        addConditionBtn.className = 'insertion-button add-condition';
        addConditionBtn.innerHTML = `
            <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
            </svg>
            Add Condition
        `;
        addConditionBtn.onclick = (e) => {
            e.stopPropagation();
            // Handle adding a new condition at this position
            addConditionAtPosition(type, index, isConditional, parentId);
        };
        buttons.appendChild(addConditionBtn);
    }

    insertionPoint.appendChild(buttons);
    return insertionPoint;
}

function setupInsertionPoints(container, type, isConditional = false, parentId = null) {
    // Get only the draggable components (not empty messages)
    const components = Array.from(container.children).filter(el => el.classList.contains('draggable-item'));

    if (components.length > 0) {
        // Add insertion point at the beginning
        container.insertBefore(createInsertionPoint(type, 0, isConditional, parentId), container.firstChild);

        // Add insertion points between components (but NOT after the last one)
        components.forEach((component, index) => {
            // Only add insertion point if it's not after the last component
            if (index < components.length - 1) {
                const insertionPoint = createInsertionPoint(type, index + 1, isConditional, parentId);
                container.insertBefore(insertionPoint, component.nextSibling);
            }
        });

        // Add a final insertion point at the end that's always visible
        const finalInsertionPoint = createInsertionPoint(type, components.length, isConditional, parentId);
        finalInsertionPoint.classList.add('always-visible');
        container.appendChild(finalInsertionPoint);
    } else {
        // Empty section - add a single always-visible insertion point
        const emptyInsertionPoint = createInsertionPoint(type, 0, isConditional, parentId);
        emptyInsertionPoint.classList.add('always-visible');
        container.appendChild(emptyInsertionPoint);
    }
}

// Setup insertion points for conditional blocks (if, else-if, else)
function setupInsertionPointsForConditional(container, type, conditionalId, blockType, elseIfIndex) {
    // Create a special insertion point creator for conditionals
    const createConditionalInsertionPoint = (index, alwaysVisible = false) => {
        const insertionPoint = document.createElement('div');
        insertionPoint.className = 'insertion-point';
        if (alwaysVisible) {
            insertionPoint.classList.add('always-visible');
        }

        const buttons = document.createElement('div');
        buttons.className = 'insertion-buttons';

        // Add Plugin button
        const addPluginBtn = document.createElement('button');
        addPluginBtn.className = 'insertion-button add-plugin';
        addPluginBtn.innerHTML = `
            <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
            </svg>
            Add Plugin
        `;
        addPluginBtn.onclick = (e) => {
            e.stopPropagation();
            showPluginModalForConditional(type, conditionalId, blockType, index, elseIfIndex);
        };
        buttons.appendChild(addPluginBtn);

        // Add Condition button (for filter and output types)
        if (type === 'filter' || type === 'output') {
            const addConditionBtn = document.createElement('button');
            addConditionBtn.className = 'insertion-button add-condition';
            addConditionBtn.innerHTML = `
                <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                </svg>
                Add Condition
            `;
            addConditionBtn.onclick = (e) => {
                e.stopPropagation();
                addConditionToConditional(type, conditionalId, blockType, index, elseIfIndex);
            };
            buttons.appendChild(addConditionBtn);
        }

        insertionPoint.appendChild(buttons);
        return insertionPoint;
    };

    // Get only the draggable plugin elements (not empty messages or other elements)
    const pluginElements = Array.from(container.children).filter(el => el.classList.contains('draggable-item'));

    if (pluginElements.length > 0) {
        // Add insertion point at the beginning
        container.insertBefore(createConditionalInsertionPoint(0), container.firstChild);

        // Add insertion points between components
        pluginElements.forEach((plugin, index) => {
            const insertionPoint = createConditionalInsertionPoint(index + 1);
            container.insertBefore(insertionPoint, plugin.nextSibling);
        });
    } else {
        // Empty conditional block - add an always-visible insertion point
        const emptyInsertionPoint = createConditionalInsertionPoint(0, true);
        container.appendChild(emptyInsertionPoint);
    }
}

function loadExistingComponents() {
    // Check if we're in simulation mode before clearing
    const wasInSimulationMode = document.querySelector('.simulation-executed-badge') !== null;
    const simulationNodes = wasInSimulationMode && window.simulationData ? window.simulationData.nodes : null;
    const originalEventData = wasInSimulationMode && window.simulationResultsCache ? 
        Object.values(window.simulationResultsCache)[0]?.originalEvent : null;
    
    // Clears all existing components first
    const componentTypes = ['input', 'filter', 'output'];

    // Clear containers
    componentTypes.forEach(type => {
        const container = document.getElementById(`${type}Components`);
        if (container) {
            // Remove all existing components but keep the empty message and insertion points
            const emptyMessage = container.querySelector('p');
            container.innerHTML = '';

            // Add empty section class if no components
            if (!components[type] || components[type].length === 0) {
                container.classList.add('empty-section');
                if (emptyMessage && emptyMessage.textContent.includes('No ')) {
                    container.appendChild(emptyMessage);
                }
            } else {
                container.classList.remove('empty-section');
            }
        }
    });

    // Add all components
    Object.entries(components).forEach(([type, componentList]) => {
        const container = document.getElementById(`${type}Components`);
        if (!container) return;

        // Remove 'No components' message if it exists
        const emptyMessage = container.querySelector('p');
        if (emptyMessage && emptyMessage.textContent.includes('No ')) {
            container.removeChild(emptyMessage);
        }

        // Add each component to the UI
        componentList.forEach((component, index) => {
            const componentEl = createComponentElement(component);
            container.appendChild(componentEl);
        });

        // Setup insertion points for this container
        setupInsertionPoints(container, type);
    });

    // Apply animation and focus to newly added plugin (only if not pending config modal)
    // Don't clear newlyAddedPluginId if there's a pending animation
    if (newlyAddedPluginId && !pendingAnimationPluginId) {
        highlightAndFocusNewPlugin(newlyAddedPluginId);
        newlyAddedPluginId = null; // Reset after use
    } else if (pendingAnimationPluginId && !newlyAddedPluginId) {
        // If we only have a pending ID, preserve it
        newlyAddedPluginId = pendingAnimationPluginId;
    }
    
    // Restore simulation data if we were in simulation mode
    if (wasInSimulationMode && simulationNodes && typeof markExecutedPlugins === 'function') {
        markExecutedPlugins(simulationNodes, originalEventData);
    }
}

// Function to trigger animation for pending plugin (called after config modal closes)
window.triggerPendingAnimation = function () {
    if (pendingAnimationPluginId) {
        highlightAndFocusNewPlugin(pendingAnimationPluginId);
        pendingAnimationPluginId = null;
        newlyAddedPluginId = null;
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

// Helper function to format config values for display
function formatConfigValue(value, key) {
    // Helper to clean up string values
    const cleanString = (str) => {
        // Remove surrounding quotes if they exist
        if (typeof str === 'string') {
            return str.replace(/^"|"$/g, '');
        }
        return String(str);
    };

    // Check if this is a sensitive field - redact the value
    if (isSensitiveField(key)) {
        const valueStr = String(value);
        if (valueStr && valueStr.length > 0) {
            return '••••••••';
        }
        return '';
    }

    // Handle codec specially FIRST - it's a nested object like {"rubydebug": {}}
    if (key === 'codec' && typeof value === 'object' && value !== null && !Array.isArray(value)) {
        const codecNames = Object.keys(value);
        if (codecNames.length > 0) {
            const codecName = codecNames[0];
            const codecConfig = value[codecName];

            // If codec has no config, just show the name
            if (!codecConfig || Object.keys(codecConfig).length === 0) {
                return `"${codecName}"`;
            }

            // If codec has config, show name with config summary
            const configCount = Object.keys(codecConfig).length;
            return `"${codecName}" (${configCount} setting${configCount > 1 ? 's' : ''})`;
        }
        return '{}';
    }

    // Handle arrays/lists
    if (Array.isArray(value)) {
        if (value.length === 0) {
            return '[]';
        }
        
        // Check if this is an array of objects (array_of_hashes)
        const firstItem = value[0];
        if (typeof firstItem === 'object' && firstItem !== null && !Array.isArray(firstItem)) {
            // This is an array of hashes - show count instead of content
            return `[${value.length} ${value.length === 1 ? 'entry' : 'entries'}]`;
        }
        
        // Format as: "item1", "item2", "item3"
        const formattedItems = value.map(item => {
            return `"${cleanString(item)}"`;
        });
        const joined = formattedItems.join(', ');
        // Truncate if too long
        if (joined.length > 50) {
            return joined.substring(0, 50) + '...';
        }
        return joined;
    }

    // Handle objects/hashes/dictionaries
    if (typeof value === 'object' && value !== null) {
        const entries = Object.entries(value);
        if (entries.length === 0) {
            return '{}';
        }
        // Format as: "key1" => "value1", "key2" => "value2"
        const formattedPairs = entries.map(([k, v]) => {
            // Skip nested objects - just show the key
            if (typeof v === 'object' && v !== null) {
                return `"${cleanString(k)}" => {...}`;
            }
            return `"${cleanString(k)}" => "${cleanString(v)}"`;
        });
        const joined = formattedPairs.join(', ');
        // Truncate if too long
        if (joined.length > 50) {
            return joined.substring(0, 50) + '...';
        }
        return joined;
    }

    // Handle strings and other primitives
    const cleanedValue = cleanString(value);
    if (cleanedValue.length > 30) {
        return cleanedValue.substring(0, 30) + '...';
    }
    return cleanedValue;
}

function createComponentElement(component, depth = 0, isConditional = false, parentId = null) {
// Check if this is a conditional block
    if (component.plugin === 'if') {
        return createConditionalBlockElement(component, depth);
    }

// Alternate background colors based on depth
    const bgColor = depth % 2 === 0 ? 'bg-gray-700' : 'bg-gray-600';
    const el = document.createElement('div');
    el.className = `${bgColor} p-3 rounded mb-2 relative group draggable-item`;
    el.dataset.id = component.id;

// Get plugin info for description and type
    const pluginInfo = pluginData[component.type]?.[component.plugin] || {};
    const typeColor = getPluginTypeColor(component.type);

// Create a summary of the configuration
    let configSummary = '';
    if (Object.keys(component.config).length > 0) {
        const configItems = [];
        for (const [key, value] of Object.entries(component.config)) {
            if (value !== undefined && value !== null && value !== '' && key !== 'plugins' && key !== 'else_ifs' && key !== 'else' && key !== 'condition') {
                let displayValue = formatConfigValue(value, key);
                
                // Add eye icon for sensitive fields
                if (isSensitiveField(key)) {
                    const actualValue = String(value).length > 30 ? String(value).substring(0, 30) + '...' : String(value);
                    const escapedActualValue = actualValue.replace(/'/g, "\\'").replace(/"/g, '&quot;');
                    configItems.push(`
                        <span class="text-xs bg-gray-800/50 px-2 py-0.5 rounded inline-flex items-center gap-1">
                            ${key}: <span class="sensitive-value" data-actual="${escapedActualValue}">${displayValue}</span>
                            <button type="button" 
                                    class="text-gray-400 hover:text-gray-200 inline-flex items-center"
                                    onclick="toggleSensitiveValue(this, event)"
                                    title="Show/Hide">
                                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                                </svg>
                            </button>
                        </span>
                    `);
                } else {
                    configItems.push(`<span class="text-xs bg-gray-800/50 px-2 py-0.5 rounded">${key}: ${displayValue}</span>`);
                }
            }
        }
        if (configItems.length > 0) {
            configSummary = `<div class="mt-2 flex flex-wrap gap-1">${configItems.join('')}</div>`;
        }
    }

    // Only show image for input and output plugins
    const imageHtml = (component.type === 'input' || component.type === 'output') 
        ? `<img src="/static/images/${component.plugin}.png" 
                alt="${component.plugin} icon" 
                class="w-5 h-5 mr-2 object-contain flex-shrink-0"
                onerror="this.style.display='none';">`
        : '';

    el.innerHTML = `
<button class="move-handle" data-component-id="${component.id}" title="Click to move this component">
  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8h16M4 16h16" />
  </svg>
</button>
<div class="flex justify-between items-start">
  <div class="flex-1">
    <div class="flex items-center">
      ${imageHtml}
      <span class="font-medium text-white">${component.plugin}</span>
      <span class="ml-2 px-1.5 py-0.5 text-xs rounded-full ${typeColor}">
        ${component.type.charAt(0).toUpperCase() + component.type.slice(1)}
      </span>
      ${pluginInfo.deprecated ?
        '<span class="ml-1 px-1.5 py-0.5 text-xs rounded-full bg-red-600/50 text-red-100">Deprecated</span>' : ''}
    </div>
    ${pluginInfo.description ?
        `<p class="text-xs text-gray-400 mt-1 line-clamp-2">${pluginInfo.description}</p>` : ''}
    ${configSummary}
  </div>
  <div class="flex space-x-1 ml-2">
    <button class="config-btn text-gray-400 hover:text-white opacity-0 group-hover:opacity-100 transition-opacity"
            data-component-id="${component.id}"
            title="Configure">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    </button>
    <button class="text-gray-400 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
            onclick="event.stopPropagation(); removeComponent('${component.id}')"
            title="Remove">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
      </svg>
    </button>
  </div>
</div>
`;

    return el;
}

// Function to highlight and focus on a newly added plugin
function highlightAndFocusNewPlugin(pluginId) {
    // Use setTimeout to ensure DOM is fully rendered
    setTimeout(() => {
        const pluginElement = document.querySelector(`[data-id="${pluginId}"]`);
        if (pluginElement) {
            // Add the animation class
            pluginElement.classList.add('newly-added');

            // Scroll to the element smoothly
            pluginElement.scrollIntoView({
                behavior: 'smooth',
                block: 'center'
            });

            // Remove the class after animation completes
            setTimeout(() => {
                pluginElement.classList.remove('newly-added');
            }, 2000);
        }
    }, 100);
}

function createConditionalBlockElement(component, depth = 0) {
// Alternate background colors based on depth
    const bgColor = depth % 2 === 0 ? 'bg-gray-700' : 'bg-gray-600';
    const el = document.createElement('div');
    el.className = `${bgColor} p-3 rounded mb-2 relative group draggable-item`;
    el.dataset.id = component.id;

    const typeColor = getPluginTypeColor(component.type);

// Create the container with border
    const container = document.createElement('div');
    container.className = 'border-l-4 border-yellow-500 pl-3';

// Create move handle for conditional block
    const moveHandle = document.createElement('button');
    moveHandle.className = 'move-handle';
    moveHandle.setAttribute('data-component-id', component.id);
    moveHandle.title = 'Click to move this condition';
    moveHandle.innerHTML = `
  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8h16M4 16h16" />
  </svg>
`;
    el.appendChild(moveHandle);

// Create header section
    const header = document.createElement('div');
    header.className = 'flex justify-between items-start mb-2';

    const headerLeft = document.createElement('div');
    headerLeft.className = 'flex-1';
    headerLeft.innerHTML = `
<div class="flex items-center">
  <button class="collapse-toggle mr-2 text-yellow-300 hover:text-yellow-400 transition-colors" data-component-id="${component.id}" title="Collapse/Expand">
    <svg class="w-4 h-4 transform transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
    </svg>
  </button>
  <span class="font-medium text-yellow-300">if</span>
  <div class="flex items-center ml-2 group/condition">
    <span class="text-xs text-gray-400 condition-text">${component.config.condition || ''}</span>
    <button class="ml-1 text-gray-500 hover:text-yellow-400 opacity-0 group-hover:opacity-100 transition-opacity edit-condition" 
            data-component-id="${component.id}">
      <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
      </svg>
    </button>
  </div>
  <span class="ml-2 px-1.5 py-0.5 text-xs rounded-full ${typeColor}">
    ${component.type.charAt(0).toUpperCase() + component.type.slice(1)}
  </span>
</div>
`;
    header.appendChild(headerLeft);

// Create button container
    const buttonContainer = document.createElement('div');
    buttonContainer.className = 'flex space-x-2 ml-2 opacity-0 group-hover:opacity-100 transition-opacity';

// Add else-if button with text
    const addElseIfBtn = document.createElement('button');
    addElseIfBtn.className = 'px-2 py-1 text-xs bg-yellow-600/80 text-white rounded hover:bg-yellow-600';
    addElseIfBtn.textContent = '+ else if';
    addElseIfBtn.setAttribute('data-action', 'add-elseif');
    addElseIfBtn.setAttribute('data-component-id', component.id);
    buttonContainer.appendChild(addElseIfBtn);

// Add else button (only if else block doesn't exist)
    if (!component.config.else) {
        const addElseBtn = document.createElement('button');
        addElseBtn.className = 'px-2 py-1 text-xs bg-yellow-600/80 text-white rounded hover:bg-yellow-600';
        addElseBtn.textContent = '+ else';
        addElseBtn.setAttribute('data-action', 'add-else');
        addElseBtn.setAttribute('data-component-id', component.id);
        buttonContainer.appendChild(addElseBtn);
    }

// Add delete button
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'text-gray-400 hover:text-red-400';
    deleteBtn.title = 'Remove';
    deleteBtn.innerHTML = `
<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
</svg>
`;
    deleteBtn.onclick = (e) => {
        e.stopPropagation();
        removeComponent(component.id);
    };
    buttonContainer.appendChild(deleteBtn);

    header.appendChild(buttonContainer);
    container.appendChild(header);

// Create collapsible content wrapper
    const collapsibleContent = document.createElement('div');
    collapsibleContent.className = 'conditional-content';
    collapsibleContent.dataset.componentId = component.id;

// Create if block plugins container with add button
    const ifPluginsContainer = document.createElement('div');
    ifPluginsContainer.className = 'ml-4 space-y-2 component-container';
    ifPluginsContainer.dataset.conditionalId = component.id;
    ifPluginsContainer.dataset.blockType = 'if';

    if (component.config.plugins && component.config.plugins.length > 0) {
        component.config.plugins.forEach(plugin => {
            const pluginEl = createComponentElement(plugin, depth + 1, true, component.id);
            ifPluginsContainer.appendChild(pluginEl);
        });
    } else {
        const emptyMsg = document.createElement('p');
        emptyMsg.className = 'text-gray-500 text-sm py-2';
        emptyMsg.textContent = 'No plugins in if block';
        ifPluginsContainer.appendChild(emptyMsg);
    }

    // Setup insertion points for this conditional block
    setupInsertionPointsForConditional(ifPluginsContainer, component.type, component.id, 'if', null);

    collapsibleContent.appendChild(ifPluginsContainer);

// Render else-if blocks
    if (component.config.else_ifs && component.config.else_ifs.length > 0) {
        component.config.else_ifs.forEach((elseIf, index) => {
            const elseIfIndex = index; // Capture the index in a local constant
            const elseIfBlock = document.createElement('div');
            elseIfBlock.className = 'mt-2';

            const conditionId = `condition-${component.id}-${elseIfIndex}`;
            const elseIfHeader = document.createElement('div');
            elseIfHeader.className = 'flex items-center justify-between group-elseif-condition';
            elseIfHeader.innerHTML = `
    <div class="flex items-center">
      <span class="font-medium text-yellow-300">else if</span>
      <div class="flex items-center ml-2">
        <span id="${conditionId}" class="text-xs text-gray-400 condition-text">${elseIf.condition || ''}</span>
        <button class="ml-1 text-gray-500 hover:text-yellow-400 opacity-0 group-hover:opacity-100 transition-opacity edit-elseif-condition" 
                data-component-id="${component.id}" 
                data-elseif-index="${elseIfIndex}"
                data-condition-id="${conditionId}">
          <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
          </svg>
        </button>
      </div>
    </div>
    <button class="text-gray-400 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity delete-elseif-btn" 
            data-component-id="${component.id}" 
            data-elseif-index="${elseIfIndex}"
            title="Remove else-if block">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
      </svg>
    </button>
  `;
            elseIfBlock.appendChild(elseIfHeader);

            const elseIfPluginsContainer = document.createElement('div');
            elseIfPluginsContainer.className = 'ml-4 space-y-2 mt-2 component-container';
            elseIfPluginsContainer.dataset.conditionalId = component.id;
            elseIfPluginsContainer.dataset.blockType = 'else_if';
            elseIfPluginsContainer.dataset.elseIfIndex = elseIfIndex;

            if (elseIf.plugins && elseIf.plugins.length > 0) {
                elseIf.plugins.forEach(plugin => {
                    const pluginEl = createComponentElement(plugin, depth + 1, true, component.id);
                    elseIfPluginsContainer.appendChild(pluginEl);
                });
            } else {
                const emptyMsg = document.createElement('p');
                emptyMsg.className = 'text-gray-500 text-sm py-2';
                emptyMsg.textContent = 'No plugins in else-if block';
                elseIfPluginsContainer.appendChild(emptyMsg);
            }

            // Setup insertion points for this else-if block
            setupInsertionPointsForConditional(elseIfPluginsContainer, component.type, component.id, 'else_if', elseIfIndex);

            elseIfBlock.appendChild(elseIfPluginsContainer);
            collapsibleContent.appendChild(elseIfBlock);
        });
    }

// Render else block (if it exists)
    if (component.config.else) {
        const elseBlock = document.createElement('div');
        elseBlock.className = 'mt-2';

        const elseHeader = document.createElement('div');
        elseHeader.className = 'flex items-center justify-between group';
        elseHeader.innerHTML = `
    <span class="font-medium text-yellow-300">else</span>
    <button class="text-gray-400 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity delete-else-btn" 
            data-component-id="${component.id}"
            title="Remove else block">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
      </svg>
    </button>
  `;
        elseBlock.appendChild(elseHeader);

        const elsePluginsContainer = document.createElement('div');
        elsePluginsContainer.className = 'ml-4 space-y-2 mt-2 component-container';
        elsePluginsContainer.dataset.conditionalId = component.id;
        elsePluginsContainer.dataset.blockType = 'else';

        if (component.config.else.plugins && component.config.else.plugins.length > 0) {
            component.config.else.plugins.forEach(plugin => {
                const pluginEl = createComponentElement(plugin, depth + 1, true, component.id);
                elsePluginsContainer.appendChild(pluginEl);
            });
        } else {
            const emptyMsg = document.createElement('p');
            emptyMsg.className = 'text-gray-500 text-sm py-2';
            emptyMsg.textContent = 'No plugins in else block';
            elsePluginsContainer.appendChild(emptyMsg);
        }

        // Setup insertion points for this else block
        setupInsertionPointsForConditional(elsePluginsContainer, component.type, component.id, 'else', null);

        elseBlock.appendChild(elsePluginsContainer);
        collapsibleContent.appendChild(elseBlock);
    }

    container.appendChild(collapsibleContent);
    el.appendChild(container);
    return el;
}

// Helper function to get color based on plugin type
function getPluginTypeColor(type) {
    const colors = {
        input: 'bg-blue-900/50 text-blue-300',
        filter: 'bg-purple-900/50 text-purple-300',
        output: 'bg-green-900/50 text-green-300',
        codec: 'bg-yellow-900/50 text-yellow-300'
    };
    return colors[type] || 'bg-gray-700 text-gray-300';
}

// Function to update a component and refresh the UI
window.updateComponent = function (updatedComponent) {
    // Helper function to recursively update in nested conditionals
    function updateInConditional(component) {
        if (!component || component.plugin !== 'if' || !component.config) {
            return false;
        }

        // Check in if block
        if (component.config.plugins) {
            const index = component.config.plugins.findIndex(c => c.id === updatedComponent.id);
            if (index !== -1) {
                component.config.plugins[index] = {...updatedComponent};
                return true;
            }
            // Recursively search in nested conditionals
            for (const plugin of component.config.plugins) {
                if (updateInConditional(plugin)) {
                    return true;
                }
            }
        }

        // Check in else-if blocks
        if (component.config.else_ifs) {
            for (const elseIf of component.config.else_ifs) {
                if (elseIf.plugins) {
                    const index = elseIf.plugins.findIndex(c => c.id === updatedComponent.id);
                    if (index !== -1) {
                        elseIf.plugins[index] = {...updatedComponent};
                        return true;
                    }
                    // Recursively search in nested conditionals
                    for (const plugin of elseIf.plugins) {
                        if (updateInConditional(plugin)) {
                            return true;
                        }
                    }
                }
            }
        }

        // Check in else block
        if (component.config.else && component.config.else.plugins) {
            const index = component.config.else.plugins.findIndex(c => c.id === updatedComponent.id);
            if (index !== -1) {
                component.config.else.plugins[index] = {...updatedComponent};
                return true;
            }
            // Recursively search in nested conditionals
            for (const plugin of component.config.else.plugins) {
                if (updateInConditional(plugin)) {
                    return true;
                }
            }
        }

        return false;
    }

    // First, try to update at top-level
    for (const type in components) {
        const index = components[type].findIndex(c => c.id === updatedComponent.id);
        if (index !== -1) {
            // Update the component
            components[type][index] = {...updatedComponent};
            // Refresh the UI
            loadExistingComponents();
            return true;
        }
    }

    // If not found at top level, search recursively in nested conditionals
    for (const type in components) {
        for (const component of components[type]) {
            if (updateInConditional(component)) {
                // Refresh the UI
                loadExistingComponents();
                return true;
            }
        }
    }

    return false;
};

// Function to handle condition editing
function handleEditCondition(componentId) {
    const component = findComponentById(componentId);
    if (!component) return;

    const conditionElement = document.querySelector(`[data-id="${componentId}"] .condition-text`);
    if (!conditionElement) return;

    const currentCondition = component.config.condition || '';
    const input = document.createElement('input');
    input.type = 'text';
    input.value = currentCondition;
    input.className = 'text-xs text-white bg-gray-700 px-1 py-0.5 rounded w-full';

    // Save on Enter or blur, cancel on Escape
    const saveCondition = () => {
        const newCondition = input.value.trim();
        component.config.condition = newCondition;
        conditionElement.textContent = newCondition || ' '; // Keep space to maintain height
        updateComponent(component);
    };

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            input.blur();
        } else if (e.key === 'Escape') {
            conditionElement.textContent = currentCondition || ' ';
        }
    });

    input.addEventListener('blur', () => {
        saveCondition();
    });

    conditionElement.textContent = '';
    conditionElement.appendChild(input);
    input.focus();
}

// Function to handle else-if condition editing
function handleEditElseIfCondition(componentId, elseIfIndex, conditionId) {
    const component = findComponentById(componentId);
    if (!component || !component.config.else_ifs || !component.config.else_ifs[elseIfIndex]) return;

    const conditionText = component.config.else_ifs[elseIfIndex].condition || '';
    const conditionElement = document.getElementById(conditionId);

    if (!conditionElement) {
        console.error('Could not find condition element with ID:', conditionId);
        return;
    }

    const input = document.createElement('input');
    input.type = 'text';
    input.value = conditionText;
    input.className = 'text-xs text-white bg-gray-700 px-1 py-0.5 rounded w-full';

    // Save on Enter or blur, cancel on Escape
    const saveCondition = () => {
        const newCondition = input.value.trim();
        component.config.else_ifs[elseIfIndex].condition = newCondition;
        conditionElement.textContent = newCondition || ' '; // Keep space to maintain height
        updateComponent(component);
    };

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            input.blur();
        } else if (e.key === 'Escape') {
            conditionElement.textContent = conditionText || ' ';
            input.remove();
            conditionElement.textContent = conditionText || ' ';
        }
    });

    input.addEventListener('blur', () => {
        saveCondition();
    });

    conditionElement.textContent = '';
    conditionElement.appendChild(input);
    input.focus();
}

// Initialize the pipeline editor
// Function to handle adding a condition at a specific position
function addConditionAtPosition(type, index, isConditional = false, parentId = null) {
    // Create a new condition component
    const conditionId = `condition-${Date.now()}`;
    const newCondition = {
        id: conditionId,
        type: type,
        plugin: 'if',
        config: {
            condition: 'true',
            plugins: []
        }
    };

    // Track the newly added condition for animation
    newlyAddedPluginId = conditionId;

    // Add the condition to the appropriate location
    if (isConditional && parentId) {
        // Find the parent component and add the condition to its plugins
        const parentComponent = findComponentById(parentId);
        if (parentComponent) {
            if (!parentComponent.config.plugins) {
                parentComponent.config.plugins = [];
            }
            parentComponent.config.plugins.splice(index, 0, newCondition);
        }
    } else {
        // Add to the main components array
        if (!components[type]) {
            components[type] = [];
        }
        components[type].splice(index, 0, newCondition);
    }

    // Refresh the UI
    loadExistingComponents();
}

// Function to show the plugin modal at a specific position
function showPluginModal(type, index, isConditional = false, parentId = null) {
    // Store the position information in the modal
    const modal = document.getElementById('pluginModal');
    modal.dataset.type = type;
    modal.dataset.index = index;
    modal.dataset.isConditional = isConditional;
    modal.dataset.parentId = parentId || '';

    // Show the modal with proper rendering (just like Add Input/Filter/Output buttons)
    PluginModal.show(type);
}

// Function to show plugin modal for conditional blocks with insertion at specific position
function showPluginModalForConditional(type, conditionalId, blockType, index, elseIfIndex) {
    const modal = document.getElementById('pluginModal');

    // Create context for conditional insertion point
    const context = {
        conditionalInsertion: true,
        conditionalId: conditionalId,
        blockType: blockType,
        elseIfIndex: elseIfIndex,
        index: index,
        type: type
    };

    modal.dataset.context = JSON.stringify(context);
    PluginModal.show(type);
}

// Function to add a condition inside a conditional block at a specific position
function addConditionToConditional(type, conditionalId, blockType, index, elseIfIndex) {
    const parentComponent = findComponentById(conditionalId);
    if (!parentComponent) return;

    // Create a new nested condition
    const newCondition = {
        id: `condition-${Date.now()}`,
        type: type,
        plugin: 'if',
        config: {
            condition: 'true',
            plugins: []
        }
    };

    // Track the newly added condition for animation
    newlyAddedPluginId = newCondition.id;

    // Determine which plugin array to insert into
    let targetPlugins;
    switch (blockType) {
        case 'if':
            if (!parentComponent.config.plugins) parentComponent.config.plugins = [];
            targetPlugins = parentComponent.config.plugins;
            break;
        case 'else_if':
            if (!parentComponent.config.else_ifs || !parentComponent.config.else_ifs[elseIfIndex]) return;
            if (!parentComponent.config.else_ifs[elseIfIndex].plugins) {
                parentComponent.config.else_ifs[elseIfIndex].plugins = [];
            }
            targetPlugins = parentComponent.config.else_ifs[elseIfIndex].plugins;
            break;
        case 'else':
            if (!parentComponent.config.else) parentComponent.config.else = {plugins: []};
            if (!parentComponent.config.else.plugins) parentComponent.config.else.plugins = [];
            targetPlugins = parentComponent.config.else.plugins;
            break;
        default:
            return;
    }

    // Insert the condition at the specified index
    targetPlugins.splice(index, 0, newCondition);

    // Refresh the UI
    loadExistingComponents();
}

document.addEventListener('DOMContentLoaded', function () {
    // Add click handlers for the insertion buttons
    document.addEventListener('click', function (e) {
        // Handle add plugin button clicks
        if (e.target.closest('.add-plugin-btn')) {
            const type = e.target.closest('.add-plugin-btn').dataset.type;
            showPluginModal(type, components[type] ? components[type].length : 0);
        }
    });

    // Update the existing plugin modal handler to use the position information
    document.querySelectorAll('.plugin-option').forEach(option => {
        option.addEventListener('click', function () {
            const modal = document.getElementById('pluginModal');
            const type = modal.dataset.type;
            const index = parseInt(modal.dataset.index || '0');
            const isConditional = modal.dataset.isConditional === 'true';
            const parentId = modal.dataset.parentId || null;

            const pluginType = this.dataset.pluginType;

            // Create the new plugin
            const newPlugin = {
                id: `plugin-${Date.now()}`,
                type: type,
                plugin: pluginType,
                config: {}
            };

            // Track the newly added plugin for animation
            newlyAddedPluginId = newPlugin.id;

            // Add the plugin to the appropriate location
            if (isConditional && parentId) {
                // Find the parent component and add the plugin to its plugins
                const parentComponent = findComponentById(parentId);
                if (parentComponent) {
                    if (!parentComponent.config.plugins) {
                        parentComponent.config.plugins = [];
                    }
                    parentComponent.config.plugins.splice(index, 0, newPlugin);
                }
            } else {
                // Add to the main components array
                if (!components[type]) {
                    components[type] = [];
                }
                components[type].splice(index, 0, newPlugin);
            }

            // Hide the modal and refresh the UI
            modal.classList.add('hidden');
            loadExistingComponents();
        });
    });
    // Add event listener for edit condition buttons
    document.addEventListener('click', function (event) {
        // Handle if condition edit
        let editBtn = event.target.closest('.edit-condition') ||
            (event.target.closest('svg') && event.target.closest('svg').parentElement.closest('.edit-condition'));

        if (editBtn) {
            event.preventDefault();
            event.stopPropagation();
            const componentId = editBtn.getAttribute('data-component-id');
            if (componentId) {
                handleEditCondition(componentId);
            }
            return;
        }

        // Handle else-if condition edit
        editBtn = event.target.closest('.edit-elseif-condition') ||
            (event.target.closest('svg') && event.target.closest('svg').parentElement.closest('.edit-elseif-condition'));

        if (editBtn) {
            event.preventDefault();
            event.stopPropagation();
            const componentId = editBtn.getAttribute('data-component-id');
            const elseIfIndex = parseInt(editBtn.getAttribute('data-elseif-index'), 10);
            const conditionId = editBtn.getAttribute('data-condition-id');
            if (componentId && !isNaN(elseIfIndex) && conditionId) {
                handleEditElseIfCondition(componentId, elseIfIndex, conditionId);
            }
        }
    });

    if (typeof components !== 'undefined') {
        loadExistingComponents();
    }

    // Initialize PluginConfigModal with plugin data
    if (typeof window.PluginConfigModal !== 'undefined' && typeof pluginData !== 'undefined') {
        window.PluginConfigModal.init(pluginData);

        // Add click handler for config buttons
        document.addEventListener('click', function (event) {
            const configBtn = event.target.closest('.config-btn');
            if (configBtn) {
                const componentId = configBtn.closest('[data-component-id]').getAttribute('data-component-id');
                const component = findComponentById(componentId);
                if (component) {
                    event.preventDefault();
                    window.PluginConfigModal.show(component);
                }
            }
        });
    }

    // Add global event listener for conditional block buttons
    document.addEventListener('click', function (event) {
        const button = event.target.closest('[data-action]');
        if (!button) return;

        const action = button.getAttribute('data-action');
        const componentId = button.getAttribute('data-component-id');

        if (!componentId) return;

        event.stopPropagation();
        event.preventDefault();

        if (action === 'add-elseif') {
            addElseIfToConditional(componentId);
        } else if (action === 'add-else') {
            addElseToConditional(componentId);
        }
    });

    // Add event listener for delete else-if buttons
    document.addEventListener('click', function (event) {
        const deleteBtn = event.target.closest('.delete-elseif-btn');
        if (deleteBtn) {
            event.stopPropagation();
            event.preventDefault();
            
            const componentId = deleteBtn.getAttribute('data-component-id');
            const elseIfIndex = parseInt(deleteBtn.getAttribute('data-elseif-index'), 10);
            
            if (componentId && !isNaN(elseIfIndex)) {
                deleteElseIfBlock(componentId, elseIfIndex);
            }
        }
    });

    // Add event listener for delete else button
    document.addEventListener('click', function (event) {
        const deleteBtn = event.target.closest('.delete-else-btn');
        if (deleteBtn) {
            event.stopPropagation();
            event.preventDefault();
            
            const componentId = deleteBtn.getAttribute('data-component-id');
            
            if (componentId) {
                deleteElseBlock(componentId);
            }
        }
    });
});

// Helper function to find component by ID (recursive for nested conditionals)
function findComponentById(id) {
    if (!id || !components) return null;

    // Recursive search function
    function searchInComponent(component) {
        if (component.id === id) {
            return component;
        }

        // If this is a conditional, search inside it
        if (component.plugin === 'if' && component.config) {
            // Search in if block
            if (component.config.plugins) {
                for (const plugin of component.config.plugins) {
                    const found = searchInComponent(plugin);
                    if (found) return found;
                }
            }

            // Search in else-if blocks
            if (component.config.else_ifs) {
                for (const elseIf of component.config.else_ifs) {
                    if (elseIf.plugins) {
                        for (const plugin of elseIf.plugins) {
                            const found = searchInComponent(plugin);
                            if (found) return found;
                        }
                    }
                }
            }

            // Search in else block
            if (component.config.else && component.config.else.plugins) {
                for (const plugin of component.config.else.plugins) {
                    const found = searchInComponent(plugin);
                    if (found) return found;
                }
            }
        }

        return null;
    }

    // Search through all top-level components
    for (const type in components) {
        for (const component of components[type]) {
            const found = searchInComponent(component);
            if (found) return found;
        }
    }

    return null;
}

function removeComponent(componentId) {
    if (!confirm('Are you sure you want to remove this component?')) {
        return;
    }

    // Helper function to recursively remove from nested conditionals
    function removeFromConditional(component) {
        if (!component || component.plugin !== 'if' || !component.config) {
            return false;
        }

        // Check in if block
        if (component.config.plugins) {
            const index = component.config.plugins.findIndex(c => c.id === componentId);
            if (index > -1) {
                component.config.plugins.splice(index, 1);
                return true;
            }
            // Recursively search in nested conditionals
            for (const plugin of component.config.plugins) {
                if (removeFromConditional(plugin)) {
                    return true;
                }
            }
        }

        // Check in else-if blocks
        if (component.config.else_ifs) {
            for (const elseIf of component.config.else_ifs) {
                if (elseIf.plugins) {
                    const index = elseIf.plugins.findIndex(c => c.id === componentId);
                    if (index > -1) {
                        elseIf.plugins.splice(index, 1);
                        return true;
                    }
                    // Recursively search in nested conditionals
                    for (const plugin of elseIf.plugins) {
                        if (removeFromConditional(plugin)) {
                            return true;
                        }
                    }
                }
            }
        }

        // Check in else block
        if (component.config.else && component.config.else.plugins) {
            const index = component.config.else.plugins.findIndex(c => c.id === componentId);
            if (index > -1) {
                component.config.else.plugins.splice(index, 1);
                return true;
            }
            // Recursively search in nested conditionals
            for (const plugin of component.config.else.plugins) {
                if (removeFromConditional(plugin)) {
                    return true;
                }
            }
        }

        return false;
    }

    // First, try to remove from top-level components
    let removed = false;
    for (const type in components) {
        const index = components[type].findIndex(c => c.id === componentId);
        if (index > -1) {
            components[type].splice(index, 1);
            removed = true;
            break;
        }
    }

    // If not found at top level, search recursively in nested conditionals
    if (!removed) {
        for (const type in components) {
            for (const component of components[type]) {
                if (removeFromConditional(component)) {
                    removed = true;
                    break;
                }
            }
            if (removed) break;
        }
    }

    // Refresh the entire UI to reflect the changes
    if (removed) {
        loadExistingComponents();
    }
}

function addElseIfToConditional(componentId) {
// Find the conditional component
    const component = findComponentById(componentId);
    if (!component || component.plugin !== 'if') {
        console.error('Component not found or not a conditional:', componentId);
        return;
    }

// Prompt for condition
    const condition = prompt('Enter the else-if condition:', '[field] == "value"');
    if (!condition) {
        return;
    }

// Initialize else_ifs array if it doesn't exist
    if (!component.config.else_ifs) {
        component.config.else_ifs = [];
    }

// Add new else-if block
    const elseIfBlock = {
        condition: condition,
        plugins: []
    };

    const elseIfIndex = component.config.else_ifs.push(elseIfBlock) - 1;

// Store the context in the modal's dataset
    const modal = document.getElementById('pluginModal');
    modal.dataset.context = JSON.stringify({
        componentId,
        blockType: 'else_if',
        elseIfIndex
    });

// Show the plugin modal for the appropriate plugin type
    PluginModal.show(component.type || 'output');

// Add a one-time event listener for plugin selection
    const handlePluginSelect = function (event) {
        const {pluginName, pluginType} = event.detail;
        const context = JSON.parse(modal.dataset.context);

        // Find the component again to ensure we have the latest state
        const component = findComponentById(context.componentId);
        if (!component) return;

        // Ensure the else_ifs array and the specific else-if block exist
        if (!component.config.else_ifs || !component.config.else_ifs[context.elseIfIndex]) {
            console.error('Invalid else-if index or else_ifs not found');
            return;
        }

        if (!component.config.else_ifs[context.elseIfIndex].plugins) {
            component.config.else_ifs[context.elseIfIndex].plugins = [];
        }

        // Create the new plugin with default config
        const newPlugin = {
            id: `${pluginType}_${pluginName}_${Date.now()}`,
            type: pluginType,
            plugin: pluginName,
            config: {}
        };

        // Track the newly added plugin for animation
        newlyAddedPluginId = newPlugin.id;

        // Mark animation as pending until config modal closes (BEFORE loadExistingComponents)
        pendingAnimationPluginId = newlyAddedPluginId;

        // Add the plugin to the else-if block
        component.config.else_ifs[context.elseIfIndex].plugins.push(newPlugin);

        // Refresh the UI
        loadExistingComponents();

        // Show the config modal for the new plugin
        if (typeof window.PluginConfigModal !== 'undefined') {
            // Use a small timeout to ensure the UI is updated first
            setTimeout(() => {
                window.PluginConfigModal.show(newPlugin);
            }, 50);
        }

        // Remove the event listener after handling the selection
        document.removeEventListener('pluginSelected', handlePluginSelect);
    };

// Listen for the plugin selection event
    document.addEventListener('pluginSelected', handlePluginSelect);
}

function addPluginToConditional(componentId, blockType, elseIfIndex = null) {
    console.log(`addPluginToConditional called - componentId: ${componentId}, blockType: ${blockType}, elseIfIndex: ${elseIfIndex}`);

// Find the conditional component
    const component = findComponentById(componentId);
    if (!component || component.plugin !== 'if') {
        console.error('Component not found or not a conditional:', componentId);
        return;
    }

// Store the context for the plugin selection callback
    const context = {componentId, blockType, elseIfIndex};

// Store the context in the modal's dataset for later use
    const modal = document.getElementById('pluginModal');

// Clean up any existing context first
    if (modal.dataset.context) {
        delete modal.dataset.context;
    }

    modal.dataset.context = JSON.stringify(context);

// Show the plugin modal for the appropriate plugin type
    PluginModal.show(component.type || 'output');

// Add a one-time event listener for plugin selection
    const handlePluginSelect = function (event) {
        const {pluginName, pluginType} = event.detail;
        console.log(`Plugin selected: ${pluginType}.${pluginName} for block type: ${blockType}`);

// Make sure we have a valid context
        if (!modal.dataset.context) {
            console.error('No context found for plugin selection');
            return;
        }

        const context = JSON.parse(modal.dataset.context);

// Find the component again to ensure we have the latest state
        const component = findComponentById(context.componentId);
        if (!component) return;

// Determine the target plugin list based on block type
        let targetPlugins;
        switch (context.blockType) {
            case 'if':
                if (!component.config.plugins) component.config.plugins = [];
                targetPlugins = component.config.plugins;
                break;
            case 'else_if':
                if (!component.config.else_ifs || !component.config.else_ifs[context.elseIfIndex]) {
                    console.error('Invalid else-if index or else_ifs not found');
                    return;
                }
                if (!component.config.else_ifs[context.elseIfIndex].plugins) {
                    component.config.else_ifs[context.elseIfIndex].plugins = [];
                }
                targetPlugins = component.config.else_ifs[context.elseIfIndex].plugins;
                break;
            case 'else':
                if (!component.config.else) {
                    component.config.else = {plugins: []};
                } else if (!component.config.else.plugins) {
                    component.config.else.plugins = [];
                }
                targetPlugins = component.config.else.plugins;
                break;
            default:
                console.error('Invalid block type:', context.blockType);
                return;
        }

// Create the new plugin with default config
        const newPlugin = {
            id: `${pluginType}_${pluginName}_${Date.now()}`,
            type: pluginType,
            plugin: pluginName,
            config: {}
        };

        // Track the newly added plugin for animation
        newlyAddedPluginId = newPlugin.id;

        // Mark animation as pending until config modal closes (BEFORE loadExistingComponents)
        pendingAnimationPluginId = newlyAddedPluginId;

// Add the plugin to the appropriate block
        targetPlugins.push(newPlugin);

// Clean up the context
        if (modal.dataset.context) {
            delete modal.dataset.context;
        }

// Remove the event listener after handling the selection
        document.removeEventListener('pluginSelected', handlePluginSelect);

// Refresh the UI
        loadExistingComponents();

// Show the config modal for the new plugin
        if (typeof window.PluginConfigModal !== 'undefined') {
            // Use a small timeout to ensure the UI is updated first
            setTimeout(() => {
                window.PluginConfigModal.show(newPlugin);
            }, 50);
        }
    };

// Listen for the plugin selection event
    document.addEventListener('pluginSelected', handlePluginSelect);

// Set a timeout to clean up the listener if the modal is closed without selecting a plugin
    const cleanupTimer = setTimeout(() => {
        document.removeEventListener('pluginSelected', handlePluginSelect);
        if (modal.dataset.context) {
            delete modal.dataset.context;
        }
    }, 60000); // 60 second timeout

// Clean up the timer when the modal is closed
    const originalHide = PluginModal.hide;
    PluginModal.hide = function () {
        clearTimeout(cleanupTimer);
        document.removeEventListener('pluginSelected', handlePluginSelect);
        originalHide.call(PluginModal);
        PluginModal.hide = originalHide; // Restore original hide function
    };
}

function addElseToConditional(componentId) {
    console.log('addElseToConditional called with:', componentId);

// Find the conditional component
    const component = findComponentById(componentId);
    console.log('Found component:', component);

    if (!component || component.plugin !== 'if') {
        console.error('Component not found or not a conditional:', componentId);
        return;
    }

// Initialize the else block if it doesn't exist
    if (!component.config.else) {
        component.config.else = {plugins: []};
    } else if (!component.config.else.plugins) {
        component.config.else.plugins = [];
    }

// Store the context in the modal's dataset
    const modal = document.getElementById('pluginModal');

// Clean up any existing context first
    if (modal.dataset.context) {
        delete modal.dataset.context;
    }

    const context = {
        componentId,
        blockType: 'else',
        isNewElseBlock: true
    };

    modal.dataset.context = JSON.stringify(context);

// Show the plugin modal for the appropriate plugin type
    PluginModal.show(component.type || 'output');

// Add a one-time event listener for plugin selection
    const handlePluginSelect = function (event) {
        const {pluginName, pluginType} = event.detail;

// Make sure we have a valid context
        if (!modal.dataset.context) {
            console.error('No context found for plugin selection');
            return;
        }

        const context = JSON.parse(modal.dataset.context);

// Find the component again to ensure we have the latest state
        const component = findComponentById(context.componentId);
        if (!component) return;

// Ensure the else block exists
        if (!component.config.else) {
            component.config.else = {plugins: []};
        } else if (!component.config.else.plugins) {
            component.config.else.plugins = [];
        }

// Create the new plugin with default config
        const newPlugin = {
            id: `${pluginType}_${pluginName}_${Date.now()}`,
            type: pluginType,
            plugin: pluginName,
            config: {}
        };

        // Track the newly added plugin for animation
        newlyAddedPluginId = newPlugin.id;

        // Mark animation as pending until config modal closes (BEFORE loadExistingComponents)
        pendingAnimationPluginId = newlyAddedPluginId;

// Add the plugin to the else block
        component.config.else.plugins.push(newPlugin);

// Clean up the context
        if (modal.dataset.context) {
            delete modal.dataset.context;
        }

// Remove the event listener after handling the selection
        document.removeEventListener('pluginSelected', handlePluginSelect);

// Refresh the UI
        loadExistingComponents();

// Show the config modal for the new plugin
        if (typeof window.PluginConfigModal !== 'undefined') {
            // Use a small timeout to ensure the UI is updated first
            setTimeout(() => {
                window.PluginConfigModal.show(newPlugin);
            }, 50);
        }
    };

// Listen for the plugin selection event
    document.addEventListener('pluginSelected', handlePluginSelect);

// Set a timeout to clean up the listener if the modal is closed without selecting a plugin
    const cleanupTimer = setTimeout(() => {
        document.removeEventListener('pluginSelected', handlePluginSelect);
        if (modal.dataset.context) {
            delete modal.dataset.context;
        }
    }, 60000); // 60 second timeout

// Clean up the timer when the modal is closed
    const originalHide = PluginModal.hide;
    PluginModal.hide = function () {
        clearTimeout(cleanupTimer);
        document.removeEventListener('pluginSelected', handlePluginSelect);
        originalHide.call(PluginModal);
        PluginModal.hide = originalHide; // Restore original hide function
    };
}


// Function to delete an else-if block
function deleteElseIfBlock(componentId, elseIfIndex) {
    if (!confirm('Are you sure you want to remove this else-if block and all its plugins?')) {
        return;
    }

    const component = findComponentById(componentId);
    if (!component || component.plugin !== 'if') {
        console.error('Component not found or not a conditional:', componentId);
        return;
    }

    if (!component.config.else_ifs || !component.config.else_ifs[elseIfIndex]) {
        console.error('else-if block not found at index:', elseIfIndex);
        return;
    }

    // Remove the else-if block
    component.config.else_ifs.splice(elseIfIndex, 1);

    // Refresh the UI
    loadExistingComponents();
}

// Function to delete an else block
function deleteElseBlock(componentId) {
    if (!confirm('Are you sure you want to remove this else block and all its plugins?')) {
        return;
    }

    const component = findComponentById(componentId);
    if (!component || component.plugin !== 'if') {
        console.error('Component not found or not a conditional:', componentId);
        return;
    }

    if (!component.config.else) {
        console.error('else block not found');
        return;
    }

    // Remove the else block
    delete component.config.else;

    // Refresh the UI
    loadExistingComponents();
}

// Function to toggle collapse/expand of conditional blocks
document.addEventListener('click', function(e) {
    const collapseToggle = e.target.closest('.collapse-toggle');
    if (collapseToggle) {
        e.stopPropagation();
        const componentId = collapseToggle.dataset.componentId;
        const content = document.querySelector(`.conditional-content[data-component-id="${componentId}"]`);
        const svg = collapseToggle.querySelector('svg');
        
        if (content && svg) {
            const isCollapsed = content.classList.contains('collapsed');
            
            if (isCollapsed) {
                // Expand
                content.classList.remove('collapsed');
                svg.style.transform = 'rotate(0deg)';
            } else {
                // Collapse
                content.classList.add('collapsed');
                svg.style.transform = 'rotate(-90deg)';
            }
        }
    }
});

// Function to toggle sensitive value visibility in component row preview
window.toggleSensitiveValue = function(button, event) {
    event.stopPropagation();
    
    const valueSpan = button.previousElementSibling;
    if (!valueSpan || !valueSpan.classList.contains('sensitive-value')) return;
    
    const actualValue = valueSpan.dataset.actual;
    const currentText = valueSpan.textContent;
    
    if (currentText === '••••••••') {
        // Show actual value
        valueSpan.textContent = actualValue;
        // Change icon to eye-slash
        button.innerHTML = `
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
            </svg>
        `;
    } else {
        // Hide value
        valueSpan.textContent = '••••••••';
        // Change icon back to eye
        button.innerHTML = `
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
        `;
    }
};

// Function to open the simulation modal
window.openSimulateModal = function() {
    const modal = document.getElementById('simulationModal');
    if (modal) {
        modal.classList.remove('hidden');
    }
};
