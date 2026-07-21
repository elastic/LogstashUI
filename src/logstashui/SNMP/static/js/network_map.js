/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// ─────────────────────────────────────────────────────────────────────────────
// Module-level state
// ─────────────────────────────────────────────────────────────────────────────

let networkMapZoomBehavior = null;
let currentNetworkTransform = null;
let networkTopologyData = null;       // full adjacency_table from last API response
let networkMapIsDragging = false;

// Network filter state — set of selected network IDs (integers); empty = show all
let _selectedNetworkIds = new Set();
// All available networks fetched from GetNetworksList
let _availableNetworks = [];

// Color scale shared between hulls and pills — assigned lazily per network label
const _networkColorScale = d3.scaleOrdinal([
    '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
    '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#6366f1',
]);
const _networkColorCache = {};

function networkColor(networkLabel) {
    if (!_networkColorCache[networkLabel]) {
        _networkColorCache[networkLabel] = _networkColorScale(networkLabel);
    }
    return _networkColorCache[networkLabel];
}

// Scale guardrail threshold
const NODE_WARN_THRESHOLD = 40;

// Fullscreen state
let _nmFullscreen = false;

// ─────────────────────────────────────────────────────────────────────────────
// Bootstrap — called once from inline <script> in network_map.html
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Entry point: load network list and map data in parallel so neither blocks
 * the other. The networks list feeds the filter dropdown; the map data renders
 * the topology. Both use the Django DB — no Elasticsearch involved here.
 */
function initNetworkMap() {
    Promise.all([
        fetch('/SNMP/GetNetworksList/').then(r => r.json()).catch(() => ({ networks: [] })),
        fetch('/SNMP/GetNetworkMapData/').then(r => r.json()).catch(() => null),
    ]).then(([listData, mapData]) => {
        _availableNetworks = listData.networks || [];
        _buildFilterDropdown(_availableNetworks);

        // Auto-select the network with the most devices; re-fetch scoped to it.
        // The initial parallel fetch was unfiltered — we discard it and re-fetch
        // so the map always opens on the most relevant network.
        const defaultIds = _autoSelectDefaultNetwork(_availableNetworks);
        if (defaultIds.length > 0) {
            fetchNetworkMapData(defaultIds);
        } else {
            handleNetworkMapData(mapData || { success: false, graph: { nodes: [], edges: [] } });
        }
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// Network filter dropdown (multiselect, auto-apply on checkbox change)
// ─────────────────────────────────────────────────────────────────────────────

let _nmFilterDebounce = null;

/**
 * Pre-check the network with the most devices and return its ID in an array.
 * Updates the checkbox and trigger label so the UI reflects the selection.
 * Returns [] if no networks or all have 0 devices.
 */
function _autoSelectDefaultNetwork(networks) {
    if (!networks || networks.length === 0) return [];
    const best = networks.reduce((a, b) => (b.device_count > a.device_count ? b : a), networks[0]);
    if (!best || best.device_count === 0) return [];

    _selectedNetworkIds.add(best.id);
    // Tick the checkbox (it may not be in the DOM yet if the pill list is empty,
    // but _buildFilterDropdown runs before this, so it should exist)
    const cb = document.getElementById(`nmnet-${best.id}`);
    if (cb) cb.checked = true;
    _updateNmFilterLabel();
    return [best.id];
}

function _buildFilterDropdown(networks) {
    const optionsEl = document.getElementById('nmFilterOptions');
    if (!optionsEl) return;

    if (networks.length === 0) {
        optionsEl.innerHTML = '<p class="px-3 py-2 text-xs text-gray-500 italic">No networks configured</p>';
        return;
    }

    optionsEl.innerHTML = networks.map(net => {
        const label = `${net.name} <span class="text-gray-500 font-mono text-xs">${net.network_range}</span>`;
        return `
            <label class="nm-filter-option">
                <input type="checkbox" id="nmnet-${net.id}" value="${net.id}"
                       onchange="_onNmFilterChange()">
                <span class="text-sm text-white leading-tight">${label}</span>
            </label>`;
    }).join('');
}

/** Called whenever any network checkbox is toggled — debounced 250ms. */
function _onNmFilterChange() {
    clearTimeout(_nmFilterDebounce);
    _nmFilterDebounce = setTimeout(() => {
        // Rebuild selected set from checkboxes
        _selectedNetworkIds.clear();
        document.querySelectorAll('#nmFilterOptions input[type="checkbox"]:checked')
            .forEach(cb => _selectedNetworkIds.add(parseInt(cb.value)));

        // Update trigger label
        _updateNmFilterLabel();

        // Nothing selected → show empty state immediately, no round-trip needed
        if (_selectedNetworkIds.size === 0) {
            _showMapEmptyState();
            return;
        }

        // Re-fetch and redraw
        fetchNetworkMapData([..._selectedNetworkIds]);
    }, 250);
}

function _updateNmFilterLabel() {
    const label = document.getElementById('nmFilterLabel');
    if (!label) return;
    const count = _selectedNetworkIds.size;
    if (count === 0) {
        label.textContent = 'All networks';
        label.classList.add('text-gray-400');
        label.classList.remove('text-white');
    } else if (count === 1) {
        const id = [..._selectedNetworkIds][0];
        const net = _availableNetworks.find(n => n.id === id);
        label.textContent = net ? net.name : `${count} selected`;
        label.classList.add('text-white');
        label.classList.remove('text-gray-400');
    } else {
        label.textContent = `${count} networks`;
        label.classList.add('text-white');
        label.classList.remove('text-gray-400');
    }
}

function toggleNmFilterDropdown(event) {
    event.stopPropagation();
    const dd = document.getElementById('nmFilterDropdown');
    if (!dd) return;
    dd.classList.toggle('hidden');
    if (!dd.classList.contains('hidden')) {
        // Focus search on open
        const search = document.getElementById('nmFilterSearch');
        if (search) { search.value = ''; filterNmDropdownOptions(''); search.focus(); }
    }
}

function filterNmDropdownOptions(query) {
    const q = query.trim().toLowerCase();
    document.querySelectorAll('.nm-filter-option').forEach(opt => {
        const text = opt.textContent.toLowerCase();
        opt.style.display = (!q || text.includes(q)) ? '' : 'none';
    });
}

// Close dropdown when clicking outside
document.addEventListener('click', function(e) {
    const wrapper = document.getElementById('nmFilterWrapper');
    if (wrapper && !wrapper.contains(e.target)) {
        const dd = document.getElementById('nmFilterDropdown');
        if (dd) dd.classList.add('hidden');
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// Data fetch
// ─────────────────────────────────────────────────────────────────────────────

// True once the map container has been shown at least once — subsequent fetches
// keep the container visible and use a lightweight overlay instead of swapping
// the whole card between loading/container/empty states.
let _mapInitialized = false;

/**
 * Fetch network map data, optionally scoped to a list of network IDs.
 */
function fetchNetworkMapData(networkIds) {
    const loadingEl   = document.getElementById('networkMapLoading');
    const containerEl = document.getElementById('networkMapContainer');
    const emptyEl     = document.getElementById('networkMapEmpty');

    if (!_mapInitialized) {
        // Initial load: use the full loading state so the card doesn't jump
        if (loadingEl)   loadingEl.classList.remove('hidden');
        if (containerEl) containerEl.classList.add('hidden');
        if (emptyEl)     emptyEl.classList.add('hidden');
    } else {
        // Subsequent filter changes: keep the canvas visible, show a thin overlay
        _setMapRefreshing(true);
    }

    let url = '/SNMP/GetNetworkMapData/';
    if (networkIds && networkIds.length > 0) {
        const params = networkIds.map(id => `networks=${encodeURIComponent(id)}`).join('&');
        url += '?' + params;
    }

    fetch(url)
        .then(r => r.json())
        .then(data => handleNetworkMapData(data))
        .catch(err => {
            console.error('Error fetching network map data:', err);
            _setMapRefreshing(false);
            if (!_mapInitialized) {
                if (loadingEl) loadingEl.classList.add('hidden');
                if (emptyEl)   emptyEl.classList.remove('hidden');
            } else {
                _renderEmptyInsideCanvas('Failed to load topology data');
            }
        });
}

// ─────────────────────────────────────────────────────────────────────────────
// Data handler
// ─────────────────────────────────────────────────────────────────────────────

function handleNetworkMapData(data) {
    const loadingEl   = document.getElementById('networkMapLoading');
    const containerEl = document.getElementById('networkMapContainer');
    const emptyEl     = document.getElementById('networkMapEmpty');

    _setMapRefreshing(false);

    if (data.success && data.graph && data.graph.nodes && data.graph.nodes.length > 0) {
        networkTopologyData = data.adjacency_table;

        if (!_mapInitialized) {
            // First successful render: transition from loading state to canvas
            if (loadingEl)   loadingEl.classList.add('hidden');
            if (emptyEl)     emptyEl.classList.add('hidden');
            if (containerEl) containerEl.classList.remove('hidden');
            _mapInitialized = true;
        }
        // Always re-render (filter changes re-use the already-visible container)
        renderNetworkMap(data.graph);
    } else {
        if (data.errors && data.errors.length > 0) {
            console.warn('Errors fetching network map data:', data.errors);
        }
        if (!_mapInitialized) {
            // Never shown the canvas — use the dedicated empty state outside it
            if (loadingEl) loadingEl.classList.add('hidden');
            if (emptyEl)   emptyEl.classList.remove('hidden');
        } else {
            // Canvas is visible — render the empty message inside the SVG
            _renderEmptyInsideCanvas('No topology data for the selected networks');
        }
    }
}

/**
 * Show/hide a semi-transparent refresh overlay on top of the existing canvas.
 * This lets filter changes feel instant without collapsing the card.
 */
function _setMapRefreshing(on) {
    const containerEl = document.getElementById('networkMapContainer');
    if (!containerEl) return;
    let overlay = document.getElementById('nmRefreshOverlay');
    if (on) {
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'nmRefreshOverlay';
            overlay.className = 'absolute inset-0 flex items-center justify-center bg-gray-900/50 rounded-lg z-40 pointer-events-none';
            overlay.innerHTML = `
                <div class="flex items-center gap-2 text-gray-300 text-sm bg-gray-800/80 px-4 py-2 rounded-lg border border-gray-700">
                    <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-400"></div>
                    Updating…
                </div>`;
            // Insert relative to the SVG wrapper so it sits over the canvas
            const wrapper = document.getElementById('nmSvgWrapper');
            if (wrapper) {
                wrapper.style.position = 'relative';
                wrapper.appendChild(overlay);
            } else {
                containerEl.appendChild(overlay);
            }
        }
    } else {
        if (overlay) overlay.remove();
    }
}

/**
 * Replace the SVG content with a plain empty-state message while keeping
 * the container (and its fixed height) fully visible.
 */
function _renderEmptyInsideCanvas(message) {
    networkTopologyData = null;
    const containerEl = document.getElementById('networkMapContainer');
    if (!containerEl) return;
    const wrapperHeight = _nmFullscreen ? 'calc(100vh - 56px)' : '600px';
    containerEl.innerHTML = `
        <div class="flex flex-col items-center justify-center w-full rounded-lg bg-gray-900"
             style="height:${wrapperHeight};">
            <div class="inline-flex items-center justify-center w-14 h-14 bg-gray-700/50 rounded-full mb-4">
                <svg class="w-7 h-7 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"/>
                </svg>
            </div>
            <p class="text-gray-400 text-sm">${escapeHtml(message)}</p>
        </div>`;
}

/**
 * Show the empty state — used when the user de-selects all networks without
 * making any API call. Keeps the canvas visible if already initialized.
 */
function _showMapEmptyState() {
    networkTopologyData = null;
    if (_mapInitialized) {
        _renderEmptyInsideCanvas('Select at least one network to view the topology');
    } else {
        const loadingEl   = document.getElementById('networkMapLoading');
        const containerEl = document.getElementById('networkMapContainer');
        const emptyEl     = document.getElementById('networkMapEmpty');
        if (loadingEl)   loadingEl.classList.add('hidden');
        if (containerEl) containerEl.classList.add('hidden');
        if (emptyEl)     emptyEl.classList.remove('hidden');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// D3 Rendering
// ─────────────────────────────────────────────────────────────────────────────

function renderNetworkMap(graphData) {
    const containerElement = document.getElementById('networkMapContainer');
    const nodeCount = graphData.nodes.length;

    // Build inner HTML — scale guardrail banner shown when over threshold
    const warnBanner = nodeCount > NODE_WARN_THRESHOLD ? `
        <div id="nmWarnBanner" class="mx-4 mt-3 px-4 py-2 bg-yellow-900/30 border border-yellow-600/40 rounded-lg flex items-center justify-between gap-3">
            <div class="flex items-center gap-2 text-yellow-300 text-sm">
                <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
                </svg>
                Large topology (${nodeCount} nodes). Use the network filter above to focus your view.
            </div>
            <button onclick="document.getElementById('nmWarnBanner').remove()"
                    class="text-yellow-400 hover:text-yellow-200 shrink-0">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
            </button>
        </div>` : '';

    // In fullscreen the SVG wrapper should fill the card body, not a fixed 600px
    const svgWrapperHeight = _nmFullscreen ? 'calc(100vh - 56px)' : '600px';

    containerElement.innerHTML = `
        ${warnBanner}
        <div class="relative w-full mt-2" id="nmSvgWrapper" style="height: ${svgWrapperHeight};">
            <svg id="networkMapSvg" class="w-full h-full bg-gray-900 rounded-lg">
                <g id="networkMapGroup"></g>
            </svg>
            <div id="networkMapTooltip"
                 class="absolute hidden bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white shadow-lg pointer-events-none z-50"
                 style="max-width: 300px;">
                <div id="tooltipContent"></div>
            </div>
            <div class="absolute top-4 right-4 flex gap-2">
                <button onclick="showAdjacencyData()"
                        class="px-3 py-2 bg-blue-700 hover:bg-blue-600 text-white rounded-lg text-sm flex items-center gap-2">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                              d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"/>
                    </svg>
                    Show JSON
                </button>
                <button onclick="resetNetworkMapZoom()"
                        class="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg text-sm">
                    Reset View
                </button>
                <button id="nmFullscreenBtn" onclick="toggleNetworkMapFullscreen()"
                        class="p-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
                        title="Toggle fullscreen">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                              d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"/>
                    </svg>
                </button>
            </div>
        </div>
    `;

    const svg     = document.getElementById('networkMapSvg');
    const svgRect = svg.getBoundingClientRect();
    const width   = svgRect.width;
    const height  = svgRect.height;

    initializeNetworkMapZoom(svg, nodeCount);

    if (!graphData.nodes.length) {
        d3.select('#networkMapGroup')
            .append('text')
            .attr('text-anchor', 'middle')
            .attr('fill', '#9ca3af')
            .attr('font-size', '16px')
            .text('No network topology data available');
        return;
    }

    // Dynamic force distances — spread more with more nodes
    const linkDistance  = Math.max(100, Math.min(200, 3000 / nodeCount));
    const chargeStr     = Math.max(-600, Math.min(-200, -15000 / nodeCount));

    const simulation = d3.forceSimulation(graphData.nodes)
        .force('link', d3.forceLink(graphData.edges).id(d => d.id).distance(linkDistance))
        .force('charge', d3.forceManyBody().strength(chargeStr))
        .force('center', d3.forceCenter(0, 0))
        .force('collision', d3.forceCollide().radius(55));

    const g = d3.select('#networkMapGroup');

    // ── Hull layer (drawn first so nodes/edges sit on top) ──
    const hullGroup = g.append('g').attr('class', 'network-hulls');

    // ── Edge layer ──
    const tooltip        = document.getElementById('networkMapTooltip');
    const tooltipContent = document.getElementById('tooltipContent');

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
            d3.select(this).attr('stroke', '#60a5fa').attr('stroke-width', 3);
            const src = d.source.id || d.source;
            const tgt = d.target.id || d.target;
            tooltipContent.innerHTML = `
                <div class="font-semibold mb-1">Connection</div>
                <div class="text-gray-300 mb-2">
                    <div>${escapeHtml(src)}</div>
                    <div class="text-xs text-gray-400 ml-2">└─ ${escapeHtml(d.source_interface)}</div>
                    <div class="text-center text-blue-400 my-1">↕</div>
                    <div>${escapeHtml(tgt)}</div>
                    <div class="text-xs text-gray-400 ml-2">└─ ${escapeHtml(d.target_interface)}</div>
                </div>
                <div class="text-xs text-gray-500 border-t border-gray-600 pt-1">Click for details</div>
                ${d.platform ? `<div class="text-xs text-gray-400 mt-1">Platform: ${escapeHtml(d.platform)}</div>` : ''}
            `;
            tooltip.classList.remove('hidden');
        })
        .on('mousemove', function(event) {
            const cr = containerElement.getBoundingClientRect();
            tooltip.style.left = (event.clientX - cr.left + 15) + 'px';
            tooltip.style.top  = (event.clientY - cr.top  + 15) + 'px';
        })
        .on('mouseleave', function() {
            d3.select(this).attr('stroke', '#6b7280').attr('stroke-width', 2);
            tooltip.classList.add('hidden');
        })
        .on('click', function(event, d) {
            event.stopPropagation();
            tooltip.classList.add('hidden');
            showEdgeDetail(d);
        });

    // ── Node layer ──
    const node = g.append('g')
        .attr('class', 'nodes')
        .selectAll('g')
        .data(graphData.nodes)
        .enter()
        .append('g')
        .call(d3.drag()
            .on('start', dragStarted)
            .on('drag',  dragged)
            .on('end',   dragEnded));

    node.append('circle')
        .attr('r', 20)
        .attr('fill',   d => d.managed ? '#3b82f6' : '#6b7280')
        .attr('stroke', d => d.managed ? '#60a5fa' : '#9ca3af')
        .attr('stroke-width', 2)
        .attr('stroke-dasharray', d => d.managed ? '0' : '5,5')
        .style('cursor', d => d.managed ? 'pointer' : 'default');

    node.append('text')
        .attr('text-anchor', 'middle')
        .attr('dy', '0.35em')
        .attr('font-size', '20px')
        .attr('fill', '#ffffff')
        .attr('pointer-events', 'none')
        .text('🖧');

    node.append('text')
        .attr('text-anchor', 'middle')
        .attr('dy', '35px')
        .attr('font-size', '12px')
        .attr('fill', '#e5e7eb')
        .attr('pointer-events', 'none')
        .text(d => d.id);

    node.append('circle')
        .attr('cx', 15).attr('cy', -15).attr('r', 10)
        .attr('fill', '#10b981').attr('stroke', '#059669').attr('stroke-width', 1);

    node.append('text')
        .attr('x', 15).attr('y', -15)
        .attr('text-anchor', 'middle').attr('dy', '0.35em')
        .attr('font-size', '10px').attr('fill', '#ffffff').attr('font-weight', 'bold')
        .attr('pointer-events', 'none')
        .text(d => d.interface_count);

    node
        .on('mouseenter', function(event, d) {
            const badge = d.managed
                ? '<span class="inline-block px-2 py-0.5 bg-blue-600 text-white text-xs rounded">Managed</span>'
                : '<span class="inline-block px-2 py-0.5 bg-gray-600 text-white text-xs rounded">Discovered</span>';
            tooltipContent.innerHTML = `
                <div class="font-semibold mb-1">${escapeHtml(d.id)}</div>
                <div class="mb-2">${badge}</div>
                <div class="text-xs text-gray-400">
                    <div>Network: ${escapeHtml(d.network)}</div>
                    <div>Adjacencies: ${d.interface_count}</div>
                </div>
                ${d.managed ? '<div class="text-xs text-gray-500 border-t border-gray-600 pt-1 mt-1">Click to inspect</div>' : ''}
            `;
            tooltip.classList.remove('hidden');
        })
        .on('mousemove', function(event) {
            const cr = containerElement.getBoundingClientRect();
            tooltip.style.left = (event.clientX - cr.left + 15) + 'px';
            tooltip.style.top  = (event.clientY - cr.top  + 15) + 'px';
        })
        .on('mouseleave', function() {
            tooltip.classList.add('hidden');
        });

    // ── Simulation tick ──
    simulation.on('tick', () => {
        link
            .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
        node.attr('transform', d => `translate(${d.x},${d.y})`);
        _drawNetworkHulls(hullGroup, graphData.nodes);
    });

    // Auto-fit once the simulation settles
    simulation.on('end', () => {
        _fitGraphToView(svg, graphData.nodes);
    });

    // ── Drag helpers ──
    function dragStarted(event, d) {
        networkMapIsDragging = false;
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x; d.fy = d.y;
    }
    function dragged(event, d) {
        networkMapIsDragging = true;
        d.fx = event.x; d.fy = event.y;
    }
    function dragEnded(event, d) {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null; d.fy = null;
        if (!networkMapIsDragging && d.managed) {
            showNodeCard(d);
        }
        networkMapIsDragging = false;
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Hull rendering
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Draw a convex hull background region for each network group.
 * Called on every simulation tick; uses D3 data join for efficiency.
 */
function _drawNetworkHulls(hullGroup, nodes) {
    const byNetwork = d3.group(nodes, d => d.network);
    const hullData  = [];

    byNetwork.forEach((pts, networkLabel) => {
        if (pts.length === 0) return;

        // d3.polygonHull requires at least 3 distinct points; for 1-2 nodes we
        // synthesise a small bounding pad so a visible region still appears.
        let points = pts.map(d => [d.x, d.y]);

        if (points.length === 1) {
            const [cx, cy] = points[0];
            points = [
                [cx - 40, cy - 40], [cx + 40, cy - 40],
                [cx + 40, cy + 40], [cx - 40, cy + 40],
            ];
        } else if (points.length === 2) {
            const [x1, y1] = points[0];
            const [x2, y2] = points[1];
            const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
            const dx = (x2 - x1) || 1, dy = (y2 - y1) || 1;
            const len = Math.sqrt(dx * dx + dy * dy);
            const nx = -dy / len * 35, ny = dx / len * 35;
            points = [
                [x1 - nx, y1 - ny], [x2 - nx, y2 - ny],
                [x2 + nx, y2 + ny], [x1 + nx, y1 + ny],
            ];
        }

        const hull = d3.polygonHull(points);
        if (!hull) return;

        // Pad the hull outward by 36px from centroid
        const centroid = d3.polygonCentroid(hull);
        const padded = hull.map(([x, y]) => {
            const dx = x - centroid[0], dy = y - centroid[1];
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            return [x + (dx / dist) * 36, y + (dy / dist) * 36];
        });

        hullData.push({ networkLabel, path: padded, centroid });
    });

    // Data join
    const paths = hullGroup.selectAll('path.network-hull').data(hullData, d => d.networkLabel);

    paths.enter()
        .append('path')
        .attr('class', 'network-hull')
        .attr('fill-opacity', 0.07)
        .attr('stroke-opacity', 0.35)
        .attr('stroke-width', 1.5)
        .attr('stroke-dasharray', '6,4')
      .merge(paths)
        .attr('fill',   d => networkColor(d.networkLabel))
        .attr('stroke', d => networkColor(d.networkLabel))
        .attr('d', d => 'M' + d.path.map(p => p.join(',')).join('L') + 'Z');

    paths.exit().remove();

    // Hull labels
    const labels = hullGroup.selectAll('text.hull-label').data(hullData, d => d.networkLabel);

    labels.enter()
        .append('text')
        .attr('class', 'hull-label')
        .attr('font-size', '11px')
        .attr('font-weight', '600')
        .attr('opacity', 0.65)
        .attr('pointer-events', 'none')
      .merge(labels)
        .attr('fill', d => networkColor(d.networkLabel))
        .attr('x', d => d.centroid[0])
        .attr('y', d => d.path.reduce((mn, p) => Math.min(mn, p[1]), Infinity) - 6)
        .attr('text-anchor', 'middle')
        .text(d => d.networkLabel);

    labels.exit().remove();
}

// ─────────────────────────────────────────────────────────────────────────────
// Zoom / pan
// ─────────────────────────────────────────────────────────────────────────────

function initializeNetworkMapZoom(svg, nodeCount) {
    const svgEl = d3.select(svg);
    const minScale = nodeCount > 0 ? Math.min(0.05, 5 / nodeCount) : 0.1;

    networkMapZoomBehavior = d3.zoom()
        .scaleExtent([minScale, 3])
        .on('zoom', event => {
            svgEl.select('g').attr('transform', event.transform);
            currentNetworkTransform = event.transform;
        });

    svgEl.call(networkMapZoomBehavior);

    if (currentNetworkTransform) {
        svgEl.call(networkMapZoomBehavior.transform, currentNetworkTransform);
    } else {
        const r = svg.getBoundingClientRect();
        const t = d3.zoomIdentity.translate(r.width / 2, r.height / 2);
        svgEl.call(networkMapZoomBehavior.transform, t);
        currentNetworkTransform = t;
    }

    svgEl.on('dblclick.zoom', () => {
        const r = svg.getBoundingClientRect();
        svgEl.transition().duration(750)
            .call(networkMapZoomBehavior.transform,
                  d3.zoomIdentity.translate(r.width / 2, r.height / 2));
    });
}

function resetNetworkMapZoom() {
    const svg = document.getElementById('networkMapSvg');
    if (!svg || !networkMapZoomBehavior) return;
    const r = svg.getBoundingClientRect();
    d3.select(svg).transition().duration(750)
        .call(networkMapZoomBehavior.transform,
              d3.zoomIdentity.translate(r.width / 2, r.height / 2));
}

/**
 * Toggle the network map card between normal and fullscreen mode.
 * Matches the same pattern used by the pipeline graph editor.
 */
function toggleNetworkMapFullscreen() {
    const card    = document.getElementById('networkMapCard');
    const btn     = document.getElementById('nmFullscreenBtn');
    const wrapper = document.getElementById('nmSvgWrapper');
    if (!card) return;

    _nmFullscreen = !_nmFullscreen;

    if (_nmFullscreen) {
        card.style.position        = 'fixed';
        card.style.top             = '0';
        card.style.left            = '0';
        card.style.right           = '0';
        card.style.bottom          = '0';
        card.style.zIndex          = '9000';
        card.style.borderRadius    = '0';
        card.style.marginBottom    = '0';
        card.style.display         = 'flex';
        card.style.flexDirection   = 'column';
        // SVG wrapper grows to fill the card below the header (~56px)
        if (wrapper) wrapper.style.height = 'calc(100vh - 56px)';

        if (btn) {
            btn.title = 'Exit fullscreen';
            btn.innerHTML = `
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M6 18L18 6M6 6l12 12"/>
                </svg>`;
        }
    } else {
        card.style.position        = '';
        card.style.top             = '';
        card.style.left            = '';
        card.style.right           = '';
        card.style.bottom          = '';
        card.style.zIndex          = '';
        card.style.borderRadius    = '';
        card.style.marginBottom    = '';
        card.style.display         = '';
        card.style.flexDirection   = '';
        if (wrapper) wrapper.style.height = '600px';

        if (btn) {
            btn.title = 'Toggle fullscreen';
            btn.innerHTML = `
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"/>
                </svg>`;
        }
    }

    // Re-fit the graph to the new viewport after the layout settles
    const svg = document.getElementById('networkMapSvg');
    if (svg && networkMapZoomBehavior) {
        setTimeout(() => {
            // Use the current node positions from the live DOM if available
            const nodes = networkTopologyData ? _liveNodesFromSvg() : null;
            if (nodes && nodes.length > 0) {
                _fitGraphToView(svg, nodes);
            } else {
                // Fall back to re-centering
                const r = svg.getBoundingClientRect();
                d3.select(svg).transition().duration(400)
                    .call(networkMapZoomBehavior.transform,
                          d3.zoomIdentity.translate(r.width / 2, r.height / 2));
            }
        }, 50);
    }
}

/**
 * Read current node x/y coordinates from the live D3 simulation via the
 * transform attributes on each node group — used to re-fit after a resize.
 */
function _liveNodesFromSvg() {
    const nodes = [];
    document.querySelectorAll('#networkMapGroup .nodes g').forEach(el => {
        const t = el.getAttribute('transform');
        if (!t) return;
        const m = t.match(/translate\(([^,]+),([^)]+)\)/);
        if (m) nodes.push({ x: parseFloat(m[1]), y: parseFloat(m[2]) });
    });
    return nodes;
}

// Escape key exits fullscreen
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && _nmFullscreen) toggleNetworkMapFullscreen();
});

/**
 * After the simulation settles, compute the bounding box of all nodes and zoom
 * the viewport to contain them with some padding.
 */
function _fitGraphToView(svgEl, nodes) {
    if (!networkMapZoomBehavior || nodes.length === 0) return;

    const r    = svgEl.getBoundingClientRect();
    const pad  = 80;
    const xs   = nodes.map(d => d.x);
    const ys   = nodes.map(d => d.y);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const gw   = maxX - minX || 1;
    const gh   = maxY - minY || 1;

    const scale = Math.min(
        (r.width  - pad * 2) / gw,
        (r.height - pad * 2) / gh,
        1.5   // don't over-zoom into a tiny graph
    );
    const tx = r.width  / 2 - scale * (minX + gw / 2);
    const ty = r.height / 2 - scale * (minY + gh / 2);

    d3.select(svgEl).transition().duration(800)
        .call(networkMapZoomBehavior.transform,
              d3.zoomIdentity.translate(tx, ty).scale(scale));
}

// ─────────────────────────────────────────────────────────────────────────────
// Edge detail modal
// ─────────────────────────────────────────────────────────────────────────────

function showEdgeDetail(d) {
    const srcName = d.source.id || d.source;
    const tgtName = d.target.id || d.target;

    const existing = document.getElementById('edge-detail-modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'edge-detail-modal';
    modal.className = 'fixed inset-0 flex items-center justify-center z-[60] p-4';
    modal.innerHTML = `
        <div class="absolute inset-0 bg-black/50 backdrop-blur-sm"
             onclick="document.getElementById('edge-detail-modal').remove()"></div>
        <div class="bg-gray-800 rounded-lg w-full max-w-2xl relative z-10 border border-gray-700 shadow-2xl max-h-[90vh] flex flex-col">
            <div class="p-4 border-b border-gray-700 flex items-center justify-between shrink-0">
                <h3 class="text-base font-semibold text-white flex items-center gap-2">
                    <svg class="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                              d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/>
                    </svg>
                    Link Detail
                </h3>
                <button onclick="document.getElementById('edge-detail-modal').remove()"
                        class="text-gray-400 hover:text-white transition-colors">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                    </svg>
                </button>
            </div>
            <!-- Loading state -->
            <div id="edgeDetailBody" class="p-5 overflow-y-auto flex-1 min-h-0">
                <div class="flex items-center justify-center py-8 gap-3 text-gray-400">
                    <div class="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-500"></div>
                    <span class="text-sm">Fetching interface data…</span>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(modal);

    // Build query string
    const params = new URLSearchParams({
        source:       srcName,
        source_iface: d.source_interface,
        target:       tgtName,
        target_iface: d.target_interface,
    });

    fetch(`/SNMP/GetEdgeInterfaceDetail/?${params}`)
        .then(r => r.json())
        .then(data => {
            const body = document.getElementById('edgeDetailBody');
            if (!body) return;
            if (!data.success) {
                body.innerHTML = `<p class="text-red-400 text-sm p-4">${escapeHtml(data.error || 'Failed to load interface data')}</p>`;
                return;
            }
            body.innerHTML = _renderEdgeDetailBody(d, data);
        })
        .catch(err => {
            const body = document.getElementById('edgeDetailBody');
            if (body) body.innerHTML = `<p class="text-red-400 text-sm p-4">Error: ${escapeHtml(err.message)}</p>`;
        });
}

/** Build the HTML for a populated edge detail modal body. */
function _renderEdgeDetailBody(d, data) {
    const capStr = _decodeCapabilities(d.capabilities);

    function _ifaceBlock(side) {
        const iface = side.interface;
        if (!iface) {
            return `<p class="text-xs text-gray-500 italic mt-1">No interface data found in Elasticsearch</p>`;
        }

        const adminStatus = iface.admin_status;
        const operStatus  = iface.oper_status;
        const upColor     = (adminStatus === 'UP' && operStatus === 'UP') ? 'text-green-400' : 'text-gray-400';
        const adminTxt    = adminStatus === 'UP'   ? '<span class="text-green-400">Up</span>'
                          : adminStatus === 'DOWN' ? '<span class="text-gray-400">Down</span>'
                          :                         '<span class="text-yellow-400">Testing</span>';
        const operTxt     = operStatus === 'UP'               ? '<span class="text-green-400">Up</span>'
                          : operStatus === 'DOWN'             ? '<span class="text-gray-400">Down</span>'
                          : operStatus === 'LOWER_LAYER_DOWN' ? '<span class="text-orange-400">Lower Layer Down</span>'
                          : operStatus === 'DORMANT'          ? '<span class="text-yellow-400">Dormant</span>'
                          : operStatus === 'NOT_PRESENT'      ? '<span class="text-gray-500">Not Present</span>'
                          :                                     `<span class="text-yellow-400">${escapeHtml(operStatus ?? 'Unknown')}</span>`;

        const speedMbps = iface.speed_high_mbps ?? (iface.speed ? Math.round(iface.speed / 1e6) : null);
        const speedTxt  = speedMbps == null ? null
                        : speedMbps >= 1000 ? `${speedMbps / 1000}G`
                        : speedMbps > 0     ? `${speedMbps}M`
                        : null;

        // Byte counters
        const inBytes   = iface.in_octets  ?? null;
        const outBytes  = iface.out_octets ?? null;

        // Error / discard counters
        const inErrors   = iface.in_errors   ?? null;
        const outErrors  = iface.out_errors  ?? null;
        const inDisc     = iface.in_discards  ?? null;
        const outDisc    = iface.out_discards ?? null;

        // Packet counters
        const inUcast   = iface.in_unicast_pkts    ?? null;
        const outUcast  = iface.out_unicast_pkts   ?? null;
        const inMcast   = iface.in_multicast_pkts  ?? null;
        const outMcast  = iface.out_multicast_pkts ?? null;
        const inBcast   = iface.in_broadcast_pkts  ?? null;
        const outBcast  = iface.out_broadcast_pkts ?? null;

        const alias      = iface.alias    ?? '';
        const altName    = iface.alt_name ?? '';
        const desc       = iface.description ?? '';
        const mtu        = iface.mtu     ?? null;
        const mac        = iface.mac     ?? null;
        const vlanId     = iface.vlan_id ?? null;
        const ifIndex    = iface.index   ?? null;
        const lastChange = iface.last_change ?? null;  // sysUpTime hundredths

        // SNMP ifType → human-readable (common values only)
        const ifTypeNum = iface.type ?? null;
        const IF_TYPES  = {6:'ethernetCsmacd', 24:'softwareLoopback', 53:'propVirtual',
                           131:'tunnel', 161:'ieee8023adLag', 166:'mpls'};
        const ifTypeTxt = ifTypeNum != null
            ? (IF_TYPES[ifTypeNum] || `type ${ifTypeNum}`) : null;

        const fmtBytes = n => {
            if (n == null) return null;
            if (n >= 1e12) return (n / 1e12).toFixed(2) + ' TB';
            if (n >= 1e9)  return (n / 1e9).toFixed(2)  + ' GB';
            if (n >= 1e6)  return (n / 1e6).toFixed(2)  + ' MB';
            if (n >= 1e3)  return (n / 1e3).toFixed(1)  + ' KB';
            return n + ' B';
        };
        const fmtN = n => (n == null ? null : n.toLocaleString());

        const hasTraffic  = inBytes  != null || outBytes  != null;
        const hasErrors   = inErrors != null || outErrors != null || inDisc != null || outDisc != null;
        const hasPackets  = inUcast  != null || outUcast  != null || inMcast != null || inBcast != null;

        return `
            <!-- Status + core -->
            <div class="grid grid-cols-2 gap-x-4 gap-y-1 text-xs mt-2">
                <div><span class="text-gray-400">Admin:</span> ${adminTxt}</div>
                <div><span class="text-gray-400">Oper:</span> ${operTxt}</div>
                ${speedTxt ? `<div><span class="text-gray-400">Speed:</span> <span class="${upColor}">${speedTxt}</span></div>` : ''}
                ${mtu  != null ? `<div><span class="text-gray-400">MTU:</span> <span class="text-white">${fmtN(mtu)}</span></div>` : ''}
                ${mac  ? `<div class="col-span-2"><span class="text-gray-400">MAC:</span> <span class="text-white font-mono">${escapeHtml(mac)}</span></div>` : ''}
                ${alias && alias !== side.iface_name ? `<div class="col-span-2"><span class="text-gray-400">Alias:</span> <span class="text-white">${escapeHtml(alias)}</span></div>` : ''}
                ${altName && altName !== side.iface_name ? `<div class="col-span-2"><span class="text-gray-400">Alt name:</span> <span class="text-white">${escapeHtml(altName)}</span></div>` : ''}
                ${desc && desc !== side.iface_name ? `<div class="col-span-2"><span class="text-gray-400">Desc:</span> <span class="text-white">${escapeHtml(desc)}</span></div>` : ''}
                ${vlanId != null ? `<div><span class="text-gray-400">VLAN:</span> <span class="text-white">${vlanId}</span></div>` : ''}
                ${ifTypeTxt ? `<div><span class="text-gray-400">Type:</span> <span class="text-white">${escapeHtml(ifTypeTxt)}</span></div>` : ''}
                ${ifIndex != null ? `<div><span class="text-gray-400">Index:</span> <span class="text-white">${ifIndex}</span></div>` : ''}
                ${lastChange != null && lastChange > 0 ? `<div><span class="text-gray-400">Last change:</span> <span class="text-white">${formatUptime(lastChange)}</span></div>` : ''}
            </div>
            ${hasTraffic ? `
            <!-- Traffic counters -->
            <div class="mt-2 border-t border-gray-700/60 pt-2">
                <p class="text-xs text-gray-500 uppercase tracking-wide mb-1">Traffic (cumulative)</p>
                <div class="grid grid-cols-2 gap-2 text-xs">
                    <div class="bg-gray-900/50 rounded px-2 py-1.5 space-y-0.5">
                        <div class="text-gray-400 font-medium">↓ In</div>
                        ${fmtBytes(inBytes)  != null ? `<div class="text-blue-300 font-mono">${fmtBytes(inBytes)}</div>`   : ''}
                        ${fmtN(inUcast)  != null ? `<div class="text-gray-400">${fmtN(inUcast)} unicast</div>`   : ''}
                        ${fmtN(inMcast)  != null ? `<div class="text-gray-400">${fmtN(inMcast)} mcast</div>`     : ''}
                        ${fmtN(inBcast)  != null ? `<div class="text-gray-400">${fmtN(inBcast)} bcast</div>`     : ''}
                        ${inErrors  != null && inErrors  > 0 ? `<div class="text-red-400">${fmtN(inErrors)} errors</div>`    : ''}
                        ${inDisc    != null && inDisc    > 0 ? `<div class="text-yellow-400">${fmtN(inDisc)} discards</div>` : ''}
                    </div>
                    <div class="bg-gray-900/50 rounded px-2 py-1.5 space-y-0.5">
                        <div class="text-gray-400 font-medium">↑ Out</div>
                        ${fmtBytes(outBytes) != null ? `<div class="text-green-300 font-mono">${fmtBytes(outBytes)}</div>`  : ''}
                        ${fmtN(outUcast) != null ? `<div class="text-gray-400">${fmtN(outUcast)} unicast</div>`  : ''}
                        ${fmtN(outMcast) != null ? `<div class="text-gray-400">${fmtN(outMcast)} mcast</div>`    : ''}
                        ${fmtN(outBcast) != null ? `<div class="text-gray-400">${fmtN(outBcast)} bcast</div>`    : ''}
                        ${outErrors != null && outErrors > 0 ? `<div class="text-red-400">${fmtN(outErrors)} errors</div>`   : ''}
                        ${outDisc   != null && outDisc   > 0 ? `<div class="text-yellow-400">${fmtN(outDisc)} discards</div>` : ''}
                    </div>
                </div>
            </div>` : ''}`;
    }

    return `
        <div class="space-y-4">
            <!-- Endpoint panels -->
            <div class="grid grid-cols-2 gap-3">
                <div class="bg-gray-900/60 rounded-lg p-3 overflow-hidden">
                    <p class="text-xs text-gray-400 mb-0.5">Source</p>
                    <p class="text-white font-semibold text-sm truncate">${escapeHtml(data.source.sysname)}</p>
                    <p class="text-blue-300 text-xs font-mono mt-0.5 truncate">${escapeHtml(data.source.iface_name)}</p>
                    ${_ifaceBlock(data.source)}
                </div>
                <div class="bg-gray-900/60 rounded-lg p-3 overflow-hidden">
                    <p class="text-xs text-gray-400 mb-0.5">Target</p>
                    <p class="text-white font-semibold text-sm truncate">${escapeHtml(data.target.sysname)}</p>
                    <p class="text-blue-300 text-xs font-mono mt-0.5 truncate">${escapeHtml(data.target.iface_name)}</p>
                    ${_ifaceBlock(data.target)}
                </div>
            </div>
            <!-- CDP metadata -->
            <div class="border-t border-gray-700 pt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
                ${d.platform ? `<div class="col-span-2"><span class="text-gray-400">Platform: </span><span class="text-white font-mono">${escapeHtml(d.platform)}</span></div>` : ''}
                ${capStr ? `<div class="col-span-2"><span class="text-gray-400">Capabilities: </span><span class="text-white">${escapeHtml(capStr)}</span></div>` : ''}
                ${d.network ? `<div class="col-span-2"><span class="text-gray-400">Network: </span><span class="text-white">${escapeHtml(d.network)}</span></div>` : ''}
            </div>
        </div>`;
}

/**
 * Decode CDP capability bitmask into readable labels.
 * Handles colon-separated hex bytes (e.g. "00:00:00:12") as well as plain hex.
 */
function _decodeCapabilities(raw) {
    if (!raw) return '';
    // Strip colons so "00:00:00:12" → "00000012" before parsing
    const clean = raw.replace(/:/g, '');
    const val   = parseInt(clean, 16);
    if (isNaN(val) || val === 0) return raw;
    const caps = [];
    if (val & 0x01) caps.push('Router');
    if (val & 0x02) caps.push('Trans-Bridge');
    if (val & 0x04) caps.push('Source-Bridge');
    if (val & 0x08) caps.push('Switch');
    if (val & 0x10) caps.push('Host');
    if (val & 0x20) caps.push('IGMP');
    if (val & 0x40) caps.push('Repeater');
    if (val & 0x80) caps.push('VoIP Phone');
    return caps.length ? caps.join(', ') : raw;
}

// ─────────────────────────────────────────────────────────────────────────────
// Adjacency debug modal
// ─────────────────────────────────────────────────────────────────────────────

function showAdjacencyData() {
    if (!networkTopologyData) {
        console.warn('No adjacency data available');
        return;
    }

    const existing = document.getElementById('adjacency-data-modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'adjacency-data-modal';
    modal.className = 'fixed inset-0 flex items-center justify-center z-[60] p-4';
    modal.innerHTML = `
        <div class="absolute inset-0 bg-black/50 backdrop-blur-sm"
             onclick="document.getElementById('adjacency-data-modal').remove()"></div>
        <div class="bg-gray-800 rounded-lg w-full max-w-6xl max-h-[90vh] flex flex-col relative z-10 border border-gray-700">
            <div class="p-4 border-b border-gray-700 flex justify-between items-center">
                <h3 class="text-lg font-semibold text-white">Network Adjacency Data (Debug)</h3>
                <button onclick="document.getElementById('adjacency-data-modal').remove()"
                        class="text-gray-400 hover:text-white">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                    </svg>
                </button>
            </div>
            <div class="p-6 overflow-y-auto flex-grow">
                <div class="bg-gray-900 rounded-lg p-4">
                    <pre class="text-gray-300 text-xs overflow-auto">${escapeHtml(JSON.stringify(networkTopologyData, null, 2))}</pre>
                </div>
            </div>
            <div class="p-4 border-t border-gray-700 flex justify-end">
                <button onclick="copyAdjacencyData(this)"
                        class="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm flex items-center gap-2">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                              d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/>
                    </svg>
                    Copy to Clipboard
                </button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

/**
 * Copy adjacency data to clipboard.
 * @param {HTMLButtonElement} btn - the button element that was clicked
 */
function copyAdjacencyData(btn) {
    if (!networkTopologyData) return;

    const jsonString = JSON.stringify(networkTopologyData, null, 2);
    navigator.clipboard.writeText(jsonString).then(() => {
        const originalHTML = btn.innerHTML;
        btn.innerHTML = `
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
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

// ─────────────────────────────────────────────────────────────────────────────
// Compact node card
// ─────────────────────────────────────────────────────────────────────────────

let _ncTopZ     = 10010;
let _ncSpawnIdx = 0;
let _ncActive   = null;
let _ncStartX   = 0, _ncStartY = 0, _ncStartL = 0, _ncStartT = 0;

document.addEventListener('mousemove', function(e) {
    if (!_ncActive) return;
    _ncActive.style.left = (_ncStartL + e.clientX - _ncStartX) + 'px';
    _ncActive.style.top  = (_ncStartT + e.clientY - _ncStartY) + 'px';
});
document.addEventListener('mouseup', function() { _ncActive = null; });

/**
 * Show a compact floating card for a node. Opens the full window on demand via
 * the "Open Full Details" button.
 */
function showNodeCard(nodeData) {
    const safeId  = (nodeData.device_id || nodeData.id.replace(/[^a-z0-9]/gi, '_'));
    const cardId  = 'nc-' + safeId;

    // Bring existing card to front
    const existing = document.getElementById(cardId);
    if (existing) {
        existing.style.zIndex = ++_ncTopZ;
        return;
    }

    const offset    = (_ncSpawnIdx % 8) * 28;
    _ncSpawnIdx++;
    const spawnTop  = 80 + offset;
    const spawnLeft = 80 + offset;

    const badge = nodeData.managed
        ? `<span class="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-600/20 text-blue-300 border border-blue-500/30 rounded text-xs">
               <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                   <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                         d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
               </svg>Managed</span>`
        : `<span class="inline-flex items-center px-2 py-0.5 bg-gray-600/20 text-gray-400 border border-gray-500/30 rounded text-xs">Discovered</span>`;

    const card = document.createElement('div');
    card.id        = cardId;
    card.className = 'node-card fixed bg-gray-800 rounded-lg border border-gray-700 shadow-2xl flex flex-col';
    card.style.cssText = `width:360px; top:${spawnTop}px; left:${spawnLeft}px; z-index:${++_ncTopZ};`;

    card.innerHTML = `
        <!-- Header (draggable) -->
        <div class="nc-header px-3 py-2.5 border-b border-gray-700 flex items-center justify-between rounded-t-lg cursor-move bg-gray-700/60 shrink-0">
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
                    ${nodeData.network ? `<p class="text-xs text-gray-400 mt-0.5 truncate">${escapeHtml(nodeData.network)}</p>` : ''}
                </div>
            </div>
            <button class="nc-close-btn p-1.5 text-gray-400 hover:text-red-400 hover:bg-gray-600 rounded transition-colors shrink-0 ml-2">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
            </button>
        </div>

        <!-- Stats row (populated async) -->
        <div class="nc-stats px-4 py-3 border-b border-gray-700/60 grid grid-cols-3 gap-3 text-center shrink-0">
            <div>
                <p class="text-xs text-gray-400 mb-0.5">Uptime</p>
                <p class="text-white text-sm font-semibold nc-uptime">—</p>
            </div>
            <div>
                <p class="text-xs text-gray-400 mb-0.5">CPU</p>
                <p class="text-white text-sm font-semibold nc-cpu">—</p>
            </div>
            <div>
                <p class="text-xs text-gray-400 mb-0.5">Memory</p>
                <p class="text-white text-sm font-semibold nc-mem">—</p>
            </div>
        </div>

        <!-- Neighbors list -->
        <div class="nc-neighbors flex-1 overflow-y-auto px-4 py-3 min-h-0" style="max-height:220px;">
            <p class="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">CDP Neighbors</p>
            <div class="nc-neighbor-list space-y-1">
                <p class="text-xs text-gray-500 italic">Loading…</p>
            </div>
        </div>

        <!-- Footer -->
        ${nodeData.managed && nodeData.device_id ? `
        <div class="px-4 py-2.5 border-t border-gray-700/60 flex justify-end shrink-0">
            <button class="nc-open-full-btn px-3 py-1.5 bg-blue-700 hover:bg-blue-600 text-white text-xs rounded-lg transition-colors flex items-center gap-1.5">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"/>
                </svg>
                Open Full Details
            </button>
        </div>` : ''}
    `;

    document.body.appendChild(card);

    // Drag on header
    card.querySelector('.nc-header').addEventListener('mousedown', function(e) {
        if (e.target.closest('.nc-close-btn')) return;
        card.style.zIndex = ++_ncTopZ;
        _ncActive  = card;
        _ncStartX  = e.clientX;
        _ncStartY  = e.clientY;
        _ncStartL  = card.offsetLeft;
        _ncStartT  = card.offsetTop;
        e.preventDefault();
    });

    // Bring to front on click
    card.addEventListener('mousedown', () => { card.style.zIndex = ++_ncTopZ; });

    // Close
    card.querySelector('.nc-close-btn').addEventListener('click', () => card.remove());

    // Open full details window — closes compact card first, passes back callback
    const openFullBtn = card.querySelector('.nc-open-full-btn');
    if (openFullBtn) {
        openFullBtn.addEventListener('click', () => {
            card.remove();
            createDeviceWindow(nodeData, () => showNodeCard(nodeData));
        });
    }

    // Populate stats and neighbor list
    _populateNodeCard(card, nodeData);
}

/** Fetch the slim summary and populate card stats + build neighbor list from memory. */
function _populateNodeCard(card, nodeData) {
    // ── Neighbors from in-memory adjacency table ──
    const neighborList = card.querySelector('.nc-neighbor-list');
    const neighbors    = _getNeighborsFromAdjacency(nodeData.id);

    if (neighbors.length === 0) {
        neighborList.innerHTML = '<p class="text-xs text-gray-500 italic">No neighbors found</p>';
    } else {
        neighborList.innerHTML = neighbors.map(nb => `
            <div class="flex items-start gap-2 py-1 border-b border-gray-700/40 last:border-0">
                <div class="shrink-0 w-1.5 h-1.5 rounded-full mt-1.5 ${nb.managed ? 'bg-blue-400' : 'bg-gray-500'}"></div>
                <div class="min-w-0 flex-1">
                    <p class="text-white text-xs font-medium truncate">${escapeHtml(nb.deviceId)}</p>
                    <p class="text-gray-400 text-xs font-mono">
                        ${escapeHtml(nb.localIface)} ↔ ${escapeHtml(nb.remoteIface)}
                    </p>
                </div>
                ${nb.platform ? `<p class="text-gray-500 text-xs shrink-0 max-w-[90px] truncate" title="${escapeHtml(nb.platform)}">${escapeHtml(nb.platform.split(' ')[0])}</p>` : ''}
            </div>
        `).join('');
    }

    // ── Stats — reuse GetDeviceVisualization (same source as the full window) ──
    if (!nodeData.managed || !nodeData.device_id) return;

    fetch(`/SNMP/GetDeviceVisualization/${nodeData.device_id}/`)
        .then(r => r.json())
        .then(data => {
            if (!card.isConnected) return;
            const uptimeEl = card.querySelector('.nc-uptime');
            const cpuEl    = card.querySelector('.nc-cpu');
            const memEl    = card.querySelector('.nc-mem');

            const metrics = data.visualizations?.metrics;
            if (!metrics) return;

            // Uptime: stored as hundredths of seconds (raw SNMP sysUpTime).
            // formatUptime() from snmp_device_visual_preview.js handles the conversion.
            if (metrics.Uptime != null && metrics.Uptime > 0) {
                uptimeEl.textContent = formatUptime(metrics.Uptime);
            }

            // CPU / Memory: arrays of 0-1 fractional values; use the most recent point.
            if (metrics.CPU && metrics.CPU.length > 0) {
                const pct = Math.round(metrics.CPU[0] * 100);
                const cls = pct >= 90 ? 'text-red-400' : pct >= 75 ? 'text-orange-400' : 'text-green-400';
                cpuEl.className = `text-sm font-semibold nc-cpu ${cls}`;
                cpuEl.textContent = pct + '%';
            }

            if (metrics.Memory && metrics.Memory.length > 0) {
                const pct = Math.round(metrics.Memory[0] * 100);
                const cls = pct >= 90 ? 'text-red-400' : pct >= 75 ? 'text-orange-400' : 'text-green-400';
                memEl.className = `text-sm font-semibold nc-mem ${cls}`;
                memEl.textContent = pct + '%';
            }
        })
        .catch(() => {
            // Stats stay as '—' — non-fatal
        });
}

/**
 * Build a neighbor list for a given device ID from the in-memory adjacency table.
 * Returns [{deviceId, localIface, remoteIface, platform, managed}, ...]
 */
function _getNeighborsFromAdjacency(deviceId) {
    if (!networkTopologyData) return [];
    const results = [];
    const managedDevices = new Set();

    // First pass: collect all managed device names
    for (const devices of Object.values(networkTopologyData)) {
        for (const dn of Object.keys(devices)) {
            managedDevices.add(dn);
        }
    }

    // Second pass: find this device's entries
    for (const devices of Object.values(networkTopologyData)) {
        if (!devices[deviceId]) continue;
        for (const [localIface, cdpData] of Object.entries(devices[deviceId])) {
            results.push({
                deviceId:    cdpData.device_id || '(unknown)',
                localIface,
                remoteIface: cdpData.port || '',
                platform:    cdpData.platform || '',
                managed:     managedDevices.has(cdpData.device_id),
            });
        }
    }
    return results;
}

// ─────────────────────────────────────────────────────────────────────────────
// Floating Device Detail Window System (full / heavy — opened on demand)
// Each click on "Open Full Details" spawns an independent floating window.
// ─────────────────────────────────────────────────────────────────────────────

let _dwTopZ      = 11000;
let _dwSpawnIdx  = 0;

let _dwActive   = null;
let _dwOp       = null;
let _dwStartX   = 0, _dwStartY = 0;
let _dwStartW   = 0, _dwStartH = 0;
let _dwStartL   = 0, _dwStartT = 0;

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
document.addEventListener('mouseup', function() { _dwActive = null; _dwOp = null; });

/**
 * @param {object} nodeData
 * @param {Function|null} onBack  Optional callback invoked when the user clicks
 *                                "Back to Summary" in the window header.
 */
function createDeviceWindow(nodeData, onBack) {
    const safeId   = (nodeData.device_id || nodeData.id.replace(/[^a-z0-9]/gi, '_'));
    const windowId = 'device-window-' + safeId;

    const existing = document.getElementById(windowId);
    if (existing) {
        existing.style.zIndex = ++_dwTopZ;
        return;
    }

    const offset    = (_dwSpawnIdx % 8) * 30;
    _dwSpawnIdx++;
    const spawnTop  = 60 + offset;
    const spawnLeft = 60 + offset;

    const badge = nodeData.managed
        ? `<span class="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-600/20 text-blue-300 border border-blue-500/30 rounded text-xs font-medium">
               <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                   <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                         d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
               </svg>Managed</span>`
        : `<span class="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-600/20 text-gray-400 border border-gray-500/30 rounded text-xs font-medium">Discovered Only</span>`;

    const win = document.createElement('div');
    win.id        = windowId;
    win.className = 'device-window fixed bg-gray-800 rounded-lg border border-gray-700 shadow-2xl flex flex-col';
    win.style.cssText = `width:720px; height:580px; top:${spawnTop}px; left:${spawnLeft}px; z-index:${++_dwTopZ};`;

    win.innerHTML = `
        <div class="resize-handle resize-handle-n"></div>
        <div class="resize-handle resize-handle-e"></div>
        <div class="resize-handle resize-handle-s"></div>
        <div class="resize-handle resize-handle-w"></div>
        <div class="resize-handle resize-handle-ne"></div>
        <div class="resize-handle resize-handle-nw"></div>
        <div class="resize-handle resize-handle-se"></div>
        <div class="resize-handle resize-handle-sw"></div>

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
                ${onBack ? `
                <button class="dw-back-btn px-2 py-1 text-xs text-blue-300 hover:text-blue-200 hover:bg-gray-600 rounded transition-colors flex items-center gap-1" title="Back to summary">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/>
                    </svg>
                    Summary
                </button>` : ''}
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

        <div class="dw-body flex-1 overflow-y-auto min-h-0"></div>`;

    document.body.appendChild(win);

    const header = win.querySelector('.window-header');
    header.addEventListener('mousedown', function(e) {
        if (e.target.closest('.dw-close-btn') || e.target.closest('.dw-maximize-btn')) return;
        _dwBringToFront(win);
        _dwActive  = win; _dwOp = 'drag';
        _dwStartX  = e.clientX; _dwStartY = e.clientY;
        _dwStartL  = win.offsetLeft; _dwStartT = win.offsetTop;
        e.preventDefault();
    });

    win.querySelectorAll('.resize-handle').forEach(function(handle) {
        handle.addEventListener('mousedown', function(e) {
            _dwBringToFront(win);
            const dir = Array.from(handle.classList)
                .find(c => c.startsWith('resize-handle-') && c !== 'resize-handle')
                .replace('resize-handle-', '');
            const rect = win.getBoundingClientRect();
            _dwActive  = win; _dwOp = dir;
            _dwStartX  = e.clientX; _dwStartY = e.clientY;
            _dwStartW  = win.offsetWidth; _dwStartH = win.offsetHeight;
            _dwStartL  = rect.left; _dwStartT = rect.top;
            win.style.left = rect.left + 'px';
            win.style.top  = rect.top  + 'px';
            e.preventDefault();
            e.stopPropagation();
        });
    });

    win.addEventListener('mousedown', function() { _dwBringToFront(win); });
    win.querySelector('.dw-close-btn').addEventListener('click', () => win.remove());

    // Back to Summary — close full window and reopen compact card
    const backBtn = win.querySelector('.dw-back-btn');
    if (backBtn && onBack) {
        backBtn.addEventListener('click', () => {
            win.remove();
            onBack();
        });
    }

    let _maximized = false, _savedStyle = null;
    win.querySelector('.dw-maximize-btn').addEventListener('click', function() {
        if (!_maximized) {
            _savedStyle = { w: win.style.width, h: win.style.height, t: win.style.top, l: win.style.left };
            win.style.cssText += 'width:100vw;height:100vh;top:0;left:0;';
            _maximized = true;
        } else {
            win.style.width  = _savedStyle.w;
            win.style.height = _savedStyle.h;
            win.style.top    = _savedStyle.t;
            win.style.left   = _savedStyle.l;
            _maximized = false;
        }
    });

    _dwPopulateBody(nodeData, win.querySelector('.dw-body'));
}

function _dwBringToFront(win) { win.style.zIndex = ++_dwTopZ; }

function _dwPopulateBody(nodeData, bodyEl) {
    if (nodeData.managed && nodeData.device_id) {
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
