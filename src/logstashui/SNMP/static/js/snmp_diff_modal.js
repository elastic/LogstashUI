/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

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

// ===== SNMP INDEX TEMPLATE STATUS =====

// connection_ids involved in the current diff (populated after GetDeployDiff)
let _snmpDiffConnectionIds = [];

// true when at least one connection is missing the template (blocks deploy)
let _snmpTemplateBlocked = false;

// true when the "no changes" path has disabled the button
let _snmpNoChangesBlocked = false;

// true when a pre-deploy validation error blocks the whole deploy
let _snmpConfigBlocked = false;

function _updateDeployButtonState() {
    const btn = document.getElementById('confirmDeployButton');
    if (!btn) return;

    if (_snmpConfigBlocked) {
        // Misconfiguration (missing keystore password / ES connection) — keep the
        // button visible but disabled so the red banner explains why.
        btn.classList.remove('hidden');
        btn.disabled = true;
        btn.classList.add('opacity-50', 'cursor-not-allowed');
    } else if (_snmpTemplateBlocked) {
        btn.classList.add('hidden');
        btn.disabled = true;
    } else if (_snmpNoChangesBlocked) {
        btn.classList.remove('hidden');
        btn.disabled = true;
        btn.classList.add('opacity-50', 'cursor-not-allowed');
    } else {
        btn.classList.remove('hidden');
        btn.disabled = false;
        btn.classList.remove('opacity-50', 'cursor-not-allowed');
    }
}

/**
 * Render the pre-deploy blocking banner. When any blocking error is present the
 * entire deploy is disabled and the user is told (with a fix link) why.
 */
function renderSnmpBlockingBanner(errors) {
    const banner = document.getElementById('snmpDiffBlockingBanner');
    if (!banner) return;

    if (!errors || errors.length === 0) {
        _snmpConfigBlocked = false;
        banner.classList.add('hidden');
        banner.innerHTML = '';
        _updateDeployButtonState();
        return;
    }

    _snmpConfigBlocked = true;

    let items = '';
    errors.forEach(e => {
        let link = '';
        if (e.policy_id) {
            link = ` <a href="/ConnectionManager/AgentPolicies/?policy_id=${e.policy_id}" class="underline font-medium text-red-200 hover:text-white">Set a keystore password &rarr;</a>`;
        }
        items += `<li>${escapeHtml(e.message)}${link}</li>`;
    });

    banner.innerHTML = `
        <div class="flex items-start gap-3">
            <svg class="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
            </svg>
            <div class="min-w-0">
                <p class="font-semibold text-red-200">Deployment blocked</p>
                <ul class="list-disc pl-5 mt-1 space-y-1 text-sm">${items}</ul>
            </div>
        </div>`;
    banner.classList.remove('hidden');
    _updateDeployButtonState();
}

/**
 * A small pill describing where a pipeline is deployed (a specific agent or an
 * Elasticsearch CPM connection).
 */
function _snmpDestinationPill(entry) {
    if (!entry || !entry.destination_name) return '';
    const isAgent = entry.destination_type === 'agent';
    const cls = isAgent
        ? 'bg-teal-600/20 text-teal-300 border-teal-600/40'
        : 'bg-indigo-600/20 text-indigo-300 border-indigo-600/40';
    const label = isAgent ? 'Agent' : 'Elasticsearch CPM';
    return `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded border ${cls} flex-shrink-0" title="Deployment destination">
        <span class="opacity-70">${label}</span>
        <span class="font-medium truncate max-w-[16rem]">${escapeHtml(entry.destination_name)}</span>
    </span>`;
}

// Reusable eye / eye-slash icon paths (matches keystore_modal.html's toggle icon).
const _SNMP_EYE_OPEN_PATHS = `
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />`;
const _SNMP_EYE_CLOSED_PATHS = `
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />`;

const _SNMP_COPY_ICON_SVG = `
    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/>
    </svg>`;

/**
 * Group the raw per-pipeline diff entries by network and merge their
 * ${KEY} lists/values, since a single network's keys can be spread across
 * its main/trap/discovery pipeline entries. Preserves first-seen key order.
 */
function _aggregateSnmpManualKeystoreEntries(networks) {
    const byNetwork = new Map();

    for (const entry of networks) {
        const keys = entry.manual_keystore_keys;
        if (!keys || keys.length === 0) continue;

        const name = entry.network_name;
        if (!byNetwork.has(name)) {
            byNetwork.set(name, { keys: [], values: {}, seen: new Set() });
        }
        const agg = byNetwork.get(name);
        const values = entry.manual_keystore_values || {};

        for (const key of keys) {
            if (!agg.seen.has(key)) {
                agg.seen.add(key);
                agg.keys.push(key);
            }
            if (values[key] !== undefined) {
                agg.values[key] = values[key];
            }
        }
    }

    return byNetwork;
}

/**
 * Render the aggregated "manual keystore values required" section at the top
 * of the modal: one collapsed row per network (collapsed by default) that,
 * when expanded, reveals the single `logstash-keystore add key1 key2 ...`
 * command for that network plus the values to paste in when prompted for
 * each key, in order. Doing it once per network (instead of once per
 * pipeline) means a single logstash-keystore/JVM invocation covers every
 * pipeline for that network.
 */
function renderSnmpManualKeystoreCommandsSection(networks) {
    const section = document.getElementById('snmpKeystoreCommandsSection');
    if (!section) return;

    const byNetwork = _aggregateSnmpManualKeystoreEntries(networks);
    if (byNetwork.size === 0) {
        section.classList.add('hidden');
        section.innerHTML = '';
        return;
    }

    let rowsHtml = '';
    for (const [networkName, agg] of byNetwork.entries()) {
        rowsHtml += _snmpManualKeystoreRow(networkName, agg.keys, agg.values);
    }

    section.innerHTML = `
        <div class="border border-yellow-600/30 rounded-lg overflow-hidden divide-y divide-yellow-600/20">
            ${rowsHtml}
        </div>`;
    section.classList.remove('hidden');
}

/**
 * A single collapsible row for one network's manual-keystore command.
 * Collapsed by default. The command itself is always visible once expanded;
 * only the credential values underneath are maskable via the eye toggle.
 *
 * The command mirrors ls_keystore_utils' LogstashKeystore._add_batch_keys()
 * exactly: `add KEY1 KEY2 ... --stdin`, fed newline-separated values in the
 * same order as the keys. That helper also prepends a "y" confirmation line
 * before any value whose key it already knows exists in the keystore it
 * manages (logstash-keystore prompts "Overwrite existing entry? [y/N]" for
 * pre-existing keys before it'll accept a new value). We can't reproduce
 * that here: in "manage keystore manually" mode LogstashUI never tracks the
 * contents of the operator's keystore, so we have no way to know which keys
 * (if any) already exist on their node. Blindly prepending "y" would corrupt
 * the paste for brand-new keys (the "y" would be read as the secret value
 * itself), so instead we surface the caveat and let the operator answer any
 * overwrite prompt themselves if one appears.
 */
function _snmpManualKeystoreRow(networkName, keys, values) {
    const blockId = `snmpKeystoreRow_${Math.random().toString(36).slice(2)}`;
    const cmd = `logstash-keystore --path.settings /etc/logstash add ${keys.join(' ')} --stdin`;
    const valueLines = keys.map(key => values[key] || '');

    // What "copy everything" copies: the command followed by each value on
    // its own line — pasted as one block into an interactive terminal, this
    // runs the add command and then answers each value prompt in order.
    const pasteBlock = [cmd, ...valueLines].join('\n');

    const maskedText = valueLines.map(v => (v ? '••••••••••••' : '(no value set)')).join('\n');
    const revealedText = valueLines.map(v => v || '(no value set)').join('\n');

    return `
        <div>
            <button type="button" onclick="_toggleSnmpKeystoreRow('${blockId}')"
                    class="w-full flex items-center gap-2 px-4 py-2.5 bg-yellow-900/10 hover:bg-yellow-900/20 text-left transition-colors">
                <svg id="${blockId}_chevron" class="w-3.5 h-3.5 text-yellow-400 flex-shrink-0 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
                </svg>
                <svg class="w-4 h-4 text-yellow-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
                </svg>
                <span class="text-sm text-yellow-200 truncate"><span class="font-semibold">${escapeHtml(networkName)}:</span> manual keystore values required, click here for the keystore command</span>
            </button>
            <div id="${blockId}_body" class="hidden px-4 py-3 bg-gray-900/40 border-t border-yellow-600/20">
                <div class="flex items-center justify-between mb-1.5">
                    <p class="text-xs text-gray-400">Run this on the Logstash node. It reads each value below from stdin, in order:</p>
                    <div class="flex items-center gap-1 flex-shrink-0">
                        <button type="button" onclick="_toggleSnmpKeystoreValues('${blockId}')" title="Show/Hide credential values"
                                class="p-1 text-gray-400 hover:text-gray-200">
                            <svg id="${blockId}_eye" class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">${_SNMP_EYE_OPEN_PATHS}</svg>
                        </button>
                        <button type="button" data-cmd="${escapeHtml(pasteBlock)}" onclick="_copySnmpKeystoreCmd(this)" title="Copy command and values"
                                class="p-1 text-gray-400 hover:text-gray-200">
                            ${_SNMP_COPY_ICON_SVG}
                        </button>
                    </div>
                </div>
                <pre class="text-xs bg-gray-900 text-gray-200 rounded px-2 py-1.5 overflow-x-auto font-mono whitespace-pre">${escapeHtml(cmd)}</pre>
                <pre id="${blockId}_values" data-masked="${escapeHtml(maskedText)}" data-revealed-text="${escapeHtml(revealedText)}" data-revealed="false"
                     class="mt-1 text-xs bg-gray-900 text-gray-500 rounded px-2 py-1.5 overflow-x-auto font-mono whitespace-pre select-none">${escapeHtml(maskedText)}</pre>
                <p class="text-xs text-gray-500 mt-1.5">If a key already exists in the keystore, it will prompt to overwrite before reading its value — answer that prompt, then continue pasting the remaining values.</p>
            </div>
        </div>`;
}

/**
 * Expand/collapse a single network's manual-keystore row.
 */
function _toggleSnmpKeystoreRow(blockId) {
    const body = document.getElementById(`${blockId}_body`);
    const chevron = document.getElementById(`${blockId}_chevron`);
    if (!body) return;

    const isCollapsed = body.classList.contains('hidden');
    body.classList.toggle('hidden');
    if (chevron) chevron.style.transform = isCollapsed ? 'rotate(90deg)' : '';
}

/**
 * Reveal or mask the credential values block for a row (the command line
 * itself is never affected by this toggle).
 */
function _toggleSnmpKeystoreValues(blockId) {
    const valuesEl = document.getElementById(`${blockId}_values`);
    const eyeEl = document.getElementById(`${blockId}_eye`);
    if (!valuesEl || !eyeEl) return;

    const revealed = valuesEl.getAttribute('data-revealed') === 'true';

    if (revealed) {
        valuesEl.textContent = valuesEl.getAttribute('data-masked') || '';
        valuesEl.classList.add('text-gray-500');
        valuesEl.classList.remove('text-gray-200');
        valuesEl.setAttribute('data-revealed', 'false');
        eyeEl.innerHTML = _SNMP_EYE_OPEN_PATHS;
    } else {
        valuesEl.textContent = valuesEl.getAttribute('data-revealed-text') || '';
        valuesEl.classList.remove('text-gray-500');
        valuesEl.classList.add('text-gray-200');
        valuesEl.setAttribute('data-revealed', 'true');
        eyeEl.innerHTML = _SNMP_EYE_CLOSED_PATHS;
    }
}

function _copySnmpKeystoreCmd(btn) {
    const cmd = btn.getAttribute('data-cmd') || '';
    navigator.clipboard.writeText(cmd).then(() => {
        const origHtml = btn.innerHTML;
        btn.innerHTML = `<svg class="w-3.5 h-3.5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>`;
        setTimeout(() => { btn.innerHTML = origHtml; }, 1500);
    }).catch(() => {});
}

/**
 * Render a dedicated card for a keystore-drift diff entry (credential/secret
 * rotation). Secret values are never shown — only key names.
 */
function _renderKeystoreDriftCard(entry) {
    const drift = entry.keystore_drift || {};
    const added = drift.added || [];
    const changed = drift.changed || [];
    const removed = drift.removed || [];

    const chip = (name, cls) =>
        `<span class="px-2 py-0.5 text-xs font-mono rounded border ${cls}">${escapeHtml(name)}</span>`;
    let chips = '';
    added.forEach(k => chips += chip(k, 'bg-green-600/20 text-green-300 border-green-600/40'));
    changed.forEach(k => chips += chip(k, 'bg-blue-600/20 text-blue-300 border-blue-600/40'));
    removed.forEach(k => chips += chip(k, 'bg-red-600/20 text-red-300 border-red-600/40'));

    let legend = [];
    if (added.length) legend.push(`<span class="text-green-300">${added.length} added</span>`);
    if (changed.length) legend.push(`<span class="text-blue-300">${changed.length} changed</span>`);
    if (removed.length) legend.push(`<span class="text-red-300">${removed.length} removed</span>`);

    return `
        <div class="border border-gray-600 rounded-lg overflow-hidden">
            <div class="bg-gray-700 px-4 py-2 border-b border-gray-600 flex items-start justify-between gap-3">
                <div class="min-w-0">
                    <h4 class="text-white font-semibold flex items-center">
                        Keystore Values
                        <span class="ml-2 px-2 py-0.5 text-xs bg-purple-600 text-white rounded">KEYSTORE</span>
                    </h4>
                    <p class="text-sm text-gray-400">${legend.join(' &middot; ')}</p>
                </div>
                ${_snmpDestinationPill(entry)}
            </div>
            <div class="p-4 bg-gray-800">
                <p class="text-xs text-gray-400 mb-3">These secret values will be (re)provisioned into the agent keystore on deploy. Secret contents are never displayed.</p>
                <div class="flex flex-wrap gap-2">${chips || '<span class="text-xs text-gray-500">No keys</span>'}</div>
            </div>
        </div>`;
}

function _templateStatusBadge(status) {
    const cfg = {
        installed:              { dot: 'bg-green-400', text: 'text-green-300',  label: 'Installed'         },
        installed_but_outdated: { dot: 'bg-yellow-400', text: 'text-yellow-300', label: 'Needs update'      },
        not_installed:          { dot: 'bg-red-400',   text: 'text-red-300',    label: 'Not installed'     },
        error:                  { dot: 'bg-gray-500',  text: 'text-gray-400',   label: 'Check failed'      },
    };
    const c = cfg[status] || cfg.error;
    return `<span class="flex items-center gap-1.5">
              <span class="w-2 h-2 rounded-full ${c.dot} flex-shrink-0"></span>
              <span class="text-xs ${c.text} font-medium">${c.label}</span>
            </span>`;
}

function _renderTemplateStatusPanel(results) {
    const list    = document.getElementById('snmpTemplateStatusList');
    const loading = document.getElementById('snmpTemplateStatusLoading');
    const panel   = document.getElementById('snmpTemplateStatusPanel');
    const btn     = document.getElementById('snmpTemplateInstallBtn');
    const label   = document.getElementById('snmpTemplateInstallBtnLabel');

    if (loading) loading.classList.add('hidden');
    if (!list) return;

    list.innerHTML = '';

    let hasMissing  = false;
    let hasOutdated = false;

    results.forEach(r => {
        if (r.status === 'not_installed') hasMissing  = true;
        if (r.status === 'installed_but_outdated') hasOutdated = true;

        const diffHint = r.differences && r.differences.length
            ? `<span class="text-xs text-gray-500 ml-1">(${r.differences.join(', ')})</span>`
            : '';
        const errorHint = r.error
            ? `<span class="text-xs text-red-400 ml-1 truncate" title="${escapeHtml(r.error)}">${escapeHtml(r.error)}</span>`
            : '';

        const row = document.createElement('div');
        row.className = 'flex items-center justify-between px-4 py-2.5 gap-4';
        row.innerHTML = `
            <div class="flex items-center gap-2 min-w-0">
                <span class="text-sm text-white truncate">${escapeHtml(r.connection_name || String(r.connection_id))}</span>
                ${diffHint}${errorHint}
            </div>
            <div class="flex-shrink-0">
                ${_templateStatusBadge(r.status)}
            </div>
        `;
        list.appendChild(row);
    });

    // Show/hide the install button and update its label
    const needsAction = hasMissing || hasOutdated;
    if (btn) {
        if (needsAction) {
            btn.classList.remove('hidden');
            if (label) label.textContent = hasMissing ? 'Install Template' : 'Update Template';
        } else {
            btn.classList.add('hidden');
        }
    }

    // Gate the deploy button when any connection is missing the template
    _snmpTemplateBlocked = hasMissing;
    _updateDeployButtonState();
}

async function checkSNMPIndexTemplateStatus(connectionIds) {
    if (!connectionIds || connectionIds.length === 0) return;

    const panel   = document.getElementById('snmpTemplateStatusPanel');
    const loading = document.getElementById('snmpTemplateStatusLoading');
    const list    = document.getElementById('snmpTemplateStatusList');

    if (panel)   panel.classList.remove('hidden');
    if (loading) loading.classList.remove('hidden');
    if (list)    list.innerHTML = '';

    try {
        const response = await fetch('/SNMP/CheckSNMPIndexTemplate/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
            },
            body: JSON.stringify({ connection_ids: connectionIds }),
        });
        const data = await response.json();
        _renderTemplateStatusPanel(data.results || []);
    } catch (err) {
        if (loading) loading.classList.add('hidden');
        _snmpTemplateBlocked = false;
        _updateDeployButtonState();
        console.error('Error checking SNMP index template:', err);
    }
}

async function installSNMPIndexTemplate() {
    if (!_snmpDiffConnectionIds || _snmpDiffConnectionIds.length === 0) return;

    const btn   = document.getElementById('snmpTemplateInstallBtn');
    const label = document.getElementById('snmpTemplateInstallBtnLabel');
    const loading = document.getElementById('snmpTemplateStatusLoading');

    if (btn)   btn.disabled = true;
    if (label) label.textContent = 'Installing…';
    if (loading) loading.classList.remove('hidden');

    try {
        const response = await fetch('/SNMP/InstallSNMPIndexTemplate/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
            },
            body: JSON.stringify({ connection_ids: _snmpDiffConnectionIds }),
        });

        if (response.status === 403) {
            showToast('Access denied: Admin role required', 'error');
            return;
        }

        const result = await response.json();

        if (!result.success) {
            const firstError = (result.results || []).find(r => !r.success);
            showToast(firstError ? firstError.error : 'Template install failed', 'error');
        } else {
            showToast('SNMP index template installed successfully', 'success');
        }
    } catch (err) {
        showToast(`Template install failed: ${err.message}`, 'error');
    } finally {
        if (btn) btn.disabled = false;
        // Re-check status after install attempt
        await checkSNMPIndexTemplateStatus(_snmpDiffConnectionIds);
    }
}

// ===== END SNMP INDEX TEMPLATE STATUS =====

function hideSnmpDiffModal() {
    document.getElementById('snmpDiffModal').classList.add('hidden');
}

function showSnmpDiffModal() {
    document.getElementById('snmpDiffModal').classList.remove('hidden');
}

/**
 * Prepare and show the SNMP diff modal
 * This fetches diffs for all networks and displays them
 */
async function prepareSnmpDiffModal() {
    // Show the modal first
    showSnmpDiffModal();

    // Show loading state
    document.getElementById('snmpDiffLoading').classList.remove('hidden');
    document.getElementById('snmpDiffContainer').classList.add('hidden');

    // Reset template status panel
    _snmpDiffConnectionIds = [];
    _snmpTemplateBlocked   = false;
    _snmpNoChangesBlocked  = false;
    _snmpConfigBlocked     = false;
    const blockingBanner = document.getElementById('snmpDiffBlockingBanner');
    if (blockingBanner) { blockingBanner.classList.add('hidden'); blockingBanner.innerHTML = ''; }
    const keystoreCommandsSection = document.getElementById('snmpKeystoreCommandsSection');
    if (keystoreCommandsSection) { keystoreCommandsSection.classList.add('hidden'); keystoreCommandsSection.innerHTML = ''; }
    const templatePanel = document.getElementById('snmpTemplateStatusPanel');
    if (templatePanel) templatePanel.classList.add('hidden');
    const templateList = document.getElementById('snmpTemplateStatusList');
    if (templateList) templateList.innerHTML = '';
    const templateBtn = document.getElementById('snmpTemplateInstallBtn');
    if (templateBtn) templateBtn.classList.add('hidden');
    
    // Reset the deploy button to enabled state (in case it was disabled from a previous deployment)
    const confirmButton = document.getElementById('confirmDeployButton');
    confirmButton.classList.remove('hidden');
    confirmButton.disabled = false;
    confirmButton.textContent = 'Confirm & Deploy Changes';
    confirmButton.classList.remove('opacity-50', 'cursor-not-allowed');

    try {
        // Fetch diff data from the server
        const response = await fetch('/SNMP/GetDeployDiff/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Failed to fetch diffs: ${response.status} - ${errorText}`);
        }

        const diffData = await response.json();

        // Hide loading, show container
        document.getElementById('snmpDiffLoading').classList.add('hidden');
        document.getElementById('snmpDiffContainer').classList.remove('hidden');

        // Render pre-deploy blocking validation (disables deploy while present)
        renderSnmpBlockingBanner(diffData.blocking_errors);

        // Render the aggregated manual-keystore command section (one row per network)
        renderSnmpManualKeystoreCommandsSection(diffData.networks);

        // Display the diffs for each network
        displayNetworkDiffs(diffData.networks);

        // If backend says no changes, refresh the indicator to clear it immediately
        // (Backend already called mark_deployed() to sync timestamps)
        if (diffData.has_changes === false) {
            if (typeof checkForUndeployedSNMPChanges === 'function') {
                checkForUndeployedSNMPChanges();
            }
        }

        // Store change count for deployment message
        window.snmpChangeCount = diffData.networks.length;

        // Kick off index template status check for all involved connections
        if (diffData.connections && diffData.connections.length > 0) {
            _snmpDiffConnectionIds = diffData.connections.map(c => c.id);
            checkSNMPIndexTemplateStatus(_snmpDiffConnectionIds);
        }

        // Display overall stats
        const newPipelines = diffData.networks.filter(n => !n.current || n.current.trim() === '').length;
        document.getElementById('snmpDiffStats').textContent =
            `${newPipelines} new pipeline(s)`;

    } catch (error) {
        console.error('Error preparing SNMP diff:', error);
        document.getElementById('snmpDiffLoading').innerHTML = `
            <div class="text-center">
                <p class="text-red-400 mb-4">Failed to load pipeline comparison</p>
                <p class="text-gray-400 text-sm">${error.message}</p>
                <button onclick="hideSnmpDiffModal()" class="mt-4 px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600">
                    Close
                </button>
            </div>
        `;
    }
}

/**
 * Display diffs for all networks
 */
function displayNetworkDiffs(networks) {
    const container = document.getElementById('snmpDiffContainer');

    let html = '';
    let networksWithChanges = 0;
    let newPipelinesCount = 0;
    let deletedPipelinesCount = 0;

    for (const network of networks) {
        // Keystore-drift entries (credential/secret rotation) get a dedicated card
        // instead of a line-by-line diff — we only ever show key names, not values.
        if (network.pipeline_type === 'keystore') {
            networksWithChanges++;
            html += _renderKeystoreDriftCard(network);
            continue;
        }

        // Skip main pipeline rendering if network has no devices (pipeline_name will be null)
        const hasMainPipeline = network.pipeline_name !== null;

        let currentLines = [];
        let newLines = [];
        let isNewPipeline = false;
        let isDeletePipeline = false;
        let hasChanges = false;
        let lineDiff = [];

        if (hasMainPipeline) {
            currentLines = network.current ? network.current.split('\n') : [];
            newLines = network.new.split('\n');

            // Check action field first, then fall back to checking current content
            if (network.action === 'create') {
                isNewPipeline = true;
            } else if (network.action === 'delete') {
                isDeletePipeline = true;
            } else if (network.action === 'update') {
                isNewPipeline = false;
            } else {
                // Fallback for backwards compatibility if action field not present
                isNewPipeline = !network.current || network.current.trim() === '';
            }

            // Compute diff
            lineDiff = computeLineDiff(currentLines, newLines);

            // Check if there are any actual changes (additions or deletions)
            hasChanges = lineDiff.some(change => change.type !== 'equal');

            // Track counts
            if (isDeletePipeline) {
                deletedPipelinesCount++;
            } else if (isNewPipeline) {
                newPipelinesCount++;
            } else if (hasChanges) {
                networksWithChanges++;
            }
        }

        // Skip this network entirely if it has no main pipeline and no trap pipeline
        if (!hasMainPipeline && !network.trap_pipeline) {
            continue;
        }

        // Skip main pipeline section if no changes and not new (but still show trap pipeline if exists)
        const shouldShowMainPipeline = hasMainPipeline && (isNewPipeline || hasChanges);

        let currentHtml = '';
        let newHtml = '';
        let currentLineNum = 1;
        let newLineNum = 1;

        if (isNewPipeline) {
            // For new pipelines, just show the new content on the right
            for (let i = 0; i < newLines.length; i++) {
                const line = escapeHtml(newLines[i]);

                currentHtml += `<div class="flex bg-gray-800/50">
                    <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                    <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                </div>`;

                newHtml += `<div class="flex bg-green-900/20 hover:bg-green-900/30">
                    <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${newLineNum++}</span>
                    <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                </div>`;
            }
        } else {
            // For existing pipelines, show the diff
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
        }

        // Build the network section with badge only if there are changes
        let networkBadge = '';
        if (isDeletePipeline) {
            networkBadge = '<span class="ml-2 px-2 py-0.5 text-xs bg-red-600 text-white rounded">DELETE</span>';
        } else if (isNewPipeline) {
            networkBadge = '<span class="ml-2 px-2 py-0.5 text-xs bg-green-600 text-white rounded">NEW</span>';
        } else if (hasChanges) {
            networkBadge = '<span class="ml-2 px-2 py-0.5 text-xs bg-blue-600 text-white rounded">MODIFIED</span>';
        }

        // Only show main pipeline section if network has devices
        if (shouldShowMainPipeline) {
            html += `
                <div class="border border-gray-600 rounded-lg overflow-hidden">
                    <div class="bg-gray-700 px-4 py-2 border-b border-gray-600 flex items-start justify-between gap-3">
                        <div class="min-w-0">
                            <h4 class="text-white font-semibold">
                                ${escapeHtml(network.network_name)}${networkBadge}
                            </h4>
                            <p class="text-sm text-gray-400 truncate">Pipeline: ${escapeHtml(network.pipeline_name)}</p>
                        </div>
                        ${_snmpDestinationPill(network)}
                    </div>
                    <div style="display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 0; height: 400px;">
                        <div class="p-4 bg-gray-700 border-r border-gray-600" style="display: flex; flex-direction: column; height: 100%; min-height: 0; min-width: 0;">
                            <div class="mb-2" style="flex-shrink: 0;">
                                <h5 class="text-sm font-semibold text-white">${isNewPipeline ? 'No Existing Pipeline' : 'Current Pipeline'}</h5>
                            </div>
                            <div class="bg-gray-800 rounded border border-gray-600 network-diff-scroll-panel" style="flex: 1; overflow-y: auto; overflow-x: auto; min-height: 0; min-width: 0;">
                                <div class="p-2 text-sm text-gray-300 font-mono">${currentHtml}</div>
                            </div>
                        </div>
                        <div class="p-4 bg-gray-700" style="display: flex; flex-direction: column; height: 100%; min-height: 0; min-width: 0;">
                            <div class="mb-2" style="flex-shrink: 0;">
                                <h5 class="text-sm font-semibold text-white">New Pipeline (After Deploy)</h5>
                            </div>
                            <div class="bg-gray-800 rounded border border-gray-600 network-diff-scroll-panel" style="flex: 1; overflow-y: auto; overflow-x: auto; min-height: 0; min-width: 0;">
                                <div class="p-2 text-sm text-gray-300 font-mono">${newHtml}</div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }

        // Handle trap pipeline if it exists
        if (network.trap_pipeline) {
            const trapPipeline = network.trap_pipeline;
            const trapCurrentLines = trapPipeline.current ? trapPipeline.current.split('\n') : [];
            const trapNewLines = trapPipeline.new ? trapPipeline.new.split('\n') : [];

            // Check if there are actual changes in the trap pipeline
            let trapHasChanges = false;
            if (trapPipeline.action === 'create' || trapPipeline.action === 'delete') {
                trapHasChanges = true;
            } else if (trapPipeline.action === 'update') {
                // Compare current and new to see if there are actual differences
                const trapLineDiff = computeLineDiff(trapCurrentLines, trapNewLines);
                trapHasChanges = trapLineDiff.some(change => change.type !== 'equal');
            }

            // Only render trap pipeline if there are actual changes
            if (trapHasChanges) {
                // Count trap pipeline in summary only if there are changes
                if (trapPipeline.action === 'create') {
                    newPipelinesCount++;
                } else if (trapPipeline.action === 'update') {
                    networksWithChanges++;
                } else if (trapPipeline.action === 'delete') {
                    deletedPipelinesCount++;
                }

                let trapBadge = '';
                let trapCurrentHtml = '';
                let trapNewHtml = '';
                let trapCurrentLineNum = 1;
                let trapNewLineNum = 1;

                if (trapPipeline.action === 'create') {
                    trapBadge = '<span class="ml-2 px-2 py-0.5 text-xs bg-green-600 text-white rounded">NEW TRAP PIPELINE</span>';

                    // Show new trap pipeline
                    for (let i = 0; i < trapNewLines.length; i++) {
                        const line = escapeHtml(trapNewLines[i]);

                        trapCurrentHtml += `<div class="flex bg-gray-800/50">
                        <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                        <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                    </div>`;

                        trapNewHtml += `<div class="flex bg-green-900/20 hover:bg-green-900/30">
                        <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${trapNewLineNum++}</span>
                        <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                    </div>`;
                    }
                } else if (trapPipeline.action === 'delete') {
                    trapBadge = '<span class="ml-2 px-2 py-0.5 text-xs bg-red-600 text-white rounded">DELETING TRAP PIPELINE</span>';

                    // Show trap pipeline being deleted
                    for (let i = 0; i < trapCurrentLines.length; i++) {
                        const line = escapeHtml(trapCurrentLines[i]);

                        trapCurrentHtml += `<div class="flex bg-red-900/20 hover:bg-red-900/30">
                        <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${trapCurrentLineNum++}</span>
                        <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                    </div>`;

                        trapNewHtml += `<div class="flex bg-gray-800/50">
                        <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                        <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                    </div>`;
                    }
                } else if (trapPipeline.action === 'update') {
                    trapBadge = '<span class="ml-2 px-2 py-0.5 text-xs bg-blue-600 text-white rounded">UPDATING TRAP PIPELINE</span>';

                    // Compute diff for trap pipeline
                    const trapLineDiff = computeLineDiff(trapCurrentLines, trapNewLines);

                    for (const change of trapLineDiff) {
                        if (change.type === 'equal') {
                            for (let i = 0; i < change.lines.length; i++) {
                                const line = escapeHtml(change.lines[i]);
                                trapCurrentHtml += `<div class="flex hover:bg-gray-700/30">
                                <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${trapCurrentLineNum++}</span>
                                <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                            </div>`;
                                trapNewHtml += `<div class="flex hover:bg-gray-700/30">
                                <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${trapNewLineNum++}</span>
                                <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                            </div>`;
                            }
                        } else if (change.type === 'delete') {
                            for (let i = 0; i < change.lines.length; i++) {
                                const line = escapeHtml(change.lines[i]);
                                trapCurrentHtml += `<div class="flex bg-red-900/20 hover:bg-red-900/30">
                                <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${trapCurrentLineNum++}</span>
                                <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                            </div>`;
                                trapNewHtml += `<div class="flex bg-gray-800/50">
                                <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                                <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                            </div>`;
                            }
                        } else if (change.type === 'insert') {
                            for (let i = 0; i < change.lines.length; i++) {
                                const line = escapeHtml(change.lines[i]);
                                trapCurrentHtml += `<div class="flex bg-gray-800/50">
                                <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                                <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                            </div>`;
                                trapNewHtml += `<div class="flex bg-green-900/20 hover:bg-green-900/30">
                                <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${trapNewLineNum++}</span>
                                <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                            </div>`;
                            }
                        } else if (change.type === 'replace') {
                            const maxLen = Math.max(change.oldLines.length, change.newLines.length);
                            for (let i = 0; i < maxLen; i++) {
                                if (i < change.oldLines.length) {
                                    const oldLine = escapeHtml(change.oldLines[i]);
                                    trapCurrentHtml += `<div class="flex bg-red-900/20 hover:bg-red-900/30">
                                    <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${trapCurrentLineNum++}</span>
                                    <span style="white-space: pre; padding-left: 0.5rem;">${oldLine || ' '}</span>
                                </div>`;
                                } else {
                                    trapCurrentHtml += `<div class="flex bg-gray-800/50">
                                    <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                                    <span style="white-space: pre; padding-left: 0.5rem;"></span>
                                </div>`;
                                }
                                if (i < change.newLines.length) {
                                    const newLine = escapeHtml(change.newLines[i]);
                                    trapNewHtml += `<div class="flex bg-green-900/20 hover:bg-green-900/30">
                                    <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${trapNewLineNum++}</span>
                                    <span style="white-space: pre; padding-left: 0.5rem;">${newLine || ' '}</span>
                                </div>`;
                                } else {
                                    trapNewHtml += `<div class="flex bg-gray-800/50">
                                    <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                                    <span style="white-space: pre; padding-left: 0.5rem;"></span>
                                </div>`;
                                }
                            }
                        }
                    }
                }

                // Add trap pipeline section
                html += `
                <div class="border border-gray-600 rounded-lg overflow-hidden mt-4">
                    <div class="bg-gray-700 px-4 py-2 border-b border-gray-600">
                        <h4 class="text-white font-semibold">
                            ${escapeHtml(network.network_name)} - Trap Pipeline${trapBadge}
                        </h4>
                        <p class="text-sm text-gray-400">Pipeline: ${escapeHtml(trapPipeline.pipeline_name)}</p>
                    </div>
                    <div style="display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 0; height: 400px;">
                        <div class="p-4 bg-gray-700 border-r border-gray-600" style="display: flex; flex-direction: column; height: 100%; min-height: 0; min-width: 0;">
                            <div class="mb-2" style="flex-shrink: 0;">
                                <h5 class="text-sm font-semibold text-white">${trapPipeline.action === 'create' ? 'No Existing Trap Pipeline' : 'Current Trap Pipeline'}</h5>
                            </div>
                            <div class="bg-gray-800 rounded border border-gray-600 network-diff-scroll-panel" style="flex: 1; overflow-y: auto; overflow-x: auto; min-height: 0; min-width: 0;">
                                <div class="p-2 text-sm text-gray-300 font-mono">${trapCurrentHtml}</div>
                            </div>
                        </div>
                        <div class="p-4 bg-gray-700" style="display: flex; flex-direction: column; height: 100%; min-height: 0; min-width: 0;">
                            <div class="mb-2" style="flex-shrink: 0;">
                                <h5 class="text-sm font-semibold text-white">${trapPipeline.action === 'delete' ? 'Pipeline Will Be Deleted' : 'New Trap Pipeline (After Deploy)'}</h5>
                            </div>
                            <div class="bg-gray-800 rounded border border-gray-600 network-diff-scroll-panel" style="flex: 1; overflow-y: auto; overflow-x: auto; min-height: 0; min-width: 0;">
                                <div class="p-2 text-sm text-gray-300 font-mono">${trapNewHtml}</div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            }
        }

        // Handle discovery pipeline if it exists
        if (network.discovery_pipeline) {
            const discoveryPipeline = network.discovery_pipeline;
            const discoveryCurrentLines = discoveryPipeline.current ? discoveryPipeline.current.split('\n') : [];
            const discoveryNewLines = discoveryPipeline.new ? discoveryPipeline.new.split('\n') : [];

            // Check if there are actual changes in the discovery pipeline
            let discoveryHasChanges = false;
            if (discoveryPipeline.action === 'create' || discoveryPipeline.action === 'delete') {
                discoveryHasChanges = true;
            } else if (discoveryPipeline.action === 'update') {
                // Compare current and new to see if there are actual differences
                const discoveryLineDiff = computeLineDiff(discoveryCurrentLines, discoveryNewLines);
                discoveryHasChanges = discoveryLineDiff.some(change => change.type !== 'equal');
            }

            // Only render discovery pipeline if there are actual changes
            if (discoveryHasChanges) {
                // Count discovery pipeline in summary only if there are changes
                if (discoveryPipeline.action === 'create') {
                    newPipelinesCount++;
                } else if (discoveryPipeline.action === 'update') {
                    networksWithChanges++;
                } else if (discoveryPipeline.action === 'delete') {
                    deletedPipelinesCount++;
                }

                let discoveryBadge = '';
                let discoveryCurrentHtml = '';
                let discoveryNewHtml = '';
                let discoveryCurrentLineNum = 1;
                let discoveryNewLineNum = 1;

                if (discoveryPipeline.action === 'create') {
                    discoveryBadge = '<span class="ml-2 px-2 py-0.5 text-xs bg-green-600 text-white rounded">NEW DISCOVERY PIPELINE</span>';

                    // Show new discovery pipeline
                    for (let i = 0; i < discoveryNewLines.length; i++) {
                        const line = escapeHtml(discoveryNewLines[i]);

                        discoveryCurrentHtml += `<div class="flex bg-gray-800/50">
                            <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                            <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                        </div>`;

                        discoveryNewHtml += `<div class="flex bg-green-900/20 hover:bg-green-900/30">
                            <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${discoveryNewLineNum++}</span>
                            <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                        </div>`;
                    }
                } else if (discoveryPipeline.action === 'delete') {
                    discoveryBadge = '<span class="ml-2 px-2 py-0.5 text-xs bg-red-600 text-white rounded">DELETING DISCOVERY PIPELINE</span>';

                    // Show discovery pipeline being deleted
                    for (let i = 0; i < discoveryCurrentLines.length; i++) {
                        const line = escapeHtml(discoveryCurrentLines[i]);

                        discoveryCurrentHtml += `<div class="flex bg-red-900/20 hover:bg-red-900/30">
                            <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${discoveryCurrentLineNum++}</span>
                            <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                        </div>`;

                        discoveryNewHtml += `<div class="flex bg-gray-800/50">
                            <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                            <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                        </div>`;
                    }
                } else if (discoveryPipeline.action === 'update') {
                    discoveryBadge = '<span class="ml-2 px-2 py-0.5 text-xs bg-blue-600 text-white rounded">UPDATING DISCOVERY PIPELINE</span>';

                    // Compute diff for discovery pipeline
                    const discoveryLineDiff = computeLineDiff(discoveryCurrentLines, discoveryNewLines);

                    for (const change of discoveryLineDiff) {
                        if (change.type === 'equal') {
                            for (let i = 0; i < change.lines.length; i++) {
                                const line = escapeHtml(change.lines[i]);
                                discoveryCurrentHtml += `<div class="flex hover:bg-gray-700/30">
                                    <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${discoveryCurrentLineNum++}</span>
                                    <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                                </div>`;
                                discoveryNewHtml += `<div class="flex hover:bg-gray-700/30">
                                    <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${discoveryNewLineNum++}</span>
                                    <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                                </div>`;
                            }
                        } else if (change.type === 'delete') {
                            for (let i = 0; i < change.lines.length; i++) {
                                const line = escapeHtml(change.lines[i]);
                                discoveryCurrentHtml += `<div class="flex bg-red-900/20 hover:bg-red-900/30">
                                    <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${discoveryCurrentLineNum++}</span>
                                    <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                                </div>`;
                                discoveryNewHtml += `<div class="flex bg-gray-800/50">
                                    <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                                    <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                                </div>`;
                            }
                        } else if (change.type === 'insert') {
                            for (let i = 0; i < change.lines.length; i++) {
                                const line = escapeHtml(change.lines[i]);
                                discoveryCurrentHtml += `<div class="flex bg-gray-800/50">
                                    <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                                    <span style="white-space: pre; padding-left: 0.5rem; color: #555;"></span>
                                </div>`;
                                discoveryNewHtml += `<div class="flex bg-green-900/20 hover:bg-green-900/30">
                                    <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${discoveryNewLineNum++}</span>
                                    <span style="white-space: pre; padding-left: 0.5rem;">${line || ' '}</span>
                                </div>`;
                            }
                        } else if (change.type === 'replace') {
                            const maxLen = Math.max(change.oldLines.length, change.newLines.length);
                            for (let i = 0; i < maxLen; i++) {
                                if (i < change.oldLines.length) {
                                    const oldLine = escapeHtml(change.oldLines[i]);
                                    discoveryCurrentHtml += `<div class="flex bg-red-900/20 hover:bg-red-900/30">
                                        <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${discoveryCurrentLineNum++}</span>
                                        <span style="white-space: pre; padding-left: 0.5rem;">${oldLine || ' '}</span>
                                    </div>`;
                                } else {
                                    discoveryCurrentHtml += `<div class="flex bg-gray-800/50">
                                        <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                                        <span style="white-space: pre; padding-left: 0.5rem;"></span>
                                    </div>`;
                                }
                                if (i < change.newLines.length) {
                                    const newLine = escapeHtml(change.newLines[i]);
                                    discoveryNewHtml += `<div class="flex bg-green-900/20 hover:bg-green-900/30">
                                        <span class="inline-block w-12 text-gray-500 text-right pr-3 select-none flex-shrink-0">${discoveryNewLineNum++}</span>
                                        <span style="white-space: pre; padding-left: 0.5rem;">${newLine || ' '}</span>
                                    </div>`;
                                } else {
                                    discoveryNewHtml += `<div class="flex bg-gray-800/50">
                                        <span class="inline-block w-12 text-gray-600 text-right pr-3 select-none flex-shrink-0">-</span>
                                        <span style="white-space: pre; padding-left: 0.5rem;"></span>
                                    </div>`;
                                }
                            }
                        }
                    }
                }

                // Add discovery pipeline section
                html += `
                    <div class="border border-gray-600 rounded-lg overflow-hidden mt-4">
                        <div class="bg-gray-700 px-4 py-2 border-b border-gray-600">
                            <h4 class="text-white font-semibold">
                                ${escapeHtml(network.network_name)} - Discovery Pipeline${discoveryBadge}
                            </h4>
                            <p class="text-sm text-gray-400">Pipeline: ${escapeHtml(discoveryPipeline.pipeline_name)}</p>
                        </div>
                        <div style="display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 0; height: 400px;">
                            <div class="p-4 bg-gray-700 border-r border-gray-600" style="display: flex; flex-direction: column; height: 100%; min-height: 0; min-width: 0;">
                                <div class="mb-2" style="flex-shrink: 0;">
                                    <h5 class="text-sm font-semibold text-white">${discoveryPipeline.action === 'create' ? 'No Existing Discovery Pipeline' : 'Current Discovery Pipeline'}</h5>
                                </div>
                                <div class="bg-gray-800 rounded border border-gray-600 network-diff-scroll-panel" style="flex: 1; overflow-y: auto; overflow-x: auto; min-height: 0; min-width: 0;">
                                    <div class="p-2 text-sm text-gray-300 font-mono">${discoveryCurrentHtml}</div>
                                </div>
                            </div>
                            <div class="p-4 bg-gray-700" style="display: flex; flex-direction: column; height: 100%; min-height: 0; min-width: 0;">
                                <div class="mb-2" style="flex-shrink: 0;">
                                    <h5 class="text-sm font-semibold text-white">${discoveryPipeline.action === 'delete' ? 'Pipeline Will Be Deleted' : 'New Discovery Pipeline (After Deploy)'}</h5>
                                </div>
                                <div class="bg-gray-800 rounded border border-gray-600 network-diff-scroll-panel" style="flex: 1; overflow-y: auto; overflow-x: auto; min-height: 0; min-width: 0;">
                                    <div class="p-2 text-sm text-gray-300 font-mono">${discoveryNewHtml}</div>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            }
        }
    }

    // If no networks have changes, show a message
    if (networksWithChanges === 0 && newPipelinesCount === 0 && deletedPipelinesCount === 0) {
        container.innerHTML = `
            <div class="text-center p-8">
                <div class="inline-flex items-center justify-center w-16 h-16 bg-green-600/20 rounded-full mb-4">
                    <svg class="w-8 h-8 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                    </svg>
                </div>
                <h3 class="text-xl font-semibold text-white mb-2">No Changes Detected</h3>
                <p class="text-gray-400">All network pipelines are up to date. No changes need to be deployed.</p>
            </div>
        `;

        // Disable the deploy button since there's nothing to deploy
        _snmpNoChangesBlocked = true;
        _updateDeployButtonState();
        return;
    }

    // Add stats at the top
    let statsHtml = '<div class="mb-4 p-4 bg-gray-700 rounded-lg border border-gray-600">';
    statsHtml += '<h3 class="text-white font-semibold mb-2">Changes Summary</h3>';
    statsHtml += '<div class="flex gap-4 text-sm">';

    if (newPipelinesCount > 0) {
        statsHtml += `<div class="flex items-center gap-2">
            <span class="px-2 py-0.5 text-xs bg-green-600 text-white rounded">NEW</span>
            <span class="text-gray-300">${newPipelinesCount} new pipeline${newPipelinesCount !== 1 ? 's' : ''}</span>
        </div>`;
    }

    if (networksWithChanges > 0) {
        statsHtml += `<div class="flex items-center gap-2">
            <span class="px-2 py-0.5 text-xs bg-blue-600 text-white rounded">MODIFIED</span>
            <span class="text-gray-300">${networksWithChanges} modified pipeline${networksWithChanges !== 1 ? 's' : ''}</span>
        </div>`;
    }

    if (deletedPipelinesCount > 0) {
        statsHtml += `<div class="flex items-center gap-2">
            <span class="px-2 py-0.5 text-xs bg-red-600 text-white rounded">DELETED</span>
            <span class="text-gray-300">${deletedPipelinesCount} deleted pipeline${deletedPipelinesCount !== 1 ? 's' : ''}</span>
        </div>`;
    }

    statsHtml += '</div></div>';

    container.innerHTML = statsHtml + html;

    // Synchronize scrolling for each network's diff panels
    const allSections = container.querySelectorAll('.border.border-gray-600');
    allSections.forEach(section => {
        const panels = section.querySelectorAll('.network-diff-scroll-panel');
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
    });
}

/**
 * Confirm and deploy the SNMP configuration
 */
async function confirmDeployConfiguration() {
    const confirmButton = document.getElementById('confirmDeployButton');
    const originalText = confirmButton.textContent;

    // Disable button and show loading state
    const changeCount = window.snmpChangeCount || 0;
    const isLargeDeployment = changeCount > 100;

    confirmButton.disabled = true;
    confirmButton.textContent = isLargeDeployment
        ? 'Deploying... (this may take several minutes)'
        : 'Deploying...';
    confirmButton.classList.add('opacity-50', 'cursor-not-allowed');

    // Show progress toast - conditional message based on change count
    const message = isLargeDeployment
        ? 'Deployment started. This may take several minutes for large configurations...'
        : 'Deployment started!';
    showToast(message, 'info');

    try {
        // Create AbortController with 10-minute timeout for large deployments
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 600000); // 10 minutes
        
        const response = await fetch('/SNMP/DeployConfiguration/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
                'Content-Type': 'application/json'
            },
            signal: controller.signal
        });
        
        clearTimeout(timeoutId);

        if (response.status === 403) {
            showToast('Access denied: Admin role required', 'error');
            if (confirmButton) confirmButton.disabled = false;
            return;
        }

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Failed to deploy configuration: ${response.status} - ${errorText}`);
        }

        const result = await response.json();

        if (result.success) {
            // Show success toast
            let message = result.message || 'Configuration deployed successfully!';
            showToast(message, 'success');

            // Show warnings as separate toasts if any
            if (result.errors && result.errors.length > 0) {
                result.errors.forEach(error => {
                    showToast(error, 'warning');
                });
            }

            // Close the modal
            hideSnmpDiffModal();

            // Refresh the undeployed changes indicator
            if (typeof window.triggerUndeployedChangesCheck === 'function') {
                window.triggerUndeployedChangesCheck();
            }

            // Optionally reload the page to reflect changes
            // window.location.reload();
        } else {
            throw new Error(result.error || 'Unknown error occurred');
        }

    } catch (error) {
        console.error('Error deploying configuration:', error);
        
        // Handle timeout/abort errors specifically
        if (error.name === 'AbortError') {
            showToast('Deployment timed out after 10 minutes. Check server logs for status.', 'error');
        } else {
            showToast('Failed to deploy configuration: ' + error.message, 'error');
        }
    } finally {
        // Re-enable button
        confirmButton.disabled = false;
        confirmButton.textContent = originalText;
        confirmButton.classList.remove('opacity-50', 'cursor-not-allowed');
    }
}

