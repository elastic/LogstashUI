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

  function renderSelect(targets, selectedId) {
    const select = document.getElementById('simTargetSelect');
    const wrap = document.getElementById('simTargetSelectWrap');
    if (!select || !wrap) return;

    select.innerHTML = '';
    if (!targets || targets.length === 0) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = 'No sim agents';
      select.appendChild(opt);
      select.disabled = true;
      wrap.title = 'Enroll a simulate agent or start embedded mode';
      return;
    }

    select.disabled = false;
    targets.forEach((t) => {
      const opt = document.createElement('option');
      opt.value = String(t.connection_id);
      opt.textContent = t.label || t.name || `agent ${t.connection_id}`;
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
    select.addEventListener('change', async () => {
      await selectTarget(select.value);
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
