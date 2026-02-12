let currentDiffMode = 'save'; // 'save' or 'view'
let storedNewPipelineCode = '';
let currentAddIdsState = false;
let quoteValidationWarnings = [];

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
                changes.push({type: 'equal', lines: equalLines});
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
                changes.push({type: 'replace', oldLines: deletedLines, newLines: insertedLines});
            } else if (deletedLines.length > 0) {
                changes.push({type: 'delete', lines: deletedLines});
            } else if (insertedLines.length > 0) {
                changes.push({type: 'insert', lines: insertedLines});
            }
        }
    }

    return changes;
}

/**
 * Compute character-level inline diff for two strings
 */
function computeInlineDiff(oldStr, newStr) {
    const oldChars = oldStr.split('');
    const newChars = newStr.split('');
    const lcs = computeLCS(oldChars, newChars);

    const changes = [];
    let i = 0, j = 0, k = 0;

    while (i < oldChars.length || j < newChars.length) {
        if (k < lcs.length && i < oldChars.length && j < newChars.length &&
            oldChars[i] === lcs[k] && newChars[j] === lcs[k]) {
            // Equal character
            const equalChars = [];
            while (k < lcs.length && i < oldChars.length && j < newChars.length &&
                oldChars[i] === lcs[k] && newChars[j] === lcs[k]) {
                equalChars.push(oldChars[i]);
                i++;
                j++;
                k++;
            }
            if (equalChars.length > 0) {
                changes.push({type: 'equal', text: equalChars.join('')});
            }
        } else {
            const deletedChars = [];
            const insertedChars = [];

            while (i < oldChars.length && (k >= lcs.length || oldChars[i] !== lcs[k])) {
                deletedChars.push(oldChars[i]);
                i++;
            }

            while (j < newChars.length && (k >= lcs.length || newChars[j] !== lcs[k])) {
                insertedChars.push(newChars[j]);
                j++;
            }

            if (deletedChars.length > 0) {
                changes.push({type: 'delete', text: deletedChars.join('')});
            }
            if (insertedChars.length > 0) {
                changes.push({type: 'insert', text: insertedChars.join('')});
            }
        }
    }

    return changes;
}

/**
 * Render inline diff with highlighting for a specific side
 */
function renderInlineDiff(changes, side) {
    const escapeHtml = (text) => {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    };

    let html = '';
    for (const change of changes) {
        if (change.type === 'equal') {
            html += escapeHtml(change.text);
        } else if (change.type === 'delete' && side === 'old') {
            html += `<span class="bg-red-500/50 font-bold">${escapeHtml(change.text)}</span>`;
        } else if (change.type === 'insert' && side === 'new') {
            html += `<span class="bg-green-500/50 font-bold">${escapeHtml(change.text)}</span>`;
        }
        // Don't render delete on new side or insert on old side
    }
    return html || ' ';
}

// ===== END DIFF ALGORITHMS =====

// ===== QUOTE VALIDATION =====

/**
 * Validate components for fields that mix single and double quotes
 * Returns array of warnings with plugin info and problematic fields
 */
function validateQuoteMixing(components) {
    const warnings = [];
    
    function checkValue(value, path) {
        if (typeof value === 'string') {
            // Check if string contains both single and double quotes
            if (value.includes('"') && value.includes("'")) {
                return {
                    path: path,
                    value: value,
                    preview: value.length > 50 ? value.substring(0, 50) + '...' : value
                };
            }
        }
        return null;
    }
    
    function scanObject(obj, basePath) {
        const issues = [];
        
        if (typeof obj !== 'object' || obj === null) {
            return issues;
        }
        
        for (const [key, value] of Object.entries(obj)) {
            const currentPath = basePath ? `${basePath}.${key}` : key;
            
            if (typeof value === 'string') {
                const issue = checkValue(value, currentPath);
                if (issue) {
                    issues.push(issue);
                }
            } else if (typeof value === 'object' && value !== null) {
                issues.push(...scanObject(value, currentPath));
            }
        }
        
        return issues;
    }
    
    // Scan all sections
    for (const section of ['input', 'filter', 'output']) {
        if (!components[section]) continue;
        
        for (let i = 0; i < components[section].length; i++) {
            const component = components[section][i];
            const pluginName = component.plugin || 'unknown';
            const pluginId = component.id || `${section}_${i}`;
            
            // Scan the config object for quote mixing
            const issues = scanObject(component.config, 'config');
            
            if (issues.length > 0) {
                warnings.push({
                    section: section,
                    plugin: pluginName,
                    id: pluginId,
                    issues: issues
                });
            }
        }
    }
    
    return warnings;
}

/**
 * Display quote validation warnings in the modal
 */
function displayQuoteWarnings(warnings) {
    const warningContainer = document.getElementById('quoteWarningContainer');
    
    if (warnings.length === 0) {
        warningContainer.classList.add('hidden');
        return;
    }
    
    const escapeHtml = (text) => {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    };
    
    let warningHtml = `
        <div class="bg-yellow-900/30 border-l-4 border-yellow-500 p-4 rounded">
            <div class="flex items-start">
                <svg class="w-6 h-6 text-yellow-500 mr-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
                </svg>
                <div class="flex-1">
                    <h4 class="text-yellow-400 font-semibold mb-2">Quote Mixing Warning</h4>
                    <p class="text-yellow-200 text-sm mb-3">
                        The following fields contain both single (') and double (") quotes. Logstash cannot properly escape these values, which may cause parsing errors.
                    </p>
                    <div class="space-y-3">
    `;
    
    for (const warning of warnings) {
        warningHtml += `
            <div class="bg-gray-800/50 p-3 rounded text-sm">
                <div class="text-white font-medium mb-1">
                    ${escapeHtml(warning.section)} → ${escapeHtml(warning.plugin)} <span class="text-gray-400">(${escapeHtml(warning.id)})</span>
                </div>
        `;
        
        for (const issue of warning.issues) {
            warningHtml += `
                <div class="ml-4 mt-2 text-gray-300">
                    <span class="text-yellow-400">Field:</span> <code class="bg-gray-900 px-2 py-0.5 rounded">${escapeHtml(issue.path)}</code><br>
                    <span class="text-yellow-400">Preview:</span> <code class="bg-gray-900 px-2 py-0.5 rounded text-xs">${escapeHtml(issue.preview)}</code>
                </div>
            `;
        }
        
        warningHtml += `</div>`;
    }
    
    warningHtml += `
                    </div>
                    <p class="text-yellow-200 text-sm mt-3">
                        <strong>Recommendation:</strong> Modify these fields to use only single quotes or only double quotes.
                    </p>
                </div>
            </div>
        </div>
    `;
    
    warningContainer.innerHTML = warningHtml;
    warningContainer.classList.remove('hidden');
}

// ===== END QUOTE VALIDATION =====

function hideDiffModal() {
    document.getElementById('diffModal').classList.add('hidden');
}

function showDiffModal() {
    document.getElementById('diffModal').classList.remove('hidden');
}

// Function to view generated code (no comparison)
async function viewGeneratedCode() {
    currentDiffMode = 'view';

    // Update UI for view mode
    document.getElementById('diffModalTitle').textContent = 'Generated Pipeline Code';
    document.getElementById('diffDescription').innerHTML = `
        <div class="flex items-center gap-2">
            <p class="text-gray-300 text-sm">View the generated Logstash configuration below.</p>
            <div class="relative group inline-block">
                <div class="p-1 rounded-full hover:bg-gray-700 transition-colors">
                    <svg class="w-4 h-4 text-gray-400 hover:text-blue-400 cursor-help transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                </div>
                <div class="hidden group-hover:block absolute z-50 w-96 p-4 mt-2 left-1/2 transform -translate-x-1/2 bg-gray-900 border border-gray-600 rounded-lg shadow-xl text-sm text-gray-300">
                    <p class="font-semibold text-white mb-2">How this works:</p>
                    <ul class="list-disc pl-5 space-y-1.5">
                        <li>If you are using spaces, it will be converted into tabs.</li>
                        <li>As of right now, comments are removed.</li>
                        <li>Space is added in the editor to generally keep changes close together.</li>
                    </ul>
                </div>
            </div>
        </div>
    `;
    document.getElementById('confirmSaveButton').classList.add('hidden');
    document.getElementById('copyCodeButton').classList.remove('hidden');
    document.getElementById('addIdsContainer').classList.add('hidden');

    // Show the modal first
    showDiffModal();

    // Show loading state
    document.getElementById('diffLoading').classList.remove('hidden');
    document.getElementById('diffContainer').classList.add('hidden');

    try {
        // Generate new pipeline code from current components
        const formData = new FormData();
        formData.append('components', JSON.stringify(components));

        const response = await fetch('/API/GetCurrentPipelineCode/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            },
            body: formData
        });

        if (!response.ok) {
            throw new Error('Failed to generate code');
        }

        const html = await response.text();
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = html;
        const code = tempDiv.querySelector('code').textContent;

        storedNewPipelineCode = code;

        // Hide loading, show container
        document.getElementById('diffLoading').classList.add('hidden');
        document.getElementById('diffContainer').classList.remove('hidden');

        // Display as single code view
        const diffContainer = document.getElementById('diffContainer');
        const lines = code.split('\n');

        const escapeHtml = (text) => {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        };

        let codeHtml = '';
        for (let i = 0; i < lines.length; i++) {
            const line = escapeHtml(lines[i]);
            codeHtml += `<div class="flex hover:bg-gray-700/30">
        <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${i + 1}</span>
        <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
      </div>`;
        }

        diffContainer.innerHTML = `
      <div class="p-4 bg-gray-700 rounded-lg border-l-4 border-blue-500" style="display: flex; flex-direction: column; height: 100%; min-height: 0;">
        <div class="mb-2" style="flex-shrink: 0;">
          <h4 class="text-lg font-semibold text-white">Generated Logstash Configuration</h4>
        </div>
        <div class="bg-gray-800 rounded border-2 border-dashed border-gray-600" style="flex: 1; overflow-y: auto; overflow-x: auto; min-height: 0;">
          <div class="p-2 text-sm text-gray-300 font-mono">${codeHtml}</div>
        </div>
      </div>
    `;

        // Display stats
        document.getElementById('diffStats').textContent = `Total: ${lines.length} lines`;

    } catch (error) {
        console.error('Error generating code:', error);
        document.getElementById('diffLoading').innerHTML = `
      <div class="text-center">
        <p class="text-red-400 mb-4">Failed to generate code</p>
        <p class="text-gray-400 text-sm">${error.message}</p>
        <button onclick="hideDiffModal()" class="mt-4 px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600">
          Close
        </button>
      </div>
    `;
    }
}

// Function to copy code to clipboard
function copyDiffCodeToClipboard() {
    const copyButton = document.getElementById('copyCodeButton');

    navigator.clipboard.writeText(storedNewPipelineCode).then(() => {
        const originalText = copyButton.textContent;
        copyButton.textContent = 'Copied!';
        copyButton.classList.remove('bg-blue-600', 'hover:bg-blue-700');
        copyButton.classList.add('bg-green-600', 'hover:bg-green-700');

        setTimeout(() => {
            copyButton.textContent = originalText;
            copyButton.classList.remove('bg-green-600', 'hover:bg-green-700');
            copyButton.classList.add('bg-blue-600', 'hover:bg-blue-700');
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy:', err);
        copyButton.textContent = 'Failed!';
        copyButton.classList.add('bg-red-600');
        setTimeout(() => {
            copyButton.textContent = 'Copy to Clipboard';
            copyButton.classList.remove('bg-red-600');
        }, 2000);
    });
}

// Function to handle checkbox change
function handleAddIdsChange() {
    const checkbox = document.getElementById('addIdsCheckbox');
    currentAddIdsState = checkbox.checked;
    
    // Only reload if we're in save mode (diff comparison)
    if (currentDiffMode === 'save') {
        loadDiffContent();
    }
}

// Function to fetch and display the diff
async function prepareDiffModal() {
    currentDiffMode = 'save';

    // Update UI for save mode
    document.getElementById('diffModalTitle').textContent = 'Review Pipeline Changes';
    document.getElementById('diffDescription').innerHTML = `
        <div class="flex items-center gap-2">
            <p class="text-gray-300 text-sm">Review the changes below before saving your pipeline.</p>
            <div class="relative group inline-block">
                <div class="p-1 rounded-full hover:bg-gray-700 transition-colors">
                    <svg class="w-4 h-4 text-gray-400 hover:text-blue-400 cursor-help transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                </div>
                <div class="hidden group-hover:block absolute z-50 w-80 p-4 mt-2 left-0 bg-gray-900 border border-gray-600 rounded-lg shadow-xl text-sm text-gray-300">
                    <p class="font-semibold text-white mb-2">How this works:</p>
                    <ul class="list-disc pl-5 space-y-1.5">
                        <li>If you are using spaces, it will be converted into tabs.</li>
                        <li>As of right now, comments are removed.</li>
                        <li>Space is added in the editor to generally keep changes close together.</li>
                    </ul>
                </div>
            </div>
        </div>
    `;
    document.getElementById('confirmSaveButton').classList.remove('hidden');
    document.getElementById('copyCodeButton').classList.add('hidden');
    document.getElementById('addIdsContainer').classList.remove('hidden');
    
    // Reset checkbox state
    const checkbox = document.getElementById('addIdsCheckbox');
    checkbox.checked = false;
    currentAddIdsState = false;
    
    // Show the modal first
    showDiffModal();

    // Validate for quote mixing
    quoteValidationWarnings = validateQuoteMixing(components);
    displayQuoteWarnings(quoteValidationWarnings);

    // Load the diff content
    await loadDiffContent();
}

// Separate function to load diff content (can be called when checkbox changes)
async function loadDiffContent() {
    // Re-validate and display warnings (in case components changed)
    quoteValidationWarnings = validateQuoteMixing(components);
    displayQuoteWarnings(quoteValidationWarnings);
    
    // Show loading state
    document.getElementById('diffLoading').classList.remove('hidden');
    document.getElementById('diffContainer').classList.add('hidden');

    try {
        // Get the current pipeline from the server
        const esId = new URLSearchParams(window.location.search).get('es_id');
        const pipelineName = new URLSearchParams(window.location.search).get('pipeline');

        console.log('Fetching diff for:', {esId, pipelineName, addIds: currentAddIdsState});

        // Fetch diff from the server
        const formData = new FormData();
        formData.append('es_id', esId);
        formData.append('pipeline', pipelineName);
        formData.append('components', JSON.stringify(components));
        formData.append('add_ids', currentAddIdsState ? 'true' : 'false');

        const diffResponse = await fetch('/API/GetDiff/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            },
            body: formData
        });

        console.log('Diff response status:', diffResponse.status);

        if (!diffResponse.ok) {
            const errorText = await diffResponse.text();
            console.error('Diff response error:', errorText);
            throw new Error(`Failed to fetch diff: ${diffResponse.status} - ${errorText}`);
        }

        const diffData = await diffResponse.json();
        console.log('Diff data received:', diffData);

        // Hide loading, show container
        document.getElementById('diffLoading').classList.add('hidden');
        document.getElementById('diffContainer').classList.remove('hidden');

        // Display the diff using simple side-by-side comparison
        const diffContainer = document.getElementById('diffContainer');

        // Escape HTML to prevent XSS
        const escapeHtml = (text) => {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        };

        // Create side-by-side diff with inline character-level highlighting
        const currentLines = diffData.current.split('\n');
        const newLines = diffData.new.split('\n');

        // Use LCS-based diff algorithm to compute line-by-line changes
        const lineDiff = computeLineDiff(currentLines, newLines);

        let currentHtml = '';
        let newHtml = '';
        let currentLineNum = 1;
        let newLineNum = 1;

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

        diffContainer.innerHTML = `
      <div style="display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 1rem; height: 100%; min-height: 0;">
        <div class="p-4 bg-gray-700 rounded-lg border-l-4 border-yellow-500" style="display: flex; flex-direction: column; height: 100%; min-height: 0; min-width: 0;">
          <div class="mb-2" style="flex-shrink: 0;">
            <h4 class="text-lg font-semibold text-white">Current Pipeline</h4>
          </div>
          <div class="bg-gray-800 rounded border-2 border-dashed border-gray-600 diff-scroll-panel" style="flex: 1; overflow-y: auto; overflow-x: auto; min-height: 0; min-width: 0;">
            <div class="p-2 text-sm text-gray-300 font-mono">${currentHtml}</div>
          </div>
        </div>
        <div class="p-4 bg-gray-700 rounded-lg border-l-4 border-green-500" style="display: flex; flex-direction: column; height: 100%; min-height: 0; min-width: 0;">
          <div class="mb-2" style="flex-shrink: 0;">
            <h4 class="text-lg font-semibold text-white">New Pipeline (After Save)</h4>
          </div>
          <div class="bg-gray-800 rounded border-2 border-dashed border-gray-600 diff-scroll-panel" style="flex: 1; overflow-y: auto; overflow-x: auto; min-height: 0; min-width: 0;">
            <div class="p-2 text-sm text-gray-300 font-mono">${newHtml}</div>
          </div>
        </div>
      </div>
    `;

        // Synchronize scrolling between the two panels
        const panels = diffContainer.querySelectorAll('.diff-scroll-panel');
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

        // Display diff stats
        document.getElementById('diffStats').textContent = diffData.stats;

    } catch (error) {
        console.error('Error preparing diff:', error);
        document.getElementById('diffLoading').innerHTML = `
      <div class="text-center">
        <p class="text-red-400 mb-4">Failed to load pipeline comparison</p>
        <p class="text-gray-400 text-sm">${error.message}</p>
        <button onclick="hideDiffModal()" class="mt-4 px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600">
          Close
        </button>
      </div>
    `;
    }
}

// Function to confirm and save the pipeline
async function confirmSavePipeline() {
    const confirmButton = document.getElementById('confirmSaveButton');
    const originalText = confirmButton.textContent;

    // Disable button and show loading state
    confirmButton.disabled = true;
    confirmButton.textContent = 'Saving...';
    confirmButton.classList.add('opacity-50', 'cursor-not-allowed');

    try {
        const esId = new URLSearchParams(window.location.search).get('es_id');
        const pipelineName = new URLSearchParams(window.location.search).get('pipeline');

        console.log('Saving pipeline:', {esId, pipelineName});

        const formData = new FormData();
        formData.append('save_pipeline', 'true');
        formData.append('es_id', esId);
        formData.append('pipeline', pipelineName);
        formData.append('components', JSON.stringify(components));
        formData.append('add_ids', currentAddIdsState ? 'true' : 'false');

        const saveResponse = await fetch('/API/SavePipeline/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            },
            body: formData
        });

        console.log('Save response status:', saveResponse.status);

        const responseText = await saveResponse.text();
        
        // Check if response contains permission denied (even with 200 status)
        if (responseText.includes('showToast') && responseText.includes('Access denied')) {
            console.log('Permission denied detected');
            // Extract script content and execute it
            const scriptMatch = responseText.match(/<script>([\s\S]*?)<\/script>/);
            if (scriptMatch && scriptMatch[1]) {
                eval(scriptMatch[1]);
            }
            // Close the modal
            hideDiffModal();
            return;
        }
        
        if (!saveResponse.ok) {
            console.error('Save error:', responseText);
            
            // Display the error HTML in the modal
            document.getElementById('diffLoading').classList.add('hidden');
            document.getElementById('diffContainer').innerHTML = responseText;
            document.getElementById('diffContainer').classList.remove('hidden');
            
            // Hide the save button since we can't proceed
            confirmButton.classList.add('hidden');
            
            return; // Don't proceed with success flow
        }

        console.log('Save response:', responseText);

        // Show success message
        document.getElementById('saveStatus').innerHTML = `
      <span class="text-green-400">${responseText}</span>
    `;

        // Close the modal
        hideDiffModal();

        // Clear success message after 3 seconds
        setTimeout(() => {
            document.getElementById('saveStatus').innerHTML = '';
        }, 3000);

    } catch (error) {
        console.error('Error saving pipeline:', error);
        alert('Failed to save pipeline: ' + error.message);
    } finally {
        // Re-enable button (unless it was hidden due to error)
        if (!confirmButton.classList.contains('hidden')) {
            confirmButton.disabled = false;
            confirmButton.textContent = originalText;
            confirmButton.classList.remove('opacity-50', 'cursor-not-allowed');
        }
    }
}
