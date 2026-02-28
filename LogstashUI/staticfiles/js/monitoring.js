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

    async function toggleLogs(nodeName, index, connectionId) {
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
                    const response = await fetch(`/Monitoring/GetLogs?logstash_node=${encodeURIComponent(nodeName)}&connection_id=${encodeURIComponent(connectionId)}`);
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
                            <p class="text-sm text-gray-300 break-words" style="word-wrap: break-word; overflow-wrap: anywhere;">${escapeHtml(message)}</p>
                            <p class="text-xs text-gray-500 mt-1">${timestamp}</p>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }

    // Make functions available globally
    window.toggleLogs = toggleLogs;
    window.filterLogs = filterLogs;

    // Pipeline logs cache and filter state
    let pipelineLogsCache = {};
    let pipelineLogsFilterLevel = {};
    let indexToPipelineName = {};

    async function togglePipelineLogs(pipelineName, index, connectionId) {
        const logsRow = document.getElementById(`pipeline-logs-row-${index}`);
        const expandIcon = document.getElementById(`pipeline-expand-icon-${index}`);

        if (logsRow.classList.contains('hidden')) {
            // Expand
            logsRow.classList.remove('hidden');
            expandIcon.style.transform = 'rotate(90deg)';

            // Store the mapping between index and pipeline name
            indexToPipelineName[index] = pipelineName;

            // Load health report and logs in parallel
            const logsPromise = !pipelineLogsCache[pipelineName] 
                ? fetch(`/Monitoring/GetLogs?pipeline_name=${encodeURIComponent(pipelineName)}&connection_id=${encodeURIComponent(connectionId)}`)
                : Promise.resolve(null);
            
            const healthPromise = fetch(`/Monitoring/GetPipelineHealthReport?pipeline=${encodeURIComponent(pipelineName)}&connection_id=${encodeURIComponent(connectionId)}`);

            try {
                // Fetch health report
                const healthResponse = await healthPromise;
                const healthData = await healthResponse.json();
                renderPipelineHealthReport(healthData, index);
            } catch (error) {
                console.error('Error loading health report:', error);
                document.getElementById(`pipeline-health-content-${index}`).innerHTML = `
                    <div class="text-center text-red-400 py-4">
                        Failed to load health report. Please try again.
                    </div>
                `;
            }

            // Load logs if not cached
            if (!pipelineLogsCache[pipelineName]) {
                try {
                    const response = await logsPromise;
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
                            <p class="text-sm text-gray-300 break-words" style="word-wrap: break-word; overflow-wrap: anywhere;">${escapeHtml(message)}</p>
                            <p class="text-xs text-gray-500 mt-1">${timestamp}</p>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }

    function renderPipelineHealthReport(healthData, index) {
        const healthContent = document.getElementById(`pipeline-health-content-${index}`);
        
        // Check if we have health data - now expecting direct _source object
        if (!healthData || Object.keys(healthData).length === 0) {
            healthContent.innerHTML = `
                <div class="text-center text-gray-400 py-4">
                    No health report data available
                </div>
            `;
            return;
        }

        // healthData is now the _source directly
        const pipeline = healthData.logstash?.pipeline;
        
        if (!pipeline) {
            healthContent.innerHTML = `
                <div class="text-center text-gray-400 py-4">
                    No pipeline health data found
                </div>
            `;
            return;
        }

        // Determine status color
        const statusColors = {
            'green': 'bg-green-500',
            'yellow': 'bg-yellow-500',
            'red': 'bg-red-500',
            'unknown': 'bg-gray-500'
        };
        const statusColor = statusColors[pipeline.status] || 'bg-gray-500';
        
        // Build the health report HTML
        let html = `
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <!-- Status -->
                <div class="bg-gray-700 rounded-lg p-4">
                    <div class="flex items-center gap-3">
                        <span class="w-3 h-3 rounded-full ${statusColor}"></span>
                        <div>
                            <p class="text-xs text-gray-400">Status</p>
                            <p class="text-lg font-semibold text-white uppercase">${escapeHtml(pipeline.status) || 'Unknown'}</p>
                        </div>
                    </div>
                </div>
                
                <!-- State -->
                <div class="bg-gray-700 rounded-lg p-4">
                    <p class="text-xs text-gray-400">State</p>
                    <p class="text-lg font-semibold text-white">${escapeHtml(pipeline.state) || 'Unknown'}</p>
                </div>
            </div>
        `;

        // Add symptom, diagnosis, and impact in a single row if any exist
        if (pipeline.symptom || pipeline.diagnosis || pipeline.impacts) {
            html += `<div class="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">`;
            
            // Add symptom if exists
            if (pipeline.symptom) {
                html += `
                    <div class="bg-yellow-900/20 border border-yellow-600/50 rounded-lg p-4">
                        <p class="text-sm font-semibold text-yellow-400 mb-1">Symptom</p>
                        <p class="text-sm text-gray-300">${escapeHtml(pipeline.symptom)}</p>
                    </div>
                `;
            }

            // Add diagnosis if exists
            if (pipeline.diagnosis) {
                const diagnosis = pipeline.diagnosis;
                html += `
                    <div class="bg-red-900/20 border border-red-600/50 rounded-lg p-4">
                        <p class="text-sm font-semibold text-red-400 mb-2">Diagnosis</p>
                        <div class="space-y-2 text-sm">
                            ${diagnosis.cause ? `<p><span class="text-gray-400">Cause:</span> <span class="text-gray-300">${escapeHtml(diagnosis.cause)}</span></p>` : ''}
                            ${diagnosis.action ? `<p><span class="text-gray-400">Action:</span> <span class="text-gray-300">${escapeHtml(diagnosis.action)}</span></p>` : ''}
                            ${diagnosis.help_url ? `<p><a href="${escapeHtml(diagnosis.help_url)}" target="_blank" class="text-blue-400 hover:text-blue-300 underline">View Documentation →</a></p>` : ''}
                        </div>
                    </div>
                `;
            }

            // Add impacts if exists
            if (pipeline.impacts) {
                const impacts = pipeline.impacts;
                const severityColors = {
                    1: 'text-red-400',
                    2: 'text-yellow-400',
                    3: 'text-blue-400'
                };
                const severityColor = severityColors[impacts.severity] || 'text-gray-400';
                
                html += `
                    <div class="bg-orange-900/20 border border-orange-600/50 rounded-lg p-4">
                        <p class="text-sm font-semibold text-orange-400 mb-2">Impact</p>
                        <div class="space-y-2 text-sm">
                            <p><span class="text-gray-400">Severity:</span> <span class="${severityColor} font-semibold">${impacts.severity}</span></p>
                            ${escapeHtml(impacts.description) ? `<p><span class="text-gray-400">Description:</span> <span class="text-gray-300">${impacts.description}</span></p>` : ''}
                            ${escapeHtml(impacts.impact_areas) ? `<p><span class="text-gray-400">Areas:</span> <span class="text-gray-300">${impacts.impact_areas.join(', ')}</span></p>` : ''}
                        </div>
                    </div>
                `;
            }
            
            html += `</div>`;
        }

        // Add worker utilization if exists
        if (pipeline.flow && pipeline.flow.worker_utilization) {
            const wu = pipeline.flow.worker_utilization;
            html += `
                <div class="mt-4 bg-gray-700 rounded-lg p-4">
                    <p class="text-sm font-semibold text-white mb-3">Worker Utilization</p>
                    <div class="grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
                        <div><span class="text-gray-400">Current:</span> <span class="text-white font-semibold">${wu.current}%</span></div>
                        <div><span class="text-gray-400">1 Minute:</span> <span class="text-white">${wu.last_1_minute}%</span></div>
                        <div><span class="text-gray-400">5 Minutes:</span> <span class="text-white">${wu.last_5_minutes}%</span></div>
                        <div><span class="text-gray-400">15 Minutes:</span> <span class="text-white">${wu.last_15_minutes}%</span></div>
                        <div><span class="text-gray-400">1 Hour:</span> <span class="text-white">${wu.last_1_hour}%</span></div>
                        <div><span class="text-gray-400">Lifetime:</span> <span class="text-white">${wu.lifetime}%</span></div>
                    </div>
                </div>
            `;
        }

        healthContent.innerHTML = html;
    }

    // Make pipeline functions available globally
    window.togglePipelineLogs = togglePipelineLogs;
    window.filterPipelineLogs = filterPipelineLogs;

})();