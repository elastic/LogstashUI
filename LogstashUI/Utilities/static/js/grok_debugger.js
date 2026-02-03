// Grok Debugger JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Get all textarea elements and their line number containers
    const sampleDataInput = document.getElementById('sampleDataInput');
    const sampleDataLineNumbers = document.getElementById('sampleDataLineNumbers');
    const grokPatternInput = document.getElementById('grokPatternInput');
    const grokPatternLineNumbers = document.getElementById('grokPatternLineNumbers');
    const customPatternsInput = document.getElementById('customPatternsInput');
    const customPatternsLineNumbers = document.getElementById('customPatternsLineNumbers');
    const simulateButton = document.getElementById('simulateButton');
    const multilineCheckbox = document.getElementById('multilineCheckbox');

    // Track if we're currently syncing to prevent infinite loops
    let isSyncing = false;

    // Get banner elements
    const multipleInputBanner = document.getElementById('multipleInputBanner');
    const multiplePatternBanner = document.getElementById('multiplePatternBanner');

    // Autocomplete state
    let grokPatterns = {};
    let autocompleteVisible = false;
    let autocompleteDropdown = null;
    let selectedIndex = -1;
    let currentTextarea = null;
    let autocompleteStartPos = -1;

    // Load grok patterns from server
    fetch('/Utilities/GrokDebugger/patterns/')
        .then(response => response.json())
        .then(data => {
            grokPatterns = data.patterns || {};
        })
        .catch(error => console.error('Error loading grok patterns:', error));

    // Function to get custom patterns from the custom patterns textarea
    function getCustomPatterns() {
        const customPatterns = {};
        const lines = customPatternsInput.value.split('\n');
        for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed && trimmed.indexOf(' ') > 0) {
                const parts = trimmed.split(/\s+/, 2);
                if (parts.length === 2) {
                    customPatterns[parts[0]] = parts[1];
                }
            }
        }
        return customPatterns;
    }

    // Function to get all available patterns (grok + custom)
    function getAllPatterns() {
        return { ...grokPatterns, ...getCustomPatterns() };
    }

    // Function to escape HTML
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Function to create autocomplete dropdown
    function createAutocompleteDropdown() {
        if (autocompleteDropdown) {
            autocompleteDropdown.remove();
        }

        autocompleteDropdown = document.createElement('div');
        autocompleteDropdown.className = 'autocomplete-dropdown';
        autocompleteDropdown.style.position = 'absolute';
        autocompleteDropdown.style.zIndex = '1000';
        document.body.appendChild(autocompleteDropdown);

        return autocompleteDropdown;
    }

    // Function to show autocomplete suggestions
    function showAutocomplete(textarea, searchTerm) {
        const allPatterns = getAllPatterns();
        const filtered = Object.keys(allPatterns).filter(name =>
            name.toUpperCase().startsWith(searchTerm.toUpperCase())
        ).sort();

        if (filtered.length === 0) {
            hideAutocomplete();
            return;
        }

        if (!autocompleteDropdown) {
            createAutocompleteDropdown();
        }

        // Position the dropdown
        const rect = textarea.getBoundingClientRect();
        const cursorPos = getCursorCoordinates(textarea);
        autocompleteDropdown.style.left = (rect.left + cursorPos.left) + 'px';
        autocompleteDropdown.style.top = (rect.top + cursorPos.top + 20) + 'px';

        // Build dropdown content
        let html = '<div class="bg-base-200 border border-base-300 rounded-lg shadow-lg max-h-64 overflow-auto">';
        filtered.forEach((name, index) => {
            const isCustom = getCustomPatterns().hasOwnProperty(name);
            const badge = isCustom ? '<span class="badge badge-xs badge-primary ml-2">Custom</span>' : '';
            const escapedName = escapeHtml(name);
            const escapedPattern = escapeHtml(allPatterns[name]);
            html += `
                <div class="autocomplete-item px-3 py-2 cursor-pointer hover:bg-base-300 ${index === selectedIndex ? 'bg-base-300' : ''}" 
                     data-index="${index}" 
                     data-pattern="${escapedName}">
                    <span class="font-mono text-sm font-semibold">${escapedName}</span>${badge}
                    <div class="text-xs text-base-content/60 font-mono truncate" style="max-width: 400px;">${escapedPattern}</div>
                </div>
            `;
        });
        html += '</div>';

        autocompleteDropdown.innerHTML = html;
        autocompleteVisible = true;
        selectedIndex = -1;

        // Add click handlers
        autocompleteDropdown.querySelectorAll('.autocomplete-item').forEach(item => {
            item.addEventListener('click', function() {
                insertPattern(this.dataset.pattern);
            });
        });
    }

    // Function to hide autocomplete
    function hideAutocomplete() {
        if (autocompleteDropdown) {
            autocompleteDropdown.remove();
            autocompleteDropdown = null;
        }
        autocompleteVisible = false;
        selectedIndex = -1;
        autocompleteStartPos = -1;
        currentTextarea = null;
    }

    // Function to get cursor coordinates in textarea
    function getCursorCoordinates(textarea) {
        const position = textarea.selectionStart;
        const div = document.createElement('div');
        const style = window.getComputedStyle(textarea);

        // Copy styles
        ['fontFamily', 'fontSize', 'fontWeight', 'lineHeight', 'padding', 'border'].forEach(prop => {
            div.style[prop] = style[prop];
        });

        div.style.position = 'absolute';
        div.style.visibility = 'hidden';
        div.style.whiteSpace = 'pre-wrap';
        div.style.wordWrap = 'break-word';
        div.style.width = textarea.clientWidth + 'px';

        const textBeforeCursor = textarea.value.substring(0, position);
        div.textContent = textBeforeCursor;

        const span = document.createElement('span');
        span.textContent = '|';
        div.appendChild(span);

        document.body.appendChild(div);
        const coordinates = {
            left: span.offsetLeft,
            top: span.offsetTop
        };
        document.body.removeChild(div);

        return coordinates;
    }

    // Function to insert selected pattern
    function insertPattern(patternName) {
        if (!currentTextarea || autocompleteStartPos === -1) return;

        const value = currentTextarea.value;
        const cursorPos = currentTextarea.selectionStart;

        // Replace from %{ to current cursor position with the pattern name
        const before = value.substring(0, autocompleteStartPos);
        const after = value.substring(cursorPos);
        const newValue = before + patternName + '}' + after;

        currentTextarea.value = newValue;
        const newCursorPos = autocompleteStartPos + patternName.length + 1;
        currentTextarea.setSelectionRange(newCursorPos, newCursorPos);

        // Update line numbers
        if (currentTextarea === grokPatternInput) {
            updateLineNumbers(grokPatternInput, grokPatternLineNumbers);
            updateBanners();
        }

        hideAutocomplete();
        currentTextarea.focus();
    }

    // Function to handle autocomplete navigation
    function navigateAutocomplete(direction) {
        if (!autocompleteVisible) return;

        const items = autocompleteDropdown.querySelectorAll('.autocomplete-item');
        if (items.length === 0) return;

        // Remove current selection
        if (selectedIndex >= 0 && selectedIndex < items.length) {
            items[selectedIndex].classList.remove('bg-base-300');
        }

        // Update index
        if (direction === 'down') {
            selectedIndex = (selectedIndex + 1) % items.length;
        } else if (direction === 'up') {
            selectedIndex = selectedIndex <= 0 ? items.length - 1 : selectedIndex - 1;
        }

        // Add new selection
        items[selectedIndex].classList.add('bg-base-300');
        items[selectedIndex].scrollIntoView({ block: 'nearest' });
    }

    // Function to handle autocomplete on input
    function handleAutocompleteInput(textarea, event) {
        const value = textarea.value;
        const cursorPos = textarea.selectionStart;

        // Check if we just typed %{
        if (value.substring(cursorPos - 2, cursorPos) === '%{') {
            currentTextarea = textarea;
            autocompleteStartPos = cursorPos;
            showAutocomplete(textarea, '');
            return;
        }

        // Check if we're currently in an autocomplete context
        if (autocompleteVisible && currentTextarea === textarea) {
            // Find the %{ before cursor
            let searchStart = cursorPos - 1;
            while (searchStart >= 0 && value[searchStart] !== '{') {
                searchStart--;
            }

            if (searchStart >= 1 && value[searchStart - 1] === '%') {
                const searchTerm = value.substring(searchStart + 1, cursorPos);
                showAutocomplete(textarea, searchTerm);
            } else {
                hideAutocomplete();
            }
        }
    }

    // Function to update banner visibility
    function updateBanners() {
        // Check Sample Data for multiple lines (hide banner if multiline mode is enabled)
        const sampleDataLines = sampleDataInput.value.split('\n').filter(line => line.trim() !== '');
        if (sampleDataLines.length > 1 && !multilineCheckbox.checked) {
            multipleInputBanner.classList.remove('hidden');
        } else {
            multipleInputBanner.classList.add('hidden');
        }

        // Check Grok Pattern for multiple lines
        const grokPatternLines = grokPatternInput.value.split('\n').filter(line => line.trim() !== '');
        if (grokPatternLines.length > 1) {
            multiplePatternBanner.classList.remove('hidden');
        } else {
            multiplePatternBanner.classList.add('hidden');
        }
    }

    // Function to update line numbers for a textarea
    function updateLineNumbers(textarea, lineNumbersContainer) {
        const lines = textarea.value.split('\n');
        const lineCount = lines.length;

        // Create a mirror div to measure actual line heights
        const mirror = document.createElement('div');
        const computedStyle = window.getComputedStyle(textarea);

        // Copy relevant styles from textarea to mirror
        mirror.style.position = 'absolute';
        mirror.style.visibility = 'hidden';
        mirror.style.whiteSpace = 'pre-wrap';
        mirror.style.wordWrap = 'break-word';
        mirror.style.overflowWrap = 'break-word';
        // Calculate width minus padding to match actual text area
        const paddingLeft = parseFloat(computedStyle.paddingLeft) || 0;
        const paddingRight = parseFloat(computedStyle.paddingRight) || 0;
        mirror.style.width = (textarea.clientWidth - paddingLeft - paddingRight) + 'px';
        mirror.style.font = computedStyle.font;
        mirror.style.fontSize = computedStyle.fontSize;
        mirror.style.fontFamily = computedStyle.fontFamily;
        mirror.style.lineHeight = computedStyle.lineHeight;
        mirror.style.padding = '0';
        mirror.style.border = 'none';
        mirror.style.boxSizing = 'content-box';

        document.body.appendChild(mirror);

        // Get single line height
        mirror.textContent = 'X';
        const singleLineHeight = mirror.offsetHeight;

        // Generate line numbers with measured heights for each logical line
        let lineNumbersHTML = '';
        for (let i = 0; i < lineCount; i++) {
            // Set mirror content to this line
            mirror.textContent = lines[i] || ' '; // Use space for empty lines
            const totalLineHeight = mirror.offsetHeight;

            // Create line number that appears at the top of this logical line
            // but takes up the full height so the next line number appears in the right place
            lineNumbersHTML += `<div style="height: ${totalLineHeight}px; line-height: ${singleLineHeight}px;">${i + 1}</div>`;
        }

        // Clean up mirror
        document.body.removeChild(mirror);

        lineNumbersContainer.innerHTML = lineNumbersHTML;

        // Sync scroll position
        lineNumbersContainer.scrollTop = textarea.scrollTop;
    }

    // Function to synchronize scroll between sample data and grok pattern
    function syncScroll(sourceTextarea, targetTextarea, sourceLineNumbers, targetLineNumbers) {
        if (isSyncing) return;

        isSyncing = true;

        // Sync vertical scroll
        targetTextarea.scrollTop = sourceTextarea.scrollTop;
        targetLineNumbers.scrollTop = sourceTextarea.scrollTop;

        // Sync horizontal scroll
        targetTextarea.scrollLeft = sourceTextarea.scrollLeft;

        isSyncing = false;
    }

    // Set up event listener for multiline checkbox
    multilineCheckbox.addEventListener('change', function() {
        updateBanners();
    });

    // Set up event listeners for sample data input
    sampleDataInput.addEventListener('input', function() {
        updateLineNumbers(sampleDataInput, sampleDataLineNumbers);
        updateBanners();
    });

    sampleDataInput.addEventListener('scroll', function() {
        sampleDataLineNumbers.scrollTop = sampleDataInput.scrollTop;
        syncScroll(sampleDataInput, grokPatternInput, sampleDataLineNumbers, grokPatternLineNumbers);
    });

    // Set up event listeners for grok pattern input
    grokPatternInput.addEventListener('input', function(e) {
        updateLineNumbers(grokPatternInput, grokPatternLineNumbers);
        updateBanners();
        handleAutocompleteInput(grokPatternInput, e);
    });

    grokPatternInput.addEventListener('scroll', function() {
        grokPatternLineNumbers.scrollTop = grokPatternInput.scrollTop;
        syncScroll(grokPatternInput, sampleDataInput, grokPatternLineNumbers, sampleDataLineNumbers);
    });

    // Keyboard navigation for autocomplete
    grokPatternInput.addEventListener('keydown', function(e) {
        if (!autocompleteVisible) return;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            navigateAutocomplete('down');
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            navigateAutocomplete('up');
        } else if (e.key === 'Enter' || e.key === 'Tab') {
            if (selectedIndex >= 0) {
                e.preventDefault();
                const items = autocompleteDropdown.querySelectorAll('.autocomplete-item');
                if (items[selectedIndex]) {
                    insertPattern(items[selectedIndex].dataset.pattern);
                }
            }
        } else if (e.key === 'Escape') {
            e.preventDefault();
            hideAutocomplete();
        }
    });

    // Close autocomplete when clicking outside
    document.addEventListener('click', function(e) {
        if (autocompleteVisible && !autocompleteDropdown.contains(e.target) &&
            e.target !== grokPatternInput) {
            hideAutocomplete();
        }
    });

    // Set up event listeners for custom patterns input
    customPatternsInput.addEventListener('input', function() {
        updateLineNumbers(customPatternsInput, customPatternsLineNumbers);
    });

    customPatternsInput.addEventListener('scroll', function() {
        customPatternsLineNumbers.scrollTop = customPatternsInput.scrollTop;
    });

    // Function to get CSRF token from cookie
    function getCookie(name) {
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

    // HTMX integration - prepare data before sending
    document.body.addEventListener('htmx:configRequest', function(event) {
        if (event.detail.path === '/Utilities/GrokDebugger/simulate/') {
            // Validate required fields
            const sampleData = sampleDataInput.value.trim();
            const grokPattern = grokPatternInput.value.trim();

            if (!sampleData || !grokPattern) {
                // Prevent the request
                event.preventDefault();

                // Show error message
                const outputArea = document.getElementById('outputArea');
                let errorMessages = [];
                if (!sampleData) errorMessages.push('Sample Data is required');
                if (!grokPattern) errorMessages.push('Grok Pattern is required');

                outputArea.innerHTML = `
                    <div class="alert alert-error">
                        <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <div>
                            <p class="font-semibold">Validation Error</p>
                            <ul class="list-disc list-inside">
                                ${errorMessages.map(msg => `<li>${msg}</li>`).join('')}
                            </ul>
                        </div>
                    </div>
                `;
                return;
            }

            // Add CSRF token to headers
            const csrftoken = getCookie('csrftoken');
            event.detail.headers['X-CSRFToken'] = csrftoken;

            // Add the form data to the request
            event.detail.parameters = {
                sample_data: sampleData,
                grok_pattern: grokPattern,
                custom_patterns: customPatternsInput.value,
                multiline_mode: multilineCheckbox.checked
            };
        }
    });

    // Handle HTMX response errors
    document.body.addEventListener('htmx:responseError', function(event) {
        if (event.detail.pathInfo.requestPath === '/Utilities/GrokDebugger/simulate/') {
            const outputArea = document.getElementById('outputArea');
            outputArea.innerHTML = `
                <div class="alert alert-error">
                    <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span>Error: Unable to process the request. Please try again.</span>
                </div>
            `;
        }
    });

    // Initialize line numbers on page load
    updateLineNumbers(sampleDataInput, sampleDataLineNumbers);
    updateLineNumbers(grokPatternInput, grokPatternLineNumbers);
    updateLineNumbers(customPatternsInput, customPatternsLineNumbers);
});
