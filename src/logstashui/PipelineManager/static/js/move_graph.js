/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// ============================================
// GRAPH EDITOR MOVE MODE
// ============================================
//
// Self-contained "Move" for the graph editor. It is intentionally segmented from
// move_mode.js (the inline editor's move mode): it shares no state, classes, element
// ids or helper functions with it. The only global it exposes is `window.graphMove`.
//
// Flow:
//   1. The user clicks the `.graph-move-handle` on a node (rendered by
//      createNodeElement in pipeline_graph_editor.js).
//   2. We harvest every existing "Add Plugin" slot button in the SVG (each one already
//      carries its insertion location in data-* attributes) and draw a "Drop here" pill
//      over each valid slot.
//   3. Clicking a pill moves the component (or, for an `if` node, the whole
//      conditional with all of its branches) and re-renders the graph.
//
// Out of scope by design: moving inputs (they have no ordered slots in the graph) and
// drag-and-drop (click handle, then click target, like the inline editor).
(function () {
    'use strict';

    const SVG_NS = 'http://www.w3.org/2000/svg';
    const SECTIONS = ['input', 'filter', 'output'];

    // Slot buttons that mark an insertion position. Condition buttons share the same
    // slots, so only the plugin buttons are harvested.
    const SLOT_BUTTON_SELECTOR = [
        '.graph-add-plugin-btn',
        '.graph-add-plugin-between-btn',
        '.graph-add-plugin-after-conditional-btn',
        '.graph-add-plugin-to-branch-btn'
    ].join(',');

    const PILL_WIDTH = 120;
    const PILL_HEIGHT = 24;

    const state = {
        active: false,
        componentId: null,
        sectionType: null,   // 'filter' | 'output' - the section the component lives in
        source: null,        // location of the component when move mode started
        excludedIds: null,   // Set of ids a drop must not land inside (the moved subtree)
        overlay: null,       // <g> holding the drop-zone pills
        hiddenElements: [],  // foreignObjects hidden while moving
        visibilityObserver: null
    };

    // ------------------------------------------------------------------
    // Data model helpers (private copies; see header comment)
    // ------------------------------------------------------------------

    /**
     * List the plugin arrays of a conditional, one entry per if / else-if / else block.
     *
     * @param {Object} conditional - A component with `plugin === 'if'`.
     * @returns {Array<{blockType: string, elseIfIndex: (number|null), plugins: Array}>}
     */
    function branchArrays(conditional) {
        const config = conditional.config || {};
        const branches = [{blockType: 'if', elseIfIndex: null, plugins: config.plugins}];
        (config.else_ifs || []).forEach((elseIf, index) => {
            branches.push({blockType: 'else_if', elseIfIndex: index, plugins: elseIf.plugins});
        });
        if (config.else) {
            branches.push({blockType: 'else', elseIfIndex: null, plugins: config.else.plugins});
        }
        return branches;
    }

    /**
     * Find where a component lives, searching nested conditionals recursively.
     *
     * `type` is always the section (input / filter / output) of the top-level
     * array that contains the component, not the `type` field of nested components.
     *
     * @param {string} id - Component id.
     * @returns {(Object|null)} A location object, or null when not found.
     */
    function locate(id) {
        for (const type of SECTIONS) {
            const list = components[type] || [];
            const index = list.findIndex(c => c.id === id);
            if (index !== -1) return {type, isNested: false, index};
            for (const component of list) {
                const found = locateInConditional(component, id, type);
                if (found) return found;
            }
        }
        return null;
    }

    function locateInConditional(conditional, id, type) {
        if (conditional.plugin !== 'if' || !conditional.config) return null;
        for (const branch of branchArrays(conditional)) {
            const plugins = branch.plugins || [];
            const index = plugins.findIndex(p => p.id === id);
            if (index !== -1) {
                return {
                    type,
                    isNested: true,
                    parentId: conditional.id,
                    blockType: branch.blockType,
                    elseIfIndex: branch.elseIfIndex,
                    index
                };
            }
            for (const plugin of plugins) {
                const found = locateInConditional(plugin, id, type);
                if (found) return found;
            }
        }
        return null;
    }

    /**
     * Resolve the array a location points into.
     *
     * @param {Object} location - Location object (top-level or nested).
     * @param {boolean} [create=false] - Create missing arrays instead of returning null.
     * @returns {(Array|null)}
     */
    function arrayAt(location, create = false) {
        if (!location.isNested) {
            if (!components[location.type] && create) components[location.type] = [];
            return components[location.type] || null;
        }
        const parent = findComponentById(location.parentId);
        if (!parent || !parent.config) return null;
        const config = parent.config;

        if (location.blockType === 'if') {
            if (!config.plugins && create) config.plugins = [];
            return config.plugins || null;
        }
        if (location.blockType === 'else_if') {
            const elseIf = (config.else_ifs || [])[location.elseIfIndex];
            if (!elseIf) return null;
            if (!elseIf.plugins && create) elseIf.plugins = [];
            return elseIf.plugins || null;
        }
        if (location.blockType === 'else') {
            if (!config.else) {
                if (!create) return null;
                config.else = {plugins: []};
            }
            if (!config.else.plugins && create) config.else.plugins = [];
            return config.else.plugins || null;
        }
        return null;
    }

    function sameContainer(a, b) {
        if (a.isNested !== b.isNested) return false;
        if (!a.isNested) return a.type === b.type;
        return a.parentId === b.parentId &&
            a.blockType === b.blockType &&
            (a.elseIfIndex ?? null) === (b.elseIfIndex ?? null);
    }

    /**
     * Collect the ids of a component and everything nested inside it.
     *
     * @param {Object} component - Any component.
     * @param {Set<string>} [ids] - Accumulator.
     * @returns {Set<string>}
     */
    function collectIds(component, ids = new Set()) {
        ids.add(component.id);
        if (component.plugin === 'if' && component.config) {
            branchArrays(component).forEach(branch => {
                (branch.plugins || []).forEach(child => collectIds(child, ids));
            });
        }
        return ids;
    }

    /**
     * Node ids the graph renders for a component subtree. A conditional is drawn as one
     * node per branch (`<id>`, `<id>_elseif_<n>`, `<id>_else`, `<id>_continue`).
     */
    function renderedNodeIds(component) {
        const ids = new Set();
        const walk = item => {
            ids.add(item.id);
            if (item.plugin === 'if' && item.config) {
                (item.config.else_ifs || []).forEach((_, i) => ids.add(`${item.id}_elseif_${i}`));
                ids.add(`${item.id}_else`);
                ids.add(`${item.id}_continue`);
                branchArrays(item).forEach(branch => (branch.plugins || []).forEach(walk));
            }
        };
        walk(component);
        return ids;
    }

    // ------------------------------------------------------------------
    // Validation
    // ------------------------------------------------------------------

    /**
     * Decide whether the moving component may be dropped at a location.
     *
     * Rejects: another section, inside the moved conditional itself, ahead of the pinned
     * `elastic_integration` prefix, and positions that would not change anything.
     *
     * @param {Object} target - Slot location.
     * @returns {boolean}
     */
    function isValidDrop(target) {
        if (!target || !Number.isInteger(target.index) || target.index < 0) return false;

        let section = target.type;
        if (target.isNested) {
            if (state.excludedIds.has(target.parentId)) return false;
            const parentLocation = locate(target.parentId);
            if (!parentLocation) return false;
            section = parentLocation.type;
        }
        if (section !== state.sectionType) return false;

        const pinnedCount = window.getPinnedFilterCount?.() || 0;
        if (!target.isNested && target.type === 'filter' && target.index < pinnedCount) return false;

        // Dropping immediately before or after itself is a no-op.
        const source = state.source;
        if (sameContainer(source, target) &&
            (target.index === source.index || target.index === source.index + 1)) {
            return false;
        }
        return true;
    }

    // ------------------------------------------------------------------
    // Slot harvesting
    // ------------------------------------------------------------------

    function slotKey(location) {
        return location.isNested
            ? `n:${location.parentId}:${location.blockType}:${location.elseIfIndex ?? ''}:${location.index}`
            : `t:${location.type}:${location.index}`;
    }

    /** Translate a slot button's data-* attributes into a location object. */
    function readSlot(button) {
        const data = button.dataset;
        const index = parseInt(data.index, 10);

        if (button.classList.contains('graph-add-plugin-to-branch-btn')) {
            const elseIf = data.elseifIndex;
            return {
                isNested: true,
                parentId: data.componentId,
                blockType: data.blockType,
                elseIfIndex: (elseIf === undefined || elseIf === 'null') ? null : parseInt(elseIf, 10),
                index
            };
        }
        if (button.classList.contains('graph-add-plugin-between-btn')) {
            return {isNested: false, type: 'filter', index};
        }
        if (button.classList.contains('graph-add-plugin-after-conditional-btn')) {
            const conditionalIndex = (components.filter || []).findIndex(c => c.id === data.componentId);
            if (conditionalIndex === -1) return null;
            return {isNested: false, type: 'filter', index: conditionalIndex + 1};
        }
        if (button.classList.contains('graph-add-plugin-btn')) {
            return {isNested: false, type: data.type, index};
        }
        return null;
    }

    function centerOf(foreignObject) {
        const x = parseFloat(foreignObject.getAttribute('x'));
        const y = parseFloat(foreignObject.getAttribute('y'));
        const width = parseFloat(foreignObject.getAttribute('width'));
        const height = parseFloat(foreignObject.getAttribute('height'));
        return {x: x + width / 2, y: y + height / 2};
    }

    function hideElement(element) {
        if (element.style.display === 'none') return;
        state.hiddenElements.push({element, display: element.style.display});
        element.style.display = 'none';
    }

    function restoreHiddenElements() {
        state.hiddenElements.forEach(({element, display}) => {
            element.style.display = display;
        });
        state.hiddenElements = [];
    }

    /**
     * Build the list of drop slots (location plus position), hiding the hover "+" buttons.
     *
     * @param {SVGGElement} mainGroup - The zoomed <g> that holds all nodes.
     * @returns {Array<{location: Object, x: number, y: number}>}
     */
    function collectSlots(mainGroup) {
        const slots = new Map();

        mainGroup.querySelectorAll(SLOT_BUTTON_SELECTOR).forEach(button => {
            const foreignObject = button.closest('foreignObject');
            const location = readSlot(button);
            if (!foreignObject || !location) return;
            const key = slotKey(location);
            if (!slots.has(key)) {
                slots.set(key, {location, ...centerOf(foreignObject)});
            }
        });

        // Hide every hover "+" button so only the drop pills are interactive.
        mainGroup.querySelectorAll('button[class*="graph-add-"]').forEach(button => {
            const foreignObject = button.closest('foreignObject');
            if (foreignObject) hideElement(foreignObject);
        });

        // The graph has no "add after" control below the last output, so synthesize that
        // slot just under the content.
        const outputs = components.output || [];
        const endLocation = {isNested: false, type: 'output', index: outputs.length};
        if (outputs.length > 0 && !slots.has(slotKey(endLocation))) {
            const anchorButton = mainGroup.querySelector('.graph-add-plugin-btn[data-type="output"]');
            const anchor = anchorButton && anchorButton.closest('foreignObject');
            if (anchor) {
                const box = mainGroup.getBBox();
                slots.set(slotKey(endLocation), {
                    location: endLocation,
                    x: centerOf(anchor).x,
                    y: box.y + box.height + PILL_HEIGHT
                });
            }
        }

        return Array.from(slots.values());
    }

    // ------------------------------------------------------------------
    // Rendering
    // ------------------------------------------------------------------

    function getMainGroup() {
        const svg = document.getElementById('graphSvg');
        return svg ? svg.querySelector(':scope > g') : null;
    }

    function createDropZone(slot) {
        const group = document.createElementNS(SVG_NS, 'g');
        group.setAttribute('class', 'graph-move-drop-zone');
        group.setAttribute('data-slot', slotKey(slot.location));
        group.setAttribute('transform', `translate(${slot.x}, ${slot.y})`);

        const rect = document.createElementNS(SVG_NS, 'rect');
        rect.setAttribute('x', -PILL_WIDTH / 2);
        rect.setAttribute('y', -PILL_HEIGHT / 2);
        rect.setAttribute('width', PILL_WIDTH);
        rect.setAttribute('height', PILL_HEIGHT);
        rect.setAttribute('rx', 6);

        const label = document.createElementNS(SVG_NS, 'text');
        label.setAttribute('text-anchor', 'middle');
        label.setAttribute('dominant-baseline', 'central');
        label.textContent = 'Drop here';

        group.appendChild(rect);
        group.appendChild(label);
        group.addEventListener('click', event => {
            event.stopPropagation();
            drop(slot.location);
        });
        return group;
    }

    function clearOverlay() {
        if (state.overlay) {
            state.overlay.remove();
            state.overlay = null;
        }
        restoreHiddenElements();
        document.querySelectorAll('.graph-node-moving').forEach(node => {
            node.classList.remove('graph-node-moving');
        });
    }

    /** (Re)build drop zones and dimming for the current graph DOM. */
    function buildOverlay() {
        clearOverlay();
        const mainGroup = getMainGroup();
        const component = findComponentById(state.componentId);
        if (!mainGroup || !component) {
            cancel();
            return;
        }

        // Dim the moving node (and, for a conditional, its whole subtree).
        const dimmedIds = renderedNodeIds(component);
        mainGroup.querySelectorAll('.graph-node').forEach(node => {
            if (dimmedIds.has(node.getAttribute('data-id'))) {
                node.classList.add('graph-node-moving');
            }
        });

        const slots = collectSlots(mainGroup).filter(slot => isValidDrop(slot.location));

        const overlay = document.createElementNS(SVG_NS, 'g');
        overlay.setAttribute('class', 'graph-move-overlay');
        slots.forEach(slot => overlay.appendChild(createDropZone(slot)));
        mainGroup.appendChild(overlay);
        state.overlay = overlay;

        updateBanner(component, slots.length);
    }

    function updateBanner(component, targetCount) {
        let banner = document.getElementById('graphMoveIndicator');
        if (!banner) {
            banner = document.createElement('div');
            banner.id = 'graphMoveIndicator';
            banner.className = 'graph-move-banner';
            document.body.appendChild(banner);
        }

        const name = component.plugin === 'if' ? 'condition' : (component.plugin || 'component');
        const message = document.createElement('span');
        message.textContent = targetCount > 0
            ? `Moving ${name} - click a "Drop here" target (Esc to cancel)`
            : `Moving ${name} - no valid targets (Esc to cancel)`;

        const closeButton = document.createElement('button');
        closeButton.type = 'button';
        closeButton.className = 'graph-move-banner-close';
        closeButton.setAttribute('aria-label', 'Cancel move');
        closeButton.textContent = '\u00d7';
        closeButton.addEventListener('click', cancel);

        banner.replaceChildren(message, closeButton);
    }

    // ------------------------------------------------------------------
    // Lifecycle
    // ------------------------------------------------------------------

    /**
     * Start moving a component. Clicking the handle of the component that is already
     * being moved cancels instead.
     *
     * @param {string} componentId - Id of the node whose handle was clicked.
     */
    function activate(componentId) {
        if (state.active && state.componentId === componentId) {
            cancel();
            return;
        }

        const component = findComponentById(componentId);
        const source = component && locate(componentId);
        if (!component || !source || source.type === 'input') return;
        if (window.isPinnedPipelineComponent?.(component)) return;

        state.active = true;
        state.componentId = componentId;
        state.sectionType = source.type;
        state.source = source;
        state.excludedIds = collectIds(component);

        document.body.classList.add('graph-move-mode');
        watchGraphVisibility();
        buildOverlay();
    }

    /** Leave move mode without changing the pipeline. */
    function cancel() {
        if (state.visibilityObserver) {
            state.visibilityObserver.disconnect();
            state.visibilityObserver = null;
        }
        clearOverlay();
        const banner = document.getElementById('graphMoveIndicator');
        if (banner) banner.remove();
        document.body.classList.remove('graph-move-mode');

        state.active = false;
        state.componentId = null;
        state.sectionType = null;
        state.source = null;
        state.excludedIds = null;
    }

    /**
     * Move the component to a slot, then re-render.
     *
     * @param {Object} target - Slot location chosen by the user.
     */
    function drop(target) {
        if (!state.active || !isValidDrop(target)) return;

        const component = findComponentById(state.componentId);
        const source = locate(state.componentId);
        const sourceArray = source && arrayAt(source);
        const targetArray = arrayAt(target, true);
        if (!component || !sourceArray || !targetArray) {
            cancel();
            return;
        }

        sourceArray.splice(source.index, 1);
        let insertIndex = target.index;
        // Removing an earlier item in the same array shifts later positions up by one.
        if (sameContainer(source, target) && source.index < target.index) insertIndex--;
        targetArray.splice(insertIndex, 0, component);

        const movedId = component.id;
        cancel();

        window.enforcePinnedPipelineOrder?.();
        // Glow and pan to the moved node on the next render.
        window.newlyAddedComponentId = movedId;
        document.body.dispatchEvent(new CustomEvent('componentModified'));
        loadExistingComponents();
    }

    /** Cancel move mode if the graph editor is hidden (user switched editor mode). */
    function watchGraphVisibility() {
        const container = document.getElementById('graphModeContainer');
        if (!container || state.visibilityObserver) return;
        state.visibilityObserver = new MutationObserver(() => {
            if (container.classList.contains('hidden')) cancel();
        });
        state.visibilityObserver.observe(container, {attributes: true, attributeFilter: ['class']});
    }

    // ------------------------------------------------------------------
    // Event wiring
    // ------------------------------------------------------------------

    // Block node interactions (config modal, remove, + else) while choosing a target.
    // Capture phase so this runs before the nodes' own handlers. The move handle itself
    // and drop zones stay interactive.
    document.addEventListener('click', event => {
        if (!state.active) return;
        const node = event.target.closest && event.target.closest('#graphSvg .graph-node');
        if (node && !event.target.closest('.graph-move-handle')) {
            event.stopPropagation();
            event.preventDefault();
        }
    }, true);

    document.addEventListener('click', event => {
        const handle = event.target.closest && event.target.closest('.graph-move-handle');
        if (!handle) return;
        event.stopPropagation();
        event.preventDefault();
        const componentId = handle.getAttribute('data-graph-move-id');
        if (componentId) activate(componentId);
    });

    document.addEventListener('keydown', event => {
        if (state.active && event.key === 'Escape') cancel();
    });

    window.graphMove = {
        activate,
        cancel,
        isActive: () => state.active,
        /** Called by renderGraphEditor after every render; restores the overlay. */
        onRender: () => {
            if (state.active) buildOverlay();
        }
    };
})();
