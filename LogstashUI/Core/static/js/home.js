// Metrics Dashboard JavaScript
(function () {
    // All filters and metrics loading now handled by HTMX
    // This file only contains log expansion/filtering functionality and host dropdown population

    // Listen for HTMX afterSwap event to update host dropdown
    document.body.addEventListener('htmx:afterSwap', function(event) {
        if (event.detail.target.id === 'nodeMetricsContainer') {
            // Extract available hosts from the response
            const hostsData = event.detail.xhr.getResponseHeader('X-Available-Hosts');
            if (hostsData) {
                try {
                    const hosts = JSON.parse(hostsData);
                    updateHostDropdown(hosts);
                } catch (e) {
                    console.error('Error parsing hosts data:', e);
                }
            }
        }
    });

    function updateHostDropdown(hosts) {
        const hostSelect = document.getElementById('hostSelect');
        const currentValue = hostSelect.value;
        
        // Clear existing options except "All Hosts"
        hostSelect.innerHTML = '<option value="">All Hosts</option>';
        
        // Add hosts to dropdown
        if (hosts && hosts.length > 0) {
            hosts.forEach(host => {
                const option = document.createElement('option');
                option.value = host;
                option.textContent = host;
                if (host === currentValue) {
                    option.selected = true;
                }
                hostSelect.appendChild(option);
            });
        }
    }

    let logsCache = {};
    let logsFilterLevel = {};
    let indexToNodeName = {};

    async function toggleLogs(nodeName, index) {
        const logsRow = document.getElementById(`logs-row-${index}`);
        const expandIcon = document.getElementById(`expand-icon-${index}`);

        if (logsRow.classList.contains('hidden')) {
            // Expand
            logsRow.classList.remove('hidden');
            expandIcon.style.transform = 'rotate(90deg)';

            // Store the mapping between index and node name
            indexToNodeName[index] = nodeName;

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

        // Get the node name from our mapping
        const nodeName = indexToNodeName[index];

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
                        <span class="px-2 py-1 rounded text-xs font-semibold flex-shrink-0 ${levelColor}">${level}</span>
                        <div class="flex-1 min-w-0 overflow-hidden">
                            <p class="text-sm text-gray-300 break-words" style="word-wrap: break-word; overflow-wrap: anywhere;">${message}</p>
                            <p class="text-xs text-gray-500 mt-1">${timestamp}</p>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }

    // formatUptime removed - now handled in Python view

    function formatNumber(num) {
        if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
        if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
        return num.toString();
    }

    // Make functions available globally
    window.toggleLogs = toggleLogs;
    window.filterLogs = filterLogs;

    // Pipeline logs cache and filter state
    let pipelineLogsCache = {};
    let pipelineLogsFilterLevel = {};
    let indexToPipelineName = {};

    async function togglePipelineLogs(pipelineName, index) {
        const logsRow = document.getElementById(`pipeline-logs-row-${index}`);
        const expandIcon = document.getElementById(`pipeline-expand-icon-${index}`);

        if (logsRow.classList.contains('hidden')) {
            // Expand
            logsRow.classList.remove('hidden');
            expandIcon.style.transform = 'rotate(90deg)';

            // Store the mapping between index and pipeline name
            indexToPipelineName[index] = pipelineName;

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

        // Get the pipeline name from our mapping
        const pipelineName = indexToPipelineName[index];

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
                        <span class="px-2 py-1 rounded text-xs font-semibold flex-shrink-0 ${levelColor}">${level}</span>
                        <div class="flex-1 min-w-0 overflow-hidden">
                            <p class="text-sm text-gray-300 break-words" style="word-wrap: break-word; overflow-wrap: anywhere;">${message}</p>
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