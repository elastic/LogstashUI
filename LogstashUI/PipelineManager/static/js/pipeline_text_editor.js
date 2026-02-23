// Track current editor mode
let currentEditorMode = 'ui'; // 'ui' or 'text'

// CodeMirror editor instance
let codeMirrorEditor = null;

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
            // Set the config text to CodeMirror editor
            if (codeMirrorEditor) {
                codeMirrorEditor.setValue(configText);
            } else if (textEditor) {
                textEditor.value = configText;
            }
            updateTextEditorStats();
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
 * Define custom Logstash mode for CodeMirror
 */
function defineLogstashMode() {
    CodeMirror.defineMode("logstash", function() {
        return {
            startState: function() {
                return {
                    inConditional: false,
                    afterArrow: false
                };
            },
            token: function(stream, state) {
                // Check for input/filter/output keywords
                if (stream.match(/\binput\b/)) {
                    return "logstash-input";
                }
                if (stream.match(/\bfilter\b/)) {
                    return "logstash-filter";
                }
                if (stream.match(/\boutput\b/)) {
                    return "logstash-output";
                }
                
                // Conditionals (if, else if, else)
                if (stream.match(/\belse\s+if\b/)) {
                    state.inConditional = true;
                    return "logstash-conditional";
                }
                if (stream.match(/\bif\b/)) {
                    state.inConditional = true;
                    return "logstash-conditional";
                }
                if (stream.match(/\belse\b/)) {
                    state.inConditional = false;
                    return "logstash-conditional";
                }
                
                // Braces
                if (stream.match(/[{}]/)) {
                    if (stream.current() === '{' && state.inConditional) {
                        state.inConditional = false;
                    }
                    return "logstash-brace";
                }
                
                // Strings
                if (stream.match(/"(?:[^\\"]|\\.)*"/)) {
                    state.afterArrow = false;
                    return "string";
                }
                if (stream.match(/'(?:[^\\']|\\.)*'/)) {
                    state.afterArrow = false;
                    return "string";
                }
                
                // Comments
                if (stream.match(/#.*/)) {
                    return "comment";
                }
                
                // Numbers
                if (stream.match(/\b\d+\b/)) {
                    return "number";
                }
                
                // Arrow operator
                if (stream.match(/=>/)) {
                    state.afterArrow = true;
                    return "operator";
                }
                
                // Other operators
                if (stream.match(/==|!=|<=|>=|<|>/)) {
                    return "operator";
                }
                
                // Plugin names (words followed by {) - now with custom color
                if (stream.match(/\b[a-z_][a-z0-9_]*(?=\s*\{)/i)) {
                    return "logstash-plugin";
                }
                
                // Option keys (words before =>)
                if (stream.match(/\b[a-z_][a-z0-9_]*(?=\s*=>)/i)) {
                    return "logstash-key";
                }
                
                // Expressions in conditionals (words/identifiers after if/else if)
                if (state.inConditional && stream.match(/\b[a-z_][a-z0-9_]*/i)) {
                    return "logstash-expression";
                }
                
                // Field names
                if (stream.match(/\[[^\]]+\]/)) {
                    return "variable";
                }
                
                stream.next();
                return null;
            }
        };
    });
}

/**
 * Initialize CodeMirror text editor
 */
function initializeTextEditor() {
    const textEditor = document.getElementById('pipelineTextEditor');
    
    if (!textEditor || codeMirrorEditor) return;
    
    // Define custom Logstash mode
    defineLogstashMode();
    
    // Initialize CodeMirror
    codeMirrorEditor = CodeMirror.fromTextArea(textEditor, {
        mode: 'logstash',
        lineNumbers: true,
        theme: 'default',
        indentUnit: 2,
        tabSize: 2,
        indentWithTabs: false,
        lineWrapping: true,
        extraKeys: {
            "'{'": function(cm) {
                cm.replaceSelection('{}');
                const cursor = cm.getCursor();
                cm.setCursor({line: cursor.line, ch: cursor.ch - 1});
            },
            "'['": function(cm) {
                cm.replaceSelection('[]');
                const cursor = cm.getCursor();
                cm.setCursor({line: cursor.line, ch: cursor.ch - 1});
            },
            "'('": function(cm) {
                cm.replaceSelection('()');
                const cursor = cm.getCursor();
                cm.setCursor({line: cursor.line, ch: cursor.ch - 1});
            },
            "'\"'": function(cm) {
                const cursor = cm.getCursor();
                const line = cm.getLine(cursor.line);
                const after = line.substring(cursor.ch);
                
                // If next char is already a quote, just move cursor
                if (after.startsWith('"')) {
                    cm.setCursor({line: cursor.line, ch: cursor.ch + 1});
                } else {
                    cm.replaceSelection('""');
                    const newCursor = cm.getCursor();
                    cm.setCursor({line: newCursor.line, ch: newCursor.ch - 1});
                }
            },
            "\"'\"": function(cm) {
                const cursor = cm.getCursor();
                const line = cm.getLine(cursor.line);
                const after = line.substring(cursor.ch);
                
                // If next char is already a quote, just move cursor
                if (after.startsWith("'")) {
                    cm.setCursor({line: cursor.line, ch: cursor.ch + 1});
                } else {
                    cm.replaceSelection("''");
                    const newCursor = cm.getCursor();
                    cm.setCursor({line: newCursor.line, ch: newCursor.ch - 1});
                }
            },
            "Tab": function(cm) {
                if (cm.somethingSelected()) {
                    cm.indentSelection("add");
                } else {
                    cm.replaceSelection("  ", "end");
                }
            },
            "Enter": function(cm) {
                const cursor = cm.getCursor();
                const line = cm.getLine(cursor.line);
                const beforeCursor = line.substring(0, cursor.ch);
                const afterCursor = line.substring(cursor.ch);
                
                // Get current indentation
                const indentMatch = beforeCursor.match(/^(\s*)/);
                const currentIndent = indentMatch ? indentMatch[1] : '';
                const indentUnit = '  '; // 2 spaces
                
                // Check if we're between matching brackets {}
                const openBracket = beforeCursor.trimEnd().endsWith('{');
                const closeBracket = afterCursor.trimStart().startsWith('}');
                
                if (openBracket && closeBracket) {
                    // Case 1: Between {} - just add newlines and indent, don't duplicate }
                    cm.replaceSelection('\n' + currentIndent + indentUnit + '\n' + currentIndent);
                    // Move cursor to the indented line
                    cm.setCursor({line: cursor.line + 1, ch: (currentIndent + indentUnit).length});
                } else if (openBracket) {
                    // Case 2: After { with no immediate } - go to next line with indent
                    cm.replaceSelection('\n' + currentIndent + indentUnit);
                } else if (closeBracket) {
                    // Case 3: Before } - maintain current indent
                    cm.replaceSelection('\n' + currentIndent);
                } else {
                    // Default: maintain current indentation
                    cm.replaceSelection('\n' + currentIndent);
                }
            }
        }
    });
    
    // Update stats on change
    codeMirrorEditor.on('change', function() {
        updateTextEditorStats();
    });
    
    // Bracket matching on cursor activity
    codeMirrorEditor.on('cursorActivity', function() {
        highlightMatchingBrackets(codeMirrorEditor);
    });
    
    // Initial stats update
    updateTextEditorStats();
}

/**
 * Highlight matching brackets
 */
let bracketMarks = [];
function highlightMatchingBrackets(cm) {
    // Clear previous marks
    bracketMarks.forEach(mark => mark.clear());
    bracketMarks = [];
    
    const cursor = cm.getCursor();
    const line = cm.getLine(cursor.line);
    const ch = cursor.ch;
    
    // Check character at cursor and before cursor
    const charAfter = line.charAt(ch);
    const charBefore = ch > 0 ? line.charAt(ch - 1) : '';
    
    const openBrackets = ['{', '[', '('];
    const closeBrackets = ['}', ']', ')'];
    const brackets = {
        '{': '}', '}': '{',
        '[': ']', ']': '[',
        '(': ')', ')': '('
    };
    
    let bracketChar = '';
    let bracketPos = null;
    let searchForward = false;
    
    // Prioritize: opening bracket at cursor, closing bracket before cursor, then others
    if (openBrackets.includes(charAfter)) {
        bracketChar = charAfter;
        bracketPos = {line: cursor.line, ch: ch};
        searchForward = true;
    } else if (closeBrackets.includes(charBefore)) {
        bracketChar = charBefore;
        bracketPos = {line: cursor.line, ch: ch - 1};
        searchForward = false;
    } else if (closeBrackets.includes(charAfter)) {
        bracketChar = charAfter;
        bracketPos = {line: cursor.line, ch: ch};
        searchForward = false;
    } else if (openBrackets.includes(charBefore)) {
        bracketChar = charBefore;
        bracketPos = {line: cursor.line, ch: ch - 1};
        searchForward = true;
    }
    
    if (!bracketChar) return;
    
    const matchChar = brackets[bracketChar];
    const matchPos = findMatchingBracket(cm, bracketPos, bracketChar, matchChar, searchForward);
    
    if (matchPos) {
        // Highlight both brackets
        const mark1 = cm.markText(
            bracketPos,
            {line: bracketPos.line, ch: bracketPos.ch + 1},
            {className: 'CodeMirror-matchingbracket'}
        );
        const mark2 = cm.markText(
            matchPos,
            {line: matchPos.line, ch: matchPos.ch + 1},
            {className: 'CodeMirror-matchingbracket'}
        );
        bracketMarks.push(mark1, mark2);
    } else {
        // Non-matching bracket
        const mark = cm.markText(
            bracketPos,
            {line: bracketPos.line, ch: bracketPos.ch + 1},
            {className: 'CodeMirror-nonmatchingbracket'}
        );
        bracketMarks.push(mark);
    }
}

/**
 * Find matching bracket position
 */
function findMatchingBracket(cm, pos, openChar, closeChar, searchForward) {
    const maxScanLines = 1000;
    let depth = 1;
    
    if (searchForward) {
        // Search forward for closing bracket
        for (let line = pos.line; line < Math.min(cm.lineCount(), pos.line + maxScanLines); line++) {
            const text = cm.getLine(line);
            const startCh = (line === pos.line) ? pos.ch + 1 : 0;
            
            for (let ch = startCh; ch < text.length; ch++) {
                if (text[ch] === openChar) depth++;
                if (text[ch] === closeChar) {
                    depth--;
                    if (depth === 0) {
                        return {line: line, ch: ch};
                    }
                }
            }
        }
    } else {
        // Search backward for opening bracket
        for (let line = pos.line; line >= Math.max(0, pos.line - maxScanLines); line--) {
            const text = cm.getLine(line);
            // Start from before the bracket position on the same line, or end of line for other lines
            const startCh = (line === pos.line) ? pos.ch : text.length;
            
            for (let ch = startCh - 1; ch >= 0; ch--) {
                if (text[ch] === closeChar) depth++;
                if (text[ch] === openChar) {
                    depth--;
                    if (depth === 0) {
                        return {line: line, ch: ch};
                    }
                }
            }
        }
    }
    
    return null;
}

/**
 * Update line and character count
 */
function updateTextEditorStats() {
    const lineCountEl = document.getElementById('lineCount');
    const charCountEl = document.getElementById('charCount');
    
    if (!lineCountEl || !charCountEl) return;
    
    let text = '';
    if (codeMirrorEditor) {
        text = codeMirrorEditor.getValue();
    } else {
        const textEditor = document.getElementById('pipelineTextEditor');
        if (textEditor) {
            text = textEditor.value;
        }
    }
    
    const lines = text.split('\n').length;
    const chars = text.length;
    
    lineCountEl.textContent = `Lines: ${lines}`;
    charCountEl.textContent = `Characters: ${chars}`;
}

// Old textarea functions removed - CodeMirror handles this now

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
