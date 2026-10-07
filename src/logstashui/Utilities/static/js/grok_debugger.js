/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// Grok Debugger: CodeMirror editors plus %{ pattern-name autocomplete. Requires debugger_editor.js.
(function () {
    const patternsUrl = document.currentScript.dataset.patternsUrl;
    const ecsSelect = document.getElementById('ecsCompatibilityInput');
    initDebuggerEditor(document.getElementById('sampleDataInput'));
    const patternEditor = initDebuggerEditor(document.getElementById('grokPatternInput'), { mode: 'grok' });
    const customEditor = initDebuggerEditor(document.getElementById('customPatternsInput'), { mode: 'grok', height: '8rem' });

    let builtInPatterns = {};
    function loadPatterns() {
        fetch(`${patternsUrl}?ecs_compatibility=${encodeURIComponent(ecsSelect.value)}`)
            .then(response => response.json())
            .then(data => { builtInPatterns = data.patterns || {}; })
            .catch(error => console.error('Error loading grok patterns:', error));
    }
    ecsSelect.addEventListener('change', loadPatterns);
    loadPatterns();

    function customPatterns() {
        const patterns = {};
        for (const line of customEditor.getValue().split('\n')) {
            const match = line.match(/^\s*([^\s#]\S*)\s+(.*)$/);
            if (match) patterns[match[1]] = match[2];
        }
        return patterns;
    }

    const dropdown = document.createElement('div');
    dropdown.className = 'debugger-autocomplete hidden';
    document.body.appendChild(dropdown);
    let activeEditor = null;
    let replaceFrom = null;
    let selected = 0;
    let justPicked = false;

    function close() {
        if (!activeEditor) return;
        activeEditor.removeKeyMap(keyMap);
        activeEditor = null;
        dropdown.classList.add('hidden');
    }

    function pick(name) {
        const editor = activeEditor;
        justPicked = true;
        editor.replaceRange(name, replaceFrom, editor.getCursor());
        close();
        editor.focus();
    }

    function highlight(index) {
        const items = dropdown.children;
        if (!items.length) return;
        items[selected].classList.remove('active');
        selected = (index + items.length) % items.length;
        items[selected].classList.add('active');
        items[selected].scrollIntoView({ block: 'nearest' });
    }

    const keyMap = {
        Up: () => highlight(selected - 1),
        Down: () => highlight(selected + 1),
        Enter: () => pick(dropdown.children[selected].dataset.name),
        Tab: () => pick(dropdown.children[selected].dataset.name),
        Esc: close,
    };

    function update(editor) {
        if (justPicked) {
            justPicked = false;
            return close();
        }
        const cursor = editor.getCursor();
        const typed = editor.getLine(cursor.line).slice(0, cursor.ch).match(/%\{([A-Za-z0-9_]*)$/);
        if (!typed || editor.somethingSelected()) return close();

        const custom = customPatterns();
        const all = { ...builtInPatterns, ...custom };
        const prefix = typed[1].toUpperCase();
        const names = Object.keys(all).filter(name => name.toUpperCase().startsWith(prefix)).sort().slice(0, 200);
        if (!names.length) return close();

        dropdown.replaceChildren(...names.map(name => {
            const item = document.createElement('div');
            item.className = 'debugger-autocomplete-item';
            item.dataset.name = name;
            const title = document.createElement('span');
            title.className = 'font-mono text-sm font-semibold';
            title.textContent = name;
            item.append(title);
            if (name in custom) {
                const badge = document.createElement('span');
                badge.className = 'badge badge-xs badge-primary ml-2';
                badge.textContent = 'Custom';
                item.append(badge);
            }
            const definition = document.createElement('div');
            definition.className = 'text-xs text-base-content/60 font-mono truncate';
            definition.textContent = all[name];
            item.append(definition);
            item.addEventListener('mousedown', event => { event.preventDefault(); pick(name); });
            return item;
        }));

        if (activeEditor !== editor) {
            close();
            activeEditor = editor;
            editor.addKeyMap(keyMap);
        }
        replaceFrom = { line: cursor.line, ch: cursor.ch - typed[1].length };
        const coords = editor.cursorCoords(replaceFrom, 'page');
        dropdown.style.top = `${coords.bottom + 4}px`;
        dropdown.style.left = '0px';
        dropdown.classList.remove('hidden');
        const maxLeft = window.scrollX + document.documentElement.clientWidth - dropdown.offsetWidth - 8;
        dropdown.style.left = `${Math.max(window.scrollX + 8, Math.min(coords.left, maxLeft))}px`;
        selected = 0;
        highlight(0);
    }

    for (const editor of [patternEditor, customEditor]) {
        editor.on('cursorActivity', update);
        editor.on('blur', close);
    }
})();
