/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// Track current graph layout mode
let currentGraphLayout = 'branch'; // 'branch' or 'flow'

// Track fullscreen state
let isGraphFullscreen = false;

// Store node original positions for snap-back
let nodeOriginalPositions = new Map();

// D3 zoom behavior
let zoomBehavior = null;

// Track newly added component for animation
let newlyAddedComponentId = null;
window.newlyAddedComponentId = null;

// Track if this is the initial render for centering and animations
let isInitialRender = true;
let nodeRenderIndex = 0;
let currentTransform = null; // Store current transform to preserve position
let animationDelayPerNode = 100; // Dynamic delay per node (ms), calculated based on total nodes

/**
 * Switch graph layout mode
 */
function switchGraphLayout(layout) {
    currentGraphLayout = layout;
    renderGraphEditor();
}

/**
 * Toggle fullscreen mode for graph editor
 */
function toggleGraphFullscreen() {
    const container = document.getElementById('graphEditorContainer');
    const btn = document.getElementById('graphFullscreenBtn');
    
    if (!container || !btn) return;
    
    isGraphFullscreen = !isGraphFullscreen;
    
    if (isGraphFullscreen) {
        // Enter fullscreen
        container.style.position = 'fixed';
        container.style.top = '0';
        container.style.left = '0';
        container.style.right = '0';
        container.style.bottom = '0';
        container.style.zIndex = '9999';
        container.style.backgroundColor = '#1a1d23';
        
        // Change icon to minimize
        btn.innerHTML = `
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
            </svg>
        `;
        btn.title = 'Exit fullscreen';
    } else {
        // Exit fullscreen
        container.style.position = '';
        container.style.top = '';
        container.style.left = '';
        container.style.right = '';
        container.style.bottom = '';
        container.style.zIndex = '';
        container.style.backgroundColor = '';
        
        // Change icon back to expand
        btn.innerHTML = `
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"></path>
            </svg>
        `;
        btn.title = 'Toggle fullscreen';
    }
    
    // Re-render to adjust to new size
    setTimeout(() => renderGraphEditor(), 100);
}

/**
 * Initialize d3 zoom and pan behavior
 */
function initializeZoomPan(svg) {
    const svgElement = d3.select(svg);
    
    // Create zoom behavior
    zoomBehavior = d3.zoom()
        .scaleExtent([0.1, 3]) // Allow zoom from 10% to 300%
        .on('zoom', (event) => {
            // Apply transform to the main group
            svgElement.select('g').attr('transform', event.transform);
            // Store current transform
            currentTransform = event.transform;
        });
    
    // Apply zoom behavior to SVG
    svgElement.call(zoomBehavior);
    
    // Apply transform: use stored transform if available, otherwise center on initial load
    if (currentTransform) {
        // Reapply the stored transform to maintain position
        svgElement.call(zoomBehavior.transform, currentTransform);
    } else if (isInitialRender) {
        // First time loading - center the canvas
        const svgRect = svg.getBoundingClientRect();
        const svgWidth = svgRect.width;
        
        // Calculate center position - aim for the "Add Input" button area
        const targetX = 300; // Approximate center of input section
        const targetY = 50;  // Position of Add Input button
        
        // Calculate transform to center horizontally and position at top
        const translateX = (svgWidth / 2) - targetX;
        const translateY = 50; // Position near top of viewport with small margin
        
        // Apply initial transform
        const initialTransform = d3.zoomIdentity.translate(translateX, translateY);
        svgElement.call(zoomBehavior.transform, initialTransform);
        currentTransform = initialTransform;
    }
    
    // Reset zoom on double-click
    svgElement.on('dblclick.zoom', () => {
        svgElement.transition()
            .duration(750)
            .call(zoomBehavior.transform, d3.zoomIdentity);
    });
}

/**
 * Pan viewport to center on a specific node while preserving zoom level
 */
function panToNode(nodeId) {
    console.log('[panToNode] Looking for node:', nodeId);
    
    const svg = document.querySelector('#graphSvg');
    if (!svg || !zoomBehavior) {
        console.warn('[panToNode] SVG or zoomBehavior not available');
        return;
    }
    
    // Find the node element
    const nodeElement = svg.querySelector(`[data-component-id="${nodeId}"]`);
    if (!nodeElement) {
        console.warn('[panToNode] Node not found for panning:', nodeId);
        // Debug: list all nodes with data-component-id
        const allNodes = svg.querySelectorAll('[data-component-id]');
        console.log('[panToNode] Available nodes:', Array.from(allNodes).map(n => n.getAttribute('data-component-id')));
        return;
    }
    
    console.log('[panToNode] Node found:', nodeElement);
    
    // Get the node's bounding box in SVG coordinates
    const bbox = nodeElement.getBBox();
    const nodeCenterX = bbox.x + bbox.width / 2;
    const nodeCenterY = bbox.y + bbox.height / 2;
    
    console.log('[panToNode] Node center:', nodeCenterX, nodeCenterY);
    
    // Get SVG viewport dimensions
    const svgRect = svg.getBoundingClientRect();
    const svgWidth = svgRect.width;
    const svgHeight = svgRect.height;
    
    // Get current zoom transform to preserve the zoom level
    const svgElement = d3.select(svg);
    const currentZoomTransform = d3.zoomTransform(svg);
    const scale = currentZoomTransform.k;
    
    console.log('[panToNode] Current zoom scale:', scale);
    
    // Calculate the transform needed to center the node while preserving zoom
    const translateX = (svgWidth / 2) - (nodeCenterX * scale);
    const translateY = (svgHeight / 2) - (nodeCenterY * scale);
    
    console.log('[panToNode] New transform:', translateX, translateY, scale);
    
    // Create new transform by modifying only the translation, keeping the same scale
    // This prevents D3 from interpolating through different zoom levels
    const newTransform = d3.zoomIdentity
        .scale(scale)
        .translate(translateX / scale, translateY / scale);
    
    // Apply smooth transition to the new position
    svgElement.transition()
        .duration(750)
        .call(zoomBehavior.transform, newTransform);
}

/**
 * Make a node draggable with snap-back physics
 * Note: Individual node dragging is disabled - use canvas pan/zoom instead
 */
function makeDraggable(nodeGroup, originalX, originalY, componentId) {
    // Dragging is now handled at the canvas level via zoom/pan
    // Nodes can still be clicked to open config
    return;
}

/**
 * Initialize and render the graph editor
 */
function renderGraphEditor() {
    if (!components) {
        console.error('Components not available');
        return;
    }

    const svg = document.getElementById('graphSvg');
    if (!svg) {
        console.error('Graph SVG not found');
        return;
    }

    // Reset node render index for staggered animations
    nodeRenderIndex = 0;
    
    // Calculate dynamic animation timing based on total node count
    // Target: all nodes rendered within ~3 seconds
    const targetTotalTime = 3000; // 3 seconds in milliseconds
    const fadeInDuration = 500; // Fixed fade-in duration
    
    // Count total nodes (including conditionals and nested plugins)
    let totalNodes = 0;
    if (typeof countTotalPlugins === 'function') {
        totalNodes = countTotalPlugins(components);
    }
    // Also count conditional nodes themselves
    if (typeof countTotalConditions === 'function') {
        totalNodes += countTotalConditions(components);
    }
    
    // Calculate delay per node to fit within target time
    // Formula: (targetTime - fadeInDuration) / totalNodes
    // Min delay: 10ms (for very large pipelines), Max delay: 150ms (for small pipelines)
    if (totalNodes > 0) {
        const calculatedDelay = Math.max(10, Math.min(150, (targetTotalTime - fadeInDuration) / totalNodes));
        animationDelayPerNode = calculatedDelay;
    } else {
        animationDelayPerNode = 100; // Default for empty pipelines
    }
    
    console.log(`[Animation] Total nodes: ${totalNodes}, Delay per node: ${animationDelayPerNode.toFixed(1)}ms`);

    // Clear existing content
    svg.innerHTML = '';

    // Collect all components
    const allComponents = {
        input: components.input || [],
        filter: components.filter || [],
        output: components.output || []
    };

    // Check if we have any components
    const hasComponents = allComponents.input.length > 0 || 
                         allComponents.filter.length > 0 || 
                         allComponents.output.length > 0;

    if (!hasComponents) {
        // Show empty state with add buttons
        renderEmptyState(svg);
        return;
    }

    // Render using branch layout (Flow will be implemented later for conditions)
    renderBranchLayout(svg, allComponents);
    
    // Initialize zoom and pan behavior
    initializeZoomPan(svg);
    
    console.log('[renderGraphEditor] Checking for newly added component...');
    console.log('[renderGraphEditor] newlyAddedComponentId:', newlyAddedComponentId);
    console.log('[renderGraphEditor] window.newlyAddedComponentId:', window.newlyAddedComponentId);
    
    // Pan to newly added node if one exists
    if (newlyAddedComponentId || window.newlyAddedComponentId) {
        const nodeId = newlyAddedComponentId || window.newlyAddedComponentId;
        console.log('[renderGraphEditor] Will pan to node:', nodeId);
        // Wait for DOM to update before panning
        setTimeout(() => {
            panToNode(nodeId);
        }, 100);
    } else {
        console.log('[renderGraphEditor] No newly added component to pan to');
    }
    
    // After first render, disable initial render flag
    setTimeout(() => {
        isInitialRender = false;
    }, 100);
}

/**
 * Create an "Add" button for empty sections
 */
function createAddButton(type) {
    const button = document.createElement('button');
    button.className = 'graph-add-button';
    button.onclick = () => {
        // Reuse existing plugin modal
        if (typeof PluginModal !== 'undefined') {
            PluginModal.show(type);
        }
    };

    const typeLabel = type.charAt(0).toUpperCase() + type.slice(1);
    button.innerHTML = `
        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
        </svg>
        <span>Add ${typeLabel}</span>
    `;

    return button;
}

/**
 * Render empty state with add buttons
 */
function renderEmptyState(svg) {
    const foreignObject = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
    foreignObject.setAttribute('x', '50%');
    foreignObject.setAttribute('y', '50%');
    foreignObject.setAttribute('width', '400');
    foreignObject.setAttribute('height', '300');
    foreignObject.setAttribute('transform', 'translate(-200, -150)');
    
    const div = document.createElement('div');
    div.className = 'flex flex-col gap-4 items-center justify-center';
    div.innerHTML = `
        <p class="text-gray-400 text-center mb-4">No components in pipeline</p>
        <button class="graph-add-button" onclick="if(typeof PluginModal !== 'undefined') PluginModal.show('input')">
            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
            </svg>
            <span>Add Input</span>
        </button>
        <button class="graph-add-button" onclick="if(typeof PluginModal !== 'undefined') PluginModal.show('filter')">
            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
            </svg>
            <span>Add Filter</span>
        </button>
        <button class="graph-add-button" onclick="if(typeof PluginModal !== 'undefined') PluginModal.show('output')">
            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
            </svg>
            <span>Add Output</span>
        </button>
    `;
    
    foreignObject.appendChild(div);
    svg.appendChild(foreignObject);
}

/**
 * Process components to identify conditionals for branch rendering
 * Returns an array where conditionals are kept as objects with their branches
 */
function processComponentsForBranching(components) {
    const processed = {
        input: [],
        filter: [],
        output: []
    };
    
    ['input', 'filter', 'output'].forEach(type => {
        if (components[type] && Array.isArray(components[type])) {
            components[type].forEach((component, index) => {
                if (component.plugin === 'if') {
                    // Keep conditional as a special branching structure
                    processed[type].push({
                        ...component,
                        isBranchPoint: true,
                        branches: extractBranches(component)
                    });
                } else {
                    // Regular plugin
                    processed[type].push(component);
                }
            });
        }
    });
    
    return processed;
}

/**
 * Process plugins array to convert nested conditionals to branch points
 */
function processPluginsForBranches(plugins) {
    if (!plugins || !Array.isArray(plugins)) return [];
    
    return plugins.map(plugin => {
        if (plugin.plugin === 'if') {
            // Convert nested conditional to branch point
            return {
                ...plugin,
                isBranchPoint: true,
                branches: extractBranches(plugin)
            };
        }
        return plugin;
    });
}

/**
 * Extract all branches from a conditional (if, else_ifs, else)
 * Recursively processes nested conditionals within each branch
 */
function extractBranches(conditional) {
    const branches = [];
    
    // Main if branch
    branches.push({
        type: 'if',
        condition: conditional.config.condition,
        plugins: processPluginsForBranches(conditional.config.plugins || []),
        id: conditional.id
    });
    
    // else_if branches
    if (conditional.config.else_ifs && Array.isArray(conditional.config.else_ifs)) {
        conditional.config.else_ifs.forEach((elseIf, index) => {
            branches.push({
                type: 'else_if',
                condition: elseIf.condition,
                plugins: processPluginsForBranches(elseIf.plugins || []),
                id: conditional.id + '_elseif_' + index
            });
        });
    }
    
    // else branch
    if (conditional.config.else && conditional.config.else.plugins) {
        branches.push({
            type: 'else',
            condition: 'else',
            plugins: processPluginsForBranches(conditional.config.else.plugins || []),
            id: conditional.id + '_else'
        });
    }
    
    return branches;
}

/**
 * Render nodes in branch layout (tree-like structure)
 */
function renderBranchLayout(svg, allComponents) {
    // Process components to identify branch points
    const processedComponents = processComponentsForBranching(allComponents);
    
    // Create a group for all nodes
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    svg.appendChild(g);

    const nodeWidth = 180;
    const nodeHeight = 150;
    const verticalSpacing = 60;
    const branchHorizontalSpacing = 110; // Spacing between branches horizontally (reduced from 220)
    const sectionSpacing = 200; // Increased spacing between sections
    const horizontalSpacing = 220;
    const filterStartX = 100;
    let currentY = 80;

    // Render Input section - always horizontal, centered over first filter
    if (processedComponents.input.length > 0) {
        const inputCount = processedComponents.input.length;
        const totalInputWidth = (inputCount * nodeWidth) + ((inputCount - 1) * (horizontalSpacing - nodeWidth));
        const firstFilterX = filterStartX;
        const inputStartX = firstFilterX + (nodeWidth / 2) - (totalInputWidth / 2);
        
        const label = createSectionLabel('INPUT', inputStartX, currentY - 30, '#3b82f6');
        g.appendChild(label);
        
        // Calculate position for "Add Input" button
        // If odd number of inputs, center above middle node
        // If even number, center between the two middle nodes
        let addButtonX;
        if (inputCount % 2 === 1) {
            // Odd: center above middle node
            const middleIndex = Math.floor(inputCount / 2);
            addButtonX = inputStartX + (middleIndex * horizontalSpacing) + (nodeWidth / 2);
        } else {
            // Even: center between two middle nodes
            const leftMiddleIndex = (inputCount / 2) - 1;
            const leftMiddleX = inputStartX + (leftMiddleIndex * horizontalSpacing);
            const rightMiddleX = inputStartX + ((leftMiddleIndex + 1) * horizontalSpacing);
            addButtonX = (leftMiddleX + rightMiddleX + nodeWidth) / 2;
        }
        
        // Add "Add Input" button using foreignObject
        const addButtonFO = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
        addButtonFO.setAttribute('x', addButtonX - 50);
        addButtonFO.setAttribute('y', currentY - 30);
        addButtonFO.setAttribute('width', '100');
        addButtonFO.setAttribute('height', '30');
        
        const addButtonDiv = document.createElement('div');
        addButtonDiv.className = 'flex justify-center';
        addButtonDiv.innerHTML = `
            <button class="px-3 py-1 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded flex items-center gap-1 transition-colors"
                    onclick="if(typeof PluginModal !== 'undefined') PluginModal.show('input')"
                    title="Add Input">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                </svg>
                <span>Add Input</span>
            </button>
        `;
        addButtonFO.appendChild(addButtonDiv);
        g.appendChild(addButtonFO);
        
        // Calculate where the first filter will be positioned
        const filterY = currentY + nodeHeight + sectionSpacing;
        
        processedComponents.input.forEach((component, index) => {
            const inputX = inputStartX + (index * horizontalSpacing);
            const nodeGroup = createNodeElement(component, inputX, currentY, nodeWidth, nodeHeight, 'input');
            g.appendChild(nodeGroup);
            
            // Draw connection line from each input to the first filter (if filter exists)
            if (processedComponents.filter.length > 0) {
                const isNewNode = component.id === newlyAddedComponentId;
                const line = createConnectionLine(
                    inputX + nodeWidth / 2, currentY + nodeHeight,
                    firstFilterX + nodeWidth / 2, filterY,
                    isNewNode,
                    'filter',
                    0,
                    false  // Don't show buttons on input-to-filter lines
                );
                g.insertBefore(line, nodeGroup);
            }
        });
        
        currentY = filterY;
    }

    // Render Filter section - handle both regular plugins and branch points
    if (processedComponents.filter.length > 0) {
        const label = createSectionLabel('FILTER', filterStartX, currentY - 30, '#22c55e');
        g.appendChild(label);
        
        processedComponents.filter.forEach((component, index) => {
            if (component.isBranchPoint) {
                // This is a conditional - render as branches
                const branches = component.branches;
                const branchCount = branches.length;
                
                // Calculate total width needed for all branches
                const totalBranchWidth = (branchCount * nodeWidth) + ((branchCount - 1) * branchHorizontalSpacing);
                const branchStartX = filterStartX + (nodeWidth / 2) - (totalBranchWidth / 2);
                
                // Store Y position before branches for connection lines
                const beforeBranchY = currentY;
                
                // Check if this is a multi-branch conditional (has else-if or else)
                const isMultiBranch = branchCount > 1;
                
                // Add extra spacing for multi-branch conditionals to account for branches spanning outward
                // Single-branch conditionals use normal spacing (same as two plugins)
                const conditionalSpacing = isMultiBranch ? verticalSpacing : 0;
                currentY += conditionalSpacing;
                
                // Track the maximum Y position across all branches
                let maxBranchEndY = currentY;
                const branchEndPositions = []; // Track end Y position of each branch
                const buttonElements = []; // Store button elements to append after lines
                
                // Render each branch
                branches.forEach((branch, branchIndex) => {
                    const branchX = branchStartX + (branchIndex * (nodeWidth + branchHorizontalSpacing));
                    let branchY = currentY; // Start at currentY (with conditional spacing applied)
                    const branchStartY = branchY; // Store start for background container
                    
                    // Draw line from previous plugin to this branch's condition node
                    if (index > 0 || processedComponents.input.length > 0) {
                        const line = createConnectionLine(
                            filterStartX + nodeWidth / 2, beforeBranchY,
                            branchX + nodeWidth / 2, branchY,
                            false,
                            'filter',
                            index,
                            false
                        );
                        g.appendChild(line);
                    }
                    
                    // Create condition node
                    const conditionNode = {
                        id: branch.id,
                        type: 'filter',
                        plugin: branch.type,
                        isConditional: true,
                        conditionText: branch.condition,
                        config: {}
                    };
                    const conditionGroup = createNodeElement(conditionNode, branchX, branchY, nodeWidth, nodeHeight, 'filter');
                    g.appendChild(conditionGroup);
                    
                    branchY += nodeHeight + verticalSpacing;
                    
                    // Track Y position before nested conditionals for container calculation
                    let branchYBeforeNested = branchY;
                    
                    // Render plugins in this branch vertically
                    branch.plugins.forEach((plugin, pluginIndex) => {
                        // Draw line from condition node to first plugin, or from previous plugin to next
                        if (pluginIndex === 0) {
                            // Line from condition node to first plugin
                            const line = createConnectionLine(
                                branchX + nodeWidth / 2, branchY - verticalSpacing,
                                branchX + nodeWidth / 2, branchY,
                                false,
                                'filter',
                                index
                            );
                            g.appendChild(line);
                        }
                        
                        // Check if this plugin is itself a branch point (nested conditional)
                        if (plugin.isBranchPoint) {
                            // Render nested conditional as a single collapsed node inside parent's shaded area
                            // This prevents it from expanding into a full branch structure at the same level
                            const nestedConditionNode = {
                                id: plugin.id,
                                type: 'filter',
                                plugin: 'if',
                                isConditional: true,
                                conditionText: plugin.config.condition,
                                config: plugin.config
                            };
                            const nestedPluginGroup = createNodeElement(nestedConditionNode, branchX, branchY, nodeWidth, nodeHeight, 'filter');
                            g.appendChild(nestedPluginGroup);
                            
                            branchY += nodeHeight + verticalSpacing;
                        } else {
                            // Regular plugin
                            const pluginGroup = createNodeElement(plugin, branchX, branchY, nodeWidth, nodeHeight, 'filter');
                            g.appendChild(pluginGroup);
                            
                            // Draw line to next plugin in branch
                            if (pluginIndex < branch.plugins.length - 1) {
                                const nextY = branchY + nodeHeight + verticalSpacing;
                                const line = createConnectionLine(
                                    branchX + nodeWidth / 2, branchY + nodeHeight,
                                    branchX + nodeWidth / 2, nextY,
                                    false,
                                    'filter',
                                    index
                                );
                                g.appendChild(line);
                            }
                            
                            branchY += nodeHeight + verticalSpacing;
                            // Update branchYBeforeNested to include this regular plugin
                            branchYBeforeNested = branchY;
                        }
                    });
                    
                    // Track the end of this branch
                    maxBranchEndY = Math.max(maxBranchEndY, branchY);
                    branchEndPositions[branchIndex] = branchY - verticalSpacing; // Store actual end position (last element's bottom)
                    
                    // Add subtle background container for this branch
                    // Extend to include button area at bottom
                    const branchHeight = branchYBeforeNested - branchStartY;
                    const branchContainer = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                    branchContainer.setAttribute('x', branchX - 12);
                    branchContainer.setAttribute('y', branchStartY - 8);
                    branchContainer.setAttribute('width', nodeWidth + 24);
                    branchContainer.setAttribute('height', branchHeight - verticalSpacing + 56);
                    branchContainer.setAttribute('rx', 8);
                    branchContainer.setAttribute('fill', 'rgba(0, 0, 0, 0.15)');
                    branchContainer.setAttribute('stroke', 'rgba(255, 255, 255, 0.05)');
                    branchContainer.setAttribute('stroke-width', 1);
                    // Insert at beginning of group so it's behind everything
                    g.insertBefore(branchContainer, g.firstChild);
                    
                    // Add yellow left border accent line
                    const yellowBorder = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                    yellowBorder.setAttribute('x', branchX - 12);
                    yellowBorder.setAttribute('y', branchStartY - 8);
                    yellowBorder.setAttribute('width', 4);
                    yellowBorder.setAttribute('height', branchHeight - verticalSpacing + 56);
                    yellowBorder.setAttribute('rx', 2);
                    yellowBorder.setAttribute('fill', '#eab308'); // Yellow-500
                    g.insertBefore(yellowBorder, g.firstChild);
                    
                    // Add buttons at bottom of branch (always visible, inside shaded container)
                    const branchEndY = branchYBeforeNested - verticalSpacing;
                    
                    // Determine the elseIfIndex based on branch type and index
                    let elseIfIndex = null;
                    let blockType = 'if';
                    
                    if (branch.type === 'else_if') {
                        blockType = 'else_if';
                        elseIfIndex = branchIndex - 1;
                    } else if (branch.type === 'else') {
                        blockType = 'else';
                    }
                    
                    // Create buttons in foreignObject (always visible)
                    const branchButtonFO = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
                    branchButtonFO.setAttribute('x', branchX + (nodeWidth / 2) - 95);
                    branchButtonFO.setAttribute('y', branchEndY + 10);
                    branchButtonFO.setAttribute('width', '190');
                    branchButtonFO.setAttribute('height', '30');
                    branchButtonFO.setAttribute('overflow', 'visible');
                    branchButtonFO.style.opacity = '1';
                    branchButtonFO.style.pointerEvents = 'auto';
                    
                    const branchButtonDiv = document.createElement('div');
                    branchButtonDiv.style.display = 'flex';
                    branchButtonDiv.style.gap = '6px';
                    branchButtonDiv.style.justifyContent = 'center';
                    branchButtonDiv.style.alignItems = 'center';
                    branchButtonDiv.innerHTML = `
                        <button class="graph-add-plugin-to-branch-btn" 
                                data-component-id="${component.id}"
                                data-block-type="${blockType}"
                                data-elseif-index="${elseIfIndex}"
                                style="pointer-events: auto; padding: 4px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; white-space: nowrap; background-color: #2563eb; color: white; display: flex; align-items: center; gap: 4px; font-weight: 500;">
                            <svg style="width: 12px; height: 12px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                            </svg>
                            <span>Add Plugin</span>
                        </button>
                        <button class="graph-add-condition-to-branch-btn"
                                data-component-id="${component.id}"
                                data-block-type="${blockType}"
                                data-elseif-index="${elseIfIndex}"
                                style="pointer-events: auto; padding: 4px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; white-space: nowrap; background-color: #d97706; color: white; display: flex; align-items: center; gap: 4px; font-weight: 500;">
                            <svg style="width: 12px; height: 12px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                            </svg>
                            <span>Add Condition</span>
                        </button>
                    `;
                    branchButtonFO.appendChild(branchButtonDiv);
                    buttonElements.push(branchButtonFO);
                    
                    // Add hover area BELOW the shaded container for adding plugin after conditional
                    const afterConditionalY = branchYBeforeNested + 8; // Just below the shaded container
                    const afterConditionalHoverHeight = 40;
                    
                    // Create hover area below shaded container
                    const afterConditionalHoverArea = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                    afterConditionalHoverArea.setAttribute('x', branchX - 12);
                    afterConditionalHoverArea.setAttribute('y', afterConditionalY);
                    afterConditionalHoverArea.setAttribute('width', nodeWidth + 24);
                    afterConditionalHoverArea.setAttribute('height', afterConditionalHoverHeight);
                    afterConditionalHoverArea.setAttribute('fill', 'transparent');
                    afterConditionalHoverArea.style.cursor = 'pointer';
                    g.appendChild(afterConditionalHoverArea);
                    
                    // Create buttons for adding plugin/condition after conditional (hover-only)
                    const afterConditionalButtonFO = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
                    afterConditionalButtonFO.setAttribute('x', branchX + (nodeWidth / 2) - 95);
                    afterConditionalButtonFO.setAttribute('y', afterConditionalY + 5);
                    afterConditionalButtonFO.setAttribute('width', '190');
                    afterConditionalButtonFO.setAttribute('height', '30');
                    afterConditionalButtonFO.setAttribute('overflow', 'visible');
                    afterConditionalButtonFO.style.opacity = '0';
                    afterConditionalButtonFO.style.pointerEvents = 'none';
                    afterConditionalButtonFO.style.transition = 'opacity 0.15s ease';
                    
                    const afterConditionalButtonDiv = document.createElement('div');
                    afterConditionalButtonDiv.style.display = 'flex';
                    afterConditionalButtonDiv.style.gap = '6px';
                    afterConditionalButtonDiv.style.justifyContent = 'center';
                    afterConditionalButtonDiv.style.alignItems = 'center';
                    afterConditionalButtonDiv.innerHTML = `
                        <button class="graph-add-plugin-after-conditional-btn" 
                                data-component-id="${component.id}"
                                style="pointer-events: auto; padding: 4px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; white-space: nowrap; background-color: #3b82f6; color: white; display: flex; align-items: center; gap: 4px; font-weight: 500;">
                            <svg style="width: 12px; height: 12px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                            </svg>
                            <span>Add Plugin</span>
                        </button>
                        <button class="graph-add-condition-after-conditional-btn" 
                                data-component-id="${component.id}"
                                style="pointer-events: auto; padding: 4px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; white-space: nowrap; background-color: #d97706; color: white; display: flex; align-items: center; gap: 4px; font-weight: 500;">
                            <svg style="width: 12px; height: 12px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                            </svg>
                            <span>Add Condition</span>
                        </button>
                    `;
                    afterConditionalButtonFO.appendChild(afterConditionalButtonDiv);
                    
                    // Show/hide button on hover
                    afterConditionalHoverArea.addEventListener('mouseenter', () => {
                        afterConditionalButtonFO.style.opacity = '1';
                        afterConditionalButtonFO.style.pointerEvents = 'auto';
                    });
                    
                    afterConditionalHoverArea.addEventListener('mouseleave', () => {
                        afterConditionalButtonFO.style.opacity = '0';
                        afterConditionalButtonFO.style.pointerEvents = 'none';
                    });
                    
                    afterConditionalButtonFO.addEventListener('mouseenter', () => {
                        afterConditionalButtonFO.style.opacity = '1';
                        afterConditionalButtonFO.style.pointerEvents = 'auto';
                    });
                    
                    afterConditionalButtonFO.addEventListener('mouseleave', () => {
                        afterConditionalButtonFO.style.opacity = '0';
                        afterConditionalButtonFO.style.pointerEvents = 'none';
                    });
                    
                    buttonElements.push(afterConditionalButtonFO);
                    
                    // Add hover area between this branch and the next for + else if / + else buttons
                    if (branchIndex < branches.length - 1) {
                        const nextBranchX = branchStartX + ((branchIndex + 1) * (nodeWidth + branchHorizontalSpacing));
                        const gapCenterX = branchX + nodeWidth + (branchHorizontalSpacing / 2);
                        const gapCenterY = branchStartY + (branchHeight / 2);
                        
                        // Create invisible hover area between branches
                        const hoverArea = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                        hoverArea.setAttribute('x', branchX + nodeWidth);
                        hoverArea.setAttribute('y', branchStartY - 8);
                        hoverArea.setAttribute('width', branchHorizontalSpacing);
                        hoverArea.setAttribute('height', branchHeight - verticalSpacing + 16);
                        hoverArea.setAttribute('fill', 'transparent');
                        hoverArea.style.cursor = 'pointer';
                        g.appendChild(hoverArea);
                        
                        // Create buttons in foreignObject
                        const buttonFO = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
                        buttonFO.setAttribute('x', gapCenterX - 40);
                        buttonFO.setAttribute('y', gapCenterY - 25);
                        buttonFO.setAttribute('width', '80');
                        buttonFO.setAttribute('height', '50');
                        buttonFO.style.opacity = '0';
                        buttonFO.style.pointerEvents = 'none';
                        buttonFO.style.transition = 'opacity 0.15s ease';
                        
                        const hasElse = component.config && component.config.else && component.config.else.plugins;
                        const buttonDiv = document.createElement('div');
                        buttonDiv.className = 'flex flex-col gap-1 items-center';
                        buttonDiv.innerHTML = `
                            <button class="graph-add-elseif-btn" 
                                    data-component-id="${component.id}"
                                    style="pointer-events: auto; padding: 2px 8px; border: none; border-radius: 3px; font-size: 11px; cursor: pointer; white-space: nowrap; height: 20px; background-color: #d97706; color: white;">
                                <span>+ else if</span>
                            </button>
                            ${!hasElse ? `
                            <button class="graph-add-else-btn"
                                    data-component-id="${component.id}"
                                    style="pointer-events: auto; padding: 2px 8px; border: none; border-radius: 3px; font-size: 11px; cursor: pointer; white-space: nowrap; height: 20px; background-color: #d97706; color: white;">
                                <span>+ else</span>
                            </button>
                            ` : ''}
                        `;
                        buttonFO.appendChild(buttonDiv);
                        
                        // Show/hide buttons on hover
                        hoverArea.addEventListener('mouseenter', () => {
                            buttonFO.style.opacity = '1';
                            buttonFO.style.pointerEvents = 'auto';
                        });
                        
                        hoverArea.addEventListener('mouseleave', () => {
                            buttonFO.style.opacity = '0';
                            buttonFO.style.pointerEvents = 'none';
                        });
                        
                        buttonFO.addEventListener('mouseenter', () => {
                            buttonFO.style.opacity = '1';
                            buttonFO.style.pointerEvents = 'auto';
                        });
                        
                        buttonFO.addEventListener('mouseleave', () => {
                            buttonFO.style.opacity = '0';
                            buttonFO.style.pointerEvents = 'none';
                        });
                        
                        g.appendChild(buttonFO);
                    }
                });
                
                // Move currentY to after all branches
                currentY = maxBranchEndY;
                
                // If there's a next component, draw convergence lines from each branch to it
                if (index < processedComponents.filter.length - 1) {
                    const nextY = currentY + verticalSpacing;
                    branches.forEach((branch, branchIndex) => {
                        const branchX = branchStartX + (branchIndex * (nodeWidth + branchHorizontalSpacing));
                        const branchEndY = branchEndPositions[branchIndex]; // Use stored end position
                        
                        const line = createConnectionLine(
                            branchX + nodeWidth / 2, branchEndY,
                            filterStartX + nodeWidth / 2, nextY,
                            false,
                            'filter',
                            index + 1,
                            false
                        );
                        g.appendChild(line);
                    });
                    currentY = nextY;
                }
                
                // Append all button elements after lines are drawn (so buttons render on top)
                buttonElements.forEach(buttonElement => {
                    g.appendChild(buttonElement);
                });
                
            } else {
                // Regular plugin - render normally
                const nodeGroup = createNodeElement(component, filterStartX, currentY, nodeWidth, nodeHeight, 'filter');
                g.appendChild(nodeGroup);
                
                // Draw connection line to next filter (if not the last one)
                if (index < processedComponents.filter.length - 1) {
                    const isNewNode = component.id === newlyAddedComponentId;
                    const nextY = currentY + nodeHeight + verticalSpacing;
                    const line = createConnectionLine(
                        filterStartX + nodeWidth / 2, currentY + nodeHeight,
                        filterStartX + nodeWidth / 2, nextY,
                        isNewNode,
                        'filter',
                        index + 1
                    );
                    g.insertBefore(line, nodeGroup);
                }
                currentY += nodeHeight + verticalSpacing;
            }
        });
        
        currentY += sectionSpacing;
    }

    // Render Output section - vertical
    if (processedComponents.output.length > 0) {
        const label = createSectionLabel('OUTPUT', filterStartX, currentY - 30, '#a855f7');
        g.appendChild(label);
        
        processedComponents.output.forEach((component, index) => {
            const nodeGroup = createNodeElement(component, filterStartX, currentY, nodeWidth, nodeHeight, 'output');
            g.appendChild(nodeGroup);
            
            // Draw connection line to next output (if not the last one)
            if (index < processedComponents.output.length - 1) {
                const isNewNode = component.id === newlyAddedComponentId;
                const nextY = currentY + nodeHeight + verticalSpacing;
                const line = createConnectionLine(
                    filterStartX + nodeWidth / 2, currentY + nodeHeight,
                    filterStartX + nodeWidth / 2, nextY,
                    isNewNode,
                    'output',
                    index + 1
                );
                g.insertBefore(line, nodeGroup);
            }
            currentY += nodeHeight + verticalSpacing;
        });
    }
}

/**
 * Create a section label
 */
function createSectionLabel(text, x, y, color) {
    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    label.setAttribute('x', x);
    label.setAttribute('y', y);
    label.setAttribute('fill', color);
    label.setAttribute('font-size', '12');
    label.setAttribute('font-weight', '600');
    label.setAttribute('letter-spacing', '0.1em');
    label.textContent = text;
    return label;
}

/**
 * Create a node element for a component
 */
function createNodeElement(component, x, y, width, height, type) {
    const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    group.setAttribute('class', 'graph-node');
    group.setAttribute('data-id', component.id);
    group.setAttribute('data-component-id', component.id);

    // Determine color based on type - using dark gray bg with colored borders
    const colors = {
        input: { fill: '#374151', stroke: '#3b82f6', text: '#60a5fa' },
        filter: { fill: '#374151', stroke: '#22c55e', text: '#86efac' },
        output: { fill: '#374151', stroke: '#a855f7', text: '#c084fc' }
    };
    
    // Special colors for conditional nodes
    const conditionalColors = {
        if: { fill: '#422006', stroke: '#f59e0b', text: '#fbbf24' },      // Amber/orange for if
        else_if: { fill: '#422006', stroke: '#f59e0b', text: '#fbbf24' }, // Same amber for else_if
        else: { fill: '#422006', stroke: '#f59e0b', text: '#fbbf24' }     // Same amber for else
    };
    
    // Check if this is a conditional node
    const isConditional = component.isConditional || component.plugin === 'if' || component.plugin === 'else_if' || component.plugin === 'else';
    const color = isConditional ? conditionalColors[component.plugin] || conditionalColors.if : (colors[type] || colors.filter);

    // Build config summary
    const configItems = [];
    
    // For conditional nodes, show the condition text
    if (isConditional && component.conditionText) {
        configItems.push({ key: 'condition', value: component.conditionText });
    }
    
    // Add other config items
    if (component.config && Object.keys(component.config).length > 0) {
        for (const [key, value] of Object.entries(component.config)) {
            if (value !== undefined && value !== null && value !== '' && 
                key !== 'plugins' && key !== 'else_ifs' && key !== 'else' && key !== 'condition') {
                const displayValue = formatConfigValueForGraph(value, key);
                configItems.push({ key, value: displayValue });
            }
        }
    }

    // Use fixed node height of 150px
    const nodeHeight = 150;
    const baseHeight = 50; // Height for header section
    const configItemHeight = 24; // Height per config item
    const configPadding = 12; // Padding for config section

    // Create node rectangle with dark background
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', x);
    rect.setAttribute('y', y);
    rect.setAttribute('width', width);
    rect.setAttribute('height', nodeHeight);
    rect.setAttribute('rx', 8);
    rect.setAttribute('fill', color.fill);
    rect.setAttribute('stroke', color.stroke);
    rect.setAttribute('stroke-width', 2);
    rect.style.cursor = 'pointer';
    
    // Apply blue glow animation if this is a newly added node
    if (component.id === newlyAddedComponentId) {
        group.setAttribute('class', 'graph-node graph-node-glow');
        // Clear the newlyAddedComponentId after applying the animation
        setTimeout(() => {
            newlyAddedComponentId = null;
        }, 6000);
    } else {
        group.setAttribute('class', 'graph-node');
    }
    
    group.appendChild(rect);

    // Add header section with icon, plugin name, and buttons using foreignObject
    const headerFO = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
    headerFO.setAttribute('x', x);
    headerFO.setAttribute('y', y);
    headerFO.setAttribute('width', width);
    headerFO.setAttribute('height', baseHeight);
    
    const headerDiv = document.createElement('div');
    headerDiv.className = 'flex items-center justify-between p-3 graph-node-header';
    headerDiv.innerHTML = `
        <div class="flex items-center gap-2 flex-1 min-w-0">
            <img src="/static/images/${component.plugin}.png"
                 alt="${component.plugin}"
                 class="w-5 h-5 object-contain flex-shrink-0"
                 onerror="this.style.display='none';">
            <span class="font-medium text-white truncate" style="color: ${color.text}">${component.plugin || 'Unknown'}</span>
        </div>
        <div class="flex gap-1 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity graph-node-buttons">
            <button class="text-gray-400 hover:text-white p-1" 
                    onclick="event.stopPropagation(); if(typeof PluginConfigModal !== 'undefined') PluginConfigModal.show(${JSON.stringify(component).replace(/"/g, '&quot;')})"
                    title="Configure">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543-.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
            </button>
            <button class="text-gray-400 hover:text-red-400 p-1"
                    onclick="event.stopPropagation(); if(typeof removeComponent === 'function') removeComponent('${component.id}')"
                    title="Remove">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
            </button>
        </div>
    `;
    
    headerFO.appendChild(headerDiv);
    group.appendChild(headerFO);

    // Add config items using foreignObject for HTML rendering
    if (configItems.length > 0) {
        const maxConfigHeight = nodeHeight - baseHeight - 8; // Leave some padding at bottom
        
        // Add shaded background area behind config pills
        const configBg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        configBg.setAttribute('x', x + 8);
        configBg.setAttribute('y', y + baseHeight);
        configBg.setAttribute('width', width - 16);
        configBg.setAttribute('height', maxConfigHeight);
        configBg.setAttribute('rx', 4);
        configBg.setAttribute('fill', 'rgba(0, 0, 0, 0.3)'); // Semi-transparent dark background
        group.appendChild(configBg);
        
        const configFO = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
        configFO.setAttribute('x', x + 8);
        configFO.setAttribute('y', y + baseHeight);
        configFO.setAttribute('width', width - 16);
        configFO.setAttribute('height', maxConfigHeight);
        
        const configDiv = document.createElement('div');
        configDiv.className = 'flex flex-wrap gap-1 p-1';
        configDiv.style.pointerEvents = 'auto'; // Enable pointer events for scrolling
        configDiv.style.maxHeight = maxConfigHeight + 'px';
        configDiv.style.overflowY = 'auto';
        configDiv.style.overflowX = 'hidden';
        // Subtle scrollbar styling
        configDiv.style.cssText += `
            scrollbar-width: thin;
            scrollbar-color: rgba(107, 114, 128, 0.5) transparent;
        `;
        // Webkit scrollbar styling
        const style = document.createElement('style');
        style.textContent = `
            .graph-node-config::-webkit-scrollbar {
                width: 4px;
            }
            .graph-node-config::-webkit-scrollbar-track {
                background: transparent;
            }
            .graph-node-config::-webkit-scrollbar-thumb {
                background: rgba(107, 114, 128, 0.5);
                border-radius: 2px;
            }
            .graph-node-config::-webkit-scrollbar-thumb:hover {
                background: rgba(107, 114, 128, 0.7);
            }
        `;
        if (!document.getElementById('graph-node-scrollbar-style')) {
            style.id = 'graph-node-scrollbar-style';
            document.head.appendChild(style);
        }
        configDiv.classList.add('graph-node-config');
        
        // Prevent scroll events from bubbling to zoom handler
        configDiv.addEventListener('wheel', (e) => {
            e.stopPropagation();
        }, { passive: false });
        
        // Prevent clicks on config area from opening modal
        configDiv.addEventListener('click', (e) => {
            e.stopPropagation();
        });
        
        configItems.forEach(item => {
            const badge = document.createElement('span');
            badge.className = 'text-xs bg-gray-800/70 px-2 py-0.5 rounded text-gray-300';
            badge.textContent = `${item.key}: ${item.value}`;
            configDiv.appendChild(badge);
        });
        
        configFO.appendChild(configDiv);
        group.appendChild(configFO);
    }

    // Add click handler to open config modal
    group.style.cursor = 'pointer';
    group.addEventListener('click', (e) => {
        // Don't open modal if clicking on a button
        if (e.target.closest('button')) {
            return;
        }
        if (typeof PluginConfigModal !== 'undefined') {
            PluginConfigModal.show(component);
        }
    });
    
    // Add hover effect on the rect
    group.addEventListener('mouseenter', () => {
        rect.setAttribute('fill', '#4b5563');
        // Show buttons
        const buttons = headerDiv.querySelector('.graph-node-buttons');
        if (buttons) buttons.style.opacity = '1';
    });
    group.addEventListener('mouseleave', () => {
        rect.setAttribute('fill', color.fill);
        // Hide buttons
        const buttons = headerDiv.querySelector('.graph-node-buttons');
        if (buttons) buttons.style.opacity = '0';
    });

    // Make node draggable with snap-back physics
    makeDraggable(group, x, y, component.id);

    // Add fade-in animation
    // Sync global and local newlyAddedComponentId
    if (window.newlyAddedComponentId) {
        newlyAddedComponentId = window.newlyAddedComponentId;
    }
    
    const isNewNode = component.id === newlyAddedComponentId;
    const shouldAnimate = isNewNode || isInitialRender;
    
    if (shouldAnimate) {
        // Start invisible
        group.style.opacity = '0';
        
        // Calculate staggered delay for initial render using dynamic timing
        const delay = isInitialRender ? nodeRenderIndex * animationDelayPerNode : 0;
        nodeRenderIndex++;
        
        // Fade in over 500ms using d3 transition
        d3.select(group)
            .transition()
            .delay(delay)
            .duration(500)
            .style('opacity', '1')
            .on('end', function() {
                // Clear the flag after animation completes (only for newly added nodes)
                if (isNewNode) {
                    newlyAddedComponentId = null;
                    window.newlyAddedComponentId = null;
                }
            });
    }

    return group;
}

/**
 * Format config value for graph display (simplified version)
 */
function formatConfigValueForGraph(value, key) {
    // Handle arrays
    if (Array.isArray(value)) {
        if (value.length === 0) return '[]';
        if (value.length === 1) return `"${value[0]}"`;
        return `[${value.length} items]`;
    }
    
    // Handle objects
    if (typeof value === 'object' && value !== null) {
        const entries = Object.entries(value);
        if (entries.length === 0) return '{}';
        if (key === 'codec') {
            const codecName = Object.keys(value)[0];
            return `"${codecName}"`;
        }
        return `{${entries.length} keys}`;
    }
    
    // Handle strings and primitives
    const str = String(value).replace(/^"|"$/g, '');
    return str.length > 20 ? str.substring(0, 20) + '...' : str;
}

/**
 * Create a connection line between nodes with orthogonal (right-angle) routing
 */
function createConnectionLine(x1, y1, x2, y2, isAnimated = false, type = 'filter', index = 0, showButtons = true) {
    // Create a group to hold the line and interactive elements
    const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    group.setAttribute('class', 'connection-line-group');
    
    // Create orthogonal path: down from start, horizontal, then down to end
    const midY = (y1 + y2) / 2;
    const pathData = `M ${x1} ${y1} L ${x1} ${midY} L ${x2} ${midY} L ${x2} ${y2}`;
    
    // Visible line
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', pathData);
    path.setAttribute('stroke', '#6b7280');
    path.setAttribute('stroke-width', 2);
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke-dasharray', '5,5');
    
    // Invisible wider hit area for hover
    const hitArea = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    hitArea.setAttribute('d', pathData);
    hitArea.setAttribute('stroke', 'transparent');
    hitArea.setAttribute('stroke-width', 20);
    hitArea.setAttribute('fill', 'none');
    hitArea.style.cursor = 'pointer';
    
    // Animate if it's a newly added node OR if this is the initial render
    const shouldAnimate = isAnimated || isInitialRender;
    
    if (shouldAnimate) {
        // Calculate total path length for animation
        const length = path.getTotalLength();
        
        // Set up for drawing animation
        path.setAttribute('stroke-dasharray', length);
        path.setAttribute('stroke-dashoffset', length);
        
        // Calculate delay based on current node index for staggered effect using dynamic timing
        const baseDelay = isInitialRender ? (nodeRenderIndex - 1) * animationDelayPerNode : 0;
        const animationDelay = baseDelay + 300; // Start after node fade-in begins
        
        // Animate the line drawing
        d3.select(path)
            .transition()
            .duration(600)
            .delay(animationDelay)
            .attr('stroke-dashoffset', 0)
            .on('end', function() {
                // Reset to normal dashed line after animation
                d3.select(this)
                    .attr('stroke-dasharray', '5,5')
                    .attr('stroke-dashoffset', 0);
            });
    }
    
    // Add the hit area and path to the group
    group.appendChild(hitArea);
    group.appendChild(path);
    
    // Add hover buttons using foreignObject (only if showButtons is true)
    if (!showButtons) {
        return group;
    }
    
    const buttonX = (x1 + x2) / 2;
    const buttonY = midY;
    const buttonFO = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
    buttonFO.setAttribute('x', buttonX - 100);
    buttonFO.setAttribute('y', buttonY - 12);
    buttonFO.setAttribute('width', '200');
    buttonFO.setAttribute('height', '24');
    buttonFO.style.opacity = '0';
    buttonFO.style.pointerEvents = 'none';
    buttonFO.style.transition = 'opacity 0.15s ease';
    
    const buttonDiv = document.createElement('div');
    buttonDiv.className = 'flex gap-1 justify-center';
    buttonDiv.style.cssText = 'gap: 4px;';
    buttonDiv.innerHTML = `
        <button class="graph-add-plugin-btn insertion-button add-plugin" 
                data-type="${type}" data-index="${index}"
                style="pointer-events: auto; padding: 2px 6px; border: none; border-radius: 3px; font-size: 11px; cursor: pointer; display: flex; align-items: center; white-space: nowrap; height: 20px; background-color: #3b82f6; color: white;">
            <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="width: 12px; height: 12px; margin-right: 4px;">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
            </svg>
            <span>Add Plugin</span>
        </button>
        ${type === 'filter' || type === 'output' ? `
        <button class="graph-add-condition-btn insertion-button add-condition"
                data-type="${type}" data-index="${index}"
                style="pointer-events: auto; padding: 2px 6px; border: none; border-radius: 3px; font-size: 11px; cursor: pointer; display: flex; align-items: center; white-space: nowrap; height: 20px; background-color: #f59e0b; color: white;">
            <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="width: 12px; height: 12px; margin-right: 4px;">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
            </svg>
            <span>Add Condition</span>
        </button>
        ` : ''}
    `;
    buttonFO.appendChild(buttonDiv);
    
    // Show/hide buttons on hover
    hitArea.addEventListener('mouseenter', () => {
        buttonFO.style.opacity = '1';
        buttonFO.style.pointerEvents = 'auto';
    });
    
    hitArea.addEventListener('mouseleave', () => {
        buttonFO.style.opacity = '0';
        buttonFO.style.pointerEvents = 'none';
    });
    
    buttonFO.addEventListener('mouseenter', () => {
        buttonFO.style.opacity = '1';
        buttonFO.style.pointerEvents = 'auto';
    });
    
    buttonFO.addEventListener('mouseleave', () => {
        buttonFO.style.opacity = '0';
        buttonFO.style.pointerEvents = 'none';
    });
    
    // Add buttons to group
    group.appendChild(buttonFO);
    
    return group;
}

// Set up listener for component changes
document.addEventListener('DOMContentLoaded', function() {
    // Listen for component additions to re-render graph
    document.body.addEventListener('componentAdded', function() {
        // Check both local and global currentEditorMode
        const editorMode = window.currentEditorMode || (typeof currentEditorMode !== 'undefined' ? currentEditorMode : null);
        
        if (editorMode === 'graph') {
            // Use pendingAnimationPluginId if available (after modal save), otherwise use newlyAddedPluginId
            // pendingAnimationPluginId is set when a plugin is added via modal
            // newlyAddedPluginId is set for conditions and other direct additions
            if (typeof pendingAnimationPluginId !== 'undefined' && pendingAnimationPluginId) {
                newlyAddedComponentId = pendingAnimationPluginId;
                // Clear it after capturing
                window.pendingAnimationPluginId = null;
            } else if (typeof newlyAddedPluginId !== 'undefined' && newlyAddedPluginId) {
                newlyAddedComponentId = newlyAddedPluginId;
                // Clear it after capturing
                window.newlyAddedPluginId = null;
            }
            renderGraphEditor();
        }
    });
    
    // Add event listeners for graph connection line buttons
    document.body.addEventListener('click', function(e) {
        // Handle Add Plugin button on connection lines
        if (e.target.closest('.graph-add-plugin-btn')) {
            const btn = e.target.closest('.graph-add-plugin-btn');
            const type = btn.dataset.type;
            const index = parseInt(btn.dataset.index);
            
            // Use the existing showPluginModal function from pipeline_editor.js
            if (typeof showPluginModal === 'function') {
                showPluginModal(type, index);
            } else if (typeof PluginModal !== 'undefined') {
                PluginModal.show(type);
            }
        }
        
        // Handle Add Condition button on connection lines
        if (e.target.closest('.graph-add-condition-btn')) {
            const btn = e.target.closest('.graph-add-condition-btn');
            const type = btn.dataset.type;
            const index = parseInt(btn.dataset.index);
            
            // Use the existing addConditionAtPosition function from pipeline_editor.js
            if (typeof addConditionAtPosition === 'function') {
                addConditionAtPosition(type, index);
            }
        }
        
        // Handle + else if button between branch columns
        if (e.target.closest('.graph-add-elseif-btn')) {
            const btn = e.target.closest('.graph-add-elseif-btn');
            const componentId = btn.dataset.componentId;
            
            // Use the existing addElseIfToConditional function from pipeline_editor.js
            if (typeof addElseIfToConditional === 'function') {
                addElseIfToConditional(componentId);
            }
        }
        
        // Handle + else button between branch columns
        if (e.target.closest('.graph-add-else-btn')) {
            const btn = e.target.closest('.graph-add-else-btn');
            const componentId = btn.dataset.componentId;
            
            // Use the existing addElseToConditional function from pipeline_editor.js
            if (typeof addElseToConditional === 'function') {
                addElseToConditional(componentId);
            }
        }
        
        // Handle Add Plugin button at bottom of branch
        if (e.target.closest('.graph-add-plugin-to-branch-btn')) {
            const btn = e.target.closest('.graph-add-plugin-to-branch-btn');
            const componentId = btn.dataset.componentId;
            const blockType = btn.dataset.blockType;
            const elseIfIndex = btn.dataset.elseifIndex !== 'null' ? parseInt(btn.dataset.elseifIndex) : null;
            
            if (typeof addPluginToConditional === 'function') {
                addPluginToConditional(componentId, blockType, elseIfIndex);
            }
        }
        
        // Handle Add Condition button at bottom of branch
        if (e.target.closest('.graph-add-condition-to-branch-btn')) {
            const btn = e.target.closest('.graph-add-condition-to-branch-btn');
            const componentId = btn.dataset.componentId;
            const blockType = btn.dataset.blockType;
            const elseIfIndex = btn.dataset.elseifIndex !== 'null' ? parseInt(btn.dataset.elseifIndex) : null;
            
            // Find the conditional component to determine the index
            const component = findComponentById(componentId);
            if (component && typeof addConditionToConditional === 'function') {
                // Determine which plugin array to use
                let targetPlugins;
                switch (blockType) {
                    case 'if':
                        targetPlugins = component.config.plugins || [];
                        break;
                    case 'else_if':
                        targetPlugins = component.config.else_ifs?.[elseIfIndex]?.plugins || [];
                        break;
                    case 'else':
                        targetPlugins = component.config.else?.plugins || [];
                        break;
                    default:
                        targetPlugins = [];
                }
                
                // Add at the end of the plugins array
                const index = targetPlugins.length;
                addConditionToConditional('filter', componentId, blockType, index, elseIfIndex);
            }
        }
        
        // Handle Add Plugin button below conditional (adds plugin after the entire conditional)
        if (e.target.closest('.graph-add-plugin-after-conditional-btn')) {
            const btn = e.target.closest('.graph-add-plugin-after-conditional-btn');
            const componentId = btn.dataset.componentId;
            
            // Find the conditional component in the filter array
            const filterComponents = window.components?.filter || [];
            const conditionalIndex = filterComponents.findIndex(c => c.id === componentId);
            
            if (conditionalIndex !== -1) {
                // Show plugin modal to add a plugin after this conditional
                if (typeof showPluginModal === 'function') {
                    showPluginModal('filter', conditionalIndex + 1);
                }
            }
        }
        
        // Handle Add Condition button below conditional (adds condition after the entire conditional)
        if (e.target.closest('.graph-add-condition-after-conditional-btn')) {
            const btn = e.target.closest('.graph-add-condition-after-conditional-btn');
            const componentId = btn.dataset.componentId;
            
            // Find the conditional component in the filter array
            const filterComponents = window.components?.filter || [];
            const conditionalIndex = filterComponents.findIndex(c => c.id === componentId);
            
            if (conditionalIndex !== -1) {
                // Add a condition after this conditional
                if (typeof addConditionAtPosition === 'function') {
                    addConditionAtPosition('filter', conditionalIndex + 1);
                }
            }
        }
    });
});

// Also listen to the global components variable changes as a fallback
// This ensures the graph updates even if the event doesn't fire
if (typeof MutationObserver !== 'undefined') {
    document.addEventListener('DOMContentLoaded', function() {
        // Set up a periodic check when in graph mode
        setInterval(function() {
            if (window.currentEditorMode === 'graph') {
                const graphContainer = document.getElementById('graphModeContainer');
                if (graphContainer && !graphContainer.classList.contains('hidden')) {
                    // Check if we need to re-render (this is a safety net)
                    const svg = document.getElementById('graphSvg');
                    if (svg && svg.children.length === 0 && typeof components !== 'undefined') {
                        renderGraphEditor();
                    }
                }
            }
        }, 500); // Check every 500ms
    });
}

// Make functions globally available
window.switchGraphLayout = switchGraphLayout;
window.renderGraphEditor = renderGraphEditor;
window.toggleGraphFullscreen = toggleGraphFullscreen;