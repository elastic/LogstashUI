/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// Shared CodeMirror setup for the Utilities debuggers. Requires codemirror.min.js.
(function () {
    // Dissect and grok are whitespace sensitive, so make runs of spaces and trailing whitespace visible.
    function whitespaceToken(stream) {
        if (stream.match(/^ {2,}/) || stream.match(/^\s+$/)) {
            return 'repeated-space';
        }
        return null;
    }

    CodeMirror.defineMode('debugger-text', function () {
        return {
            token: function (stream) {
                const style = whitespaceToken(stream);
                if (style) return style;
                if (!stream.eatWhile(/[^ ]/)) stream.next();
                return null;
            }
        };
    });

    CodeMirror.defineMode('dissect', function () {
        return {
            token: function (stream) {
                if (stream.match(/^%\{[^}]*\}/)) return 'pattern-ref';
                const style = whitespaceToken(stream);
                if (style) return style;
                if (!stream.eatWhile(/[^ %]/)) stream.next();
                return null;
            }
        };
    });

    CodeMirror.defineMode('grok', function () {
        return {
            token: function (stream) {
                if (stream.match(/^%\{[^}]*\}/) || stream.match(/^\(\?<(?![=!])[^>]*>/)) return 'pattern-ref';
                if (stream.match(/^\\./)) return 'regex-escape';
                const style = whitespaceToken(stream);
                if (style) return style;
                if (!stream.eatWhile(/[^ %(\\]/)) stream.next();
                return null;
            }
        };
    });

    // Ctrl+Enter (Cmd+Enter on macOS) anywhere on the page runs the simulation. Capture phase so
    // CodeMirror sees the event as handled and does not insert a newline.
    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Enter' || !(event.ctrlKey || event.metaKey)) return;
        const form = document.querySelector('.debugger-editor')?.closest('form');
        if (!form) return;
        event.preventDefault();
        form.requestSubmit();
    }, true);

    /**
     * Replace a textarea with a CodeMirror editor that keeps the textarea in sync,
     * so HTMX forms keep posting the textarea as usual.
     *
     * @param {HTMLTextAreaElement} textarea
     * @param {{mode?: string, height?: string}} options
     * @returns {CodeMirror.Editor}
     */
    window.initDebuggerEditor = function (textarea, options = {}) {
        const editor = CodeMirror.fromTextArea(textarea, {
            mode: options.mode || 'debugger-text',
            lineNumbers: true,
            lineWrapping: true,
            viewportMargin: Infinity,
        });
        editor.setSize('100%', options.height || '14rem');

        const lines = editor.getWrapperElement().querySelector('.CodeMirror-lines');
        function update() {
            editor.save();
            if (textarea.placeholder && editor.getValue() === '') {
                lines.setAttribute('data-placeholder', textarea.placeholder);
            } else {
                lines.removeAttribute('data-placeholder');
            }
        }
        editor.on('change', update);
        update();
        return editor;
    };
})();
