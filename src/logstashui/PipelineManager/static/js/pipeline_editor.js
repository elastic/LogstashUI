/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// Track newly added plugin IDs for animation
let newlyAddedPluginId = null;
let pendingAnimationPluginId = null; // Plugin waiting for config modal to close

// Track selection mode state
let isSelectionMode = false;

// Note: moveMode is now defined in move_mode.js as window.moveMode

/**
 * Trigger pipeline warming / slot preallocation.
 * Used on page load/refresh, after plugin changes, and (as fallback) when the
 * simulation modal opens. Prefer a warm slot so "Run simulate" only feeds docs.
 *
 * @param {object} [opts]
 * @param {boolean} [opts.force=false] - warm even if we already have a session slot
 * @param {boolean} [opts.fromPageLoad=false] - allow embedded mode (page open path)
 * @param {boolean} [opts.soft=false] - skip if already warm (page-load / modal only)
 */
// In-flight page warm: avoid double allocate from hx-trigger=load + setTimeout backup
let _pipelineWarmInFlight = false;
// Bump on each target-switch / force warm so stale allocate responses are ignored
window.__slotWarmGeneration = 0;
// Coalesce concurrent warms (target switch + Run + soft re-warm must share one request)
window.__slotWarmPromise = null;
window.__slotWarmConn = null;
window.__slotWarmAbort = null;

/**
 * Session slot is scoped to a sim agent (connection id).
 * embedded slot-1 is NOT simulate-1 slot-1 — never cross nodes.
 */
window.clearSimulationSessionSlot = function clearSimulationSessionSlot(reason) {
    if (reason) {
        console.log('[Slot Session] clear:', reason);
    }
    window.simulationSessionSlotId = null;
    window.simulationSessionConnectionId = null;
    window.currentSlotId = null;
    if (typeof currentSlotId !== 'undefined') {
        currentSlotId = null;
    }
};

/**
 * Drop warm-cache entry(ies). Pass a connection id, or omit to clear all.
 * Used on target switch so we never Ready-chip a foreign node's slot name.
 */
window.invalidateSlotWarmCache = function invalidateSlotWarmCache(connectionId) {
    if (!window.__slotWarmCache) {
        window.__slotWarmCache = {};
        return;
    }
    if (connectionId == null || connectionId === '') {
        window.__slotWarmCache = {};
        console.log('[Slot Warm] cache cleared (all)');
        return;
    }
    const key = String(connectionId);
    if (window.__slotWarmCache[key]) {
        delete window.__slotWarmCache[key];
        console.log('[Slot Warm] cache invalidated for connection', key);
    }
};

window.rememberSimulationSessionSlot = function rememberSimulationSessionSlot(slotId, connectionId) {
    if (!slotId) return;
    const conn =
        connectionId != null && connectionId !== ''
            ? String(connectionId)
            : (typeof window.getSimConnectionId === 'function' && window.getSimConnectionId()) ||
              null;
    window.simulationSessionSlotId = String(slotId);
    window.simulationSessionConnectionId = conn != null ? String(conn) : null;
    window.__lastSimWarmConnection = window.simulationSessionConnectionId;
    window.currentSlotId = String(slotId);
    if (typeof currentSlotId !== 'undefined') {
        currentSlotId = String(slotId);
    }
    console.log(
        '[Slot Session] remember slot',
        slotId,
        'on connection',
        window.simulationSessionConnectionId
    );
};

/** Warm slot only if it belongs to the currently selected sim agent. */
window.getWarmSessionSlotForCurrentTarget = function getWarmSessionSlotForCurrentTarget() {
    const conn =
        (typeof window.getSimConnectionId === 'function' && window.getSimConnectionId()) ||
        null;
    const slotConn = window.simulationSessionConnectionId;
    const slotId =
        window.simulationSessionSlotId ||
        window.currentSlotId ||
        (typeof currentSlotId !== 'undefined' ? currentSlotId : null) ||
        null;

    if (!slotId) {
        return null;
    }

    // Hard rule: a slot id without a recorded connection is unusable when any
    // target is selected (legacy bleed embedded ↔ simulate-N).
    if (conn && !slotConn) {
        console.warn(
            '[Slot Session] rejecting slot',
            slotId,
            '— missing connection scope (will re-allocate on current target',
            conn,
            ')'
        );
        window.clearSimulationSessionSlot('missing connection scope');
        return null;
    }

    if (conn && slotConn && String(conn) !== String(slotConn)) {
        console.warn(
            '[Slot Session] rejecting slot',
            slotId,
            'from connection',
            slotConn,
            '— current target is',
            conn,
            '(cross-node reuse forbidden)'
        );
        // Do not clear the foreign slot's identity from cache of the other
        // connection; just refuse to use it here.
        return null;
    }

    return String(slotId);
};

/** True when a warm allocate is in flight for the current sim target. */
window.isSlotWarmInFlightForCurrentTarget = function isSlotWarmInFlightForCurrentTarget() {
    if (!window.__slotWarmPromise) return false;
    const conn =
        (typeof window.getSimConnectionId === 'function' && window.getSimConnectionId()) ||
        '';
    return String(window.__slotWarmConn || '') === String(conn || '');
};

// Cold-allocate UX: elapsed timer + one “still preparing” toast
let _slotWarmElapsedTimer = null;
let _slotWarmToastTimer = null;
let _slotWarmStartedAt = 0;
let _slotWarmSlowToastShown = false;
const SLOT_WARM_SLOW_TOAST_MS = 10000;
const SLOT_WARM_COLD_HINT =
    'First load of a pipeline config on an agent can take up to ~1–2 minutes (Logstash create + verify).';

function _stopSlotWarmElapsedUi() {
    if (_slotWarmElapsedTimer) {
        clearInterval(_slotWarmElapsedTimer);
        _slotWarmElapsedTimer = null;
    }
    if (_slotWarmToastTimer) {
        clearTimeout(_slotWarmToastTimer);
        _slotWarmToastTimer = null;
    }
    _slotWarmStartedAt = 0;
    _slotWarmSlowToastShown = false;
}

function _formatWarmElapsed(seconds) {
    if (seconds < 60) {
        return `${seconds}s`;
    }
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}m ${s}s`;
}

function _paintWarmElapsedLabel() {
    const statusMessage = document.getElementById('pipelineStatusMessage');
    const statusContainer = document.getElementById('pipelineLoadStatus');
    if (!statusMessage || !_slotWarmStartedAt) return;
    // Only update while chip is still in a warming-like state
    const text = statusMessage.textContent || '';
    if (
        !text.startsWith('Warming') &&
        !text.startsWith('Retrying') &&
        !text.startsWith('Preparing') &&
        text !== 'Running…'
    ) {
        return;
    }
    const elapsedSec = Math.max(0, Math.floor((Date.now() - _slotWarmStartedAt) / 1000));
    const base = text.startsWith('Retrying')
        ? 'Retrying…'
        : text.startsWith('Preparing')
          ? 'Preparing…'
          : 'Warming…';
    statusMessage.textContent = `${base} ${_formatWarmElapsed(elapsedSec)}`;
    if (statusContainer) {
        const baseTitle =
            statusContainer.dataset.warmBaseTitle ||
            'Allocating simulation slot on selected agent…';
        statusContainer.title = `${baseTitle} (${_formatWarmElapsed(elapsedSec)} elapsed). ${SLOT_WARM_COLD_HINT}`;
    }
}

function _startSlotWarmElapsedUi(baseTitle) {
    const wasRunning = !!_slotWarmElapsedTimer;
    if (!_slotWarmStartedAt) {
        _slotWarmStartedAt = Date.now();
    }
    const statusContainer = document.getElementById('pipelineLoadStatus');
    if (statusContainer) {
        statusContainer.dataset.warmBaseTitle =
            baseTitle ||
            'Allocating simulation slot on selected agent…';
    }
    // Immediate label with 0s so user sees timer right away
    _paintWarmElapsedLabel();
    if (!wasRunning) {
        _slotWarmElapsedTimer = setInterval(_paintWarmElapsedLabel, 1000);
    }
    // One toast if still warming after 10s (avoid spam on retries)
    if (!_slotWarmSlowToastShown && !_slotWarmToastTimer) {
        _slotWarmToastTimer = setTimeout(() => {
            _slotWarmToastTimer = null;
            if (!_slotWarmStartedAt) return;
            const msgEl = document.getElementById('pipelineStatusMessage');
            const t = (msgEl && msgEl.textContent) || '';
            if (
                !t.startsWith('Warming') &&
                !t.startsWith('Retrying') &&
                !t.startsWith('Preparing')
            ) {
                return;
            }
            _slotWarmSlowToastShown = true;
            const elapsedSec = Math.max(
                0,
                Math.floor((Date.now() - _slotWarmStartedAt) / 1000)
            );
            if (typeof showToast === 'function') {
                showToast(
                    `Still preparing simulation slot (${_formatWarmElapsed(elapsedSec)}). ${SLOT_WARM_COLD_HINT}`,
                    'info'
                );
            }
        }, SLOT_WARM_SLOW_TOAST_MS);
    }
}

/**
 * Enable/disable click-to-retry on the slot status chip (Failed state only).
 */
function _setSlotChipRetryable(statusContainer, enabled, errorTitle) {
    if (!statusContainer) return;
    if (enabled) {
        statusContainer.dataset.slotChipRetry = '1';
        statusContainer.setAttribute('role', 'button');
        statusContainer.setAttribute('tabindex', '0');
        statusContainer.setAttribute('aria-label', 'Slot allocate failed. Activate to retry.');
        statusContainer.classList.add(
            'cursor-pointer',
            'hover:bg-red-900/40',
            'hover:border-red-400',
            'focus:outline-none',
            'focus:ring-1',
            'focus:ring-red-400'
        );
        const base = errorTitle || 'Simulation slot allocate failed';
        statusContainer.title = `${base} — Click to retry`;
    } else {
        statusContainer.dataset.slotChipRetry = '0';
        statusContainer.removeAttribute('role');
        statusContainer.removeAttribute('tabindex');
        statusContainer.removeAttribute('aria-label');
        statusContainer.classList.remove(
            'cursor-pointer',
            'hover:bg-red-900/40',
            'hover:border-red-400',
            'focus:outline-none',
            'focus:ring-1',
            'focus:ring-red-400'
        );
    }
}

/**
 * Re-run slot allocate for the currently selected sim agent (Failed chip click).
 */
window.retryFailedSlotWarm = function retryFailedSlotWarm() {
    const chip = document.getElementById('pipelineLoadStatus');
    if (chip && chip.dataset.slotChipRetry === '1') {
        // Prevent double-fire while we transition to Warming
        _setSlotChipRetryable(chip, false);
    }
    console.log('[Slot Warm] user retry from Failed chip');
    if (typeof window.clearSimulationSessionSlot === 'function') {
        window.clearSimulationSessionSlot('user retry');
    }
    // Drop stale hover cache for current target so we don't short-circuit on a bad slot
    try {
        const conn =
            (typeof window.getSimConnectionId === 'function' && window.getSimConnectionId()) ||
            null;
        if (conn && window.__slotWarmCache) {
            delete window.__slotWarmCache[String(conn)];
        }
    } catch (_) {
        /* ignore */
    }
    if (typeof window.warmSlotForCurrentTarget === 'function') {
        window
            .warmSlotForCurrentTarget({
                showWarming: true,
                forceNew: true,
                maxAttempts: 2,
                warmLabel: 'Retrying…',
            })
            .catch((e) => {
                console.error('[Slot Warm] retry failed', e);
            });
        return;
    }
    if (typeof window.triggerPipelineWarmingAndChecking === 'function') {
        window.triggerPipelineWarmingAndChecking({
            force: true,
            fromPageLoad: true,
            useFetch: true,
        });
    }
};

// Bind once: click / keyboard activate Failed chip → retry allocate
if (!window.__slotChipRetryBound) {
    window.__slotChipRetryBound = true;
    document.addEventListener('click', function (e) {
        const chip = e.target && e.target.closest && e.target.closest('#pipelineLoadStatus');
        if (!chip || chip.dataset.slotChipRetry !== '1') return;
        e.preventDefault();
        e.stopPropagation();
        window.retryFailedSlotWarm();
    });
    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        const chip = document.getElementById('pipelineLoadStatus');
        if (!chip || chip.dataset.slotChipRetry !== '1') return;
        if (document.activeElement !== chip) return;
        e.preventDefault();
        window.retryFailedSlotWarm();
    });
}

/**
 * Compact slot chip states: unallocated | warming | ready | failed
 * Used on page load, target switch, and allocate completion.
 */
window.setPipelineSlotChip = function setPipelineSlotChip(state, detail) {
    const statusContainer = document.getElementById('pipelineLoadStatus');
    let statusIcon = document.getElementById('pipelineStatusIcon');
    const statusMessage = document.getElementById('pipelineStatusMessage');
    if (!statusContainer || !statusMessage) return;

    statusContainer.style.display = 'inline-flex';
    statusContainer.classList.remove('hidden');

    const slotId = detail && detail.slotId != null ? detail.slotId : null;
    const title = (detail && detail.title) || '';
    // Allow "warming" sub-labels (Retrying / Preparing) while keeping elapsed timer
    const warmLabel = (detail && detail.warmLabel) || 'Warming…';

    if (state === 'warming') {
        _setSlotChipRetryable(statusContainer, false);
        statusContainer.className =
            'inline-flex items-center gap-1.5 px-2 py-1 rounded-full border border-blue-600/40 bg-blue-900/20 max-w-[14rem]';
        const baseTitle =
            title ||
            'Allocating simulation slot on selected agent…';
        statusContainer.title = `${baseTitle} ${SLOT_WARM_COLD_HINT}`;
        if (statusIcon) {
            statusIcon.outerHTML = `
                <svg id="pipelineStatusIcon" class="w-3.5 h-3.5 text-blue-300 shrink-0 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>`;
        }
        statusMessage.className = 'text-xs font-medium text-blue-200 truncate';
        statusMessage.textContent = warmLabel;
        _startSlotWarmElapsedUi(baseTitle);
        return;
    }

    // Leaving warming: stop elapsed UI
    _stopSlotWarmElapsedUi();
    if (statusContainer.dataset.warmBaseTitle) {
        delete statusContainer.dataset.warmBaseTitle;
    }

    if (state === 'ready') {
        _setSlotChipRetryable(statusContainer, false);
        statusContainer.className =
            'inline-flex items-center gap-1.5 px-2 py-1 rounded-full border border-green-600 bg-green-900/30 max-w-[11rem]';
        statusContainer.title =
            title || (slotId ? `Simulation ready (slot ${slotId})` : 'Simulation ready');
        if (statusIcon) {
            statusIcon.outerHTML = `
                <svg id="pipelineStatusIcon" class="w-3.5 h-3.5 text-green-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                </svg>`;
        }
        statusMessage.className = 'text-xs font-medium text-green-300 truncate';
        statusMessage.textContent = slotId ? `Slot ${slotId}` : 'Ready';
        return;
    }

    if (state === 'failed') {
        statusContainer.className =
            'inline-flex items-center gap-1.5 px-2 py-1 rounded-full border border-red-600/50 bg-red-900/20 max-w-[12rem]';
        if (statusIcon) {
            statusIcon.outerHTML = `
                <svg id="pipelineStatusIcon" class="w-3.5 h-3.5 text-red-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
                </svg>`;
        }
        statusMessage.className = 'text-xs font-medium text-red-300 truncate';
        statusMessage.textContent = 'Failed · Retry';
        _setSlotChipRetryable(
            statusContainer,
            true,
            title || 'Simulation slot allocate failed'
        );
        return;
    }

    // default: unallocated
    _setSlotChipRetryable(statusContainer, false);
    statusContainer.className =
        'inline-flex items-center gap-1.5 px-2 py-1 rounded-full border border-gray-600 bg-gray-700/50 max-w-[11rem]';
    statusContainer.title = title || 'Simulation slot not allocated yet';
    if (statusIcon) {
        statusIcon.outerHTML = `
            <svg id="pipelineStatusIcon" class="w-3.5 h-3.5 text-gray-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>`;
    }
    statusMessage.className = 'text-xs font-medium text-gray-400 truncate';
    statusMessage.textContent = 'Unallocated';
};

/**
 * One allocate attempt (shared by warmSlotForCurrentTarget + background hover warm).
 * @param {string|null} connAtStart
 * @param {AbortController} controller
 * @param {number|null|undefined} generation - if set, abort when __slotWarmGeneration advances;
 *   pass null for background warms that must not be cancelled by main-path generation bumps.
 * @returns {Promise<{ok:boolean, slotId?:string, error?:string, aborted?:boolean, html?:string}>}
 */
async function _slotAllocateOnce(connAtStart, controller, generation) {
    const isStale = () =>
        generation != null && generation !== window.__slotWarmGeneration;

    const formData = new FormData();
    formData.append('components', JSON.stringify(components));
    formData.append('log_text', '');
    const csrf =
        document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
        document.cookie
            .split('; ')
            .find((r) => r.startsWith('csrftoken='))
            ?.split('=')[1] ||
        '';
    formData.append('csrfmiddlewaretoken', csrf);
    if (connAtStart) {
        formData.append('sim_connection_id', connAtStart);
    }
    const lsId = new URLSearchParams(window.location.search).get('ls_id');
    const esId = new URLSearchParams(window.location.search).get('es_id');
    const pipelineName = new URLSearchParams(window.location.search).get('pipeline');
    if (lsId) formData.append('ls_id', lsId);
    if (esId) formData.append('es_id', esId);
    if (pipelineName) formData.append('pipeline', pipelineName);

    try {
        const timer = setTimeout(() => controller.abort(), 130000);
        const response = await fetch('/ConnectionManager/SimulatePipeline/', {
            method: 'POST',
            body: formData,
            headers: { 'X-CSRFToken': csrf },
            signal: controller.signal,
        });
        clearTimeout(timer);
        const html = await response.text();
        if (isStale()) {
            return { ok: false, aborted: true };
        }
        const errFailed = /data-pipeline-failed="true"/.test(html);
        const slotMatch =
            html.match(/data-slot-id="(\d+)"/) || html.match(/Slot\s+(\d+)/i);
        if (slotMatch && !errFailed) {
            return { ok: true, slotId: slotMatch[1], html };
        }
        // Parse human message from error HTML if present
        let errMsg = 'Slot allocate failed';
        const msgMatch = html.match(/Error allocating slot:\s*([^<]+)/i);
        if (msgMatch) {
            errMsg = msgMatch[1].trim();
        } else if (errFailed) {
            errMsg = 'Pipeline failed to load on agent';
        } else if (!response.ok) {
            errMsg = `HTTP ${response.status}`;
        } else if (!slotMatch) {
            errMsg = 'No slot id in allocate response';
        }
        return { ok: false, error: errMsg, html, slotId: slotMatch ? slotMatch[1] : null };
    } catch (e) {
        if (e && e.name === 'AbortError') {
            return { ok: false, aborted: true, error: 'aborted' };
        }
        return { ok: false, error: String((e && e.message) || e) };
    }
}

// Background (hover) warms: per-connection, silent, do not steal the Ready chip
// unless the user has since selected that connection.
window.__bgWarmJobs = window.__bgWarmJobs || {}; // connId -> { promise, abort }
window.__slotWarmCache = window.__slotWarmCache || {}; // connId -> { slotId, at }
const SLOT_WARM_CACHE_TTL_MS = 15 * 60 * 1000;

function _cacheWarmSlot(connKey, slotId) {
    if (!connKey || !slotId) return;
    window.__slotWarmCache[connKey] = { slotId: String(slotId), at: Date.now() };
}

function _getCachedWarmSlot(connKey) {
    const entry = window.__slotWarmCache && window.__slotWarmCache[connKey];
    if (!entry || !entry.slotId) return null;
    if (Date.now() - (entry.at || 0) > SLOT_WARM_CACHE_TTL_MS) {
        delete window.__slotWarmCache[connKey];
        return null;
    }
    return entry.slotId;
}

// Ensure cache helpers exist even if this file loads before first warm
window.__slotWarmCache = window.__slotWarmCache || {};

/**
 * Silently warm a specific agent (for hover prewarm). Does not change selection
 * or the chip unless that agent is already the selected target when it finishes.
 *
 * @param {string|number} connectionId
 * @param {object} [opts]
 * @returns {Promise<string|null>}
 */
window.warmSlotForConnection = async function warmSlotForConnection(connectionId, opts) {
    const options = opts || {};
    const connKey = String(connectionId || '');
    if (!connKey) return null;

    const hasFilters = components && components.filter && components.filter.length > 0;
    if (!hasFilters) return null;

    // Join main-path warm for this connection
    if (window.__slotWarmPromise && window.__slotWarmConn === connKey) {
        return window.__slotWarmPromise;
    }
    // Join existing background job
    if (window.__bgWarmJobs[connKey] && window.__bgWarmJobs[connKey].promise) {
        return window.__bgWarmJobs[connKey].promise;
    }
    // Fresh enough cache — nothing to do
    if (_getCachedWarmSlot(connKey) && !options.force) {
        console.log('[Slot Warm] hover cache hit for connection', connKey);
        return _getCachedWarmSlot(connKey);
    }

    const ac = new AbortController();
    const run = (async function () {
        console.log('[Slot Warm] background prewarm connection', connKey);
        try {
            const result = await _slotAllocateOnce(connKey, ac, null /* no gen gate */);
            if (result.aborted) return null;
            if (result.ok && result.slotId) {
                _cacheWarmSlot(connKey, result.slotId);
                // If user selected this agent while we were warming, adopt the slot
                const selected =
                    (typeof window.getSimConnectionId === 'function' &&
                        window.getSimConnectionId()) ||
                    null;
                if (String(selected || '') === connKey) {
                    if (typeof window.rememberSimulationSessionSlot === 'function') {
                        window.rememberSimulationSessionSlot(result.slotId, connKey);
                    }
                    if (typeof window.setPipelineSlotChip === 'function') {
                        window.setPipelineSlotChip('ready', {
                            slotId: result.slotId,
                            title: `Simulation ready (slot ${result.slotId})`,
                        });
                    }
                    const resultEl = document.getElementById('slotPreallocationResult');
                    if (resultEl && result.html) {
                        resultEl.innerHTML = result.html;
                    }
                }
                return result.slotId;
            }
            console.warn('[Slot Warm] background prewarm failed', connKey, result.error);
            return null;
        } finally {
            if (window.__bgWarmJobs[connKey] && window.__bgWarmJobs[connKey].promise === run) {
                delete window.__bgWarmJobs[connKey];
            }
        }
    })();

    window.__bgWarmJobs[connKey] = { promise: run, abort: ac };
    return run;
};

/**
 * Cancel a background hover warm (e.g. user left the dropdown).
 */
window.cancelBackgroundSlotWarm = function cancelBackgroundSlotWarm(connectionId) {
    const connKey = connectionId != null ? String(connectionId) : null;
    const jobs = window.__bgWarmJobs || {};
    const keys = connKey ? [connKey] : Object.keys(jobs);
    keys.forEach((k) => {
        const job = jobs[k];
        if (job && job.abort) {
            try {
                job.abort.abort();
            } catch (_) {
                /* ignore */
            }
        }
        delete jobs[k];
    });
};

/**
 * Allocate (or re-allocate) a slot on the *currently selected* sim agent via fetch.
 * Concurrent callers for the same target share one in-flight promise (target switch
 * + Run must not start two cold allocates). Joins hover prewarm when available.
 *
 * @returns {Promise<string|null>} slot id or null
 */
window.warmSlotForCurrentTarget = async function warmSlotForCurrentTarget(opts) {
    const options = opts || {};
    const showWarming = options.showWarming !== false;
    const forceNew = !!options.forceNew;
    const maxAttempts = options.maxAttempts != null ? options.maxAttempts : 2;
    const connAtStart =
        options.connectionId != null
            ? String(options.connectionId)
            : (typeof window.getSimConnectionId === 'function' && window.getSimConnectionId()) ||
              null;
    const connKey = String(connAtStart || '');

    const hasFilters = components && components.filter && components.filter.length > 0;
    if (!hasFilters) {
        const statusBanner = document.getElementById('pipelineStatusBanner');
        if (statusBanner) statusBanner.style.display = 'none';
        return null;
    }

    // Prefer completed hover cache only when caller allows it (NOT after a
    // hard target switch — that must allocate on the new node).
    if ((!forceNew || options.preferCache) && options.preferCache !== false) {
        const cached = _getCachedWarmSlot(connKey);
        if (cached && !window.__slotWarmPromise) {
            console.log('[Slot Warm] adopting hover cache for', connKey, 'slot', cached);
            if (typeof window.rememberSimulationSessionSlot === 'function') {
                window.rememberSimulationSessionSlot(cached, connKey);
            }
            if (showWarming && typeof window.setPipelineSlotChip === 'function') {
                window.setPipelineSlotChip('ready', {
                    slotId: cached,
                    title: `Simulation ready (slot ${cached})`,
                });
            }
            // Refresh agent last_accessed / confirm pipeline (silent pure-reuse)
            window
                .warmSlotForConnection(connKey, { force: true })
                .catch(() => {});
            return cached;
        }
    }

    // Join background hover warm for this connection only when it is for the
    // same connection we are warming (never a foreign node’s job).
    if (window.__bgWarmJobs && window.__bgWarmJobs[connKey] && window.__bgWarmJobs[connKey].promise) {
        console.log('[Slot Warm] joining hover prewarm for connection', connKey);
        if (showWarming && typeof window.setPipelineSlotChip === 'function') {
            window.setPipelineSlotChip('warming', {
                title: 'Allocating slot on this agent…',
                warmLabel: 'Warming…',
            });
        }
        try {
            const slotId = await window.__bgWarmJobs[connKey].promise;
            if (slotId) {
                if (typeof window.rememberSimulationSessionSlot === 'function') {
                    window.rememberSimulationSessionSlot(slotId, connKey);
                }
                if (showWarming && typeof window.setPipelineSlotChip === 'function') {
                    window.setPipelineSlotChip('ready', {
                        slotId,
                        title: `Simulation ready (slot ${slotId})`,
                    });
                }
                return slotId;
            }
        } catch (e) {
            console.warn('[Slot Warm] hover prewarm join failed, falling through', e);
        }
    }

    // Coalesce: wait for existing warm on the same agent instead of stacking allocates
    if (
        !forceNew &&
        window.__slotWarmPromise &&
        window.__slotWarmConn === connKey
    ) {
        console.log('[Slot Warm] joining in-flight warm for connection', connKey);
        if (showWarming && typeof window.setPipelineSlotChip === 'function') {
            window.setPipelineSlotChip('warming', {
                title: 'Slot allocate already in progress on this agent…',
                warmLabel: 'Warming…',
            });
        }
        return window.__slotWarmPromise;
    }

    // Abort any warm for a different (or previous) target — never let the
    // aborted call paint Failed on the chip (new warm owns the UI).
    if (window.__slotWarmAbort) {
        try {
            window.__slotWarmAbort.abort();
        } catch (_) {
            /* ignore */
        }
        window.__slotWarmAbort = null;
    }

    // New warm generation: reset elapsed clock for a clean "Warming… 0s"
    if (forceNew) {
        _stopSlotWarmElapsedUi();
    }

    const generation = ++window.__slotWarmGeneration;
    const controller = new AbortController();
    window.__slotWarmAbort = controller;
    window.__slotWarmConn = connKey;

    const run = (async function () {
        if (showWarming && typeof window.setPipelineSlotChip === 'function') {
            window.setPipelineSlotChip('warming', {
                title: connAtStart
                    ? `Allocating slot on agent ${connAtStart}…`
                    : 'Allocating simulation slot…',
                warmLabel: options.warmLabel || 'Warming…',
            });
        }

        console.log('[Slot Warm] allocate on connection', connAtStart, 'gen', generation);

        let lastError = 'Slot allocate failed';
        for (let attempt = 1; attempt <= maxAttempts; attempt++) {
            if (generation !== window.__slotWarmGeneration) {
                return null;
            }
            // Fresh AbortController per attempt (retry after transient agent 500)
            const attemptController =
                attempt === 1 ? controller : new AbortController();
            if (attempt === 1) {
                window.__slotWarmAbort = controller;
            } else {
                window.__slotWarmAbort = attemptController;
                if (typeof window.setPipelineSlotChip === 'function') {
                    window.setPipelineSlotChip('warming', {
                        title: `Retrying slot allocate (attempt ${attempt}/${maxAttempts})…`,
                        warmLabel: 'Retrying…',
                    });
                }
                await new Promise((r) => setTimeout(r, 1500));
                if (generation !== window.__slotWarmGeneration) {
                    return null;
                }
            }

            const result = await _slotAllocateOnce(
                connAtStart,
                attemptController,
                generation
            );

            if (result.aborted || generation !== window.__slotWarmGeneration) {
                // Superseded by a newer warm — do not paint Failed
                console.log('[Slot Warm] attempt aborted/superseded gen', generation);
                return null;
            }

            if (result.ok && result.slotId) {
                const resultEl = document.getElementById('slotPreallocationResult');
                if (resultEl && result.html) {
                    resultEl.innerHTML = result.html;
                }
                _cacheWarmSlot(connKey, result.slotId);
                if (typeof window.rememberSimulationSessionSlot === 'function') {
                    window.rememberSimulationSessionSlot(result.slotId, connKey);
                }
                if (typeof window.setPipelineSlotChip === 'function') {
                    window.setPipelineSlotChip('ready', {
                        slotId: result.slotId,
                        title: `Simulation ready (slot ${result.slotId})`,
                    });
                }
                // Optional status probe — never undo Ready
                if (typeof checkPipelineLoadStatus === 'function') {
                    try {
                        await checkPipelineLoadStatus({ preserveReadyOnError: true });
                    } catch (probeErr) {
                        console.warn('[Slot Warm] status probe failed (keeping Ready)', probeErr);
                    }
                }
                return result.slotId;
            }

            lastError = result.error || lastError;
            console.warn(
                `[Slot Warm] attempt ${attempt}/${maxAttempts} failed:`,
                lastError
            );
        }

        if (generation !== window.__slotWarmGeneration) {
            return null;
        }
        if (typeof window.setPipelineSlotChip === 'function') {
            window.setPipelineSlotChip('failed', { title: lastError });
        }
        return null;
    })();

    window.__slotWarmPromise = run;
    try {
        return await run;
    } finally {
        // Only clear the shared promise if we still own this generation
        if (generation === window.__slotWarmGeneration) {
            if (window.__slotWarmPromise === run) {
                window.__slotWarmPromise = null;
                window.__slotWarmConn = null;
            }
            if (window.__slotWarmAbort === controller) {
                window.__slotWarmAbort = null;
            }
        }
        _pipelineWarmInFlight = false;
    }
};

function triggerPipelineWarmingAndChecking(opts) {
    const options = opts || {};
    const force = !!options.force;
    const fromPageLoad = !!options.fromPageLoad;
    // Soft = page-load/modal: do not re-allocate if a session slot is already ready.
    // Plugin/config edits leave soft=false so hash changes get a new warm slot.
    const soft = !!options.soft || fromPageLoad;
    // Target-switch / explicit re-warm: use fetch path with Warming chip (reliable)
    const useFetchWarm = !!options.useFetch || force;

    // Component-edit warming is host/simulate only; page-open always warms when filters exist.
    // Force always runs (e.g. sim target switch to embedded).
    if (
        !fromPageLoad &&
        !force &&
        typeof simulationMode !== 'undefined' &&
        simulationMode === 'embedded'
    ) {
        return;
    }

    // Already warm on *this* agent — skip only soft warms (not config edits / target switch)
    const existing =
        typeof window.getWarmSessionSlotForCurrentTarget === 'function'
            ? window.getWarmSessionSlotForCurrentTarget()
            : window.simulationSessionSlotId ||
              window.currentSlotId ||
              (typeof currentSlotId !== 'undefined' ? currentSlotId : null);
    if (existing && soft && !force) {
        return;
    }

    if ((_pipelineWarmInFlight || window.__slotPreallocInFlight) && soft && !force) {
        return;
    }

    // Config / target change: clear previous session slot so Run does not reuse stale state
    if (!soft || force) {
        if (typeof window.clearSimulationSessionSlot === 'function') {
            window.clearSimulationSessionSlot(force ? 'force re-warm' : 'config change');
        } else {
            window.simulationSessionSlotId = null;
            window.simulationSessionConnectionId = null;
            window.currentSlotId = null;
            if (typeof currentSlotId !== 'undefined') {
                currentSlotId = null;
            }
        }
    }

    // Check if there are any filter components
    const hasFilters = components && components.filter && components.filter.length > 0;

    if (!hasFilters) {
        // No filters, hide status banner
        const statusBanner = document.getElementById('pipelineStatusBanner');
        if (statusBanner) {
            statusBanner.style.display = 'none';
        }
        return;
    }

    // Target switch / force: fetch-based warm with visible Warming → Ready
    if (useFetchWarm && typeof window.warmSlotForCurrentTarget === 'function') {
        _pipelineWarmInFlight = true;
        window
            .warmSlotForCurrentTarget({ showWarming: true })
            .finally(function () {
                _pipelineWarmInFlight = false;
            });
        return;
    }

    // Quiet background warm (page load / soft) — leave Unallocated until Ready
    const statusBanner = document.getElementById('pipelineLoadStatus');
    if (statusBanner) {
        statusBanner.style.display = 'inline-flex';
    }

    // Trigger the slot preallocation using HTMX
    const slotPreallocation = document.getElementById('slotPreallocation');

    if (slotPreallocation && typeof htmx !== 'undefined') {
        // Use htmx.ajax to send the request with current components data
        const warmValues = {
            components: JSON.stringify(components),
            log_text: ''
        };
        if (typeof window.getSimConnectionId === 'function' && window.getSimConnectionId()) {
            warmValues.sim_connection_id = window.getSimConnectionId();
        }
        const lsIdWarm = new URLSearchParams(window.location.search).get('ls_id');
        if (lsIdWarm) {
            warmValues.ls_id = lsIdWarm;
        }
        _pipelineWarmInFlight = true;
        const ajaxResult = htmx.ajax('POST', '/ConnectionManager/SimulatePipeline/', {
            target: '#slotPreallocationResult',
            swap: 'innerHTML',
            values: warmValues,
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || ''
            },
            // Cold allocate can exceed 30s (create + verify); keep request open.
            timeout: 130000,
        });
        if (ajaxResult && typeof ajaxResult.finally === 'function') {
            ajaxResult.finally(function () {
                _pipelineWarmInFlight = false;
            });
        } else {
            _pipelineWarmInFlight = false;
        }
    } else {
        console.error('[Pipeline Warming] Cannot trigger pipeline warming - slotPreallocation element or htmx library not found');
    }
}

// Expose for page-load / modal / target-switch callers
window.triggerPipelineWarmingAndChecking = triggerPipelineWarmingAndChecking;

// Function to update the floating Simulate Subset button
function updateSimulateSubsetButton() {
    const selectedElements = document.querySelectorAll('.simulation-selected');
    const container = document.getElementById('simulateSubsetContainer');
    const countBadge = document.getElementById('selectedCount');

    if (!container || !countBadge) return;

    const count = selectedElements.length;

    if (count > 0) {
        container.classList.remove('hidden');
        countBadge.textContent = count;
    } else {
        container.classList.add('hidden');
        countBadge.textContent = '0';
    }
}

// Function to clear all selections
window.clearAllSelections = function() {
    const selectedElements = document.querySelectorAll('.simulation-selected');

    selectedElements.forEach(element => {
        const componentId = element.getAttribute('data-id');
        if (!componentId) return;

        // Find the component to determine if it's a conditional block
        const component = findComponentById(componentId);

        if (component && component.plugin === 'if') {
            // It's a conditional block
            deselectConditionalBlock(componentId);
        } else {
            // It's a regular plugin
            deselectPlugin(componentId);
        }
    });

    // Update the button visibility
    updateSimulateSubsetButton();
};

// Track if we're in subset simulation mode
let isSubsetSimulation = false;
let selectedComponentIds = [];

// Function to get all selected component IDs
function getSelectedComponentIds() {
    const selectedElements = document.querySelectorAll('.simulation-selected');
    const ids = [];

    selectedElements.forEach(element => {
        const id = element.getAttribute('data-id');
        if (id) {
            ids.push(id);
        }
    });

    return ids;
}

// Function to filter components to only include selected ones
function getSubsetComponents() {
    if (!isSubsetSimulation || selectedComponentIds.length === 0) {
        return components;
    }

    // Create a deep copy of components
    const subsetComponents = {
        input: [],
        filter: [],
        output: []
    };

    // Helper function to check if a component or any of its children are selected
    function isComponentSelected(component) {
        return selectedComponentIds.includes(component.id);
    }

    // Helper function to recursively filter conditional blocks
    function filterConditionalBlock(component) {
        if (!isComponentSelected(component)) {
            return null;
        }

        // Clone the component
        const filtered = JSON.parse(JSON.stringify(component));

        // If it's a conditional block, we include all its nested plugins
        // (they were already selected when the parent was selected)
        return filtered;
    }

    // Filter each section
    ['input', 'filter', 'output'].forEach(type => {
        if (components[type]) {
            components[type].forEach(component => {
                if (component.plugin === 'if') {
                    const filtered = filterConditionalBlock(component);
                    if (filtered) {
                        subsetComponents[type].push(filtered);
                    }
                } else if (isComponentSelected(component)) {
                    subsetComponents[type].push(JSON.parse(JSON.stringify(component)));
                }
            });
        }
    });

    return subsetComponents;
}

// Function to open simulation modal for subset
window.openSimulateSubsetModal = function() {
    // Set subset mode and collect selected IDs
    isSubsetSimulation = true;
    selectedComponentIds = getSelectedComponentIds();

    // Check for memory-intensive filter plugins
    checkMemoryIntensivePlugins();

    // Check for plugins requiring file paths
    checkFilePathRequiredPlugins();

    // Open the same simulation modal
    const modal = document.getElementById('simulationModal');
    if (modal) {
        modal.classList.remove('hidden');
    }
};

// Helper function to select a plugin for simulation
function selectPlugin(componentId) {
    const componentElement = document.querySelector(`[data-id="${componentId}"]`);
    if (!componentElement) return;

    // Add green border
    componentElement.classList.add('simulation-selected');

    // Replace play button with checkmark
    const playBtn = componentElement.querySelector('.play-btn');
    if (playBtn) {
        playBtn.innerHTML = `
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
        `;
        playBtn.classList.remove('opacity-0', 'group-hover:opacity-100');
        playBtn.classList.add('simulation-selected-checkbox');
        playBtn.title = 'Deselect from simulation';
    }

    // Update floating button
    updateSimulateSubsetButton();
}

// Helper function to deselect a plugin
function deselectPlugin(componentId) {
    const componentElement = document.querySelector(`[data-id="${componentId}"]`);
    if (!componentElement) return;

    // Remove green border
    componentElement.classList.remove('simulation-selected');

    // Restore play button
    const playBtn = componentElement.querySelector('.play-btn');
    if (playBtn) {
        playBtn.innerHTML = `
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
        `;
        playBtn.classList.add('opacity-0', 'group-hover:opacity-100');
        playBtn.classList.remove('simulation-selected-checkbox');
        playBtn.title = 'Select for simulation';
    }

    // Update floating button
    updateSimulateSubsetButton();
}

// Helper function to select an entire conditional block (if/else if/else)
function selectConditionalBlock(componentId) {
    const component = findComponentById(componentId);
    if (!component || component.plugin !== 'if') return;

    const componentElement = document.querySelector(`[data-id="${componentId}"]`);
    if (!componentElement) return;

    // Add green border to the main conditional block
    componentElement.classList.add('simulation-selected');

    // Replace play button with checkmark
    const playBtn = componentElement.querySelector('.play-btn');
    if (playBtn) {
        playBtn.innerHTML = `
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
        `;
        playBtn.classList.remove('opacity-0', 'group-hover:opacity-100');
        playBtn.classList.add('simulation-selected-checkbox');
        playBtn.title = 'Deselect from simulation';
    }

    // Helper to select a plugin and convert its play button
    const selectNestedPlugin = (plugin) => {
        const pluginElement = document.querySelector(`[data-id="${plugin.id}"]`);
        if (pluginElement) {
            pluginElement.classList.add('simulation-selected');

            // Convert play button to checkmark
            const nestedPlayBtn = pluginElement.querySelector('.play-btn');
            if (nestedPlayBtn) {
                nestedPlayBtn.innerHTML = `
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                    </svg>
                `;
                nestedPlayBtn.classList.remove('opacity-0', 'group-hover:opacity-100');
                nestedPlayBtn.classList.add('simulation-selected-checkbox');
                nestedPlayBtn.title = 'Deselect from simulation';
            }
        }
    };

    // Select all plugins in the if block
    if (component.config.plugins) {
        component.config.plugins.forEach(selectNestedPlugin);
    }

    // Select all plugins in else-if blocks
    if (component.config.else_ifs) {
        component.config.else_ifs.forEach(elseIf => {
            if (elseIf.plugins) {
                elseIf.plugins.forEach(selectNestedPlugin);
            }
        });
    }

    // Select all plugins in else block
    if (component.config.else && component.config.else.plugins) {
        component.config.else.plugins.forEach(selectNestedPlugin);
    }

    // Update floating button
    updateSimulateSubsetButton();
}

// Helper function to deselect an entire conditional block
function deselectConditionalBlock(componentId) {
    const component = findComponentById(componentId);
    if (!component || component.plugin !== 'if') return;

    const componentElement = document.querySelector(`[data-id="${componentId}"]`);
    if (!componentElement) return;

    // Remove green border from the main conditional block
    componentElement.classList.remove('simulation-selected');

    // Restore play button
    const playBtn = componentElement.querySelector('.play-btn');
    if (playBtn) {
        playBtn.innerHTML = `
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
        `;
        playBtn.classList.add('opacity-0', 'group-hover:opacity-100');
        playBtn.classList.remove('simulation-selected-checkbox');
        playBtn.title = 'Select entire condition for simulation';
    }

    // Helper to deselect a plugin and restore its play button
    const deselectNestedPlugin = (plugin) => {
        const pluginElement = document.querySelector(`[data-id="${plugin.id}"]`);
        if (pluginElement) {
            pluginElement.classList.remove('simulation-selected');

            // Restore play button
            const nestedPlayBtn = pluginElement.querySelector('.play-btn');
            if (nestedPlayBtn) {
                nestedPlayBtn.innerHTML = `
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                `;
                nestedPlayBtn.classList.add('opacity-0', 'group-hover:opacity-100');
                nestedPlayBtn.classList.remove('simulation-selected-checkbox');
                nestedPlayBtn.title = 'Select for simulation';
            }
        }
    };

    // Deselect all plugins in the if block
    if (component.config.plugins) {
        component.config.plugins.forEach(deselectNestedPlugin);
    }

    // Deselect all plugins in else-if blocks
    if (component.config.else_ifs) {
        component.config.else_ifs.forEach(elseIf => {
            if (elseIf.plugins) {
                elseIf.plugins.forEach(deselectNestedPlugin);
            }
        });
    }

    // Deselect all plugins in else block
    if (component.config.else && component.config.else.plugins) {
        component.config.else.plugins.forEach(deselectNestedPlugin);
    }

    // Update floating button
    updateSimulateSubsetButton();
}

function createInsertionPoint(type, index = 0, isConditional = false, parentId = null) {
    const insertionPoint = document.createElement('div');
    insertionPoint.className = 'insertion-point';

    const buttons = document.createElement('div');
    buttons.className = 'insertion-buttons';

    // Always show Add Plugin button
    const addPluginBtn = document.createElement('button');
    addPluginBtn.className = 'insertion-button add-plugin';
    addPluginBtn.innerHTML = `
        <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
        </svg>
        Add Plugin
    `;
    addPluginBtn.onclick = (e) => {
        e.stopPropagation();
        // Handle adding a new plugin at this position
        showPluginModal(type, index, isConditional, parentId);
    };

    buttons.appendChild(addPluginBtn);

    // Show Add Condition button for filter and output sections, or inside conditionals
    if ((type === 'filter' || type === 'output' || isConditional) && !parentId) {
        const addConditionBtn = document.createElement('button');
        addConditionBtn.className = 'insertion-button add-condition';
        addConditionBtn.innerHTML = `
            <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
            </svg>
            Add Condition
        `;
        addConditionBtn.onclick = (e) => {
            e.stopPropagation();
            // Handle adding a new condition at this position
            addConditionAtPosition(type, index, isConditional, parentId);
        };
        buttons.appendChild(addConditionBtn);
    }

    insertionPoint.appendChild(buttons);
    return insertionPoint;
}

function setupInsertionPoints(container, type, isConditional = false, parentId = null) {
    // Get only the draggable components (not empty messages)
    const components = Array.from(container.children).filter(el => el.classList.contains('draggable-item'));

    if (components.length > 0) {
        // Add insertion point at the beginning
        container.insertBefore(createInsertionPoint(type, 0, isConditional, parentId), container.firstChild);

        // Add insertion points between components (but NOT after the last one)
        components.forEach((component, index) => {
            // Only add insertion point if it's not after the last component
            if (index < components.length - 1) {
                const insertionPoint = createInsertionPoint(type, index + 1, isConditional, parentId);
                container.insertBefore(insertionPoint, component.nextSibling);
            }
        });

        // Add a final insertion point at the end that's always visible
        const finalInsertionPoint = createInsertionPoint(type, components.length, isConditional, parentId);
        finalInsertionPoint.classList.add('always-visible');
        container.appendChild(finalInsertionPoint);
    } else {
        // Empty section - add a single always-visible insertion point
        const emptyInsertionPoint = createInsertionPoint(type, 0, isConditional, parentId);
        emptyInsertionPoint.classList.add('always-visible');
        container.appendChild(emptyInsertionPoint);
    }
}

// Setup insertion points for conditional blocks (if, else-if, else)
function setupInsertionPointsForConditional(container, type, conditionalId, blockType, elseIfIndex) {
    // Create a special insertion point creator for conditionals
    const createConditionalInsertionPoint = (index, alwaysVisible = false) => {
        const insertionPoint = document.createElement('div');
        insertionPoint.className = 'insertion-point';
        if (alwaysVisible) {
            insertionPoint.classList.add('always-visible');
        }

        const buttons = document.createElement('div');
        buttons.className = 'insertion-buttons';

        // Add Plugin button
        const addPluginBtn = document.createElement('button');
        addPluginBtn.className = 'insertion-button add-plugin';
        addPluginBtn.innerHTML = `
            <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
            </svg>
            Add Plugin
        `;
        addPluginBtn.onclick = (e) => {
            e.stopPropagation();
            showPluginModalForConditional(type, conditionalId, blockType, index, elseIfIndex);
        };
        buttons.appendChild(addPluginBtn);

        // Add Condition button (for filter and output types)
        if (type === 'filter' || type === 'output') {
            const addConditionBtn = document.createElement('button');
            addConditionBtn.className = 'insertion-button add-condition';
            addConditionBtn.innerHTML = `
                <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                </svg>
                Add Condition
            `;
            addConditionBtn.onclick = (e) => {
                e.stopPropagation();
                addConditionToConditional(type, conditionalId, blockType, index, elseIfIndex);
            };
            buttons.appendChild(addConditionBtn);
        }

        insertionPoint.appendChild(buttons);
        return insertionPoint;
    };

    // Get only the draggable plugin elements (not empty messages or other elements)
    const pluginElements = Array.from(container.children).filter(el => el.classList.contains('draggable-item'));

    if (pluginElements.length > 0) {
        // Add insertion point at the beginning
        container.insertBefore(createConditionalInsertionPoint(0), container.firstChild);

        // Add insertion points between components
        pluginElements.forEach((plugin, index) => {
            const insertionPoint = createConditionalInsertionPoint(index + 1);
            container.insertBefore(insertionPoint, plugin.nextSibling);
        });
    } else {
        // Empty conditional block - add an always-visible insertion point
        const emptyInsertionPoint = createConditionalInsertionPoint(0, true);
        container.appendChild(emptyInsertionPoint);
    }
}

/**
 * Update the blocking problems indicator based on current validation state
 */
function updateBlockingProblemsIndicator() {
    const indicator = document.getElementById('blockingProblemsIndicator');
    const content = document.getElementById('blockingProblemsContent');
    
    if (!indicator || !content) return;
    
    const problems = [];
    
    // Check for empty conditionals
    const emptyConditionals = [];
    ['input', 'filter', 'output'].forEach(type => {
        if (components[type] && Array.isArray(components[type])) {
            components[type].forEach(component => {
                if (component.plugin === 'if') {
                    const emptyBlocks = getEmptyBlocksList(component);
                    if (emptyBlocks.length > 0) {
                        emptyConditionals.push({
                            type: type,
                            blocks: emptyBlocks
                        });
                    }
                }
            });
        }
    });
    
    // Check for missing required fields
    const missingFields = [];
    function checkComponentFields(component) {
        if (component.plugin === 'comment' || component.plugin === 'if') {
            if (component.plugin === 'if') {
                // Check nested plugins in conditionals
                if (component.config.plugins) {
                    component.config.plugins.forEach(checkComponentFields);
                }
                if (component.config.else_ifs) {
                    component.config.else_ifs.forEach(elseIf => {
                        if (elseIf.plugins) elseIf.plugins.forEach(checkComponentFields);
                    });
                }
                if (component.config.else && component.config.else.plugins) {
                    component.config.else.plugins.forEach(checkComponentFields);
                }
            }
            return;
        }
        
        const validation = validateRequiredFields(component);
        if (!validation.isValid) {
            missingFields.push({
                plugin: component.plugin,
                fields: validation.missingFields
            });
        }
    }
    
    ['input', 'filter', 'output'].forEach(type => {
        if (components[type] && Array.isArray(components[type])) {
            components[type].forEach(checkComponentFields);
        }
    });
    
    // Build problems list
    if (emptyConditionals.length > 0) {
        problems.push('<div class="font-medium text-red-400">Empty Conditional Blocks:</div>');
        emptyConditionals.forEach(item => {
            problems.push(`<div class="ml-2">• ${item.type}: ${item.blocks.join(', ')}</div>`);
        });
    }
    
    if (missingFields.length > 0) {
        if (problems.length > 0) problems.push('<div class="mt-2"></div>');
        problems.push('<div class="font-medium text-red-400">Missing Required Fields:</div>');
        missingFields.forEach(item => {
            problems.push(`<div class="ml-2">• ${item.plugin}: ${item.fields.join(', ')}</div>`);
        });
    }
    
    // Count total problem items
    const totalProblems = emptyConditionals.length + missingFields.length;
    
    // Update the count display
    const countElement = document.getElementById('blockingProblemsCount');
    if (countElement) {
        countElement.textContent = totalProblems;
    }
    
    // Update capsule styling based on problem count
    const capsule = document.getElementById('blockingProblemsCapsule');
    const iconContainer = document.getElementById('blockingProblemsIconContainer');
    
    if (totalProblems > 0) {
        // Red styling when there are problems
        if (capsule) {
            capsule.className = 'flex items-center gap-3 px-4 py-2 bg-red-900/30 rounded-lg border border-red-600/50 hover:bg-red-900/40 transition-colors';
        }
        if (iconContainer) {
            iconContainer.className = 'flex items-center justify-center w-8 h-8 bg-red-600/20 rounded-lg';
            const svg = iconContainer.querySelector('svg');
            if (svg) svg.className = 'w-5 h-5 text-red-400';
        }
        // Update text colors
        const labelElements = capsule?.querySelectorAll('.text-gray-400');
        labelElements?.forEach(el => {
            el.classList.remove('text-gray-400');
            el.classList.add('text-red-300');
        });
        const countEl = document.getElementById('blockingProblemsCount');
        if (countEl) {
            countEl.classList.remove('text-white');
            countEl.classList.add('text-red-400');
        }
    } else {
        // Normal gray styling when no problems
        if (capsule) {
            capsule.className = 'flex items-center gap-3 px-4 py-2 bg-gray-700/50 rounded-lg border border-gray-600/50 hover:bg-gray-700 transition-colors';
        }
        if (iconContainer) {
            iconContainer.className = 'flex items-center justify-center w-8 h-8 bg-gray-600/20 rounded-lg';
            const svg = iconContainer.querySelector('svg');
            if (svg) svg.className = 'w-5 h-5 text-gray-400';
        }
        // Update text colors back to gray
        const labelElements = capsule?.querySelectorAll('.text-red-300');
        labelElements?.forEach(el => {
            el.classList.remove('text-red-300');
            el.classList.add('text-gray-400');
        });
        const countEl = document.getElementById('blockingProblemsCount');
        if (countEl) {
            countEl.classList.remove('text-red-400');
            countEl.classList.add('text-white');
        }
    }
    
    // Update indicator visibility and content
    content.innerHTML = problems.join('');
    indicator.classList.remove('hidden');
}

function loadExistingComponents() {
    // Check if we're in simulation mode before clearing
    const wasInSimulationMode = document.querySelector('.simulation-executed-badge') !== null;
    const simulationNodes = wasInSimulationMode && window.simulationData ? window.simulationData.nodes : null;
    const originalEventData = wasInSimulationMode && window.simulationResultsCache ?
        Object.values(window.simulationResultsCache)[0]?.originalEvent : null;

    // Clears all existing components first
    const componentTypes = ['input', 'filter', 'output'];

    // Clear containers
    componentTypes.forEach(type => {
        const container = document.getElementById(`${type}Components`);
        if (container) {
            // Remove all existing components but keep the empty message and insertion points
            const emptyMessage = container.querySelector('p');
            container.innerHTML = '';

            // Add empty section class if no components
            if (!components[type] || components[type].length === 0) {
                container.classList.add('empty-section');
                if (emptyMessage && emptyMessage.textContent.includes('No ')) {
                    container.appendChild(emptyMessage);
                }
            } else {
                container.classList.remove('empty-section');
            }
        }
    });

    // Add all components
    Object.entries(components).forEach(([type, componentList]) => {
        const container = document.getElementById(`${type}Components`);
        if (!container) return;

        // Remove 'No components' message if it exists
        const emptyMessage = container.querySelector('p');
        if (emptyMessage && emptyMessage.textContent.includes('No ')) {
            container.removeChild(emptyMessage);
        }

        // Add each component to the UI
        componentList.forEach((component, index) => {
            const componentEl = createComponentElement(component);
            container.appendChild(componentEl);
        });

        // Setup insertion points for this container
        setupInsertionPoints(container, type);
    });

    // Apply animation and focus to newly added plugin (only if not pending config modal)
    // Don't clear newlyAddedPluginId if there's a pending animation
    if (newlyAddedPluginId && !pendingAnimationPluginId) {
        highlightAndFocusNewPlugin(newlyAddedPluginId);
        newlyAddedPluginId = null; // Reset after use
    } else if (pendingAnimationPluginId && !newlyAddedPluginId) {
        // If we only have a pending ID, preserve it
        newlyAddedPluginId = pendingAnimationPluginId;
    }
    
    // Update blocking problems indicator
    updateBlockingProblemsIndicator();

    // Restore simulation data if we were in simulation mode
    if (wasInSimulationMode && simulationNodes && typeof markExecutedPlugins === 'function') {
        markExecutedPlugins(simulationNodes, originalEventData);
    }
    
    // If in graph mode, re-render the graph
    if (window.currentEditorMode === 'graph' && typeof renderGraphEditor === 'function') {
        // Capture newly added plugin ID for animation
        if (newlyAddedPluginId && typeof window.newlyAddedComponentId !== 'undefined') {
            window.newlyAddedComponentId = newlyAddedPluginId;
        }
        renderGraphEditor();
    }
    
    // Update stats strip with current plugin counts
    if (typeof updateStatsStrip === 'function') {
        updateStatsStrip();
    }
}

// Function to trigger animation for pending plugin (called after config modal closes)
window.triggerPendingAnimation = function () {
    if (pendingAnimationPluginId) {
        highlightAndFocusNewPlugin(pendingAnimationPluginId);
        pendingAnimationPluginId = null;
        newlyAddedPluginId = null;
    }
}

// Helper function to check if a field is sensitive (password/api_key)
function isSensitiveField(fieldName) {
    const lowerFieldName = fieldName.toLowerCase();
    return lowerFieldName.includes('password') ||
           lowerFieldName.includes('api_key') ||
           lowerFieldName.includes('apikey') ||
           lowerFieldName === 'token' ||
           lowerFieldName.includes('secret');
}

/**
 * Check if a conditional component has any empty blocks (if/else-if/else)
 * @param {Object} component - The conditional component to check
 * @returns {boolean} - True if any block is empty or only contains comments
 */
function checkConditionalForEmptyBlocks(component) {
    if (component.plugin !== 'if') {
        return false;
    }

    // Check if main if block is empty or only has comments
    if (isPluginsArrayEmpty(component.config.plugins)) {
        return true;
    }

    // Check else-if blocks
    if (component.config.else_ifs && Array.isArray(component.config.else_ifs)) {
        for (const elseIf of component.config.else_ifs) {
            if (isPluginsArrayEmpty(elseIf.plugins)) {
                return true;
            }
        }
    }

    // Check else block
    if (component.config.else) {
        if (isPluginsArrayEmpty(component.config.else.plugins)) {
            return true;
        }
    }

    return false;
}

/**
 * Helper to check if a plugins array is effectively empty (no plugins or only comments)
 * @param {Array} plugins - Array of plugins to check
 * @returns {boolean} - True if empty or only contains comments
 */
function isPluginsArrayEmpty(plugins) {
    if (!plugins || plugins.length === 0) {
        return true;
    }
    // Check if all plugins are comments
    return plugins.every(plugin => plugin.plugin === 'comment');
}

/**
 * Get list of empty blocks in a conditional component
 * @param {Object} component - The conditional component to check
 * @returns {Array<string>} - List of empty block names
 */
function getEmptyBlocksList(component) {
    const emptyBlocks = [];
    
    if (component.plugin !== 'if') {
        return emptyBlocks;
    }

    // Check if main if block is empty or only has comments
    if (isPluginsArrayEmpty(component.config.plugins)) {
        emptyBlocks.push('if');
    }

    // Check else-if blocks
    if (component.config.else_ifs && Array.isArray(component.config.else_ifs)) {
        component.config.else_ifs.forEach((elseIf, index) => {
            if (isPluginsArrayEmpty(elseIf.plugins)) {
                emptyBlocks.push(`else-if #${index + 1}`);
            }
        });
    }

    // Check else block
    if (component.config.else) {
        if (isPluginsArrayEmpty(component.config.else.plugins)) {
            emptyBlocks.push('else');
        }
    }

    return emptyBlocks;
}

/**
 * Validate that all required fields for a plugin are filled in.
 * @param {Object} component - The component to validate
 * @returns {Object} - { isValid: boolean, missingFields: Array<string> }
 */
function validateRequiredFields(component) {
    const result = {
        isValid: true,
        missingFields: []
    };

    // Skip validation for comment plugins and conditionals
    if (component.plugin === 'comment' || component.plugin === 'if') {
        return result;
    }

    // Get plugin definition from pluginData (check both global scope and window)
    const pluginDataSource = typeof pluginData !== 'undefined' ? pluginData : window.pluginData;
    const pluginDef = pluginDataSource?.[component.type]?.[component.plugin];

    if (!pluginDataSource) {
        console.error('[Validation] pluginData not available yet');
        return result;
    }

    if (!pluginDef) {
        console.error(`[Validation] No plugin definition for ${component.plugin}`);
        return result;
    }

    // The field definitions are in 'options', not 'fields'
    if (!pluginDef.options) {
        console.error(`[Validation] No options property for ${component.plugin}`);
        return result;
    }

    // Check each field in the plugin definition
    for (const [fieldName, fieldDef] of Object.entries(pluginDef.options)) {
        // Check if field is required
        if (fieldDef.required === 'Yes') {
            const fieldValue = component.config[fieldName];

            // Check if field is missing or empty
            if (fieldValue === undefined || fieldValue === null || fieldValue === '') {
                result.isValid = false;
                result.missingFields.push(fieldName);
            }
            // Check for empty arrays
            else if (Array.isArray(fieldValue) && fieldValue.length === 0) {
                result.isValid = false;
                result.missingFields.push(fieldName);
            }
            // Check for empty objects
            else if (typeof fieldValue === 'object' && !Array.isArray(fieldValue) && Object.keys(fieldValue).length === 0) {
                result.isValid = false;
                result.missingFields.push(fieldName);
            }
        }
    }

    return result;
}

// Helper function to format config values for display
function formatConfigValue(value, key) {
    // Helper to clean up string values
    const cleanString = (str) => {
        // Remove surrounding quotes if they exist
        if (typeof str === 'string') {
            return str.replace(/^"|"$/g, '');
        }
        return String(str);
    };

    // Check if this is a sensitive field - redact the value
    if (isSensitiveField(key)) {
        const valueStr = String(value);
        if (valueStr && valueStr.length > 0) {
            return '••••••••';
        }
        return '';
    }

    // Handle codec specially FIRST - it's a nested object like {"rubydebug": {}}
    if (key === 'codec' && typeof value === 'object' && value !== null && !Array.isArray(value)) {
        const codecNames = Object.keys(value);
        if (codecNames.length > 0) {
            const codecName = codecNames[0];
            const codecConfig = value[codecName];

            // If codec has no config, just show the name
            if (!codecConfig || Object.keys(codecConfig).length === 0) {
                return `"${codecName}"`;
            }

            // If codec has config, show name with config summary
            const configCount = Object.keys(codecConfig).length;
            return `"${codecName}" (${configCount} setting${configCount > 1 ? 's' : ''})`;
        }
        return '{}';
    }

    // Handle arrays/lists
    if (Array.isArray(value)) {
        if (value.length === 0) {
            return '[]';
        }

        // Check if this is an array of objects (array_of_hashes)
        const firstItem = value[0];
        if (typeof firstItem === 'object' && firstItem !== null && !Array.isArray(firstItem)) {
            // This is an array of hashes - show count instead of content
            return `[${value.length} ${value.length === 1 ? 'entry' : 'entries'}]`;
        }

        // Format as: "item1", "item2", "item3"
        const formattedItems = value.map(item => {
            return `"${cleanString(item)}"`;
        });
        const joined = formattedItems.join(', ');
        // Truncate if too long
        if (joined.length > 50) {
            return joined.substring(0, 50) + '...';
        }
        return joined;
    }

    // Handle objects/hashes/dictionaries
    if (typeof value === 'object' && value !== null) {
        const entries = Object.entries(value);
        if (entries.length === 0) {
            return '{}';
        }
        // Format as: "key1" => "value1", "key2" => "value2"
        const formattedPairs = entries.map(([k, v]) => {
            // Skip nested objects - just show the key
            if (typeof v === 'object' && v !== null) {
                return `"${cleanString(k)}" => {...}`;
            }
            return `"${cleanString(k)}" => "${cleanString(v)}"`;
        });
        const joined = formattedPairs.join(', ');
        // Truncate if too long
        if (joined.length > 50) {
            return joined.substring(0, 50) + '...';
        }
        return joined;
    }

    // Handle strings and other primitives
    const cleanedValue = cleanString(value);
    if (cleanedValue.length > 30) {
        return cleanedValue.substring(0, 30) + '...';
    }
    return cleanedValue;
}

function createComponentElement(component, depth = 0, isConditional = false, parentId = null) {
// Check if this is a conditional block
    if (component.plugin === 'if') {
        return createConditionalBlockElement(component, depth);
    }

// Check if this is a comment plugin - apply special styling
    const isComment = component.plugin === 'comment';

// Alternate background colors based on depth
    const bgColor = isComment ? 'bg-gray-800' : (depth % 2 === 0 ? 'bg-gray-700' : 'bg-gray-600');
    const el = document.createElement('div');
    const commentClass = isComment ? 'comment-plugin' : '';
    el.className = `${bgColor} p-3 rounded mb-2 relative group draggable-item ${commentClass}`;
    el.dataset.id = component.id;

// Get plugin info for description and type
    const pluginInfo = pluginData[component.type]?.[component.plugin] || {};
    const typeColor = getPluginTypeColor(component.type);

// Create a summary of the configuration
    let configSummary = '';
    if (Object.keys(component.config).length > 0) {
        const configItems = [];
        for (const [key, value] of Object.entries(component.config)) {
            if (value !== undefined && value !== null && value !== '' && key !== 'plugins' && key !== 'else_ifs' && key !== 'else' && key !== 'condition') {
                // Special handling for comment plugin - show full text with newlines (no field name prefix)
                if (isComment && (key === 'string' || key === 'message' || key === 'text')) {
                    const fullText = String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                    configItems.push(`<div class="text-sm text-gray-300 whitespace-pre-wrap font-mono mt-2">${fullText}</div>`);
                    continue;
                }

                let displayValue = formatConfigValue(value, key);

                // Add eye icon for sensitive fields
                if (isSensitiveField(key)) {
                    const actualValue = String(value).length > 30 ? String(value).substring(0, 30) + '...' : String(value);
                    const escapedActualValue = actualValue.replace(/'/g, "\\'").replace(/"/g, '&quot;');
                    configItems.push(`
                        <span class="text-xs bg-gray-800/50 px-2 py-0.5 rounded inline-flex items-center gap-1">
                            ${key}: <span class="sensitive-value" data-actual="${escapedActualValue}">${escapeHtml(displayValue)}</span>
                            <button type="button"
                                    class="text-gray-400 hover:text-gray-200 inline-flex items-center"
                                    onclick="toggleSensitiveValue(this, event)"
                                    title="Show/Hide">
                                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                                </svg>
                            </button>
                        </span>
                    `);
                } else {
                    configItems.push(`<span class="text-xs bg-gray-800/50 px-2 py-0.5 rounded">${key}: ${escapeHtml(displayValue)}</span>`);
                }
            }
        }
        if (configItems.length > 0) {
            configSummary = `<div class="mt-2 flex flex-wrap gap-1">${configItems.join('')}</div>`;
        }
    }

    // Show image for input, filter, and output plugins
    const imageHtml = `<img src="/static/images/${component.plugin}.png"
                alt="${component.plugin} icon"
                class="w-5 h-5 mr-2 object-contain flex-shrink-0"
                onerror="this.style.display='none';">`;

    // Validate required fields
    const validation = validateRequiredFields(component);

    el.innerHTML = `
<button class="move-handle" data-component-id="${component.id}" title="Click to move this component">
  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8h16M4 16h16" />
  </svg>
</button>
<div class="flex justify-between items-start">
  <div class="flex-1">
    <div class="flex items-center ${isComment ? 'flex-wrap' : ''}">
      ${imageHtml}
      <span class="font-medium text-white">${component.plugin}</span>
      <span class="ml-2 px-1.5 py-0.5 text-xs rounded-full ${typeColor}">
        ${component.type.charAt(0).toUpperCase() + component.type.slice(1)}
      </span>
      ${pluginInfo.deprecated ?
        '<span class="ml-1 px-1.5 py-0.5 text-xs rounded-full bg-red-600/50 text-red-100">Deprecated</span>' : ''}
      ${isComment && pluginInfo.description ?
        `<span class="ml-2 text-xs text-gray-400 italic">${pluginInfo.description}</span>` : ''}
    </div>
    ${!isComment && pluginInfo.description ?
        `<p class="text-xs text-gray-400 mt-1 line-clamp-2">${pluginInfo.description}</p>` : ''}
    ${configSummary}
  </div>
  <div class="flex space-x-1 ml-2">
    ${component.type === 'filter' && !isComment ? `
    <!-- Play button / Checkbox (toggles based on selection state) -->
    <button class="play-btn text-gray-400 hover:text-green-400 opacity-0 group-hover:opacity-100 transition-opacity"
            data-component-id="${component.id}"
            title="Select for simulation">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    </button>
    ` : ''}

    <button class="config-btn text-gray-400 hover:text-white opacity-0 group-hover:opacity-100 transition-opacity"
            data-component-id="${component.id}"
            title="Configure">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    </button>
    <button class="text-gray-400 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
            onclick="event.stopPropagation(); removeComponent('${component.id}')"
            title="Remove">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
      </svg>
    </button>
  </div>
</div>
`;

    // Add warning badge and text if required fields are missing
    if (!validation.isValid) {
        const badge = document.createElement('div');
        badge.className = 'required-fields-badge';
        badge.innerHTML = '!';
        badge.title = `MISSING REQUIRED FIELDS\n${validation.missingFields.join(', ')}`;
        badge.style.cssText = `
            position: absolute;
            bottom: 8px;
            right: 8px;
            width: 20px;
            height: 20px;
            background: #dc2626;
            color: white;
            border-radius: 3px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 13px;
            font-weight: 700;
            font-family: system-ui, -apple-system, sans-serif;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
            z-index: 10;
            animation: badgePop 0.3s ease-out;
        `;
        el.appendChild(badge);

        // Add text indicator below the plugin
        const warningText = document.createElement('div');
        warningText.className = 'required-fields-warning';
        warningText.innerHTML = `
            <div style="margin-top: 8px; padding: 6px 8px; background: rgba(220, 38, 38, 0.1); border-left: 3px solid #dc2626; border-radius: 4px;">
                <div style="font-size: 11px; font-weight: 600; color: #fca5a5; margin-bottom: 2px;">Missing Required Fields</div>
                <div style="font-size: 10px; color: #fecaca;">${validation.missingFields.join(', ')}</div>
            </div>
        `;
        el.appendChild(warningText);
    }

    return el;
}

// Function to highlight and focus on a newly added plugin
function highlightAndFocusNewPlugin(pluginId) {
    // Use setTimeout to ensure DOM is fully rendered
    setTimeout(() => {
        const pluginElement = document.querySelector(`[data-id="${pluginId}"]`);
        if (pluginElement) {
            // Add the animation class
            pluginElement.classList.add('newly-added');

            // Scroll to the element smoothly
            pluginElement.scrollIntoView({
                behavior: 'smooth',
                block: 'center'
            });

            // Remove the class after animation completes
            setTimeout(() => {
                pluginElement.classList.remove('newly-added');
            }, 2000);
        }
    }, 100);
}

function createConditionalBlockElement(component, depth = 0) {
// Alternate background colors based on depth
    const bgColor = depth % 2 === 0 ? 'bg-gray-700' : 'bg-gray-600';
    const el = document.createElement('div');
    el.className = `${bgColor} p-3 rounded mb-2 relative group draggable-item`;
    el.dataset.id = component.id;

    const typeColor = getPluginTypeColor(component.type);

// Create the container with border
    const container = document.createElement('div');
    container.className = 'border-l-4 border-yellow-500 pl-3';

// Create move handle for conditional block
    const moveHandle = document.createElement('button');
    moveHandle.className = 'move-handle';
    moveHandle.setAttribute('data-component-id', component.id);
    moveHandle.title = 'Click to move this condition';
    moveHandle.innerHTML = `
  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8h16M4 16h16" />
  </svg>
`;
    el.appendChild(moveHandle);

// Create header section
    const header = document.createElement('div');
    header.className = 'flex justify-between items-start mb-2';

    const headerLeft = document.createElement('div');
    headerLeft.className = 'flex-1';
    headerLeft.innerHTML = `
<div class="flex items-center">
  <button class="collapse-toggle mr-2 text-yellow-300 hover:text-yellow-400 transition-colors" data-component-id="${component.id}" title="Collapse/Expand">
    <svg class="w-4 h-4 transform transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
    </svg>
  </button>
  <span class="font-medium text-yellow-300">if</span>
  <div class="flex items-center ml-2 group/condition">
    <span class="text-xs text-gray-400 condition-text">${component.config.condition || ''}</span>
    <!-- Expression Editor Button - Temporarily Commented Out
    <button class="ml-1 text-gray-500 hover:text-blue-400 opacity-0 group-hover:opacity-100 transition-opacity expression-editor-btn"
            data-component-id="${component.id}"
            title="Expression Editor">
      <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    </button>
    -->
    <button class="ml-2 px-2 py-0.5 text-xs font-medium text-blue-400 hover:text-blue-300 hover:bg-blue-900/30 rounded transition-colors flex items-center gap-1 edit-condition"
            data-component-id="${component.id}">
      <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
      </svg>
      <span>Edit</span>
    </button>
  </div>
  <span class="ml-2 px-1.5 py-0.5 text-xs rounded-full ${typeColor}">
    ${component.type.charAt(0).toUpperCase() + component.type.slice(1)}
  </span>
</div>
`;
    header.appendChild(headerLeft);

// Create button container
    const buttonContainer = document.createElement('div');
    buttonContainer.className = 'flex space-x-2 ml-2 opacity-0 group-hover:opacity-100 transition-opacity';

// Add play button for filter conditionals (before else-if button)
    if (component.type === 'filter') {
        const playBtn = document.createElement('button');
        playBtn.className = 'play-btn text-gray-400 hover:text-green-400';
        playBtn.setAttribute('data-component-id', component.id);
        playBtn.setAttribute('data-is-conditional', 'true');
        playBtn.title = 'Select entire condition for simulation';
        playBtn.innerHTML = `
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
        `;
        buttonContainer.appendChild(playBtn);
    }

// Add else-if button with text
    const addElseIfBtn = document.createElement('button');
    addElseIfBtn.className = 'px-2 py-1 text-xs bg-yellow-600/80 text-white rounded hover:bg-yellow-600';
    addElseIfBtn.textContent = '+ else if';
    addElseIfBtn.setAttribute('data-action', 'add-elseif');
    addElseIfBtn.setAttribute('data-component-id', component.id);
    buttonContainer.appendChild(addElseIfBtn);

// Add else button (only if else block doesn't exist)
    if (!component.config.else) {
        const addElseBtn = document.createElement('button');
        addElseBtn.className = 'px-2 py-1 text-xs bg-yellow-600/80 text-white rounded hover:bg-yellow-600';
        addElseBtn.textContent = '+ else';
        addElseBtn.setAttribute('data-action', 'add-else');
        addElseBtn.setAttribute('data-component-id', component.id);
        buttonContainer.appendChild(addElseBtn);
    }

// Add delete button
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'text-gray-400 hover:text-red-400';
    deleteBtn.title = 'Remove';
    deleteBtn.innerHTML = `
<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
</svg>
`;
    deleteBtn.onclick = (e) => {
        e.stopPropagation();
        removeComponent(component.id);
    };
    buttonContainer.appendChild(deleteBtn);

    header.appendChild(buttonContainer);
    container.appendChild(header);

// Create collapsible content wrapper
    const collapsibleContent = document.createElement('div');
    collapsibleContent.className = 'conditional-content';
    collapsibleContent.dataset.componentId = component.id;

// Create if block plugins container with add button
    const ifPluginsContainer = document.createElement('div');
    ifPluginsContainer.className = 'ml-4 space-y-2 component-container';
    ifPluginsContainer.dataset.conditionalId = component.id;
    ifPluginsContainer.dataset.blockType = 'if';

    const isIfBlockEmpty = !component.config.plugins || component.config.plugins.length === 0;
    
    if (component.config.plugins && component.config.plugins.length > 0) {
        component.config.plugins.forEach(plugin => {
            const pluginEl = createComponentElement(plugin, depth + 1, true, component.id);
            ifPluginsContainer.appendChild(pluginEl);
        });
    } else {
        const emptyMsg = document.createElement('p');
        emptyMsg.className = 'text-gray-500 text-sm py-2';
        emptyMsg.textContent = 'No plugins in if block';
        ifPluginsContainer.appendChild(emptyMsg);
    }

    // Setup insertion points for this conditional block
    setupInsertionPointsForConditional(ifPluginsContainer, component.type, component.id, 'if', null);

    collapsibleContent.appendChild(ifPluginsContainer);

// Render else-if blocks
    if (component.config.else_ifs && component.config.else_ifs.length > 0) {
        component.config.else_ifs.forEach((elseIf, index) => {
            const elseIfIndex = index; // Capture the index in a local constant
            const elseIfBlock = document.createElement('div');
            elseIfBlock.className = 'mt-2';

            const conditionId = `condition-${component.id}-${elseIfIndex}`;
            const elseIfHeader = document.createElement('div');
            elseIfHeader.className = 'flex items-center justify-between group-elseif-condition';
            elseIfHeader.innerHTML = `
    <div class="flex items-center">
      <span class="font-medium text-yellow-300">else if</span>
      <div class="flex items-center ml-2">
        <span id="${conditionId}" class="text-xs text-gray-400 condition-text">${elseIf.condition || ''}</span>
        <!-- Expression Editor Button - Temporarily Commented Out
        <button class="ml-1 text-gray-500 hover:text-blue-400 opacity-0 group-hover:opacity-100 transition-opacity expression-editor-btn"
                data-component-id="${component.id}"
                data-elseif-index="${elseIfIndex}"
                title="Expression Editor">
          <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        </button>
        -->
        <button class="ml-2 px-2 py-0.5 text-xs font-medium text-blue-400 hover:text-blue-300 hover:bg-blue-900/30 rounded transition-colors flex items-center gap-1 edit-elseif-condition"
                data-component-id="${component.id}"
                data-elseif-index="${elseIfIndex}"
                data-condition-id="${conditionId}">
          <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
          </svg>
          <span>Edit</span>
        </button>
      </div>
    </div>
    <button class="text-gray-400 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity delete-elseif-btn"
            data-component-id="${component.id}"
            data-elseif-index="${elseIfIndex}"
            title="Remove else-if block">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
      </svg>
    </button>
  `;
            elseIfBlock.appendChild(elseIfHeader);

            const elseIfPluginsContainer = document.createElement('div');
            elseIfPluginsContainer.className = 'ml-4 space-y-2 mt-2 component-container';
            elseIfPluginsContainer.dataset.conditionalId = component.id;
            elseIfPluginsContainer.dataset.blockType = 'else_if';
            elseIfPluginsContainer.dataset.elseIfIndex = elseIfIndex;

            const isElseIfBlockEmpty = !elseIf.plugins || elseIf.plugins.length === 0;
            
            if (elseIf.plugins && elseIf.plugins.length > 0) {
                elseIf.plugins.forEach(plugin => {
                    const pluginEl = createComponentElement(plugin, depth + 1, true, component.id);
                    elseIfPluginsContainer.appendChild(pluginEl);
                });
            } else {
                const emptyMsg = document.createElement('p');
                emptyMsg.className = 'text-gray-500 text-sm py-2';
                emptyMsg.textContent = 'No plugins in else-if block';
                elseIfPluginsContainer.appendChild(emptyMsg);
            }

            // Setup insertion points for this else-if block
            setupInsertionPointsForConditional(elseIfPluginsContainer, component.type, component.id, 'else_if', elseIfIndex);

            elseIfBlock.appendChild(elseIfPluginsContainer);
            collapsibleContent.appendChild(elseIfBlock);
        });
    }

// Render else block (if it exists)
    if (component.config.else) {
        const elseBlock = document.createElement('div');
        elseBlock.className = 'mt-2';

        const elseHeader = document.createElement('div');
        elseHeader.className = 'flex items-center justify-between group';
        elseHeader.innerHTML = `
    <span class="font-medium text-yellow-300">else</span>
    <button class="text-gray-400 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity delete-else-btn"
            data-component-id="${component.id}"
            title="Remove else block">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
      </svg>
    </button>
  `;
        elseBlock.appendChild(elseHeader);

        const elsePluginsContainer = document.createElement('div');
        elsePluginsContainer.className = 'ml-4 space-y-2 mt-2 component-container';
        elsePluginsContainer.dataset.conditionalId = component.id;
        elsePluginsContainer.dataset.blockType = 'else';

        const isElseBlockEmpty = !component.config.else.plugins || component.config.else.plugins.length === 0;
        
        if (component.config.else.plugins && component.config.else.plugins.length > 0) {
            component.config.else.plugins.forEach(plugin => {
                const pluginEl = createComponentElement(plugin, depth + 1, true, component.id);
                elsePluginsContainer.appendChild(pluginEl);
            });
        } else {
            const emptyMsg = document.createElement('p');
            emptyMsg.className = 'text-gray-500 text-sm py-2';
            emptyMsg.textContent = 'No plugins in else block';
            elsePluginsContainer.appendChild(emptyMsg);
        }

        // Setup insertion points for this else block
        setupInsertionPointsForConditional(elsePluginsContainer, component.type, component.id, 'else', null);

        elseBlock.appendChild(elsePluginsContainer);
        collapsibleContent.appendChild(elseBlock);
    }

    container.appendChild(collapsibleContent);
    el.appendChild(container);
    
    // Add warning badge and text if any block in this conditional is empty
    const emptyBlocksList = getEmptyBlocksList(component);
    if (emptyBlocksList.length > 0) {
        const badge = document.createElement('div');
        badge.className = 'empty-conditional-badge';
        badge.innerHTML = '!';
        badge.title = `EMPTY CONDITIONAL BLOCKS\n${emptyBlocksList.join(', ')}`;
        badge.style.cssText = `
            position: absolute;
            bottom: 8px;
            right: 8px;
            width: 20px;
            height: 20px;
            background: #dc2626;
            color: white;
            border-radius: 3px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 13px;
            font-weight: 700;
            font-family: system-ui, -apple-system, sans-serif;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
            z-index: 10;
            animation: badgePop 0.3s ease-out;
        `;
        el.appendChild(badge);

        // Add text indicator below the conditional
        const warningText = document.createElement('div');
        warningText.className = 'empty-conditional-warning';
        warningText.innerHTML = `
            <div style="margin-top: 8px; padding: 6px 8px; background: rgba(220, 38, 38, 0.1); border-left: 3px solid #dc2626; border-radius: 4px;">
                <div style="font-size: 11px; font-weight: 600; color: #fca5a5; margin-bottom: 2px;">Empty Conditional Blocks</div>
                <div style="font-size: 10px; color: #fecaca;">${emptyBlocksList.join(', ')}</div>
            </div>
        `;
        el.appendChild(warningText);
    }
    
    return el;
}

// Helper function to get color based on plugin type
function getPluginTypeColor(type) {
    const colors = {
        input: 'bg-blue-900/50 text-blue-300',
        filter: 'bg-purple-900/50 text-purple-300',
        output: 'bg-green-900/50 text-green-300',
        codec: 'bg-yellow-900/50 text-yellow-300'
    };
    return colors[type] || 'bg-gray-700 text-gray-300';
}

// Function to update a component and refresh the UI
window.updateComponent = function (updatedComponent) {
    // Helper function to recursively update in nested conditionals
    function updateInConditional(component) {
        if (!component || component.plugin !== 'if' || !component.config) {
            return false;
        }

        // Check in if block
        if (component.config.plugins) {
            const index = component.config.plugins.findIndex(c => c.id === updatedComponent.id);
            if (index !== -1) {
                component.config.plugins[index] = {...updatedComponent};
                return true;
            }
            // Recursively search in nested conditionals
            for (const plugin of component.config.plugins) {
                if (updateInConditional(plugin)) {
                    return true;
                }
            }
        }

        // Check in else-if blocks
        if (component.config.else_ifs) {
            for (const elseIf of component.config.else_ifs) {
                if (elseIf.plugins) {
                    const index = elseIf.plugins.findIndex(c => c.id === updatedComponent.id);
                    if (index !== -1) {
                        elseIf.plugins[index] = {...updatedComponent};
                        return true;
                    }
                    // Recursively search in nested conditionals
                    for (const plugin of elseIf.plugins) {
                        if (updateInConditional(plugin)) {
                            return true;
                        }
                    }
                }
            }
        }

        // Check in else block
        if (component.config.else && component.config.else.plugins) {
            const index = component.config.else.plugins.findIndex(c => c.id === updatedComponent.id);
            if (index !== -1) {
                component.config.else.plugins[index] = {...updatedComponent};
                return true;
            }
            // Recursively search in nested conditionals
            for (const plugin of component.config.else.plugins) {
                if (updateInConditional(plugin)) {
                    return true;
                }
            }
        }

        return false;
    }

    // First, try to update at top-level
    for (const type in components) {
        const index = components[type].findIndex(c => c.id === updatedComponent.id);
        if (index !== -1) {
            // Update the component
            components[type][index] = {...updatedComponent};
            // Refresh the UI
            loadExistingComponents();
            return true;
        }
    }

    // If not found at top level, search recursively in nested conditionals
    for (const type in components) {
        for (const component of components[type]) {
            if (updateInConditional(component)) {
                // Refresh the UI
                loadExistingComponents();
                return true;
            }
        }
    }

    return false;
};

// Function to handle condition editing
function handleEditCondition(componentId) {
    const component = findComponentById(componentId);
    if (!component) return;

    const conditionElement = document.querySelector(`[data-id="${componentId}"] .condition-text`);
    if (!conditionElement) return;

    const currentCondition = component.config.condition || '';
    const input = document.createElement('input');
    input.type = 'text';
    input.value = currentCondition;
    input.className = 'text-xs text-white bg-gray-700 px-1 py-0.5 rounded w-full';

    // Save on Enter or blur, cancel on Escape
    const saveCondition = () => {
        const newCondition = input.value.trim();
        component.config.condition = newCondition;
        conditionElement.textContent = newCondition || ' '; // Keep space to maintain height
        updateComponent(component);
    };

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            input.blur();
        } else if (e.key === 'Escape') {
            conditionElement.textContent = currentCondition || ' ';
        }
    });

    input.addEventListener('blur', () => {
        saveCondition();
    });

    conditionElement.textContent = '';
    conditionElement.appendChild(input);
    input.focus();
}

// Function to handle else-if condition editing
function handleEditElseIfCondition(componentId, elseIfIndex, conditionId) {
    const component = findComponentById(componentId);
    if (!component || !component.config.else_ifs || !component.config.else_ifs[elseIfIndex]) return;

    const conditionText = component.config.else_ifs[elseIfIndex].condition || '';
    const conditionElement = document.getElementById(conditionId);

    if (!conditionElement) {
        console.error('Could not find condition element with ID:', conditionId);
        return;
    }

    const input = document.createElement('input');
    input.type = 'text';
    input.value = conditionText;
    input.className = 'text-xs text-white bg-gray-700 px-1 py-0.5 rounded w-full';

    // Save on Enter or blur, cancel on Escape
    const saveCondition = () => {
        const newCondition = input.value.trim();
        component.config.else_ifs[elseIfIndex].condition = newCondition;
        conditionElement.textContent = newCondition || ' '; // Keep space to maintain height
        updateComponent(component);
    };

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            input.blur();
        } else if (e.key === 'Escape') {
            conditionElement.textContent = conditionText || ' ';
            input.remove();
            conditionElement.textContent = conditionText || ' ';
        }
    });

    input.addEventListener('blur', () => {
        saveCondition();
    });

    conditionElement.textContent = '';
    conditionElement.appendChild(input);
    input.focus();
}

// Initialize the pipeline editor
// Function to handle adding a condition at a specific position
function addConditionAtPosition(type, index, isConditional = false, parentId = null) {
    // Create a new condition component
    const conditionId = `condition-${Date.now()}`;
    const newCondition = {
        id: conditionId,
        type: type,
        plugin: 'if',
        config: {
            condition: '[message]',
            plugins: []
        }
    };

    // Track the newly added condition for animation
    newlyAddedPluginId = conditionId;

    // Add the condition to the appropriate location
    if (isConditional && parentId) {
        // Find the parent component and add the condition to its plugins
        const parentComponent = findComponentById(parentId);
        if (parentComponent) {
            if (!parentComponent.config.plugins) {
                parentComponent.config.plugins = [];
            }
            parentComponent.config.plugins.splice(index, 0, newCondition);
        }
    } else {
        // Add to the main components array
        if (!components[type]) {
            components[type] = [];
        }
        components[type].splice(index, 0, newCondition);
    }

    // Dispatch event to mark UI as changed (before loadExistingComponents clears the ID)
    document.body.dispatchEvent(new CustomEvent('componentAdded'));
    
    // Refresh the UI
    loadExistingComponents();
}

// Function to show the plugin modal at a specific position
function showPluginModal(type, index, isConditional = false, parentId = null) {
    // Store the position information in the modal
    const modal = document.getElementById('pluginModal');
    modal.dataset.type = type;
    modal.dataset.index = index;
    modal.dataset.isConditional = isConditional;
    modal.dataset.parentId = parentId || '';

    // Show the modal with proper rendering (just like Add Input/Filter/Output buttons)
    PluginModal.show(type);
}

// Function to show plugin modal for conditional blocks with insertion at specific position
function showPluginModalForConditional(type, conditionalId, blockType, index, elseIfIndex) {
    const modal = document.getElementById('pluginModal');

    // Create context for conditional insertion point
    const context = {
        conditionalInsertion: true,
        conditionalId: conditionalId,
        blockType: blockType,
        elseIfIndex: elseIfIndex,
        index: index,
        type: type
    };

    modal.dataset.context = JSON.stringify(context);
    PluginModal.show(type);
}

// Function to add a condition inside a conditional block at a specific position
function addConditionToConditional(type, conditionalId, blockType, index, elseIfIndex) {
    const parentComponent = findComponentById(conditionalId);
    if (!parentComponent) return;

    // Create a new nested condition
    const newCondition = {
        id: `condition-${Date.now()}`,
        type: type,
        plugin: 'if',
        config: {
            condition: '[message]',
            plugins: [],
            else_ifs: [],
            else: null
        }
    };

    // Track the newly added condition for animation
    newlyAddedPluginId = newCondition.id;

    // Determine which plugin array to insert into
    let targetPlugins;
    switch (blockType) {
        case 'if':
            if (!parentComponent.config.plugins) parentComponent.config.plugins = [];
            targetPlugins = parentComponent.config.plugins;
            break;
        case 'else_if':
            if (!parentComponent.config.else_ifs || !parentComponent.config.else_ifs[elseIfIndex]) return;
            if (!parentComponent.config.else_ifs[elseIfIndex].plugins) {
                parentComponent.config.else_ifs[elseIfIndex].plugins = [];
            }
            targetPlugins = parentComponent.config.else_ifs[elseIfIndex].plugins;
            break;
        case 'else':
            if (!parentComponent.config.else) parentComponent.config.else = {plugins: []};
            if (!parentComponent.config.else.plugins) parentComponent.config.else.plugins = [];
            targetPlugins = parentComponent.config.else.plugins;
            break;
        default:
            return;
    }

    // Insert the condition at the specified index
    targetPlugins.splice(index, 0, newCondition);

    // Refresh the UI
    loadExistingComponents();
}

document.addEventListener('DOMContentLoaded', function () {
    // Add click handlers for the insertion buttons
    document.addEventListener('click', function (e) {
        // Handle add plugin button clicks
        if (e.target.closest('.add-plugin-btn')) {
            const type = e.target.closest('.add-plugin-btn').dataset.type;
            showPluginModal(type, components[type] ? components[type].length : 0);
        }
    });

    // Update the existing plugin modal handler to use the position information
    document.querySelectorAll('.plugin-option').forEach(option => {
        option.addEventListener('click', function () {
            const modal = document.getElementById('pluginModal');
            const type = modal.dataset.type;
            const index = parseInt(modal.dataset.index || '0');
            const isConditional = modal.dataset.isConditional === 'true';
            const parentId = modal.dataset.parentId || null;

            const pluginType = this.dataset.pluginType;

            // Create the new plugin
            const newPlugin = {
                id: `plugin-${Date.now()}`,
                type: type,
                plugin: pluginType,
                config: {}
            };

            // Track the newly added plugin for animation
            newlyAddedPluginId = newPlugin.id;

            // Add the plugin to the appropriate location
            if (isConditional && parentId) {
                // Find the parent component and add the plugin to its plugins
                const parentComponent = findComponentById(parentId);
                if (parentComponent) {
                    if (!parentComponent.config.plugins) {
                        parentComponent.config.plugins = [];
                    }
                    parentComponent.config.plugins.splice(index, 0, newPlugin);
                }
            } else {
                // Add to the main components array
                if (!components[type]) {
                    components[type] = [];
                }
                components[type].splice(index, 0, newPlugin);
            }

            // Hide the modal and refresh the UI
            modal.classList.add('hidden');
            loadExistingComponents();
        });
    });
    // Add event listener for edit condition buttons
    document.addEventListener('click', function (event) {
        // Handle if condition edit
        let editBtn = event.target.closest('.edit-condition') ||
            (event.target.closest('svg') && event.target.closest('svg').parentElement.closest('.edit-condition'));

        if (editBtn) {
            event.preventDefault();
            event.stopPropagation();
            const componentId = editBtn.getAttribute('data-component-id');
            if (componentId) {
                handleEditCondition(componentId);
            }
            return;
        }

        // Handle else-if condition edit
        editBtn = event.target.closest('.edit-elseif-condition') ||
            (event.target.closest('svg') && event.target.closest('svg').parentElement.closest('.edit-elseif-condition'));

        if (editBtn) {
            event.preventDefault();
            event.stopPropagation();
            const componentId = editBtn.getAttribute('data-component-id');
            const elseIfIndex = parseInt(editBtn.getAttribute('data-elseif-index'), 10);
            const conditionId = editBtn.getAttribute('data-condition-id');
            if (componentId && !isNaN(elseIfIndex) && conditionId) {
                handleEditElseIfCondition(componentId, elseIfIndex, conditionId);
            }
        }
    });

    if (typeof components !== 'undefined') {
        loadExistingComponents();
    }

    // Initialize PluginConfigModal with plugin data
    if (typeof window.PluginConfigModal !== 'undefined' && typeof pluginData !== 'undefined') {
        window.PluginConfigModal.init(pluginData);

        // Pass keystore keys if available
        const keystoreKeysEl = document.getElementById('keystore-keys');
        if (keystoreKeysEl) {
            const keystoreKeys = JSON.parse(keystoreKeysEl.textContent);
            if (keystoreKeys.length > 0) {
                window.PluginConfigModal.setKeystoreKeys(keystoreKeys);
            }
        }

        // Add click handler for config buttons
        document.addEventListener('click', function (event) {
            const configBtn = event.target.closest('.config-btn');
            if (configBtn) {
                const componentId = configBtn.closest('[data-component-id]').getAttribute('data-component-id');
                const component = findComponentById(componentId);
                if (component) {
                    event.preventDefault();
                    window.PluginConfigModal.show(component);
                }
            }
        });

        // Add click handler for play buttons
        document.addEventListener('click', function (event) {
            const playBtn = event.target.closest('.play-btn');
            if (playBtn) {
                event.preventDefault();
                event.stopPropagation();

                const componentId = playBtn.getAttribute('data-component-id');
                const isConditional = playBtn.getAttribute('data-is-conditional') === 'true';
                const componentElement = document.querySelector(`[data-id="${componentId}"]`);

                if (!componentElement) return;

                // Check if already selected
                const isSelected = componentElement.classList.contains('simulation-selected');

                if (isSelected) {
                    // Deselect
                    if (isConditional) {
                        deselectConditionalBlock(componentId);
                    } else {
                        deselectPlugin(componentId);
                    }
                } else {
                    // Select
                    if (isConditional) {
                        selectConditionalBlock(componentId);
                    } else {
                        selectPlugin(componentId);
                    }
                }
            }
        });
    }

    // Add global event listener for conditional block buttons
    document.addEventListener('click', function (event) {
        const button = event.target.closest('[data-action]');
        if (!button) return;

        const action = button.getAttribute('data-action');
        const componentId = button.getAttribute('data-component-id');

        if (!componentId) return;

        event.stopPropagation();
        event.preventDefault();

        if (action === 'add-elseif') {
            addElseIfToConditional(componentId);
        } else if (action === 'add-else') {
            addElseToConditional(componentId);
        }
    });

    // Add event listener for delete else-if buttons
    document.addEventListener('click', function (event) {
        const deleteBtn = event.target.closest('.delete-elseif-btn');
        if (deleteBtn) {
            event.stopPropagation();
            event.preventDefault();

            const componentId = deleteBtn.getAttribute('data-component-id');
            const elseIfIndex = parseInt(deleteBtn.getAttribute('data-elseif-index'), 10);

            if (componentId && !isNaN(elseIfIndex)) {
                deleteElseIfBlock(componentId, elseIfIndex);
            }
        }
    });

    // Add event listener for delete else button
    document.addEventListener('click', function (event) {
        const deleteBtn = event.target.closest('.delete-else-btn');
        if (deleteBtn) {
            event.stopPropagation();
            event.preventDefault();

            const componentId = deleteBtn.getAttribute('data-component-id');

            if (componentId) {
                deleteElseBlock(componentId);
            }
        }
    });
});

// Helper function to find component by ID (recursive for nested conditionals)
function findComponentById(id) {
    if (!id || !components) return null;

    // Recursive search function
    function searchInComponent(component) {
        if (component.id === id) {
            return component;
        }

        // If this is a conditional, search inside it
        if (component.plugin === 'if' && component.config) {
            // Search in if block
            if (component.config.plugins) {
                for (const plugin of component.config.plugins) {
                    const found = searchInComponent(plugin);
                    if (found) return found;
                }
            }

            // Search in else-if blocks
            if (component.config.else_ifs) {
                for (const elseIf of component.config.else_ifs) {
                    if (elseIf.plugins) {
                        for (const plugin of elseIf.plugins) {
                            const found = searchInComponent(plugin);
                            if (found) return found;
                        }
                    }
                }
            }

            // Search in else block
            if (component.config.else && component.config.else.plugins) {
                for (const plugin of component.config.else.plugins) {
                    const found = searchInComponent(plugin);
                    if (found) return found;
                }
            }
        }

        return null;
    }

    // Search through all top-level components
    for (const type in components) {
        for (const component of components[type]) {
            const found = searchInComponent(component);
            if (found) return found;
        }
    }

    return null;
}

async function removeComponent(componentId) {
    const confirmed = await ConfirmationModal.show(
        'Are you sure you want to remove this component?',
        'Remove Component',
        'Remove'
    );
    
    if (!confirmed) {
        return;
    }

    // Helper function to recursively remove from nested conditionals
    function removeFromConditional(component) {
        if (!component || component.plugin !== 'if' || !component.config) {
            return false;
        }

        // Check in if block
        if (component.config.plugins) {
            const index = component.config.plugins.findIndex(c => c.id === componentId);
            if (index > -1) {
                component.config.plugins.splice(index, 1);
                return true;
            }
            // Recursively search in nested conditionals
            for (const plugin of component.config.plugins) {
                if (removeFromConditional(plugin)) {
                    return true;
                }
            }
        }

        // Check in else-if blocks
        if (component.config.else_ifs) {
            for (const elseIf of component.config.else_ifs) {
                if (elseIf.plugins) {
                    const index = elseIf.plugins.findIndex(c => c.id === componentId);
                    if (index > -1) {
                        elseIf.plugins.splice(index, 1);
                        return true;
                    }
                    // Recursively search in nested conditionals
                    for (const plugin of elseIf.plugins) {
                        if (removeFromConditional(plugin)) {
                            return true;
                        }
                    }
                }
            }
        }

        // Check in else block
        if (component.config.else && component.config.else.plugins) {
            const index = component.config.else.plugins.findIndex(c => c.id === componentId);
            if (index > -1) {
                component.config.else.plugins.splice(index, 1);
                return true;
            }
            // Recursively search in nested conditionals
            for (const plugin of component.config.else.plugins) {
                if (removeFromConditional(plugin)) {
                    return true;
                }
            }
        }

        return false;
    }

    // First, try to remove from top-level components
    let removed = false;
    for (const type in components) {
        const index = components[type].findIndex(c => c.id === componentId);
        if (index > -1) {
            components[type].splice(index, 1);
            removed = true;
            break;
        }
    }

    // If not found at top level, search recursively in nested conditionals
    if (!removed) {
        for (const type in components) {
            for (const component of components[type]) {
                if (removeFromConditional(component)) {
                    removed = true;
                    break;
                }
            }
            if (removed) break;
        }
    }

    // Refresh the entire UI to reflect the changes
    if (removed) {
        loadExistingComponents();
        // Trigger pipeline warming and checking after removal
        triggerPipelineWarmingAndChecking();
        // Dispatch event to mark UI as changed
        document.body.dispatchEvent(new CustomEvent('componentDeleted'));
    }
}

async function addElseIfToConditional(componentId) {
// Find the conditional component
    const component = findComponentById(componentId);
    if (!component || component.plugin !== 'if') {
        console.error('Component not found or not a conditional:', componentId);
        return;
    }

// Prompt for condition using custom modal
    const condition = await ConfirmationModal.prompt(
        'Enter the else-if condition:',
        '[message]',
        'Add Else-If Condition',
        'e.g., [message] == "error"'
    );
    if (!condition) {
        return;
    }

// Initialize else_ifs array if it doesn't exist
    if (!component.config.else_ifs) {
        component.config.else_ifs = [];
    }

// Add new else-if block with empty plugins array
    const elseIfBlock = {
        condition: condition,
        plugins: []
    };

    component.config.else_ifs.push(elseIfBlock);
    
    // Set the newly added else_if as the component to highlight in graph mode
    const newElseIfIndex = component.config.else_ifs.length - 1;
    window.newlyAddedComponentId = component.id + '_elseif_' + newElseIfIndex;

// Refresh the UI to show the new empty else-if block
    loadExistingComponents();

// Dispatch event to mark UI as changed
    document.body.dispatchEvent(new CustomEvent('componentAdded'));

// Trigger pipeline warming and checking
    triggerPipelineWarmingAndChecking();
}

function addPluginToConditional(componentId, blockType, elseIfIndex = null, index = null) {
    // console.log(`addPluginToConditional called - componentId: ${componentId}, blockType: ${blockType}, elseIfIndex: ${elseIfIndex}, index: ${index}`);

// Find the conditional component
    const component = findComponentById(componentId);
    if (!component || component.plugin !== 'if') {
        console.error('Component not found or not a conditional:', componentId);
        return;
    }

// Store the context for the plugin selection callback
    const context = {componentId, blockType, elseIfIndex, index};

// Store the context in the modal's dataset for later use
    const modal = document.getElementById('pluginModal');

// Clean up any existing context first
    if (modal.dataset.context) {
        delete modal.dataset.context;
    }

    modal.dataset.context = JSON.stringify(context);

// Show the plugin modal for the appropriate plugin type
    PluginModal.show(component.type || 'output');

// Add a one-time event listener for plugin selection
    const handlePluginSelect = function (event) {
        const {pluginName, pluginType} = event.detail;

// Make sure we have a valid context
        if (!modal.dataset.context) {
            console.error('No context found for plugin selection');
            return;
        }

        const context = JSON.parse(modal.dataset.context);

// Find the component again to ensure we have the latest state
        const component = findComponentById(context.componentId);
        if (!component) return;

// Determine the target plugin list based on block type
        let targetPlugins;
        switch (context.blockType) {
            case 'if':
                if (!component.config.plugins) component.config.plugins = [];
                targetPlugins = component.config.plugins;
                break;
            case 'else_if':
                if (!component.config.else_ifs || !component.config.else_ifs[context.elseIfIndex]) {
                    console.error('Invalid else-if index or else_ifs not found');
                    return;
                }
                if (!component.config.else_ifs[context.elseIfIndex].plugins) {
                    component.config.else_ifs[context.elseIfIndex].plugins = [];
                }
                targetPlugins = component.config.else_ifs[context.elseIfIndex].plugins;
                break;
            case 'else':
                if (!component.config.else) {
                    component.config.else = {plugins: []};
                } else if (!component.config.else.plugins) {
                    component.config.else.plugins = [];
                }
                targetPlugins = component.config.else.plugins;
                break;
            default:
                console.error('Invalid block type:', context.blockType);
                return;
        }

// Create the new plugin with default config
        const newPlugin = {
            id: `${pluginType}_${pluginName}_${Date.now()}`,
            type: pluginType,
            plugin: pluginName,
            config: {}
        };

        // Track the newly added plugin for animation
        newlyAddedPluginId = newPlugin.id;

        // Mark animation as pending until config modal closes (BEFORE loadExistingComponents)
        pendingAnimationPluginId = newlyAddedPluginId;

// Add the plugin to the appropriate block at the specified index
        if (context.index !== null && context.index !== undefined) {
            targetPlugins.splice(context.index, 0, newPlugin);
        } else {
            targetPlugins.push(newPlugin);
        }

// Clean up the context
        if (modal.dataset.context) {
            delete modal.dataset.context;
        }

// Remove the event listener after handling the selection
        document.removeEventListener('pluginSelected', handlePluginSelect);

// Refresh the UI
        loadExistingComponents();

// Show the config modal for the new plugin
        if (typeof window.PluginConfigModal !== 'undefined') {
            // Use a small timeout to ensure the UI is updated first
            setTimeout(() => {
                window.PluginConfigModal.show(newPlugin);
            }, 50);
        }

        // Dispatch event to mark UI as changed
        document.body.dispatchEvent(new CustomEvent('componentAdded'));
    };

// Listen for the plugin selection event
    document.addEventListener('pluginSelected', handlePluginSelect);

// Set a timeout to clean up the listener if the modal is closed without selecting a plugin
    const cleanupTimer = setTimeout(() => {
        document.removeEventListener('pluginSelected', handlePluginSelect);
        if (modal.dataset.context) {
            delete modal.dataset.context;
        }
    }, 60000); // 60 second timeout

// Clean up the timer when the modal is closed
    const originalHide = PluginModal.hide;
    PluginModal.hide = function () {
        clearTimeout(cleanupTimer);
        document.removeEventListener('pluginSelected', handlePluginSelect);
        originalHide.call(PluginModal);
        PluginModal.hide = originalHide; // Restore original hide function
    };
}

function addElseToConditional(componentId) {

// Find the conditional component
    const component = findComponentById(componentId);

    if (!component || component.plugin !== 'if') {
        console.error('Component not found or not a conditional:', componentId);
        return;
    }

// Check if else block already exists
    if (component.config.else && component.config.else.plugins) {
        alert('An else block already exists for this conditional.');
        return;
    }

// Initialize the else block with empty plugins array
    component.config.else = {plugins: []};
    
    // Set the newly added else as the component to highlight in graph mode
    window.newlyAddedComponentId = component.id + '_else';

// Refresh the UI to show the new empty else block
    loadExistingComponents();

// Dispatch event to mark UI as changed
    document.body.dispatchEvent(new CustomEvent('componentAdded'));

// Trigger pipeline warming and checking
    triggerPipelineWarmingAndChecking();
}


// Function to delete an else-if block
function deleteElseIfBlock(componentId, elseIfIndex) {
    if (!confirm('Are you sure you want to remove this else-if block and all its plugins?')) {
        return;
    }

    const component = findComponentById(componentId);
    if (!component || component.plugin !== 'if') {
        console.error('Component not found or not a conditional:', componentId);
        return;
    }

    if (!component.config.else_ifs || !component.config.else_ifs[elseIfIndex]) {
        console.error('else-if block not found at index:', elseIfIndex);
        return;
    }

    // Remove the else-if block
    component.config.else_ifs.splice(elseIfIndex, 1);

    // Refresh the UI
    loadExistingComponents();

    // Trigger pipeline warming and checking after removal
    triggerPipelineWarmingAndChecking();
}

// Function to delete an else block
function deleteElseBlock(componentId) {
    if (!confirm('Are you sure you want to remove this else block and all its plugins?')) {
        return;
    }

    const component = findComponentById(componentId);
    if (!component || component.plugin !== 'if') {
        console.error('Component not found or not a conditional:', componentId);
        return;
    }

    if (!component.config.else) {
        console.error('else block not found');
        return;
    }

    // Remove the else block
    delete component.config.else;

    // Refresh the UI
    loadExistingComponents();

    // Trigger pipeline warming and checking after removal
    triggerPipelineWarmingAndChecking();
}

// Function to toggle collapse/expand of conditional blocks
document.addEventListener('click', function(e) {
    const collapseToggle = e.target.closest('.collapse-toggle');
    if (collapseToggle) {
        e.stopPropagation();
        const componentId = collapseToggle.dataset.componentId;
        const content = document.querySelector(`.conditional-content[data-component-id="${componentId}"]`);
        const svg = collapseToggle.querySelector('svg');

        if (content && svg) {
            const isCollapsed = content.classList.contains('collapsed');

            if (isCollapsed) {
                // Expand
                content.classList.remove('collapsed');
                svg.style.transform = 'rotate(0deg)';
            } else {
                // Collapse
                content.classList.add('collapsed');
                svg.style.transform = 'rotate(-90deg)';
            }
        }
    }
});

// Function to toggle sensitive value visibility in component row preview
window.toggleSensitiveValue = function(button, event) {
    event.stopPropagation();

    const valueSpan = button.previousElementSibling;
    if (!valueSpan || !valueSpan.classList.contains('sensitive-value')) return;

    const actualValue = valueSpan.dataset.actual;
    const currentText = valueSpan.textContent;

    if (currentText === '••••••••') {
        // Show actual value
        valueSpan.textContent = actualValue;
        // Change icon to open eye (password is now visible — click to hide)
        button.innerHTML = `
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
        `;
    } else {
        // Hide value
        valueSpan.textContent = '••••••••';
        // Change icon back to eye-slash (password is now hidden — click to reveal)
        button.innerHTML = `
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
            </svg>
        `;
    }
};

// Function to open the simulation modal
window.openSimulateModal = function() {
    // Reset subset mode when opening regular simulation
    isSubsetSimulation = false;
    selectedComponentIds = [];

    // Check for memory-intensive filter plugins
    checkMemoryIntensivePlugins();

    // Check for plugins requiring file paths
    checkFilePathRequiredPlugins();

    const modal = document.getElementById('simulationModal');
    if (modal) {
        modal.classList.remove('hidden');

        // Only warm if page-load prealloc has not already prepared a slot
        if (typeof triggerPipelineWarmingAndChecking === 'function') {
            triggerPipelineWarmingAndChecking({ soft: true });
        }
    }
};

// Function to check for memory-intensive filter plugins and display warning
function checkMemoryIntensivePlugins() {
    const warningDiv = document.getElementById('memoryIntensiveWarning');
    const pluginListDiv = document.getElementById('memoryIntensivePluginList');

    if (!warningDiv || !pluginListDiv) return;

    // Get components to check (either subset or all)
    const componentsToCheck = isSubsetSimulation ? getSubsetComponents() : components;

    // Find all memory-intensive filter plugins
    const memoryIntensivePlugins = [];

    if (componentsToCheck.filter && Array.isArray(componentsToCheck.filter)) {
        componentsToCheck.filter.forEach(component => {
            // Check if this is a regular plugin (not a conditional block)
            if (component.plugin && component.plugin !== 'if') {
                const pluginInfo = pluginData?.filter?.[component.plugin];
                if (pluginInfo && pluginInfo.memory_intensive === 'Yes') {
                    memoryIntensivePlugins.push(component.plugin);
                }
            }

            // Check plugins inside conditional blocks
            if (component.plugin === 'if') {
                // Check plugins in the if block
                if (component.config.plugins && Array.isArray(component.config.plugins)) {
                    component.config.plugins.forEach(plugin => {
                        const pluginInfo = pluginData?.filter?.[plugin.plugin];
                        if (pluginInfo && pluginInfo.memory_intensive === 'Yes') {
                            memoryIntensivePlugins.push(plugin.plugin);
                        }
                    });
                }

                // Check plugins in else-if blocks
                if (component.config.else_ifs && Array.isArray(component.config.else_ifs)) {
                    component.config.else_ifs.forEach(elseIf => {
                        if (elseIf.plugins && Array.isArray(elseIf.plugins)) {
                            elseIf.plugins.forEach(plugin => {
                                const pluginInfo = pluginData?.filter?.[plugin.plugin];
                                if (pluginInfo && pluginInfo.memory_intensive === 'Yes') {
                                    memoryIntensivePlugins.push(plugin.plugin);
                                }
                            });
                        }
                    });
                }

                // Check plugins in else block
                if (component.config.else && component.config.else.plugins && Array.isArray(component.config.else.plugins)) {
                    component.config.else.plugins.forEach(plugin => {
                        const pluginInfo = pluginData?.filter?.[plugin.plugin];
                        if (pluginInfo && pluginInfo.memory_intensive === 'Yes') {
                            memoryIntensivePlugins.push(plugin.plugin);
                        }
                    });
                }
            }
        });
    }

    // Remove duplicates
    const uniquePlugins = [...new Set(memoryIntensivePlugins)];

    // Display warning if any memory-intensive plugins found
    if (uniquePlugins.length > 0) {
        let message = "Looks like you're using ";
        if (uniquePlugins.length === 1) {
            message += `<strong>${uniquePlugins[0]}</strong>. This plugin can use a lot of memory. You may have to bump up your JVM heap if it fails.`;
        } else {
            const pluginNames = uniquePlugins.map(p => `<strong>${p}</strong>`).join(', ');
            message += `${pluginNames}. These plugins can use a lot of memory. You may have to bump up your JVM heap if it fails.`;
        }

        pluginListDiv.innerHTML = message;
        warningDiv.classList.remove('hidden');
    } else {
        warningDiv.classList.add('hidden');
    }
}

// Function to check for plugins requiring file paths and display warning
function checkFilePathRequiredPlugins() {
    const warningDiv = document.getElementById('filePathRequiredWarning');
    const pluginListDiv = document.getElementById('filePathPluginList');

    if (!warningDiv || !pluginListDiv) return;

    // Get components to check (either subset or all)
    const componentsToCheck = isSubsetSimulation ? getSubsetComponents() : components;

    // Find all plugins with fs_path options
    const pluginsWithFilePaths = [];

    // Helper function to check a component for fs_path options (recursive for nested conditionals)
    function checkComponentForFilePaths(component, type) {
        if (!component.plugin) return;

        // If this is a conditional, recursively check its nested plugins
        if (component.plugin === 'if') {
            // Check plugins in the if block
            if (component.config.plugins && Array.isArray(component.config.plugins)) {
                component.config.plugins.forEach(plugin => {
                    checkComponentForFilePaths(plugin, type);
                });
            }

            // Check plugins in else-if blocks
            if (component.config.else_ifs && Array.isArray(component.config.else_ifs)) {
                component.config.else_ifs.forEach(elseIf => {
                    if (elseIf.plugins && Array.isArray(elseIf.plugins)) {
                        elseIf.plugins.forEach(plugin => {
                            checkComponentForFilePaths(plugin, type);
                        });
                    }
                });
            }

            // Check plugins in else block
            if (component.config.else && component.config.else.plugins && Array.isArray(component.config.else.plugins)) {
                component.config.else.plugins.forEach(plugin => {
                    checkComponentForFilePaths(plugin, type);
                });
            }
            return; // Don't check the conditional itself for fs_path options
        }

        // For non-conditional plugins, check for fs_path options
        const pluginInfo = pluginData?.[type]?.[component.plugin];
        if (!pluginInfo || !pluginInfo.options) return;

        // Check if any option has input_type: "fs_path" AND has a value configured
        const fsPathOptionsWithValues = [];
        Object.entries(pluginInfo.options).forEach(([optionName, optionInfo]) => {
            if (optionInfo.input_type && optionInfo.input_type.toLowerCase() === 'fs_path') {
                // Only include if the component has a value for this option
                const configValue = component.config?.[optionName];
                if (configValue !== undefined && configValue !== null && configValue !== '') {
                    fsPathOptionsWithValues.push(optionName);
                }
            }
        });

        if (fsPathOptionsWithValues.length > 0) {
            pluginsWithFilePaths.push({
                name: component.plugin,
                type: type,
                options: fsPathOptionsWithValues,
                componentId: component.id
            });
        }
    }

    // Check all plugin types
    ['input', 'filter', 'output'].forEach(type => {
        if (componentsToCheck[type] && Array.isArray(componentsToCheck[type])) {
            componentsToCheck[type].forEach(component => {
                checkComponentForFilePaths(component, type);
            });
        }
    });

    // Display warning if any plugins with file paths found
    if (pluginsWithFilePaths.length > 0) {
        let html = '';

        pluginsWithFilePaths.forEach((plugin, index) => {
            const pluginId = `file-path-plugin-${index}`;

            html += `
                <div class="bg-gray-800/50 rounded p-3 border border-gray-600">
                    ${plugin.options.map((optionName, optIndex) => {
                        const inputId = `${pluginId}-${optIndex}`;
                        const checkboxId = `${pluginId}-ignore-${optIndex}`;
                        return `
                            <div class="mb-3">
                                <div class="flex items-center gap-2 mb-2">
                                    <span class="font-medium text-blue-200">${plugin.name}</span>
                                    <span class="text-gray-400">(${plugin.type})</span>
                                    <span class="text-gray-400">${optionName}</span>
                                    <label class="flex items-center gap-1 cursor-pointer ml-auto">
                                        <input type="checkbox" id="${checkboxId}" class="w-4 h-4 text-blue-600 bg-gray-700 border-gray-600 rounded focus:ring-blue-500" onchange="toggleFilePathInput('${inputId}', this.checked)">
                                        <span class="text-xs text-gray-300">Ignore</span>
                                    </label>
                                </div>
                                <div class="flex items-center gap-2">
                                    <input type="text" id="${inputId}"
                                           class="flex-1 p-2 bg-gray-700 border border-gray-600 rounded text-white text-sm"
                                           placeholder="Enter file path or click Browse..."
                                           data-plugin-name="${plugin.name}"
                                           data-plugin-type="${plugin.type}"
                                           data-option-name="${optionName}"
                                           data-component-id="${plugin.componentId}">
                                    <button type="button" class="px-3 py-2 bg-gray-600 text-white rounded hover:bg-gray-500 text-sm whitespace-nowrap" onclick="browseFilePathForSimulation('${inputId}')" title="Browse for file">
                                        <svg class="w-4 h-4 inline-block mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                                        </svg>
                                        Browse...
                                    </button>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            `;
        });

        pluginListDiv.innerHTML = html;
        warningDiv.classList.remove('hidden');
    } else {
        warningDiv.classList.add('hidden');
    }
}

// Listen for slot preallocation completion to update status
document.addEventListener('htmx:afterSwap', function(event) {
    if (event.detail.target.id === 'slotPreallocationResult') {
        // Check if the response contains a slot-id (successful allocation)
        const slotElement = event.detail.target.querySelector('[data-slot-id]');
        if (slotElement) {
            const slotId = slotElement.getAttribute('data-slot-id');
            if (slotId) {
                // Store the slot ID scoped to the current sim agent
                if (typeof window.rememberSimulationSessionSlot === 'function') {
                    window.rememberSimulationSessionSlot(slotId);
                } else {
                    currentSlotId = slotId;
                    window.currentSlotId = slotId;
                    window.simulationSessionSlotId = slotId;
                }
                // Check pipeline status
                checkPipelineLoadStatus();
            }
        }
    }
});

/**
 * Check if the pipeline successfully loaded in Logstash
 * Called after slot preallocation completes
 * @param {object} [opts]
 * @param {boolean} [opts.preserveReadyOnError] - if chip already Ready, don't overwrite on probe errors
 */
async function checkPipelineLoadStatus(opts) {
        const options = opts || {};
        const preserveReadyOnError = !!options.preserveReadyOnError;
        const statusContainer = document.getElementById('pipelineLoadStatus');
        // Re-query each time — setPipelineSlotChip replaces the icon node
        let statusIcon = document.getElementById('pipelineStatusIcon');
        const statusMessage = document.getElementById('pipelineStatusMessage');

        if (!statusContainer || !statusMessage) {
            console.error('Pipeline status elements not found');
            return;
        }
        if (!statusIcon) {
            // Icon may be mid-replace; still allow Ready/failed via setPipelineSlotChip
            console.warn('pipelineStatusIcon missing; continuing with chip helpers only');
        }

        // Get slot_id from preallocation result (or failed marker without slot_id)
        const preallocationResult = document.getElementById('slotPreallocationResult');

        const slotElement = preallocationResult?.querySelector('[data-slot-id]');
        const failedOnly = preallocationResult?.querySelector('[data-pipeline-failed="true"]');

        const slotId = slotElement?.getAttribute('data-slot-id');
        const pipelineFailed =
            slotElement?.getAttribute('data-pipeline-failed') === 'true' ||
            (!!failedOnly && !slotId);

        // Store slot_id scoped to current sim agent (even if pipeline failed — logs still useful)
        if (slotId) {
            if (typeof window.rememberSimulationSessionSlot === 'function') {
                window.rememberSimulationSessionSlot(slotId);
            } else {
                currentSlotId = slotId;
                window.currentSlotId = slotId;
                window.simulationSessionSlotId = slotId;
            }
        }

        // If pipeline already failed during allocation, show failure immediately
        // (unless we already marked Ready from a successful warm)
        if (pipelineFailed) {
            if (preserveReadyOnError) {
                return;
            }
            if (typeof window.setPipelineSlotChip === 'function') {
                window.setPipelineSlotChip('failed', { title: 'Simulation error during allocate' });
            } else {
                statusContainer.classList.remove('hidden');
                statusContainer.className =
                    'inline-flex items-center gap-1.5 px-2 py-1 rounded-full border border-yellow-600/50 bg-yellow-900/20 max-w-[11rem]';
                statusContainer.title = 'Simulation error';
                statusMessage.textContent = 'Error';
                statusMessage.className = 'text-xs font-medium text-yellow-400 truncate';
            }
            return;
        }

        if (!slotId) {
            if (preserveReadyOnError) {
                return;
            }
            // No slot_id means the pipeline failed to allocate a slot entirely
            console.error('Slot ID not found in preallocation result - pipeline failed to allocate');
            if (typeof window.setPipelineSlotChip === 'function') {
                window.setPipelineSlotChip('failed', {
                    title: 'Simulation failed — no slot allocated',
                });
            } else {
                statusContainer.classList.remove('hidden');
                statusContainer.className =
                    'inline-flex items-center gap-1.5 px-2 py-1 rounded-full border border-yellow-600/50 bg-yellow-900/20 max-w-[11rem]';
                statusContainer.title = 'Simulation failed — no slot allocated';
                statusMessage.textContent = 'Failed';
                statusMessage.className = 'text-xs font-medium text-yellow-400 truncate';
            }
            return;
        }

        // The actual pipeline name in Logstash is slot{id}-filter1
        const slotPipelineName = `slot${slotId}-filter1`;

        // If we already marked Ready (warm path), skip the intermediate "Running…" flip
        const alreadyReady =
            preserveReadyOnError ||
            (statusMessage.textContent &&
                (statusMessage.textContent === 'Ready' ||
                    statusMessage.textContent.startsWith('Slot ')));

        if (!alreadyReady) {
            statusContainer.classList.remove('hidden');
            if (typeof window.setPipelineSlotChip === 'function') {
                window.setPipelineSlotChip('warming', {
                    title: `Verifying slot ${slotId} pipeline…`,
                });
            } else {
                statusContainer.className =
                    'inline-flex items-center gap-1.5 px-2 py-1 rounded-full border border-gray-600 bg-gray-700/50 max-w-[11rem]';
                statusContainer.title = 'Running simulation…';
                statusMessage.textContent = 'Running…';
                statusMessage.className = 'text-xs font-medium text-gray-300 truncate';
            }
        }

        try {
            // Backend already verifies pipelines are running before returning slot allocation
            // Check pipeline status using the slot pipeline name on the *selected* agent
            let checkUrl = `/ConnectionManager/CheckIfPipelineLoaded/?pipeline_name=${encodeURIComponent(slotPipelineName)}`;
            if (typeof window.getSimConnectionId === 'function' && window.getSimConnectionId()) {
                checkUrl += `&sim_connection_id=${encodeURIComponent(window.getSimConnectionId())}`;
            }
            const response = await fetch(checkUrl);

            // Try to parse response even if status is not OK (e.g., 500 errors may still have is_running field)
            let data;
            try {
                data = await response.json();
            } catch (parseError) {
                throw new Error('Failed to parse response from server');
            }

            // Check is_running field regardless of HTTP status code
            const isRunning = data.is_running;

            if (isRunning) {
                // Success - Pipeline is running
                if (typeof window.setPipelineSlotChip === 'function') {
                    window.setPipelineSlotChip('ready', {
                        slotId,
                        title: `Simulation ready (slot ${slotId})`,
                    });
                } else {
                    statusContainer.className = 'inline-flex items-center gap-1.5 px-2 py-1 rounded-full border border-green-600 bg-green-900/30 max-w-[11rem]';
                    statusContainer.title = `Simulation ready (slot ${slotId})`;
                    const iconOk = document.getElementById('pipelineStatusIcon');
                    if (iconOk) {
                        iconOk.outerHTML = `
                        <svg id="pipelineStatusIcon" class="w-3.5 h-3.5 text-green-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                        </svg>
                    `;
                    }
                    statusMessage.textContent = 'Ready';
                    statusMessage.className = 'text-xs font-medium text-green-300 truncate';
                }
            } else if (preserveReadyOnError || alreadyReady) {
                // Allocate already succeeded — keep Ready on a laggy status API
                console.warn(
                    'CheckIfPipelineLoaded reported not running; keeping Ready (allocate already verified)'
                );
                if (typeof window.setPipelineSlotChip === 'function') {
                    window.setPipelineSlotChip('ready', {
                        slotId,
                        title: `Simulation ready (slot ${slotId})`,
                    });
                }
            } else {
                // Failure - Pipeline not running
                statusContainer.className = 'inline-flex items-center gap-1.5 px-2 py-1 rounded-full border border-yellow-600/50 bg-yellow-900/20 max-w-[11rem]';
                statusContainer.title = 'Simulation error — pipeline not running';
                const iconEl = document.getElementById('pipelineStatusIcon');
                if (iconEl) {
                    iconEl.outerHTML = `
                        <svg id="pipelineStatusIcon" class="w-3.5 h-3.5 text-yellow-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
                        </svg>
                    `;
                }
                statusMessage.textContent = 'Error';
                statusMessage.className = 'text-xs font-medium text-yellow-400 truncate';
            }

        } catch (error) {
            console.error('Error checking pipeline status:', error);

            // Don't overwrite a successful green status with yellow on transient errors
            if (
                preserveReadyOnError ||
                statusMessage.textContent === 'Ready' ||
                statusMessage.textContent === 'Simulation Ready' ||
                (statusMessage.textContent && statusMessage.textContent.startsWith('Slot '))
            ) {
                console.log('Status already shows Ready, not overwriting with error state');
                if (typeof window.setPipelineSlotChip === 'function' && slotId) {
                    window.setPipelineSlotChip('ready', {
                        slotId,
                        title: `Simulation ready (slot ${slotId})`,
                    });
                }
                return;
            }

            // Unknown - Error occurred (network failure or unparseable response)
            statusIcon.classList.remove('animate-spin');
            statusContainer.className = 'inline-flex items-center gap-1.5 px-2 py-1 rounded-full border border-yellow-600 bg-yellow-900/30 max-w-[11rem]';
            statusContainer.title = 'Unable to verify simulation status';
            statusIcon.outerHTML = `
                <svg id="pipelineStatusIcon" class="w-3.5 h-3.5 text-yellow-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
                </svg>
            `;
            statusMessage.textContent = 'Unknown';
            statusMessage.className = 'text-xs font-medium text-yellow-400 truncate';
        }
    }


// Toggle file path input enabled/disabled based on ignore checkbox
window.toggleFilePathInput = function(inputId, isIgnored) {
    const input = document.getElementById(inputId);
    if (input) {
        input.disabled = isIgnored;
        if (isIgnored) {
            input.classList.add('opacity-50', 'cursor-not-allowed');
        } else {
            input.classList.remove('opacity-50', 'cursor-not-allowed');
        }
    }
};

// Browse file path for simulation and upload the file
window.browseFilePathForSimulation = function(inputId) {
    // Create a hidden file input
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.style.display = 'none';

    fileInput.addEventListener('change', async function(e) {
        const file = e.target.files[0];
        if (file) {
            const textInput = document.getElementById(inputId);
            if (!textInput) return;

            // Get metadata from data attributes
            const componentId = textInput.dataset.componentId;
            const optionName = textInput.dataset.optionName;

            // Get file extension
            const originalExtension = file.name.split('.').pop();

            // Generate filename for backend: {component_id}_{option_name}.{extension}
            const generatedFilename = `${componentId}_${optionName}.${originalExtension}`;

            // Show the original filename to the user
            textInput.value = file.name;

            // Store the generated filename in a data attribute for later use
            textInput.dataset.generatedFilename = generatedFilename;

            // Upload the file to the API with the generated filename
            try {
                const formData = new FormData();
                formData.append('file', file);
                formData.append('filename', generatedFilename);

                const response = await fetch('/ConnectionManager/UploadFile/', {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                    }
                });

                if (response.ok) {
                    // Show success toast
                    showToast('Upload successful', 'success');
                } else {
                    const errorData = await response.json();
                    console.error('File upload failed:', errorData);
                    showToast('Upload failed: ' + (errorData.error || 'Unknown error'), 'error');
                }
            } catch (error) {
                console.error('Error uploading file:', error);
                showToast('Upload failed: ' + error.message, 'error');
            }
        }

        // Clean up
        document.body.removeChild(fileInput);
    });

    // Trigger the file picker
    document.body.appendChild(fileInput);
    fileInput.click();
};
