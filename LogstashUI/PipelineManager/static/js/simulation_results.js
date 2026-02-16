/**
 * Simulation Results Polling
 * Polls the GetSimulationResults endpoint and displays streaming results
 */

/**
 * Mark executed plugins in the editor with visual indicators
 */
function markExecutedPlugins(nodes, originalEvent) {
    // Clear any existing simulation badges and data indicators
    document.querySelectorAll('.simulation-executed-badge').forEach(badge => badge.remove());
    document.querySelectorAll('.simulation-data-indicator').forEach(indicator => indicator.remove());
    document.querySelectorAll('.simulation-data-flow').forEach(flow => flow.remove());
    
    // Remove any existing dimming
    document.querySelectorAll('.simulation-dimmed').forEach(el => {
        el.classList.remove('simulation-dimmed');
    });
    
    // Collect IDs of executed plugins
    const executedPluginIds = new Set();
    nodes.forEach(node => {
        if (node.id !== 'start') {
            let componentId = node.id;
            if (node.isDecisionPoint) {
                componentId = node.conditionalId;
            }
            executedPluginIds.add(componentId);
        }
    });
    
    // Dim all plugins that were NOT executed
    document.querySelectorAll('[data-id]').forEach(element => {
        const componentId = element.getAttribute('data-id');
        if (componentId && !executedPluginIds.has(componentId)) {
            element.classList.add('simulation-dimmed');
        }
    });
    
    // Add original event data flow indicator at the top of filter section
    if (originalEvent) {
        const filterContainer = document.getElementById('filterComponents');
        if (filterContainer && filterContainer.firstChild) {
            addOriginalEventIndicator(filterContainer, originalEvent);
        }
    }
    
    // Add badges and data indicators to executed plugins
    nodes.forEach(node => {
        // Skip the start node
        if (node.id === 'start') return;
        
        let componentId = node.id;
        
        // For decision point nodes, use the conditional ID
        if (node.isDecisionPoint) {
            componentId = node.conditionalId;
        }
        
        // Use data-id selector (not data-component-id)
        const componentElement = document.querySelector(`[data-id="${componentId}"]`);
        
        if (componentElement) {
            // Add badge indicator
            if (!componentElement.querySelector('.simulation-executed-badge')) {
                const badge = document.createElement('div');
                badge.className = 'simulation-executed-badge';
                badge.innerHTML = '✓';
                badge.title = 'Executed in simulation';
                badge.style.cssText = `
                    position: absolute;
                    top: 8px;
                    right: 8px;
                    width: 24px;
                    height: 24px;
                    background: linear-gradient(135deg, #10b981, #059669);
                    color: white;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 12px;
                    font-weight: bold;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
                    z-index: 10;
                    animation: badgePop 0.3s ease-out;
                `;
                
                componentElement.appendChild(badge);
            }
            
            // Add change indicators inside the plugin row
            if (!node.isDecisionPoint && node.hasChanges && node.changesText && node.changesText !== 'No changes') {
                const changesIndicator = document.createElement('div');
                changesIndicator.className = 'simulation-data-indicator';
                changesIndicator.style.cssText = `
                    margin-top: 8px;
                    padding: 8px;
                    background: rgba(16, 185, 129, 0.1);
                    border-left: 3px solid #10b981;
                    border-radius: 4px;
                    font-size: 11px;
                    color: #86efac;
                `;
                
                try {
                    const changes = JSON.parse(node.changesText);
                    let changesHtml = '<div style="font-weight: 600; margin-bottom: 4px;">Changes:</div>';
                    
                    if (changes.added && Object.keys(changes.added).length > 0) {
                        changesHtml += '<div style="color: #86efac; margin-bottom: 4px;">';
                        for (const [key, value] of Object.entries(changes.added)) {
                            const displayValue = typeof value === 'object' ? JSON.stringify(value) : value;
                            changesHtml += `<div style="margin-bottom: 2px;">+ <strong>${key}</strong>: ${displayValue}</div>`;
                        }
                        changesHtml += '</div>';
                    }
                    if (changes.modified && Object.keys(changes.modified).length > 0) {
                        changesHtml += '<div style="color: #fbbf24; margin-bottom: 4px;">';
                        for (const [key, value] of Object.entries(changes.modified)) {
                            const fromValue = typeof value.from === 'object' ? JSON.stringify(value.from) : value.from;
                            const toValue = typeof value.to === 'object' ? JSON.stringify(value.to) : value.to;
                            changesHtml += `<div style="margin-bottom: 2px;">~ <strong>${key}</strong>: <span style="text-decoration: line-through; opacity: 0.7;">${fromValue}</span> → ${toValue}</div>`;
                        }
                        changesHtml += '</div>';
                    }
                    if (changes.deleted && Object.keys(changes.deleted).length > 0) {
                        changesHtml += '<div style="color: #f87171;">';
                        for (const [key, value] of Object.entries(changes.deleted)) {
                            const displayValue = typeof value === 'object' ? JSON.stringify(value) : value;
                            changesHtml += `<div style="margin-bottom: 2px;">- <strong>${key}</strong>: ${displayValue}</div>`;
                        }
                        changesHtml += '</div>';
                    }
                    
                    changesIndicator.innerHTML = changesHtml;
                } catch (e) {
                    changesIndicator.innerHTML = '<div style="font-weight: 600;">Changes detected</div>';
                }
                
                componentElement.appendChild(changesIndicator);
            }
            
            // Add data flow indicator after this plugin (showing output state)
            if (!node.isDecisionPoint) {
                addDataFlowIndicator(componentElement, node);
            }
        }
    });
}

/**
 * Add original event indicator at the top of filter section
 */
function addOriginalEventIndicator(filterContainer, originalEvent) {
    const dataFlow = document.createElement('div');
    dataFlow.className = 'simulation-data-flow';
    dataFlow.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
        </svg>
        <span>Original Event</span>
    `;
    
    dataFlow.style.cssText = `
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 6px 12px;
        margin: 8px 0;
        background: linear-gradient(90deg, rgba(16, 185, 129, 0.1), rgba(5, 150, 105, 0.1));
        border: 1px solid rgba(16, 185, 129, 0.3);
        border-radius: 6px;
        color: #10b981;
        font-size: 11px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s ease;
    `;
    
    // Store the original event data
    dataFlow.dataset.eventJson = JSON.stringify(originalEvent, null, 2);
    
    // Add click to show sticky tooltip
    dataFlow.addEventListener('click', function(e) {
        e.stopPropagation();
        showDataFlowTooltip(e, this.dataset.eventJson, true); // sticky = true
    });
    
    // Add hover effects and tooltip
    dataFlow.addEventListener('mouseenter', function(e) {
        this.style.background = 'linear-gradient(90deg, rgba(16, 185, 129, 0.2), rgba(5, 150, 105, 0.2))';
        this.style.borderColor = 'rgba(16, 185, 129, 0.5)';
        this.style.transform = 'translateX(4px)';
        
        // Show hover tooltip (non-sticky)
        showDataFlowTooltip(e, this.dataset.eventJson, false);
    });
    
    dataFlow.addEventListener('mouseleave', function() {
        this.style.background = 'linear-gradient(90deg, rgba(16, 185, 129, 0.1), rgba(5, 150, 105, 0.1))';
        this.style.borderColor = 'rgba(16, 185, 129, 0.3)';
        this.style.transform = 'translateX(0)';
        
        // Hide hover tooltip (only if not sticky)
        const tooltip = document.getElementById('data-flow-tooltip');
        if (tooltip && tooltip.style.pointerEvents !== 'auto') {
            hideDataFlowTooltip();
        }
    });
    
    // Insert at the beginning of the filter container
    filterContainer.insertBefore(dataFlow, filterContainer.firstChild);
}

/**
 * Add a data flow indicator after a plugin showing the event state
 */
function addDataFlowIndicator(componentElement, node) {
    // Create the data flow icon
    const dataFlow = document.createElement('div');
    dataFlow.className = 'simulation-data-flow';
    dataFlow.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="3"/>
            <path d="M12 1v6m0 6v6m5.2-13.2l-4.2 4.2m0 6l4.2 4.2M23 12h-6m-6 0H1m18.2 5.2l-4.2-4.2m0-6l4.2-4.2"/>
        </svg>
        <span>Data Flow</span>
    `;
    
    dataFlow.style.cssText = `
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 6px 12px;
        margin: 8px 0;
        background: linear-gradient(90deg, rgba(59, 130, 246, 0.1), rgba(147, 51, 234, 0.1));
        border: 1px solid rgba(59, 130, 246, 0.3);
        border-radius: 6px;
        color: #60a5fa;
        font-size: 11px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s ease;
    `;
    
    // Store the full event snapshot data for tooltip (from node's eventJson if available)
    let eventData = 'No data available';
    if (node.eventJson) {
        // node.eventJson contains the full snapshot
        eventData = node.eventJson;
    }
    dataFlow.dataset.eventJson = eventData;
    
    // Add click to show sticky tooltip
    dataFlow.addEventListener('click', function(e) {
        e.stopPropagation();
        showDataFlowTooltip(e, this.dataset.eventJson, true); // sticky = true
    });
    
    // Add hover effects and tooltip
    dataFlow.addEventListener('mouseenter', function(e) {
        this.style.background = 'linear-gradient(90deg, rgba(59, 130, 246, 0.2), rgba(147, 51, 234, 0.2))';
        this.style.borderColor = 'rgba(59, 130, 246, 0.5)';
        this.style.transform = 'translateX(4px)';
        
        // Show hover tooltip (non-sticky)
        showDataFlowTooltip(e, this.dataset.eventJson, false);
    });
    
    dataFlow.addEventListener('mouseleave', function() {
        this.style.background = 'linear-gradient(90deg, rgba(59, 130, 246, 0.1), rgba(147, 51, 234, 0.1))';
        this.style.borderColor = 'rgba(59, 130, 246, 0.3)';
        this.style.transform = 'translateX(0)';
        
        // Hide hover tooltip (only if not sticky)
        const tooltip = document.getElementById('data-flow-tooltip');
        if (tooltip && tooltip.style.pointerEvents !== 'auto') {
            hideDataFlowTooltip();
        }
    });
    
    // Insert after the component element
    componentElement.parentNode.insertBefore(dataFlow, componentElement.nextSibling);
}

/**
 * Show tooltip with event JSON data
 * @param {Event} event - The mouse event
 * @param {string} eventJson - The JSON data to display
 * @param {boolean} sticky - If true, tooltip stays open until closed; if false, auto-hides on mouse out
 */
function showDataFlowTooltip(event, eventJson, sticky = false) {
    let tooltip = document.getElementById('data-flow-tooltip');
    
    if (!tooltip) {
        tooltip = document.createElement('div');
        tooltip.id = 'data-flow-tooltip';
        tooltip.style.cssText = `
            position: fixed;
            background: #1f2937;
            border: 1px solid #4b5563;
            border-radius: 8px;
            padding: 12px;
            max-width: 600px;
            max-height: 400px;
            overflow: auto;
            z-index: 10000;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5);
            font-family: monospace;
            font-size: 11px;
            color: #d1d5db;
            pointer-events: none;
            cursor: default;
        `;
        document.body.appendChild(tooltip);
    }
    
    if (sticky) {
        // Sticky mode: make interactive and draggable
        tooltip.style.pointerEvents = 'auto';
        tooltip.style.cursor = 'move';
        
        // Update content with close button
        tooltip.innerHTML = `
            <button onclick="hideDataFlowTooltip()" 
                    style="position: absolute; top: 8px; right: 8px; background: transparent; border: none; color: #9ca3af; cursor: pointer; font-size: 16px; padding: 0; width: 20px; height: 20px; display: flex; align-items: center; justify-content: center;"
                    onmouseover="this.style.color='#fff'" onmouseout="this.style.color='#9ca3af'">✕</button>
            <div style="font-weight: 600; color: #60a5fa; margin-bottom: 8px; padding-right: 24px;">Event State at This Point:</div>
            <pre style="margin: 0; white-space: pre-wrap; color: #86efac;">${eventJson}</pre>
        `;
        
        // Make draggable only when sticky
        makeDraggable(tooltip);
    } else {
        // Hover mode: non-interactive, no close button
        tooltip.style.pointerEvents = 'none';
        tooltip.style.cursor = 'default';
        
        tooltip.innerHTML = `
            <div style="font-weight: 600; color: #60a5fa; margin-bottom: 8px;">Event State at This Point:</div>
            <pre style="margin: 0; white-space: pre-wrap; color: #86efac;">${eventJson}</pre>
        `;
    }
    
    // Position the tooltip near the cursor
    const x = event.clientX + 10;
    const y = event.clientY + 10;
    
    tooltip.style.left = x + 'px';
    tooltip.style.top = y + 'px';
    tooltip.style.display = 'block';
}

/**
 * Make an element draggable
 */
function makeDraggable(element) {
    let pos1 = 0, pos2 = 0, pos3 = 0, pos4 = 0;
    
    element.onmousedown = dragMouseDown;
    
    function dragMouseDown(e) {
        // Don't drag if clicking on close button or scrollbar
        if (e.target.tagName === 'BUTTON' || e.target.closest('button')) {
            return;
        }
        
        e.preventDefault();
        pos3 = e.clientX;
        pos4 = e.clientY;
        document.onmouseup = closeDragElement;
        document.onmousemove = elementDrag;
    }
    
    function elementDrag(e) {
        e.preventDefault();
        pos1 = pos3 - e.clientX;
        pos2 = pos4 - e.clientY;
        pos3 = e.clientX;
        pos4 = e.clientY;
        element.style.top = (element.offsetTop - pos2) + 'px';
        element.style.left = (element.offsetLeft - pos1) + 'px';
    }
    
    function closeDragElement() {
        document.onmouseup = null;
        document.onmousemove = null;
    }
}

/**
 * Hide the data flow tooltip
 */
function hideDataFlowTooltip() {
    const tooltip = document.getElementById('data-flow-tooltip');
    if (tooltip) {
        tooltip.style.display = 'none';
    }
}

/**
 * Create a D3 force-directed graph visualization
 */
function createForceDirectedGraph(graphData) {
    const svg = d3.select("#pipeline-graph");
    const containerElement = document.getElementById("results-container");
    const height = containerElement.clientHeight || 100;
    
    // Calculate proper spacing and total width needed
    const nodeSpacing = 100; // Space between nodes (adjust to match node size)
    const padding = 50; // Padding on left and right
    
    // Find max step to calculate total width needed
    const maxStep = Math.max(...graphData.nodes.map(n => n.step));
    const totalWidth = (maxStep * nodeSpacing) + (padding * 2);
    
    // Set SVG width to accommodate all nodes
    const width = Math.max(totalWidth, containerElement.clientWidth);
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
    
    // Set fixed positions for nodes - completely static, no simulation
    console.log('Setting node positions:', {
        nodeCount: graphData.nodes.length,
        padding,
        nodeSpacing,
        height,
        nodes: graphData.nodes.map(n => ({ id: n.id, step: n.step }))
    });
    
    graphData.nodes.forEach((node, i) => {
        node.x = padding + (node.step * nodeSpacing); // Space nodes horizontally with proper spacing
        node.y = height / 2; // Center all nodes vertically for linear flow
        console.log(`Node ${node.id}: step=${node.step}, x=${node.x}, y=${node.y}`);
    });
    
    // Resolve link source/target to actual node objects
    graphData.links.forEach(link => {
        if (typeof link.source === 'string') {
            link.source = graphData.nodes.find(n => n.id === link.source);
        }
        if (typeof link.target === 'string') {
            link.target = graphData.nodes.find(n => n.id === link.target);
        }
    });
    
    console.log('Links resolved:', graphData.links.map(l => ({ 
        source: l.source.id, 
        target: l.target.id,
        sourceX: l.source.x,
        targetX: l.target.x
    })));
    
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
        .on("click", function(event, d) {
            event.stopPropagation();
            // Show sticky tooltip on click
            showLinkTooltip(event, d.eventJson, true);
        })
        .on("mouseover", function(event, d) {
            // Highlight the link
            d3.select(this.previousSibling)
                .attr("stroke", "#22c55e")
                .attr("stroke-width", 3);
            
            // Show hover tooltip
            showLinkTooltip(event, d.eventJson, false);
        })
        .on("mouseout", function(event, d) {
            // Reset link style
            d3.select(this.previousSibling)
                .attr("stroke", "#6b7280")
                .attr("stroke-width", 2);
            
            // Hide hover tooltip (only if not sticky)
            const tooltip = d3.select('.d3-link-tooltip');
            if (tooltip.style('pointer-events') === 'none') {
                hideLinkTooltip();
            }
        });
    
    // Create node groups (no drag behavior since positions are fixed)
    const node = container.append("g")
        .selectAll("g")
        .data(graphData.nodes)
        .enter().append("g");
    
    // Add shapes to nodes (circles for regular, hexagons for decision points)
    node.each(function(d) {
        const nodeGroup = d3.select(this);
        
        if (d.isConditional && d.isDecisionPoint) {
            // Hexagon shape for decision point nodes (path taken)
            const size = 20;
            const hexPath = `M ${size},0 L ${size/2},${size*0.866} L ${-size/2},${size*0.866} L ${-size},0 L ${-size/2},${-size*0.866} L ${size/2},${-size*0.866} Z`;
            
            nodeGroup.append("path")
                .attr("d", hexPath)
                .attr("fill", "#eab308")
                .attr("stroke", "#fbbf24")
                .attr("stroke-width", 2)
                .style("cursor", "pointer")
                .on("mouseover", function(event, d) {
                    d3.select(this)
                        .attr("stroke-width", 3)
                        .attr("fill", "#fbbf24");
                    showNodeTooltip(event, d);
                })
                .on("mouseout", function(event, d) {
                    d3.select(this)
                        .attr("stroke-width", 2)
                        .attr("fill", "#eab308");
                    hideNodeTooltip();
                });
        } else {
            // Circle for regular plugin nodes
            nodeGroup.append("circle")
                .attr("r", 18)
                .attr("fill", d.hasChanges ? "#16a34a" : "#4b5563")
                .attr("stroke", d.hasChanges ? "#22c55e" : "#6b7280")
                .attr("stroke-width", 2)
                .style("cursor", "pointer")
                .on("mouseover", function(event, d) {
                    d3.select(this)
                        .attr("stroke-width", 3)
                        .attr("r", 22);
                    showNodeTooltip(event, d);
                })
                .on("mouseout", function(event, d) {
                    d3.select(this)
                        .attr("stroke-width", 2)
                        .attr("r", 18);
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
    
    // Manually position all elements since we have no simulation
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
    
    // Add click handlers to scroll to component in editor
    node.on("click", function(event, d) {
        event.stopPropagation();
        
        // Extract the component ID from the node
        let componentId = d.id;
        
        // For decision point nodes, extract the original conditional ID
        if (d.isDecisionPoint) {
            componentId = d.conditionalId;
        }
        
        // Find the component in the editor using data-id
        const componentElement = document.querySelector(`[data-id="${componentId}"]`);
        
        if (componentElement) {
            // Scroll to the component
            componentElement.scrollIntoView({ 
                behavior: 'smooth', 
                block: 'center' 
            });
            
            // Apply the same glowing animation used when adding plugins
            componentElement.classList.add('newly-added');
            
            // Remove the animation class after it completes
            setTimeout(() => {
                componentElement.classList.remove('newly-added');
            }, 2000);
        } else if (componentId !== 'start') {
            // Don't warn about 'start' - it's a virtual node not in the editor
            console.warn(`Component not found: ${componentId}`);
        }
    });
    
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
        .style("z-index", "10000")
        .style("box-shadow", "0 10px 25px rgba(0, 0, 0, 0.5)")
        .style("font-family", "monospace")
        .style("font-size", "11px")
        .style("color", "#d1d5db")
        .style("pointer-events", "none");
    
    function showLinkTooltip(event, eventJson, sticky = false) {
        if (sticky) {
            // Make tooltip interactive and draggable when pinned
            linkTooltip.style("pointer-events", "auto")
                .style("cursor", "move");
            
            // Add close button for sticky tooltips
            const content = `
                <div style="position: relative; padding-right: 24px;">
                    <button onclick="d3.select('.d3-link-tooltip').style('visibility', 'hidden').style('pointer-events', 'none')" 
                            style="position: absolute; top: -8px; right: -8px; background: transparent; border: none; color: #9ca3af; cursor: pointer; font-size: 16px; padding: 0; width: 20px; height: 20px;"
                            onmouseover="this.style.color='#fff'" onmouseout="this.style.color='#9ca3af'">✕</button>
                    <div style="font-weight: 600; color: #9ca3af; margin-bottom: 0.5rem;">Event State:</div>
                    <pre style="margin: 0; white-space: pre-wrap; color: #86efac;">${eventJson}</pre>
                </div>
            `;
            linkTooltip.html(content);
            
            // Make draggable
            makeDraggable(linkTooltip.node());
        } else {
            linkTooltip.html(`
                <div style="font-weight: 600; color: #9ca3af; margin-bottom: 0.5rem;">Event State:</div>
                <pre style="margin: 0; white-space: pre-wrap; color: #86efac;">${eventJson}</pre>
            `);
        }
        
        linkTooltip
            .style("visibility", "visible")
            .style("left", (event.clientX + 10) + "px")
            .style("top", (event.clientY - 10) + "px");
    }
    
    function hideLinkTooltip() {
        linkTooltip.style("visibility", "hidden");
    }
    
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

// Global function to switch between overlay views
window.switchOverlayView = function(mode) {
    const resultsContainer = document.getElementById('results-container');
    const textViewContainer = document.getElementById('textViewContainer');
    const textViewContent = document.getElementById('textViewContent');
    
    if (mode === 'debugger') {
        resultsContainer.style.display = 'block';
        textViewContainer.style.display = 'none';
    } else if (mode === 'text') {
        resultsContainer.style.display = 'none';
        textViewContainer.style.display = 'block';
        
        // Generate text view if we have simulation data
        if (window.simulationData && textViewContent) {
            textViewContent.innerHTML = generateTextView(window.simulationData);
        }
    }
};

// Global function to generate text view HTML from simulation data
window.generateTextView = function(data) {
    if (!data || !data.nodes) return '<div class="text-gray-500 text-center py-8">No simulation data available</div>';
    
    let html = '';
    
    // Filter out the 'start' node and sort by step
    const pluginNodes = data.nodes.filter(n => n.id !== 'start').sort((a, b) => a.step - b.step);
    
    pluginNodes.forEach((node, index) => {
        const stepNum = index + 1;
        const pluginName = node.label;
        const hasChanges = node.hasChanges;
        const changesText = node.changesText || 'No changes';
        const eventJson = node.eventJson || 'No event data';
        
        html += `
            <div class="border border-gray-700 rounded-lg p-4 bg-gray-800">
                <div class="text-lg font-bold text-blue-400 mb-3 pb-2 border-b border-gray-700">
                    ~~~ Step ${stepNum}: ${pluginName} ~~~
                </div>
                
                <div class="mb-4">
                    <div class="text-sm font-semibold text-gray-400 mb-2">Plugin Changes:</div>
                    <pre class="text-xs ${hasChanges ? 'text-green-300' : 'text-gray-500'} bg-gray-900 p-3 rounded border border-gray-700 overflow-x-auto">${changesText}</pre>
                </div>
                
                <div>
                    <div class="text-sm font-semibold text-gray-400 mb-2">Event After Plugin Execution:</div>
                    <pre class="text-xs text-cyan-300 bg-gray-900 p-3 rounded border border-gray-700 overflow-x-auto">${eventJson}</pre>
                </div>
            </div>
        `;
    });
    
    return html || '<div class="text-gray-500 text-center py-8">No simulation data available</div>';
};

// Global function to toggle overlay expansion
window.toggleOverlayExpand = function() {
    const overlay = document.getElementById('simulation-overlay');
    const mainContent = document.querySelector('main');
    const expandBtn = document.getElementById('expandOverlayBtn');
    
    if (!overlay) return;
    
    const isExpanded = overlay.style.height === '100vh' || overlay.style.height === '100%';
    
    if (isExpanded) {
        // Collapse back to 150px
        overlay.style.height = '150px';
        if (mainContent) {
            mainContent.style.paddingTop = '150px';
        }
        if (expandBtn) {
            expandBtn.title = 'Expand to full screen';
            expandBtn.innerHTML = `<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"></path>
            </svg>`;
        }
    } else {
        // Expand to full screen
        overlay.style.height = '100vh';
        if (mainContent) {
            mainContent.style.paddingTop = '100vh';
        }
        if (expandBtn) {
            expandBtn.title = 'Collapse';
            expandBtn.innerHTML = `<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
            </svg>`;
        }
    }
};

// Document cycling functions
window.previousDocument = function() {
    if (!window.simulationDocuments || window.simulationDocuments.length <= 1) return;
    
    window.currentDocumentIndex--;
    if (window.currentDocumentIndex < 0) {
        window.currentDocumentIndex = window.simulationDocuments.length - 1;
    }
    
    switchToDocument(window.currentDocumentIndex);
};

window.nextDocument = function() {
    if (!window.simulationDocuments || window.simulationDocuments.length <= 1) return;
    
    window.currentDocumentIndex++;
    if (window.currentDocumentIndex >= window.simulationDocuments.length) {
        window.currentDocumentIndex = 0;
    }
    
    switchToDocument(window.currentDocumentIndex);
};

function switchToDocument(index) {
    console.log('=== Switching to document', index, '===');
    console.log('simulationRunIds array:', window.simulationRunIds);
    console.log('simulationDocuments array length:', window.simulationDocuments ? window.simulationDocuments.length : 0);
    
    // Check if we have a run_id for this document
    if (!window.simulationRunIds || !window.simulationRunIds[index]) {
        console.error('No run_id available for document', index);
        console.error('Available run_ids:', window.simulationRunIds);
        alert('Document ' + (index + 1) + ' is still being submitted. Please wait a moment and try again.');
        return;
    }
    
    const runId = window.simulationRunIds[index];
    console.log('Switching to run_id:', runId);
    
    // Initialize results cache if needed
    if (!window.simulationResultsCache) {
        window.simulationResultsCache = {};
    }
    
    // Check if we have cached results for this run_id
    if (window.simulationResultsCache[runId]) {
        console.log('Using cached results for run_id:', runId);
        renderCachedResults(runId, index);
    } else {
        console.log('No cached results, starting poller for run_id:', runId);
        console.log('Active pollers before switch:', window.activePollers ? Array.from(window.activePollers) : []);
        
        // Clear existing simulation artifacts
        clearSimulationArtifacts();
        
        // Update counter
        updateDocumentCounter();
        
        // Show loading indicator
        const loadingIndicator = document.getElementById('simulation-loading-indicator');
        if (loadingIndicator) {
            loadingIndicator.style.display = 'flex';
            console.log('Loading indicator shown');
        } else {
            console.error('Loading indicator not found');
        }
        
        // Hide view mode selector during reload
        const viewModeSelector = document.getElementById('viewModeSelector');
        if (viewModeSelector) {
            viewModeSelector.style.display = 'none';
        }
        
        // Start polling for this run_id
        console.log('Calling initSimulationResults for run_id:', runId);
        initSimulationResults(runId);
    }
}

function renderCachedResults(runId, index) {
    const cachedData = window.simulationResultsCache[runId];
    console.log('Rendering cached results for run_id:', runId, 'data:', cachedData);
    
    // Clear existing simulation artifacts
    clearSimulationArtifacts();
    
    // Update counter
    updateDocumentCounter();
    
    // Re-render the graph and badges with cached data
    if (cachedData.nodes && cachedData.links) {
        // Mark executed plugins
        if (cachedData.originalEvent) {
            markExecutedPlugins(cachedData.nodes, cachedData.originalEvent);
        }
        
        // Create the graph
        createForceDirectedGraph({ nodes: cachedData.nodes, links: cachedData.links });
        
        // Show view mode selector
        const viewModeSelector = document.getElementById('viewModeSelector');
        if (viewModeSelector) {
            viewModeSelector.style.display = 'flex';
        }
        
        // Hide loading indicator
        const loadingIndicator = document.getElementById('simulation-loading-indicator');
        if (loadingIndicator) {
            loadingIndicator.style.display = 'none';
        }
        
        console.log('Cached results rendered successfully');
    } else {
        console.error('Cached data missing nodes or links');
    }
}

function clearSimulationArtifacts() {
    // Clear graph
    const svg = d3.select("#pipeline-graph");
    if (svg) {
        svg.selectAll("*").remove();
    }
    
    // Remove all simulation badges and indicators from pipeline editor
    document.querySelectorAll('.simulation-executed-badge').forEach(badge => badge.remove());
    document.querySelectorAll('.simulation-data-indicator').forEach(indicator => indicator.remove());
    document.querySelectorAll('.simulation-data-flow').forEach(flow => flow.remove());
    
    // Remove dimming effect
    document.querySelectorAll('.simulation-dimmed').forEach(el => {
        el.classList.remove('simulation-dimmed');
    });
    
    // Close any open tooltips
    const dataFlowTooltip = document.getElementById('data-flow-tooltip');
    if (dataFlowTooltip) {
        dataFlowTooltip.remove();
    }
    
    const linkTooltip = document.querySelector('.d3-link-tooltip');
    if (linkTooltip) {
        linkTooltip.remove();
    }
    
    // Clear text view
    const textViewContent = document.getElementById('textViewContent');
    if (textViewContent) {
        textViewContent.innerHTML = '';
    }
}

function updateDocumentCounter() {
    const counter = document.getElementById('documentCounter');
    const prevBtn = document.getElementById('prevDocBtn');
    const nextBtn = document.getElementById('nextDocBtn');
    
    if (counter && window.simulationDocuments) {
        const total = window.simulationDocuments.length;
        const current = window.currentDocumentIndex + 1;
        counter.textContent = `${current} / ${total}`;
        
        // Enable/disable buttons
        if (prevBtn) prevBtn.disabled = total <= 1;
        if (nextBtn) nextBtn.disabled = total <= 1;
    }
}

// Global cleanup function
window.cleanupSimulation = function() {
    // Remove overlay
    const overlay = document.getElementById('simulation-overlay');
    if (overlay) {
        overlay.remove();
    }
    
    // Reset padding
    const mainContent = document.querySelector('main');
    if (mainContent) {
        mainContent.style.paddingTop = '0';
    }
    
    // Remove all simulation artifacts
    clearSimulationArtifacts();
    
    // Clear document storage
    window.simulationDocuments = [];
    window.currentDocumentIndex = 0;
};

function initSimulationResults(runId) {
    // Initialize active pollers set if it doesn't exist
    if (!window.activePollers) {
        window.activePollers = new Set();
    }
    
    // Prevent double polling for the same run_id
    if (window.activePollers.has(runId)) {
        console.log('Already polling for run_id:', runId, '- skipping duplicate');
        return;
    }
    window.activePollers.add(runId);
    console.log('Active pollers:', Array.from(window.activePollers));
    
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
                                                        eventJson: JSON.stringify(snapshot, null, 2),
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
                                    
                                    // Store simulation data globally for view switching
                                    window.simulationData = { nodes, links };
                                    
                                    // Cache results for this run_id
                                    if (!window.simulationResultsCache) {
                                        window.simulationResultsCache = {};
                                    }
                                    window.simulationResultsCache[runId] = {
                                        nodes: nodes,
                                        links: links,
                                        originalEvent: originalEvent
                                    };
                                    console.log('Cached results for run_id:', runId);
                                    
                                    // Check if we're in text mode (modal-based) or overlay mode
                                    const viewModeRadio = document.querySelector('input[name="viewMode"]:checked');
                                    const isTextMode = viewModeRadio && viewModeRadio.value === 'text';
                                    
                                    if (isTextMode) {
                                        // Text Mode: Skip graph creation, just dispatch event for modal
                                        window.dispatchEvent(new CustomEvent('simulationDataReady', { 
                                            detail: { nodes, links } 
                                        }));
                                    } else {
                                        // Overlay Mode: Mark plugins and create graph
                                        markExecutedPlugins(nodes, originalEvent);
                                        createForceDirectedGraph({ nodes, links });
                                        
                                        // Show view mode selector in overlay
                                        const viewModeSelector = document.getElementById('viewModeSelector');
                                        console.log('Looking for viewModeSelector:', viewModeSelector);
                                        if (viewModeSelector) {
                                            console.log('Setting viewModeSelector display to flex');
                                            viewModeSelector.style.display = 'flex';
                                            console.log('viewModeSelector display is now:', viewModeSelector.style.display);
                                        } else {
                                            console.error('viewModeSelector element not found in DOM');
                                        }
                                        
                                        // Show document navigation if multiple documents
                                        console.log('Checking for document navigation:', window.simulationDocuments ? window.simulationDocuments.length : 0, 'documents');
                                        if (window.simulationDocuments && window.simulationDocuments.length > 1) {
                                            const docNav = document.getElementById('documentNavigation');
                                            console.log('Document navigation element:', docNav);
                                            if (docNav) {
                                                docNav.style.display = 'flex';
                                                updateDocumentCounter();
                                                console.log('Navigation buttons shown');
                                            }
                                        } else {
                                            console.log('Not showing navigation - only', window.simulationDocuments ? window.simulationDocuments.length : 0, 'documents');
                                        }
                                        
                                        // Hide loading indicator
                                        const loadingIndicator = document.getElementById('simulation-loading-indicator');
                                        if (loadingIndicator) {
                                            loadingIndicator.style.display = 'none';
                                        }
                                        
                                        // Remove from active pollers
                                        if (window.activePollers) {
                                            window.activePollers.delete(runId);
                                            console.log('Polling complete for', runId, ', active pollers:', Array.from(window.activePollers));
                                        }
                                    }
                                } else {
                                    console.error('Components variable not accessible or snapshots missing');
                                }
                        }
                    });
                }
                
                // Stop polling if we received the final event
                if (receivedFinal) {
                    if (window.activePollers) {
                        window.activePollers.delete(runId);
                        console.log('Polling complete for', runId, ', active pollers:', Array.from(window.activePollers));
                    }
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


