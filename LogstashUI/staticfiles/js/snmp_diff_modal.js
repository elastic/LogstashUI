// ===== INLINE DIFF ALGORITHMS =====

/**
 * Compute Longest Common Subsequence using dynamic programming
 */
function computeLCS(arr1, arr2) {
    const m = arr1.length;
    const n = arr2.length;
    const dp = Array(m + 1).fill(null).map(() => Array(n + 1).fill(0));

    for (let i = 1; i <= m; i++) {
        for (let j = 1; j <= n; j++) {
            if (arr1[i - 1] === arr2[j - 1]) {
                dp[i][j] = dp[i - 1][j - 1] + 1;
            } else {
                dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
            }
        }
    }

    // Backtrack to find LCS
    const lcs = [];
    let i = m, j = n;
    while (i > 0 && j > 0) {
        if (arr1[i - 1] === arr2[j - 1]) {
            lcs.unshift(arr1[i - 1]);
            i--;
            j--;
        } else if (dp[i - 1][j] > dp[i][j - 1]) {
            i--;
        } else {
            j--;
        }
    }

    return lcs;
}

/**
 * Compute line-level diff using LCS algorithm
 */
function computeLineDiff(oldLines, newLines) {
    const changes = [];
    const lcs = computeLCS(oldLines, newLines);

    let i = 0, j = 0, k = 0;

    while (i < oldLines.length || j < newLines.length) {
        // Check if we're at a common line
        if (k < lcs.length && i < oldLines.length && j < newLines.length &&
            oldLines[i] === lcs[k] && newLines[j] === lcs[k]) {
            // Equal line
            const equalLines = [];
            while (k < lcs.length && i < oldLines.length && j < newLines.length &&
                oldLines[i] === lcs[k] && newLines[j] === lcs[k]) {
                equalLines.push(oldLines[i]);
                i++;
                j++;
                k++;
            }
            if (equalLines.length > 0) {
                changes.push({ type: 'equal', lines: equalLines });
            }
        } else {
            // Collect deletions and insertions
            const deletedLines = [];
            const insertedLines = [];

            while (i < oldLines.length && (k >= lcs.length || oldLines[i] !== lcs[k])) {
                deletedLines.push(oldLines[i]);
                i++;
            }

            while (j < newLines.length && (k >= lcs.length || newLines[j] !== lcs[k])) {
                insertedLines.push(newLines[j]);
                j++;
            }

            // If we have both deletions and insertions, treat as replacement
            if (deletedLines.length > 0 && insertedLines.length > 0) {
                changes.push({ type: 'replace', oldLines: deletedLines, newLines: insertedLines });
            } else if (deletedLines.length > 0) {
                changes.push({ type: 'delete', lines: deletedLines });
            } else if (insertedLines.length > 0) {
                changes.push({ type: 'insert', lines: insertedLines });
            }
        }
    }

    return changes;
}

// ===== END DIFF ALGORITHMS =====

function hideSnmpDiffModal() {
    document.getElementById('snmpDiffModal').classList.add('hidden');
}

function showSnmpDiffModal() {
    document.getElementById('snmpDiffModal').classList.remove('hidden');
}

/**
 * Prepare and show the SNMP diff modal
 * This fetches diffs for all networks and displays them
 */
async function prepareSnmpDiffModal() {
    // Show the modal first
    showSnmpDiffModal();

    // Show loading state
    document.getElementById('snmpDiffLoading').classList.remove('hidden');
    document.getElementById('snmpDiffContainer').classList.add('hidden');
    
    // Reset the commit button to enabled state (in case it was disabled from a previous commit)
    const confirmButton = document.getElementById('confirmCommitButton');
    confirmButton.classList.remove('hidden');
    confirmButton.disabled = false;
    confirmButton.textContent = 'Confirm & Commit Changes';
    confirmButton.classList.remove('opacity-50', 'cursor-not-allowed');

    try {
        // Fetch diff data from the server
        const response = await fetch('/API/SNMP/GetCommitDiff/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Failed to fetch diffs: ${response.status} - ${errorText}`);
        }

        const diffData = await response.json();
        console.log('SNMP Diff data received:', diffData);

        // Hide loading, show container
        document.getElementById('snmpDiffLoading').classList.add('hidden');
        document.getElementById('snmpDiffContainer').classList.remove('hidden');

        // Display the diffs for each network
        displayNetworkDiffs(diffData.networks);

        // Display overall stats
        const totalNetworks = diffData.networks.length;
        const newNetworks = diffData.networks.filter(n => !n.current || n.current.trim() === '').length;
        document.getElementById('snmpDiffStats').textContent =
            `${totalNetworks} network(s) • ${newNetworks} new pipeline(s)`;

    } catch (error) {
        console.error('Error preparing SNMP diff:', error);
        document.getElementById('snmpDiffLoading').innerHTML = `
            <div class="text-center">
                <p class="text-red-400 mb-4">Failed to load pipeline comparison</p>
                <p class="text-gray-400 text-sm">${error.message}</p>
                <button onclick="hideSnmpDiffModal()" class="mt-4 px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600">
                    Close
                </button>
            </div>
        `;
    }
}

/**
 * Display diffs for all networks
 */
function displayNetworkDiffs(networks) {
    const container = document.getElementById('snmpDiffContainer');

    let html = '';
    let networksWithChanges = 0;
    let newPipelinesCount = 0;
    let deletedPipelinesCount = 0;

    for (const network of networks) {
        // Skip main pipeline rendering if network has no devices (pipeline_name will be null)
        const hasMainPipeline = network.pipeline_name !== null;

        let currentLines = [];
        let newLines = [];
        let isNewPipeline = false;
        let hasChanges = false;
        let lineDiff = [];

        if (hasMainPipeline) {
            currentLines = network.current ? network.current.split('\n') : [];
            newLines = network.new.split('\n');

            // Check if this is a new pipeline (no current content)
            isNewPipeline = !network.current || network.current.trim() === '';

            // Compute diff
            lineDiff = computeLineDiff(currentLines, newLines);

            // Check if there are any actual changes (additions or deletions)
            hasChanges = lineDiff.some(change => change.type !== 'equal');

            // Track counts
            if (isNewPipeline) {
                newPipelinesCount++;
            } else if (hasChanges) {
                networksWithChanges++;
            }
        }

        // Skip this network entirely if it has no main pipeline and no trap pipeline
        if (!hasMainPipeline && !network.trap_pipeline) {
            continue;
        }

        // Skip main pipeline section if no changes and not new (but still show trap pipeline if exists)
        const shouldShowMainPipeline = hasMainPipeline && (isNewPipeline || hasChanges);

        let currentHtml = '';
        let newHtml = '';
        let currentLineNum = 1;
        let newLineNum = 1;

        if (isNewPipeline) {
            // For new pipelines, just show the new content on the right
            for (let i = 0; i < newLines.length; i++) {
                const line = escapeHtml(newLines[i]);

                currentHtml += `<div class="flex bg-gray-800/50">
                    <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                    <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                </div>`;

                newHtml += `<div class="flex bg-green-900/20 hover:bg-green-900/30">
                    <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${newLineNum++}</span>
                    <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                </div>`;
            }
        } else {
            // For existing pipelines, show the diff
            for (const change of lineDiff) {
                if (change.type === 'equal') {
                    // Unchanged lines - show on both sides without highlighting
                    for (let i = 0; i < change.lines.length; i++) {
                        const line = escapeHtml(change.lines[i]);

                        currentHtml += `<div class="flex hover:bg-gray-700/30">
                            <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${currentLineNum++}</span>
                            <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                        </div>`;

                        newHtml += `<div class="flex hover:bg-gray-700/30">
                            <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${newLineNum++}</span>
                            <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                        </div>`;
                    }
                } else if (change.type === 'delete') {
                    // Deleted lines - show only on left with red background
                    for (let i = 0; i < change.lines.length; i++) {
                        const line = escapeHtml(change.lines[i]);

                        currentHtml += `<div class="flex bg-red-900/20 hover:bg-red-900/30">
                            <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${currentLineNum++}</span>
                            <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                        </div>`;

                        // Empty placeholder on right side
                        newHtml += `<div class="flex bg-gray-800/50">
                            <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                            <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                        </div>`;
                    }
                } else if (change.type === 'insert') {
                    // Inserted lines - show only on right with green background
                    for (let i = 0; i < change.lines.length; i++) {
                        const line = escapeHtml(change.lines[i]);

                        // Empty placeholder on left side
                        currentHtml += `<div class="flex bg-gray-800/50">
                            <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                            <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                        </div>`;

                        newHtml += `<div class="flex bg-green-900/20 hover:bg-green-900/30">
                            <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${newLineNum++}</span>
                            <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                        </div>`;
                    }
                } else if (change.type === 'replace') {
                    // Modified lines - show with simple light background highlighting
                    const oldLines = change.oldLines;
                    const newLines = change.newLines;
                    const maxLen = Math.max(oldLines.length, newLines.length);

                    for (let i = 0; i < maxLen; i++) {
                        if (i < oldLines.length) {
                            const oldLine = escapeHtml(oldLines[i]);

                            currentHtml += `<div class="flex bg-red-900/20 hover:bg-red-900/30">
                                <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${currentLineNum++}</span>
                                <span style="white-space: pre; padding-left: 0.5rem;">${oldLine || ' '}</span>
                            </div>`;
                        } else {
                            currentHtml += `<div class="flex bg-gray-800/50">
                                <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                                <span style="white-space: pre; padding-left: 0.5rem;"></span>
                            </div>`;
                        }

                        if (i < newLines.length) {
                            const newLine = escapeHtml(newLines[i]);

                            newHtml += `<div class="flex bg-green-900/20 hover:bg-green-900/30">
                                <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${newLineNum++}</span>
                                <span style="white-space: pre; padding-left: 0.5rem;">${newLine || ' '}</span>
                            </div>`;
                        } else {
                            newHtml += `<div class="flex bg-gray-800/50">
                                <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                                <span style="white-space: pre; padding-left: 0.5rem;"></span>
                            </div>`;
                        }
                    }
                }
            }
        }

        // Build the network section with badge only if there are changes
        let networkBadge = '';
        if (isNewPipeline) {
            networkBadge = '<span class="ml-2 px-2 py-0.5 text-xs bg-green-600 text-white rounded">NEW</span>';
        } else if (hasChanges) {
            networkBadge = '<span class="ml-2 px-2 py-0.5 text-xs bg-blue-600 text-white rounded">MODIFIED</span>';
        }

        // Only show main pipeline section if network has devices
        if (shouldShowMainPipeline) {
            html += `
                <div class="border border-gray-600 rounded-lg overflow-hidden">
                    <div class="bg-gray-700 px-4 py-2 border-b border-gray-600">
                        <h4 class="text-white font-semibold">
                            ${escapeHtml(network.network_name)}${networkBadge}
                        </h4>
                        <p class="text-sm text-gray-400">Pipeline: ${escapeHtml(network.pipeline_name)}</p>
                    </div>
                    <div style="display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 0; height: 400px;">
                        <div class="p-4 bg-gray-700 border-r border-gray-600" style="display: flex; flex-direction: column; height: 100%; min-height: 0; min-width: 0;">
                            <div class="mb-2" style="flex-shrink: 0;">
                                <h5 class="text-sm font-semibold text-white">${isNewPipeline ? 'No Existing Pipeline' : 'Current Pipeline'}</h5>
                            </div>
                            <div class="bg-gray-800 rounded border border-gray-600 network-diff-scroll-panel" style="flex: 1; overflow-y: auto; overflow-x: auto; min-height: 0; min-width: 0;">
                                <div class="p-2 text-sm text-gray-300 font-mono">${currentHtml}</div>
                            </div>
                        </div>
                        <div class="p-4 bg-gray-700" style="display: flex; flex-direction: column; height: 100%; min-height: 0; min-width: 0;">
                            <div class="mb-2" style="flex-shrink: 0;">
                                <h5 class="text-sm font-semibold text-white">New Pipeline (After Commit)</h5>
                            </div>
                            <div class="bg-gray-800 rounded border border-gray-600 network-diff-scroll-panel" style="flex: 1; overflow-y: auto; overflow-x: auto; min-height: 0; min-width: 0;">
                                <div class="p-2 text-sm text-gray-300 font-mono">${newHtml}</div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }

        // Handle trap pipeline if it exists
        if (network.trap_pipeline) {
            const trapPipeline = network.trap_pipeline;
            const trapCurrentLines = trapPipeline.current ? trapPipeline.current.split('\n') : [];
            const trapNewLines = trapPipeline.new ? trapPipeline.new.split('\n') : [];

            // Check if there are actual changes in the trap pipeline
            let trapHasChanges = false;
            if (trapPipeline.action === 'create' || trapPipeline.action === 'delete') {
                trapHasChanges = true;
            } else if (trapPipeline.action === 'update') {
                // Compare current and new to see if there are actual differences
                const trapLineDiff = computeLineDiff(trapCurrentLines, trapNewLines);
                trapHasChanges = trapLineDiff.some(change => change.type !== 'equal');
            }

            // Only render trap pipeline if there are actual changes
            if (trapHasChanges) {
                // Count trap pipeline in summary only if there are changes
                if (trapPipeline.action === 'create') {
                    newPipelinesCount++;
                } else if (trapPipeline.action === 'update') {
                    networksWithChanges++;
                } else if (trapPipeline.action === 'delete') {
                    deletedPipelinesCount++;
                }

                let trapBadge = '';
                let trapCurrentHtml = '';
                let trapNewHtml = '';
                let trapCurrentLineNum = 1;
                let trapNewLineNum = 1;

                if (trapPipeline.action === 'create') {
                    trapBadge = '<span class="ml-2 px-2 py-0.5 text-xs bg-green-600 text-white rounded">NEW TRAP PIPELINE</span>';

                    // Show new trap pipeline
                    for (let i = 0; i < trapNewLines.length; i++) {
                        const line = escapeHtml(trapNewLines[i]);

                        trapCurrentHtml += `<div class="flex bg-gray-800/50">
                        <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                        <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                    </div>`;

                        trapNewHtml += `<div class="flex bg-green-900/20 hover:bg-green-900/30">
                        <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${trapNewLineNum++}</span>
                        <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                    </div>`;
                    }
                } else if (trapPipeline.action === 'delete') {
                    trapBadge = '<span class="ml-2 px-2 py-0.5 text-xs bg-red-600 text-white rounded">DELETING TRAP PIPELINE</span>';

                    // Show trap pipeline being deleted
                    for (let i = 0; i < trapCurrentLines.length; i++) {
                        const line = escapeHtml(trapCurrentLines[i]);

                        trapCurrentHtml += `<div class="flex bg-red-900/20 hover:bg-red-900/30">
                        <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${trapCurrentLineNum++}</span>
                        <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                    </div>`;

                        trapNewHtml += `<div class="flex bg-gray-800/50">
                        <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                        <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                    </div>`;
                    }
                } else if (trapPipeline.action === 'update') {
                    trapBadge = '<span class="ml-2 px-2 py-0.5 text-xs bg-blue-600 text-white rounded">UPDATING TRAP PIPELINE</span>';

                    // Compute diff for trap pipeline
                    const trapLineDiff = computeLineDiff(trapCurrentLines, trapNewLines);

                    for (const change of trapLineDiff) {
                        if (change.type === 'equal') {
                            for (let i = 0; i < change.lines.length; i++) {
                                const line = escapeHtml(change.lines[i]);
                                trapCurrentHtml += `<div class="flex hover:bg-gray-700/30">
                                <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${trapCurrentLineNum++}</span>
                                <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                            </div>`;
                                trapNewHtml += `<div class="flex hover:bg-gray-700/30">
                                <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${trapNewLineNum++}</span>
                                <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                            </div>`;
                            }
                        } else if (change.type === 'delete') {
                            for (let i = 0; i < change.lines.length; i++) {
                                const line = escapeHtml(change.lines[i]);
                                trapCurrentHtml += `<div class="flex bg-red-900/20 hover:bg-red-900/30">
                                <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${trapCurrentLineNum++}</span>
                                <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                            </div>`;
                                trapNewHtml += `<div class="flex bg-gray-800/50">
                                <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                                <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                            </div>`;
                            }
                        } else if (change.type === 'insert') {
                            for (let i = 0; i < change.lines.length; i++) {
                                const line = escapeHtml(change.lines[i]);
                                trapCurrentHtml += `<div class="flex bg-gray-800/50">
                                <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                                <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                            </div>`;
                                trapNewHtml += `<div class="flex bg-green-900/20 hover:bg-green-900/30">
                                <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${trapNewLineNum++}</span>
                                <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                            </div>`;
                            }
                        } else if (change.type === 'replace') {
                            const maxLen = Math.max(change.oldLines.length, change.newLines.length);
                            for (let i = 0; i < maxLen; i++) {
                                if (i < change.oldLines.length) {
                                    const oldLine = escapeHtml(change.oldLines[i]);
                                    trapCurrentHtml += `<div class="flex bg-red-900/20 hover:bg-red-900/30">
                                    <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${trapCurrentLineNum++}</span>
                                    <span style="white-space: pre; padding-left: 0.5rem;">${oldLine || ' '}</span>
                                </div>`;
                                } else {
                                    trapCurrentHtml += `<div class="flex bg-gray-800/50">
                                    <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                                    <span style="white-space: pre; padding-left: 0.5rem;"></span>
                                </div>`;
                                }
                                if (i < change.newLines.length) {
                                    const newLine = escapeHtml(change.newLines[i]);
                                    trapNewHtml += `<div class="flex bg-green-900/20 hover:bg-green-900/30">
                                    <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${trapNewLineNum++}</span>
                                    <span style="white-space: pre; padding-left: 0.5rem;">${newLine || ' '}</span>
                                </div>`;
                                } else {
                                    trapNewHtml += `<div class="flex bg-gray-800/50">
                                    <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                                    <span style="white-space: pre; padding-left: 0.5rem;"></span>
                                </div>`;
                                }
                            }
                        }
                    }
                }

                // Add trap pipeline section
                html += `
                <div class="border border-gray-600 rounded-lg overflow-hidden mt-4">
                    <div class="bg-gray-700 px-4 py-2 border-b border-gray-600">
                        <h4 class="text-white font-semibold">
                            ${escapeHtml(network.network_name)} - Trap Pipeline${trapBadge}
                        </h4>
                        <p class="text-sm text-gray-400">Pipeline: ${escapeHtml(trapPipeline.pipeline_name)}</p>
                    </div>
                    <div style="display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 0; height: 400px;">
                        <div class="p-4 bg-gray-700 border-r border-gray-600" style="display: flex; flex-direction: column; height: 100%; min-height: 0; min-width: 0;">
                            <div class="mb-2" style="flex-shrink: 0;">
                                <h5 class="text-sm font-semibold text-white">${trapPipeline.action === 'create' ? 'No Existing Trap Pipeline' : 'Current Trap Pipeline'}</h5>
                            </div>
                            <div class="bg-gray-800 rounded border border-gray-600 network-diff-scroll-panel" style="flex: 1; overflow-y: auto; overflow-x: auto; min-height: 0; min-width: 0;">
                                <div class="p-2 text-sm text-gray-300 font-mono">${trapCurrentHtml}</div>
                            </div>
                        </div>
                        <div class="p-4 bg-gray-700" style="display: flex; flex-direction: column; height: 100%; min-height: 0; min-width: 0;">
                            <div class="mb-2" style="flex-shrink: 0;">
                                <h5 class="text-sm font-semibold text-white">${trapPipeline.action === 'delete' ? 'Pipeline Will Be Deleted' : 'New Trap Pipeline (After Commit)'}</h5>
                            </div>
                            <div class="bg-gray-800 rounded border border-gray-600 network-diff-scroll-panel" style="flex: 1; overflow-y: auto; overflow-x: auto; min-height: 0; min-width: 0;">
                                <div class="p-2 text-sm text-gray-300 font-mono">${trapNewHtml}</div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            }
        }

        // Handle discovery pipeline if it exists
        if (network.discovery_pipeline) {
            const discoveryPipeline = network.discovery_pipeline;
            const discoveryCurrentLines = discoveryPipeline.current ? discoveryPipeline.current.split('\n') : [];
            const discoveryNewLines = discoveryPipeline.new ? discoveryPipeline.new.split('\n') : [];

            // Check if there are actual changes in the discovery pipeline
            let discoveryHasChanges = false;
            if (discoveryPipeline.action === 'create' || discoveryPipeline.action === 'delete') {
                discoveryHasChanges = true;
            } else if (discoveryPipeline.action === 'update') {
                // Compare current and new to see if there are actual differences
                const discoveryLineDiff = computeLineDiff(discoveryCurrentLines, discoveryNewLines);
                discoveryHasChanges = discoveryLineDiff.some(change => change.type !== 'equal');
            }

            // Only render discovery pipeline if there are actual changes
            if (discoveryHasChanges) {
                // Count discovery pipeline in summary only if there are changes
                if (discoveryPipeline.action === 'create') {
                    newPipelinesCount++;
                } else if (discoveryPipeline.action === 'update') {
                    networksWithChanges++;
                } else if (discoveryPipeline.action === 'delete') {
                    deletedPipelinesCount++;
                }

                let discoveryBadge = '';
                let discoveryCurrentHtml = '';
                let discoveryNewHtml = '';
                let discoveryCurrentLineNum = 1;
                let discoveryNewLineNum = 1;

                if (discoveryPipeline.action === 'create') {
                    discoveryBadge = '<span class="ml-2 px-2 py-0.5 text-xs bg-green-600 text-white rounded">NEW DISCOVERY PIPELINE</span>';

                    // Show new discovery pipeline
                    for (let i = 0; i < discoveryNewLines.length; i++) {
                        const line = escapeHtml(discoveryNewLines[i]);

                        discoveryCurrentHtml += `<div class="flex bg-gray-800/50">
                            <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                            <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                        </div>`;

                        discoveryNewHtml += `<div class="flex bg-green-900/20 hover:bg-green-900/30">
                            <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${discoveryNewLineNum++}</span>
                            <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                        </div>`;
                    }
                } else if (discoveryPipeline.action === 'delete') {
                    discoveryBadge = '<span class="ml-2 px-2 py-0.5 text-xs bg-red-600 text-white rounded">DELETING DISCOVERY PIPELINE</span>';

                    // Show discovery pipeline being deleted
                    for (let i = 0; i < discoveryCurrentLines.length; i++) {
                        const line = escapeHtml(discoveryCurrentLines[i]);

                        discoveryCurrentHtml += `<div class="flex bg-red-900/20 hover:bg-red-900/30">
                            <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${discoveryCurrentLineNum++}</span>
                            <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                        </div>`;

                        discoveryNewHtml += `<div class="flex bg-gray-800/50">
                            <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                            <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                        </div>`;
                    }
                } else if (discoveryPipeline.action === 'update') {
                    discoveryBadge = '<span class="ml-2 px-2 py-0.5 text-xs bg-blue-600 text-white rounded">UPDATING DISCOVERY PIPELINE</span>';

                    // Compute diff for discovery pipeline
                    const discoveryLineDiff = computeLineDiff(discoveryCurrentLines, discoveryNewLines);

                    for (const change of discoveryLineDiff) {
                        if (change.type === 'equal') {
                            for (let i = 0; i < change.lines.length; i++) {
                                const line = escapeHtml(change.lines[i]);
                                discoveryCurrentHtml += `<div class="flex hover:bg-gray-700/30">
                                    <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${discoveryCurrentLineNum++}</span>
                                    <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                                </div>`;
                                discoveryNewHtml += `<div class="flex hover:bg-gray-700/30">
                                    <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${discoveryNewLineNum++}</span>
                                    <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                                </div>`;
                            }
                        } else if (change.type === 'delete') {
                            for (let i = 0; i < change.lines.length; i++) {
                                const line = escapeHtml(change.lines[i]);
                                discoveryCurrentHtml += `<div class="flex bg-red-900/20 hover:bg-red-900/30">
                                    <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${discoveryCurrentLineNum++}</span>
                                    <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                                </div>`;
                                discoveryNewHtml += `<div class="flex bg-gray-800/50">
                                    <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                                    <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                                </div>`;
                            }
                        } else if (change.type === 'insert') {
                            for (let i = 0; i < change.lines.length; i++) {
                                const line = escapeHtml(change.lines[i]);
                                discoveryCurrentHtml += `<div class="flex bg-gray-800/50">
                                    <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                                    <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                                </div>`;
                                discoveryNewHtml += `<div class="flex bg-green-900/20 hover:bg-green-900/30">
                                    <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${discoveryNewLineNum++}</span>
                                    <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                                </div>`;
                            }
                        } else if (change.type === 'replace') {
                            const maxLen = Math.max(change.oldLines.length, change.newLines.length);
                            for (let i = 0; i < maxLen; i++) {
                                if (i < change.oldLines.length) {
                                    const oldLine = escapeHtml(change.oldLines[i]);
                                    discoveryCurrentHtml += `<div class="flex bg-red-900/20 hover:bg-red-900/30">
                                        <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${discoveryCurrentLineNum++}</span>
                                        <span style="white-space: pre; padding-left: 0.5rem;">${oldLine || ' '}</span>
                                    </div>`;
                                } else {
                                    discoveryCurrentHtml += `<div class="flex bg-gray-800/50">
                                        <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                                        <span style="white-space: pre; padding-left: 0.5rem;"></span>
                                    </div>`;
                                }
                                if (i < change.newLines.length) {
                                    const newLine = escapeHtml(change.newLines[i]);
                                    discoveryNewHtml += `<div class="flex bg-green-900/20 hover:bg-green-900/30">
                                        <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${discoveryNewLineNum++}</span>
                                        <span style="white-space: pre; padding-left: 0.5rem;">${newLine || ' '}</span>
                                    </div>`;
                                } else {
                                    discoveryNewHtml += `<div class="flex bg-gray-800/50">
                                        <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                                        <span style="white-space: pre; padding-left: 0.5rem;"></span>
                                    </div>`;
                                }
                            }
                        }
                    }
                }

                // Add discovery pipeline section
                html += `
                    <div class="border border-gray-600 rounded-lg overflow-hidden mt-4">
                        <div class="bg-gray-700 px-4 py-2 border-b border-gray-600">
                            <h4 class="text-white font-semibold">
                                ${escapeHtml(network.network_name)} - Discovery Pipeline${discoveryBadge}
                            </h4>
                            <p class="text-sm text-gray-400">Pipeline: ${escapeHtml(discoveryPipeline.pipeline_name)}</p>
                        </div>
                        <div style="display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 0; height: 400px;">
                            <div class="p-4 bg-gray-700 border-r border-gray-600" style="display: flex; flex-direction: column; height: 100%; min-height: 0; min-width: 0;">
                                <div class="mb-2" style="flex-shrink: 0;">
                                    <h5 class="text-sm font-semibold text-white">${discoveryPipeline.action === 'create' ? 'No Existing Discovery Pipeline' : 'Current Discovery Pipeline'}</h5>
                                </div>
                                <div class="bg-gray-800 rounded border border-gray-600 network-diff-scroll-panel" style="flex: 1; overflow-y: auto; overflow-x: auto; min-height: 0; min-width: 0;">
                                    <div class="p-2 text-sm text-gray-300 font-mono">${discoveryCurrentHtml}</div>
                                </div>
                            </div>
                            <div class="p-4 bg-gray-700" style="display: flex; flex-direction: column; height: 100%; min-height: 0; min-width: 0;">
                                <div class="mb-2" style="flex-shrink: 0;">
                                    <h5 class="text-sm font-semibold text-white">${discoveryPipeline.action === 'delete' ? 'Pipeline Will Be Deleted' : 'New Discovery Pipeline (After Commit)'}</h5>
                                </div>
                                <div class="bg-gray-800 rounded border border-gray-600 network-diff-scroll-panel" style="flex: 1; overflow-y: auto; overflow-x: auto; min-height: 0; min-width: 0;">
                                    <div class="p-2 text-sm text-gray-300 font-mono">${discoveryNewHtml}</div>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            }
        }
    }

    // If no networks have changes, show a message
    if (networksWithChanges === 0 && newPipelinesCount === 0 && deletedPipelinesCount === 0) {
        container.innerHTML = `
            <div class="text-center p-8">
                <div class="inline-flex items-center justify-center w-16 h-16 bg-green-600/20 rounded-full mb-4">
                    <svg class="w-8 h-8 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                    </svg>
                </div>
                <h3 class="text-xl font-semibold text-white mb-2">No Changes Detected</h3>
                <p class="text-gray-400">All network pipelines are up to date. No changes need to be committed.</p>
            </div>
        `;

        // Disable the commit button since there's nothing to commit
        const commitButton = document.getElementById('confirmCommitButton');
        if (commitButton) {
            commitButton.disabled = true;
            commitButton.classList.add('opacity-50', 'cursor-not-allowed');
        }
        return;
    }

    // Add stats at the top
    let statsHtml = '<div class="mb-4 p-4 bg-gray-700 rounded-lg border border-gray-600">';
    statsHtml += '<h3 class="text-white font-semibold mb-2">Changes Summary</h3>';
    statsHtml += '<div class="flex gap-4 text-sm">';

    if (newPipelinesCount > 0) {
        statsHtml += `<div class="flex items-center gap-2">
            <span class="px-2 py-0.5 text-xs bg-green-600 text-white rounded">NEW</span>
            <span class="text-gray-300">${newPipelinesCount} new pipeline${newPipelinesCount !== 1 ? 's' : ''}</span>
        </div>`;
    }

    if (networksWithChanges > 0) {
        statsHtml += `<div class="flex items-center gap-2">
            <span class="px-2 py-0.5 text-xs bg-blue-600 text-white rounded">MODIFIED</span>
            <span class="text-gray-300">${networksWithChanges} modified pipeline${networksWithChanges !== 1 ? 's' : ''}</span>
        </div>`;
    }

    if (deletedPipelinesCount > 0) {
        statsHtml += `<div class="flex items-center gap-2">
            <span class="px-2 py-0.5 text-xs bg-red-600 text-white rounded">DELETED</span>
            <span class="text-gray-300">${deletedPipelinesCount} deleted pipeline${deletedPipelinesCount !== 1 ? 's' : ''}</span>
        </div>`;
    }

    statsHtml += '</div></div>';

    container.innerHTML = statsHtml + html;

    // Synchronize scrolling for each network's diff panels
    const allSections = container.querySelectorAll('.border.border-gray-600');
    allSections.forEach(section => {
        const panels = section.querySelectorAll('.network-diff-scroll-panel');
        const leftPanel = panels[0];
        const rightPanel = panels[1];

        if (leftPanel && rightPanel) {
            let isScrolling = false;

            leftPanel.addEventListener('scroll', () => {
                if (!isScrolling) {
                    isScrolling = true;
                    rightPanel.scrollTop = leftPanel.scrollTop;
                    rightPanel.scrollLeft = leftPanel.scrollLeft;
                    setTimeout(() => {
                        isScrolling = false;
                    }, 10);
                }
            });

            rightPanel.addEventListener('scroll', () => {
                if (!isScrolling) {
                    isScrolling = true;
                    leftPanel.scrollTop = rightPanel.scrollTop;
                    leftPanel.scrollLeft = rightPanel.scrollLeft;
                    setTimeout(() => {
                        isScrolling = false;
                    }, 10);
                }
            });
        }
    });
}

/**
 * Confirm and commit the SNMP configuration
 */
async function confirmCommitConfiguration() {
    const confirmButton = document.getElementById('confirmCommitButton');
    const originalText = confirmButton.textContent;

    // Disable button and show loading state
    confirmButton.disabled = true;
    confirmButton.textContent = 'Committing...';
    confirmButton.classList.add('opacity-50', 'cursor-not-allowed');

    try {
        const response = await fetch('/API/SNMP/CommitConfiguration/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Failed to commit configuration: ${response.status} - ${errorText}`);
        }

        const result = await response.json();
        console.log('Commit response:', result);

        if (result.success) {
            // Show success toast
            let message = result.message || 'Configuration committed successfully!';
            showToast(message, 'success');

            // Show warnings as separate toasts if any
            if (result.errors && result.errors.length > 0) {
                result.errors.forEach(error => {
                    showToast(error, 'warning');
                });
            }

            // Close the modal
            hideSnmpDiffModal();

            // Optionally reload the page to reflect changes
            // window.location.reload();
        } else {
            throw new Error(result.error || 'Unknown error occurred');
        }

    } catch (error) {
        console.error('Error committing configuration:', error);
        showToast('Failed to commit configuration: ' + error.message, 'error');
    } finally {
        // Re-enable button
        confirmButton.disabled = false;
        confirmButton.textContent = originalText;
        confirmButton.classList.remove('opacity-50', 'cursor-not-allowed');
    }
}

/**
 * Toast notification function
 */
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container') || createToastContainer();
    const toast = document.createElement('div');
    const colors = {
        success: 'bg-green-500',
        error: 'bg-red-500',
        info: 'bg-blue-500',
        warning: 'bg-yellow-500'
    };

    toast.className = `${colors[type] || 'bg-gray-800'} text-white px-6 py-3 rounded-lg shadow-lg flex items-center justify-between min-w-[300px]`;
    toast.innerHTML = `
        <span>${escapeHtml(message)}</span>
        <button onclick="this.parentElement.remove()" class="text-white hover:text-gray-200 ml-4">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
        </button>
    `;

    container.appendChild(toast);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}

function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'fixed top-4 right-4 z-50 flex flex-col gap-2';
    document.body.appendChild(container);
    return container;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
