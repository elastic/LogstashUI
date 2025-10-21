function loadExistingComponents() {
    // Clears all existing components first
    const componentTypes = ['input', 'filter', 'output'];

    // Clear containers
    componentTypes.forEach(type => {
        const container = document.getElementById(`${type}Components`);
        if (container) {
            const emptyMessage = container.querySelector('p');
            container.innerHTML = '';

            // Restore 'No components' message if needed
            if (emptyMessage && emptyMessage.textContent.includes('No ')) {
                if (!components[type] || components[type].length === 0) {
                    container.appendChild(emptyMessage);
                }
            }
        }
    });

    // Add all components
    Object.entries(components).forEach(([type, componentList]) => {
        const container = document.getElementById(`${type}Components`);
        if (!container) return;

        // Remove 'No components' message
        const emptyMessage = container.querySelector('p');
        if (emptyMessage && emptyMessage.textContent.includes('No ')) {
            container.removeChild(emptyMessage);
        }

        // Add each component to the UI
        componentList.forEach(component => {
            const componentEl = createComponentElement(component);
            container.appendChild(componentEl);
        });
    });
}

function createComponentElement(component, depth = 0) {
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
                let displayValue = value;
                if (typeof value === 'object') {
                    displayValue = JSON.stringify(value).substring(0, 30) + (JSON.stringify(value).length > 30 ? '...' : '');
                } else if (String(value).length > 20) {
                    displayValue = String(value).substring(0, 20) + '...';
                }
                configItems.push(`<span class="text-xs bg-gray-800/50 px-2 py-0.5 rounded">${key}: ${displayValue}</span>`);
            }
        }
        if (configItems.length > 0) {
            configSummary = `<div class="mt-2 flex flex-wrap gap-1">${configItems.join('')}</div>`;
        }
    }

    el.innerHTML = `
<div class="flex justify-between items-start">
  <div class="flex-1">
    <div class="flex items-center">
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
    <button class="text-gray-400 hover:text-white opacity-0 group-hover:opacity-100 transition-opacity"
            onclick="event.stopPropagation(); showConfigModal(${JSON.stringify(component).replace(/"/g, '&quot;')})"
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

// Create header section
    const header = document.createElement('div');
    header.className = 'flex justify-between items-start mb-2';

    const headerLeft = document.createElement('div');
    headerLeft.className = 'flex-1';
    headerLeft.innerHTML = `
<div class="flex items-center">
  <span class="font-medium text-yellow-300">if</span>
  <div class="flex items-center ml-2 group/condition">
    <span class="text-xs text-gray-400">${component.config.condition || ''}</span>
    <button class="ml-1 text-gray-500 hover:text-yellow-400 opacity-0 group-hover:opacity-100 transition-opacity">
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

// Add else button (only if else block doesn't exist or has no plugins
    if (!component.config.else || !component.config.else.plugins || component.config.else.plugins.length === 0) {
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

// Create if block plugins container with add button
    const ifPluginsContainer = document.createElement('div');
    ifPluginsContainer.className = 'ml-4 space-y-2';

// Add Plugin button for if block
    const addIfPluginBtn = document.createElement('button');
    addIfPluginBtn.className = 'text-xs text-gray-400 hover:text-yellow-400 flex items-center mb-2';
    addIfPluginBtn.innerHTML = `
<svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
</svg>
Add Plugin
`;
    addIfPluginBtn.onclick = (e) => {
        e.stopPropagation();
        addPluginToConditional(component.id, 'if');
    };
    ifPluginsContainer.appendChild(addIfPluginBtn);

    if (component.config.plugins && component.config.plugins.length > 0) {
        component.config.plugins.forEach(plugin => {
            const pluginEl = createComponentElement(plugin, depth + 1);
            ifPluginsContainer.appendChild(pluginEl);
        });
    } else {
        const emptyMsg = document.createElement('p');
        emptyMsg.className = 'text-gray-500 text-sm py-2';
        emptyMsg.textContent = 'No plugins in if block';
        ifPluginsContainer.appendChild(emptyMsg);
    }
    container.appendChild(ifPluginsContainer);

// Render else-if blocks
    if (component.config.else_ifs && component.config.else_ifs.length > 0) {
        component.config.else_ifs.forEach(elseIf => {
            const elseIfBlock = document.createElement('div');
            elseIfBlock.className = 'mt-2';

            const elseIfHeader = document.createElement('div');
            elseIfHeader.className = 'flex items-center';
            elseIfHeader.innerHTML = `
    <span class="font-medium text-yellow-300">else if</span>
    <span class="ml-2 text-xs text-gray-400">${elseIf.condition || ''}</span>
  `;
            elseIfBlock.appendChild(elseIfHeader);

            const elseIfPluginsContainer = document.createElement('div');
            elseIfPluginsContainer.className = 'ml-4 space-y-2 mt-2';

            // Add Plugin button for else-if block
            const addElseIfPluginBtn = document.createElement('button');
            addElseIfPluginBtn.className = 'text-xs text-gray-400 hover:text-yellow-400 flex items-center mb-2';
            addElseIfPluginBtn.innerHTML = `
    <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
    </svg>
    Add Plugin
  `;
            addElseIfPluginBtn.onclick = (e) => {
                e.stopPropagation();
                addPluginToConditional(component.id, 'else_if', elseIfIndex);
            };
            elseIfPluginsContainer.appendChild(addElseIfPluginBtn);

            if (elseIf.plugins && elseIf.plugins.length > 0) {
                elseIf.plugins.forEach(plugin => {
                    const pluginEl = createComponentElement(plugin, depth + 1);
                    elseIfPluginsContainer.appendChild(pluginEl);
                });
            } else {
                const emptyMsg = document.createElement('p');
                emptyMsg.className = 'text-gray-500 text-sm py-2';
                emptyMsg.textContent = 'No plugins in else-if block';
                elseIfPluginsContainer.appendChild(emptyMsg);
            }

            elseIfBlock.appendChild(elseIfPluginsContainer);
            container.appendChild(elseIfBlock);
        });
    }

// Render else block (only if it exists and has plugins)
    if (component.config.else && component.config.else.plugins && component.config.else.plugins.length > 0) {
        const elseBlock = document.createElement('div');
        elseBlock.className = 'mt-2';

        const elseHeader = document.createElement('div');
        elseHeader.className = 'flex items-center';
        elseHeader.innerHTML = '<span class="font-medium text-yellow-300">else</span>';
        elseBlock.appendChild(elseHeader);

        const elsePluginsContainer = document.createElement('div');
        elsePluginsContainer.className = 'ml-4 space-y-2 mt-2';

// Add Plugin button for else block
        const addElsePluginBtn = document.createElement('button');
        addElsePluginBtn.className = 'text-xs text-gray-400 hover:text-yellow-400 flex items-center mb-2';
        addElsePluginBtn.innerHTML = `
  <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
  </svg>
  Add Plugin
`;
        addElsePluginBtn.onclick = (e) => {
            e.stopPropagation();
            addPluginToConditional(component.id, 'else');
        };
        elsePluginsContainer.appendChild(addElsePluginBtn);

        component.config.else.plugins.forEach(plugin => {
            const pluginEl = createComponentElement(plugin, depth + 1);
            elsePluginsContainer.appendChild(pluginEl);
        });

        elseBlock.appendChild(elsePluginsContainer);
        container.appendChild(elseBlock);
    }

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
    // Find and update the component in the global components object
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
    return false;
};

// Initialize the pipeline editor
document.addEventListener('DOMContentLoaded', function () {
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

// Remove from components object
    for (const type in components) {
        const index = components[type].findIndex(c => c.id === componentId);
        if (index > -1) {
            components[type].splice(index, 1);
            break;
        }
    }

// Remove from DOM
    const element = document.querySelector(`[data-id="${componentId}"]`);
    if (element) {
        const parent = element.parentElement;
        element.remove();

// Show placeholder if no components left
        if (parent.children.length === 0) {
            const placeholder = document.createElement('p');
            placeholder.className = 'text-gray-400 text-center py-8';
            placeholder.textContent = parent.id === 'inputComponents' ? 'No input components added' :
                parent.id === 'filterComponents' ? 'No filter components added' :
                    'No output components added';
            parent.appendChild(placeholder);
        }
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

// Add the plugin to the else-if block
        component.config.else_ifs[context.elseIfIndex].plugins.push(newPlugin);

// Refresh the UI
        loadExistingComponents();

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
