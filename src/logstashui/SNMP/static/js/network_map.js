/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// D3 zoom behavior
let networkMapZoomBehavior = null;
let currentNetworkTransform = null;

// Store network topology data
let networkTopologyData = null;

// Track whether the last mouse interaction was a drag so we can ignore it as a click
let networkMapIsDragging = false;

/**
 * Initialize D3 zoom and pan behavior for network map
 */
function initializeNetworkMapZoom(svg) {
    const svgElement = d3.select(svg);
    
    // Create zoom behavior
    networkMapZoomBehavior = d3.zoom()
        .scaleExtent([0.1, 3]) // Allow zoom from 10% to 300%
        .on('zoom', (event) => {
            // Apply transform to the main group
            svgElement.select('g').attr('transform', event.transform);
            // Store current transform
            currentNetworkTransform = event.transform;
        });
    
    // Apply zoom behavior to SVG
    svgElement.call(networkMapZoomBehavior);
    
    // Apply initial transform if available
    if (currentNetworkTransform) {
        svgElement.call(networkMapZoomBehavior.transform, currentNetworkTransform);
    } else {
        // Center the canvas initially
        const svgRect = svg.getBoundingClientRect();
        const svgWidth = svgRect.width;
        const svgHeight = svgRect.height;
        
        // Center transform
        const initialTransform = d3.zoomIdentity.translate(svgWidth / 2, svgHeight / 2);
        svgElement.call(networkMapZoomBehavior.transform, initialTransform);
        currentNetworkTransform = initialTransform;
    }
    
    // Reset zoom on double-click
    svgElement.on('dblclick.zoom', () => {
        svgElement.transition()
            .duration(750)
            .call(networkMapZoomBehavior.transform, d3.zoomIdentity.translate(svgRect.width / 2, svgRect.height / 2));
    });
}

/**
 * Render the network topology map using D3
 */
function renderNetworkMap(graphData) {
    console.log('Rendering network map with graph data:', graphData);
    
    const containerElement = document.getElementById('networkMapContainer');
    
    // Create SVG container
    containerElement.innerHTML = `
        <div class="relative w-full" style="height: 600px;">
            <svg id="networkMapSvg" class="w-full h-full bg-gray-900 rounded-lg">
                <g id="networkMapGroup"></g>
            </svg>
            <div id="networkMapTooltip" class="absolute hidden bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white shadow-lg pointer-events-none z-50" style="max-width: 300px;">
                <div id="tooltipContent"></div>
            </div>
            <div class="absolute top-4 right-4 flex gap-2">
                <button onclick="showAdjacencyData()" class="px-3 py-2 bg-blue-700 hover:bg-blue-600 text-white rounded-lg text-sm flex items-center gap-2">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"></path>
                    </svg>
                    Show JSON
                </button>
                <button onclick="resetNetworkMapZoom()" class="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg text-sm">
                    Reset View
                </button>
            </div>
        </div>
    `;
    
    const svg = document.getElementById('networkMapSvg');
    const svgRect = svg.getBoundingClientRect();
    const width = svgRect.width;
    const height = svgRect.height;
    
    // Initialize zoom/pan
    initializeNetworkMapZoom(svg);
    
    // Check if we have graph data
    if (!graphData || !graphData.nodes || graphData.nodes.length === 0) {
        const g = d3.select('#networkMapGroup');
        g.append('text')
            .attr('x', 0)
            .attr('y', 0)
            .attr('text-anchor', 'middle')
            .attr('fill', '#9ca3af')
            .attr('font-size', '16px')
            .text('No network topology data available');
        return;
    }
    
    // Create force simulation
    const simulation = d3.forceSimulation(graphData.nodes)
        .force('link', d3.forceLink(graphData.edges)
            .id(d => d.id)
            .distance(150))
        .force('charge', d3.forceManyBody().strength(-300))
        .force('center', d3.forceCenter(0, 0))
        .force('collision', d3.forceCollide().radius(50));
    
    const g = d3.select('#networkMapGroup');
    
    // Get tooltip element
    const tooltip = document.getElementById('networkMapTooltip');
    const tooltipContent = document.getElementById('tooltipContent');
    
    // Create edges (links)
    const link = g.append('g')
        .attr('class', 'links')
        .selectAll('line')
        .data(graphData.edges)
        .enter()
        .append('line')
        .attr('stroke', '#6b7280')
        .attr('stroke-width', 2)
        .style('cursor', 'pointer')
        .on('mouseenter', function(event, d) {
            // Highlight the line on hover
            d3.select(this)
                .attr('stroke', '#60a5fa')
                .attr('stroke-width', 3);
            
            // Show tooltip
            const sourceDevice = d.source.id || d.source;
            const targetDevice = d.target.id || d.target;
            tooltipContent.innerHTML = `
                <div class="font-semibold mb-1">Connection</div>
                <div class="text-gray-300 mb-2">
                    <div>${sourceDevice}</div>
                    <div class="text-xs text-gray-400 ml-2">└─ ${d.source_interface}</div>
                    <div class="text-center text-blue-400 my-1">↕</div>
                    <div>${targetDevice}</div>
                    <div class="text-xs text-gray-400 ml-2">└─ ${d.target_interface}</div>
                </div>
                ${d.platform ? `<div class="text-xs text-gray-400 border-t border-gray-600 pt-1 mt-1">Platform: ${d.platform}</div>` : ''}
            `;
            tooltip.classList.remove('hidden');
        })
        .on('mousemove', function(event) {
            // Position tooltip near cursor
            const containerRect = containerElement.getBoundingClientRect();
            tooltip.style.left = (event.clientX - containerRect.left + 15) + 'px';
            tooltip.style.top = (event.clientY - containerRect.top + 15) + 'px';
        })
        .on('mouseleave', function(event, d) {
            // Reset the line style
            d3.select(this)
                .attr('stroke', '#6b7280')
                .attr('stroke-width', 2);
            
            // Hide tooltip
            tooltip.classList.add('hidden');
        });
    
    // Create nodes
    const node = g.append('g')
        .attr('class', 'nodes')
        .selectAll('g')
        .data(graphData.nodes)
        .enter()
        .append('g')
        .call(d3.drag()
            .on('start', dragStarted)
            .on('drag', dragged)
            .on('end', dragEnded));
    
    // Add circles to nodes with different styles for managed vs discovered-only
    node.append('circle')
        .attr('r', 20)
        .attr('fill', d => d.managed ? '#3b82f6' : '#6b7280')
        .attr('stroke', d => d.managed ? '#60a5fa' : '#9ca3af')
        .attr('stroke-width', 2)
        .attr('stroke-dasharray', d => d.managed ? '0' : '5,5')
        .style('cursor', d => d.managed ? 'pointer' : 'default');
    
    // Add device icon to nodes
    node.append('text')
        .attr('text-anchor', 'middle')
        .attr('dy', '0.35em')
        .attr('font-size', '20px')
        .attr('fill', '#ffffff')
        .attr('pointer-events', 'none')
        .text('🖧');
    
    // Add labels to nodes
    node.append('text')
        .attr('text-anchor', 'middle')
        .attr('dy', '35px')
        .attr('font-size', '12px')
        .attr('fill', '#e5e7eb')
        .attr('pointer-events', 'none')
        .text(d => d.id);
    
    // Add interface count badge
    node.append('circle')
        .attr('cx', 15)
        .attr('cy', -15)
        .attr('r', 10)
        .attr('fill', '#10b981')
        .attr('stroke', '#059669')
        .attr('stroke-width', 1);
    
    node.append('text')
        .attr('x', 15)
        .attr('y', -15)
        .attr('text-anchor', 'middle')
        .attr('dy', '0.35em')
        .attr('font-size', '10px')
        .attr('fill', '#ffffff')
        .attr('font-weight', 'bold')
        .attr('pointer-events', 'none')
        .text(d => d.interface_count);
    
    // Add tooltips on hover for nodes
    node
        .on('mouseenter', function(event, d) {
            const statusBadge = d.managed 
                ? '<span class="inline-block px-2 py-0.5 bg-blue-600 text-white text-xs rounded">Managed</span>'
                : '<span class="inline-block px-2 py-0.5 bg-gray-600 text-white text-xs rounded">Discovered Only</span>';
            
            tooltipContent.innerHTML = `
                <div class="font-semibold mb-1">${d.id}</div>
                <div class="mb-2">${statusBadge}</div>
                <div class="text-xs text-gray-400">
                    <div>Network: ${d.network}</div>
                    <div>Interfaces: ${d.interface_count}</div>
                </div>
            `;
            tooltip.classList.remove('hidden');
        })
        .on('mousemove', function(event) {
            const containerRect = containerElement.getBoundingClientRect();
            tooltip.style.left = (event.clientX - containerRect.left + 15) + 'px';
            tooltip.style.top = (event.clientY - containerRect.top + 15) + 'px';
        })
        .on('mouseleave', function() {
            tooltip.classList.add('hidden');
        });
    
    // Update positions on each tick
    simulation.on('tick', () => {
        link
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);
        
        node.attr('transform', d => `translate(${d.x},${d.y})`);
    });
    
    // Drag functions
    // We open the device panel on drag-end only when no actual dragging occurred,
    // distinguishing a simple click from a genuine node reposition.
    function dragStarted(event, d) {
        networkMapIsDragging = false;
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
    }
    
    function dragged(event, d) {
        networkMapIsDragging = true;
        d.fx = event.x;
        d.fy = event.y;
    }
    
    function dragEnded(event, d) {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;

        // Treat a mousedown+mouseup with no movement as a click
        if (!networkMapIsDragging && d.managed) {
            createDeviceWindow(d);
        }
        networkMapIsDragging = false;
    }
    
    console.log(`Rendered ${graphData.nodes.length} nodes and ${graphData.edges.length} edges`);
}

/**
 * Reset network map zoom to default
 */
function resetNetworkMapZoom() {
    const svg = document.getElementById('networkMapSvg');
    if (!svg || !networkMapZoomBehavior) return;
    
    const svgRect = svg.getBoundingClientRect();
    const svgElement = d3.select(svg);
    
    svgElement.transition()
        .duration(750)
        .call(networkMapZoomBehavior.transform, d3.zoomIdentity.translate(svgRect.width / 2, svgRect.height / 2));
}

/**
 * Show adjacency data in a modal for debugging
 */
function showAdjacencyData() {
    if (!networkTopologyData) {
        console.warn('No adjacency data available');
        return;
    }
    
    // Create modal
    const modal = document.createElement('div');
    modal.id = 'adjacency-data-modal';
    modal.className = 'fixed inset-0 flex items-center justify-center z-[60] p-4';
    modal.innerHTML = `
        <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" onclick="document.getElementById('adjacency-data-modal').remove()"></div>
        <div class="bg-gray-800 rounded-lg w-full max-w-6xl max-h-[90vh] flex flex-col relative z-10 border border-gray-700">
            <div class="p-4 border-b border-gray-700 flex justify-between items-center">
                <h3 class="text-lg font-semibold text-white">Network Adjacency Data (Debug)</h3>
                <button onclick="document.getElementById('adjacency-data-modal').remove()" class="text-gray-400 hover:text-white">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
            </div>
            <div class="p-6 overflow-y-auto flex-grow">
                <div class="bg-gray-900 rounded-lg p-4">
                    <pre class="text-gray-300 text-xs overflow-auto">${JSON.stringify(networkTopologyData, null, 2)}</pre>
                </div>
            </div>
            <div class="p-4 border-t border-gray-700 flex justify-end">
                <button onclick="copyAdjacencyData()" class="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm flex items-center gap-2">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
                    </svg>
                    Copy to Clipboard
                </button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
}

/**
 * Copy adjacency data to clipboard
 */
function copyAdjacencyData() {
    if (!networkTopologyData) return;
    
    const jsonString = JSON.stringify(networkTopologyData, null, 2);
    navigator.clipboard.writeText(jsonString).then(() => {
        // Show success feedback
        const btn = event.target.closest('button');
        const originalHTML = btn.innerHTML;
        btn.innerHTML = `
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
            </svg>
            Copied!
        `;
        btn.classList.add('bg-green-600');
        btn.classList.remove('bg-blue-600');
        
        setTimeout(() => {
            btn.innerHTML = originalHTML;
            btn.classList.remove('bg-green-600');
            btn.classList.add('bg-blue-600');
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy:', err);
    });
}

/**
 * Handle network map data from API
 */
function handleNetworkMapData(data) {
    console.log('Network map data received:', data);
    
    const loadingElement = document.getElementById('networkMapLoading');
    const containerElement = document.getElementById('networkMapContainer');
    const emptyElement = document.getElementById('networkMapEmpty');
    
    // Hide loading state
    loadingElement.classList.add('hidden');
    
    if (data.success && data.graph && data.graph.nodes && data.graph.nodes.length > 0) {
        // Store the data
        networkTopologyData = data.adjacency_table;
        
        // Show the map container
        containerElement.classList.remove('hidden');
        
        // Render the network map with graph data
        renderNetworkMap(data.graph);
    } else {
        // Show empty state
        emptyElement.classList.remove('hidden');
        
        if (data.errors && data.errors.length > 0) {
            console.warn('Errors fetching network map data:', data.errors);
        }
    }
}

// Listen for HTMX response
document.addEventListener('DOMContentLoaded', function() {
    const networkMapCard = document.getElementById('networkMapCard');
    
    if (networkMapCard) {
        networkMapCard.addEventListener('htmx:afterRequest', function(event) {
            if (event.detail.successful) {
                const data = JSON.parse(event.detail.xhr.responseText);
                handleNetworkMapData(data);
            } else {
                console.error('Error fetching network map data');
                document.getElementById('networkMapLoading').classList.add('hidden');
                document.getElementById('networkMapEmpty').classList.remove('hidden');
            }
        });
    }
});

// ──────────────────────────────────────────────────────────────────────────────
// Floating Device Detail Window System
// Each click on a managed node spawns (or focuses) an independent floating
// window that can be dragged and resized — same pattern as DocsIframeModal.
// ──────────────────────────────────────────────────────────────────────────────

let _dwTopZ      = 10010;  // z-index counter; brought-to-front windows get ++
let _dwSpawnIdx  = 0;      // stagger position counter

// Shared active-operation state (one drag/resize at a time across all windows)
let _dwActive   = null;   // window element currently being dragged/resized
let _dwOp       = null;   // 'drag' or resize-direction string (e.g. 'se', 'n')
let _dwStartX   = 0;
let _dwStartY   = 0;
let _dwStartW   = 0;
let _dwStartH   = 0;
let _dwStartL   = 0;
let _dwStartT   = 0;

// Single shared document-level mouse handlers (registered once)
document.addEventListener('mousemove', function(e) {
    if (!_dwActive || !_dwOp) return;

    const dx = e.clientX - _dwStartX;
    const dy = e.clientY - _dwStartY;

    if (_dwOp === 'drag') {
        _dwActive.style.left = (_dwStartL + dx) + 'px';
        _dwActive.style.top  = (_dwStartT + dy) + 'px';
    } else {
        let newW = _dwStartW, newH = _dwStartH, newL = _dwStartL, newT = _dwStartT;
        if (_dwOp.includes('e')) newW = Math.max(400, _dwStartW + dx);
        if (_dwOp.includes('w')) { newW = Math.max(400, _dwStartW - dx); newL = _dwStartL + (_dwStartW - newW); }
        if (_dwOp.includes('s')) newH = Math.max(280, _dwStartH + dy);
        if (_dwOp.includes('n')) { newH = Math.max(280, _dwStartH - dy); newT = _dwStartT + (_dwStartH - newH); }
        _dwActive.style.width  = newW + 'px';
        _dwActive.style.height = newH + 'px';
        _dwActive.style.left   = newL + 'px';
        _dwActive.style.top    = newT + 'px';
    }
});

document.addEventListener('mouseup', function() {
    _dwActive = null;
    _dwOp     = null;
});

/**
 * Create (or focus) a floating device detail window for a network map node.
 * Re-clicking the same node brings its existing window to the front instead
 * of opening a duplicate.
 */
function createDeviceWindow(nodeData) {
    // Stable window ID derived from the device database ID or sanitised node name
    const safeId   = (nodeData.device_id || nodeData.id.replace(/[^a-z0-9]/gi, '_'));
    const windowId = 'device-window-' + safeId;

    // Bring existing window to front and bail early
    const existing = document.getElementById(windowId);
    if (existing) {
        existing.style.zIndex = ++_dwTopZ;
        return;
    }

    // Staggered spawn position (cycles every 8 windows)
    const offset    = (_dwSpawnIdx % 8) * 30;
    _dwSpawnIdx++;
    const spawnTop  = 60 + offset;
    const spawnLeft = 60 + offset;

    // Status badge
    const badge = nodeData.managed
        ? `<span class="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-600/20 text-blue-300 border border-blue-500/30 rounded text-xs font-medium">
               <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                   <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                         d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
               </svg>Managed</span>`
        : `<span class="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-600/20 text-gray-400 border border-gray-500/30 rounded text-xs font-medium">Discovered Only</span>`;

    // Build window element
    const win = document.createElement('div');
    win.id        = windowId;
    win.className = 'device-window fixed bg-gray-800 rounded-lg border border-gray-700 shadow-2xl flex flex-col';
    win.style.cssText = `width:720px; height:580px; top:${spawnTop}px; left:${spawnLeft}px; z-index:${++_dwTopZ};`;

    win.innerHTML = `
        <!-- 8-direction resize handles -->
        <div class="resize-handle resize-handle-n"></div>
        <div class="resize-handle resize-handle-e"></div>
        <div class="resize-handle resize-handle-s"></div>
        <div class="resize-handle resize-handle-w"></div>
        <div class="resize-handle resize-handle-ne"></div>
        <div class="resize-handle resize-handle-nw"></div>
        <div class="resize-handle resize-handle-se"></div>
        <div class="resize-handle resize-handle-sw"></div>

        <!-- Draggable title bar -->
        <div class="window-header px-3 py-2.5 border-b border-gray-700 flex items-center justify-between rounded-t-lg cursor-move shrink-0 bg-gray-700/60">
            <div class="flex items-center gap-2 min-w-0 flex-1">
                <svg class="w-4 h-4 text-blue-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/>
                </svg>
                <div class="min-w-0">
                    <div class="flex items-center gap-2 flex-wrap">
                        <span class="text-white font-semibold text-sm truncate">${escapeHtml(nodeData.id)}</span>
                        ${badge}
                    </div>
                    ${nodeData.network ? `<p class="text-xs text-gray-400 mt-0.5">${escapeHtml(nodeData.network)}</p>` : ''}
                </div>
            </div>
            <div class="flex items-center gap-0.5 shrink-0 ml-2">
                <button class="dw-maximize-btn p-1.5 text-gray-400 hover:text-white hover:bg-gray-600 rounded transition-colors" title="Maximize / Restore">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                              d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"/>
                    </svg>
                </button>
                <button class="dw-close-btn p-1.5 text-gray-400 hover:text-red-400 hover:bg-gray-600 rounded transition-colors" title="Close">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                    </svg>
                </button>
            </div>
        </div>

        <!-- Scrollable body (device preview rendered here) -->
        <div class="dw-body flex-1 overflow-y-auto min-h-0"></div>`;

    document.body.appendChild(win);

    // ── Drag (header mousedown) ────────────────────────────────────────────
    const header = win.querySelector('.window-header');
    header.addEventListener('mousedown', function(e) {
        if (e.target.closest('.dw-close-btn') || e.target.closest('.dw-maximize-btn')) return;
        _dwBringToFront(win);
        _dwActive = win;
        _dwOp     = 'drag';
        _dwStartX = e.clientX;
        _dwStartY = e.clientY;
        _dwStartL = win.offsetLeft;
        _dwStartT = win.offsetTop;
        e.preventDefault();
    });

    // ── Resize handles ────────────────────────────────────────────────────
    win.querySelectorAll('.resize-handle').forEach(function(handle) {
        handle.addEventListener('mousedown', function(e) {
            _dwBringToFront(win);
            const dir = Array.from(handle.classList)
                .find(c => c.startsWith('resize-handle-') && c !== 'resize-handle')
                .replace('resize-handle-', '');
            const rect = win.getBoundingClientRect();
            _dwActive  = win;
            _dwOp      = dir;
            _dwStartX  = e.clientX;
            _dwStartY  = e.clientY;
            _dwStartW  = win.offsetWidth;
            _dwStartH  = win.offsetHeight;
            _dwStartL  = rect.left;
            _dwStartT  = rect.top;
            // Pin position so resize math is consistent
            win.style.left = rect.left + 'px';
            win.style.top  = rect.top  + 'px';
            e.preventDefault();
            e.stopPropagation();
        });
    });

    // ── Bring to front on any click inside the window ─────────────────────
    win.addEventListener('mousedown', function() {
        _dwBringToFront(win);
    });

    // ── Close ─────────────────────────────────────────────────────────────
    win.querySelector('.dw-close-btn').addEventListener('click', function() {
        win.remove();
    });

    // ── Maximize / Restore ────────────────────────────────────────────────
    let _maximized = false;
    let _savedStyle = null;
    win.querySelector('.dw-maximize-btn').addEventListener('click', function() {
        if (!_maximized) {
            _savedStyle = { w: win.style.width, h: win.style.height, t: win.style.top, l: win.style.left };
            win.style.width  = '100vw';
            win.style.height = '100vh';
            win.style.top    = '0';
            win.style.left   = '0';
            _maximized = true;
        } else {
            win.style.width  = _savedStyle.w;
            win.style.height = _savedStyle.h;
            win.style.top    = _savedStyle.t;
            win.style.left   = _savedStyle.l;
            _maximized = false;
        }
    });

    // ── Load device content ───────────────────────────────────────────────
    _dwPopulateBody(nodeData, win.querySelector('.dw-body'));
}

/** Bump a window's z-index so it sits above all sibling windows. */
function _dwBringToFront(win) {
    win.style.zIndex = ++_dwTopZ;
}

/** Fill the scrollable body area of a device window with content. */
function _dwPopulateBody(nodeData, bodyEl) {
    if (nodeData.managed && nodeData.device_id) {
        // Loading spinner
        bodyEl.innerHTML = `
            <div class="flex items-center justify-center" style="min-height:200px;">
                <div class="text-center">
                    <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mb-3"></div>
                    <p class="text-gray-400 text-sm">Loading device details...</p>
                </div>
            </div>`;

        fetch(`/SNMP/GetDeviceVisualization/${nodeData.device_id}/`)
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    bodyEl.innerHTML = '';
                    // renderDevicePreview (snmp_device_visual_preview.js) needs a div
                    // with id="device-preview-content-{id}" as its insertion target.
                    const wrapper = document.createElement('div');
                    wrapper.id = `device-preview-content-${nodeData.device_id}`;
                    bodyEl.appendChild(wrapper);
                    renderDevicePreview(nodeData.device_id, data.device, data.visualizations);
                } else {
                    bodyEl.innerHTML = `<div class="p-8 text-center text-red-400"><p>${escapeHtml(data.error || 'Error loading device')}</p></div>`;
                }
            })
            .catch(err => {
                bodyEl.innerHTML = `<div class="p-8 text-center text-red-400"><p>Error: ${escapeHtml(err.message)}</p></div>`;
            });

    } else {
        // Discovered-only or managed-but-unmatched
        const isManaged = nodeData.managed;
        bodyEl.innerHTML = `
            <div class="flex items-center justify-center" style="min-height:200px;">
                <div class="text-center p-8">
                    <div class="inline-flex items-center justify-center w-14 h-14 bg-gray-700/50 rounded-full mb-4">
                        <svg class="w-7 h-7 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                  d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/>
                        </svg>
                    </div>
                    <h4 class="text-white font-semibold mb-2">
                        ${isManaged ? 'Device Not Found in Inventory' : 'Discovered Device'}
                    </h4>
                    <p class="text-gray-400 text-sm max-w-xs mx-auto">
                        ${isManaged
                            ? 'This device is sending SNMP data but could not be matched to a device in your inventory.'
                            : 'This device was discovered via CDP/LLDP but is not currently in your inventory.'}
                    </p>
                    <a href="/SNMP/Devices/"
                       class="mt-5 inline-block px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm transition-colors">
                        Add to Inventory
                    </a>
                </div>
            </div>`;
    }
}
