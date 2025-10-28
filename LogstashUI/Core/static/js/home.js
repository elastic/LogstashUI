// Metrics Dashboard JavaScript
(function () {
    let currentFilters = {
        connection: '',
        host: '',
        pipeline: ''
    };

    // Initialize on page load
    document.addEventListener('DOMContentLoaded', function () {
        loadMetrics();
        setupEventListeners();
    });

    function setupEventListeners() {
        document.getElementById('connectionSelect').addEventListener('change', function (e) {
            currentFilters.connection = e.target.value;

            // Reset dependent dropdowns to "All"
            document.getElementById('hostSelect').value = '';
            document.getElementById('pipelineSelect').value = '';
            currentFilters.host = '';
            currentFilters.pipeline = '';

            loadMetrics();
        });

        document.getElementById('hostSelect').addEventListener('change', function (e) {
            currentFilters.host = e.target.value;

            // Reset pipeline dropdown to "All"
            document.getElementById('pipelineSelect').value = '';
            currentFilters.pipeline = '';

            loadMetrics();
        });

        document.getElementById('pipelineSelect').addEventListener('change', function (e) {
            currentFilters.pipeline = e.target.value;
            loadMetrics();
        });

        document.getElementById('refreshMetrics').addEventListener('click', function (e) {
            e.preventDefault();
            // Add spinning animation to the refresh button
            const btn = this;
            const svg = btn.querySelector('svg');
            svg.classList.add('animate-spin');

            loadMetrics();

            // Remove spinning animation after 1 second
            setTimeout(() => {
                svg.classList.remove('animate-spin');
            }, 1000);
        });
    }

    function loadMetrics() {
        loadNodeMetrics();
        loadPipelineMetrics();
    }

    function loadNodeMetrics() {
        const params = new URLSearchParams(currentFilters);

        fetch(`/API/GetNodeMetrics?${params}`)
            .then(response => response.json())
            .then(data => {
                // Update host dropdown with nodes from the response
                updateHostDropdown(data.nodes || []);
                renderNodeMetrics(data);
                renderNodeBreakdownTable(data.node_buckets || []);
            })
            .catch(error => {
                console.error('Error loading node metrics:', error);
                renderErrorState('nodeMetrics');
            });
    }

    function loadPipelineMetrics() {
        const params = new URLSearchParams(currentFilters);

        fetch(`/API/GetPipelineMetrics?${params}`)
            .then(response => response.json())
            .then(data => {
                renderPipelineMetrics(data);
            })
            .catch(error => {
                console.error('Error loading pipeline metrics:', error);
                renderErrorState('pipelineMetrics');
            });
    }

    function updateHostDropdown(nodes) {
        const hostSelect = document.getElementById('hostSelect');
        const currentValue = hostSelect.value;

        // Clear existing options except "All Hosts"
        hostSelect.innerHTML = '<option value="">All Hosts</option>';

        // Add nodes to dropdown
        nodes.forEach(node => {
            const option = document.createElement('option');
            option.value = node;
            option.textContent = node;
            if (node === currentValue) {
                option.selected = true;
            }
            hostSelect.appendChild(option);
        });
    }

    function renderNodeMetrics(data) {
        const container = document.getElementById('nodeMetrics');
        const nodeCount = data.nodes ? data.nodes.length : 0;
        const reloadSuccess = data.reloads ? data.reloads.successes || 0 : 0;
        const reloadFailures = data.reloads ? data.reloads.failures || 0 : 0;
        const eventsIn = data.events ? data.events.in || 0 : 0;
        const eventsOut = data.events ? data.events.out || 0 : 0;
        const queuedEvents = data.events ? data.events.queued || 0 : 0;
        const avgCpu = data.cpu || 0;
        const avgMemory = data.heap_memory || 0;

        container.innerHTML = `
            ${createMetricCard('Logstash Nodes', nodeCount, 'text-blue-400', 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z')}
            ${createMetricCard('Reloads', `${reloadSuccess} / ${reloadFailures}`, reloadFailures > 0 ? 'text-red-400' : 'text-green-400', 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15', 'Success / Failures')}
            ${createMetricCard('Events In/Out', `${formatNumber(eventsIn)} / ${formatNumber(eventsOut)}`, 'text-purple-400', 'M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4')}
            ${createMetricCard('Queued Events', formatNumber(queuedEvents), 'text-yellow-400', 'M4 6h16M4 10h16M4 14h16M4 18h16')}
            ${createMetricCard('Avg CPU', `${avgCpu.toFixed(1)}%`, 'text-red-400', 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z')}
            ${createMetricCard('Avg Heap Memory', `${avgMemory.toFixed(1)}%`, 'text-orange-400', 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4')}
        `;
    }
function renderPipelineMetrics(data) {
    const warningsContainer = document.getElementById('pipelineWarnings');
    const metricsContainer = document.getElementById('pipelineMetrics');
    const pipelineCount = data.pipelines ? data.pipelines.length : 0;
    const reloadSuccess = data.reloads ? data.reloads.successes || 0 : 0;
    const reloadFailures = data.reloads ? data.reloads.failures || 0 : 0;
    const eventsIn = data.events ? data.events.in || 0 : 0;
    const eventsOut = data.events ? data.events.out || 0 : 0;
    const avgDuration = data.duration || 0;

    // Render warnings in separate container for full width
    if (data.connections_with_no_data && data.connections_with_no_data.length > 0) {
        const connectionNames = data.connections_with_no_data.map(c => c.name).join(', ');
        warningsContainer.innerHTML = `
            <div class="bg-yellow-900/20 border border-yellow-600/50 rounded-lg p-4">
                <div class="flex items-start gap-3">
                    <svg class="w-6 h-6 text-yellow-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    <div class="flex-1">
                        <h3 class="text-yellow-400 font-semibold mb-1">No Pipeline Data Available</h3>
                        <p class="text-gray-300 text-sm mb-2">
                            The following connection(s) have no pipeline metrics in the last 30 minutes: <strong>${connectionNames}</strong>
                        </p>
                        <p class="text-gray-400 text-xs">Please verify:</p>
                        <ul class="text-gray-400 text-xs list-disc list-inside ml-2 mt-1">
                            <li>Elastic Agent is running and connected</li>
                            <li>Logstash integration is properly configured</li>
                            <li>Logstash API is accessible and responding</li>
                            <li>Pipeline metrics are being collected (check metrics-logstash.pipeline-* index)</li>
                        </ul>
                    </div>
                </div>
            </div>
        `;
    } else {
        warningsContainer.innerHTML = '';
    }

    // Render metric cards in grid container
    metricsContainer.innerHTML = `
        ${createMetricCard('Active Pipelines', pipelineCount, 'text-green-400', 'M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z')}
        ${createMetricCard('Reloads', `${reloadSuccess} / ${reloadFailures}`, reloadFailures > 0 ? 'text-red-400' : 'text-green-400', 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15', 'Success / Failures')}
        ${createMetricCard('Events In/Out', `${formatNumber(eventsIn)} / ${formatNumber(eventsOut)}`, 'text-purple-400', 'M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4')}
        ${createMetricCard('Avg Duration', `${avgDuration.toFixed(2)}ms`, 'text-blue-400', 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z')}
    `;

    // Render pipeline breakdown table
    renderPipelineBreakdownTable(data.pipeline_buckets || []);
}

    function createMetricCard(title, value, colorClass, iconPath, subtitle = '') {
        return `
            <div class="bg-gray-800 rounded-lg p-6 hover:bg-gray-750 transition-colors">
                <div class="flex items-center justify-between mb-2">
                    <h3 class="text-sm font-medium text-gray-400">${title}</h3>
                    <svg class="w-5 h-5 ${colorClass}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="${iconPath}" />
                    </svg>
                </div>
                <p class="text-3xl font-bold text-white mb-1">${value}</p>
                ${subtitle ? `<p class="text-xs text-gray-500">${subtitle}</p>` : ''}
            </div>
        `;
    }

    function renderErrorState(containerId) {
        const container = document.getElementById(containerId);
        container.innerHTML = `
            <div class="col-span-full bg-red-900/20 border border-red-600/50 rounded-lg p-6 text-center">
                <svg class="w-12 h-12 text-red-500 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <p class="text-red-400">Failed to load metrics. Please check your connection and the Elastic Agent integration to make sure there are no errors.</p>
            </div>
        `;
    }

    function renderNodeBreakdownTable(nodeBuckets) {
        const tbody = document.getElementById('nodeBreakdownBody');

        if (!nodeBuckets || nodeBuckets.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="11" class="px-6 py-8 text-center text-gray-400">
                        No node data available
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = nodeBuckets.map((bucket, index) => {
            const nodeData = bucket.last_hit.hits.hits[0]._source.logstash.node.stats;
            const logstashInfo = bucket.last_hit.hits.hits[0]._source.logstash.node.stats.logstash;

            const nodeName = bucket.key;
            const status = logstashInfo.status || 'unknown';
            const version = logstashInfo.version || 'N/A';
            const uptimeMs = nodeData.jvm.uptime_in_millis || 0;
            const uptime = formatUptime(uptimeMs);
            const cpuPercent = nodeData.os?.cpu?.percent || nodeData.process?.cpu?.percent || 0;
            const heapPercent = nodeData.jvm.mem.heap_used_percent || 0;
            const eventsIn = nodeData.events.in || 0;
            const eventsOut = nodeData.events.out || 0;
            const queued = nodeData.queue.events_count || 0;
            const reloadSuccess = nodeData.reloads.successes || 0;
            const reloadFailures = nodeData.reloads.failures || 0;

            const statusColor = {
                'green': 'bg-green-500',
                'yellow': 'bg-yellow-500',
                'red': 'bg-red-500'
            }[status] || 'bg-gray-500';

            const rowId = `node-row-${index}`;
            const logsRowId = `logs-row-${index}`;

            return `
                <tr class="hover:bg-gray-700/50 transition-colors" id="${rowId}">
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
                        <button onclick="toggleLogs('${nodeName}', ${index})" class="text-blue-400 hover:text-blue-300 focus:outline-none" id="expand-btn-${index}">
                            <svg class="w-5 h-5 transform transition-transform" id="expand-icon-${index}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                            </svg>
                        </button>
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-white">${nodeName}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
                        <span class="inline-flex items-center gap-2">
                            <span class="w-2 h-2 rounded-full ${statusColor}"></span>
                            ${status}
                        </span>
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${version}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${uptime}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${cpuPercent.toFixed(1)}%</td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${heapPercent}%</td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${formatNumber(eventsIn)}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${formatNumber(eventsOut)}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${formatNumber(queued)}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm">
                        <span class="${reloadFailures > 0 ? 'text-red-400' : 'text-green-400'}">
                            ${reloadSuccess} / ${reloadFailures}
                        </span>
                    </td>
                </tr>
                <tr id="${logsRowId}" class="hidden bg-gray-900">
                    <td colspan="11" class="px-6 py-4">
                        <div class="bg-gray-800 rounded-lg p-4">
                            <div class="flex justify-between items-center mb-4">
                                <h4 class="text-lg font-semibold text-white">Logs for ${nodeName}</h4>
                                <div class="flex gap-2">
                                    <button onclick="filterLogs(${index}, 'ALL')" class="px-3 py-1 text-xs font-semibold rounded transition-colors log-filter-btn-${index} bg-blue-600 text-white" data-level="ALL">
                                        All
                                    </button>
                                    <button onclick="filterLogs(${index}, 'ERROR')" class="px-3 py-1 text-xs font-semibold rounded transition-colors log-filter-btn-${index} bg-gray-700 text-gray-300 hover:bg-gray-600" data-level="ERROR">
                                        Error
                                    </button>
                                    <button onclick="filterLogs(${index}, 'WARN')" class="px-3 py-1 text-xs font-semibold rounded transition-colors log-filter-btn-${index} bg-gray-700 text-gray-300 hover:bg-gray-600" data-level="WARN">
                                        Warn
                                    </button>
                                    <button onclick="filterLogs(${index}, 'INFO')" class="px-3 py-1 text-xs font-semibold rounded transition-colors log-filter-btn-${index} bg-gray-700 text-gray-300 hover:bg-gray-600" data-level="INFO">
                                        Info
                                    </button>
                                </div>
                            </div>
                            <div id="logs-content-${index}" class="max-h-96 overflow-y-auto scrollbar-thin scrollbar-thumb-gray-600 scrollbar-track-gray-800">
                                <div class="text-center text-gray-400 py-4">
                                    <div class="animate-pulse">Loading logs...</div>
                                </div>
                            </div>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
    }

    let logsCache = {};
    let logsFilterLevel = {};

    async function toggleLogs(nodeName, index) {
        const logsRow = document.getElementById(`logs-row-${index}`);
        const expandIcon = document.getElementById(`expand-icon-${index}`);

        if (logsRow.classList.contains('hidden')) {
            // Expand
            logsRow.classList.remove('hidden');
            expandIcon.style.transform = 'rotate(90deg)';

            // Load logs if not cached
            if (!logsCache[nodeName]) {
                try {
                    const response = await fetch(`/API/GetLogs?logstash_node=${encodeURIComponent(nodeName)}`);
                    const logs = await response.json();
                    // Sort logs by timestamp (newest first) immediately after fetching
                    logsCache[nodeName] = logs.sort((a, b) => {
                        const timeA = new Date(a['@timestamp']).getTime();
                        const timeB = new Date(b['@timestamp']).getTime();
                        return timeB - timeA; // Descending order (newest first)
                    });
                    logsFilterLevel[index] = 'ALL'; // Default filter
                    renderLogs(logsCache[nodeName], index, 'ALL');
                } catch (error) {
                    console.error('Error loading logs:', error);
                    document.getElementById(`logs-content-${index}`).innerHTML = `
                        <div class="text-center text-red-400 py-4">
                            Failed to load logs. Please try again.
                        </div>
                    `;
                }
            } else {
                renderLogs(logsCache[nodeName], index, logsFilterLevel[index] || 'ALL');
            }
        } else {
            // Collapse
            logsRow.classList.add('hidden');
            expandIcon.style.transform = 'rotate(0deg)';
        }
    }

    function filterLogs(index, level) {
        // Update filter state
        logsFilterLevel[index] = level;

        // Update button styles
        const buttons = document.querySelectorAll(`.log-filter-btn-${index}`);
        buttons.forEach(btn => {
            if (btn.getAttribute('data-level') === level) {
                btn.className = `px-3 py-1 text-xs font-semibold rounded transition-colors log-filter-btn-${index} bg-blue-600 text-white`;
            } else {
                btn.className = `px-3 py-1 text-xs font-semibold rounded transition-colors log-filter-btn-${index} bg-gray-700 text-gray-300 hover:bg-gray-600`;
            }
        });

        // Find the node name for this index
        const nodeName = Object.keys(logsCache).find((name, idx) => {
            return document.getElementById(`logs-content-${index}`) !== null;
        });

        if (nodeName && logsCache[nodeName]) {
            renderLogs(logsCache[nodeName], index, level);
        }
    }

    function renderLogs(logs, index, filterLevel = 'ALL') {
        const logsContent = document.getElementById(`logs-content-${index}`);

        if (!logs || logs.length === 0) {
            logsContent.innerHTML = `
                <div class="text-center text-gray-400 py-4">
                    No logs available
                </div>
            `;
            return;
        }

        // Filter logs by level if not 'ALL'
        const filteredLogs = filterLevel === 'ALL'
            ? logs
            : logs.filter(log => {
                const level = log.log?.level || 'INFO';
                return level === filterLevel;
            });

        if (filteredLogs.length === 0) {
            logsContent.innerHTML = `
                <div class="text-center text-gray-400 py-4">
                    No logs found for level: ${filterLevel}
                </div>
            `;
            return;
        }

        logsContent.innerHTML = filteredLogs.map(log => {
            const level = log.log?.level || 'INFO';
            const message = log.message || 'No message';
            const timestamp = new Date(log['@timestamp']).toLocaleString();

            const levelColors = {
                'ERROR': 'text-red-400 bg-red-900/20',
                'WARN': 'text-yellow-400 bg-yellow-900/20',
                'INFO': 'text-blue-400 bg-blue-900/20',
                'DEBUG': 'text-gray-400 bg-gray-700/20',
                'TRACE': 'text-purple-400 bg-purple-900/20'
            };

            const levelColor = levelColors[level] || 'text-gray-400 bg-gray-700/20';

            return `
                <div class="border-b border-gray-700 py-3 hover:bg-gray-700/30 transition-colors">
                    <div class="flex items-start gap-3">
                        <span class="px-2 py-1 rounded text-xs font-semibold ${levelColor}">${level}</span>
                        <div class="flex-1 min-w-0">
                            <p class="text-sm text-gray-300 break-words">${message}</p>
                            <p class="text-xs text-gray-500 mt-1">${timestamp}</p>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }

    function formatUptime(milliseconds) {
        const seconds = Math.floor(milliseconds / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);

        if (days > 0) {
            return `${days}d ${hours % 24}h`;
        } else if (hours > 0) {
            return `${hours}h ${minutes % 60}m`;
        } else if (minutes > 0) {
            return `${minutes}m ${seconds % 60}s`;
        } else {
            return `${seconds}s`;
        }
    }

    function formatNumber(num) {
        if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
        if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
        return num.toString();
    }

    // Make functions available globally
    window.toggleLogs = toggleLogs;
    window.filterLogs = filterLogs;
function renderPipelineBreakdownTable(pipelineBuckets) {
    const tbody = document.getElementById('pipelineBreakdownBody');

    if (!pipelineBuckets || pipelineBuckets.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="10" class="px-6 py-8 text-center text-gray-400">
                    No pipeline data available
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = pipelineBuckets.map((bucket, index) => {
        try {
            const pipelineData = bucket.last_hit.hits.hits[0]._source.logstash.pipeline;

            const pipelineName = bucket.key;
            const hostName = pipelineData.host.name || 'N/A';
            const workers = pipelineData.info.workers || 0;
            const batchSize = pipelineData.info.batch_size || 0;
            const eventsIn = pipelineData.total.events.in || 0;
            const eventsOut = pipelineData.total.events.out || 0;
            const eventsFiltered = pipelineData.total.events.filtered || 0;
            const duration = pipelineData.total.time.duration.ms || 0;
            const reloadSuccess = pipelineData.total.reloads.successes || 0;
            const reloadFailures = pipelineData.total.reloads.failures || 0;

            const rowId = `pipeline-row-${index}`;
            const logsRowId = `pipeline-logs-row-${index}`;

            return `
            <tr class="hover:bg-gray-700/50 transition-colors" id="${rowId}">
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
                    <button onclick="togglePipelineLogs('${pipelineName}', ${index})" class="text-blue-400 hover:text-blue-300 focus:outline-none" id="pipeline-expand-btn-${index}">
                        <svg class="w-5 h-5 transform transition-transform" id="pipeline-expand-icon-${index}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                        </svg>
                    </button>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-white">${pipelineName}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${hostName}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${workers}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${batchSize}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${formatNumber(eventsIn)}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${formatNumber(eventsOut)}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${formatNumber(eventsFiltered)}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${duration.toFixed(2)}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm">
                    <span class="${reloadFailures > 0 ? 'text-red-400' : 'text-green-400'}">
                        ${reloadSuccess} / ${reloadFailures}
                    </span>
                </td>
            </tr>
            <tr id="${logsRowId}" class="hidden bg-gray-900">
                <td colspan="10" class="px-6 py-4">
                    <div class="bg-gray-800 rounded-lg p-4">
                        <div class="flex justify-between items-center mb-4">
                            <h4 class="text-lg font-semibold text-white">Logs for ${pipelineName}</h4>
                            <div class="flex gap-2">
                                <button onclick="filterPipelineLogs(${index}, 'ALL')" class="px-3 py-1 text-xs font-semibold rounded transition-colors pipeline-log-filter-btn-${index} bg-blue-600 text-white" data-level="ALL">
                                    All
                                </button>
                                <button onclick="filterPipelineLogs(${index}, 'ERROR')" class="px-3 py-1 text-xs font-semibold rounded transition-colors pipeline-log-filter-btn-${index} bg-gray-700 text-gray-300 hover:bg-gray-600" data-level="ERROR">
                                    Error
                                </button>
                                <button onclick="filterPipelineLogs(${index}, 'WARN')" class="px-3 py-1 text-xs font-semibold rounded transition-colors pipeline-log-filter-btn-${index} bg-gray-700 text-gray-300 hover:bg-gray-600" data-level="WARN">
                                    Warn
                                </button>
                                <button onclick="filterPipelineLogs(${index}, 'INFO')" class="px-3 py-1 text-xs font-semibold rounded transition-colors pipeline-log-filter-btn-${index} bg-gray-700 text-gray-300 hover:bg-gray-600" data-level="INFO">
                                    Info
                                </button>
                            </div>
                        </div>
                        <div id="pipeline-logs-content-${index}" class="max-h-96 overflow-y-auto scrollbar-thin scrollbar-thumb-gray-600 scrollbar-track-gray-800">
                            <div class="text-center text-gray-400 py-4">
                                <div class="animate-pulse">Loading logs...</div>
                            </div>
                        </div>
                    </div>
                </td>
            </tr>
        `;
        } catch (error) {
            console.error('Error rendering pipeline row:', error, bucket);
            return '';
        }
    }).join('');
}

    // Pipeline logs cache and filter state
    let pipelineLogsCache = {};
    let pipelineLogsFilterLevel = {};

    async function togglePipelineLogs(pipelineName, index) {
        const logsRow = document.getElementById(`pipeline-logs-row-${index}`);
        const expandIcon = document.getElementById(`pipeline-expand-icon-${index}`);

        if (logsRow.classList.contains('hidden')) {
            // Expand
            logsRow.classList.remove('hidden');
            expandIcon.style.transform = 'rotate(90deg)';

            // Load logs if not cached
            if (!pipelineLogsCache[pipelineName]) {
                try {
                    const response = await fetch(`/API/GetLogs?pipeline_name=${encodeURIComponent(pipelineName)}`);
                    const logs = await response.json();
                    // Sort logs by timestamp (newest first) immediately after fetching
                    pipelineLogsCache[pipelineName] = logs.sort((a, b) => {
                        const timeA = new Date(a['@timestamp']).getTime();
                        const timeB = new Date(b['@timestamp']).getTime();
                        return timeB - timeA; // Descending order (newest first)
                    });
                    pipelineLogsFilterLevel[index] = 'ALL'; // Default filter
                    renderPipelineLogs(pipelineLogsCache[pipelineName], index, 'ALL');
                } catch (error) {
                    console.error('Error loading pipeline logs:', error);
                    document.getElementById(`pipeline-logs-content-${index}`).innerHTML = `
                        <div class="text-center text-red-400 py-4">
                            Failed to load logs. Please try again.
                        </div>
                    `;
                }
            } else {
                renderPipelineLogs(pipelineLogsCache[pipelineName], index, pipelineLogsFilterLevel[index] || 'ALL');
            }
        } else {
            // Collapse
            logsRow.classList.add('hidden');
            expandIcon.style.transform = 'rotate(0deg)';
        }
    }

    function filterPipelineLogs(index, level) {
        // Update filter state
        pipelineLogsFilterLevel[index] = level;

        // Update button styles
        const buttons = document.querySelectorAll(`.pipeline-log-filter-btn-${index}`);
        buttons.forEach(btn => {
            if (btn.getAttribute('data-level') === level) {
                btn.className = `px-3 py-1 text-xs font-semibold rounded transition-colors pipeline-log-filter-btn-${index} bg-blue-600 text-white`;
            } else {
                btn.className = `px-3 py-1 text-xs font-semibold rounded transition-colors pipeline-log-filter-btn-${index} bg-gray-700 text-gray-300 hover:bg-gray-600`;
            }
        });

        // Find the pipeline name for this index
        const pipelineName = Object.keys(pipelineLogsCache).find((name, idx) => {
            return document.getElementById(`pipeline-logs-content-${index}`) !== null;
        });

        if (pipelineName && pipelineLogsCache[pipelineName]) {
            renderPipelineLogs(pipelineLogsCache[pipelineName], index, level);
        }
    }

    function renderPipelineLogs(logs, index, filterLevel = 'ALL') {
        const logsContent = document.getElementById(`pipeline-logs-content-${index}`);

        if (!logs || logs.length === 0) {
            logsContent.innerHTML = `
                <div class="text-center text-gray-400 py-4">
                    No logs available
                </div>
            `;
            return;
        }

        // Filter logs by level if not 'ALL'
        const filteredLogs = filterLevel === 'ALL'
            ? logs
            : logs.filter(log => {
                const level = log.log?.level || 'INFO';
                return level === filterLevel;
            });

        if (filteredLogs.length === 0) {
            logsContent.innerHTML = `
                <div class="text-center text-gray-400 py-4">
                    No logs found for level: ${filterLevel}
                </div>
            `;
            return;
        }

        logsContent.innerHTML = filteredLogs.map(log => {
            const level = log.log?.level || 'INFO';
            const message = log.message || 'No message';
            const timestamp = new Date(log['@timestamp']).toLocaleString();

            const levelColors = {
                'ERROR': 'text-red-400 bg-red-900/20',
                'WARN': 'text-yellow-400 bg-yellow-900/20',
                'INFO': 'text-blue-400 bg-blue-900/20',
                'DEBUG': 'text-gray-400 bg-gray-700/20',
                'TRACE': 'text-purple-400 bg-purple-900/20'
            };

            const levelColor = levelColors[level] || 'text-gray-400 bg-gray-700/20';

            return `
                <div class="border-b border-gray-700 py-3 hover:bg-gray-700/30 transition-colors">
                    <div class="flex items-start gap-3">
                        <span class="px-2 py-1 rounded text-xs font-semibold ${levelColor}">${level}</span>
                        <div class="flex-1 min-w-0">
                            <p class="text-sm text-gray-300 break-words">${message}</p>
                            <p class="text-xs text-gray-500 mt-1">${timestamp}</p>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }

    // Make pipeline functions available globally
    window.togglePipelineLogs = togglePipelineLogs;
    window.filterPipelineLogs = filterPipelineLogs;

})();