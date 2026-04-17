/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

let currentPolicyDiffData = null;
let sectionsWithChanges = new Set();

// ===== DIFF ALGORITHMS (from diff_modal.js) =====

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

// Escape HTML to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Hide modal
function hideDeployDiffModal() {
    document.getElementById('deployDiffModal').classList.add('hidden');
    const confirmBtn = document.getElementById('confirmDeployBtn');
    confirmBtn.disabled = false;
    confirmBtn.textContent = 'Confirm Deploy';
    confirmBtn.classList.remove('opacity-50', 'cursor-not-allowed');
}

// Show modal
function showDeployDiffModal() {
    document.getElementById('deployDiffModal').classList.remove('hidden');
}

// Setup tab switching
function setupDeployDiffTabs() {
    // Remove any existing event listeners by cloning and replacing
    document.querySelectorAll('.deploy-diff-tab').forEach(tab => {
        const newTab = tab.cloneNode(true);
        tab.parentNode.replaceChild(newTab, tab);
    });
    
    // Add fresh event listeners
    document.querySelectorAll('.deploy-diff-tab').forEach(tab => {
        tab.addEventListener('click', function(e) {
            e.preventDefault();
            const section = this.dataset.section;
            
            console.log('Tab clicked:', section); // Debug log
            
            // Update active tab - matching agent_policies.html behavior
            document.querySelectorAll('.deploy-diff-tab').forEach(t => {
                t.classList.remove('active');
                const span = t.querySelector('span');
                const svg = t.querySelector('svg');
                if (span) {
                    span.classList.remove('text-white', 'font-semibold');
                    span.classList.add('text-gray-500');
                }
                if (svg) {
                    svg.classList.remove('opacity-60');
                    svg.classList.add('opacity-40');
                }
            });
            this.classList.add('active');
            const span = this.querySelector('span');
            const svg = this.querySelector('svg');
            if (span) {
                span.classList.remove('text-gray-500');
                span.classList.add('text-white', 'font-semibold');
            }
            if (svg) {
                svg.classList.remove('opacity-40');
                svg.classList.add('opacity-60');
            }
            
            // Show/hide no changes banner based on whether this section has changes
            const noChangesBanner = document.getElementById('noChangesBanner');
            if (sectionsWithChanges.has(section)) {
                noChangesBanner.classList.add('hidden');
            } else {
                noChangesBanner.classList.remove('hidden');
            }
            
            // Show corresponding diff section
            document.querySelectorAll('.deploy-diff-section').forEach(s => {
                s.classList.add('hidden');
            });
            const targetSection = document.getElementById(`diff-${section}`);
            if (targetSection) {
                targetSection.classList.remove('hidden');
                console.log('Showing section:', section); // Debug log
            } else {
                console.error('Section not found:', `diff-${section}`); // Debug log
            }
        });
    });
}

// Update tab indicators to show which sections have changes
function updateTabChangeIndicators() {
    document.querySelectorAll('.deploy-diff-tab').forEach(tab => {
        const section = tab.dataset.section;
        if (sectionsWithChanges.has(section)) {
            tab.classList.add('has-changes');
        } else {
            tab.classList.remove('has-changes');
        }
    });
}

// Check if text content has changes
function hasTextChanges(oldText, newText) {
    return oldText !== newText;
}

// Render side-by-side text diff
function renderSideBySideTextDiff(containerId, oldText, newText) {
    const container = document.getElementById(containerId);
    const oldLines = oldText.split('\n');
    const newLines = newText.split('\n');
    
    // Track if this section has changes
    const sectionName = containerId.replace('diff-', '');
    if (hasTextChanges(oldText, newText)) {
        sectionsWithChanges.add(sectionName);
    }
    
    // Use LCS-based diff algorithm
    const lineDiff = computeLineDiff(oldLines, newLines);
    
    let oldHtml = '';
    let newHtml = '';
    let oldLineNum = 1;
    let newLineNum = 1;
    
    for (const change of lineDiff) {
        if (change.type === 'equal') {
            // Unchanged lines - show on both sides
            for (let i = 0; i < change.lines.length; i++) {
                const line = escapeHtml(change.lines[i]);
                
                oldHtml += `<div class="flex hover:bg-gray-700/30">
                    <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${oldLineNum++}</span>
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
                
                oldHtml += `<div class="flex bg-red-900/20 hover:bg-red-900/30">
                    <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${oldLineNum++}</span>
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
                oldHtml += `<div class="flex bg-gray-800/50">
                    <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                    <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                </div>`;
                
                newHtml += `<div class="flex bg-green-900/20 hover:bg-green-900/30">
                    <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${newLineNum++}</span>
                    <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                </div>`;
            }
        } else if (change.type === 'replace') {
            // Modified lines
            const oldLines = change.oldLines;
            const newLines = change.newLines;
            const maxLen = Math.max(oldLines.length, newLines.length);
            
            for (let i = 0; i < maxLen; i++) {
                if (i < oldLines.length) {
                    const oldLine = escapeHtml(oldLines[i]);
                    oldHtml += `<div class="flex bg-red-900/20 hover:bg-red-900/30">
                        <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${oldLineNum++}</span>
                        <span style="white-space: pre; padding-left: 0.5rem;">${oldLine || ' '}</span>
                    </div>`;
                } else {
                    oldHtml += `<div class="flex bg-gray-800/50">
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
    
    container.innerHTML = `
        <div style="display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 1rem; height: 100%; min-height: 0;">
            <div class="p-4 bg-gray-700 rounded-lg border-l-4 border-yellow-500" style="display: flex; flex-direction: column; height: 100%; min-height: 0; min-width: 0;">
                <div class="mb-2" style="flex-shrink: 0;">
                    <h4 class="text-lg font-semibold text-white">Previous (Version ${currentPolicyDiffData.last_deployed_revision})</h4>
                </div>
                <div class="bg-gray-800 rounded border-2 border-dashed border-gray-600 diff-scroll-panel" style="flex: 1; overflow-y: auto; overflow-x: auto; min-height: 0; min-width: 0;">
                    <div class="p-2 text-sm text-gray-300 font-mono">${oldHtml}</div>
                </div>
            </div>
            <div class="p-4 bg-gray-700 rounded-lg border-l-4 border-green-500" style="display: flex; flex-direction: column; height: 100%; min-height: 0; min-width: 0;">
                <div class="mb-2" style="flex-shrink: 0;">
                    <h4 class="text-lg font-semibold text-white">New (Version ${currentPolicyDiffData.current_revision + 1})</h4>
                </div>
                <div class="bg-gray-800 rounded border-2 border-dashed border-gray-600 diff-scroll-panel" style="flex: 1; overflow-y: auto; overflow-x: auto; min-height: 0; min-width: 0;">
                    <div class="p-2 text-sm text-gray-300 font-mono">${newHtml}</div>
                </div>
            </div>
        </div>
    `;
    
    // Synchronize scrolling between the two panels
    const panels = container.querySelectorAll('.diff-scroll-panel');
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
}

// Render pipelines diff
function renderPipelinesDiff(oldPipelines, newPipelines) {
    const container = document.getElementById('diff-pipelines');
    let cardsHtml = '';
    let hasChanges = false;
    let addedCount = 0;
    let modifiedCount = 0;
    let removedCount = 0;
    let hasWarnings = false; // Track if any pipelines have warnings

    // Create maps for easier comparison
    const oldMap = new Map(oldPipelines.map(p => [p.name, p]));
    const newMap = new Map(newPipelines.map(p => [p.name, p]));

    // Helper: build line-numbered html for a single side of the diff
    function buildDiffHtml(lineDiff, action) {
        let leftHtml = '';
        let rightHtml = '';
        let leftNum = 1;
        let rightNum = 1;

        if (action === 'added') {
            // All lines are new — left is empty placeholders, right is green
            for (const change of lineDiff) {
                const chunk = change.lines || [];
                for (const l of chunk) {
                    const line = escapeHtml(l);
                    leftHtml += `<div class="flex bg-gray-800/50">
                        <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                        <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                    </div>`;
                    rightHtml += `<div class="flex bg-green-900/20 hover:bg-green-900/30">
                        <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${rightNum++}</span>
                        <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                    </div>`;
                }
            }
        } else if (action === 'removed') {
            // All lines are old — left is red, right is empty placeholders
            for (const change of lineDiff) {
                const chunk = change.oldLines || change.lines || [];
                for (const l of chunk) {
                    const line = escapeHtml(l);
                    leftHtml += `<div class="flex bg-red-900/20 hover:bg-red-900/30">
                        <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${leftNum++}</span>
                        <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                    </div>`;
                    rightHtml += `<div class="flex bg-gray-800/50">
                        <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                        <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                    </div>`;
                }
            }
        } else {
            // Modified — standard LCS diff rendering
            for (const change of lineDiff) {
                if (change.type === 'equal') {
                    for (const l of change.lines) {
                        const line = escapeHtml(l);
                        leftHtml += `<div class="flex hover:bg-gray-700/30">
                            <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${leftNum++}</span>
                            <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                        </div>`;
                        rightHtml += `<div class="flex hover:bg-gray-700/30">
                            <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${rightNum++}</span>
                            <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                        </div>`;
                    }
                } else if (change.type === 'delete') {
                    for (const l of change.lines) {
                        const line = escapeHtml(l);
                        leftHtml += `<div class="flex bg-red-900/20 hover:bg-red-900/30">
                            <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${leftNum++}</span>
                            <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                        </div>`;
                        rightHtml += `<div class="flex bg-gray-800/50">
                            <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                            <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                        </div>`;
                    }
                } else if (change.type === 'insert') {
                    for (const l of change.lines) {
                        const line = escapeHtml(l);
                        leftHtml += `<div class="flex bg-gray-800/50">
                            <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                            <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                        </div>`;
                        rightHtml += `<div class="flex bg-green-900/20 hover:bg-green-900/30">
                            <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${rightNum++}</span>
                            <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                        </div>`;
                    }
                } else if (change.type === 'replace') {
                    const maxLen = Math.max(change.oldLines.length, change.newLines.length);
                    for (let i = 0; i < maxLen; i++) {
                        if (i < change.oldLines.length) {
                            const line = escapeHtml(change.oldLines[i]);
                            leftHtml += `<div class="flex bg-red-900/20 hover:bg-red-900/30">
                                <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${leftNum++}</span>
                                <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                            </div>`;
                        } else {
                            leftHtml += `<div class="flex bg-gray-800/50">
                                <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                                <span style="white-space: pre; padding-left: 0.5rem;"></span>
                            </div>`;
                        }
                        if (i < change.newLines.length) {
                            const line = escapeHtml(change.newLines[i]);
                            rightHtml += `<div class="flex bg-green-900/20 hover:bg-green-900/30">
                                <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${rightNum++}</span>
                                <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                            </div>`;
                        } else {
                            rightHtml += `<div class="flex bg-gray-800/50">
                                <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                                <span style="white-space: pre; padding-left: 0.5rem;"></span>
                            </div>`;
                        }
                    }
                }
            }
        }

        return { leftHtml, rightHtml };
    }

    // Helper: build a pipeline card
    function buildPipelineCard(name, description, action, leftHtml, rightHtml, pipelineData) {
        const badge = action === 'added'
            ? '<span class="ml-2 px-2 py-0.5 text-xs bg-green-600 text-white rounded">NEW</span>'
            : action === 'removed'
                ? '<span class="ml-2 px-2 py-0.5 text-xs bg-red-600 text-white rounded">DELETED</span>'
                : '<span class="ml-2 px-2 py-0.5 text-xs bg-blue-600 text-white rounded">MODIFIED</span>';

        const leftTitle = action === 'added' ? 'No Existing Pipeline' : 'Current Pipeline';
        const rightTitle = action === 'removed' ? 'Pipeline Will Be Deleted' : 'New Pipeline (After Deploy)';

        // Build warning banners for no_input and non_reloadable flags
        let warningBannersHtml = '';
        if (pipelineData && action !== 'removed') {
            if (pipelineData.no_input) {
                hasWarnings = true;
                warningBannersHtml += `
                    <div class="pipeline-warning-banner no-input">
                        <svg class="w-5 h-5 text-blue-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <div class="flex-1">
                            <span class="text-sm text-blue-300 font-semibold">Pipeline found with no input.</span>
                            <p class="text-xs text-blue-200 mt-1">This will be deployed, but skipped until it has an input.</p>
                        </div>
                    </div>
                `;
            }
            if (pipelineData.non_reloadable) {
                hasWarnings = true;
                warningBannersHtml += `
                    <div class="pipeline-warning-banner non-reloadable">
                        <svg class="w-5 h-5 text-amber-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                        <div class="flex-1">
                            <span class="text-sm text-amber-300 font-semibold">Stdin input found.</span>
                            <p class="text-xs text-amber-200 mt-1">Stdin is non-reloadable. We will re-create the pipeline every time instead of hot reloading it.</p>
                        </div>
                    </div>
                `;
            }
        }

        return `
            <div class="pipeline-diff-card border border-gray-600 rounded-lg overflow-hidden mb-4">
                <div class="bg-gray-700 px-4 py-2 border-b border-gray-600">
                    <h4 class="text-white font-semibold">${escapeHtml(name)}${badge}</h4>
                    <p class="text-sm text-gray-400">Description: ${escapeHtml(description || 'N/A')}</p>
                </div>
                ${warningBannersHtml ? `<div class="px-4 pt-3">${warningBannersHtml}</div>` : ''}
                <div style="display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 0; height: 400px;">
                    <div class="p-4 bg-gray-700 border-r border-gray-600" style="display: flex; flex-direction: column; height: 100%; min-height: 0; min-width: 0;">
                        <div class="mb-2" style="flex-shrink: 0;">
                            <h5 class="text-sm font-semibold text-white">${leftTitle}</h5>
                        </div>
                        <div class="bg-gray-800 rounded border border-gray-600 pipeline-diff-scroll-panel" style="flex: 1; overflow-y: auto; overflow-x: auto; min-height: 0; min-width: 0;">
                            <div class="p-2 text-sm text-gray-300 font-mono">${leftHtml}</div>
                        </div>
                    </div>
                    <div class="p-4 bg-gray-700" style="display: flex; flex-direction: column; height: 100%; min-height: 0; min-width: 0;">
                        <div class="mb-2" style="flex-shrink: 0;">
                            <h5 class="text-sm font-semibold text-white">${rightTitle}</h5>
                        </div>
                        <div class="bg-gray-800 rounded border border-gray-600 pipeline-diff-scroll-panel" style="flex: 1; overflow-y: auto; overflow-x: auto; min-height: 0; min-width: 0;">
                            <div class="p-2 text-sm text-gray-300 font-mono">${rightHtml}</div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    // Added pipelines
    newPipelines.forEach(pipeline => {
        if (!oldMap.has(pipeline.name)) {
            hasChanges = true;
            addedCount++;
            const lines = (pipeline.lscl || '').split('\n');
            const lineDiff = [{ type: 'insert', lines }];
            const { leftHtml, rightHtml } = buildDiffHtml(lineDiff, 'added');
            cardsHtml += buildPipelineCard(pipeline.name, pipeline.description, 'added', leftHtml, rightHtml, pipeline);
        }
    });

    // Removed pipelines
    oldPipelines.forEach(pipeline => {
        if (!newMap.has(pipeline.name)) {
            hasChanges = true;
            removedCount++;
            const lines = (pipeline.lscl || '').split('\n');
            const lineDiff = [{ type: 'delete', lines }];
            const { leftHtml, rightHtml } = buildDiffHtml(lineDiff, 'removed');
            cardsHtml += buildPipelineCard(pipeline.name, pipeline.description, 'removed', leftHtml, rightHtml, null);
        }
    });

    // Modified pipelines
    newPipelines.forEach(newPipeline => {
        const oldPipeline = oldMap.get(newPipeline.name);
        if (oldPipeline && oldPipeline.lscl !== newPipeline.lscl) {
            hasChanges = true;
            modifiedCount++;
            const oldLines = (oldPipeline.lscl || '').split('\n');
            const newLines = (newPipeline.lscl || '').split('\n');
            const lineDiff = computeLineDiff(oldLines, newLines);
            const { leftHtml, rightHtml } = buildDiffHtml(lineDiff, 'modified');
            cardsHtml += buildPipelineCard(newPipeline.name, newPipeline.description, 'modified', leftHtml, rightHtml, newPipeline);
        }
    });

    if (!hasChanges) {
        container.innerHTML = '<div class="text-gray-400 text-center py-8">No pipeline changes</div>';
        return;
    }

    // Build changes summary
    let summaryHtml = '<div class="mb-4 p-4 bg-gray-700 rounded-lg border border-gray-600">';
    summaryHtml += '<h3 class="text-white font-semibold mb-2">Changes Summary</h3>';
    summaryHtml += '<div class="flex gap-4 text-sm">';
    if (addedCount > 0) {
        summaryHtml += `<div class="flex items-center gap-2">
            <span class="px-2 py-0.5 text-xs bg-green-600 text-white rounded">NEW</span>
            <span class="text-gray-300">${addedCount} new pipeline${addedCount !== 1 ? 's' : ''}</span>
        </div>`;
    }
    if (modifiedCount > 0) {
        summaryHtml += `<div class="flex items-center gap-2">
            <span class="px-2 py-0.5 text-xs bg-blue-600 text-white rounded">MODIFIED</span>
            <span class="text-gray-300">${modifiedCount} modified pipeline${modifiedCount !== 1 ? 's' : ''}</span>
        </div>`;
    }
    if (removedCount > 0) {
        summaryHtml += `<div class="flex items-center gap-2">
            <span class="px-2 py-0.5 text-xs bg-red-600 text-white rounded">DELETED</span>
            <span class="text-gray-300">${removedCount} deleted pipeline${removedCount !== 1 ? 's' : ''}</span>
        </div>`;
    }
    summaryHtml += '</div></div>';

    container.innerHTML = summaryHtml + cardsHtml;

    // Synchronize scrolling for each pipeline card
    container.querySelectorAll('.pipeline-diff-card').forEach(card => {
        const panels = card.querySelectorAll('.pipeline-diff-scroll-panel');
        const leftPanel = panels[0];
        const rightPanel = panels[1];
        if (leftPanel && rightPanel) {
            let isScrolling = false;
            leftPanel.addEventListener('scroll', () => {
                if (!isScrolling) {
                    isScrolling = true;
                    rightPanel.scrollTop = leftPanel.scrollTop;
                    rightPanel.scrollLeft = leftPanel.scrollLeft;
                    setTimeout(() => { isScrolling = false; }, 10);
                }
            });
            rightPanel.addEventListener('scroll', () => {
                if (!isScrolling) {
                    isScrolling = true;
                    leftPanel.scrollTop = rightPanel.scrollTop;
                    leftPanel.scrollLeft = rightPanel.scrollLeft;
                    setTimeout(() => { isScrolling = false; }, 10);
                }
            });
        }
    });

    // Track if this section has changes
    sectionsWithChanges.add('pipelines');
    
    // Add warning indicator to pipelines tab if any pipeline has warnings
    if (hasWarnings) {
        const pipelinesTab = document.querySelector('.deploy-diff-tab[data-section="pipelines"]');
        if (pipelinesTab) {
            pipelinesTab.classList.add('has-warnings');
        }
    }
}

// Render keystore diff
function renderKeystoreDiff(oldKeystore, newKeystore, oldPasswordHash, newPasswordHash) {
    const container = document.getElementById('diff-keystore');
    let html = '';
    let hasChanges = false;
    
    // Check for keystore password change
    if (oldPasswordHash !== newPasswordHash) {
        hasChanges = true;
        html += `
            <div class="mb-2 p-2 bg-amber-900/20 border-l-4 border-amber-600">
                <span class="text-amber-400 font-semibold">⚠ Keystore Password Changed</span>
                <span class="text-gray-400 ml-2">(password updated)</span>
            </div>
        `;
    }
    
    // Create maps for easier comparison
    const oldMap = new Map(oldKeystore.map(k => [k.key_name, k]));
    const newMap = new Map(newKeystore.map(k => [k.key_name, k]));
    
    // Find added keys
    newKeystore.forEach(key => {
        if (!oldMap.has(key.key_name)) {
            hasChanges = true;
            html += `
                <div class="mb-2 p-2 bg-green-900/20 border-l-4 border-green-600">
                    <span class="text-green-400 font-semibold">+ Added Key:</span>
                    <span class="text-gray-300 ml-2">${escapeHtml(key.key_name)}</span>
                    <span class="text-gray-500 ml-2">(value encrypted)</span>
                </div>
            `;
        }
    });
    
    // Find removed keys
    oldKeystore.forEach(key => {
        if (!newMap.has(key.key_name)) {
            hasChanges = true;
            html += `
                <div class="mb-2 p-2 bg-red-900/20 border-l-4 border-red-600">
                    <span class="text-red-400 font-semibold">- Removed Key:</span>
                    <span class="text-gray-300 ml-2">${escapeHtml(key.key_name)}</span>
                </div>
            `;
        }
    });
    
    // Find modified keys (value changed)
    newKeystore.forEach(newKey => {
        const oldKey = oldMap.get(newKey.key_name);
        if (oldKey && oldKey.key_value !== newKey.key_value) {
            hasChanges = true;
            html += `
                <div class="mb-2 p-2 bg-blue-900/20 border-l-4 border-blue-600">
                    <span class="text-blue-400 font-semibold">~ Modified Key:</span>
                    <span class="text-gray-300 ml-2">${escapeHtml(newKey.key_name)}</span>
                    <span class="text-gray-500 ml-2">(value changed)</span>
                </div>
            `;
        }
    });
    
    if (html === '') {
        html = '<div class="text-gray-400 text-center py-8">No keystore changes</div>';
    }
    
    // Track if this section has changes
    if (hasChanges) {
        sectionsWithChanges.add('keystore');
    }
    
    container.innerHTML = html;
}

// Show restart warning with agent count
async function showRestartWarning(policyId) {
    try {
        // Fetch the count of agents using this policy
        const response = await fetch(`/ConnectionManager/GetPolicyAgentCount/?policy_id=${policyId}`, {
            method: 'GET',
            headers: {
                'X-CSRFToken': getCsrfToken()
            }
        });
        
        const data = await response.json();
        
        if (data.success) {
            const agentCount = data.agent_count || 0;
            document.getElementById('agentCount').textContent = agentCount;
            document.getElementById('restartWarningBanner').classList.remove('hidden');
        } else {
            console.error('Failed to get agent count:', data.error);
            // Still show the warning but with 0 count
            document.getElementById('agentCount').textContent = '0';
            document.getElementById('restartWarningBanner').classList.remove('hidden');
        }
    } catch (error) {
        console.error('Error fetching agent count:', error);
        // Still show the warning but with 0 count
        document.getElementById('agentCount').textContent = '0';
        document.getElementById('restartWarningBanner').classList.remove('hidden');
    }
}

// Render global settings diff (settings_path, logs_path, binary_path)
function renderGlobalSettingsDiff(previousData, currentData) {
    const container = document.getElementById('diff-global_settings');
    let html = '<div class="p-4">';
    let hasChanges = false;

    const prevSettingsPath = previousData.settings_path || '';
    const currSettingsPath = currentData.settings_path || '';
    const prevLogsPath = previousData.logs_path || '';
    const currLogsPath = currentData.logs_path || '';
    const prevBinaryPath = previousData.binary_path || '';
    const currBinaryPath = currentData.binary_path || '';
    
    // Settings Path
    html += '<div class="mb-6">';
    html += '<h4 class="text-lg font-semibold text-white mb-3">Logstash Settings Path</h4>';
    if (prevSettingsPath !== currSettingsPath) {
        hasChanges = true;
        html += `
            <div class="grid grid-cols-2 gap-4">
                <div class="p-3 bg-red-900/20 border-l-4 border-red-600 rounded">
                    <div class="text-red-400 text-xs font-semibold mb-1">Previous</div>
                    <div class="text-gray-300 font-mono text-sm">${escapeHtml(prevSettingsPath) || '<em class="text-gray-500">Not set</em>'}</div>
                </div>
                <div class="p-3 bg-green-900/20 border-l-4 border-green-600 rounded">
                    <div class="text-green-400 text-xs font-semibold mb-1">New</div>
                    <div class="text-gray-300 font-mono text-sm">${escapeHtml(currSettingsPath) || '<em class="text-gray-500">Not set</em>'}</div>
                </div>
            </div>
        `;
    } else {
        html += `
            <div class="p-3 bg-gray-700/50 border-l-4 border-gray-600 rounded">
                <div class="text-gray-400 text-xs font-semibold mb-1">No changes</div>
                <div class="text-gray-300 font-mono text-sm">${escapeHtml(currSettingsPath) || '<em class="text-gray-500">Not set</em>'}</div>
            </div>
        `;
    }
    html += '</div>';
    
    // Logs Path
    html += '<div class="mb-6">';
    html += '<h4 class="text-lg font-semibold text-white mb-3">Logstash Logs Path</h4>';
    if (prevLogsPath !== currLogsPath) {
        hasChanges = true;
        html += `
            <div class="grid grid-cols-2 gap-4">
                <div class="p-3 bg-red-900/20 border-l-4 border-red-600 rounded">
                    <div class="text-red-400 text-xs font-semibold mb-1">Previous</div>
                    <div class="text-gray-300 font-mono text-sm">${escapeHtml(prevLogsPath) || '<em class="text-gray-500">Not set</em>'}</div>
                </div>
                <div class="p-3 bg-green-900/20 border-l-4 border-green-600 rounded">
                    <div class="text-green-400 text-xs font-semibold mb-1">New</div>
                    <div class="text-gray-300 font-mono text-sm">${escapeHtml(currLogsPath) || '<em class="text-gray-500">Not set</em>'}</div>
                </div>
            </div>
        `;
    } else {
        html += `
            <div class="p-3 bg-gray-700/50 border-l-4 border-gray-600 rounded">
                <div class="text-gray-400 text-xs font-semibold mb-1">No changes</div>
                <div class="text-gray-300 font-mono text-sm">${escapeHtml(currLogsPath) || '<em class="text-gray-500">Not set</em>'}</div>
            </div>
        `;
    }
    html += '</div>';

    // Binary Path
    html += '<div class="mb-6">';
    html += '<h4 class="text-lg font-semibold text-white mb-3">Logstash Binary Path</h4>';
    if (prevBinaryPath !== currBinaryPath) {
        hasChanges = true;
        html += `
            <div class="grid grid-cols-2 gap-4">
                <div class="p-3 bg-red-900/20 border-l-4 border-red-600 rounded">
                    <div class="text-red-400 text-xs font-semibold mb-1">Previous</div>
                    <div class="text-gray-300 font-mono text-sm">${escapeHtml(prevBinaryPath) || '<em class="text-gray-500">Not set</em>'}</div>
                </div>
                <div class="p-3 bg-green-900/20 border-l-4 border-green-600 rounded">
                    <div class="text-green-400 text-xs font-semibold mb-1">New</div>
                    <div class="text-gray-300 font-mono text-sm">${escapeHtml(currBinaryPath) || '<em class="text-gray-500">Not set</em>'}</div>
                </div>
            </div>
        `;
    } else {
        html += `
            <div class="p-3 bg-gray-700/50 border-l-4 border-gray-600 rounded">
                <div class="text-gray-400 text-xs font-semibold mb-1">No changes</div>
                <div class="text-gray-300 font-mono text-sm">${escapeHtml(currBinaryPath) || '<em class="text-gray-500">Not set</em>'}</div>
            </div>
        `;
    }
    html += '</div>';

    html += '</div>';

    // Track if this section has changes
    if (hasChanges) {
        sectionsWithChanges.add('global_settings');
    }

    container.innerHTML = html;
}

// Load and display policy diff
async function loadPolicyDiff(policyId, policyName) {
    try {
        // Fetch diff data from server
        const response = await fetch(`/ConnectionManager/GetPolicyDiff/?policy_id=${policyId}`, {
            method: 'GET',
            headers: {
                'X-CSRFToken': getCsrfToken()
            }
        });
        
        const data = await response.json();
        
        if (!data.success) {
            throw new Error(data.error || 'Failed to load policy diff');
        }
        
        // Store diff data globally (including policy_id for deployment)
        currentPolicyDiffData = data;
        currentPolicyDiffData.policy_id = policyId;
        
        // Debug: Log the data structure
        console.log('Policy diff data received:', data);
        console.log('Previous logstash_yml length:', (data.previous.logstash_yml || '').length);
        console.log('Current logstash_yml length:', (data.current.logstash_yml || '').length);
        console.log('Previous log4j2_properties length:', (data.previous.log4j2_properties || '').length);
        console.log('Current log4j2_properties length:', (data.current.log4j2_properties || '').length);
        
        // Reset sections with changes tracking
        sectionsWithChanges.clear();
        
        // Populate modal header
        document.getElementById('deployPolicyName').textContent = data.policy_name;
        document.getElementById('currentRevisionNum').textContent = data.last_deployed_revision;
        document.getElementById('newRevisionNum').textContent = data.current_revision + 1;
        
        // Hide loading, show container
        document.getElementById('deployDiffLoading').classList.add('hidden');
        document.getElementById('deployDiffContainer').classList.remove('hidden');
        
        // Render diffs for each section
        console.log('Rendering logstash.yml diff...');
        renderSideBySideTextDiff('diff-logstash_yml', data.previous.logstash_yml || '', data.current.logstash_yml || '');
        console.log('Rendering jvm.options diff...');
        renderSideBySideTextDiff('diff-jvm_options', data.previous.jvm_options || '', data.current.jvm_options || '');
        console.log('Rendering log4j2.properties diff...');
        renderSideBySideTextDiff('diff-log4j2_properties', data.previous.log4j2_properties || '', data.current.log4j2_properties || '');
        renderPipelinesDiff(data.previous.pipelines || [], data.current.pipelines || []);
        renderKeystoreDiff(data.previous.keystore || [], data.current.keystore || [], data.previous.keystore_password_hash || '', data.current.keystore_password_hash || '');
        renderGlobalSettingsDiff(data.previous, data.current);
        
        // Setup tab switching
        setupDeployDiffTabs();
        
        // Update tab indicators to show which sections have changes
        updateTabChangeIndicators();
        
        // Check if the currently active tab has changes and show/hide banner accordingly
        const activeTab = document.querySelector('.deploy-diff-tab.active');
        const activeSection = activeTab?.dataset.section;
        const noChangesBanner = document.getElementById('noChangesBanner');
        if (activeSection && !sectionsWithChanges.has(activeSection)) {
            noChangesBanner.classList.remove('hidden');
        } else {
            noChangesBanner.classList.add('hidden');
        }
        
        // Check if config files have changed (excluding pipelines)
        const hasConfigChanges = sectionsWithChanges.has('logstash_yml') || 
                                 sectionsWithChanges.has('jvm_options') || 
                                 sectionsWithChanges.has('log4j2_properties') || 
                                 sectionsWithChanges.has('keystore');
        
        // Show restart warning if config files changed
        if (hasConfigChanges) {
            await showRestartWarning(policyId);
        } else {
            document.getElementById('restartWarningBanner').classList.add('hidden');
        }
        
        // Calculate and display stats
        const oldLines = (data.previous.logstash_yml || '').split('\n').length;
        const newLines = (data.current.logstash_yml || '').split('\n').length;
        document.getElementById('deployDiffStats').textContent = `Logstash.yml: ${oldLines} → ${newLines} lines`;

        // Disable confirm button if there are no pending changes
        const confirmBtn = document.getElementById('confirmDeployBtn');
        if (sectionsWithChanges.size === 0) {
            confirmBtn.disabled = true;
            confirmBtn.classList.add('opacity-50', 'cursor-not-allowed');
        } else {
            confirmBtn.disabled = false;
            confirmBtn.classList.remove('opacity-50', 'cursor-not-allowed');
        }

    } catch (error) {
        console.error('Error loading policy diff:', error);
        document.getElementById('deployDiffLoading').innerHTML = `
            <div class="text-center">
                <p class="text-red-400 mb-4">Failed to load policy diff</p>
                <p class="text-gray-400 text-sm">${error.message}</p>
                <button onclick="hideDeployDiffModal()" class="mt-4 px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600">
                    Close
                </button>
            </div>
        `;
    }
}

// Confirm deploy
async function confirmDeployPolicy() {
    if (!currentPolicyDiffData) {
        console.error('No policy diff data available');
        return;
    }
    
    const confirmBtn = document.getElementById('confirmDeployBtn');
    const originalText = confirmBtn.textContent;
    
    try {
        // Disable button and show loading state
        confirmBtn.disabled = true;
        confirmBtn.textContent = 'Deploying...';
        confirmBtn.classList.add('opacity-50', 'cursor-not-allowed');
        
        // Call deploy endpoint
        const response = await fetch('/ConnectionManager/DeployPolicy/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                policy_id: currentPolicyDiffData.policy_id
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Show success message
            if (typeof showToast === 'function') {
                showToast(data.message || 'Policy deployed successfully!', 'success');
            } else {
                alert(data.message || 'Policy deployed successfully!');
            }
            
            // Close modal
            hideDeployDiffModal();
            
            // Reload the page or refresh policy data
            if (typeof loadPolicyData === 'function') {
                loadPolicyData();
            } else {
                // Fallback: reload the page
                window.location.reload();
            }
        } else {
            throw new Error(data.error || 'Failed to deploy policy');
        }
        
    } catch (error) {
        console.error('Error deploying policy:', error);
        
        if (typeof showToast === 'function') {
            showToast('Failed to deploy policy: ' + error.message, 'error');
        } else {
            alert('Failed to deploy policy: ' + error.message);
        }
        
        // Re-enable button
        confirmBtn.disabled = false;
        confirmBtn.textContent = originalText;
        confirmBtn.classList.remove('opacity-50', 'cursor-not-allowed');
    }
}

// Get CSRF token from cookie
function getCsrfToken() {
    const name = 'csrftoken';
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
