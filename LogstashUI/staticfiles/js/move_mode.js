// ============================================
// MOVE MODE FUNCTIONALITY
// ============================================

// Move mode state - defined here to ensure it's available when this script loads
window.moveMode = window.moveMode || {
    active: false,
    componentId: null,
    componentType: null,
    sourceLocation: null // {type, index, parentId, blockType, elseIfIndex}
};

// Function to activate move mode for a component
function activateMoveMode(componentId) {
    const component = findComponentById(componentId);
    if (!component) return;

    // Find the component's location in the data structure
    const location = findComponentLocation(componentId);
    if (!location) return;

    // Set move mode state
    window.moveMode.active = true;
    window.moveMode.componentId = componentId;
    window.moveMode.componentType = component.type;
    window.moveMode.sourceLocation = location;

    // Add visual indicators
    document.body.classList.add('move-mode');
    
    // Highlight the component being moved
    const componentEl = document.querySelector(`[data-id="${componentId}"]`);
    if (componentEl) {
        componentEl.classList.add('component-moving');
    }

    // Show move mode indicator
    showMoveModeIndicator();

    // Update insertion points to show which are valid
    updateInsertionPointsForMoveMode();
}

// Function to deactivate move mode
function deactivateMoveMode() {
    // Remove visual indicators
    document.body.classList.remove('move-mode');
    
    const movingComponent = document.querySelector('.component-moving');
    if (movingComponent) {
        movingComponent.classList.remove('component-moving');
    }

    // Hide move mode indicator
    hideMoveModeIndicator();

    // Reset move mode state
    window.moveMode.active = false;
    window.moveMode.componentId = null;
    window.moveMode.componentType = null;
    window.moveMode.sourceLocation = null;

    // Refresh UI to restore normal insertion points
    loadExistingComponents();
}

// Function to show move mode indicator
function showMoveModeIndicator() {
    // Remove existing indicator if any
    hideMoveModeIndicator();

    const indicator = document.createElement('div');
    indicator.id = 'moveModeIndicator';
    indicator.className = 'move-mode-active';
    indicator.innerHTML = `
        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8h16M4 16h16" />
        </svg>
        <span>Moving component - Click insertion point to drop</span>
        <button onclick="deactivateMoveMode()" class="ml-2 hover:text-gray-200">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
        </button>
    `;
    document.body.appendChild(indicator);
}

// Function to hide move mode indicator
function hideMoveModeIndicator() {
    const indicator = document.getElementById('moveModeIndicator');
    if (indicator) {
        indicator.remove();
    }
}

// Function to find a component's location in the data structure
function findComponentLocation(componentId) {
    // Search in top-level components
    for (const type in components) {
        const index = components[type].findIndex(c => c.id === componentId);
        if (index !== -1) {
            return {
                type: type,
                index: index,
                isNested: false
            };
        }
    }

    // Search in nested conditionals
    for (const type in components) {
        for (let i = 0; i < components[type].length; i++) {
            const component = components[type][i];
            const nestedLocation = findInConditional(component, componentId);
            if (nestedLocation) {
                return nestedLocation;
            }
        }
    }

    return null;
}

// Helper function to search within conditional blocks
function findInConditional(component, targetId) {
    if (component.plugin !== 'if' || !component.config) {
        return null;
    }

    // Check in if block
    if (component.config.plugins) {
        const index = component.config.plugins.findIndex(c => c.id === targetId);
        if (index !== -1) {
            return {
                type: component.type,
                isNested: true,
                parentId: component.id,
                blockType: 'if',
                index: index
            };
        }

        // Recursively search in nested conditionals
        for (let i = 0; i < component.config.plugins.length; i++) {
            const nested = findInConditional(component.config.plugins[i], targetId);
            if (nested) return nested;
        }
    }

    // Check in else-if blocks
    if (component.config.else_ifs) {
        for (let elseIfIndex = 0; elseIfIndex < component.config.else_ifs.length; elseIfIndex++) {
            const elseIf = component.config.else_ifs[elseIfIndex];
            if (elseIf.plugins) {
                const index = elseIf.plugins.findIndex(c => c.id === targetId);
                if (index !== -1) {
                    return {
                        type: component.type,
                        isNested: true,
                        parentId: component.id,
                        blockType: 'else_if',
                        elseIfIndex: elseIfIndex,
                        index: index
                    };
                }

                // Recursively search in nested conditionals
                for (let i = 0; i < elseIf.plugins.length; i++) {
                    const nested = findInConditional(elseIf.plugins[i], targetId);
                    if (nested) return nested;
                }
            }
        }
    }

    // Check in else block
    if (component.config.else && component.config.else.plugins) {
        const index = component.config.else.plugins.findIndex(c => c.id === targetId);
        if (index !== -1) {
            return {
                type: component.type,
                isNested: true,
                parentId: component.id,
                blockType: 'else',
                index: index
            };
        }

        // Recursively search in nested conditionals
        for (let i = 0; i < component.config.else.plugins.length; i++) {
            const nested = findInConditional(component.config.else.plugins[i], targetId);
            if (nested) return nested;
        }
    }

    return null;
}

// Function to update insertion points for move mode
function updateInsertionPointsForMoveMode() {
    const insertionPoints = document.querySelectorAll('.insertion-point');
    const movingComponent = findComponentById(window.moveMode.componentId);
    const isMovingCondition = movingComponent && movingComponent.plugin === 'if';
    
    insertionPoints.forEach(point => {
        // Determine the section type of this insertion point
        const container = point.closest('[data-type]');
        const sectionType = container ? container.dataset.type : null;

        // Disable insertion points in different sections
        if (sectionType && sectionType !== window.moveMode.componentType) {
            point.classList.add('disabled');
            return;
        }

        // If moving a condition, disable insertion points inside itself
        if (isMovingCondition) {
            const componentContainer = point.closest('.component-container');
            if (componentContainer) {
                const conditionalId = componentContainer.dataset.conditionalId;
                
                // Check if this insertion point is inside the condition being moved
                // This includes direct children and deeply nested descendants
                if (conditionalId) {
                    // Check if the conditionalId is the component being moved OR is a descendant of it
                    if (conditionalId === window.moveMode.componentId || isDescendantOf(conditionalId, window.moveMode.componentId)) {
                        point.classList.add('disabled');
                        return;
                    }
                }
            }
        }

        // Otherwise, enable the insertion point
        point.classList.remove('disabled');
    });
}

// Function to handle dropping a component at an insertion point
function dropComponentAtInsertionPoint(insertionPoint) {
    if (!window.moveMode.active) return;

    // Check if this insertion point is disabled
    if (insertionPoint.classList.contains('disabled')) {
        return;
    }

    // Get the target location from the insertion point's context
    const targetLocation = getInsertionPointLocation(insertionPoint);
    if (!targetLocation) {
        console.error('Could not determine target location');
        return;
    }

    // Validate that we're not dropping in the same location
    if (isSameLocation(window.moveMode.sourceLocation, targetLocation)) {
        deactivateMoveMode();
        return;
    }

    // Perform the move
    moveComponent(window.moveMode.sourceLocation, targetLocation);

    // Deactivate move mode
    deactivateMoveMode();
}

// Helper function to check if a component is a descendant of another
// Returns true if componentId is a descendant of (nested inside) ancestorId
function isDescendantOf(componentId, ancestorId) {
    if (componentId === ancestorId) {
        return true;
    }

    const ancestor = findComponentById(ancestorId);
    if (!ancestor) return false;

    // If the ancestor is a conditional, check if componentId is nested inside it
    if (ancestor.plugin === 'if' && ancestor.config) {
        // Check if block
        if (ancestor.config.plugins) {
            for (const plugin of ancestor.config.plugins) {
                if (plugin.id === componentId || isDescendantOf(componentId, plugin.id)) {
                    return true;
                }
            }
        }

        // Check else-if blocks
        if (ancestor.config.else_ifs) {
            for (const elseIf of ancestor.config.else_ifs) {
                if (elseIf.plugins) {
                    for (const plugin of elseIf.plugins) {
                        if (plugin.id === componentId || isDescendantOf(componentId, plugin.id)) {
                            return true;
                        }
                    }
                }
            }
        }

        // Check else block
        if (ancestor.config.else && ancestor.config.else.plugins) {
            for (const plugin of ancestor.config.else.plugins) {
                if (plugin.id === componentId || isDescendantOf(componentId, plugin.id)) {
                    return true;
                }
            }
        }
    }

    return false;
}

// Function to get insertion point location
function getInsertionPointLocation(insertionPoint) {
    // Find the parent container
    const container = insertionPoint.closest('.component-container');
    if (!container) return null;

    // Determine if this is a conditional block
    const conditionalId = container.dataset.conditionalId;
    const blockType = container.dataset.blockType;
    const elseIfIndex = container.dataset.elseIfIndex;

    // Find the index by counting previous draggable items
    const allItems = Array.from(container.children);
    const insertionIndex = allItems.indexOf(insertionPoint);
    
    // Count how many draggable items come before this insertion point
    let index = 0;
    for (let i = 0; i < insertionIndex; i++) {
        if (allItems[i].classList.contains('draggable-item')) {
            index++;
        }
    }

    if (conditionalId) {
        // This is inside a conditional block
        return {
            type: window.moveMode.componentType,
            isNested: true,
            parentId: conditionalId,
            blockType: blockType,
            elseIfIndex: elseIfIndex ? parseInt(elseIfIndex) : null,
            index: index
        };
    } else {
        // This is a top-level insertion point
        const sectionContainer = insertionPoint.closest('[data-type]');
        const type = sectionContainer ? sectionContainer.dataset.type : null;
        
        return {
            type: type,
            isNested: false,
            index: index
        };
    }
}

// Function to check if two locations are the same
function isSameLocation(loc1, loc2) {
    if (loc1.isNested !== loc2.isNested) return false;
    if (loc1.type !== loc2.type) return false;

    if (loc1.isNested) {
        return loc1.parentId === loc2.parentId &&
               loc1.blockType === loc2.blockType &&
               loc1.elseIfIndex === loc2.elseIfIndex &&
               loc1.index === loc2.index;
    } else {
        return loc1.index === loc2.index;
    }
}

// Function to move a component from source to target location
function moveComponent(source, target) {
    // Get the component to move
    const component = findComponentById(window.moveMode.componentId);
    if (!component) {
        console.error('Component not found');
        return;
    }

    // Remove from source location
    removeComponentFromLocation(source);

    // Adjust target index if moving within the same container
    let adjustedTargetIndex = target.index;
    if (!source.isNested && !target.isNested && source.type === target.type) {
        // Moving within the same top-level array
        if (source.index < target.index) {
            adjustedTargetIndex--;
        }
    } else if (source.isNested && target.isNested &&
               source.parentId === target.parentId &&
               source.blockType === target.blockType &&
               source.elseIfIndex === target.elseIfIndex) {
        // Moving within the same nested array
        if (source.index < target.index) {
            adjustedTargetIndex--;
        }
    }

    // Insert at target location
    insertComponentAtLocation(component, target, adjustedTargetIndex);

    // Refresh the UI
    newlyAddedPluginId = component.id;
    loadExistingComponents();
}

// Function to remove a component from its location
function removeComponentFromLocation(location) {
    if (!location.isNested) {
        // Remove from top-level
        components[location.type].splice(location.index, 1);
    } else {
        // Remove from nested conditional
        const parentComponent = findComponentById(location.parentId);
        if (!parentComponent) return;

        let targetArray;
        switch (location.blockType) {
            case 'if':
                targetArray = parentComponent.config.plugins;
                break;
            case 'else_if':
                targetArray = parentComponent.config.else_ifs[location.elseIfIndex].plugins;
                break;
            case 'else':
                targetArray = parentComponent.config.else.plugins;
                break;
        }

        if (targetArray) {
            targetArray.splice(location.index, 1);
        }
    }
}

// Function to insert a component at a location
function insertComponentAtLocation(component, location, index) {
    if (!location.isNested) {
        // Insert at top-level
        if (!components[location.type]) {
            components[location.type] = [];
        }
        components[location.type].splice(index, 0, component);
    } else {
        // Insert into nested conditional
        const parentComponent = findComponentById(location.parentId);
        if (!parentComponent) return;

        let targetArray;
        switch (location.blockType) {
            case 'if':
                if (!parentComponent.config.plugins) {
                    parentComponent.config.plugins = [];
                }
                targetArray = parentComponent.config.plugins;
                break;
            case 'else_if':
                if (!parentComponent.config.else_ifs[location.elseIfIndex].plugins) {
                    parentComponent.config.else_ifs[location.elseIfIndex].plugins = [];
                }
                targetArray = parentComponent.config.else_ifs[location.elseIfIndex].plugins;
                break;
            case 'else':
                if (!parentComponent.config.else) {
                    parentComponent.config.else = {plugins: []};
                }
                if (!parentComponent.config.else.plugins) {
                    parentComponent.config.else.plugins = [];
                }
                targetArray = parentComponent.config.else.plugins;
                break;
        }

        if (targetArray) {
            targetArray.splice(index, 0, component);
        }
    }
}

// Event listener for move handle clicks
document.addEventListener('click', function(e) {
    const moveHandle = e.target.closest('.move-handle');
    if (moveHandle) {
        e.stopPropagation();
        const componentId = moveHandle.getAttribute('data-component-id');
        if (componentId) {
            if (window.moveMode.active) {
                // If already in move mode, cancel it
                deactivateMoveMode();
            } else {
                // Activate move mode
                activateMoveMode(componentId);
            }
        }
    }
});

// Event listener for insertion point clicks during move mode
document.addEventListener('click', function(e) {
    if (!window.moveMode.active) return;
    
    const insertionPoint = e.target.closest('.insertion-point');
    if (insertionPoint) {
        e.stopPropagation();
        dropComponentAtInsertionPoint(insertionPoint);
    }
});

// Make functions globally accessible
window.activateMoveMode = activateMoveMode;
window.deactivateMoveMode = deactivateMoveMode;
