/**
 * Simulation Results Polling
 * Polls the GetSimulationResults endpoint and displays streaming results
 */

/**
 * Create a D3 force-directed graph visualization
 */
function createForceDirectedGraph(graphData) {
    const svg = d3.select("#pipeline-graph");
    const width = document.getElementById("results-container").clientWidth;
    const height = 600;
    
    svg.attr("width", width).attr("height", height);
    
    // Clear any existing content
    svg.selectAll("*").remove();
    
    // Create a container group for zoom/pan
    const container = svg.append("g");
    
    // Add zoom behavior
    const zoom = d3.zoom()
        .scaleExtent([0.1, 4])
        .on("zoom", (event) => {
            container.attr("transform", event.transform);
        });
    
    svg.call(zoom);
    
    // Create arrow marker for links
    svg.append("defs").append("marker")
        .attr("id", "arrowhead")
        .attr("viewBox", "0 -5 10 10")
        .attr("refX", 25)
        .attr("refY", 0)
        .attr("markerWidth", 6)
        .attr("markerHeight", 6)
        .attr("orient", "auto")
        .append("path")
        .attr("d", "M0,-5L10,0L0,5")
        .attr("fill", "#6b7280");
    
    // Set initial positions for nodes in a left-to-right flow
    graphData.nodes.forEach((node, i) => {
        node.x = 100 + (node.step * 150); // Space nodes horizontally based on step
        node.y = height / 2; // Center all nodes vertically for linear flow
        
        // Pin the Start node to the left
        if (node.id === 'start') {
            node.fx = 100; // Fixed x position
            node.fy = height / 2; // Fixed y position
        }
    });
    
    // Create force simulation with horizontal bias
    const simulation = d3.forceSimulation(graphData.nodes)
        .force("link", d3.forceLink(graphData.links).id(d => d.id).distance(150).strength(1))
        .force("charge", d3.forceManyBody().strength(-500))
        .force("x", d3.forceX().x(d => {
            // Encourage horizontal positioning based on step
            return 100 + (d.step * 150);
        }).strength(0.5))
        .force("y", d3.forceY(height / 2).strength(0.3)) // Keep all nodes centered vertically
        .force("collision", d3.forceCollide().radius(50));
    
    // Create links with hover interaction
    const linkGroup = container.append("g")
        .selectAll("g")
        .data(graphData.links)
        .enter().append("g");
    
    // Add visible line
    const link = linkGroup.append("line")
        .attr("stroke", "#6b7280")
        .attr("stroke-width", 2)
        .attr("marker-end", "url(#arrowhead)");
    
    // Add invisible wider line for easier hovering
    const linkHover = linkGroup.append("line")
        .attr("stroke", "transparent")
        .attr("stroke-width", 10)
        .style("cursor", "pointer")
        .on("mouseover", function(event, d) {
            // Highlight the link
            d3.select(this.previousSibling)
                .attr("stroke", "#22c55e")
                .attr("stroke-width", 3);
            
            // Show tooltip
            showLinkTooltip(event, d.eventJson);
        })
        .on("mouseout", function(event, d) {
            // Reset link style
            d3.select(this.previousSibling)
                .attr("stroke", "#6b7280")
                .attr("stroke-width", 2);
            
            // Hide tooltip
            hideLinkTooltip();
        });
    
    // Create node groups
    const node = container.append("g")
        .selectAll("g")
        .data(graphData.nodes)
        .enter().append("g")
        .call(d3.drag()
            .on("start", dragstarted)
            .on("drag", dragged)
            .on("end", dragended));
    
    // Add shapes to nodes (circles for regular, hexagons for decision points)
    node.each(function(d) {
        const nodeGroup = d3.select(this);
        
        if (d.isConditional && d.isDecisionPoint) {
            // Hexagon shape for decision point nodes (path taken)
            const size = 35;
            const hexPath = `M ${size},0 L ${size/2},${size*0.866} L ${-size/2},${size*0.866} L ${-size},0 L ${-size/2},${-size*0.866} L ${size/2},${-size*0.866} Z`;
            
            nodeGroup.append("path")
                .attr("d", hexPath)
                .attr("fill", "#eab308")
                .attr("stroke", "#fbbf24")
                .attr("stroke-width", 3)
                .style("cursor", "pointer")
                .on("mouseover", function(event, d) {
                    d3.select(this)
                        .attr("stroke-width", 5)
                        .attr("fill", "#fbbf24");
                    showNodeTooltip(event, d);
                })
                .on("mouseout", function(event, d) {
                    d3.select(this)
                        .attr("stroke-width", 3)
                        .attr("fill", "#eab308");
                    hideNodeTooltip();
                });
        } else {
            // Circle for regular plugin nodes
            nodeGroup.append("circle")
                .attr("r", 30)
                .attr("fill", d.hasChanges ? "#16a34a" : "#4b5563")
                .attr("stroke", d.hasChanges ? "#22c55e" : "#6b7280")
                .attr("stroke-width", 2)
                .style("cursor", "pointer")
                .on("mouseover", function(event, d) {
                    d3.select(this)
                        .attr("stroke-width", 4)
                        .attr("r", 35);
                    showNodeTooltip(event, d);
                })
                .on("mouseout", function(event, d) {
                    d3.select(this)
                        .attr("stroke-width", 2)
                        .attr("r", 30);
                    hideNodeTooltip();
                });
        }
    });
    
    // Add text labels to nodes
    node.append("text")
        .text(d => d.label)
        .attr("text-anchor", "middle")
        .attr("dy", ".35em")
        .attr("fill", "white")
        .attr("font-size", "10px")
        .attr("font-weight", "bold")
        .style("pointer-events", "none");
    
    // Create tooltip container for links
    const linkTooltip = d3.select("body").append("div")
        .attr("class", "d3-link-tooltip")
        .style("position", "absolute")
        .style("visibility", "hidden")
        .style("background-color", "#1f2937")
        .style("border", "1px solid #4b5563")
        .style("border-radius", "0.5rem")
        .style("padding", "0.75rem")
        .style("max-width", "600px")
        .style("max-height", "400px")
        .style("overflow", "auto")
        .style("z-index", "1000")
        .style("box-shadow", "0 10px 15px -3px rgba(0, 0, 0, 0.3)")
        .style("font-size", "11px")
        .style("color", "#d1d5db");
    
    // Create tooltip container for nodes
    const nodeTooltip = d3.select("body").append("div")
        .attr("class", "d3-node-tooltip")
        .style("position", "absolute")
        .style("visibility", "hidden")
        .style("background-color", "#1f2937")
        .style("border", "1px solid #4b5563")
        .style("border-radius", "0.5rem")
        .style("padding", "0.75rem")
        .style("max-width", "600px")
        .style("max-height", "400px")
        .style("overflow", "auto")
        .style("z-index", "1000")
        .style("box-shadow", "0 10px 15px -3px rgba(0, 0, 0, 0.3)")
        .style("font-size", "11px")
        .style("color", "#d1d5db");
    
    function showLinkTooltip(event, eventJson) {
        linkTooltip.html(`<div style="font-weight: 600; color: #9ca3af; margin-bottom: 0.5rem;">Event State:</div><pre style="color: #86efac; white-space: pre-wrap; margin: 0;">${eventJson}</pre>`)
            .style("visibility", "visible")
            .style("left", (event.pageX + 10) + "px")
            .style("top", (event.pageY - 10) + "px");
    }
    
    function hideLinkTooltip() {
        linkTooltip.style("visibility", "hidden");
    }
    
    function showNodeTooltip(event, d) {
        let title, content;
        
        if (d.isConditional && d.isDecisionPoint) {
            // Decision point node - show which branch was taken
            title = `<div style="font-weight: 600; color: #fbbf24; margin-bottom: 0.5rem;">
                🔀 Conditional Decision Point
                <br/><span style="font-weight: 400; font-size: 10px; color: #9ca3af;">${d.id}</span>
            </div>`;
            content = `<div style="margin-bottom: 0.5rem;">
                <div style="font-weight: 600; color: #9ca3af; margin-bottom: 0.25rem;">Branch taken:</div>
                <div style="color: #fbbf24; font-weight: 600;">${d.label}</div>
            </div>
            <div style="margin-bottom: 0.5rem;">
                <div style="font-weight: 600; color: #9ca3af; margin-bottom: 0.25rem;">Total branches available:</div>
                <div style="color: #d1d5db;">${d.totalBranches}</div>
            </div>
            <div>
                <div style="font-weight: 600; color: #9ca3af; margin-bottom: 0.25rem;">Condition:</div>
                <pre style="color: #86efac; white-space: pre-wrap; margin: 0; font-size: 10px;">${d.condition}</pre>
            </div>`;
        } else {
            // Regular plugin node - show changes
            title = `<div style="font-weight: 600; color: #9ca3af; margin-bottom: 0.5rem;">Step ${d.step}: ${d.label}<br/><span style="font-weight: 400; font-size: 10px;">${d.id}</span></div>`;
            content = d.hasChanges 
                ? `<div style="font-weight: 600; color: #9ca3af; margin-bottom: 0.25rem;">Changes:</div><pre style="color: #86efac; white-space: pre-wrap; margin: 0;">${d.changesText}</pre>`
                : `<div style="color: #6b7280; font-style: italic;">No changes</div>`;
        }
        
        nodeTooltip.html(title + content)
            .style("visibility", "visible")
            .style("left", (event.pageX + 10) + "px")
            .style("top", (event.pageY - 10) + "px");
    }
    
    function hideNodeTooltip() {
        nodeTooltip.style("visibility", "hidden");
    }
    
    // Update positions on each tick
    simulation.on("tick", () => {
        link
            .attr("x1", d => d.source.x)
            .attr("y1", d => d.source.y)
            .attr("x2", d => d.target.x)
            .attr("y2", d => d.target.y);
        
        linkHover
            .attr("x1", d => d.source.x)
            .attr("y1", d => d.source.y)
            .attr("x2", d => d.target.x)
            .attr("y2", d => d.target.y);
        
        node.attr("transform", d => `translate(${d.x},${d.y})`);
    });
    
    // After simulation stabilizes, zoom to fit all nodes
    simulation.on("end", () => {
        // Calculate bounding box of all nodes
        let minX = Infinity, maxX = -Infinity;
        let minY = Infinity, maxY = -Infinity;
        
        graphData.nodes.forEach(node => {
            if (node.x < minX) minX = node.x;
            if (node.x > maxX) maxX = node.x;
            if (node.y < minY) minY = node.y;
            if (node.y > maxY) maxY = node.y;
        });
        
        // Add padding
        const padding = 100;
        minX -= padding;
        maxX += padding;
        minY -= padding;
        maxY += padding;
        
        // Calculate scale to fit
        const graphWidth = maxX - minX;
        const graphHeight = maxY - minY;
        const scale = Math.min(width / graphWidth, height / graphHeight, 1);
        
        // Calculate translation to center
        const translateX = (width - graphWidth * scale) / 2 - minX * scale;
        const translateY = (height - graphHeight * scale) / 2 - minY * scale;
        
        // Apply initial zoom
        svg.call(zoom.transform, d3.zoomIdentity
            .translate(translateX, translateY)
            .scale(scale));
    });
    
    // Drag functions
    function dragstarted(event, d) {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
    }
    
    function dragged(event, d) {
        d.fx = event.x;
        d.fy = event.y;
    }
    
    function dragended(event, d) {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
    }
}

/**
 * Render a component as a node in a grid with hover to show changes
 */
function renderComponentWithChanges(component, stepNumber, changes, hasChanges) {
    // Determine node color based on whether there are changes
    const nodeColor = hasChanges ? 'bg-green-600/20 border-green-500' : 'bg-gray-600/20 border-gray-500';
    const textColor = hasChanges ? 'text-green-300' : 'text-gray-400';
    
    // Format changes as JSON for tooltip
    let changesJson = '';
    if (hasChanges) {
        const changesObj = {};
        if (Object.keys(changes.added).length > 0) changesObj.added = changes.added;
        if (Object.keys(changes.modified).length > 0) changesObj.modified = changes.modified;
        if (Object.keys(changes.deleted).length > 0) changesObj.deleted = changes.deleted;
        changesJson = JSON.stringify(changesObj, null, 2);
    } else {
        changesJson = 'No changes';
    }
    
    // Escape for HTML attribute
    const escapedChanges = changesJson.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    
    return `
        <div class="simulation-node inline-block m-1 relative group">
            <div class="${nodeColor} border-2 rounded-lg p-3 cursor-pointer transition-all hover:scale-105 hover:shadow-lg" 
                 style="min-width: 120px; max-width: 150px;">
                <div class="text-center">
                    <div class="font-medium text-white text-xs mb-1">${component.plugin}</div>
                    <div class="text-xs ${textColor}">Step ${stepNumber}</div>
                    ${hasChanges ? '<div class="text-xs text-green-400 mt-1">✓ Changed</div>' : '<div class="text-xs text-gray-500 mt-1">No change</div>'}
                </div>
            </div>
            
            <!-- Hover tooltip -->
            <div class="absolute left-0 top-full mt-2 hidden group-hover:block z-50 bg-gray-900 border border-gray-600 rounded-lg p-3 shadow-xl" 
                 style="min-width: 300px; max-width: 500px; max-height: 400px; overflow-y: auto;">
                <div class="text-xs font-semibold text-gray-300 mb-2">
                    ${component.plugin} - ${component.id}
                </div>
                <pre class="text-xs text-green-300 whitespace-pre-wrap">${changesJson}</pre>
            </div>
        </div>
    `;
}

/**
 * Format config value for display
 */
function formatConfigValue(value) {
    if (value === null || value === undefined) {
        return '';
    }
    
    if (Array.isArray(value)) {
        if (value.length === 0) return '[]';
        const formattedItems = value.map(item => `"${String(item).replace(/"/g, '&quot;')}"`);
        const joined = formattedItems.join(', ');
        return joined.length > 50 ? joined.substring(0, 50) + '...' : joined;
    }
    
    if (typeof value === 'object') {
        const entries = Object.entries(value);
        if (entries.length === 0) return '{}';
        const formattedPairs = entries.map(([k, v]) => {
            if (typeof v === 'object' && v !== null) {
                return `"${k}" => {...}`;
            }
            return `"${k}" => "${String(v).replace(/"/g, '&quot;')}"`;
        });
        const joined = formattedPairs.join(', ');
        return joined.length > 50 ? joined.substring(0, 50) + '...' : joined;
    }
    
    const strValue = String(value).replace(/"/g, '&quot;');
    return strValue.length > 30 ? strValue.substring(0, 30) + '...' : strValue;
}

/**
 * Deep diff two objects and return only the changes
 * Returns an object with added, modified, and deleted fields
 */
function diffObjects(prev, curr, path = '') {
    const changes = {
        added: {},
        modified: {},
        deleted: {}
    };
    
    // Handle null/undefined cases
    if (prev === null || prev === undefined) {
        if (curr !== null && curr !== undefined) {
            changes.added[path || 'root'] = curr;
        }
        return changes;
    }
    if (curr === null || curr === undefined) {
        changes.deleted[path || 'root'] = prev;
        return changes;
    }
    
    // If both are primitives or arrays, compare directly
    if (typeof prev !== 'object' || typeof curr !== 'object' || Array.isArray(prev) || Array.isArray(curr)) {
        if (JSON.stringify(prev) !== JSON.stringify(curr)) {
            changes.modified[path] = { from: prev, to: curr };
        }
        return changes;
    }
    
    // Get all keys from both objects
    const prevKeys = new Set(Object.keys(prev));
    const currKeys = new Set(Object.keys(curr));
    
    // Check for deleted keys
    prevKeys.forEach(key => {
        if (!currKeys.has(key)) {
            const fullPath = path ? `${path}.${key}` : key;
            changes.deleted[fullPath] = prev[key];
        }
    });
    
    // Check for added and modified keys
    currKeys.forEach(key => {
        const fullPath = path ? `${path}.${key}` : key;
        
        if (!prevKeys.has(key)) {
            // Key was added
            changes.added[fullPath] = curr[key];
        } else {
            // Key exists in both, check if modified
            const prevVal = prev[key];
            const currVal = curr[key];
            
            if (typeof prevVal === 'object' && prevVal !== null && 
                typeof currVal === 'object' && currVal !== null &&
                !Array.isArray(prevVal) && !Array.isArray(currVal)) {
                // Recursively diff nested objects
                const nestedChanges = diffObjects(prevVal, currVal, fullPath);
                Object.assign(changes.added, nestedChanges.added);
                Object.assign(changes.modified, nestedChanges.modified);
                Object.assign(changes.deleted, nestedChanges.deleted);
            } else if (JSON.stringify(prevVal) !== JSON.stringify(currVal)) {
                changes.modified[fullPath] = { from: prevVal, to: currVal };
            }
        }
    });
    
    return changes;
}

function initSimulationResults(runId) {
    let pollCount = 0;
    const maxPolls = 120; // Poll for 120 * 250ms = 30 seconds max
    const pollInterval = 250; // Poll every 250ms for faster updates
    let receivedFinal = false; // Track if we've received the final event
    let originalEvent = null; // Store the original event for baseline comparison
    
    console.log('Starting simulation polling for run_id:', runId);
    
    function pollResults() {
        // Stop if we've received the final event
        if (receivedFinal) {
            console.log('Received final event, stopping polling');
            return;
        }
        
        if (pollCount >= maxPolls) {
            const stream = document.getElementById('results-stream');
            if (stream && stream.innerHTML.trim() === '') {
                stream.innerHTML = '<span class="text-yellow-400">No results received. Check Logstash logs.</span>';
            }
            return;
        }
        
        fetch(`/API/GetSimulationResults/?run_id=${encodeURIComponent(runId)}`)
            .then(response => response.json())
            .then(data => {
                console.log('Poll response:', data);
                console.log('Results count:', data.results ? data.results.length : 0);
                
                if (data.results && data.results.length > 0) {
                    console.log('Processing', data.results.length, 'events');
                    
                    data.results.forEach(event => {
                        // Check if this is the original event
                        if (event.step_id === 'original') {
                            console.log('Storing original event for baseline comparison');
                            originalEvent = event;
                        }
                        // Check if this is the final event
                        else if (event.step_id === 'final') {
                                console.log('Found final event, processing snapshots in order');
                                receivedFinal = true;
                                // Access the components variable from the page
                                if (typeof components !== 'undefined' && components.filter && event.snapshots) {
                                    let previousSnapshot = originalEvent; // Start with original event as baseline
                                    
                                    // Build graph data structure
                                    const nodes = [];
                                    const links = [];
                                    
                                    // Add starting node
                                    nodes.push({
                                        id: 'start',
                                        label: 'Start',
                                        step: 0,
                                        hasChanges: false,
                                        changesText: 'Original event',
                                        isConditional: false
                                    });
                                    
                                    // Track the last node ID that was actually added
                                    let lastNodeId = 'start';
                                    let stepNumber = 0;
                                    
                                    // Get conditional branches taken from the final event
                                    const conditionalBranches = event.conditional_branches || {};
                                    const conditionalConditions = event.conditional_conditions || {};
                                    
                                    // Helper function to recursively process plugins and conditionals
                                    function processPlugins(pluginsList, parentNodeId) {
                                        let currentNodeId = parentNodeId;
                                        
                                        pluginsList.forEach((filterPlugin) => {
                                            if (filterPlugin.plugin === 'if') {
                                                // This is a conditional - only show the path that was taken
                                                const conditionalId = filterPlugin.id;
                                                const branchTaken = conditionalBranches[conditionalId];
                                                
                                                // Find which branch was taken and get its details
                                                let takenBranchInfo = null;
                                                let takenBranchPlugins = null;
                                                
                                                if (branchTaken === 'if') {
                                                    takenBranchInfo = {
                                                        label: 'if',
                                                        condition: filterPlugin.config.condition || '',
                                                        branchType: 'if'
                                                    };
                                                    takenBranchPlugins = filterPlugin.config.plugins;
                                                } else if (branchTaken && branchTaken.startsWith('else_if_')) {
                                                    const elseIfIdx = parseInt(branchTaken.split('_')[2]);
                                                    const elseIf = filterPlugin.config.else_ifs[elseIfIdx];
                                                    takenBranchInfo = {
                                                        label: `else if #${elseIfIdx + 1}`,
                                                        condition: elseIf.condition || '',
                                                        branchType: branchTaken
                                                    };
                                                    takenBranchPlugins = elseIf.plugins;
                                                } else if (branchTaken === 'else') {
                                                    takenBranchInfo = {
                                                        label: 'else',
                                                        condition: 'default branch',
                                                        branchType: 'else'
                                                    };
                                                    takenBranchPlugins = filterPlugin.config.else.plugins;
                                                }
                                                
                                                // Create a single "decision point" node showing which branch was taken
                                                if (takenBranchInfo) {
                                                    stepNumber++;
                                                    const decisionNodeId = `${conditionalId}_decision`;
                                                    
                                                    // Count total branches for context
                                                    let totalBranches = 1; // if
                                                    if (filterPlugin.config.else_ifs) totalBranches += filterPlugin.config.else_ifs.length;
                                                    if (filterPlugin.config.else) totalBranches += 1;
                                                    
                                                    nodes.push({
                                                        id: decisionNodeId,
                                                        label: `✓ ${takenBranchInfo.label}`,
                                                        step: stepNumber,
                                                        hasChanges: false,
                                                        changesText: `Conditional evaluated (${totalBranches} branches)\nTook: ${takenBranchInfo.label}\nCondition: ${takenBranchInfo.condition}`,
                                                        condition: takenBranchInfo.condition,
                                                        isConditional: true,
                                                        isDecisionPoint: true,
                                                        conditionalId: conditionalId,
                                                        branchType: takenBranchInfo.branchType,
                                                        wasTaken: true,
                                                        totalBranches: totalBranches
                                                    });
                                                    
                                                    // Connect from previous node
                                                    links.push({
                                                        source: currentNodeId,
                                                        target: decisionNodeId,
                                                        eventJson: 'Conditional evaluation',
                                                        isConditional: true
                                                    });
                                                    
                                                    // Process plugins from the taken branch
                                                    if (takenBranchPlugins) {
                                                        currentNodeId = processPlugins(takenBranchPlugins, decisionNodeId);
                                                    } else {
                                                        currentNodeId = decisionNodeId;
                                                    }
                                                }
                                            } else {
                                                // Regular plugin
                                                const pluginId = filterPlugin.id;
                                                const snapshot = event.snapshots[pluginId];
                                                
                                                if (snapshot) {
                                                    stepNumber++;
                                                    
                                                    // Compare with previous snapshot (or original) and show only changes
                                                    const changes = diffObjects(previousSnapshot, snapshot);
                                                    
                                                    // Check if there are any changes
                                                    const hasChanges = Object.keys(changes.added).length > 0 ||
                                                                     Object.keys(changes.modified).length > 0 ||
                                                                     Object.keys(changes.deleted).length > 0;
                                                    
                                                    // Format changes for tooltip
                                                    let changesText = 'No changes';
                                                    if (hasChanges) {
                                                        const changesObj = {};
                                                        if (Object.keys(changes.added).length > 0) changesObj.added = changes.added;
                                                        if (Object.keys(changes.modified).length > 0) changesObj.modified = changes.modified;
                                                        if (Object.keys(changes.deleted).length > 0) changesObj.deleted = changes.deleted;
                                                        changesText = JSON.stringify(changesObj, null, 2);
                                                    }
                                                    
                                                    // Add node
                                                    nodes.push({
                                                        id: pluginId,
                                                        label: filterPlugin.plugin,
                                                        step: stepNumber,
                                                        hasChanges: hasChanges,
                                                        changesText: changesText,
                                                        isConditional: false
                                                    });
                                                    
                                                    // Add link from the last actual node that was added
                                                    // Include the snapshot (event state) for this link
                                                    links.push({
                                                        source: currentNodeId,
                                                        target: pluginId,
                                                        eventJson: JSON.stringify(snapshot, null, 2),
                                                        isConditional: false
                                                    });
                                                    
                                                    // Update current node ID for next iteration
                                                    currentNodeId = pluginId;
                                                    
                                                    // Update previous snapshot for next iteration
                                                    previousSnapshot = snapshot;
                                                }
                                            }
                                        });
                                        
                                        return currentNodeId;
                                    }
                                    
                                    // Process all filter plugins
                                    processPlugins(components.filter, lastNodeId);
                                    
                                    // Create the force-directed graph
                                    createForceDirectedGraph({ nodes, links });
                                } else {
                                    console.error('Components variable not accessible or snapshots missing');
                                }
                        }
                    });
                }
                
                // Stop polling if we received the final event
                if (receivedFinal) {
                    return;
                }
                
                pollCount++;
                setTimeout(pollResults, pollInterval);
            })
            .catch(error => {
                console.error('Error polling results:', error);
                pollCount++;
                setTimeout(pollResults, pollInterval);
            });
    }
    
    // Start polling immediately
    setTimeout(pollResults, 100);
}


