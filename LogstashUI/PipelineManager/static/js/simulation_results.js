/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

/**
 * Simulation Results Polling
 * Polls the GetSimulationResults endpoint and displays streaming results
 */

/**
 * Annotate an object with change status metadata
 * Walks through the object and marks fields based on the changes diff
 * Also includes deleted fields from the changes object
 */
function annotateWithChanges(obj, changes, path = '', inheritedStatus = null) {
    const annotated = {};
    
    // First, process existing fields
    for (const key in obj) {
        if (!obj.hasOwnProperty(key)) continue;
        
        const fullPath = path ? `${path}.${key}` : key;
        const value = obj[key];
        
        // Determine the status of this field
        let status = inheritedStatus; // Start with inherited status from parent
        if (changes) {
            if (changes.added && changes.added.hasOwnProperty(fullPath)) {
                status = 'added';
            } else if (changes.modified && changes.modified.hasOwnProperty(fullPath)) {
                status = 'modified';
            }
        }
        
        // If this is an object, recursively annotate it
        if (value && typeof value === 'object' && !Array.isArray(value)) {
            annotated[key] = {
                __status: status,
                __value: annotateWithChanges(value, changes, fullPath, status) // Pass status down
            };
        } else {
            annotated[key] = {
                __status: status,
                __value: value
            };
        }
    }
    
    // Now add deleted fields if we're at the root level (path is empty)
    if (path === '' && changes && changes.deleted) {
        for (const deletedPath in changes.deleted) {
            if (changes.deleted.hasOwnProperty(deletedPath)) {
                const deletedValue = changes.deleted[deletedPath];
                
                // Add the deleted field to the annotated object
                if (deletedValue && typeof deletedValue === 'object' && !Array.isArray(deletedValue)) {
                    annotated[deletedPath] = {
                        __status: 'deleted',
                        __value: annotateDeletedObject(deletedValue, 'deleted')
                    };
                } else {
                    annotated[deletedPath] = {
                        __status: 'deleted',
                        __value: deletedValue
                    };
                }
            }
        }
    }
    
    return annotated;
}

/**
 * Helper to annotate deleted objects - all nested fields inherit 'deleted' status
 */
function annotateDeletedObject(obj, status) {
    const annotated = {};
    
    for (const key in obj) {
        if (!obj.hasOwnProperty(key)) continue;
        
        const value = obj[key];
        
        if (value && typeof value === 'object' && !Array.isArray(value)) {
            annotated[key] = {
                __status: status,
                __value: annotateDeletedObject(value, status)
            };
        } else {
            annotated[key] = {
                __status: status,
                __value: value
            };
        }
    }
    
    return annotated;
}

/**
 * Syntax highlight JSON string with colors, optionally showing change context
 * @param {string} jsonString - The JSON string to highlight
 * @param {Object} changes - Optional diff object with added/modified/deleted fields
 * Returns HTML with colored JSON elements
 */
function highlightJSON(jsonString, changes = null) {
    try {
        // Parse the JSON
        const obj = JSON.parse(jsonString);

        // Add deleted fields to the object for display
        if (changes && changes.deleted) {
            for (const deletedPath in changes.deleted) {
                if (changes.deleted.hasOwnProperty(deletedPath)) {
                    obj[deletedPath] = changes.deleted[deletedPath];
                }
            }
        }

        // Annotate with change information
        const annotated = changes ? annotateWithChanges(obj, changes) : null;

        // Format for display
        const formatted = JSON.stringify(obj, null, 2);

        // Track path as we process lines
        let pathStack = [];
        let lastKey = '';

        const highlighted = formatted.split('\n').map(line => {
            const trimmed = line.trim();

            // Update path stack based on braces BEFORE processing the line
            if (trimmed.endsWith('{')) {
                // Line ends with opening brace - this key starts an object
                // The key will be captured in the regex below, then we push it
            } else if (trimmed === '}' || trimmed === '},') {
                // Closing brace - pop from stack
                if (pathStack.length > 0) {
                    pathStack.pop();
                }
            }

            let shouldPushKey = trimmed.endsWith('{');

            return line.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, (match) => {
                const escaped = match.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

                if (/^"/.test(match) && /:$/.test(match)) {
                    // This is a key
                    lastKey = match.slice(1, -2);

                    // If this line ends with {, push this key to the stack after we process it
                    if (shouldPushKey) {
                        pathStack.push(lastKey);
                        shouldPushKey = false; // Only push once per line
                    }

                    return `<span style="color: #60a5fa">${escaped}</span>`;
                } else {
                    // Value - get status from annotated object
                    const fullPath = pathStack.length > 0 ? pathStack.join('.') + '.' + lastKey : lastKey;
                    let color = '#ffffff';

                    if (annotated) {
                        const status = getStatus(annotated, fullPath);
                        if (status === 'added') color = '#86efac'; // green
                        else if (status === 'modified') color = '#fbbf24'; // yellow
                        else if (status === 'deleted') color = '#ef4444'; // red
                    }

                    if (/null/.test(match)) color = '#9ca3af';

                    return `<span style="color: ${color}">${escaped}</span>`;
                }
            });
        }).join('\n');

        return highlighted;
    } catch (e) {
        return jsonString.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
}

/**
 * Get the status of a field from the annotated object
 * Handles both dot-notation keys (like "log.original") and nested paths (like "observer.ip" -> "name")
 */
function getStatus(annotated, path) {
    // First, try the path as a single key (for Logstash dot-notation fields like "log.original")
    if (annotated[path] && annotated[path].__status) {
        return annotated[path].__status;
    }

    // Try as a nested path
    const parts = path.split('.');
    let current = annotated;

    // Try different combinations - e.g., for "observer.ip.name", try:
    // 1. "observer.ip" as key, then "name"
    // 2. "observer" -> "ip" -> "name"
    for (let i = parts.length - 1; i >= 0; i--) {
        const keyPart = parts.slice(0, i + 1).join('.');
        const remainingParts = parts.slice(i + 1);

        if (annotated[keyPart]) {
            // Found a key that matches - now traverse the remaining parts
            let temp = annotated[keyPart];

            if (remainingParts.length === 0) {
                // This is the exact field
                return temp.__status || null;
            }

            // Navigate through remaining parts
            for (const part of remainingParts) {
                if (!temp || !temp.__value || !temp.__value[part]) {
                    break;
                }
                temp = temp.__value[part];
            }

            if (temp && temp.__status) {
                return temp.__status;
            }
        }
    }

    // Fallback: try as fully nested path
    current = annotated;
    for (const part of parts) {
        if (!current || !current[part]) return null;

        const status = current[part].__status;
        if (status) return status;

        current = current[part].__value;
    }

    return null;
}

/**
 * Check if an event has parsing failure tags
 * Looks for common Logstash failure tags in the tags field
 * Also checks for custom tag_on_failure values if they exist in the event
 * @param {Object} event - The event object to check
 * @returns {Object} - Object with hasFailure boolean and failureTags array
 */
function checkForParsingFailures(event) {
    const result = {
        hasFailure: false,
        failureTags: []
    };

    if (!event) {
        return result;
    }


    // Common Logstash parsing failure tags
    const commonFailureTags = [
        '_grokparsefailure',
        '_dissectfailure',
        '_dateparsefailure',
        '_jsonparsefailure'
    ];

    // Check if event has a tags field
    if (event.tags && Array.isArray(event.tags)) {

        // Check for common failure tags (case-insensitive)
        const foundCommonFailures = event.tags.filter(tag =>
            typeof tag === 'string' && commonFailureTags.includes(tag.toLowerCase())
        );

        if (foundCommonFailures.length > 0) {
            result.hasFailure = true;
            result.failureTags.push(...foundCommonFailures);
        }

        // Also check for ANY tag that starts with underscore and contains "fail"
        // This catches custom failure tags like "_grok_syslog_wrapper_fail", "_grok_ciscotag_fail", etc.
        const customFailureTags = event.tags.filter(tag =>
            typeof tag === 'string' &&
            tag.startsWith('_') &&
            tag.toLowerCase().includes('fail')
        );

        if (customFailureTags.length > 0) {
            result.hasFailure = true;
            result.failureTags.push(...customFailureTags);
        }
    } else {
        console.error('checkForParsingFailures: Event has no tags field or tags is not an array');
    }

    // Remove duplicates from failureTags
    result.failureTags = [...new Set(result.failureTags)];


    return result;
}

/**
 * Helper to filter simulation metadata from event objects
 * Returns a copy without simulation, slot, run_id if Debug Metadata toggle is unchecked
 */
function filterMetadata(obj) {
    if (!obj) {
        return obj;
    }

    const toggle = document.getElementById('debugMetadataToggle');
    const showMetadata = toggle ? toggle.checked : false; // Default to hiding metadata

    if (showMetadata) {
        return obj; // Return original if showing metadata
    }

    // Create copy and remove metadata fields
    const copy = JSON.parse(JSON.stringify(obj));
    delete copy.simulation;
    delete copy.slot;
    delete copy.run_id;

    return copy;
}

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
            // Check for parsing failures ADDED by this plugin
            let hasFailure = false;
            let failureTags = [];
            if (node.eventJson && node.changes) {
                try {
                    // Check if this plugin ADDED any failure tags
                    // Look in the changes.added or changes.modified for the 'tags' field
                    const changes = typeof node.changes === 'string' ? JSON.parse(node.changes) : node.changes;

                    // Check if tags were added
                    if (changes.added && changes.added.tags) {
                        const addedTags = Array.isArray(changes.added.tags) ? changes.added.tags : [changes.added.tags];
                        const failureCheck = checkForParsingFailures({ tags: addedTags });
                        if (failureCheck.hasFailure) {
                            hasFailure = true;
                            failureTags = failureCheck.failureTags;
                        }
                    }

                    // Check if tags were modified (from old value to new value)
                    if (!hasFailure && changes.modified && changes.modified.tags) {
                        const modifiedTags = changes.modified.tags;
                        const oldTags = Array.isArray(modifiedTags.from) ? modifiedTags.from : [];
                        const newTags = Array.isArray(modifiedTags.to) ? modifiedTags.to : [];

                        // Find tags that were added (in new but not in old)
                        const addedInModification = newTags.filter(tag => !oldTags.includes(tag));

                        if (addedInModification.length > 0) {
                            const failureCheck = checkForParsingFailures({ tags: addedInModification });
                            if (failureCheck.hasFailure) {
                                hasFailure = true;
                                failureTags = failureCheck.failureTags;
                            }
                        }
                    }
                } catch (e) {
                    console.error('Error checking for failure tags in changes:', e);
                }
            }

            // Add badge indicator (success or failure)
            if (!componentElement.querySelector('.simulation-executed-badge')) {
                const badge = document.createElement('div');
                badge.className = 'simulation-executed-badge';

                if (hasFailure) {
                    // Failure badge - clean and professional
                    badge.innerHTML = '!';
                    badge.title = `PARSING FAILURE DETECTED\nFailed tags: ${failureTags.join(', ')}`;
                    badge.style.cssText = `
                        position: absolute;
                        bottom: 8px;
                        right: 8px;
                        width: 20px;
                        height: 20px;
                        background: #dc2626;
                        color: white;
                        border-radius: 3px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 13px;
                        font-weight: 700;
                        font-family: system-ui, -apple-system, sans-serif;
                        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
                        z-index: 10;
                        animation: badgePop 0.3s ease-out;
                    `;
                } else {
                    // Success badge
                    badge.innerHTML = '✓';
                    badge.title = 'Executed in simulation';
                    badge.style.cssText = `
                        position: absolute;
                        bottom: 8px;
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
                }

                componentElement.appendChild(badge);
            }

            // Add execution time badge if available
            if (node.executionTimeMs && !componentElement.querySelector('.simulation-timing-badge')) {
                const timingBadge = document.createElement('div');
                timingBadge.className = 'simulation-timing-badge';
                timingBadge.innerHTML = `⏱ ${node.executionTimeMs}ms`;
                timingBadge.title = `Execution time: ${node.executionTimeMs} milliseconds`;
                timingBadge.style.cssText = `
                    position: absolute;
                    top: 8px;
                    right: 120px;
                    padding: 4px 8px;
                    background: linear-gradient(135deg, #eab308, #ca8a04);
                    color: white;
                    border-radius: 12px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 11px;
                    font-weight: bold;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
                    z-index: 10;
                    animation: badgePop 0.3s ease-out;
                    white-space: nowrap;
                `;

                componentElement.appendChild(timingBadge);
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
        <svg class="hover-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-left: auto; opacity: 0.5;">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
            <path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
        </svg>
        <svg class="click-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="opacity: 0.5;">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122"></path>
        </svg>
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
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    `;

    // Store the original event data (filter metadata if toggle unchecked)
    const filtered = filterMetadata(originalEvent);
    dataFlow.dataset.eventJson = JSON.stringify(filtered, null, 2);

    // Add click to show sticky tooltip
    dataFlow.addEventListener('click', function(e) {
        e.stopPropagation();
        showDataFlowTooltip(e, this.dataset.eventJson, true, null); // No changes for original event
    });

    // Add hover effects and tooltip
    dataFlow.addEventListener('mouseenter', function(e) {
        this.style.background = 'linear-gradient(90deg, rgba(16, 185, 129, 0.2), rgba(5, 150, 105, 0.2))';
        this.style.borderColor = 'rgba(16, 185, 129, 0.5)';
        this.style.transform = 'translateX(4px)';
        this.style.boxShadow = '0 4px 6px rgba(16, 185, 129, 0.2)';

        // Make icons more visible on hover
        const icons = this.querySelectorAll('.hover-icon, .click-icon');
        icons.forEach(icon => icon.style.opacity = '1');

        // Show hover tooltip (non-sticky)
        showDataFlowTooltip(e, this.dataset.eventJson, false, null);
    });

    dataFlow.addEventListener('mouseleave', function() {
        this.style.background = 'linear-gradient(90deg, rgba(16, 185, 129, 0.1), rgba(5, 150, 105, 0.1))';
        this.style.borderColor = 'rgba(16, 185, 129, 0.3)';
        this.style.transform = 'translateX(0)';
        this.style.boxShadow = '0 1px 3px rgba(0, 0, 0, 0.1)';

        // Reset icon opacity
        const icons = this.querySelectorAll('.hover-icon, .click-icon');
        icons.forEach(icon => icon.style.opacity = '0.5');

        // Hide hover tooltip (only if not sticky)
        const tooltip = document.getElementById('data-flow-tooltip');
        if (tooltip && tooltip.style.display !== 'none' && !tooltip.querySelector('button[onclick*="hideDataFlowTooltip"]')) {
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
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M8 2v4"/>
            <path d="M16 2v4"/>
            <rect x="3" y="4" width="18" height="18" rx="2"/>
            <path d="M3 10h18"/>
        </svg>
        <span>View Full Event</span>
        <svg class="hover-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-left: auto; opacity: 0.5;">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
            <path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
        </svg>
        <svg class="click-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="opacity: 0.5;">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122"></path>
        </svg>
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
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    `;

    // Store the full event snapshot data for tooltip (from node's eventJson if available)
    let eventData = 'No data available';
    let changesData = null;
    if (node.eventJson) {
        // Parse, filter, and re-stringify
        const parsed = JSON.parse(node.eventJson);
        const filtered = filterMetadata(parsed);
        eventData = JSON.stringify(filtered, null, 2);
        changesData = node.changes || null; // Store changes for highlighting
    }
    dataFlow.dataset.eventJson = eventData;
    if (changesData) {
        dataFlow.dataset.changes = JSON.stringify(changesData);
    }

    // Add click to show sticky tooltip
    dataFlow.addEventListener('click', function(e) {
        e.stopPropagation();
        const changes = this.dataset.changes ? JSON.parse(this.dataset.changes) : null;
        showDataFlowTooltip(e, this.dataset.eventJson, true, changes); // sticky = true
    });

    // Add hover effects and tooltip
    dataFlow.addEventListener('mouseenter', function(e) {
        this.style.background = 'linear-gradient(90deg, rgba(59, 130, 246, 0.2), rgba(147, 51, 234, 0.2))';
        this.style.borderColor = 'rgba(59, 130, 246, 0.5)';
        this.style.transform = 'translateX(4px)';
        this.style.boxShadow = '0 4px 6px rgba(59, 130, 246, 0.2)';

        // Make icons more visible on hover
        const icons = this.querySelectorAll('.hover-icon, .click-icon');
        icons.forEach(icon => icon.style.opacity = '1');

        // Show hover tooltip (non-sticky)
        const changes = this.dataset.changes ? JSON.parse(this.dataset.changes) : null;
        showDataFlowTooltip(e, this.dataset.eventJson, false, changes);
    });

    dataFlow.addEventListener('mouseleave', function() {
        this.style.background = 'linear-gradient(90deg, rgba(59, 130, 246, 0.1), rgba(147, 51, 234, 0.1))';
        this.style.borderColor = 'rgba(59, 130, 246, 0.3)';
        this.style.transform = 'translateX(0)';
        this.style.boxShadow = '0 1px 3px rgba(0, 0, 0, 0.1)';

        // Reset icon opacity
        const icons = this.querySelectorAll('.hover-icon, .click-icon');
        icons.forEach(icon => icon.style.opacity = '0.5');

        // Hide hover tooltip (only if not sticky)
        const tooltip = document.getElementById('data-flow-tooltip');
        if (tooltip && tooltip.style.display !== 'none' && !tooltip.querySelector('button[onclick*="hideDataFlowTooltip"]')) {
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
 * @param {Object} changes - Optional changes object for context-aware highlighting
 */
function showDataFlowTooltip(event, eventJson, sticky = false, changes = null) {
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

        // Apply syntax highlighting with change context
        const highlightedJSON = highlightJSON(eventJson, changes);

        // Store the raw JSON data for copying
        tooltip.dataset.eventJson = eventJson;

        // Update content with close button and copy button
        tooltip.innerHTML = `
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                <div style="font-weight: 600; color: #60a5fa;">Event State at This Point:</div>
                <div style="display: flex; gap: 4px;">
                    <button onclick="copyTooltipData()" 
                            id="copyTooltipBtn"
                            style="background: #3b82f6; border: none; color: white; cursor: pointer; font-size: 11px; padding: 4px 8px; border-radius: 4px; display: flex; align-items: center; gap: 4px; font-family: system-ui, -apple-system, sans-serif;"
                            onmouseover="this.style.background='#2563eb'" onmouseout="this.style.background='#3b82f6'"
                            title="Copy JSON to clipboard">
                        <svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
                        </svg>
                        Copy
                    </button>
                    <button onclick="hideDataFlowTooltip()" 
                            style="background: transparent; border: none; color: #9ca3af; cursor: pointer; font-size: 16px; padding: 0; width: 20px; height: 20px; display: flex; align-items: center; justify-content: center;"
                            onmouseover="this.style.color='#fff'" onmouseout="this.style.color='#9ca3af'"
                            title="Close">✕</button>
                </div>
            </div>
            <pre style="margin: 0; white-space: pre-wrap;">${highlightedJSON}</pre>
        `;

        // Make draggable only when sticky
        makeDraggable(tooltip);
    } else {
        // Hover mode: allow copy button clicks but prevent other interactions
        tooltip.style.pointerEvents = 'auto';
        tooltip.style.cursor = 'default';

        // Apply syntax highlighting with change context
        const highlightedJSON = highlightJSON(eventJson, changes);

        // Store the raw JSON data for copying
        tooltip.dataset.eventJson = eventJson;

        tooltip.innerHTML = `
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                <div style="font-weight: 600; color: #60a5fa;">Event State at This Point:</div>
                <button onclick="copyTooltipData()" 
                        id="copyTooltipBtn"
                        style="background: #3b82f6; border: none; color: white; cursor: pointer; font-size: 11px; padding: 4px 8px; border-radius: 4px; display: flex; align-items: center; gap: 4px; font-family: system-ui, -apple-system, sans-serif; pointer-events: auto;"
                        onmouseover="this.style.background='#2563eb'" onmouseout="this.style.background='#3b82f6'"
                        title="Copy JSON to clipboard">
                    <svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
                    </svg>
                    Copy
                </button>
            </div>
            <pre style="margin: 0; white-space: pre-wrap;">${highlightedJSON}</pre>
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

    // Remove any existing mousedown handler to avoid duplicates
    element.onmousedown = null;

    element.onmousedown = dragMouseDown;

    function dragMouseDown(e) {
        // Don't drag if clicking on close button, copy button, or any interactive element
        if (e.target.tagName === 'BUTTON' ||
            e.target.closest('button') ||
            e.target.tagName === 'SVG' ||
            e.target.closest('svg')) {
            return;
        }

        e.preventDefault();
        e.stopPropagation();
        pos3 = e.clientX;
        pos4 = e.clientY;
        document.onmouseup = closeDragElement;
        document.onmousemove = elementDrag;

        // Add visual feedback that dragging is active
        element.style.cursor = 'grabbing';
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
        // Restore cursor
        element.style.cursor = 'move';
    }
}

/**
 * Copy tooltip JSON data to clipboard
 */
function copyTooltipData() {
    const tooltip = document.getElementById('data-flow-tooltip');
    if (!tooltip || !tooltip.dataset.eventJson) return;

    const jsonData = tooltip.dataset.eventJson;

    // Try to format the JSON nicely
    try {
        const parsed = JSON.parse(jsonData);
        const formatted = JSON.stringify(parsed, null, 2);

        // Copy to clipboard
        navigator.clipboard.writeText(formatted).then(() => {
            // Visual feedback - change button text and color temporarily
            const copyBtn = document.getElementById('copyTooltipBtn');
            if (copyBtn) {
                const originalHTML = copyBtn.innerHTML;
                const originalBg = copyBtn.style.background;

                copyBtn.innerHTML = `
                    <svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                    </svg>
                    Copied!
                `;
                copyBtn.style.background = '#10b981';
                copyBtn.onmouseover = null;
                copyBtn.onmouseout = null;

                // Reset after 2 seconds
                setTimeout(() => {
                    copyBtn.innerHTML = originalHTML;
                    copyBtn.style.background = originalBg;
                    copyBtn.onmouseover = function() { this.style.background = '#2563eb'; };
                    copyBtn.onmouseout = function() { this.style.background = '#3b82f6'; };
                }, 2000);
            }
        }).catch(err => {
            console.error('Failed to copy to clipboard:', err);
            alert('Failed to copy to clipboard. Please try again.');
        });
    } catch (e) {
        // If parsing fails, just copy the raw string
        navigator.clipboard.writeText(jsonData).then(() => {
            const copyBtn = document.getElementById('copyTooltipBtn');
            if (copyBtn) {
                const originalHTML = copyBtn.innerHTML;
                copyBtn.innerHTML = 'Copied!';
                setTimeout(() => {
                    copyBtn.innerHTML = originalHTML;
                }, 2000);
            }
        }).catch(err => {
            console.error('Failed to copy to clipboard:', err);
            alert('Failed to copy to clipboard. Please try again.');
        });
    }
}

/**
 * Hide the data flow tooltip
 */
function hideDataFlowTooltip() {
    const tooltip = document.getElementById('data-flow-tooltip');
    if (tooltip) {
        tooltip.style.display = 'none';
        // Reset pointer events to default for next use
        tooltip.style.pointerEvents = 'none';
        tooltip.style.cursor = 'default';
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


    graphData.nodes.forEach((node, i) => {
        node.x = padding + (node.step * nodeSpacing); // Space nodes horizontally with proper spacing
        node.y = height / 2; // Center all nodes vertically for linear flow
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
            showLinkTooltip(event, d.eventJson, true, d.changes);
        })
        .on("mouseover", function(event, d) {
            // Highlight the link
            d3.select(this.previousSibling)
                .attr("stroke", "#22c55e")
                .attr("stroke-width", 3);

            // Show hover tooltip
            showLinkTooltip(event, d.eventJson, false, d.changes);
        })
        .on("mouseout", function(event, d) {
            // Reset link style
            d3.select(this.previousSibling)
                .attr("stroke", "#6b7280")
                .attr("stroke-width", 2);

            // Hide hover tooltip immediately
            hideLinkTooltip();
        });

    // Create node groups (no drag behavior since positions are fixed)
    const node = container.append("g")
        .selectAll("g")
        .data(graphData.nodes)
        .enter().append("g");

    // Add shapes to nodes (circles for regular, hexagons for decision points)
    node.each(function(d) {
        const nodeGroup = d3.select(this);

        // Check for parsing failures ADDED by this node
        let hasFailure = false;
        let failureTags = [];
        if (d.eventJson && !d.isConditional && d.changes) {
            try {
                // Check if this plugin ADDED any failure tags
                const changes = typeof d.changes === 'string' ? JSON.parse(d.changes) : d.changes;

                // Check if tags were added
                if (changes.added && changes.added.tags) {
                    const addedTags = Array.isArray(changes.added.tags) ? changes.added.tags : [changes.added.tags];
                    const failureCheck = checkForParsingFailures({ tags: addedTags });
                    if (failureCheck.hasFailure) {
                        hasFailure = true;
                        failureTags = failureCheck.failureTags;
                    }
                }

                // Check if tags were modified (from old value to new value)
                if (!hasFailure && changes.modified && changes.modified.tags) {
                    const modifiedTags = changes.modified.tags;
                    const oldTags = Array.isArray(modifiedTags.from) ? modifiedTags.from : [];
                    const newTags = Array.isArray(modifiedTags.to) ? modifiedTags.to : [];

                    // Find tags that were added (in new but not in old)
                    const addedInModification = newTags.filter(tag => !oldTags.includes(tag));

                    if (addedInModification.length > 0) {
                        const failureCheck = checkForParsingFailures({ tags: addedInModification });
                        if (failureCheck.hasFailure) {
                            hasFailure = true;
                            failureTags = failureCheck.failureTags;
                        }
                    }
                }

                // Store failure info on the node for tooltip
                d.hasFailure = hasFailure;
                d.failureTags = failureTags;
            } catch (e) {
                console.error('Error checking for failure tags in changes:', e);
            }
        }

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
            // Color based on failure status, then changes
            let fillColor, strokeColor;
            if (hasFailure) {
                fillColor = "#dc2626"; // Red for failures
                strokeColor = "#ef4444";
            } else if (d.hasChanges) {
                fillColor = "#16a34a"; // Green for changes
                strokeColor = "#22c55e";
            } else {
                fillColor = "#4b5563"; // Gray for no changes
                strokeColor = "#6b7280";
            }

            nodeGroup.append("circle")
                .attr("r", 18)
                .attr("fill", fillColor)
                .attr("stroke", strokeColor)
                .attr("stroke-width", hasFailure ? 3 : 2)
                .style("cursor", "pointer")
                .style("filter", hasFailure ? "drop-shadow(0 0 8px rgba(220, 38, 38, 0.8))" : "none")
                .on("mouseover", function(event, d) {
                    const isSlowest = d.isSlowest;
                    d3.select(this)
                        .attr("stroke-width", hasFailure ? 4 : 3)
                        .attr("stroke", isSlowest ? "#60a5fa" : (hasFailure ? strokeColor : strokeColor))
                        .attr("r", 22);
                    showNodeTooltip(event, d);
                })
                .on("mouseout", function(event, d) {
                    d3.select(this)
                        .attr("stroke-width", hasFailure ? 3 : 2)
                        .attr("stroke", strokeColor)
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

    // Find the slowest plugin (highest execution time)
    let slowestNode = null;
    let maxExecutionTime = 0;
    graphData.nodes.forEach(n => {
        if (n.executionTimeMs && parseFloat(n.executionTimeMs) > maxExecutionTime) {
            maxExecutionTime = parseFloat(n.executionTimeMs);
            slowestNode = n;
        }
    });

    // Mark slowest node for later reference
    if (slowestNode) {
        slowestNode.isSlowest = true;
    }

    // Add execution time text below nodes (if available)
    node.each(function(d) {
        if (d.executionTimeMs) {
            const isSlowest = d.isSlowest;
            const nodeGroup = d3.select(this);
            
            nodeGroup.append("text")
                .text(`${d.executionTimeMs}ms`)
                .attr("text-anchor", "middle")
                .attr("dy", "3.2em")
                .attr("fill", isSlowest ? "#60a5fa" : "#fbbf24")
                .attr("font-size", "9px")
                .attr("font-weight", "600")
                .style("pointer-events", "none");
        }
    });

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

        // Special handling for "Start" node - scroll to Original Event
        if (d.id === 'start') {
            const originalEventElement = document.querySelector('.simulation-data-flow');
            if (originalEventElement) {
                originalEventElement.scrollIntoView({
                    behavior: 'smooth',
                    block: 'center'
                });

                // Apply the same glowing animation
                originalEventElement.classList.add('newly-added');

                // Remove the animation class after it completes
                setTimeout(() => {
                    originalEventElement.classList.remove('newly-added');
                }, 2000);
            }
            return;
        }

        // Special handling for "End" node - scroll to last "View Full Event"
        if (d.id === 'end') {
            const allDataFlows = document.querySelectorAll('.simulation-data-flow');
            if (allDataFlows.length > 0) {
                const lastDataFlow = allDataFlows[allDataFlows.length - 1];
                lastDataFlow.scrollIntoView({
                    behavior: 'smooth',
                    block: 'center'
                });

                // Apply the same glowing animation
                lastDataFlow.classList.add('newly-added');

                // Remove the animation class after it completes
                setTimeout(() => {
                    lastDataFlow.classList.remove('newly-added');
                }, 2000);
            }
            return;
        }

        // Extract the component ID from the node
        let componentId = d.id;

        // For decision point nodes, find the first plugin in the taken branch instead
        if (d.isDecisionPoint) {
            // Find the next node in the graph that is NOT a decision point
            // This will be the first plugin in the condition branch
            const currentStep = d.step;
            const nextPlugin = graphData.nodes.find(node =>
                node.step > currentStep && !node.isDecisionPoint && node.id !== 'start'
            );

            if (nextPlugin) {
                componentId = nextPlugin.id;
            } else {
                // Fallback to the condition block if no plugin found
                componentId = d.conditionalId;
            }
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
        } else {
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

    function showLinkTooltip(event, eventJson, sticky = false, changes = null) {
        // Apply syntax highlighting with change context
        const highlightedJSON = highlightJSON(eventJson, changes);

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
                    <pre style="margin: 0; white-space: pre-wrap;">${highlightedJSON}</pre>
                </div>
            `;
            linkTooltip.html(content);

            // Make draggable
            makeDraggable(linkTooltip.node());
        } else {
            linkTooltip.html(`
                <div style="font-weight: 600; color: #9ca3af; margin-bottom: 0.5rem;">Event State:</div>
                <pre style="margin: 0; white-space: pre-wrap;">${highlightedJSON}</pre>
            `);
        }

        linkTooltip
            .style("visibility", "visible")
            .style("left", (event.clientX + 10) + "px")
            .style("top", (event.clientY - 10) + "px");
    }

    function hideLinkTooltip() {
        linkTooltip.style("visibility", "hidden")
            .style("pointer-events", "none")
            .style("cursor", "default");
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
            // Regular plugin node - show changes and failure status
            let titleColor = d.hasFailure ? '#ef4444' : '#9ca3af';
            let failureWarning = '';
            let slowestWarning = '';

            if (d.hasFailure) {
                failureWarning = `<div style="background: rgba(220, 38, 38, 0.2); border: 2px solid #dc2626; border-radius: 6px; padding: 8px; margin-bottom: 0.5rem;">
                    <div style="font-weight: 700; color: #fca5a5; margin-bottom: 0.25rem; font-size: 12px;">⚠ PARSING FAILURE DETECTED</div>
                    <div style="font-weight: 600; color: #9ca3af; margin-bottom: 0.25rem; font-size: 10px;">Failed tags:</div>
                    <div style="color: #ef4444; font-weight: 600; font-size: 11px;">${d.failureTags.join(', ')}</div>
                </div>`;
            }

            if (d.isSlowest) {
                slowestWarning = `<div style="background: rgba(96, 165, 250, 0.15); border: 2px solid #60a5fa; border-radius: 6px; padding: 8px; margin-bottom: 0.5rem;">
                    <div style="font-weight: 700; color: #60a5fa; margin-bottom: 0.25rem; font-size: 12px;">🐌 Slowest Plugin</div>
                    <div style="font-weight: 600; color: #9ca3af; margin-bottom: 0.25rem; font-size: 10px;">Execution time:</div>
                    <div style="color: #60a5fa; font-weight: 600; font-size: 11px;">${d.executionTimeMs}ms</div>
                </div>`;
            }

            title = `<div style="font-weight: 600; color: ${titleColor}; margin-bottom: 0.5rem;">Step ${d.step}: ${d.label}<br/><span style="font-weight: 400; font-size: 10px;">${d.id}</span></div>`;
            content = slowestWarning + failureWarning + (d.hasChanges
                ? `<div style="font-weight: 600; color: #9ca3af; margin-bottom: 0.25rem;">Changes:</div><pre style="color: #86efac; white-space: pre-wrap; margin: 0;">${d.changesText}</pre>`
                : `<div style="color: #6b7280; font-style: italic;">No changes</div>`);
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

        // Apply syntax highlighting to the event JSON
        const highlightedEventJson = highlightJSON(eventJson);

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
                    <pre class="text-xs bg-gray-900 p-3 rounded border border-gray-700 overflow-x-auto">${highlightedEventJson}</pre>
                </div>
            </div>
        `;
    });

    return html || '<div class="text-gray-500 text-center py-8">No simulation data available</div>';
};

// Global function to toggle overlay expansion
window.toggleOverlayExpand = function() {
    const overlay = document.getElementById('simulation-overlay');
    const expandBtn = document.getElementById('expandOverlayBtn');

    if (!overlay) return;

    const isExpanded = overlay.style.height === '100vh' || overlay.style.height === '100%';

    if (isExpanded) {
        // Collapse back to 150px
        overlay.style.height = '150px';
        if (expandBtn) {
            expandBtn.title = 'Expand to full screen';
            expandBtn.innerHTML = `<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"></path>
            </svg>`;
        }
    } else {
        // Expand to full screen
        overlay.style.height = '100vh';
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
    // Check if we have a run_id for this document
    if (!window.simulationRunIds || !window.simulationRunIds[index]) {
        console.error('No run_id available for document', index);
        console.error('Available run_ids:', window.simulationRunIds);
        alert('Document ' + (index + 1) + ' is still being submitted. Please wait a moment and try again.');
        return;
    }

    const runId = window.simulationRunIds[index];

    // Initialize results cache if needed
    if (!window.simulationResultsCache) {
        window.simulationResultsCache = {};
    }

    // Check if we have cached results for this run_id
    if (window.simulationResultsCache[runId]) {
        renderCachedResults(runId, index);
    } else {
        // Clear existing simulation artifacts
        clearSimulationArtifacts();

        // Update counter
        updateDocumentCounter();

        // Show loading indicator
        const loadingIndicator = document.getElementById('simulation-loading-indicator');
        if (loadingIndicator) {
            loadingIndicator.style.display = 'flex';
        } else {
            console.error('Loading indicator not found');
        }

        // Hide view mode selector during reload
        const viewModeSelector = document.getElementById('viewModeSelector');
        if (viewModeSelector) {
            viewModeSelector.style.display = 'none';
        }

        // Start polling for this run_id
        initSimulationResults(runId);
    }
}

function renderCachedResults(runId, index) {
    const cachedData = window.simulationResultsCache[runId];

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

        // Display total execution time
        const totalTimeElement = document.getElementById('totalExecutionTime');
        if (totalTimeElement && cachedData.totalExecutionTimeMs) {
            totalTimeElement.textContent = `⏱ ${cachedData.totalExecutionTimeMs}ms`;
            totalTimeElement.style.display = 'inline';
        }

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
    document.querySelectorAll('.simulation-timing-badge').forEach(badge => badge.remove());
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
        return;
    }
    window.activePollers.add(runId);

    let pollCount = 0;
    const maxPolls = 120; // Poll for 120 * 250ms = 30 seconds max
    const pollInterval = 250; // Poll every 250ms for faster updates
    let receivedFinal = false; // Track if we've received the final event
    let originalEvent = null; // Store the original event for baseline comparison


    // Add a 10-second timeout to show a warning message
    const loadingTimeout = setTimeout(() => {
        if (!receivedFinal) {
            const loadingIndicator = document.getElementById('simulation-loading-indicator');
            if (loadingIndicator) {
                // Check if warning doesn't already exist
                if (!document.getElementById('loading-timeout-warning')) {
                    const warning = document.createElement('span');
                    warning.id = 'loading-timeout-warning';
                    warning.className = 'text-xs text-yellow-400 ml-2';
                    warning.textContent = 'This is taking a while, you should check the logs using the button to the right.';
                    loadingIndicator.appendChild(warning);
                }
            }
        }
    }, 10000); // 10 seconds

    function pollResults() {
        // Stop if we've received the final event
        if (receivedFinal) {
            return;
        }

        if (pollCount >= maxPolls) {
            const stream = document.getElementById('results-stream');
            if (stream && stream.innerHTML.trim() === '') {
                stream.innerHTML = '<span class="text-yellow-400">No results received. Check Logstash logs.</span>';
            }
            return;
        }

        fetch(`/ConnectionManager/GetSimulationResults/?run_id=${encodeURIComponent(runId)}`)
            .then(response => response.json())
            .then(data => {


                if (data.results && data.results.length > 0) {

                    data.results.forEach(event => {
                        // Check if this is the original event
                        if (event.simulation.id === 'original') {
                            originalEvent = event;
                        }
                        // Check if this is the final event
                        else if (event.simulation.id === 'final') {
                                receivedFinal = true;

                                // Check if no plugins were executed (empty or missing snapshots)
                                const hasSnapshots = event.snapshots && Object.keys(event.snapshots).length > 0;

                                if (!hasSnapshots) {

                                    // Hide loading indicator
                                    const loadingIndicator = document.getElementById('simulation-loading-indicator');
                                    if (loadingIndicator) {
                                        loadingIndicator.style.display = 'none';
                                    }

                                    // Show message that no plugins were executed
                                    const resultsContainer = document.getElementById('results-container');
                                    if (resultsContainer) {
                                        resultsContainer.innerHTML = `
                                            <div class="w-full p-4 bg-yellow-900/30 border-y border-yellow-600">
                                                <div class="flex items-center gap-3">
                                                    <svg class="w-6 h-6 text-yellow-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
                                                    </svg>
                                                    <div>
                                                        <h3 class="text-base font-semibold text-yellow-400">No Plugins Executed</h3>
                                                        <p class="text-sm text-yellow-200">
                                                            No plugins were triggered during this execution.
                                                        </p>
                                                    </div>
                                                </div>
                                            </div>
                                        `;
                                    }

                                    // Clear loading timeout
                                    if (loadingTimeout) {
                                        clearTimeout(loadingTimeout);
                                    }

                                    // Remove from active pollers
                                    if (window.activePollers) {
                                        window.activePollers.delete(runId);
                                    }

                                    return;
                                }

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
                                    const conditionalBranches = event.simulation?.conditional_branches || {};
                                    const conditionalConditions = event.simulation?.conditional_conditions || {};

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
                                                // Skip comment plugins - they don't execute in Logstash
                                                if (filterPlugin.plugin !== 'comment') {
                                                    const pluginId = filterPlugin.id;
                                                    const snapshot = event.snapshots[pluginId];

                                                    if (snapshot) {
                                                        stepNumber++;

                                                        // Filter metadata from both snapshots before comparing
                                                        const filteredPrevious = filterMetadata(previousSnapshot);
                                                        const filteredCurrent = filterMetadata(snapshot);

                                                        // Compare with previous snapshot (or original) and show only changes
                                                        const changes = diffObjects(filteredPrevious, filteredCurrent);

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

                                                        // Filter snapshot before storing
                                                        const filteredSnap = filterMetadata(snapshot);

                                                        // Extract timing data if available
                                                        let executionTimeMs = null;
                                                        if (snapshot.simulation && snapshot.simulation.timing && snapshot.simulation.timing.execution_ns) {
                                                            // Convert nanoseconds to milliseconds, rounded to 3 decimal places
                                                            executionTimeMs = (snapshot.simulation.timing.execution_ns / 1000000).toFixed(3);
                                                        }

                                                        // Add node with changes for context-aware highlighting
                                                        nodes.push({
                                                            id: pluginId,
                                                            label: filterPlugin.plugin,
                                                            step: stepNumber,
                                                            hasChanges: hasChanges,
                                                            changesText: changesText,
                                                            eventJson: JSON.stringify(filteredSnap, null, 2),
                                                            changes: changes, // Store changes for highlighting
                                                            isConditional: false,
                                                            executionTimeMs: executionTimeMs // Store execution time in milliseconds
                                                        });

                                                        // Add link from the last actual node that was added
                                                        // Include the snapshot (event state) for this link
                                                        links.push({
                                                            source: currentNodeId,
                                                            target: pluginId,
                                                            eventJson: JSON.stringify(filteredSnap, null, 2),
                                                            changes: changes, // Store changes for highlighting in tooltips
                                                            isConditional: false
                                                        });

                                                        // Update current node ID for next iteration
                                                        currentNodeId = pluginId;

                                                        // Update previous snapshot for next iteration
                                                        previousSnapshot = snapshot;
                                                    }
                                                }
                                            }
                                        });

                                        return currentNodeId;
                                    }

                                    // Process all filter plugins
                                    const finalNodeId = processPlugins(components.filter, lastNodeId);

                                    // Add ending node
                                    stepNumber++;
                                    nodes.push({
                                        id: 'end',
                                        label: 'End',
                                        step: stepNumber,
                                        hasChanges: false,
                                        changesText: 'Pipeline complete',
                                        isConditional: false
                                    });

                                    // Connect final plugin to end node
                                    links.push({
                                        source: finalNodeId,
                                        target: 'end',
                                        eventJson: 'Pipeline complete',
                                        isConditional: false
                                    });

                                    // Calculate total execution time from all nodes
                                    let totalExecutionTimeMs = 0;
                                    nodes.forEach(node => {
                                        if (node.executionTimeMs) {
                                            totalExecutionTimeMs += parseFloat(node.executionTimeMs);
                                        }
                                    });

                                    // Store simulation data globally for view switching
                                    window.simulationData = { nodes, links, totalExecutionTimeMs: totalExecutionTimeMs.toFixed(3) };

                                    // Cache results for this run_id
                                    if (!window.simulationResultsCache) {
                                        window.simulationResultsCache = {};
                                    }
                                    window.simulationResultsCache[runId] = {
                                        nodes: nodes,
                                        links: links,
                                        originalEvent: originalEvent,
                                        totalExecutionTimeMs: totalExecutionTimeMs.toFixed(3)
                                    };

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

                                        // Display total execution time
                                        const totalTimeElement = document.getElementById('totalExecutionTime');
                                        if (totalTimeElement && totalExecutionTimeMs > 0) {
                                            totalTimeElement.textContent = `⏱ ${totalExecutionTimeMs.toFixed(3)}ms`;
                                            totalTimeElement.style.display = 'inline';
                                        }

                                        // Show view mode selector in overlay
                                        const viewModeSelector = document.getElementById('viewModeSelector');
                                        if (viewModeSelector) {
                                            viewModeSelector.style.display = 'flex';
                                        } else {
                                            console.error('viewModeSelector element not found in DOM');
                                        }

                                        // Show document navigation if multiple documents
                                        if (window.simulationDocuments && window.simulationDocuments.length > 1) {
                                            const docNav = document.getElementById('documentNavigation');
                                            if (docNav) {
                                                docNav.style.display = 'flex';
                                                updateDocumentCounter();
                                            }
                                        }

                                        // Hide loading indicator
                                        const loadingIndicator = document.getElementById('simulation-loading-indicator');
                                        if (loadingIndicator) {
                                            loadingIndicator.style.display = 'none';
                                        }

                                        // Clear the loading timeout
                                        if (loadingTimeout) {
                                            clearTimeout(loadingTimeout);
                                        }

                                        // Remove from active pollers
                                        if (window.activePollers) {
                                            window.activePollers.delete(runId);
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

/**
 * View Logstash logs for the current simulation
 */
window.viewSimulationLogs = function() {
    const overlay = document.getElementById('simulation-overlay');
    if (!overlay) {
        console.error('Simulation overlay not found');
        alert('Unable to fetch logs - simulation overlay not found');
        return;
    }
    
    const slotId = overlay.getAttribute('data-slot-id');
    if (!slotId) {
        console.error('Slot ID not found in overlay');
        alert('Unable to fetch logs - slot information not available');
        return;
    }
    
    // Show loading modal
    const modal = document.createElement('div');
    modal.id = 'logs-modal';
    modal.className = 'fixed inset-0 flex items-center justify-center z-[60] p-4';
    modal.innerHTML = `
        <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" onclick="document.getElementById('logs-modal').remove()"></div>
        <div class="bg-gray-800 rounded-lg w-full max-w-6xl max-h-[90vh] flex flex-col relative z-10 border border-gray-700">
            <div class="p-4 border-b border-gray-700 flex justify-between items-center">
                <h3 class="text-lg font-semibold text-white">Pipeline Logs - slot${slotId}-filter1</h3>
                <button onclick="document.getElementById('logs-modal').remove()" class="text-gray-400 hover:text-white">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
            </div>
            <div class="p-6 overflow-y-auto flex-grow">
                <div id="logs-content" class="bg-gray-900 rounded-lg p-4 font-mono text-sm text-gray-300">
                    <div class="flex items-center justify-center py-8">
                        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400"></div>
                        <span class="ml-3">Loading logs...</span>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Fetch logs from Django API endpoint
    fetch(`/ConnectionManager/GetRelatedLogs/?slot_id=${encodeURIComponent(slotId)}&max_entries=100&min_level=INFO`)
        .then(response => response.json())
        .then(data => {
            const logsContent = document.getElementById('logs-content');
            
            if (!data.logs || data.logs.length === 0) {
                logsContent.innerHTML = '<div class="text-yellow-400">No logs found for this pipeline.</div>';
                return;
            }
            
            let html = `<div class="text-green-400 mb-4">Found ${data.log_count} log entries - Time shown in UTC</div>`;
            
            data.logs.forEach((log, idx) => {
                const level = log.level || 'INFO';
                const levelColor = {
                    'ERROR': 'text-red-400',
                    'WARN': 'text-yellow-400',
                    'INFO': 'text-blue-400',
                    'DEBUG': 'text-gray-400'
                }[level] || 'text-gray-400';
                
                const timestamp = log.timeMillis ? new Date(log.timeMillis).toISOString() : 'N/A';
                const logEvent = log.logEvent || {};
                const message = logEvent.message || log.message || 'No message';
                const logger = log.loggerName || 'unknown';
                
                html += `
                    <div class="mb-4 pb-4 border-b border-gray-700">
                        <div class="flex items-center gap-3 mb-2">
                            <span class="${levelColor} font-bold">[${level}]</span>
                            <span class="text-gray-500 text-xs">${timestamp}</span>
                            <span class="text-gray-400 text-xs">${logger}</span>
                        </div>
                        <div class="text-gray-200 mb-2">${escapeHtml(message)}</div>
                        <details class="text-xs">
                            <summary class="cursor-pointer text-blue-400 hover:text-blue-300">View full log entry</summary>
                            <pre class="mt-2 p-2 bg-gray-950 rounded overflow-x-auto">${JSON.stringify(log, null, 2)}</pre>
                        </details>
                    </div>
                `;
            });
            
            logsContent.innerHTML = html;
        })
        .catch(error => {
            const logsContent = document.getElementById('logs-content');
            logsContent.innerHTML = `<div class="text-red-400">Error fetching logs: ${error.message}</div>`;
        });
};

// Global cleanup for tooltips - hide any open tooltips when clicking outside
document.addEventListener('click', function(e) {
    // Only hide if click is outside tooltip and not on a trigger
    const tooltip = document.getElementById('data-flow-tooltip');
    if (tooltip && !tooltip.contains(e.target) && !e.target.closest('.simulation-data-flow')) {
        hideDataFlowTooltip();
    }
    
    // Also clean up any D3 link tooltips
    const linkTooltip = document.querySelector('.d3-link-tooltip');
    if (linkTooltip && !linkTooltip.contains(e.target)) {
        linkTooltip.remove();
    }
});

