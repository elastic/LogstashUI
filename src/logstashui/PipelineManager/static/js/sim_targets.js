//Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
//or more contributor license agreements. Licensed under the Elastic License;
//you may not use this file except in compliance with the Elastic License.

/**
 * Simulation target selection for the pipeline editor.
 * - Loads targets from GetSimulationTargets
 * - Persists choice via SelectSimulationTarget (session)
 * - Exposes window.getSimConnectionId() for fetch/htmx callers
 */

(function () {
  const STORAGE_KEY = 'logstashui_sim_connection_id';

  function getCsrfToken() {
    return (
      document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
      document.cookie
        .split('; ')
        .find((r) => r.startsWith('csrftoken='))
        ?.split('=')[1] ||
      ''
    );
  }

  window.getSimConnectionId = function getSimConnectionId() {
    const select = document.getElementById('simTargetSelect');
    if (select && select.value) {
      return select.value;
    }
    if (window.__simConnectionId) {
      return String(window.__simConnectionId);
    }
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) return stored;
    } catch (_) {
      /* ignore */
    }
    return null;
  };

  window.appendSimConnectionToFormData = function appendSimConnectionToFormData(formData) {
    const id = window.getSimConnectionId();
    if (id) {
      formData.append('sim_connection_id', id);
    }
    return formData;
  };

  window.simConnectionHtmxValues = function simConnectionHtmxValues(extra) {
    const values = Object.assign({}, extra || {});
    const id = window.getSimConnectionId();
    if (id) {
      values.sim_connection_id = id;
    }
    return values;
  };

  async function selectTarget(connectionId) {
    if (!connectionId) return;
    window.__simConnectionId = connectionId;
    try {
      localStorage.setItem(STORAGE_KEY, String(connectionId));
    } catch (_) {
      /* ignore */
    }
    try {
      await fetch('/ConnectionManager/SelectSimulationTarget/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken(),
        },
        body: JSON.stringify({ connection_id: Number(connectionId) }),
      });
    } catch (e) {
      console.warn('[sim targets] failed to persist selection', e);
    }
  }

  function shortLabel(t) {
    if (t.label) return t.label;
    if (t.policy_type === 'EMBEDDED') return 'embedded';
    if (t.instance_id != null) return `simulate-${t.instance_id}`;
    return t.name || `agent ${t.connection_id}`;
  }

  function detailLabel(t) {
    if (t.detail) return t.detail;
    const parts = [shortLabel(t)];
    if (t.host) parts.push(t.host);
    if (t.logstash_version) parts.push(`Logstash ${t.logstash_version}`);
    return parts.join(' · ');
  }

  function syncSelectTitle(select) {
    if (!select) return;
    const opt = select.options[select.selectedIndex];
    const detail =
      (opt && (opt.dataset.detail || opt.getAttribute('title'))) ||
      select.value ||
      '';
    select.title = detail
      ? `${detail} — choose target for simulation`
      : 'Choose which agent runs this simulation';
  }

  function renderSelect(targets, selectedId) {
    const select = document.getElementById('simTargetSelect');
    const wrap = document.getElementById('simTargetSelectWrap');
    if (!select || !wrap) return;

    select.innerHTML = '';
    if (!targets || targets.length === 0) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = 'None';
      select.appendChild(opt);
      select.disabled = true;
      wrap.title = 'Enroll a simulate agent or start embedded mode';
      select.title = wrap.title;
      return;
    }

    select.disabled = false;
    targets.forEach((t) => {
      const opt = document.createElement('option');
      opt.value = String(t.connection_id);
      // Closed control shows terse label; open list + title show host/version
      opt.textContent = shortLabel(t);
      opt.dataset.detail = detailLabel(t);
      opt.dataset.policyType = t.policy_type || '';
      opt.title = detailLabel(t);
      select.appendChild(opt);
    });

    let chosen = selectedId != null ? String(selectedId) : null;
    if (!chosen || !targets.some((t) => String(t.connection_id) === chosen)) {
      try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored && targets.some((t) => String(t.connection_id) === stored)) {
          chosen = stored;
        }
      } catch (_) {
        /* ignore */
      }
    }
    if (!chosen) {
      chosen = String(targets[0].connection_id);
    }
    select.value = chosen;
    window.__simConnectionId = chosen;
    syncSelectTitle(select);

    // Hide dropdown chrome when only one target (still set selection)
    if (targets.length === 1) {
      wrap.classList.add('sim-target-single');
    } else {
      wrap.classList.remove('sim-target-single');
    }
  }

  async function loadSimTargets() {
    try {
      const resp = await fetch('/ConnectionManager/GetSimulationTargets/');
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      const targets = data.targets || [];
      renderSelect(targets, data.selected_connection_id);
      // Ensure server session matches UI
      const id = window.getSimConnectionId();
      if (id) {
        await selectTarget(id);
      }
      return targets;
    } catch (e) {
      console.error('[sim targets] load failed', e);
      renderSelect([], null);
      return [];
    }
  }

  function bindSelect() {
    const select = document.getElementById('simTargetSelect');
    if (!select || select.dataset.bound === '1') return;
    select.dataset.bound = '1';
    // Debounce rapid dropdown flips so we only warm the final selection
    let targetChangeTimer = null;
    let targetChangeSeq = 0;

    select.addEventListener('change', async () => {
      syncSelectTitle(select);
      const selectedValue = select.value;
      const seq = ++targetChangeSeq;

      await selectTarget(selectedValue);
      if (seq !== targetChangeSeq) return; // superseded by a newer change

      // Keep modal/JS simulationMode in sync with selected target policy type
      try {
        const opt = select.options[select.selectedIndex];
        const pt = (opt && opt.dataset.policyType) || '';
        const mode =
          pt === 'EMBEDDED' || (opt && opt.textContent.trim() === 'embedded')
            ? 'embedded'
            : 'simulate';
        window.simulationMode = mode;
        if (typeof simulationMode !== 'undefined') {
          // pipeline_editor declares var simulationMode
          // eslint-disable-next-line no-global-assign
          simulationMode = mode;
        }
        const modeLabel = document.getElementById('simModalModeLabel');
        if (modeLabel) modeLabel.textContent = mode;
        const note = document.getElementById('simEmbeddedModeNote');
        if (note) {
          note.classList.toggle('hidden', mode !== 'embedded');
        }
      } catch (_) {
        /* ignore */
      }

      // Slots are per-agent. Clear immediately so Run cannot reuse the other agent.
      if (typeof window.clearSimulationSessionSlot === 'function') {
        window.clearSimulationSessionSlot('sim target changed');
      } else {
        window.simulationSessionSlotId = null;
        window.simulationSessionConnectionId = null;
        window.currentSlotId = null;
        if (typeof currentSlotId !== 'undefined') {
          currentSlotId = null;
        }
      }

      if (typeof window.setPipelineSlotChip === 'function') {
        window.setPipelineSlotChip('warming', {
          title: 'Switching simulation agent…',
        });
      }

      // Debounce warm: rapid embedded↔simulate flips only allocate for the last pick
      if (targetChangeTimer) {
        clearTimeout(targetChangeTimer);
      }
      targetChangeTimer = setTimeout(() => {
        targetChangeTimer = null;
        if (seq !== targetChangeSeq) return;
        if (String(window.getSimConnectionId?.() || '') !== String(selectedValue || '')) {
          return;
        }
        if (typeof window.warmSlotForCurrentTarget === 'function') {
          window
            .warmSlotForCurrentTarget({ showWarming: true, forceNew: true, maxAttempts: 2 })
            .catch((e) => {
              console.error('[sim targets] re-warm after target change failed', e);
            });
        } else if (typeof window.triggerPipelineWarmingAndChecking === 'function') {
          window.triggerPipelineWarmingAndChecking({
            force: true,
            fromPageLoad: true,
            useFetch: true,
          });
        }
      }, 200);

      // Refresh status chips for the newly selected agent
      if (typeof checkAgentStatus === 'function') {
        checkAgentStatus();
      }
      if (typeof checkLogstashState === 'function') {
        checkLogstashState();
      }
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    bindSelect();
    loadSimTargets();
  });

  window.loadSimTargets = loadSimTargets;
  window.selectSimTarget = selectTarget;
})();
