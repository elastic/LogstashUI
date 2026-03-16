/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

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

    // Always render using branch layout (supports empty sections now)
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
    } else {
        // Add "Continue - No matching condition" branch when there's no else block
        branches.push({
            type: 'continue',
            condition: 'Continue - No matching condition',
            plugins: [], // No plugins in continue branch
            id: conditional.id + '_continue',
            isContinue: true // Flag to identify this as a continue branch
        });
    }
    
    return branches;
}

/**
 * Helper function to recursively calculate the width needed for a branch with nested conditionals
 */
function calculateBranchWidth(branch, nodeWidth, branchHorizontalSpacing) {
    if (!branch.plugins || branch.plugins.length === 0) {
        return nodeWidth;
    }
    
    let maxNestedWidth = nodeWidth;
    
    branch.plugins.forEach(plugin => {
        if (plugin.isBranchPoint && plugin.branches) {
            // Recursively calculate width for each nested branch
            const nestedBranchWidths = plugin.branches.map(nestedBranch => 
                calculateBranchWidth(nestedBranch, nodeWidth, branchHorizontalSpacing)
            );
            
            const nestedTotalWidth = nestedBranchWidths.reduce((sum, w) => sum + w, 0) + 
                                    ((plugin.branches.length - 1) * branchHorizontalSpacing);
            
            // Parent needs to be at least as wide as its nested content plus padding
            maxNestedWidth = Math.max(maxNestedWidth, nestedTotalWidth + 24);
        }
    });
    
    return maxNestedWidth;
}

/**
 * Recursively render a nested conditional as a full branch layout
 * This handles conditionals at any depth of nesting
 */
function renderNestedConditional(g, nestedConditional, parentX, startY, parentWidth, nodeWidth, nodeHeight, verticalSpacing, branchHorizontalSpacing, filterIndex, parentComponentId) {
    const nestedBranches = nestedConditional.branches;
    const branchCount = nestedBranches.length;
    
    let currentY = startY;
    
    // Calculate dynamic widths for nested branches using recursive calculation
    const branchWidths = nestedBranches.map(branch => 
        calculateBranchWidth(branch, nodeWidth, branchHorizontalSpacing)
    );
    
    const totalBranchWidth = branchWidths.reduce((sum, w) => sum + w, 0) + 
                            ((branchCount - 1) * branchHorizontalSpacing);
    const branchStartX = parentX + (parentWidth / 2) - (totalBranchWidth / 2);
    
    let maxBranchEndY = currentY;
    const branchEndPositions = [];
    const buttonElements = [];
    
    // Add spacing before nested conditional branches (similar to base-level conditionals)
    const beforeBranchY = currentY;
    const isMultiBranch = branchCount > 1;
    const conditionalSpacing = isMultiBranch ? verticalSpacing : 0;
    currentY += conditionalSpacing;
    
    // Draw forking connection lines from parent to each nested branch
    // This creates the visual pattern: line down from parent, split horizontally, then down to each condition
    if (isMultiBranch) {
        // For multi-branch: draw vertical line down, then horizontal lines to each branch, then vertical down to each condition
        const parentCenterX = parentX + (parentWidth / 2);
        const forkY = beforeBranchY + (conditionalSpacing / 2);
        
        // Draw vertical line from parent to fork point
        const verticalLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        verticalLine.setAttribute('x1', parentCenterX);
        verticalLine.setAttribute('y1', beforeBranchY);
        verticalLine.setAttribute('x2', parentCenterX);
        verticalLine.setAttribute('y2', forkY);
        verticalLine.setAttribute('stroke', '#6b7280');
        verticalLine.setAttribute('stroke-width', 2);
        verticalLine.setAttribute('stroke-dasharray', '5,5');
        g.appendChild(verticalLine);
        
        // Draw horizontal line spanning all branches
        let cumulativeX = branchStartX;
        const leftmostBranchCenterX = branchStartX + (branchWidths[0] / 2);
        const rightmostBranchCenterX = branchStartX + branchWidths.reduce((sum, w, idx) => {
            if (idx < branchCount - 1) {
                return sum + w + branchHorizontalSpacing;
            }
            return sum + w;
        }, 0) - branchWidths[branchCount - 1] + (branchWidths[branchCount - 1] / 2);
        
        const horizontalLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        horizontalLine.setAttribute('x1', leftmostBranchCenterX);
        horizontalLine.setAttribute('y1', forkY);
        horizontalLine.setAttribute('x2', rightmostBranchCenterX);
        horizontalLine.setAttribute('y2', forkY);
        horizontalLine.setAttribute('stroke', '#6b7280');
        horizontalLine.setAttribute('stroke-width', 2);
        horizontalLine.setAttribute('stroke-dasharray', '5,5');
        g.appendChild(horizontalLine);
        
        // Draw vertical lines from fork point down to each condition node
        cumulativeX = branchStartX;
        nestedBranches.forEach((branch, branchIndex) => {
            const branchWidth = branchWidths[branchIndex];
            const branchCenterX = cumulativeX + (branchWidth / 2);
            
            const branchVerticalLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            branchVerticalLine.setAttribute('x1', branchCenterX);
            branchVerticalLine.setAttribute('y1', forkY);
            branchVerticalLine.setAttribute('x2', branchCenterX);
            branchVerticalLine.setAttribute('y2', currentY);
            branchVerticalLine.setAttribute('stroke', '#6b7280');
            branchVerticalLine.setAttribute('stroke-width', 2);
            branchVerticalLine.setAttribute('stroke-dasharray', '5,5');
            g.appendChild(branchVerticalLine);
            
            cumulativeX += branchWidth + branchHorizontalSpacing;
        });
    } else {
        // For single-branch: draw simple vertical line from parent to condition
        const parentCenterX = parentX + (parentWidth / 2);
        const branchCenterX = branchStartX + (branchWidths[0] / 2);
        
        const singleLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        singleLine.setAttribute('x1', parentCenterX);
        singleLine.setAttribute('y1', beforeBranchY);
        singleLine.setAttribute('x2', branchCenterX);
        singleLine.setAttribute('y2', currentY);
        singleLine.setAttribute('stroke', '#6b7280');
        singleLine.setAttribute('stroke-width', 2);
        singleLine.setAttribute('stroke-dasharray', '5,5');
        g.appendChild(singleLine);
    }
    
    // Render each nested branch
    let cumulativeX = branchStartX;
    nestedBranches.forEach((branch, branchIndex) => {
        const branchWidth = branchWidths[branchIndex];
        const branchX = cumulativeX;
        let branchY = currentY;
        const branchStartY = branchY;
        
        // Create condition node
        // Check if the parent conditional has an else block
        const hasElse = nestedConditional.branches.some(b => b.type === 'else');
        const conditionNode = {
            id: branch.id,
            type: 'filter',
            plugin: branch.type,
            isConditional: true,
            conditionText: branch.condition,
            hasElse: hasElse,
            isContinue: branch.isContinue || false,
            config: {}
        };
        const conditionGroup = createNodeElement(conditionNode, branchX, branchY, branchWidth, nodeHeight, 'filter');
        g.appendChild(conditionGroup);
        
        branchY += nodeHeight + verticalSpacing;
        
        // Render plugins in this nested branch
        if (branch.plugins && branch.plugins.length > 0) {
            branch.plugins.forEach((plugin, pluginIndex) => {
                // Add hover area between plugins
                if (pluginIndex > 0) {
                    const betweenY = branchY - verticalSpacing;
                    const betweenHeight = verticalSpacing;
                    
                    const betweenHoverArea = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                    betweenHoverArea.setAttribute('x', branchX - 12);
                    betweenHoverArea.setAttribute('y', betweenY);
                    betweenHoverArea.setAttribute('width', branchWidth + 24);
                    betweenHoverArea.setAttribute('height', betweenHeight);
                    betweenHoverArea.setAttribute('fill', 'transparent');
                    betweenHoverArea.style.cursor = 'pointer';
                    g.appendChild(betweenHoverArea);
                    
                    const betweenButtonFO = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
                    betweenButtonFO.setAttribute('x', branchX + (branchWidth / 2) - 95);
                    betweenButtonFO.setAttribute('y', betweenY + (betweenHeight / 2) - 15);
                    betweenButtonFO.setAttribute('width', '190');
                    betweenButtonFO.setAttribute('height', '30');
                    betweenButtonFO.setAttribute('overflow', 'visible');
                    betweenButtonFO.style.opacity = '0';
                    betweenButtonFO.style.pointerEvents = 'none';
                    betweenButtonFO.style.transition = 'opacity 0.15s ease';
                    
                    const betweenButtonDiv = document.createElement('div');
                    betweenButtonDiv.style.display = 'flex';
                    betweenButtonDiv.style.gap = '6px';
                    betweenButtonDiv.style.justifyContent = 'center';
                    betweenButtonDiv.style.alignItems = 'center';
                    
                    const blockType = branch.type === 'else_if' ? 'else_if' : (branch.type === 'else' ? 'else' : 'if');
                    const elseIfIndex = branch.type === 'else_if' ? branchIndex - 1 : null;
                    
                    betweenButtonDiv.innerHTML = `
                        <button class="graph-add-plugin-to-branch-btn" 
                                data-component-id="${nestedConditional.id}"
                                data-block-type="${blockType}"
                                data-elseif-index="${elseIfIndex}"
                                data-index="${pluginIndex}"
                                style="pointer-events: auto; padding: 4px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; white-space: nowrap; background-color: #3b82f6; color: white; display: flex; align-items: center; gap: 4px; font-weight: 500;">
                            <svg style="width: 12px; height: 12px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                            </svg>
                            <span>Add Plugin</span>
                        </button>
                        <button class="graph-add-condition-to-branch-btn"
                                data-component-id="${nestedConditional.id}"
                                data-block-type="${blockType}"
                                data-elseif-index="${elseIfIndex}"
                                data-index="${pluginIndex}"
                                style="pointer-events: auto; padding: 4px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; white-space: nowrap; background-color: #d97706; color: white; display: flex; align-items: center; gap: 4px; font-weight: 500;">
                            <svg style="width: 12px; height: 12px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                            </svg>
                            <span>Add Condition</span>
                        </button>
                    `;
                    betweenButtonFO.appendChild(betweenButtonDiv);
                    
                    betweenHoverArea.addEventListener('mouseenter', () => {
                        betweenButtonFO.style.opacity = '1';
                        betweenButtonFO.style.pointerEvents = 'auto';
                    });
                    betweenHoverArea.addEventListener('mouseleave', () => {
                        betweenButtonFO.style.opacity = '0';
                        betweenButtonFO.style.pointerEvents = 'none';
                    });
                    betweenButtonFO.addEventListener('mouseenter', () => {
                        betweenButtonFO.style.opacity = '1';
                        betweenButtonFO.style.pointerEvents = 'auto';
                    });
                    betweenButtonFO.addEventListener('mouseleave', () => {
                        betweenButtonFO.style.opacity = '0';
                        betweenButtonFO.style.pointerEvents = 'none';
                    });
                    
                    g.appendChild(betweenButtonFO);
                }
                
                // Draw connection line
                if (pluginIndex === 0) {
                    const blockType = branch.type === 'else_if' ? 'else_if' : (branch.type === 'else' ? 'else' : 'if');
                    const elseIfIndex = branch.type === 'else_if' ? branchIndex - 1 : null;
                    const line = createConnectionLine(
                        branchX + branchWidth / 2, branchY - verticalSpacing,
                        branchX + branchWidth / 2, branchY,
                        false,
                        'filter',
                        0,
                        true,
                        nestedConditional.id,
                        blockType,
                        elseIfIndex
                    );
                    g.appendChild(line);
                }
                
                // Check if this plugin is itself a nested conditional (recursive case)
                if (plugin.isBranchPoint) {
                    const deeperNestedResult = renderNestedConditional(
                        g, plugin, branchX, branchY, branchWidth,
                        nodeWidth, nodeHeight, verticalSpacing, branchHorizontalSpacing,
                        filterIndex, nestedConditional.id
                    );
                    branchY = deeperNestedResult.endY;
                    
                    if (pluginIndex < branch.plugins.length - 1) {
                        const blockType = branch.type === 'else_if' ? 'else_if' : (branch.type === 'else' ? 'else' : 'if');
                        const elseIfIndex = branch.type === 'else_if' ? branchIndex - 1 : null;
                        const line = createConnectionLine(
                            branchX + branchWidth / 2, deeperNestedResult.endY - verticalSpacing,
                            branchX + branchWidth / 2, branchY,
                            false,
                            'filter',
                            pluginIndex + 1,
                            true,
                            nestedConditional.id,
                            blockType,
                            elseIfIndex
                        );
                        g.appendChild(line);
                    }
                } else {
                    // Regular plugin
                    const pluginGroup = createNodeElement(plugin, branchX, branchY, branchWidth, nodeHeight, 'filter');
                    g.appendChild(pluginGroup);
                    
                    if (pluginIndex < branch.plugins.length - 1) {
                        const nextY = branchY + nodeHeight + verticalSpacing;
                        const blockType = branch.type === 'else_if' ? 'else_if' : (branch.type === 'else' ? 'else' : 'if');
                        const elseIfIndex = branch.type === 'else_if' ? branchIndex - 1 : null;
                        const line = createConnectionLine(
                            branchX + branchWidth / 2, branchY + nodeHeight,
                            branchX + branchWidth / 2, nextY,
                            false,
                            'filter',
                            pluginIndex + 1,
                            true,
                            nestedConditional.id,
                            blockType,
                            elseIfIndex
                        );
                        g.appendChild(line);
                    }
                    
                    branchY += nodeHeight + verticalSpacing;
                }
            });
        }
        
        // Add hover area and buttons at bottom of branch (skip for continue branches)
        const branchEndY = branchY - verticalSpacing;
        
        if (!branch.isContinue) {
            const blockType = branch.type === 'else_if' ? 'else_if' : (branch.type === 'else' ? 'else' : 'if');
            const elseIfIndex = branch.type === 'else_if' ? branchIndex - 1 : null;
            const pluginInsertIndex = branch.plugins ? branch.plugins.length : 0;
            
            const branchButtonHoverArea = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            branchButtonHoverArea.setAttribute('x', branchX - 12);
            branchButtonHoverArea.setAttribute('y', branchEndY);
            branchButtonHoverArea.setAttribute('width', branchWidth + 24);
            branchButtonHoverArea.setAttribute('height', 48);
            branchButtonHoverArea.setAttribute('fill', 'transparent');
            branchButtonHoverArea.style.cursor = 'pointer';
            g.appendChild(branchButtonHoverArea);
            
            const branchButtonFO = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
            branchButtonFO.setAttribute('x', branchX + (branchWidth / 2) - 95);
            branchButtonFO.setAttribute('y', branchEndY + 10);
            branchButtonFO.setAttribute('width', '190');
            branchButtonFO.setAttribute('height', '30');
            branchButtonFO.setAttribute('overflow', 'visible');
            branchButtonFO.style.opacity = '0';
            branchButtonFO.style.pointerEvents = 'none';
            branchButtonFO.style.transition = 'opacity 0.15s ease';
            
            const branchButtonDiv = document.createElement('div');
            branchButtonDiv.style.display = 'flex';
            branchButtonDiv.style.gap = '6px';
            branchButtonDiv.style.justifyContent = 'center';
            branchButtonDiv.style.alignItems = 'center';
            branchButtonDiv.innerHTML = `
                <button class="graph-add-plugin-to-branch-btn" 
                        data-component-id="${nestedConditional.id}"
                        data-block-type="${blockType}"
                        data-elseif-index="${elseIfIndex}"
                        data-index="${pluginInsertIndex}"
                        style="pointer-events: auto; padding: 4px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; white-space: nowrap; background-color: #2563eb; color: white; display: flex; align-items: center; gap: 4px; font-weight: 500;">
                    <svg style="width: 12px; height: 12px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                    </svg>
                    <span>Add Plugin</span>
                </button>
                <button class="graph-add-condition-to-branch-btn"
                        data-component-id="${nestedConditional.id}"
                        data-block-type="${blockType}"
                        data-elseif-index="${elseIfIndex}"
                        data-index="${pluginInsertIndex}"
                        style="pointer-events: auto; padding: 4px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; white-space: nowrap; background-color: #d97706; color: white; display: flex; align-items: center; gap: 4px; font-weight: 500;">
                    <svg style="width: 12px; height: 12px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                    </svg>
                    <span>Add Condition</span>
                </button>
            `;
            branchButtonFO.appendChild(branchButtonDiv);
            
            branchButtonHoverArea.addEventListener('mouseenter', () => {
                branchButtonFO.style.opacity = '1';
                branchButtonFO.style.pointerEvents = 'auto';
            });
            branchButtonHoverArea.addEventListener('mouseleave', () => {
                branchButtonFO.style.opacity = '0';
                branchButtonFO.style.pointerEvents = 'none';
            });
            branchButtonFO.addEventListener('mouseenter', () => {
                branchButtonFO.style.opacity = '1';
                branchButtonFO.style.pointerEvents = 'auto';
            });
            branchButtonFO.addEventListener('mouseleave', () => {
                branchButtonFO.style.opacity = '0';
                branchButtonFO.style.pointerEvents = 'none';
            });
            
            buttonElements.push(branchButtonFO);
        }
        
        // Add branch container background
        const branchHeight = branchY - branchStartY;
        // Don't add extra height - branchY already includes button positioning
        const containerHeight = branchHeight - verticalSpacing + 56;
        const branchContainer = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        branchContainer.setAttribute('x', branchX - 12);
        branchContainer.setAttribute('y', branchStartY - 8);
        branchContainer.setAttribute('width', branchWidth + 24);
        branchContainer.setAttribute('height', containerHeight);
        branchContainer.setAttribute('rx', 8);
        branchContainer.setAttribute('fill', 'rgba(0, 0, 0, 0.2)');
        branchContainer.setAttribute('stroke', 'rgba(255, 255, 255, 0.08)');
        branchContainer.setAttribute('stroke-width', 1);
        branchContainer.setAttribute('data-branch-container', 'true');
        branchContainer.setAttribute('data-branch-level', 'nested');
        // Insert AFTER any existing parent containers to maintain proper z-order
        const existingContainers = g.querySelectorAll('[data-branch-container="true"]');
        if (existingContainers.length > 0) {
            // Insert after the last container so nested appears on top of parent
            const lastContainer = existingContainers[existingContainers.length - 1];
            g.insertBefore(branchContainer, lastContainer.nextSibling);
        } else {
            g.insertBefore(branchContainer, g.firstChild);
        }
        
        // Add colored border stripe based on branch type
        const stripeColors = {
            'if': '#22c55e',      // Green
            'else_if': '#f59e0b', // Amber
            'else': '#a855f7'     // Purple
        };
        const stripeColor = branch.isContinue ? '#3b82f6' : (stripeColors[branch.type] || '#22c55e');
        
        const branchBorder = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        branchBorder.setAttribute('x', branchX - 12);
        branchBorder.setAttribute('y', branchStartY - 8);
        branchBorder.setAttribute('width', 4);
        branchBorder.setAttribute('height', containerHeight);
        branchBorder.setAttribute('rx', 2);
        branchBorder.setAttribute('fill', stripeColor);
        branchBorder.setAttribute('data-branch-border', 'true');
        // Insert after the container to maintain z-order
        g.insertBefore(branchBorder, branchContainer.nextSibling);
        
        branchEndPositions[branchIndex] = branchY - verticalSpacing;
        maxBranchEndY = Math.max(maxBranchEndY, branchY);
        cumulativeX += branchWidth + branchHorizontalSpacing;
    });
    
    // Append button elements
    buttonElements.forEach(buttonElement => {
        g.appendChild(buttonElement);
    });
    
    // Draw rejoining fork pattern for multi-branch nested conditionals
    const finalEndY = maxBranchEndY + 48;
    if (isMultiBranch) {
        // Calculate rejoin point (halfway between branch ends and final end)
        const rejoinSpacing = 30;
        const rejoinY = maxBranchEndY + (rejoinSpacing / 2);
        
        // Draw vertical lines from each branch up to rejoin point
        let convergenceCumulativeX = branchStartX;
        nestedBranches.forEach((branch, branchIndex) => {
            const branchWidth = branchWidths[branchIndex];
            const branchX = convergenceCumulativeX;
            const branchEndY = branchEndPositions[branchIndex];
            const branchCenterX = branchX + (branchWidth / 2);
            
            const verticalLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            verticalLine.setAttribute('x1', branchCenterX);
            verticalLine.setAttribute('y1', branchEndY);
            verticalLine.setAttribute('x2', branchCenterX);
            verticalLine.setAttribute('y2', rejoinY);
            verticalLine.setAttribute('stroke', '#6b7280');
            verticalLine.setAttribute('stroke-width', 2);
            verticalLine.setAttribute('stroke-dasharray', '5,5');
            g.appendChild(verticalLine);
            
            convergenceCumulativeX += branchWidth + branchHorizontalSpacing;
        });
        
        // Draw horizontal line connecting all branches at rejoin point
        const leftmostBranchCenterX = branchStartX + (branchWidths[0] / 2);
        const rightmostBranchCenterX = branchStartX + branchWidths.reduce((sum, w, idx) => {
            if (idx < branchCount - 1) {
                return sum + w + branchHorizontalSpacing;
            }
            return sum + w;
        }, 0) - branchWidths[branchCount - 1] + (branchWidths[branchCount - 1] / 2);
        
        const horizontalLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        horizontalLine.setAttribute('x1', leftmostBranchCenterX);
        horizontalLine.setAttribute('y1', rejoinY);
        horizontalLine.setAttribute('x2', rightmostBranchCenterX);
        horizontalLine.setAttribute('y2', rejoinY);
        horizontalLine.setAttribute('stroke', '#6b7280');
        horizontalLine.setAttribute('stroke-width', 2);
        horizontalLine.setAttribute('stroke-dasharray', '5,5');
        g.appendChild(horizontalLine);
        
        // Draw vertical line from rejoin point down to final end point
        const parentCenterX = parentX + (parentWidth / 2);
        const finalVerticalLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        finalVerticalLine.setAttribute('x1', parentCenterX);
        finalVerticalLine.setAttribute('y1', rejoinY);
        finalVerticalLine.setAttribute('x2', parentCenterX);
        finalVerticalLine.setAttribute('y2', finalEndY);
        finalVerticalLine.setAttribute('stroke', '#6b7280');
        finalVerticalLine.setAttribute('stroke-width', 2);
        finalVerticalLine.setAttribute('stroke-dasharray', '5,5');
        g.appendChild(finalVerticalLine);
    }
    
    return {
        endY: finalEndY, // Add button area height to endY so parent knows total height
        branchEndPositions,
        totalWidth: totalBranchWidth,
        actualBranchWidths: branchWidths // Return actual widths used for each branch
    };
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

    // Render Input section - always render, even if empty
    // Always horizontal, centered over first filter
    const hasInputs = processedComponents.input.length > 0;
    if (true) {
        const inputCount = processedComponents.input.length;
        const firstFilterX = filterStartX;
        
        // If no inputs, show add button aligned left
        if (inputCount === 0) {
            const label = createSectionLabel('INPUT', firstFilterX, currentY, '#3b82f6');
            g.appendChild(label);
            
            // Add "Add Input" button aligned left below the label
            const addButtonFO = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
            addButtonFO.setAttribute('x', firstFilterX + (nodeWidth / 2) - 78);
            addButtonFO.setAttribute('y', currentY + 30);
            addButtonFO.setAttribute('width', '156');
            addButtonFO.setAttribute('height', '50');
            
            const addButtonDiv = document.createElement('div');
            addButtonDiv.className = 'flex justify-center';
            addButtonDiv.innerHTML = `
                <button class="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded flex items-center gap-2 transition-colors shadow-lg whitespace-nowrap"
                        onclick="if(typeof PluginModal !== 'undefined') PluginModal.show('input')"
                        title="Add Input">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                    </svg>
                    <span>Add Input</span>
                </button>
            `;
            addButtonFO.appendChild(addButtonDiv);
            g.appendChild(addButtonFO);
            
            currentY += 180; // Space for empty INPUT section
            
            // No connection line needed when input is empty
        } else {
            const totalInputWidth = (inputCount * nodeWidth) + ((inputCount - 1) * (horizontalSpacing - nodeWidth));
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
                
                // Draw connection line from each input to the next section
                if (processedComponents.filter.length > 0) {
                    // Draw to filter if it has components
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
                } else if (processedComponents.output.length > 0) {
                    // Draw to output if filter is empty but output has components
                    const outputY = filterY + sectionSpacing;
                    const isNewNode = component.id === newlyAddedComponentId;
                    const line = createConnectionLine(
                        inputX + nodeWidth / 2, currentY + nodeHeight,
                        firstFilterX + nodeWidth / 2, outputY,
                        isNewNode,
                        'output',
                        0,
                        false
                    );
                    g.insertBefore(line, nodeGroup);
                }
            });
            
            currentY = filterY;
        }
    }

    // Render Filter section - always render, even if empty
    const hasFilters = processedComponents.filter.length > 0;
    if (true) {
        const label = createSectionLabel('FILTER', filterStartX, currentY - 45, '#22c55e');
        g.appendChild(label);
        
        // If no filters, show add button aligned left below label
        if (!hasFilters) {
            const addButtonFO = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
            addButtonFO.setAttribute('x', filterStartX + (nodeWidth / 2) - 78);
            addButtonFO.setAttribute('y', currentY - 15);
            addButtonFO.setAttribute('width', '156');
            addButtonFO.setAttribute('height', '50');
            
            const addButtonDiv = document.createElement('div');
            addButtonDiv.className = 'flex justify-center gap-2';
            addButtonDiv.innerHTML = `
                <button class="px-4 py-2 text-sm bg-green-600 hover:bg-green-700 text-white rounded flex items-center gap-2 transition-colors shadow-lg whitespace-nowrap"
                        onclick="if(typeof PluginModal !== 'undefined') PluginModal.show('filter')"
                        title="Add Filter">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                    </svg>
                    <span>Add Filter</span>
                </button>
            `;
            addButtonFO.appendChild(addButtonDiv);
            g.appendChild(addButtonFO);
            
            currentY += 150; // Space for empty FILTER section
        } else {
        
        // Add hover area and buttons before the first filter component
        const beforeFirstFilterY = currentY - (verticalSpacing / 2);
        const beforeFirstFilterHeight = verticalSpacing / 2;
        
        const beforeFirstFilterHoverArea = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        beforeFirstFilterHoverArea.setAttribute('x', filterStartX - 20);
        beforeFirstFilterHoverArea.setAttribute('y', beforeFirstFilterY);
        beforeFirstFilterHoverArea.setAttribute('width', nodeWidth + 40);
        beforeFirstFilterHoverArea.setAttribute('height', beforeFirstFilterHeight);
        beforeFirstFilterHoverArea.setAttribute('fill', 'transparent');
        beforeFirstFilterHoverArea.style.cursor = 'pointer';
        g.appendChild(beforeFirstFilterHoverArea);
        
        const beforeFirstFilterButtonFO = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
        beforeFirstFilterButtonFO.setAttribute('x', filterStartX + (nodeWidth / 2) - 95);
        beforeFirstFilterButtonFO.setAttribute('y', beforeFirstFilterY + (beforeFirstFilterHeight / 2) - 15);
        beforeFirstFilterButtonFO.setAttribute('width', '190');
        beforeFirstFilterButtonFO.setAttribute('height', '30');
        beforeFirstFilterButtonFO.setAttribute('overflow', 'visible');
        beforeFirstFilterButtonFO.style.opacity = '0';
        beforeFirstFilterButtonFO.style.pointerEvents = 'none';
        beforeFirstFilterButtonFO.style.transition = 'opacity 0.15s ease';
        
        const beforeFirstFilterButtonDiv = document.createElement('div');
        beforeFirstFilterButtonDiv.style.display = 'flex';
        beforeFirstFilterButtonDiv.style.gap = '6px';
        beforeFirstFilterButtonDiv.style.justifyContent = 'center';
        beforeFirstFilterButtonDiv.style.alignItems = 'center';
        beforeFirstFilterButtonDiv.innerHTML = `
            <button class="graph-add-plugin-btn" 
                    data-type="filter"
                    data-index="0"
                    style="pointer-events: auto; padding: 4px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; white-space: nowrap; background-color: #3b82f6; color: white; display: flex; align-items: center; gap: 4px; font-weight: 500;">
                <svg style="width: 12px; height: 12px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                </svg>
                <span>Add Plugin</span>
            </button>
            <button class="graph-add-condition-btn" 
                    data-type="filter"
                    data-index="0"
                    style="pointer-events: auto; padding: 4px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; white-space: nowrap; background-color: #d97706; color: white; display: flex; align-items: center; gap: 4px; font-weight: 500;">
                <svg style="width: 12px; height: 12px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                </svg>
                <span>Add Condition</span>
            </button>
        `;
        beforeFirstFilterButtonFO.appendChild(beforeFirstFilterButtonDiv);
        
        beforeFirstFilterHoverArea.addEventListener('mouseenter', () => {
            beforeFirstFilterButtonFO.style.opacity = '1';
            beforeFirstFilterButtonFO.style.pointerEvents = 'auto';
        });
        
        beforeFirstFilterHoverArea.addEventListener('mouseleave', () => {
            beforeFirstFilterButtonFO.style.opacity = '0';
            beforeFirstFilterButtonFO.style.pointerEvents = 'none';
        });
        
        beforeFirstFilterButtonFO.addEventListener('mouseenter', () => {
            beforeFirstFilterButtonFO.style.opacity = '1';
            beforeFirstFilterButtonFO.style.pointerEvents = 'auto';
        });
        
        beforeFirstFilterButtonFO.addEventListener('mouseleave', () => {
            beforeFirstFilterButtonFO.style.opacity = '0';
            beforeFirstFilterButtonFO.style.pointerEvents = 'none';
        });
        
        g.appendChild(beforeFirstFilterButtonFO);
        
        processedComponents.filter.forEach((component, index) => {
            // Add hover area between this component and the previous one (if not first)
            if (index > 0) {
                const betweenY = currentY - verticalSpacing;
                const betweenHeight = verticalSpacing;
                
                const betweenHoverArea = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                betweenHoverArea.setAttribute('x', filterStartX - 20);
                betweenHoverArea.setAttribute('y', betweenY);
                betweenHoverArea.setAttribute('width', nodeWidth + 40);
                betweenHoverArea.setAttribute('height', betweenHeight);
                betweenHoverArea.setAttribute('fill', 'transparent');
                betweenHoverArea.style.cursor = 'pointer';
                g.appendChild(betweenHoverArea);
                
                const betweenButtonFO = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
                betweenButtonFO.setAttribute('x', filterStartX + (nodeWidth / 2) - 95);
                betweenButtonFO.setAttribute('y', betweenY + (betweenHeight / 2) - 15);
                betweenButtonFO.setAttribute('width', '190');
                betweenButtonFO.setAttribute('height', '30');
                betweenButtonFO.setAttribute('overflow', 'visible');
                betweenButtonFO.style.opacity = '0';
                betweenButtonFO.style.pointerEvents = 'none';
                betweenButtonFO.style.transition = 'opacity 0.15s ease';
                
                const betweenButtonDiv = document.createElement('div');
                betweenButtonDiv.style.display = 'flex';
                betweenButtonDiv.style.gap = '6px';
                betweenButtonDiv.style.justifyContent = 'center';
                betweenButtonDiv.style.alignItems = 'center';
                betweenButtonDiv.innerHTML = `
                    <button class="graph-add-plugin-between-btn" 
                            data-index="${index}"
                            style="pointer-events: auto; padding: 4px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; white-space: nowrap; background-color: #3b82f6; color: white; display: flex; align-items: center; gap: 4px; font-weight: 500;">
                        <svg style="width: 12px; height: 12px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                        </svg>
                        <span>Add Plugin</span>
                    </button>
                    <button class="graph-add-condition-between-btn" 
                            data-index="${index}"
                            style="pointer-events: auto; padding: 4px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; white-space: nowrap; background-color: #d97706; color: white; display: flex; align-items: center; gap: 4px; font-weight: 500;">
                        <svg style="width: 12px; height: 12px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                        </svg>
                        <span>Add Condition</span>
                    </button>
                `;
                betweenButtonFO.appendChild(betweenButtonDiv);
                
                betweenHoverArea.addEventListener('mouseenter', () => {
                    betweenButtonFO.style.opacity = '1';
                    betweenButtonFO.style.pointerEvents = 'auto';
                });
                
                betweenHoverArea.addEventListener('mouseleave', () => {
                    betweenButtonFO.style.opacity = '0';
                    betweenButtonFO.style.pointerEvents = 'none';
                });
                
                betweenButtonFO.addEventListener('mouseenter', () => {
                    betweenButtonFO.style.opacity = '1';
                    betweenButtonFO.style.pointerEvents = 'auto';
                });
                
                betweenButtonFO.addEventListener('mouseleave', () => {
                    betweenButtonFO.style.opacity = '0';
                    betweenButtonFO.style.pointerEvents = 'none';
                });
                
                g.appendChild(betweenButtonFO);
            }
            
            if (component.isBranchPoint) {
                // This is a conditional - render as branches
                const branches = component.branches;
                const branchCount = branches.length;
                
                // Store Y position before branches for connection lines
                const beforeBranchY = currentY;
                
                // Check if this is a multi-branch conditional (has else-if or else)
                const isMultiBranch = branchCount > 1;
                
                // Add extra spacing for multi-branch conditionals to account for branches spanning outward
                // Single-branch conditionals use normal spacing (same as two plugins)
                const conditionalSpacing = isMultiBranch ? verticalSpacing : 0;
                currentY += conditionalSpacing;
                
                // Calculate dynamic widths for each branch using recursive calculation
                const branchWidths = branches.map(branch => 
                    calculateBranchWidth(branch, nodeWidth, branchHorizontalSpacing)
                );
                
                // Recalculate total width and starting positions based on dynamic widths
                const totalBranchWidth = branchWidths.reduce((sum, w) => sum + w, 0) + 
                                        ((branchCount - 1) * branchHorizontalSpacing);
                const dynamicBranchStartX = filterStartX + (nodeWidth / 2) - (totalBranchWidth / 2);
                
                // Track the maximum Y position across all branches
                let maxBranchEndY = currentY;
                const branchEndPositions = []; // Track end Y position of each branch
                const buttonElements = []; // Store button elements to append after lines
                
                // Render each branch
                let cumulativeX = dynamicBranchStartX;
                branches.forEach((branch, branchIndex) => {
                    const branchWidth = branchWidths[branchIndex];
                    const branchX = cumulativeX;
                    let branchY = currentY; // Start at currentY (with conditional spacing applied)
                    const branchStartY = branchY; // Store start for background container
                    
                    // Draw line from previous plugin to this branch's condition node
                    if (index > 0 || processedComponents.input.length > 0) {
                        const line = createConnectionLine(
                            filterStartX + nodeWidth / 2, beforeBranchY,
                            branchX + branchWidth / 2, branchY,
                            false,
                            'filter',
                            index,
                            false
                        );
                        g.insertBefore(line, g.firstChild);
                    }
                    
                    // Create condition node (use dynamic branch width)
                    // Check if this conditional has an else block
                    const hasElse = branches.some(b => b.type === 'else');
                    const conditionNode = {
                        id: branch.id,
                        type: 'filter',
                        plugin: branch.type,
                        isConditional: true,
                        conditionText: branch.condition,
                        hasElse: hasElse,
                        isContinue: branch.isContinue || false,
                        config: {}
                    };
                    const conditionGroup = createNodeElement(conditionNode, branchX, branchY, branchWidth, nodeHeight, 'filter');
                    g.appendChild(conditionGroup);
                    
                    branchY += nodeHeight + verticalSpacing;
                    let branchYBeforeNested = branchY;
                    
                    // Render plugins in this branch vertically
                    branch.plugins.forEach((plugin, pluginIndex) => {
                        // Add hover area between plugins (not before first plugin)
                        if (pluginIndex > 0) {
                            const betweenY = branchY - verticalSpacing;
                            const betweenHeight = verticalSpacing;
                            
                            const betweenHoverArea = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                            betweenHoverArea.setAttribute('x', branchX - 12);
                            betweenHoverArea.setAttribute('y', betweenY);
                            betweenHoverArea.setAttribute('width', branchWidth + 24);
                            betweenHoverArea.setAttribute('height', betweenHeight);
                            betweenHoverArea.setAttribute('fill', 'transparent');
                            betweenHoverArea.style.cursor = 'pointer';
                            g.appendChild(betweenHoverArea);
                            
                            const betweenButtonFO = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
                            betweenButtonFO.setAttribute('x', branchX + (branchWidth / 2) - 95);
                            betweenButtonFO.setAttribute('y', betweenY + (betweenHeight / 2) - 15);
                            betweenButtonFO.setAttribute('width', '190');
                            betweenButtonFO.setAttribute('height', '30');
                            betweenButtonFO.setAttribute('overflow', 'visible');
                            betweenButtonFO.style.opacity = '0';
                            betweenButtonFO.style.pointerEvents = 'none';
                            betweenButtonFO.style.transition = 'opacity 0.15s ease';
                            
                            const betweenButtonDiv = document.createElement('div');
                            betweenButtonDiv.style.display = 'flex';
                            betweenButtonDiv.style.gap = '6px';
                            betweenButtonDiv.style.justifyContent = 'center';
                            betweenButtonDiv.style.alignItems = 'center';
                            
                            const blockType = branch.type === 'else_if' ? 'else_if' : (branch.type === 'else' ? 'else' : 'if');
                            const elseIfIndex = branch.type === 'else_if' ? branchIndex - 1 : null;
                            
                            betweenButtonDiv.innerHTML = `
                                <button class="graph-add-plugin-to-branch-btn" 
                                        data-component-id="${component.id}"
                                        data-block-type="${blockType}"
                                        data-elseif-index="${elseIfIndex}"
                                        data-index="${pluginIndex}"
                                        style="pointer-events: auto; padding: 4px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; white-space: nowrap; background-color: #3b82f6; color: white; display: flex; align-items: center; gap: 4px; font-weight: 500;">
                                    <svg style="width: 12px; height: 12px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                                    </svg>
                                    <span>Add Plugin</span>
                                </button>
                                <button class="graph-add-condition-to-branch-btn"
                                        data-component-id="${component.id}"
                                        data-block-type="${blockType}"
                                        data-elseif-index="${elseIfIndex}"
                                        data-index="${pluginIndex}"
                                        style="pointer-events: auto; padding: 4px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; white-space: nowrap; background-color: #d97706; color: white; display: flex; align-items: center; gap: 4px; font-weight: 500;">
                                    <svg style="width: 12px; height: 12px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                                    </svg>
                                    <span>Add Condition</span>
                                </button>
                            `;
                            betweenButtonFO.appendChild(betweenButtonDiv);
                            
                            betweenHoverArea.addEventListener('mouseenter', () => {
                                betweenButtonFO.style.opacity = '1';
                                betweenButtonFO.style.pointerEvents = 'auto';
                            });
                            
                            betweenHoverArea.addEventListener('mouseleave', () => {
                                betweenButtonFO.style.opacity = '0';
                                betweenButtonFO.style.pointerEvents = 'none';
                            });
                            
                            betweenButtonFO.addEventListener('mouseenter', () => {
                                betweenButtonFO.style.opacity = '1';
                                betweenButtonFO.style.pointerEvents = 'auto';
                            });
                            
                            betweenButtonFO.addEventListener('mouseleave', () => {
                                betweenButtonFO.style.opacity = '0';
                                betweenButtonFO.style.pointerEvents = 'none';
                            });
                            
                            g.appendChild(betweenButtonFO);
                        }
                        
                        // Draw line from condition node to first plugin, or from previous plugin to next
                        if (pluginIndex === 0) {
                            // Line from condition node to first plugin
                            const blockType = branch.type === 'else_if' ? 'else_if' : (branch.type === 'else' ? 'else' : 'if');
                            const elseIfIndex = branch.type === 'else_if' ? branchIndex - 1 : null;
                            const line = createConnectionLine(
                                branchX + branchWidth / 2, branchY - verticalSpacing,
                                branchX + branchWidth / 2, branchY,
                                false,
                                'filter',
                                pluginIndex, // Use pluginIndex for insertion at this position
                                true, // Show buttons on connection lines within branches
                                component.id, // Pass component ID for data-component-id
                                blockType,
                                elseIfIndex
                            );
                            g.appendChild(line);
                        }
                        
                        // Check if this plugin is itself a branch point (nested conditional)
                        if (plugin.isBranchPoint) {
                            // Recursively render nested conditional as full branch layout
                            const nestedResult = renderNestedConditional(
                                g, plugin, branchX, branchY, branchWidth,
                                nodeWidth, nodeHeight, verticalSpacing, branchHorizontalSpacing,
                                index, component.id
                            );
                            branchY = nestedResult.endY;
                            
                            // Draw connection line to next plugin if there is one
                            if (pluginIndex < branch.plugins.length - 1) {
                                const nextY = branchY;
                                const blockType = branch.type === 'else_if' ? 'else_if' : (branch.type === 'else' ? 'else' : 'if');
                                const elseIfIndex = branch.type === 'else_if' ? branchIndex - 1 : null;
                                const line = createConnectionLine(
                                    branchX + branchWidth / 2, nestedResult.endY - verticalSpacing,
                                    branchX + branchWidth / 2, nextY,
                                    false,
                                    'filter',
                                    pluginIndex + 1, // Insert after the nested conditional
                                    true, // Show buttons on connection lines within branches
                                    component.id,
                                    blockType,
                                    elseIfIndex
                                );
                                g.appendChild(line);
                            }
                        } else {
                            // Regular plugin (use branch width)
                            const pluginGroup = createNodeElement(plugin, branchX, branchY, branchWidth, nodeHeight, 'filter');
                            g.appendChild(pluginGroup);
                            
                            // Draw line to next plugin in branch
                            if (pluginIndex < branch.plugins.length - 1) {
                                const nextY = branchY + nodeHeight + verticalSpacing;
                                const blockType = branch.type === 'else_if' ? 'else_if' : (branch.type === 'else' ? 'else' : 'if');
                                const elseIfIndex = branch.type === 'else_if' ? branchIndex - 1 : null;
                                const line = createConnectionLine(
                                    branchX + branchWidth / 2, branchY + nodeHeight,
                                    branchX + branchWidth / 2, nextY,
                                    false,
                                    'filter',
                                    pluginIndex + 1, // Insert after this plugin
                                    true, // Show buttons on connection lines within branches
                                    component.id,
                                    blockType,
                                    elseIfIndex
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
                    
                    // Add subtle background container for this branch (use dynamic width)
                    // Use branchY to include nested conditionals in the height calculation
                    const branchHeight = branchY - branchStartY;
                    const branchContainer = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                    branchContainer.setAttribute('x', branchX - 12);
                    branchContainer.setAttribute('y', branchStartY - 8);
                    branchContainer.setAttribute('width', branchWidth + 24);
                    branchContainer.setAttribute('height', branchHeight - verticalSpacing + 56);
                    branchContainer.setAttribute('rx', 8);
                    branchContainer.setAttribute('fill', 'rgba(0, 0, 0, 0.15)');
                    branchContainer.setAttribute('stroke', 'rgba(255, 255, 255, 0.05)');
                    branchContainer.setAttribute('stroke-width', 1);
                    branchContainer.setAttribute('data-branch-container', 'true');
                    branchContainer.setAttribute('data-branch-level', 'parent');
                    // Insert at beginning of group so it's behind everything
                    g.insertBefore(branchContainer, g.firstChild);
                    
                    // Add colored left border stripe based on branch type
                    const stripeColors = {
                        'if': '#22c55e',      // Green
                        'else_if': '#f59e0b', // Amber
                        'else': '#a855f7'     // Purple
                    };
                    const stripeColor = branch.isContinue ? '#3b82f6' : (stripeColors[branch.type] || '#22c55e');
                    
                    const branchBorder = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                    branchBorder.setAttribute('x', branchX - 12);
                    branchBorder.setAttribute('y', branchStartY - 8);
                    branchBorder.setAttribute('width', 4);
                    branchBorder.setAttribute('height', branchHeight - verticalSpacing + 56);
                    branchBorder.setAttribute('rx', 2);
                    branchBorder.setAttribute('fill', stripeColor);
                    branchBorder.setAttribute('data-branch-border', 'true');
                    // Insert after the container to maintain z-order
                    g.insertBefore(branchBorder, branchContainer.nextSibling);
                    
                    // Add buttons at bottom of branch (skip for continue branches)
                    const branchEndY = branchY - verticalSpacing;
                    
                    if (!branch.isContinue) {
                        // Determine the elseIfIndex based on branch type and index
                        let elseIfIndex = null;
                        let blockType = 'if';
                        
                        if (branch.type === 'else_if') {
                            blockType = 'else_if';
                            elseIfIndex = branchIndex - 1;
                        } else if (branch.type === 'else') {
                            blockType = 'else';
                        }
                        
                        // Calculate the index where new plugins should be added (at the end of this branch's plugins)
                        const pluginInsertIndex = branch.plugins ? branch.plugins.length : 0;
                        
                        // Add hover area for buttons at bottom of branch
                        const branchButtonHoverArea = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                        branchButtonHoverArea.setAttribute('x', branchX - 12);
                        branchButtonHoverArea.setAttribute('y', branchEndY);
                        branchButtonHoverArea.setAttribute('width', branchWidth + 24);
                        branchButtonHoverArea.setAttribute('height', 48);
                        branchButtonHoverArea.setAttribute('fill', 'transparent');
                        branchButtonHoverArea.style.cursor = 'pointer';
                        g.appendChild(branchButtonHoverArea);
                        
                        // Create buttons in foreignObject (hover-based, centered in branch width)
                        const branchButtonFO = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
                        branchButtonFO.setAttribute('x', branchX + (branchWidth / 2) - 95);
                        branchButtonFO.setAttribute('y', branchEndY + 10);
                        branchButtonFO.setAttribute('width', '190');
                        branchButtonFO.setAttribute('height', '30');
                        branchButtonFO.setAttribute('overflow', 'visible');
                        branchButtonFO.style.opacity = '0';
                        branchButtonFO.style.pointerEvents = 'none';
                        branchButtonFO.style.transition = 'opacity 0.15s ease';
                        
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
                                    data-index="${pluginInsertIndex}"
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
                                    data-index="${pluginInsertIndex}"
                                    style="pointer-events: auto; padding: 4px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; white-space: nowrap; background-color: #d97706; color: white; display: flex; align-items: center; gap: 4px; font-weight: 500;">
                                <svg style="width: 12px; height: 12px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                                </svg>
                                <span>Add Condition</span>
                            </button>
                        `;
                        branchButtonFO.appendChild(branchButtonDiv);
                        
                        // Show/hide buttons on hover
                        branchButtonHoverArea.addEventListener('mouseenter', () => {
                            branchButtonFO.style.opacity = '1';
                            branchButtonFO.style.pointerEvents = 'auto';
                        });
                        
                        branchButtonHoverArea.addEventListener('mouseleave', () => {
                            branchButtonFO.style.opacity = '0';
                            branchButtonFO.style.pointerEvents = 'none';
                        });
                        
                        branchButtonFO.addEventListener('mouseenter', () => {
                            branchButtonFO.style.opacity = '1';
                            branchButtonFO.style.pointerEvents = 'auto';
                        });
                        
                        branchButtonFO.addEventListener('mouseleave', () => {
                            branchButtonFO.style.opacity = '0';
                            branchButtonFO.style.pointerEvents = 'none';
                        });
                        
                        // Store button element to append later (after lines are drawn)
                        buttonElements.push(branchButtonFO);
                    }
                    
                    // Advance cumulativeX for next branch
                    cumulativeX += branchWidth + branchHorizontalSpacing;
                });
                
                // Move currentY to after all branches
                currentY = maxBranchEndY;
                
                // Add extra spacing after conditionals for better visual separation
                const conditionalExtraSpacing = 20;
                
                // If there's a next component, draw convergence lines from each branch to it
                if (index < processedComponents.filter.length - 1) {
                    const nextY = currentY + verticalSpacing + conditionalExtraSpacing;
                    
                    // For multi-branch conditionals, draw rejoining fork pattern
                    if (isMultiBranch) {
                        // Calculate the rejoin point (halfway between branches end and next component)
                        const rejoinY = currentY + (conditionalExtraSpacing / 2);
                        
                        // Recalculate branch positions for convergence lines
                        let convergenceCumulativeX = dynamicBranchStartX;
                        
                        // Draw vertical lines from each branch up to rejoin point
                        branches.forEach((branch, branchIndex) => {
                            const branchWidth = branchWidths[branchIndex];
                            const branchX = convergenceCumulativeX;
                            const branchEndY = branchEndPositions[branchIndex];
                            const branchCenterX = branchX + (branchWidth / 2);
                            
                            const verticalLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                            verticalLine.setAttribute('x1', branchCenterX);
                            verticalLine.setAttribute('y1', branchEndY);
                            verticalLine.setAttribute('x2', branchCenterX);
                            verticalLine.setAttribute('y2', rejoinY);
                            verticalLine.setAttribute('stroke', '#6b7280');
                            verticalLine.setAttribute('stroke-width', 2);
                            verticalLine.setAttribute('stroke-dasharray', '5,5');
                            g.appendChild(verticalLine);
                            
                            convergenceCumulativeX += branchWidth + branchHorizontalSpacing;
                        });
                        
                        // Draw horizontal line connecting all branches at rejoin point
                        const leftmostBranchCenterX = dynamicBranchStartX + (branchWidths[0] / 2);
                        const rightmostBranchCenterX = dynamicBranchStartX + branchWidths.reduce((sum, w, idx) => {
                            if (idx < branchCount - 1) {
                                return sum + w + branchHorizontalSpacing;
                            }
                            return sum + w;
                        }, 0) - branchWidths[branchCount - 1] + (branchWidths[branchCount - 1] / 2);
                        
                        const horizontalLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                        horizontalLine.setAttribute('x1', leftmostBranchCenterX);
                        horizontalLine.setAttribute('y1', rejoinY);
                        horizontalLine.setAttribute('x2', rightmostBranchCenterX);
                        horizontalLine.setAttribute('y2', rejoinY);
                        horizontalLine.setAttribute('stroke', '#6b7280');
                        horizontalLine.setAttribute('stroke-width', 2);
                        horizontalLine.setAttribute('stroke-dasharray', '5,5');
                        g.appendChild(horizontalLine);
                        
                        // Draw vertical line from rejoin point down to next component
                        const targetX = filterStartX + (nodeWidth / 2);
                        const finalVerticalLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                        finalVerticalLine.setAttribute('x1', targetX);
                        finalVerticalLine.setAttribute('y1', rejoinY);
                        finalVerticalLine.setAttribute('x2', targetX);
                        finalVerticalLine.setAttribute('y2', nextY);
                        finalVerticalLine.setAttribute('stroke', '#6b7280');
                        finalVerticalLine.setAttribute('stroke-width', 2);
                        finalVerticalLine.setAttribute('stroke-dasharray', '5,5');
                        g.appendChild(finalVerticalLine);
                    } else {
                        // Single branch: draw simple line from branch to next component
                        const branchWidth = branchWidths[0];
                        const branchX = dynamicBranchStartX;
                        const branchEndY = branchEndPositions[0];
                        
                        const line = createConnectionLine(
                            branchX + branchWidth / 2, branchEndY,
                            filterStartX + nodeWidth / 2, nextY,
                            false,
                            'filter',
                            index + 1,
                            false
                        );
                        g.appendChild(line);
                    }
                    
                    currentY = nextY;
                }
                
                // Append all button elements after lines are drawn (so buttons render on top)
                buttonElements.forEach(buttonElement => {
                    g.appendChild(buttonElement);
                });
                
                // Add hover area and buttons after the entire conditional for adding plugin/condition after it
                const afterConditionalY = currentY;
                const afterConditionalHoverHeight = 40;
                
                const afterConditionalHoverArea = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                afterConditionalHoverArea.setAttribute('x', filterStartX - 20);
                afterConditionalHoverArea.setAttribute('y', afterConditionalY);
                afterConditionalHoverArea.setAttribute('width', nodeWidth + 40);
                afterConditionalHoverArea.setAttribute('height', afterConditionalHoverHeight);
                afterConditionalHoverArea.setAttribute('fill', 'transparent');
                afterConditionalHoverArea.style.cursor = 'pointer';
                g.appendChild(afterConditionalHoverArea);
                
                const afterConditionalButtonFO = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
                afterConditionalButtonFO.setAttribute('x', filterStartX + (nodeWidth / 2) - 95);
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
                
                // Show/hide buttons on hover
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
                
                g.appendChild(afterConditionalButtonFO);
                
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
        
        // Add hover area and buttons after the last filter plugin
        if (processedComponents.filter.length > 0) {
            // Store the position right after the last filter for the connection line
            const lastFilterBottomY = currentY;
            
            // Position buttons right at the bottom of the last filter
            const afterLastFilterY = currentY - verticalSpacing;
            const afterLastFilterHeight = 40; // Just enough height for the buttons
            
            const afterLastFilterHoverArea = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            afterLastFilterHoverArea.setAttribute('x', filterStartX - 20);
            afterLastFilterHoverArea.setAttribute('y', afterLastFilterY);
            afterLastFilterHoverArea.setAttribute('width', nodeWidth + 40);
            afterLastFilterHoverArea.setAttribute('height', afterLastFilterHeight);
            afterLastFilterHoverArea.setAttribute('fill', 'transparent');
            afterLastFilterHoverArea.style.cursor = 'pointer';
            g.appendChild(afterLastFilterHoverArea);
            
            const afterLastFilterButtonFO = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
            afterLastFilterButtonFO.setAttribute('x', filterStartX + (nodeWidth / 2) - 95);
            afterLastFilterButtonFO.setAttribute('y', afterLastFilterY + 5);
            afterLastFilterButtonFO.setAttribute('width', '190');
            afterLastFilterButtonFO.setAttribute('height', '30');
            afterLastFilterButtonFO.setAttribute('overflow', 'visible');
            afterLastFilterButtonFO.style.opacity = '0';
            afterLastFilterButtonFO.style.pointerEvents = 'none';
            afterLastFilterButtonFO.style.transition = 'opacity 0.15s ease';
            
            const afterLastFilterButtonDiv = document.createElement('div');
            afterLastFilterButtonDiv.style.display = 'flex';
            afterLastFilterButtonDiv.style.gap = '6px';
            afterLastFilterButtonDiv.style.justifyContent = 'center';
            afterLastFilterButtonDiv.style.alignItems = 'center';
            afterLastFilterButtonDiv.innerHTML = `
                <button class="graph-add-plugin-btn" 
                        data-type="filter"
                        data-index="${processedComponents.filter.length}"
                        style="pointer-events: auto; padding: 4px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; white-space: nowrap; background-color: #3b82f6; color: white; display: flex; align-items: center; gap: 4px; font-weight: 500;">
                    <svg style="width: 12px; height: 12px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                    </svg>
                    <span>Add Plugin</span>
                </button>
                <button class="graph-add-condition-btn" 
                        data-type="filter"
                        data-index="${processedComponents.filter.length}"
                        style="pointer-events: auto; padding: 4px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; white-space: nowrap; background-color: #d97706; color: white; display: flex; align-items: center; gap: 4px; font-weight: 500;">
                    <svg style="width: 12px; height: 12px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                    </svg>
                    <span>Add Condition</span>
                </button>
            `;
            afterLastFilterButtonFO.appendChild(afterLastFilterButtonDiv);
            
            afterLastFilterHoverArea.addEventListener('mouseenter', () => {
                afterLastFilterButtonFO.style.opacity = '1';
                afterLastFilterButtonFO.style.pointerEvents = 'auto';
            });
            
            afterLastFilterHoverArea.addEventListener('mouseleave', () => {
                afterLastFilterButtonFO.style.opacity = '0';
                afterLastFilterButtonFO.style.pointerEvents = 'none';
            });
            
            afterLastFilterButtonFO.addEventListener('mouseenter', () => {
                afterLastFilterButtonFO.style.opacity = '1';
                afterLastFilterButtonFO.style.pointerEvents = 'auto';
            });
            
            afterLastFilterButtonFO.addEventListener('mouseleave', () => {
                afterLastFilterButtonFO.style.opacity = '0';
                afterLastFilterButtonFO.style.pointerEvents = 'none';
            });
            
            g.appendChild(afterLastFilterButtonFO);
        }
        
        // Don't add extra spacing here - currentY is already positioned after the last filter
        }
    }

    // Render Output section - always render, even if empty
    const hasOutputs = processedComponents.output.length > 0;
    if (true) {
        // Draw connection line from filter to output (only if filter has components AND output has components)
        if (processedComponents.filter.length > 0 && processedComponents.output.length > 0) {
            // Start line from bottom of last filter (currentY - verticalSpacing)
            const lineStartY = currentY - verticalSpacing;
            // Add spacing for the connection line
            currentY += 100;
            const lineEndY = currentY;
            const line = createConnectionLine(
                filterStartX + nodeWidth / 2, lineStartY,
                filterStartX + nodeWidth / 2, lineEndY,
                false,
                'output',
                0,
                false
            );
            g.appendChild(line);
        }
        
        const label = createSectionLabel('OUTPUT', filterStartX, currentY - 45, '#a855f7');
        g.appendChild(label);
        
        // If no outputs, show add button aligned left below label
        if (!hasOutputs) {
            const addButtonFO = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
            addButtonFO.setAttribute('x', filterStartX + (nodeWidth / 2) - 78);
            addButtonFO.setAttribute('y', currentY - 15);
            addButtonFO.setAttribute('width', '156');
            addButtonFO.setAttribute('height', '50');
            
            const addButtonDiv = document.createElement('div');
            addButtonDiv.className = 'flex justify-center gap-2';
            addButtonDiv.innerHTML = `
                <button class="px-4 py-2 text-sm bg-purple-600 hover:bg-purple-700 text-white rounded flex items-center gap-2 transition-colors shadow-lg whitespace-nowrap"
                        onclick="if(typeof PluginModal !== 'undefined') PluginModal.show('output')"
                        title="Add Output">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                    </svg>
                    <span>Add Output</span>
                </button>
            `;
            addButtonFO.appendChild(addButtonDiv);
            g.appendChild(addButtonFO);
            
            currentY += 150; // Space for empty OUTPUT section
        } else {
        
        processedComponents.output.forEach((component, index) => {
            // Add hover area between components (including before first component for output)
            if (index > 0 || index === 0) {
                const betweenY = index === 0 ? currentY - (verticalSpacing / 2) : currentY - verticalSpacing;
                const betweenHeight = index === 0 ? verticalSpacing / 2 : verticalSpacing;
                
                const betweenHoverArea = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                betweenHoverArea.setAttribute('x', filterStartX - 20);
                betweenHoverArea.setAttribute('y', betweenY);
                betweenHoverArea.setAttribute('width', nodeWidth + 40);
                betweenHoverArea.setAttribute('height', betweenHeight);
                betweenHoverArea.setAttribute('fill', 'transparent');
                betweenHoverArea.style.cursor = 'pointer';
                g.appendChild(betweenHoverArea);
                
                const betweenButtonFO = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
                betweenButtonFO.setAttribute('x', filterStartX + (nodeWidth / 2) - 95);
                betweenButtonFO.setAttribute('y', betweenY + (betweenHeight / 2) - 15);
                betweenButtonFO.setAttribute('width', '190');
                betweenButtonFO.setAttribute('height', '30');
                betweenButtonFO.setAttribute('overflow', 'visible');
                betweenButtonFO.style.opacity = '0';
                betweenButtonFO.style.pointerEvents = 'none';
                betweenButtonFO.style.transition = 'opacity 0.15s ease';
                
                const betweenButtonDiv = document.createElement('div');
                betweenButtonDiv.style.display = 'flex';
                betweenButtonDiv.style.gap = '6px';
                betweenButtonDiv.style.justifyContent = 'center';
                betweenButtonDiv.style.alignItems = 'center';
                betweenButtonDiv.innerHTML = `
                    <button class="graph-add-plugin-btn" 
                            data-type="output"
                            data-index="${index}"
                            style="pointer-events: auto; padding: 4px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; white-space: nowrap; background-color: #3b82f6; color: white; display: flex; align-items: center; gap: 4px; font-weight: 500;">
                        <svg style="width: 12px; height: 12px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                        </svg>
                        <span>Add Plugin</span>
                    </button>
                    <button class="graph-add-condition-btn" 
                            data-type="output"
                            data-index="${index}"
                            style="pointer-events: auto; padding: 4px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; white-space: nowrap; background-color: #d97706; color: white; display: flex; align-items: center; gap: 4px; font-weight: 500;">
                        <svg style="width: 12px; height: 12px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                        </svg>
                        <span>Add Condition</span>
                    </button>
                `;
                betweenButtonFO.appendChild(betweenButtonDiv);
                
                betweenHoverArea.addEventListener('mouseenter', () => {
                    betweenButtonFO.style.opacity = '1';
                    betweenButtonFO.style.pointerEvents = 'auto';
                });
                
                betweenHoverArea.addEventListener('mouseleave', () => {
                    betweenButtonFO.style.opacity = '0';
                    betweenButtonFO.style.pointerEvents = 'none';
                });
                
                betweenButtonFO.addEventListener('mouseenter', () => {
                    betweenButtonFO.style.opacity = '1';
                    betweenButtonFO.style.pointerEvents = 'auto';
                });
                
                betweenButtonFO.addEventListener('mouseleave', () => {
                    betweenButtonFO.style.opacity = '0';
                    betweenButtonFO.style.pointerEvents = 'none';
                });
                
                g.appendChild(betweenButtonFO);
            }
            
            if (component.isBranchPoint) {
                // This is a conditional - render as branches (same as filter section)
                const branches = component.branches;
                const branchCount = branches.length;
                
                const beforeBranchY = currentY;
                const isMultiBranch = branchCount > 1;
                const conditionalSpacing = isMultiBranch ? verticalSpacing : 0;
                currentY += conditionalSpacing;
                
                const branchWidths = branches.map(branch => 
                    calculateBranchWidth(branch, nodeWidth, branchHorizontalSpacing)
                );
                
                const totalBranchWidth = branchWidths.reduce((sum, w) => sum + w, 0) + 
                                        ((branchCount - 1) * branchHorizontalSpacing);
                const dynamicBranchStartX = filterStartX + (nodeWidth / 2) - (totalBranchWidth / 2);
                
                let maxBranchEndY = currentY;
                const branchEndPositions = [];
                const buttonElements = [];
                
                // Render each branch
                let cumulativeX = dynamicBranchStartX;
                branches.forEach((branch, branchIndex) => {
                    const branchWidth = branchWidths[branchIndex];
                    const branchX = cumulativeX;
                    let branchY = currentY;
                    const branchStartY = branchY;
                    
                    // Draw line from previous component to this branch's condition node
                    // For first output component (index 0), draw from filter section if it exists
                    // For subsequent components, draw from previous output
                    if (index === 0 && (processedComponents.filter.length > 0 || processedComponents.input.length > 0)) {
                        // First output component - draw from above (filter or input section)
                        const line = createConnectionLine(
                            filterStartX + nodeWidth / 2, beforeBranchY,
                            branchX + branchWidth / 2, branchY,
                            false,
                            'output',
                            index,
                            false
                        );
                        g.insertBefore(line, g.firstChild);
                    } else if (index > 0) {
                        // Subsequent output components - draw from previous output
                        const line = createConnectionLine(
                            filterStartX + nodeWidth / 2, beforeBranchY,
                            branchX + branchWidth / 2, branchY,
                            false,
                            'output',
                            index,
                            false
                        );
                        g.insertBefore(line, g.firstChild);
                    }
                    
                    // Create condition node
                    const hasElse = branches.some(b => b.type === 'else');
                    const conditionNode = {
                        id: branch.id,
                        type: 'output',
                        plugin: branch.type,
                        isConditional: true,
                        conditionText: branch.condition,
                        hasElse: hasElse,
                        isContinue: branch.isContinue || false,
                        config: {}
                    };
                    const conditionGroup = createNodeElement(conditionNode, branchX, branchY, branchWidth, nodeHeight, 'output');
                    g.appendChild(conditionGroup);
                    
                    branchY += nodeHeight + verticalSpacing;
                    let branchYBeforeNested = branchY;
                    
                    // Render plugins in this branch vertically (same pattern as filter section)
                    branch.plugins.forEach((plugin, pluginIndex) => {
                        // Add hover area between plugins
                        if (pluginIndex > 0) {
                            const betweenY = branchY - verticalSpacing;
                            const betweenHeight = verticalSpacing;
                            
                            const betweenHoverArea = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                            betweenHoverArea.setAttribute('x', branchX - 12);
                            betweenHoverArea.setAttribute('y', betweenY);
                            betweenHoverArea.setAttribute('width', branchWidth + 24);
                            betweenHoverArea.setAttribute('height', betweenHeight);
                            betweenHoverArea.setAttribute('fill', 'transparent');
                            betweenHoverArea.style.cursor = 'pointer';
                            g.appendChild(betweenHoverArea);
                            
                            const betweenButtonFO = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
                            betweenButtonFO.setAttribute('x', branchX + (branchWidth / 2) - 95);
                            betweenButtonFO.setAttribute('y', betweenY + (betweenHeight / 2) - 15);
                            betweenButtonFO.setAttribute('width', '190');
                            betweenButtonFO.setAttribute('height', '30');
                            betweenButtonFO.setAttribute('overflow', 'visible');
                            betweenButtonFO.style.opacity = '0';
                            betweenButtonFO.style.pointerEvents = 'none';
                            betweenButtonFO.style.transition = 'opacity 0.15s ease';
                            
                            const betweenButtonDiv = document.createElement('div');
                            betweenButtonDiv.style.display = 'flex';
                            betweenButtonDiv.style.gap = '6px';
                            betweenButtonDiv.style.justifyContent = 'center';
                            betweenButtonDiv.style.alignItems = 'center';
                            
                            const blockType = branch.type === 'else_if' ? 'else_if' : (branch.type === 'else' ? 'else' : 'if');
                            const elseIfIndex = branch.type === 'else_if' ? branchIndex - 1 : null;
                            
                            betweenButtonDiv.innerHTML = `
                                <button class="graph-add-plugin-to-branch-btn" 
                                        data-component-id="${component.id}"
                                        data-block-type="${blockType}"
                                        data-elseif-index="${elseIfIndex}"
                                        data-index="${pluginIndex}"
                                        style="pointer-events: auto; padding: 4px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; white-space: nowrap; background-color: #3b82f6; color: white; display: flex; align-items: center; gap: 4px; font-weight: 500;">
                                    <svg style="width: 12px; height: 12px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                                    </svg>
                                    <span>Add Plugin</span>
                                </button>
                                <button class="graph-add-condition-to-branch-btn"
                                        data-component-id="${component.id}"
                                        data-block-type="${blockType}"
                                        data-elseif-index="${elseIfIndex}"
                                        data-index="${pluginIndex}"
                                        style="pointer-events: auto; padding: 4px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; white-space: nowrap; background-color: #d97706; color: white; display: flex; align-items: center; gap: 4px; font-weight: 500;">
                                    <svg style="width: 12px; height: 12px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                                    </svg>
                                    <span>Add Condition</span>
                                </button>
                            `;
                            betweenButtonFO.appendChild(betweenButtonDiv);
                            
                            betweenHoverArea.addEventListener('mouseenter', () => {
                                betweenButtonFO.style.opacity = '1';
                                betweenButtonFO.style.pointerEvents = 'auto';
                            });
                            
                            betweenHoverArea.addEventListener('mouseleave', () => {
                                betweenButtonFO.style.opacity = '0';
                                betweenButtonFO.style.pointerEvents = 'none';
                            });
                            
                            betweenButtonFO.addEventListener('mouseenter', () => {
                                betweenButtonFO.style.opacity = '1';
                                betweenButtonFO.style.pointerEvents = 'auto';
                            });
                            
                            betweenButtonFO.addEventListener('mouseleave', () => {
                                betweenButtonFO.style.opacity = '0';
                                betweenButtonFO.style.pointerEvents = 'none';
                            });
                            
                            g.appendChild(betweenButtonFO);
                        }
                        
                        // Draw line from condition node to first plugin
                        if (pluginIndex === 0) {
                            const blockType = branch.type === 'else_if' ? 'else_if' : (branch.type === 'else' ? 'else' : 'if');
                            const elseIfIndex = branch.type === 'else_if' ? branchIndex - 1 : null;
                            const line = createConnectionLine(
                                branchX + branchWidth / 2, branchY - verticalSpacing,
                                branchX + branchWidth / 2, branchY,
                                false,
                                'output',
                                pluginIndex,
                                true,
                                component.id,
                                blockType,
                                elseIfIndex
                            );
                            g.appendChild(line);
                        }
                        
                        // Check if this plugin is itself a branch point (nested conditional)
                        if (plugin.isBranchPoint) {
                            const nestedResult = renderNestedConditional(
                                g, plugin, branchX, branchY, branchWidth,
                                nodeWidth, nodeHeight, verticalSpacing, branchHorizontalSpacing,
                                index, component.id
                            );
                            branchY = nestedResult.endY;
                        } else {
                            const pluginGroup = createNodeElement(plugin, branchX, branchY, branchWidth, nodeHeight, 'output');
                            g.appendChild(pluginGroup);
                            branchY += nodeHeight + verticalSpacing;
                        }
                    });
                    
                    // Add subtle background container for this branch (output section)
                    const branchHeight = branchY - branchStartY;
                    const branchContainer = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                    branchContainer.setAttribute('x', branchX - 12);
                    branchContainer.setAttribute('y', branchStartY - 8);
                    branchContainer.setAttribute('width', branchWidth + 24);
                    branchContainer.setAttribute('height', branchHeight - verticalSpacing + 56);
                    branchContainer.setAttribute('rx', 8);
                    branchContainer.setAttribute('fill', 'rgba(0, 0, 0, 0.15)');
                    branchContainer.setAttribute('stroke', 'rgba(255, 255, 255, 0.05)');
                    branchContainer.setAttribute('stroke-width', 1);
                    branchContainer.setAttribute('data-branch-container', 'true');
                    branchContainer.setAttribute('data-branch-level', 'parent');
                    // Insert at beginning of group so it's behind everything
                    g.insertBefore(branchContainer, g.firstChild);
                    
                    // Add purple left border accent line (for output section)
                    const purpleBorder = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                    purpleBorder.setAttribute('x', branchX - 12);
                    purpleBorder.setAttribute('y', branchStartY - 8);
                    purpleBorder.setAttribute('width', 4);
                    purpleBorder.setAttribute('height', branchHeight - verticalSpacing + 56);
                    purpleBorder.setAttribute('rx', 2);
                    purpleBorder.setAttribute('fill', '#a855f7'); // Purple-500
                    purpleBorder.setAttribute('data-branch-border', 'true');
                    // Insert after the container to maintain z-order
                    g.insertBefore(purpleBorder, branchContainer.nextSibling);
                    
                    // Add buttons at bottom of branch (skip for continue branches)
                    const branchEndY = branchY - verticalSpacing;
                    
                    if (!branch.isContinue) {
                        const blockType = branch.type === 'else_if' ? 'else_if' : (branch.type === 'else' ? 'else' : 'if');
                        const elseIfIndex = branch.type === 'else_if' ? branchIndex - 1 : null;
                        const pluginInsertIndex = branch.plugins ? branch.plugins.length : 0;
                        
                        const branchButtonHoverArea = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                        branchButtonHoverArea.setAttribute('x', branchX - 12);
                        branchButtonHoverArea.setAttribute('y', branchEndY);
                        branchButtonHoverArea.setAttribute('width', branchWidth + 24);
                        branchButtonHoverArea.setAttribute('height', 48);
                        branchButtonHoverArea.setAttribute('fill', 'transparent');
                        branchButtonHoverArea.style.cursor = 'pointer';
                        g.appendChild(branchButtonHoverArea);
                        
                        const branchButtonFO = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
                        branchButtonFO.setAttribute('x', branchX + (branchWidth / 2) - 95);
                        branchButtonFO.setAttribute('y', branchEndY + 10);
                        branchButtonFO.setAttribute('width', '190');
                        branchButtonFO.setAttribute('height', '30');
                        branchButtonFO.setAttribute('overflow', 'visible');
                        branchButtonFO.style.opacity = '0';
                        branchButtonFO.style.pointerEvents = 'none';
                        branchButtonFO.style.transition = 'opacity 0.15s ease';
                        
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
                                    data-index="${pluginInsertIndex}"
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
                                    data-index="${pluginInsertIndex}"
                                    style="pointer-events: auto; padding: 4px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; white-space: nowrap; background-color: #d97706; color: white; display: flex; align-items: center; gap: 4px; font-weight: 500;">
                                <svg style="width: 12px; height: 12px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                                </svg>
                                <span>Add Condition</span>
                            </button>
                        `;
                        branchButtonFO.appendChild(branchButtonDiv);
                        
                        branchButtonHoverArea.addEventListener('mouseenter', () => {
                            branchButtonFO.style.opacity = '1';
                            branchButtonFO.style.pointerEvents = 'auto';
                        });
                        branchButtonHoverArea.addEventListener('mouseleave', () => {
                            branchButtonFO.style.opacity = '0';
                            branchButtonFO.style.pointerEvents = 'none';
                        });
                        branchButtonFO.addEventListener('mouseenter', () => {
                            branchButtonFO.style.opacity = '1';
                            branchButtonFO.style.pointerEvents = 'auto';
                        });
                        branchButtonFO.addEventListener('mouseleave', () => {
                            branchButtonFO.style.opacity = '0';
                            branchButtonFO.style.pointerEvents = 'none';
                        });
                        
                        buttonElements.push(branchButtonFO);
                    }
                    
                    branchEndPositions.push(branchY);
                    if (branchY > maxBranchEndY) {
                        maxBranchEndY = branchY;
                    }
                    
                    cumulativeX += branchWidth + branchHorizontalSpacing;
                });
                
                // Draw rejoining fork lines at the end of branches
                if (isMultiBranch) {
                    const convergenceY = maxBranchEndY + verticalSpacing;
                    
                    cumulativeX = dynamicBranchStartX;
                    branches.forEach((branch, branchIndex) => {
                        const branchWidth = branchWidths[branchIndex];
                        const branchCenterX = cumulativeX + (branchWidth / 2);
                        const branchEndY = branchEndPositions[branchIndex];
                        
                        const verticalLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                        verticalLine.setAttribute('x1', branchCenterX);
                        verticalLine.setAttribute('y1', branchEndY);
                        verticalLine.setAttribute('x2', branchCenterX);
                        verticalLine.setAttribute('y2', convergenceY - (verticalSpacing / 2));
                        verticalLine.setAttribute('stroke', '#6b7280');
                        verticalLine.setAttribute('stroke-width', 2);
                        verticalLine.setAttribute('stroke-dasharray', '5,5');
                        g.appendChild(verticalLine);
                        
                        cumulativeX += branchWidth + branchHorizontalSpacing;
                    });
                    
                    const leftmostBranchCenterX = dynamicBranchStartX + (branchWidths[0] / 2);
                    const rightmostBranchCenterX = dynamicBranchStartX + branchWidths.reduce((sum, w, idx) => {
                        if (idx < branchCount - 1) {
                            return sum + w + branchHorizontalSpacing;
                        }
                        return sum + w;
                    }, 0) - branchWidths[branchCount - 1] + (branchWidths[branchCount - 1] / 2);
                    
                    const horizontalLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                    horizontalLine.setAttribute('x1', leftmostBranchCenterX);
                    horizontalLine.setAttribute('y1', convergenceY - (verticalSpacing / 2));
                    horizontalLine.setAttribute('x2', rightmostBranchCenterX);
                    horizontalLine.setAttribute('y2', convergenceY - (verticalSpacing / 2));
                    horizontalLine.setAttribute('stroke', '#6b7280');
                    horizontalLine.setAttribute('stroke-width', 2);
                    horizontalLine.setAttribute('stroke-dasharray', '5,5');
                    g.appendChild(horizontalLine);
                    
                    const centerX = filterStartX + (nodeWidth / 2);
                    const finalVerticalLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                    finalVerticalLine.setAttribute('x1', centerX);
                    finalVerticalLine.setAttribute('y1', convergenceY - (verticalSpacing / 2));
                    finalVerticalLine.setAttribute('x2', centerX);
                    finalVerticalLine.setAttribute('y2', convergenceY);
                    finalVerticalLine.setAttribute('stroke', '#6b7280');
                    finalVerticalLine.setAttribute('stroke-width', 2);
                    finalVerticalLine.setAttribute('stroke-dasharray', '5,5');
                    g.appendChild(finalVerticalLine);
                    
                    currentY = convergenceY;
                } else {
                    currentY = maxBranchEndY;
                }
                
                buttonElements.forEach(btn => g.appendChild(btn));
                
            } else {
                // Regular plugin (not a conditional)
                const nodeGroup = createNodeElement(component, filterStartX, currentY, nodeWidth, nodeHeight, 'output');
                g.appendChild(nodeGroup);
                
                // Draw connection line to next component (if not the last one)
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
            }
        });
        }
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
        else: { fill: '#422006', stroke: '#f59e0b', text: '#fbbf24' },     // Same amber for else
        continue: { fill: '#1e3a8a', stroke: '#3b82f6', text: '#60a5fa' }  // Blue for continue
    };
    
    // Check if this is a conditional node or continue branch
    const isConditional = component.isConditional || component.plugin === 'if' || component.plugin === 'else_if' || component.plugin === 'else';
    const isContinue = component.isContinue || component.type === 'continue';
    const color = isContinue ? conditionalColors.continue : (isConditional ? conditionalColors[component.plugin] || conditionalColors.if : (colors[type] || colors.filter));

    // Build config summary
    const configItems = [];
    
    // For conditional nodes and continue branches, show the condition text
    if ((isConditional || isContinue) && component.conditionText) {
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

    // Add + else if and + else buttons at the bottom for conditional nodes
    if (isConditional && !isContinue) {
        const bottomButtonsY = y + nodeHeight - 35; // Position near bottom of node
        const bottomButtonsFO = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
        bottomButtonsFO.setAttribute('x', x);
        bottomButtonsFO.setAttribute('y', bottomButtonsY);
        bottomButtonsFO.setAttribute('width', width);
        bottomButtonsFO.setAttribute('height', '30');
        
        const bottomButtonsDiv = document.createElement('div');
        bottomButtonsDiv.className = 'flex gap-1 justify-center items-center px-2 opacity-0 transition-opacity graph-node-bottom-buttons';
        bottomButtonsDiv.style.pointerEvents = 'auto';
        
        const baseComponentId = component.id.split('_elseif_')[0].split('_else')[0];
        bottomButtonsDiv.innerHTML = `
            <button class="px-2 py-1 text-xs bg-yellow-600/80 text-white rounded hover:bg-yellow-600" 
                    onclick="event.stopPropagation(); if(typeof addElseIfToConditional === 'function') addElseIfToConditional('${baseComponentId}')"
                    title="Add else if"
                    style="pointer-events: auto;">
                + else if
            </button>
            ${!component.hasElse ? `
                <button class="px-2 py-1 text-xs bg-yellow-600/80 text-white rounded hover:bg-yellow-600" 
                        onclick="event.stopPropagation(); if(typeof addElseToConditional === 'function') addElseToConditional('${baseComponentId}')"
                        title="Add else"
                        style="pointer-events: auto;">
                    + else
                </button>
            ` : ''}
        `;
        
        bottomButtonsFO.appendChild(bottomButtonsDiv);
        group.appendChild(bottomButtonsFO);
    }
    
    // Add click handler to open config modal or condition prompt
    group.style.cursor = 'pointer';
    group.addEventListener('click', async (e) => {
        // Don't open modal if clicking on a button
        if (e.target.closest('button')) {
            return;
        }
        
        // Handle continue nodes - do nothing
        if (isContinue) {
            return;
        }
        
        // Handle if/else_if nodes - show condition prompt
        if (isConditional && (component.plugin === 'if' || component.plugin === 'else_if')) {
            if (typeof ConfirmationModal !== 'undefined' && typeof ConfirmationModal.prompt === 'function') {
                // Get the base component ID (remove _elseif_ or _else suffixes)
                const baseComponentId = component.id.split('_elseif_')[0].split('_else')[0];
                const baseComponent = findComponentById(baseComponentId);
                
                if (!baseComponent) {
                    console.error('Could not find base component:', baseComponentId);
                    return;
                }
                
                // Determine which condition we're editing
                let currentCondition = '';
                let elseIfIndex = null;
                
                if (component.plugin === 'if') {
                    currentCondition = baseComponent.config.condition || '';
                } else if (component.plugin === 'else_if') {
                    // Extract the else_if index from the component ID
                    const match = component.id.match(/_elseif_(\d+)$/);
                    if (match) {
                        elseIfIndex = parseInt(match[1]);
                        currentCondition = baseComponent.config.else_ifs?.[elseIfIndex]?.condition || '';
                    }
                }
                
                // Show the prompt
                const title = component.plugin === 'if' ? 'Edit If Condition' : 'Edit Else-If Condition';
                const newCondition = await ConfirmationModal.prompt(
                    `Enter the ${component.plugin === 'if' ? 'if' : 'else-if'} condition:`,
                    currentCondition,
                    title,
                    'e.g., [message] == "error"'
                );
                
                if (newCondition !== null && newCondition !== currentCondition) {
                    // Update the condition
                    if (component.plugin === 'if') {
                        baseComponent.config.condition = newCondition;
                    } else if (component.plugin === 'else_if' && elseIfIndex !== null) {
                        baseComponent.config.else_ifs[elseIfIndex].condition = newCondition;
                    }
                    
                    // Update the component and refresh UI
                    if (typeof updateComponent === 'function') {
                        updateComponent(baseComponent);
                    }
                }
            }
            return;
        }
        
        // Handle else nodes - show plugin config modal (no condition to edit)
        // Handle regular plugins - show plugin config modal
        if (typeof PluginConfigModal !== 'undefined') {
            PluginConfigModal.show(component);
        }
    });
    
    // Add hover effect on the rect
    group.addEventListener('mouseenter', () => {
        rect.setAttribute('fill', '#4b5563');
        // Show buttons in header
        const buttons = headerDiv.querySelector('.graph-node-buttons');
        if (buttons) buttons.style.opacity = '1';
        // Show buttons at bottom for conditionals
        if (isConditional && !isContinue) {
            const bottomButtons = group.querySelector('.graph-node-bottom-buttons');
            if (bottomButtons) bottomButtons.style.opacity = '1';
        }
    });
    group.addEventListener('mouseleave', () => {
        rect.setAttribute('fill', color.fill);
        // Hide buttons in header
        const buttons = headerDiv.querySelector('.graph-node-buttons');
        if (buttons) buttons.style.opacity = '0';
        // Hide buttons at bottom for conditionals
        if (isConditional && !isContinue) {
            const bottomButtons = group.querySelector('.graph-node-bottom-buttons');
            if (bottomButtons) bottomButtons.style.opacity = '0';
        }
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
function createConnectionLine(x1, y1, x2, y2, isAnimated = false, type = 'filter', index = 0, showButtons = true, componentId = null, blockType = null, elseIfIndex = null) {
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
    // If componentId is provided, create buttons for conditional branches with data-component-id
    // Otherwise, create buttons for top-level components with data-type/data-index
    if (componentId) {
        buttonDiv.innerHTML = `
            <button class="graph-add-plugin-to-branch-btn" 
                    data-component-id="${componentId}"
                    data-block-type="${blockType}"
                    data-elseif-index="${elseIfIndex}"
                    data-index="${index}"
                    style="pointer-events: auto; padding: 2px 6px; border: none; border-radius: 3px; font-size: 11px; cursor: pointer; display: flex; align-items: center; white-space: nowrap; height: 20px; background-color: #3b82f6; color: white;">
                <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="width: 12px; height: 12px; margin-right: 4px;">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                </svg>
                <span>Add Plugin</span>
            </button>
            <button class="graph-add-condition-to-branch-btn"
                    data-component-id="${componentId}"
                    data-block-type="${blockType}"
                    data-elseif-index="${elseIfIndex}"
                    data-index="${index}"
                    style="pointer-events: auto; padding: 2px 6px; border: none; border-radius: 3px; font-size: 11px; cursor: pointer; display: flex; align-items: center; white-space: nowrap; height: 20px; background-color: #f59e0b; color: white;">
                <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="width: 12px; height: 12px; margin-right: 4px;">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                </svg>
                <span>Add Condition</span>
            </button>
        `;
    } else {
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
    }
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
        // Handle Add Plugin button between components
        if (e.target.closest('.graph-add-plugin-between-btn')) {
            const btn = e.target.closest('.graph-add-plugin-between-btn');
            const index = parseInt(btn.dataset.index);
            
            if (typeof showPluginModal === 'function') {
                showPluginModal('filter', index);
            }
        }
        
        // Handle Add Condition button between components
        if (e.target.closest('.graph-add-condition-between-btn')) {
            const btn = e.target.closest('.graph-add-condition-between-btn');
            const index = parseInt(btn.dataset.index);
            
            if (typeof addConditionAtPosition === 'function') {
                addConditionAtPosition('filter', index);
            }
        }
        
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
            const index = parseInt(btn.dataset.index);
            
            console.log('[GRAPH] Add Plugin button clicked:', {componentId, blockType, elseIfIndex, index});
            
            if (typeof addPluginToConditional === 'function') {
                addPluginToConditional(componentId, blockType, elseIfIndex, index);
            }
        }
        
        // Handle Add Condition button at bottom of branch
        if (e.target.closest('.graph-add-condition-to-branch-btn')) {
            const btn = e.target.closest('.graph-add-condition-to-branch-btn');
            const componentId = btn.dataset.componentId;
            const blockType = btn.dataset.blockType;
            const elseIfIndex = btn.dataset.elseifIndex !== 'null' ? parseInt(btn.dataset.elseifIndex) : null;
            const index = btn.dataset.index !== undefined ? parseInt(btn.dataset.index) : null;
            
            console.log('[GRAPH] Add Condition button clicked:', {componentId, blockType, elseIfIndex, index});
            
            // Find the conditional component
            const component = findComponentById(componentId);
            if (component && typeof addConditionToConditional === 'function') {
                // If index is provided, use it; otherwise add at the end
                let insertIndex = index;
                if (insertIndex === null) {
                    // Determine which plugin array to use to get the length
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
                    insertIndex = targetPlugins.length;
                }
                
                addConditionToConditional('filter', componentId, blockType, insertIndex, elseIfIndex);
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
window.renderGraphEditor = renderGraphEditor;
window.toggleGraphFullscreen = toggleGraphFullscreen;