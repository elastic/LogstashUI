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
 * Detect if cursor is inside a plugin block and return plugin info
 */
function detectCurrentPlugin(cm, cursor) {
    let depth = 0;
    
    console.log('detectCurrentPlugin - Starting at line', cursor.line, 'ch', cursor.ch);
    
    // First, count braces from cursor position backwards to determine current depth
    for (let line = cursor.line; line >= 0; line--) {
        const fullLine = cm.getLine(line);
        const endCh = (line === cursor.line) ? cursor.ch : fullLine.length;
        
        // Scan this line from the end position backwards
        for (let ch = endCh - 1; ch >= 0; ch--) {
            if (fullLine[ch] === '}') depth++;
            if (fullLine[ch] === '{') depth--;
        }
    }
    
    console.log('detectCurrentPlugin - Current depth:', depth);
    
    // If depth is >= 0, we're not inside any block
    if (depth >= 0) {
        console.log('detectCurrentPlugin - Not inside any block (depth >= 0)');
        return null;
    }
    
    // We're inside a block (depth < 0), now find which plugin
    // Search backwards to find the opening brace that contains us
    let searchDepth = 0;
    for (let line = cursor.line; line >= 0; line--) {
        const fullLine = cm.getLine(line);
        const lineText = fullLine.trim();
        const endCh = (line === cursor.line) ? cursor.ch : fullLine.length;
        
        // Scan this line from the end position backwards
        for (let ch = endCh - 1; ch >= 0; ch--) {
            if (fullLine[ch] === '}') searchDepth++;
            if (fullLine[ch] === '{') {
                searchDepth--;
                
                // When we find the opening brace that matches our depth
                if (searchDepth < 0) {
                    console.log('detectCurrentPlugin - Found opening brace at line', line, ':', lineText);
                    // Check if this line starts a plugin
                    const pluginMatch = lineText.match(/^(\w+)\s*\{/);
                    if (pluginMatch) {
                        const possiblePlugin = pluginMatch[1];
                        console.log('detectCurrentPlugin - Found possible plugin:', possiblePlugin);
                        
                        // Make sure it's not a main section
                        if (!['input', 'filter', 'output', 'if', 'else'].includes(possiblePlugin)) {
                            // We found the plugin we're inside
                            const section = detectCurrentSection(cm, { line: line, ch: 0 });
                            console.log('detectCurrentPlugin - Detected plugin:', possiblePlugin, 'type:', section);
                            return { name: possiblePlugin, type: section };
                        } else {
                            console.log('detectCurrentPlugin - Skipping main section:', possiblePlugin);
                        }
                    }
                    // Found the brace but it's not a plugin, stop searching
                    console.log('detectCurrentPlugin - No plugin detected');
                    return null;
                }
            }
        }
    }
    
    console.log('detectCurrentPlugin - No plugin detected');
    return null;
}

/**
 * Detect which section (input/filter/output) the cursor is currently in
 */
function detectCurrentSection(cm, cursor) {
    let currentSection = null;
    
    // Search backwards from cursor to find the section we're in
    for (let line = cursor.line; line >= 0; line--) {
        const lineText = cm.getLine(line).trim();
        
        // Check if we found a section start
        if (/^input\s*\{/.test(lineText)) {
            currentSection = 'input';
            break;
        } else if (/^filter\s*\{/.test(lineText)) {
            currentSection = 'filter';
            break;
        } else if (/^output\s*\{/.test(lineText)) {
            currentSection = 'output';
            break;
        }
        
        // If we hit a closing brace at the start of a line, we might be outside sections
        if (/^\}/.test(lineText)) {
            // Check if this closes a section by counting braces
            let depth = 0;
            for (let i = line; i >= 0; i--) {
                const text = cm.getLine(i);
                for (let ch = 0; ch < text.length; ch++) {
                    if (text[ch] === '{') depth++;
                    if (text[ch] === '}') depth--;
                }
                
                const trimmed = text.trim();
                if (depth === 0 && /^(input|filter|output)\s*\{/.test(trimmed)) {
                    // We're outside this section
                    return null;
                }
            }
        }
    }
    
    return currentSection;
}

/**
 * Get plugin suggestions based on current section
 */
function getPluginSuggestions(section, filterText = '') {
    console.log('getPluginSuggestions - section:', section);
    console.log('window.pluginData exists:', !!window.pluginData);
    console.log('window.pluginData:', window.pluginData);
    
    if (!section || !window.pluginData || !window.pluginData[section]) {
        console.log('Early return - section:', section, 'pluginData:', !!window.pluginData, 'pluginData[section]:', window.pluginData ? !!window.pluginData[section] : 'N/A');
        return [];
    }
    
    const plugins = window.pluginData[section];
    console.log('Plugins for section:', section, 'count:', Object.keys(plugins).length);
    const suggestions = [];
    const filter = filterText.toLowerCase();
    
    for (const pluginName in plugins) {
        const plugin = plugins[pluginName];
        
        // Skip the 'comment' plugin
        if (pluginName === 'comment') {
            continue;
        }
        
        // Filter by substring match
        if (filter && !pluginName.toLowerCase().includes(filter)) {
            continue;
        }
        
        suggestions.push({
            text: pluginName,
            displayText: pluginName + (plugin.description ? ' - ' + plugin.description : ''),
            plugin: plugin,
            render: function(element, self, data) {
                element.innerHTML = '<span style="font-weight: bold;">' + data.text + '</span>' +
                                  (data.plugin.description ? '<span style="color: #9ca3af; margin-left: 8px;"> - ' + data.plugin.description + '</span>' : '');
            },
            hint: function(cm, self, data) {
                const cursor = cm.getCursor();
                const line = cm.getLine(cursor.line);
                
                // Calculate proper indentation based on nesting level
                const properIndent = calculateIndentation(cm, cursor);
                
                // Get required options for this plugin with their types
                const requiredOptions = [];
                if (data.plugin.options) {
                    for (const optionName in data.plugin.options) {
                        const option = data.plugin.options[optionName];
                        if (option.required && option.required.toLowerCase().includes('yes')) {
                            requiredOptions.push({
                                name: optionName,
                                type: option.input_type,
                                option: option
                            });
                        }
                    }
                }
                
                // Build the plugin block with proper indentation and placeholders
                let pluginBlock = data.text + ' {\n';
                
                if (requiredOptions.length > 0) {
                    for (const reqOption of requiredOptions) {
                        const placeholder = getPlaceholderForType(reqOption.type);
                        pluginBlock += properIndent + '  ' + reqOption.name + ' => ' + placeholder + '\n';
                    }
                }
                
                pluginBlock += properIndent + '}';
                
                // Replace the current line content
                cm.replaceRange(
                    properIndent + pluginBlock,
                    { line: cursor.line, ch: 0 },
                    { line: cursor.line, ch: line.length }
                );
                
                // Position cursor at the placeholder value of the first required option
                if (requiredOptions.length > 0) {
                    const firstOption = requiredOptions[0];
                    const placeholder = getPlaceholderForType(firstOption.type);
                    const lineWithOption = cursor.line + 1;
                    const optionLineText = properIndent + '  ' + firstOption.name + ' => ' + placeholder;
                    const placeholderStart = (properIndent + '  ' + firstOption.name + ' => ').length;
                    
                    // Select the placeholder so user can immediately type to replace it
                    cm.setSelection(
                        { line: lineWithOption, ch: placeholderStart },
                        { line: lineWithOption, ch: placeholderStart + placeholder.length }
                    );
                } else {
                    cm.setCursor({ line: cursor.line + 1, ch: properIndent.length + 2 });
                }
            }
        });
    }
    
    // Sort alphabetically
    suggestions.sort((a, b) => a.text.localeCompare(b.text));
    
    return suggestions;
}

/**
 * Show autocomplete for plugin options
 */
function showOptionAutocomplete(cm, plugin) {
    if (!plugin || !plugin.options) return;
    
    CodeMirror.showHint(cm, function(cm) {
        const cursor = cm.getCursor();
        const line = cm.getLine(cursor.line);
        const lineUpToCursor = line.substring(0, cursor.ch);
        const currentIndent = line.match(/^\s*/)[0];
        const trimmed = line.trim();
        const wordStart = lineUpToCursor.search(/\S+$/);
        const word = wordStart >= 0 ? lineUpToCursor.substring(wordStart) : '';
        
        const suggestions = [];
        
        for (const optionName in plugin.options) {
            const option = plugin.options[optionName];
            
            // Filter by what's already typed
            if (word && !optionName.toLowerCase().includes(word.toLowerCase())) {
                continue;
            }
            
            suggestions.push({
                text: optionName,
                displayText: optionName + ' => ' + (option.input_type || '') + 
                           (option.required && option.required.toLowerCase().includes('yes') ? ' (required)' : ''),
                option: option,
                hint: function(cm, self, data) {
                    const cursor = cm.getCursor();
                    const line = cm.getLine(cursor.line);
                    const currentIndent = line.match(/^\s*/)[0];
                    
                    // Get placeholder for this option type
                    const placeholder = getPlaceholderForType(data.option.input_type);
                    const optionLine = data.text + ' => ' + placeholder;
                    
                    // Replace the current line
                    cm.replaceRange(
                        currentIndent + optionLine,
                        { line: cursor.line, ch: 0 },
                        { line: cursor.line, ch: line.length }
                    );
                    
                    // Select the placeholder
                    const placeholderStart = currentIndent.length + data.text.length + ' => '.length;
                    cm.setSelection(
                        { line: cursor.line, ch: placeholderStart },
                        { line: cursor.line, ch: placeholderStart + placeholder.length }
                    );
                }
            });
        }
        
        suggestions.sort((a, b) => a.text.localeCompare(b.text));
        
        if (suggestions.length === 0) return null;
        
        return {
            list: suggestions,
            from: CodeMirror.Pos(cursor.line, currentIndent.length),
            to: CodeMirror.Pos(cursor.line, line.length)
        };
    }, {
        completeSingle: false,
        closeOnUnfocus: false
    });
}

/**
 * Calculate proper indentation based on current nesting level
 */
function calculateIndentation(cm, cursor) {
    let depth = 0;
    const indentUnit = '  '; // 2 spaces
    
    // Count opening and closing braces from start to cursor position
    for (let lineNum = 0; lineNum <= cursor.line; lineNum++) {
        const lineText = cm.getLine(lineNum);
        const endCh = (lineNum === cursor.line) ? cursor.ch : lineText.length;
        
        for (let ch = 0; ch < endCh; ch++) {
            if (lineText[ch] === '{') depth++;
            if (lineText[ch] === '}') depth--;
        }
    }
    
    // Generate indentation string
    return indentUnit.repeat(Math.max(0, depth));
}

/**
 * Get placeholder value based on input type
 */
function getPlaceholderForType(inputType) {
    if (!inputType) return '""';
    
    const type = inputType.toLowerCase();
    
    // Handle array types
    if (type.includes('array')) {
        return '[]';
    }
    
    // Handle hash/object types
    if (type.includes('hash')) {
        return '{}';
    }
    
    // Handle number types
    if (type.includes('number')) {
        return '0';
    }
    
    // Handle boolean types
    if (type.includes('boolean')) {
        return 'false';
    }
    
    // Handle codec type
    if (type.includes('codec')) {
        return '"json"';
    }
    
    // Handle path types
    if (type.includes('path')) {
        return '"/path/to/file"';
    }
    
    // Handle password types
    if (type.includes('password')) {
        return '"password"';
    }
    
    // Default to empty string for string types and unknown
    return '""';
}

/**
 * Show plugin autocomplete
 */
function showPluginAutocomplete(cm) {
    console.log('showPluginAutocomplete called');
    console.log('CodeMirror.showHint available:', typeof CodeMirror.showHint);
    
    if (typeof CodeMirror.showHint !== 'function') {
        console.error('CodeMirror.showHint is not available! The show-hint addon is not loaded.');
        return;
    }
    
    const cursor = cm.getCursor();
    const line = cm.getLine(cursor.line);
    const lineUpToCursor = line.substring(0, cursor.ch);
    const trimmedLine = line.trim();
    
    // Detect which section we're in
    const section = detectCurrentSection(cm, cursor);
    console.log('Section detected:', section);
    if (!section) return;
    
    // Get the word being typed (if any) - this will be used for filtering
    const wordMatch = trimmedLine.match(/^([a-zA-Z_]+)$/);
    const filterText = wordMatch ? wordMatch[1] : '';
    console.log('Filter text:', filterText);
    
    // Get plugin suggestions (filtered by current text)
    const suggestions = getPluginSuggestions(section, filterText);
    console.log('Suggestions count:', suggestions.length);
    if (suggestions.length === 0) return;
    
    console.log('Calling CodeMirror.showHint...');
    CodeMirror.showHint(cm, function(cm) {
        const cursor = cm.getCursor();
        const line = cm.getLine(cursor.line);
        const currentIndent = line.match(/^\s*/)[0];
        const trimmed = line.trim();
        
        // Re-filter suggestions based on current input
        const currentFilter = trimmed.match(/^([a-zA-Z_]+)$/) ? trimmed : '';
        const filteredSuggestions = getPluginSuggestions(section, currentFilter);
        
        return {
            list: filteredSuggestions,
            from: CodeMirror.Pos(cursor.line, currentIndent.length),
            to: CodeMirror.Pos(cursor.line, line.length)
        };
    }, {
        completeSingle: false,
        closeOnUnfocus: false
    });
    console.log('CodeMirror.showHint called');
}

/**
 * Custom fold helper for Logstash syntax
 * Folds input/filter/output blocks, plugin blocks, and conditional blocks
 */
CodeMirror.registerHelper("fold", "logstash", function(cm, start) {
    const line = cm.getLine(start.line);
    const lineText = line.trim();
    
    // Check if this line starts a foldable block
    // Match: input {, filter {, output {, plugin_name {, if/else if/else {
    const isMainSection = /^(input|filter|output)\s*\{/.test(lineText);
    const isConditional = /^(if\s+|else\s+if\s+|else\s*)\{/.test(lineText) || 
                         /^(if|else\s+if|else)\s+.*\{/.test(lineText);
    const isPlugin = /^\w+\s*\{/.test(lineText);
    
    const blockStart = isMainSection || isConditional || isPlugin;
    
    if (!blockStart) return;
    
    // Find the opening brace position
    const openBracePos = line.indexOf('{');
    if (openBracePos === -1) return;
    
    // Find the matching closing brace
    let depth = 0;
    let foundOpen = false;
    
    for (let lineNum = start.line; lineNum < cm.lineCount(); lineNum++) {
        const currentLine = cm.getLine(lineNum);
        const startCh = (lineNum === start.line) ? openBracePos : 0;
        
        for (let ch = startCh; ch < currentLine.length; ch++) {
            if (currentLine[ch] === '{') {
                depth++;
                foundOpen = true;
            } else if (currentLine[ch] === '}') {
                depth--;
                if (foundOpen && depth === 0) {
                    // Found the matching closing brace
                    return {
                        from: CodeMirror.Pos(start.line, line.length),
                        to: CodeMirror.Pos(lineNum, ch)
                    };
                }
            }
        }
    }
    
    return null;
});

/**
 * Fold/unfold code at cursor position
 */
CodeMirror.defineExtension("foldCode", function(pos) {
    const cm = this;
    
    // First check if we're clicking on a folded region to unfold it
    const marks = cm.findMarksAt(pos);
    for (let j = 0; j < marks.length; j++) {
        if (marks[j].__isFold) {
            marks[j].clear();
            updateFoldGutter(cm);
            return;
        }
    }
    
    // Not clicking on a fold, so try to create a new fold
    const helpers = cm.getHelpers(pos, "fold");
    
    for (let i = 0; i < helpers.length; i++) {
        const range = helpers[i](cm, pos);
        if (range) {
            // Create fold
            const widget = document.createElement("span");
            widget.className = "CodeMirror-foldmarker";
            widget.textContent = "⦚";
            widget.title = "Click to unfold";
            
            const mark = cm.markText(range.from, range.to, {
                replacedWith: widget,
                clearOnEnter: true,
                __isFold: true
            });
            
            // Use mousedown instead of click for more reliable unfold
            widget.addEventListener("mousedown", function(e) {
                e.preventDefault();
                e.stopPropagation();
                mark.clear();
                updateFoldGutter(cm);
            });
            
            updateFoldGutter(cm);
            return;
        }
    }
});

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
        foldGutter: true,
        gutters: ["CodeMirror-linenumbers", "CodeMirror-foldgutter"],
        extraKeys: {
            "Ctrl-Q": function(cm) { cm.foldCode(cm.getCursor()); },
            "Cmd-Q": function(cm) { cm.foldCode(cm.getCursor()); },
            "'{'": function(cm) {
                if (cm.somethingSelected()) {
                    const selection = cm.getSelection();
                    cm.replaceSelection('{' + selection + '}');
                } else {
                    cm.replaceSelection('{}');
                    const cursor = cm.getCursor();
                    cm.setCursor({line: cursor.line, ch: cursor.ch - 1});
                }
            },
            "'}'":  function(cm) {
                const cursor = cm.getCursor();
                const line = cm.getLine(cursor.line);
                const after = line.substring(cursor.ch);
                
                // If next char is already a closing brace, just move cursor
                if (after.startsWith('}')) {
                    cm.setCursor({line: cursor.line, ch: cursor.ch + 1});
                } else {
                    cm.replaceSelection('}');
                }
            },
            "'['": function(cm) {
                if (cm.somethingSelected()) {
                    const selection = cm.getSelection();
                    cm.replaceSelection('[' + selection + ']');
                } else {
                    cm.replaceSelection('[]');
                    const cursor = cm.getCursor();
                    cm.setCursor({line: cursor.line, ch: cursor.ch - 1});
                }
            },
            "']'":  function(cm) {
                const cursor = cm.getCursor();
                const line = cm.getLine(cursor.line);
                const after = line.substring(cursor.ch);
                
                // If next char is already a closing bracket, just move cursor
                if (after.startsWith(']')) {
                    cm.setCursor({line: cursor.line, ch: cursor.ch + 1});
                } else {
                    cm.replaceSelection(']');
                }
            },
            "'('": function(cm) {
                if (cm.somethingSelected()) {
                    const selection = cm.getSelection();
                    cm.replaceSelection('(' + selection + ')');
                } else {
                    cm.replaceSelection('()');
                    const cursor = cm.getCursor();
                    cm.setCursor({line: cursor.line, ch: cursor.ch - 1});
                }
            },
            "')'":  function(cm) {
                const cursor = cm.getCursor();
                const line = cm.getLine(cursor.line);
                const after = line.substring(cursor.ch);
                
                // If next char is already a closing paren, just move cursor
                if (after.startsWith(')')) {
                    cm.setCursor({line: cursor.line, ch: cursor.ch + 1});
                } else {
                    cm.replaceSelection(')');
                }
            },
            "'\"'": function(cm) {
                if (cm.somethingSelected()) {
                    const selection = cm.getSelection();
                    cm.replaceSelection('"' + selection + '"');
                } else {
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
                }
            },
            "\"'\"": function(cm) {
                if (cm.somethingSelected()) {
                    const selection = cm.getSelection();
                    cm.replaceSelection("'" + selection + "'");
                } else {
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
                }
            },
            "'\''": function(cm) {
                if (cm.somethingSelected()) {
                    const selection = cm.getSelection();
                    cm.replaceSelection("'" + selection + "'");
                } else {
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
    
    // Autocomplete on cursor activity and input
    let autocompleteTimeout = null;
    
    codeMirrorEditor.on('cursorActivity', function(cm) {
        // Clear any pending autocomplete
        clearTimeout(autocompleteTimeout);
        
        // Don't show autocomplete if there's already a hint widget open
        if (cm.state.completionActive) return;
        
        const cursor = cm.getCursor();
        const line = cm.getLine(cursor.line);
        const lineUpToCursor = line.substring(0, cursor.ch);
        const trimmedLine = line.trim();
        
        // First check if we're inside a plugin block
        const currentPlugin = detectCurrentPlugin(cm, cursor);
        
        if (currentPlugin) {
            // We're inside a plugin - show option autocomplete
            console.log('Inside plugin:', currentPlugin.name, 'type:', currentPlugin.type);
            
            // Check if line contains only whitespace or partial word (option name)
            if (trimmedLine === '' || /^[a-zA-Z_]+$/.test(trimmedLine)) {
                console.log('Triggering option autocomplete...');
                autocompleteTimeout = setTimeout(() => {
                    const pluginInfo = window.pluginData?.[currentPlugin.type]?.[currentPlugin.name];
                    if (pluginInfo) {
                        showOptionAutocomplete(cm, pluginInfo);
                    }
                }, 150);
            }
        } else {
            // Not inside a plugin - show plugin autocomplete
            const section = detectCurrentSection(cm, cursor);
            console.log('Autocomplete check - Section:', section, 'Line:', trimmedLine);
            
            if (!section) return;
            
            // Check if line contains only whitespace or partial word (no special chars like =>, {, etc)
            if (trimmedLine === '' || /^[a-zA-Z_]+$/.test(trimmedLine)) {
                console.log('Triggering autocomplete...');
                autocompleteTimeout = setTimeout(() => {
                    showPluginAutocomplete(cm);
                }, 150);
            }
        }
    });
    
    // Update fold gutter markers
    codeMirrorEditor.on('change', function() {
        updateFoldGutter(codeMirrorEditor);
    });
    
    // Handle gutter clicks for folding
    codeMirrorEditor.on('gutterClick', function(cm, line, gutter) {
        if (gutter === "CodeMirror-foldgutter") {
            // Check if this line is already folded by checking for fold marks on the entire line
            const lineText = cm.getLine(line);
            let foundFold = false;
            
            // Check all positions on this line for a fold mark
            for (let ch = 0; ch <= lineText.length; ch++) {
                const marks = cm.findMarksAt(CodeMirror.Pos(line, ch));
                for (let i = 0; i < marks.length; i++) {
                    if (marks[i].__isFold) {
                        marks[i].clear();
                        updateFoldGutter(cm);
                        foundFold = true;
                        break;
                    }
                }
                if (foundFold) break;
            }
            
            // If not folded, create a fold
            if (!foundFold) {
                cm.foldCode(CodeMirror.Pos(line, 0));
            }
        }
    });
    
    // Initial fold gutter update
    updateFoldGutter(codeMirrorEditor);
    
    // Initial stats update
    updateTextEditorStats();
}

/**
 * Update fold gutter markers for all foldable lines
 */
function updateFoldGutter(cm) {
    cm.clearGutter("CodeMirror-foldgutter");
    
    for (let line = 0; line < cm.lineCount(); line++) {
        const lineText = cm.getLine(line).trim();
        
        // Check if this line can be folded
        const isMainSection = /^(input|filter|output)\s*\{/.test(lineText);
        const isConditional = /^(if\s+|else\s+if\s+|else\s*)\{/.test(lineText) || 
                             /^(if|else\s+if|else)\s+.*\{/.test(lineText);
        const isPlugin = /^\w+\s*\{/.test(lineText);
        
        const canFold = isMainSection || isConditional || isPlugin;
        
        if (canFold) {
            // Check if currently folded
            const marks = cm.findMarksAt(CodeMirror.Pos(line, 0));
            let isFolded = false;
            
            for (let i = 0; i < marks.length; i++) {
                if (marks[i].__isFold) {
                    isFolded = true;
                    break;
                }
            }
            
            const marker = document.createElement("div");
            marker.className = isFolded ? "CodeMirror-foldgutter-folded" : "CodeMirror-foldgutter-open";
            cm.setGutterMarker(line, "CodeMirror-foldgutter", marker);
        }
    }
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
function findMatchingBracket(cm, pos, bracketChar, matchChar, searchForward) {
    const maxScanLines = 1000;
    
    if (searchForward) {
        // Search forward for closing bracket
        let depth = 0;
        for (let line = pos.line; line < Math.min(cm.lineCount(), pos.line + maxScanLines); line++) {
            const text = cm.getLine(line);
            const startCh = (line === pos.line) ? pos.ch : 0;
            
            for (let ch = startCh; ch < text.length; ch++) {
                if (text[ch] === bracketChar) depth++;
                if (text[ch] === matchChar) {
                    depth--;
                    if (depth === 0) {
                        return {line: line, ch: ch};
                    }
                }
            }
        }
    } else {
        // Search backward for opening bracket (mirror of forward search)
        let depth = 0;
        for (let line = pos.line; line >= Math.max(0, pos.line - maxScanLines); line--) {
            const text = cm.getLine(line);
            const startCh = (line === pos.line) ? pos.ch : text.length - 1;
            
            for (let ch = startCh; ch >= 0; ch--) {
                if (text[ch] === bracketChar) depth++;
                if (text[ch] === matchChar) {
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
