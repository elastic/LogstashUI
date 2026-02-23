// Track current editor mode
let currentEditorMode = 'ui'; // 'ui' or 'text'

/**
 * Switch to UI mode
 */
function switchToUIMode() {
    currentEditorMode = 'ui';
    
    // Update button styles
    const uiBtn = document.getElementById('uiModeBtn');
    const textBtn = document.getElementById('textModeBtn');
    
    if (uiBtn && textBtn) {
        uiBtn.className = 'px-4 py-2 rounded-md font-medium transition-colors bg-green-600 text-white relative z-10';
        textBtn.className = 'px-4 py-2 rounded-md font-medium transition-colors text-gray-300 hover:bg-gray-600 relative z-10';
        
        // Add flash animation
        addFlashAnimation(uiBtn);
    }
    
    // Show UI container, hide text container
    const uiContainer = document.getElementById('uiModeContainer');
    const textContainer = document.getElementById('textModeContainer');
    
    if (uiContainer && textContainer) {
        uiContainer.classList.remove('hidden');
        textContainer.classList.add('hidden');
    }
    
    // Enable View Code and Simulate Pipeline buttons
    enableEditorButtons();
}

/**
 * Switch to Text mode
 */
function switchToTextMode() {
    currentEditorMode = 'text';
    
    // Update button styles
    const uiBtn = document.getElementById('uiModeBtn');
    const textBtn = document.getElementById('textModeBtn');
    
    if (uiBtn && textBtn) {
        uiBtn.className = 'px-4 py-2 rounded-md font-medium transition-colors text-gray-300 hover:bg-gray-600 relative z-10';
        textBtn.className = 'px-4 py-2 rounded-md font-medium transition-colors bg-green-600 text-white relative z-10';
        
        // Add flash animation
        addFlashAnimation(textBtn);
    }
    
    // Hide UI container, show text container
    const uiContainer = document.getElementById('uiModeContainer');
    const textContainer = document.getElementById('textModeContainer');
    
    if (uiContainer && textContainer) {
        uiContainer.classList.add('hidden');
        textContainer.classList.remove('hidden');
    }
    
    // Disable View Code and Simulate Pipeline buttons
    disableEditorButtons();
    
    // Use fetch to convert components to config
    if (typeof components !== 'undefined') {
        const textEditor = document.getElementById('pipelineTextEditor');
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
        
        // Create form data
        const formData = new FormData();
        formData.append('components', JSON.stringify(components));
        
        fetch('/API/ComponentsToConfig/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken
            },
            body: formData
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.text();
        })
        .then(configText => {
            // Set the config text to the textarea
            if (textEditor) {
                textEditor.value = configText;
                updateTextEditorStats();
                
                // Update line numbers and syntax highlighting
                const lineNumbers = document.getElementById('pipelineTextEditorLineNumbers');
                if (lineNumbers) {
                    updateLineNumbers(textEditor, lineNumbers);
                }
                applySyntaxHighlighting();
            }
        })
        .catch(error => {
            console.error('Error converting components to config:', error);
            // Fallback to client-side conversion on error
            syncUIToTextEditor();
        });
    } else {
        // Fallback to client-side conversion if components not available
        syncUIToTextEditor();
    }
    
    // Initialize text editor features
    initializeTextEditor();
}

/**
 * Convert UI components to Logstash configuration text
 */
function syncUIToTextEditor() {
    if (typeof components === 'undefined') {
        console.warn('Components not defined, cannot sync to text editor');
        return;
    }
    
    const textEditor = document.getElementById('pipelineTextEditor');
    if (!textEditor) return;
    
    let configText = '';
    
    // Generate input section
    if (components.input && components.input.length > 0) {
        configText += 'input {\n';
        components.input.forEach(plugin => {
            configText += generatePluginConfig(plugin, 1);
        });
        configText += '}\n\n';
    }
    
    // Generate filter section
    if (components.filter && components.filter.length > 0) {
        configText += 'filter {\n';
        components.filter.forEach(component => {
            configText += generateComponentConfig(component, 1);
        });
        configText += '}\n\n';
    }
    
    // Generate output section
    if (components.output && components.output.length > 0) {
        configText += 'output {\n';
        components.output.forEach(component => {
            configText += generateComponentConfig(component, 1);
        });
        configText += '}\n';
    }
    
    textEditor.value = configText.trim();
    updateTextEditorStats();
}

/**
 * Generate configuration text for a component (plugin or conditional)
 */
function generateComponentConfig(component, indentLevel) {
    const indent = '  '.repeat(indentLevel);
    let config = '';
    
    if (component.type === 'conditional') {
        config += `${indent}if ${component.condition} {\n`;
        if (component.plugins && component.plugins.length > 0) {
            component.plugins.forEach(plugin => {
                config += generatePluginConfig(plugin, indentLevel + 1);
            });
        }
        config += `${indent}}\n`;
    } else {
        config += generatePluginConfig(component, indentLevel);
    }
    
    return config;
}

/**
 * Generate configuration text for a plugin
 */
function generatePluginConfig(plugin, indentLevel) {
    const indent = '  '.repeat(indentLevel);
    let config = '';
    
    if (plugin.type === 'comment') {
        config += `${indent}# ${plugin.config?.text || plugin.config?.comment || ''}\n`;
        return config;
    }
    
    config += `${indent}${plugin.plugin_name} {\n`;
    
    if (plugin.config) {
        Object.entries(plugin.config).forEach(([key, value]) => {
            config += `${indent}  ${key} => ${formatConfigValue(value)}\n`;
        });
    }
    
    config += `${indent}}\n`;
    return config;
}

/**
 * Format a configuration value for Logstash syntax
 */
function formatConfigValue(value) {
    if (typeof value === 'string') {
        // Check if it's already quoted or a special value
        if (value.startsWith('"') || value.startsWith("'") || 
            value === 'true' || value === 'false' || 
            !isNaN(value)) {
            return value;
        }
        return `"${value}"`;
    } else if (typeof value === 'number' || typeof value === 'boolean') {
        return value;
    } else if (Array.isArray(value)) {
        return `[${value.map(v => formatConfigValue(v)).join(', ')}]`;
    } else if (typeof value === 'object') {
        const entries = Object.entries(value).map(([k, v]) => `"${k}" => ${formatConfigValue(v)}`);
        return `{ ${entries.join(', ')} }`;
    }
    return String(value);
}

/**
 * Initialize text editor features (line count, character count, etc.)
 */
function initializeTextEditor() {
    const textEditor = document.getElementById('pipelineTextEditor');
    const lineNumbers = document.getElementById('pipelineTextEditorLineNumbers');
    const overlay = document.getElementById('syntaxHighlightOverlay');
    
    if (!textEditor) return;
    
    // Update stats, line numbers, and syntax highlighting on input
    textEditor.addEventListener('input', function() {
        updateTextEditorStats();
        updateLineNumbers(textEditor, lineNumbers);
        applySyntaxHighlighting();
    });
    
    // Sync scroll between textarea, line numbers, and overlay
    textEditor.addEventListener('scroll', function() {
        if (lineNumbers) {
            lineNumbers.scrollTop = textEditor.scrollTop;
        }
        if (overlay) {
            overlay.scrollTop = textEditor.scrollTop;
            overlay.scrollLeft = textEditor.scrollLeft;
        }
    });
    
    // Initial updates
    updateTextEditorStats();
    updateLineNumbers(textEditor, lineNumbers);
    applySyntaxHighlighting();
}

/**
 * Update line and character count
 */
function updateTextEditorStats() {
    const textEditor = document.getElementById('pipelineTextEditor');
    const lineCountEl = document.getElementById('lineCount');
    const charCountEl = document.getElementById('charCount');
    
    if (!textEditor || !lineCountEl || !charCountEl) return;
    
    const text = textEditor.value;
    const lines = text.split('\n').length;
    const chars = text.length;
    
    lineCountEl.textContent = `Lines: ${lines}`;
    charCountEl.textContent = `Characters: ${chars}`;
}

/**
 * Update line numbers for the text editor (from grok debugger)
 */
function updateLineNumbers(textarea, lineNumbersContainer) {
    if (!textarea || !lineNumbersContainer) return;
    
    const lines = textarea.value.split('\n');
    const lineCount = lines.length;

    // Create a mirror div to measure actual line heights
    const mirror = document.createElement('div');
    const computedStyle = window.getComputedStyle(textarea);

    // Copy relevant styles from textarea to mirror
    mirror.style.position = 'absolute';
    mirror.style.visibility = 'hidden';
    mirror.style.whiteSpace = computedStyle.whiteSpace;
    mirror.style.wordWrap = computedStyle.wordWrap;
    mirror.style.overflowWrap = computedStyle.overflowWrap;
    
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

/**
 * Apply syntax highlighting to the text editor
 */
function applySyntaxHighlighting() {
    const textEditor = document.getElementById('pipelineTextEditor');
    const overlay = document.getElementById('syntaxHighlightOverlay');
    
    if (!textEditor || !overlay) return;
    
    const text = textEditor.value;
    
    // Escape HTML
    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
    
    // Apply color rules for input, filter, output sections
    let highlighted = escapeHtml(text);
    
    // Match 'input {' and its closing bracket
    highlighted = highlighted.replace(
        /(input)(\s*)(\{)/gi,
        '<span class="syntax-input">$1$2$3</span>'
    );
    
    // Match 'filter {' and its closing bracket
    highlighted = highlighted.replace(
        /(filter)(\s*)(\{)/gi,
        '<span class="syntax-filter">$1$2$3</span>'
    );
    
    // Match 'output {' and its closing bracket
    highlighted = highlighted.replace(
        /(output)(\s*)(\{)/gi,
        '<span class="syntax-output">$1$2$3</span>'
    );
    
    // Find and color matching closing braces for each section
    highlighted = colorMatchingBraces(text, highlighted);
    
    overlay.innerHTML = highlighted;
}

/**
 * Color matching closing braces for input/filter/output sections
 */
function colorMatchingBraces(originalText, highlightedHtml) {
    const sections = ['input', 'filter', 'output'];
    const colors = {
        'input': 'syntax-input',
        'filter': 'syntax-filter',
        'output': 'syntax-output'
    };
    
    sections.forEach(section => {
        const regex = new RegExp(`(${section})\\s*\\{`, 'gi');
        let match;
        
        while ((match = regex.exec(originalText)) !== null) {
            const startPos = match.index + match[0].length - 1; // Position of opening brace
            let braceCount = 1;
            let endPos = -1;
            
            // Find matching closing brace
            for (let i = startPos + 1; i < originalText.length; i++) {
                if (originalText[i] === '{') braceCount++;
                if (originalText[i] === '}') {
                    braceCount--;
                    if (braceCount === 0) {
                        endPos = i;
                        break;
                    }
                }
            }
            
            // If we found a matching brace, color it
            if (endPos !== -1) {
                // Count how many characters before the closing brace in the original text
                const beforeBrace = originalText.substring(0, endPos);
                // We need to find this position in the highlighted HTML
                // For simplicity, we'll use a marker approach
                const marker = `__CLOSE_BRACE_${section.toUpperCase()}_${match.index}__`;
                highlightedHtml = highlightedHtml.replace(
                    new RegExp(`(${escapeRegex(originalText.substring(endPos, endPos + 1))})`, 'g'),
                    function(m, p1, offset) {
                        // Check if this is roughly the right position
                        return `<span class="${colors[section]}">${p1}</span>`;
                    }
                );
            }
        }
    });
    
    return highlightedHtml;
}

/**
 * Escape special regex characters
 */
function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Add flash animation to a button
 */
function addFlashAnimation(button) {
    const container = button.closest('.bg-gray-700');
    if (!container) return;
    
    // Add the flash class
    container.classList.add('toggle-flash');
    
    // Remove the class after animation completes
    setTimeout(() => {
        container.classList.remove('toggle-flash');
    }, 600);
}

/**
 * Disable View Code and Simulate Pipeline buttons
 */
function disableEditorButtons() {
    const viewCodeBtn = document.getElementById('viewCode');
    const simulateBtn = document.getElementById('simulatePipeline');
    
    if (viewCodeBtn) {
        viewCodeBtn.disabled = true;
        viewCodeBtn.classList.add('opacity-50', 'cursor-not-allowed');
        viewCodeBtn.classList.remove('hover:bg-gray-600');
    }
    
    if (simulateBtn) {
        simulateBtn.disabled = true;
        simulateBtn.classList.add('opacity-50', 'cursor-not-allowed');
        simulateBtn.classList.remove('hover:bg-purple-700');
    }
}

/**
 * Enable View Code and Simulate Pipeline buttons
 */
function enableEditorButtons() {
    const viewCodeBtn = document.getElementById('viewCode');
    const simulateBtn = document.getElementById('simulatePipeline');
    
    if (viewCodeBtn) {
        viewCodeBtn.disabled = false;
        viewCodeBtn.classList.remove('opacity-50', 'cursor-not-allowed');
        viewCodeBtn.classList.add('hover:bg-gray-600');
    }
    
    if (simulateBtn) {
        simulateBtn.disabled = false;
        simulateBtn.classList.remove('opacity-50', 'cursor-not-allowed');
        simulateBtn.classList.add('hover:bg-purple-700');
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Set initial mode to UI
    switchToUIMode();
});
